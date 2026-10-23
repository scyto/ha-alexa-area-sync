"""Devices exposed to Alexa in HA that Alexa doesn't know about.

HA Cloud normally tells Alexa about every exposed entity. Occasionally that hand-off
is lost (an integration that re-creates its entities is one way), and the device
silently drops out of Alexa. Each run lists these, and after a grace period asks HA
Cloud to resend just those entities to Alexa: the same report its own "Sync entities"
button sends, without the deletes that turning exposure off and on would cause.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# A newly exposed device normally reaches Alexa within a minute or two.
GRACE = timedelta(minutes=10)
# Don't ask HA Cloud more often than this for the same account.
MIN_INTERVAL = timedelta(hours=1)


def missing_in_alexa(plan) -> dict[str, str]:
    """entity_id -> name for exposed, area-assigned devices Alexa doesn't list,
    before any group filter (skipped areas, domains kept out of groups)."""
    return dict(plan.not_in_alexa)


def _state(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    return hass.data.setdefault(DOMAIN, {}).setdefault("_missing", {}).setdefault(
        entry.entry_id, {"first_seen": {}, "last_resend": None}
    )


def due_for_resend(hass: HomeAssistant, entry: ConfigEntry,
                   missing: dict[str, str]) -> list[str]:
    """Track when each device was first seen missing; return the ones past the grace
    period, or [] if we asked HA Cloud too recently."""
    now = dt_util.utcnow()
    state = _state(hass, entry)
    first_seen: dict[str, datetime] = state["first_seen"]
    for entity_id in list(first_seen):
        if entity_id not in missing:
            del first_seen[entity_id]
    for entity_id in missing:
        first_seen.setdefault(entity_id, now)
    last = state["last_resend"]
    if last is not None and now - last < MIN_INTERVAL:
        return []
    return [e for e, seen in first_seen.items() if now - seen >= GRACE]


async def resend_via_cloud(hass: HomeAssistant, entry: ConfigEntry,
                           entity_ids: list[str]) -> str | None:
    """Ask HA Cloud to send Alexa an add-or-update report for ``entity_ids``.

    Returns None on success, else why it couldn't. HA Cloud's Alexa config isn't a
    public API for other integrations, so every failure is caught and reported.
    """
    _state(hass, entry)["last_resend"] = dt_util.utcnow()
    try:
        from homeassistant.components.alexa import state_report  # noqa: PLC0415
        from homeassistant.components.cloud.const import DATA_CLOUD  # noqa: PLC0415

        cloud = hass.data.get(DATA_CLOUD)
        if cloud is None or not cloud.is_logged_in:
            return "HA Cloud isn't logged in"
        config = await cloud.client.get_alexa_config()
        if not config.enabled:
            return "Alexa isn't enabled in HA Cloud"
        await config.async_get_access_token()
        resp = await state_report.async_send_add_or_update_message(hass, config, entity_ids)
        status = getattr(resp, "status", 200)
        if status >= 400:
            return f"Alexa answered HTTP {status}"
    except Exception as err:  # noqa: BLE001 - private API: never break a sync over it
        _LOGGER.warning("Couldn't ask HA Cloud to resend %s to Alexa: %s", entity_ids, err)
        return str(err) or type(err).__name__
    _LOGGER.info("Asked HA Cloud to resend %s to Alexa", entity_ids)
    return None
