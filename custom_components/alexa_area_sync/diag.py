"""Read-only diagnostics for the Alexa /api/phoenix appliance payload.

Purpose: work out *where* (if anywhere) an appliance record carries the HA
entity_id it was built from, so the matcher can be fixed. Everything here is GET
only. Amazon identifiers, tokens and Echo serial numbers are redacted before anything
leaves the box; device names are kept, since matching by name is what this debugs.
"""

from __future__ import annotations

import re
from typing import Any

# HA domains an entity_id can start with (superset of the controllable set — we want
# to *detect* an entity_id wherever it hides, not just controllable ones). Ordered
# LONGEST-FIRST so alternation prefers e.g. `binary_sensor` over `sensor`.
_HA_DOMAIN_LIST = sorted(
    (
        "light", "switch", "climate", "fan", "cover", "lock", "media_player",
        "humidifier", "water_heater", "vacuum", "camera", "sensor", "binary_sensor",
        "scene", "script", "input_boolean", "input_number", "input_select", "number",
        "select", "button", "group", "lawn_mower", "valve", "alarm_control_panel",
    ),
    key=len,
    reverse=True,
)
# entity_id-shaped: <domain><sep><object_id> where sep is '.' or '#' (Alexa/HA cloud
# encodes the dot as '#' inside endpoint/appliance ids). The lookbehind excludes a
# preceding *alphanumeric* but ALLOWS '_' / '#' / '.' / '-', so an entity_id embedded
# in an Amazon id like `SKILL_<stage>_light#gf_kitchen_lights` is still detected.
_ENTITY_RE = re.compile(
    r"(?<![a-zA-Z0-9])(?:" + "|".join(_HA_DOMAIN_LIST) + r")[.#][a-z0-9_]+"
)

# Keys whose *values* are Amazon identifiers/tokens — redact these in samples.
_REDACT_KEYS = {
    "applianceId",
    "entityId",
    "endpointId",
    "reachabilityHint",
    "applianceKey",
    "mergedApplianceIds",
    "aliases",
    "applianceNetworkState",
    "connectedVia",
    # Echo serial numbers
    "alexaDeviceIdentifierList",
    "deviceSerialNumber",
    "serialNumber",
    "dsn",
}


def _redact_value(val: str) -> str:
    """Redact an Amazon id but keep any embedded HA-entity-id tail visible."""
    m = _ENTITY_RE.search(val)
    if m:
        return f"<redacted>::{m.group(0)}"
    if len(val) > 12:
        return f"<redacted:{len(val)}chars>"
    return "<redacted>"


def _redact(obj: Any, key: str | None = None) -> Any:
    if isinstance(obj, dict):
        return {k: _redact(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v, key) for v in obj]
    if isinstance(obj, str) and key in _REDACT_KEYS:
        return _redact_value(obj)
    return obj


def _find_entity_ids(obj: Any, path: str = "") -> list[tuple[str, str]]:
    """Return (json_path, matched_entity_id) for every entity-id-shaped string."""
    hits: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits.extend(_find_entity_ids(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_find_entity_ids(v, f"{path}[{i}]"))
    elif isinstance(obj, str):
        for m in _ENTITY_RE.findall(obj):
            hits.append((path, m))
    return hits


def summarize(raw: list[dict], sample_count: int = 4) -> dict:
    """Build a redacted structural summary of the appliance payload."""
    key_freq: dict[str, int] = {}
    # json_path (with list indices stripped) -> count of appliances where an
    # entity-id-shaped string appears there.
    entity_path_freq: dict[str, int] = {}
    entity_path_example: dict[str, str] = {}
    with_entity = 0

    for rec in raw:
        for k in rec:
            key_freq[k] = key_freq.get(k, 0) + 1
        hits = _find_entity_ids(rec)
        if hits:
            with_entity += 1
        seen_paths: set[str] = set()
        for path, eid in hits:
            norm = re.sub(r"\[\d+\]", "[]", path)
            if norm not in seen_paths:
                seen_paths.add(norm)
                entity_path_freq[norm] = entity_path_freq.get(norm, 0) + 1
                entity_path_example.setdefault(norm, eid)

    samples = [_redact(rec) for rec in raw[:sample_count]]

    return {
        "appliance_count": len(raw),
        "appliances_with_embedded_entity_id": with_entity,
        "top_level_key_frequency": dict(
            sorted(key_freq.items(), key=lambda kv: -kv[1])
        ),
        "entity_id_locations": [
            {
                "json_path": path,
                "appliance_count": cnt,
                "example_value": entity_path_example.get(path, ""),
            }
            for path, cnt in sorted(entity_path_freq.items(), key=lambda kv: -kv[1])
        ],
        "redacted_samples": samples,
    }
