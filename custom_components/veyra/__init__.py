from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.mqtt.client import async_subscribe
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VeyraApi, VeyraApiError
from .const import DOMAIN, PLATFORMS
from .coordinator import VeyraCoordinator
from .notifications import (
    VeyraCurrentNotificationView,
    VeyraNotificationManager,
    VeyraThumbnailView,
)


@dataclass
class VeyraRuntimeData:
    api: VeyraApi
    coordinator: VeyraCoordinator
    info: dict
    notifications: VeyraNotificationManager | None = None
    availability_unsubscribe: Any | None = None
    notification_rearming: bool = False


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
    if not domain_data.get("notification_views_registered"):
        hass.http.register_view(VeyraThumbnailView)
        hass.http.register_view(VeyraCurrentNotificationView)
        domain_data["notification_views_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    runtime.notifications = VeyraNotificationManager(hass, entry, runtime)
    await runtime.notifications.async_start()

    # A Veyra CORE restart must not require manually reloading notifications in
    # Home Assistant. Veyra publishes a retained availability topic; when CORE
    # comes back online, refresh API metadata and re-arm the event subscription.
    availability_topic = str(
        (((runtime.info or {}).get("mqtt") or {}).get("available_topic") or "ainvr/available")
    )

    async def _veyra_availability_message(msg) -> None:
        payload = str(getattr(msg, "payload", "") or "").strip().lower()
        if payload != "online" or runtime.notification_rearming:
            return
        runtime.notification_rearming = True
        try:
            try:
                runtime.info = await runtime.api.async_info()
            except VeyraApiError:
                # The retained MQTT online packet may beat the HTTP listener by a
                # fraction of a second. Re-arming still helps because the event
                # topic is stable and defaults to ainvr/events.
                pass
            if runtime.notifications is not None:
                await runtime.notifications.async_stop()
                await runtime.notifications.async_start()
        finally:
            runtime.notification_rearming = False

    runtime.availability_unsubscribe = await async_subscribe(
        hass, availability_topic, _veyra_availability_message, qos=1
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = getattr(entry, "runtime_data", None)
    if runtime and runtime.availability_unsubscribe is not None:
        runtime.availability_unsubscribe()
        runtime.availability_unsubscribe = None
    if runtime and runtime.notifications:
        await runtime.notifications.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
