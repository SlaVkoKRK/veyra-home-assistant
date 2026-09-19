from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .entity import VeyraEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = entry.runtime_data
    entities = [
        VeyraGlobalSensor(runtime, "cpu_tree_pct", "cpu_usage", PERCENTAGE),
        VeyraGlobalSensor(runtime, "igpu_usage", "igpu_usage", PERCENTAGE),
        VeyraGlobalSensor(runtime, "coral_ms", "coral_latency", "ms"),
    ]
    for cam in runtime.info.get("cameras", []):
        cid = cam["id"]
        entities.extend(
            [
                VeyraCameraSensor(runtime, cid, "fps", "fps", "fps"),
                VeyraCameraSensor(runtime, cid, "active_count", "active_objects", None),
                VeyraCameraSensor(runtime, cid, "detector_ms", "detector_latency", "ms"),
            ]
        )
    async_add_entities(entities)


class VeyraGlobalSensor(VeyraEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, runtime, key: str, translation_key: str, unit: str | None) -> None:
        super().__init__(runtime)
        self.key = key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{self.instance_id}_{key}"
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self.key == "cpu_tree_pct":
            return (data.get("runtime") or {}).get("cpu_tree_pct")
        if self.key == "igpu_usage":
            return (data.get("igpu") or {}).get("usage_pct")
        if self.key == "coral_ms":
            return (data.get("coral") or {}).get("last_ms")
        return None


class VeyraCameraSensor(VeyraEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, runtime, camera: str, key: str, translation_key: str, unit: str | None) -> None:
        super().__init__(runtime, camera)
        self.key = key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{self.instance_id}_{camera}_{key}"
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        data = self.camera_data
        if self.key == "fps":
            return data.get("fps")
        if self.key == "active_count":
            return len(data.get("active_objects") or [])
        if self.key == "detector_ms":
            return data.get("detector_ms")
        return None
