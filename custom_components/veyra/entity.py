from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class VeyraEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, runtime, camera: str | None = None) -> None:
        super().__init__(runtime.coordinator)
        self.runtime = runtime
        self.camera = camera
        self.instance_id = str(runtime.info.get("instance_id") or "veyra")

    @property
    def device_info(self) -> DeviceInfo:
        if self.camera is None:
            return DeviceInfo(
                identifiers={(DOMAIN, self.instance_id)},
                name="Veyra",
                manufacturer="Veyra",
                model="Veyra Edge Vision",
                sw_version=str(self.runtime.info.get("version") or "unknown"),
                configuration_url=self.runtime.api.base_url,
            )

        info = next(
            (
                item
                for item in self.runtime.info.get("cameras", [])
                if isinstance(item, dict) and item.get("id") == self.camera
            ),
            {},
        )
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.instance_id}:{self.camera}")},
            name=str(info.get("name") or self.camera.replace("_", " ").title()),
            manufacturer="Veyra",
            model="Veyra Camera",
            configuration_url=f"{self.runtime.api.base_url}/camera/{self.camera}",
        )

    @property
    def camera_data(self) -> dict:
        if not self.camera:
            return {}
        cameras = ((self.coordinator.data or {}).get("cameras") or {})
        if not isinstance(cameras, dict):
            return {}
        data = cameras.get(self.camera, {})
        return data if isinstance(data, dict) else {}
