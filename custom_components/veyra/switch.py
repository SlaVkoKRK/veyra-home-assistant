from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .entity import VeyraEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = entry.runtime_data
    entities = [
        VeyraGlobalSwitch(runtime, "ai_detection", "ai_detection"),
        VeyraGlobalSwitch(runtime, "notifications", "notifications"),
        VeyraGlobalSwitch(runtime, "snapshots", "snapshots", diagnostic=True),
    ]
    for cam in runtime.info.get("cameras", []):
        cid = cam["id"]
        entities.extend(
            [
                VeyraCameraSwitch(runtime, cid, "ai_detection", "ai_detection"),
                VeyraCameraSwitch(runtime, cid, "notifications", "notifications"),
                VeyraCameraSwitch(runtime, cid, "snapshots", "snapshots", diagnostic=True),
            ]
        )
    async_add_entities(entities)


class _BaseSwitch(VeyraEntity, SwitchEntity):
    def __init__(self, runtime, feature: str, translation_key: str, camera: str | None = None, diagnostic: bool = False) -> None:
        super().__init__(runtime, camera)
        self.feature = feature
        self._attr_translation_key = translation_key
        if diagnostic:
            self._attr_entity_category = EntityCategory.CONFIG


class VeyraGlobalSwitch(_BaseSwitch):
    def __init__(self, runtime, feature: str, translation_key: str, diagnostic: bool = False) -> None:
        super().__init__(runtime, feature, translation_key, diagnostic=diagnostic)
        self._attr_unique_id = f"{self.instance_id}_global_{feature}"

    @property
    def is_on(self) -> bool:
        return bool(((self.coordinator.data or {}).get("global") or {}).get(self.feature, False))

    async def async_turn_on(self, **kwargs) -> None:
        await self.runtime.api.async_set_global(self.feature, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.runtime.api.async_set_global(self.feature, False)
        await self.coordinator.async_request_refresh()


class VeyraCameraSwitch(_BaseSwitch):
    def __init__(self, runtime, camera: str, feature: str, translation_key: str, diagnostic: bool = False) -> None:
        super().__init__(runtime, feature, translation_key, camera, diagnostic)
        self._attr_unique_id = f"{self.instance_id}_{camera}_{feature}"

    @property
    def is_on(self) -> bool:
        data = self.camera_data
        if self.feature == "ai_detection":
            return bool(data.get("detect_enabled", False) and data.get("motion_enabled", False))
        if self.feature == "notifications":
            return bool(data.get("notifications_enabled", True))
        if self.feature == "snapshots":
            return bool(data.get("snapshots_enabled", True))
        return False

    async def async_turn_on(self, **kwargs) -> None:
        await self.runtime.api.async_set_camera(self.camera, self.feature, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.runtime.api.async_set_camera(self.camera, self.feature, False)
        await self.coordinator.async_request_refresh()
