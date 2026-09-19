from __future__ import annotations

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .entity import VeyraEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = entry.runtime_data
    entities = [VeyraCamera(runtime, cam["id"], cam.get("stream") or cam["id"]) for cam in runtime.info.get("cameras", [])]
    async_add_entities(entities)


class VeyraCamera(VeyraEntity, Camera):
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, runtime, camera: str, stream: str) -> None:
        VeyraEntity.__init__(self, runtime, camera)
        Camera.__init__(self)
        self.stream_name = stream
        self._attr_unique_id = f"{self.instance_id}_{camera}_camera"
        self._attr_name = None

    @property
    def is_on(self) -> bool:
        data = self.camera_data
        return bool(data.get("enabled", True) and data.get("running", False))

    @property
    def use_stream_for_stills(self) -> bool:
        return True

    @property
    def motion_detection_enabled(self) -> bool:
        return bool(self.camera_data.get("detect_enabled", False) and self.camera_data.get("motion_enabled", False))

    async def stream_source(self) -> str | None:
        if not self.is_on:
            return None
        return self.runtime.api.rtsp_url(self.stream_name)

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        return await self.runtime.api.async_camera_image(self.camera)
