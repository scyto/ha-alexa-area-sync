"""Constants for the Alexa Room Sync integration."""

from __future__ import annotations

DOMAIN = "alexa_room_sync"

# The integration this one piggy-backs on for an authenticated Alexa session.
ALEXA_MEDIA_DOMAIN = "alexa_media"

# The Assist/Cloud exposure key we mirror. Alexa Room Sync only ever considers
# entities that are exposed to Amazon Alexa (via HA Cloud / Nabu Casa).
ASSISTANT_ALEXA = "cloud.alexa"

# Private Alexa API endpoints (reached through alexapy's authenticated session).
EP_GROUP = "/api/phoenix/group"          # GET list, POST create, DELETE /{id}
EP_PHOENIX = "/api/phoenix"              # GET all smart-home appliances

# Config / options keys
CONF_EMAIL = "email"
CONF_DRY_RUN = "dry_run"
CONF_ROOM_PREFIX = "room_prefix"
CONF_INCLUDE_CLIMATE = "include_climate"
CONF_INCLUDE_CHILD_LOCKS = "include_child_locks"
CONF_AREA_NAME_OVERRIDES = "area_name_overrides"
CONF_CONFIRMED = "confirmed_not_dry_run"

DEFAULT_DRY_RUN = True
DEFAULT_ROOM_PREFIX = ""
DEFAULT_INCLUDE_CLIMATE = True
DEFAULT_INCLUDE_CHILD_LOCKS = False

# Services
SERVICE_PREVIEW = "preview"
SERVICE_SYNC_AREA = "sync_area"
SERVICE_SYNC = "sync"
SERVICE_LIST_GROUPS = "list_groups"
SERVICE_DUMP_APPLIANCES = "dump_appliances"

ATTR_AREA_ID = "area_id"

# Domains Alexa treats as controllable "devices" that make sense inside a room.
CONTROLLABLE_DOMAINS = {
    "light",
    "switch",
    "fan",
    "cover",
    "climate",
    "lock",
    "media_player",
    "humidifier",
    "water_heater",
    "vacuum",
    "camera",
}
