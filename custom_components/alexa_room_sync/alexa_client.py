"""Thin client over the *unofficial* Alexa API for smart-home group management.

We do NOT authenticate ourselves. Instead we borrow the live, already-authenticated
``AlexaLogin`` object created by the ``alexa_media`` integration and drive alexapy's
``AlexaAPI._static_request`` primitive. That primitive already handles the session
cookie, the ``csrf`` header and OAuth token refresh, so no credentials, cookies or the
2FA login dance ever live in this integration.

Endpoints (private consumer Alexa API, reached at ``https://alexa.<amazon-domain>``):

* ``GET  /api/phoenix``          -> every smart-home appliance (applianceId, friendlyName, entityId)
* ``GET  /api/phoenix/group``    -> existing groups/rooms
* ``POST /api/phoenix/group``    -> create a group  {"applianceIds": [...], "name": "..."}
* ``DELETE /api/phoenix/group/{id}`` -> delete a group (undo)

The create/delete shape is the one proven by imduffy15's gist and used by the Alexa app;
alexa-remote (node) confirms the GET/DELETE shapes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant

from .const import ALEXA_MEDIA_DOMAIN, EP_GROUP, EP_PHOENIX

_LOGGER = logging.getLogger(__name__)


class AlexaClientError(Exception):
    """Raised when the Alexa side cannot be reached or returns an error."""


@dataclass
class Appliance:
    """A smart-home appliance as Alexa knows it."""

    appliance_id: str
    friendly_name: str
    entity_id: str | None  # HA entity_id if the appliance carries one (Nabu Casa does)


@dataclass
class AlexaGroup:
    """An existing Alexa group/room."""

    group_id: str
    name: str
    appliance_ids: list[str]


def get_login_obj(hass: HomeAssistant, email: str | None = None):
    """Return the authenticated alexapy AlexaLogin from the alexa_media integration.

    If ``email`` is None, return the first configured account. Raises AlexaClientError
    if alexa_media isn't set up or the account/session is missing.
    """
    accounts = (
        hass.data.get(ALEXA_MEDIA_DOMAIN, {}).get("accounts", {})
        if isinstance(hass.data.get(ALEXA_MEDIA_DOMAIN), dict)
        else {}
    )
    if not accounts:
        raise AlexaClientError(
            "alexa_media has no configured accounts. Install and log in to the "
            "Alexa Media Player integration first."
        )
    if email is None:
        email = next(iter(accounts))
    account = accounts.get(email)
    if not account:
        raise AlexaClientError(
            f"No alexa_media account for '{email}'. Available: {list(accounts)}"
        )
    login = account.get("login_obj")
    if login is None:
        raise AlexaClientError(f"alexa_media account '{email}' has no login object yet.")
    status = getattr(login, "status", {}) or {}
    if not status.get("login_successful"):
        raise AlexaClientError(
            f"alexa_media account '{email}' is not logged in "
            "(re-authenticate Alexa Media Player)."
        )
    return login


def list_configured_emails(hass: HomeAssistant) -> list[str]:
    """Return the emails alexa_media currently has configured."""
    data = hass.data.get(ALEXA_MEDIA_DOMAIN)
    if not isinstance(data, dict):
        return []
    return list(data.get("accounts", {}))


async def _request(login, method: str, uri: str, data: dict | None = None) -> Any:
    """Call the private Alexa API via alexapy's authenticated primitive."""
    # Imported lazily: alexapy is provided at runtime by alexa_media's requirements.
    from alexapy import AlexaAPI  # noqa: PLC0415

    try:
        resp = await AlexaAPI._static_request(  # noqa: SLF001 - the documented reuse path
            method, login, uri, data=data
        )
    except Exception as err:  # noqa: BLE001 - surface any alexapy/login failure uniformly
        raise AlexaClientError(f"{method.upper()} {uri} failed: {err}") from err
    if resp is None:
        raise AlexaClientError(f"{method.upper()} {uri} returned no response")
    if getattr(resp, "status", 200) >= 400:
        text = ""
        try:
            text = await resp.text()
        except Exception:  # noqa: BLE001
            pass
        raise AlexaClientError(
            f"{method.upper()} {uri} -> HTTP {resp.status}: {text[:300]}"
        )
    if method.lower() == "delete":
        return True
    try:
        return await resp.json()
    except Exception:  # noqa: BLE001
        return {}


