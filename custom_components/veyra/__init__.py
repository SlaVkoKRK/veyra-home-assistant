from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VeyraApi, VeyraApiError
from .const import DOMAIN, PLATFORMS
from .coordinator import VeyraCoordinator
from .notifications import VeyraNotificationManager, VeyraThumbnailView


@dataclass
class VeyraRuntimeData:
    api: VeyraApi
    coordinator: VeyraCoordinator
    info: dict
    notifications: VeyraNotificationManager | None = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = VeyraApi(async_get_clientsession(hass), entry.data[CONF_HOST], entry.data[CONF_PORT])
    try:
        info = await api.async_info()
    except VeyraApiError as err:
        raise ConfigEntryNotReady(f"Veyra is unavailable: {err}") from err

    coordinator = VeyraCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()
    runtime = VeyraRuntimeData(api=api, coordinator=coordinator, info=info)
    entry.runtime_data = runtime

    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("thumbnail_view_registered"):
        hass.http.register_view(VeyraThumbnailView)
        domain_data["thumbnail_view_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    runtime.notifications = VeyraNotificationManager(hass, entry, runtime)
    await runtime.notifications.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = getattr(entry, "runtime_data", None)
    if runtime and runtime.notifications:
        await runtime.notifications.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
