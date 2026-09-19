from __future__ import annotations

import logging

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import VeyraApiError
from .entity import VeyraEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


def _camera_definitions(runtime) -> list[tuple[str, str]]:
    """Return every camera known by info OR live status, without duplicates."""
    cameras: dict[str, str] = {}

    for item in runtime.info.get("cameras", []) or []:
        if not isinstance(item, dict):
            continue
        camera_id = str(item.get("id") or "").strip()
        if not camera_id:
            continue
        cameras[camera_id] = str(item.get("stream") or camera_id)

    status_cameras = ((runtime.coordinator.data or {}).get("cameras") or {})
    if isinstance(status_cameras, dict):
        for camera_id, state in status_cameras.items():
            cid = str(camera_id or "").strip()
            if not cid:
                continue
            stream = cid
            if isinstance(state, dict):
                stream = str(state.get("stream") or cid)
            cameras.setdefault(cid, stream)

    return list(cameras.items())


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = entry.runtime_data
    entities = [
        VeyraCamera(runtime, camera_id, stream)
        for camera_id, stream in _camera_definitions(runtime)
    ]
    _LOGGER.info("Adding %d Veyra camera entities: %s", len(entities), [x.camera for x in entities])
    async_add_entities(entities)


class VeyraCamera(VeyraEntity, Camera):
    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_translation_key = "live_view"

    def __init__(self, runtime, camera: str, stream: str) -> None:
        VeyraEntity.__init__(self, runtime, camera)
        Camera.__init__(self)
        self.stream_name = stream
        self._attr_unique_id = f"{self.instance_id}_{camera}_camera"

    @property
    def is_on(self) -> bool:
        data = self.camera_data
        return bool(data.get("enabled", True) and data.get("running", False))

    @property
    def use_stream_for_stills(self) -> bool:
        # Stills must use Veyra's per-camera snapshot API. RTSP/go2rtc is kept
        # only for live view; this avoids one stream helper affecting other cameras.
        return False

    @property
    def motion_detection_enabled(self) -> bool:
        return bool(
            self.camera_data.get("detect_enabled", False)
            and self.camera_data.get("motion_enabled", False)
        )

    async def stream_source(self) -> str | None:
        if not self.is_on:
            return None
        return self.runtime.api.rtsp_url(self.stream_name)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        try:
            return await self.runtime.api.async_camera_image(self.camera)
        except VeyraApiError as err:
            _LOGGER.debug("Snapshot unavailable for Veyra camera %s: %s", self.camera, err)
            return None
