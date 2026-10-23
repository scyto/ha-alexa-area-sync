"""Config & options flow for Alexa Area Sync."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import AreaSelector, AreaSelectorConfig

from . import alexa_client as ac
from . import runner
from .const import (
    CONF_AREA_NAME_OVERRIDES,
    CONF_AUTO_SYNC,
    CONF_CONFIRMED,
    CONF_DRY_RUN,
    CONF_EMAIL,
    CONF_EXCLUDED_AREAS,
    CONF_FLOOR_GROUPS,
    CONF_FLOOR_LIGHTS_ONLY,
    CONF_RESEND_MISSING,
    CONF_INCLUDE_CHILD_LOCKS,
    CONF_INCLUDE_ECHOS,
    CONF_INCLUDE_CLIMATE,
    CONF_ROOM_PREFIX,
    DEFAULT_AUTO_SYNC,
    DEFAULT_DRY_RUN,
    DEFAULT_FLOOR_GROUPS,
    DEFAULT_FLOOR_LIGHTS_ONLY,
    DEFAULT_RESEND_MISSING,
    DEFAULT_INCLUDE_CHILD_LOCKS,
    DEFAULT_INCLUDE_ECHOS,
    DEFAULT_INCLUDE_CLIMATE,
    DEFAULT_ROOM_PREFIX,
    ASSISTANT_ALEXA,
    DOMAIN,
)


def _cloud_note(hass) -> str:
    """A warning for the setup form if HA Cloud won't give Alexa any devices to group:
    not logged in, Alexa turned off in it, or nothing exposed to Alexa."""
    try:
        from homeassistant.components.cloud.const import DATA_CLOUD  # noqa: PLC0415

        cloud = hass.data.get(DATA_CLOUD)
    except ImportError:
        cloud = None
    if cloud is None or not getattr(cloud, "is_logged_in", False):
        return ("\n\n**Note:** Home Assistant Cloud isn't logged in, so Alexa won't see "
                "your Home Assistant devices and there will be nothing to group.")
    try:
        from homeassistant.components.homeassistant.exposed_entities import (  # noqa: PLC0415
            async_should_expose,
        )
        from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

        exposed = sum(
            1 for e in er.async_get(hass).entities.values()
            if async_should_expose(hass, ASSISTANT_ALEXA, e.entity_id)
        )
    except Exception:  # noqa: BLE001 - only a hint on the form
        return ""
    if not exposed:
        return ("\n\n**Note:** nothing is exposed to Alexa yet (Settings > Voice "
                "assistants > Expose), so there will be nothing to group.")
    return ""


class AlexaAreaSyncConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Alexa Area Sync."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        emails = ac.list_configured_emails(self.hass)
        if not emails:
            # Say which requirement is missing: no login integration at all, or one
            # that's set up but not signed in (or still starting).
            states = ac.login_integration_states(self.hass)
            if not states:
                return self.async_abort(reason="no_login_integration")
            return self.async_abort(
                reason="login_not_ready",
                description_placeholders={"states": ", ".join(states)},
            )

        errors: dict[str, str] = {}
        placeholders = {"error": "", "cloud_note": _cloud_note(self.hass)}
        if user_input is not None:
            email = user_input[CONF_EMAIL]
            await self.async_set_unique_id(f"{DOMAIN}:{email}")
            self._abort_if_unique_id_configured()
            # Prove the borrowed session works before creating the entry.
            try:
                await ac.get_groups(ac.get_login_obj(self.hass, email))
            except ac.AlexaClientError as err:
                errors["base"] = "cannot_connect"
                placeholders["error"] = str(err)[:300]
        if user_input is not None and not errors:
            # Renamed from alexa_room_sync: start with that entry's settings if it exists.
            legacy = runner.legacy_entries(self.hass, email)
            options = dict(legacy[0].options) if legacy else {CONF_DRY_RUN: DEFAULT_DRY_RUN}
            return self.async_create_entry(
                title=f"Alexa Area Sync ({email})",
                data={CONF_EMAIL: email},
                options=options,
            )

        schema = vol.Schema(
            {vol.Required(CONF_EMAIL, default=emails[0]): vol.In(emails)}
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AlexaAreaSyncOptionsFlow(config_entry)


SKIP_SECTION = "skip"


class AlexaAreaSyncOptionsFlow(OptionsFlow):
    """Options: dry-run, naming, and the write-confirmation gate."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["settings", "remove_rooms"]
        )

    async def async_step_remove_rooms(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete the rooms this integration made in Alexa (keeps rooms with Echos)."""
        if user_input is not None:
            if not user_input.get("confirm"):
                return self.async_abort(reason="remove_cancelled")
            try:
                results = await runner.remove_managed_rooms(self.hass, self._entry)
            except HomeAssistantError as err:
                return self.async_abort(
                    reason="remove_failed", description_placeholders={"error": str(err)}
                )
            summary = "\n".join(f"- {name}: {res}" for name, res in results.items())
            return self.async_abort(
                reason="rooms_removed",
                description_placeholders={"summary": summary or "No Alexa groups to remove."},
            )
        return self.async_show_form(
            step_id="remove_rooms",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # The area picker sits in its own titled section; store it flat as before.
            skip = user_input.pop(SKIP_SECTION, {}) or {}
            user_input[CONF_EXCLUDED_AREAS] = skip.get(CONF_EXCLUDED_AREAS, [])
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DRY_RUN,
                    default=opts.get(CONF_DRY_RUN, DEFAULT_DRY_RUN),
                ): bool,
                vol.Optional(
                    CONF_CONFIRMED,
                    default=opts.get(CONF_CONFIRMED, False),
                ): bool,
                vol.Optional(
                    CONF_ROOM_PREFIX,
                    default=opts.get(CONF_ROOM_PREFIX, DEFAULT_ROOM_PREFIX),
                ): str,
                vol.Optional(
                    CONF_INCLUDE_CLIMATE,
                    default=opts.get(CONF_INCLUDE_CLIMATE, DEFAULT_INCLUDE_CLIMATE),
                ): bool,
                vol.Optional(
                    CONF_INCLUDE_CHILD_LOCKS,
                    default=opts.get(
                        CONF_INCLUDE_CHILD_LOCKS, DEFAULT_INCLUDE_CHILD_LOCKS
                    ),
                ): bool,
                vol.Optional(
                    CONF_INCLUDE_ECHOS,
                    default=opts.get(CONF_INCLUDE_ECHOS, DEFAULT_INCLUDE_ECHOS),
                ): bool,
                vol.Optional(
                    CONF_FLOOR_GROUPS,
                    default=opts.get(CONF_FLOOR_GROUPS, DEFAULT_FLOOR_GROUPS),
                ): bool,
                vol.Optional(
                    CONF_FLOOR_LIGHTS_ONLY,
                    default=opts.get(CONF_FLOOR_LIGHTS_ONLY, DEFAULT_FLOOR_LIGHTS_ONLY),
                ): bool,
                vol.Optional(
                    CONF_RESEND_MISSING,
                    default=opts.get(CONF_RESEND_MISSING, DEFAULT_RESEND_MISSING),
                ): bool,
                vol.Optional(
                    CONF_AUTO_SYNC,
                    default=opts.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC),
                ): bool,
                vol.Required(SKIP_SECTION): section(
                    vol.Schema(
                        {
                            vol.Optional(
                                CONF_EXCLUDED_AREAS,
                                default=opts.get(CONF_EXCLUDED_AREAS, []),
                            ): AreaSelector(AreaSelectorConfig(multiple=True)),
                        }
                    ),
                    {"collapsed": False},
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)
