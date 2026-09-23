from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .entity import VeyraEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = entry.runtime_data
    entities = []
    for cam in runtime.info.get("cameras", []):
        cid = cam["id"]
        entities.extend(
            [
                VeyraCameraBinarySensor(runtime, cid, "motion", "motion", BinarySensorDeviceClass.MOTION),
                VeyraCameraBinarySensor(runtime, cid, "objects", "objects", BinarySensorDeviceClass.OCCUPANCY),
                VeyraCameraBinarySensor(runtime, cid, "glare_approach", "glare_approach", None),
                VeyraCameraBinarySensor(runtime, cid, "night", "night", None, diagnostic=True),
                VeyraCameraBinarySensor(runtime, cid, "online", "online", BinarySensorDeviceClass.CONNECTIVITY, diagnostic=True),
            ]
        )
    async_add_entities(entities)


class VeyraCameraBinarySensor(VeyraEntity, BinarySensorEntity):
    def __init__(self, runtime, camera: str, key: str, translation_key: str, device_class, diagnostic: bool = False) -> None:
        super().__init__(runtime, camera)
        self.key = key
        self._attr_translation_key = translation_key
        self._attr_device_class = device_class
        self._attr_unique_id = f"{self.instance_id}_{camera}_{key}"
        if key == "glare_approach":
            self._attr_icon = "mdi:car-light-high"
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        data = self.camera_data
        if self.key == "motion":
            return bool(data.get("motion", False))
        if self.key == "objects":
            return bool(data.get("active_objects") or [])
        if self.key == "glare_approach":
            return bool(data.get("glare_approach_active", False))
        if self.key == "night":
            return bool(data.get("night", False))
        if self.key == "online":
            return bool(data.get("running", False) and not data.get("error"))
        return False

    @property
    def extra_state_attributes(self) -> dict:
        if self.key == "objects":
            objects = self.camera_data.get("active_objects") or []
            return {
                "labels": sorted({str(o.get("label")) for o in objects if o.get("label")}),
                "count": len(objects),
                "objects": objects[:8],
            }
        if self.key == "glare_approach":
            data = self.camera_data
            return {
                "score": data.get("glare_approach_score"),
                "growth": data.get("glare_approach_growth"),
                "motion_overlap": data.get("glare_approach_motion_overlap"),
                "area_fraction": data.get("glare_approach_area_fraction"),
                "last_alert": data.get("glare_approach_last_ts"),
                "count": data.get("glare_approach_count", 0),
            }
        return {}
