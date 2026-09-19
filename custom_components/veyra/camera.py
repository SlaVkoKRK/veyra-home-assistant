from __future__ import annotations

import logging

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import VeyraApiError
from .const import DOMAIN

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


def _camera_definitions(runtime) -> list[tuple[str, str, str]]:
    """Return every camera known by info OR live status, without duplicates."""
    cameras: dict[str, tuple[str, str]] = {}

    for item in runtime.info.get("cameras", []) or []:
        if not isinstance(item, dict):
            continue
        camera_id = str(item.get("id") or "").strip()
        if not camera_id:
            continue
        stream = str(item.get("stream") or camera_id)
        name = str(item.get("name") or item.get("display_name") or camera_id.replace("_", " ").title())
        cameras[camera_id] = (stream, name)

    status_cameras = ((runtime.coordinator.data or {}).get("cameras") or {})
    if isinstance(status_cameras, dict):
        for camera_id, state in status_cameras.items():
            cid = str(camera_id or "").strip()
            if not cid:
                continue
            stream = cid
            name = cid.replace("_", " ").title()
            if isinstance(state, dict):
                stream = str(state.get("stream") or cid)
                name = str(state.get("name") or state.get("display_name") or name)
            cameras.setdefault(cid, (stream, name))

    return [(cid, stream, name) for cid, (stream, name) in cameras.items()]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    runtime = entry.runtime_data
    definitions = _camera_definitions(runtime)
    entities = [
        VeyraCamera(runtime, camera_id, stream, name)
        for camera_id, stream, name in definitions
    ]
    _LOGGER.info(
        "Adding %d independent Veyra camera entities: %s",
        len(entities),
        [x.camera_id for x in entities],
    )
    async_add_entities(entities, update_before_add=False)


class VeyraCamera(CoordinatorEntity, Camera):
    """One independent Home Assistant camera entity per Veyra camera."""

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_name = "Podgląd"
    _attr_should_poll = False

    def __init__(self, runtime, camera_id: str, stream: str, camera_name: str) -> None:
        # Keep Camera completely independent from the common VeyraEntity class.
        # In particular, do not reuse a generic `camera` attribute/device_info cache
        # between camera entities.
        CoordinatorEntity.__init__(self, runtime.coordinator)
        Camera.__init__(self)

        self.runtime = runtime
        self.camera_id = str(camera_id)
        self.stream_name = str(stream or camera_id)
        self.camera_name = str(camera_name or camera_id.replace("_", " ").title())
        self.instance_id = str(runtime.info.get("instance_id") or "veyra")

        self._attr_unique_id = f"{self.instance_id}:{self.camera_id}:live"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.instance_id}:{self.camera_id}")},
            name=self.camera_name,
            manufacturer="Veyra",
            model="Veyra Camera",
            via_device=(DOMAIN, self.instance_id),
            configuration_url=f"{self.runtime.api.base_url}/camera/{self.camera_id}",
        )

    @property
    def camera_data(self) -> dict:
        cameras = ((self.coordinator.data or {}).get("cameras") or {})
        if not isinstance(cameras, dict):
            return {}
        data = cameras.get(self.camera_id, {})
        return data if isinstance(data, dict) else {}

    @property
    def is_on(self) -> bool:
        # The entity must remain present even while a camera is temporarily offline.
        # `running` only controls whether HA should try to open the live stream.
        data = self.camera_data
        return bool(data.get("enabled", True))

    @property
    def available(self) -> bool:
        # Do not hide/remove the entity just because RTSP or a snapshot is momentarily
        # unavailable. Coordinator availability still reflects Veyra itself.
        return bool(super().available)

    @property
    def use_stream_for_stills(self) -> bool:
        return False

    @property
    def motion_detection_enabled(self) -> bool:
        data = self.camera_data
        return bool(data.get("detect_enabled", False) and data.get("motion_enabled", False))

    async def stream_source(self) -> str | None:
        data = self.camera_data
        if data and data.get("running") is False:
            return None
        return self.runtime.api.rtsp_url(self.stream_name)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        try:
            return await self.runtime.api.async_camera_image(self.camera_id)
        except VeyraApiError as err:
            _LOGGER.debug(
                "Snapshot unavailable for Veyra camera %s: %s", self.camera_id, err
            )
            return None