def _walk_appliance_dicts(obj: Any):
    """Yield every dict that looks like an appliance record.

    The ``/api/phoenix`` payload nests appliances deeply under stringified
    ``networkDetail`` -> locationDetails -> amazonBridgeDetails -> applianceDetails.
    Rather than hard-code the (occasionally-changing) path, walk the whole tree and
    pick out anything carrying an ``applianceId``.
    """
    if isinstance(obj, dict):
        if "applianceId" in obj and isinstance(obj.get("applianceId"), str):
            yield obj
        for value in obj.values():
            yield from _walk_appliance_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_appliance_dicts(value)


def _extract_entity_id(appliance: dict) -> str | None:
    """Best-effort pull of the HA entity_id an Alexa appliance was built from.

    Nabu Casa appliances carry the HA entity_id, most reliably inside
    ``additionalApplianceDetails`` but sometimes as a ``domain.object_id``-shaped
    ``entityId``/alias. We only accept values that look like an HA entity_id.
    """

    def looks_like_entity_id(val: Any) -> str | None:
        if isinstance(val, str) and "." in val and " " not in val:
            head = val.split(".", 1)[0]
            if head.isidentifier():
                return val
        return None

    details = appliance.get("additionalApplianceDetails")
    if isinstance(details, dict):
        for key in ("entity_id", "entityId", "id"):
            found = looks_like_entity_id(details.get(key))
            if found:
                return found
    return looks_like_entity_id(appliance.get("entityId"))


async def _fetch_appliance_tree(login) -> Any:
    """Fetch /api/phoenix and return the parsed appliance tree.

    /api/phoenix returns {"networkDetail": "<stringified json>"} (plus other keys);
    we un-stringify networkDetail when present.
    """
    payload = await _request(login, "get", EP_PHOENIX)
    network_detail = payload.get("networkDetail") if isinstance(payload, dict) else None
    tree: Any = payload
    if isinstance(network_detail, str):
        try:
            tree = json.loads(network_detail)
        except json.JSONDecodeError:
            tree = payload
    return tree


async def get_raw_appliance_dicts(login) -> list[dict]:
    """Return every raw appliance record dict (unflattened) for diagnostics."""
    tree = await _fetch_appliance_tree(login)
    out: list[dict] = []
    seen_ids: set[str] = set()
    for rec in _walk_appliance_dicts(tree):
        aid = rec.get("applianceId")
        if aid and aid in seen_ids:
            continue
        if aid:
            seen_ids.add(aid)
        out.append(rec)
    return out


async def get_appliances(login) -> list[Appliance]:
    """Fetch and flatten every smart-home appliance Alexa knows about."""
    tree = await _fetch_appliance_tree(login)

    seen: dict[str, Appliance] = {}
    for rec in _walk_appliance_dicts(tree):
        aid = rec.get("applianceId")
        if not aid or aid in seen:
            continue
        name = rec.get("friendlyName") or rec.get("friendlyDescription") or ""
        seen[aid] = Appliance(
            appliance_id=aid,
            friendly_name=str(name).strip(),
            entity_id=_extract_entity_id(rec),
        )
    return list(seen.values())


async def get_groups(login) -> list[AlexaGroup]:
    """Fetch existing Alexa groups/rooms."""
    payload = await _request(login, "get", EP_GROUP)
    groups: list[AlexaGroup] = []
    raw = []
    if isinstance(payload, dict):
        raw = payload.get("applianceGroups") or payload.get("groups") or []
    elif isinstance(payload, list):
        raw = payload
    for g in raw:
        if not isinstance(g, dict):
            continue
        gid = g.get("groupId") or g.get("id") or g.get("entityId") or ""
        groups.append(
            AlexaGroup(
                group_id=str(gid),
                name=str(g.get("name", "")).strip(),
                appliance_ids=list(g.get("applianceIds", []) or []),
            )
        )
    return groups


async def create_group(login, name: str, appliance_ids: list[str]) -> dict:
    """Create a new Alexa group/room containing the given appliances."""
    if not appliance_ids:
        raise AlexaClientError(f"Refusing to create empty group '{name}'")
    return await _request(
        login,
        "post",
        EP_GROUP,
        data={"applianceIds": appliance_ids, "name": name},
    )


async def delete_group(login, group_id: str) -> bool:
    """Delete an Alexa group by id (undo)."""
    if not group_id:
        raise AlexaClientError("delete_group requires a group_id")
    return await _request(login, "delete", f"{EP_GROUP}/{group_id}")
