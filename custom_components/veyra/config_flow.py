from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import VeyraApi, VeyraApiError
from .const import (
    CONF_FLOOD_MUTE_DURATION_MINUTES,
    CONF_FLOOD_MUTE_ENABLED,
    CONF_FLOOD_MUTE_THRESHOLD,
    CONF_FLOOD_MUTE_WINDOW_SECONDS,
    CONF_NOTIFY_TARGETS,
    DEFAULT_FLOOD_MUTE_DURATION_MINUTES,
    DEFAULT_FLOOD_MUTE_ENABLED,
    DEFAULT_FLOOD_MUTE_THRESHOLD,
    DEFAULT_FLOOD_MUTE_WINDOW_SECONDS,
    DEFAULT_PORT,
    DOMAIN,
)


class VeyraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            api = VeyraApi(async_get_clientsession(self.hass), host, port)
            try:
                info = await api.async_info()
                instance_id = str(info.get("instance_id") or "")
                if not instance_id:
                    errors["base"] = "invalid_response"
                else:
                    await self.async_set_unique_id(instance_id)
                    self._abort_if_unique_id_configured(
                        updates={CONF_HOST: host, CONF_PORT: port}
                    )
                    return self.async_create_entry(
                        title=str(info.get("name") or "Veyra"),
                        data={CONF_HOST: host, CONF_PORT: port},
                    )
            except VeyraApiError:
                errors["base"] = "cannot_connect"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return VeyraOptionsFlow()


class VeyraOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            options = dict(self.config_entry.options)
            options[CONF_NOTIFY_TARGETS] = list(user_input.get(CONF_NOTIFY_TARGETS, []))
            options[CONF_FLOOD_MUTE_ENABLED] = bool(
                user_input.get(CONF_FLOOD_MUTE_ENABLED, DEFAULT_FLOOD_MUTE_ENABLED)
            )
            options[CONF_FLOOD_MUTE_THRESHOLD] = int(
                user_input.get(CONF_FLOOD_MUTE_THRESHOLD, DEFAULT_FLOOD_MUTE_THRESHOLD)
            )
            options[CONF_FLOOD_MUTE_WINDOW_SECONDS] = int(
                user_input.get(
                    CONF_FLOOD_MUTE_WINDOW_SECONDS, DEFAULT_FLOOD_MUTE_WINDOW_SECONDS
                )
            )
            options[CONF_FLOOD_MUTE_DURATION_MINUTES] = int(
                user_input.get(
                    CONF_FLOOD_MUTE_DURATION_MINUTES,
                    DEFAULT_FLOOD_MUTE_DURATION_MINUTES,
                )
            )
            return self.async_create_entry(data=options)

        services = self.hass.services.async_services().get("notify", {})
        mobile = sorted(
            str(name) for name in services if str(name).startswith("mobile_app_")
        )
        if CONF_NOTIFY_TARGETS in self.config_entry.options:
            current_targets = list(
                self.config_entry.options.get(CONF_NOTIFY_TARGETS, []) or []
            )
        else:
            current_targets = list(mobile)

        fields: dict[Any, Any] = {}
        if mobile:
            selector_options = [
                SelectOptionDict(
                    value=name,
                    label=name.replace("mobile_app_", "").replace("_", " ").title(),
                )
                for name in mobile
            ]
            fields[vol.Optional(CONF_NOTIFY_TARGETS, default=current_targets)] = SelectSelector(
                SelectSelectorConfig(
                    options=selector_options,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )

        fields[
            vol.Optional(
                CONF_FLOOD_MUTE_ENABLED,
                default=bool(
                    self.config_entry.options.get(
                        CONF_FLOOD_MUTE_ENABLED, DEFAULT_FLOOD_MUTE_ENABLED
                    )
                ),
            )
        ] = bool
        fields[
            vol.Optional(
                CONF_FLOOD_MUTE_THRESHOLD,
                default=int(
                    self.config_entry.options.get(
                        CONF_FLOOD_MUTE_THRESHOLD, DEFAULT_FLOOD_MUTE_THRESHOLD
                    )
                ),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=3, max=50))

        current_window = str(
            int(
                self.config_entry.options.get(
                    CONF_FLOOD_MUTE_WINDOW_SECONDS, DEFAULT_FLOOD_MUTE_WINDOW_SECONDS
                )
            )
        )
        fields[
            vol.Optional(CONF_FLOOD_MUTE_WINDOW_SECONDS, default=current_window)
        ] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value="30", label="30 s"),
                    SelectOptionDict(value="60", label="60 s"),
                    SelectOptionDict(value="90", label="90 s"),
                    SelectOptionDict(value="120", label="2 min"),
                    SelectOptionDict(value="180", label="3 min"),
                ],
                multiple=False,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )

        current_duration = str(
            int(
                self.config_entry.options.get(
                    CONF_FLOOD_MUTE_DURATION_MINUTES,
                    DEFAULT_FLOOD_MUTE_DURATION_MINUTES,
                )
            )
        )
        fields[
            vol.Optional(CONF_FLOOD_MUTE_DURATION_MINUTES, default=current_duration)
        ] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value="10", label="10 min"),
                    SelectOptionDict(value="15", label="15 min"),
                    SelectOptionDict(value="20", label="20 min"),
                    SelectOptionDict(value="30", label="30 min"),
                ],
                multiple=False,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )

        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
