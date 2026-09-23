from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "veyra"
DEFAULT_PORT = 8080
DEFAULT_SCAN_INTERVAL = 2

CONF_NOTIFY_TARGETS = "notify_targets"
CONF_CLASS_LEVELS = "class_levels"

LEVEL_OFF = "off"
LEVEL_SILENT = "silent"
LEVEL_NORMAL = "normal"
LEVEL_URGENT = "urgent"
LEVEL_CRITICAL = "critical"
NOTIFICATION_LEVELS = (
    LEVEL_OFF,
    LEVEL_SILENT,
    LEVEL_NORMAL,
    LEVEL_URGENT,
    LEVEL_CRITICAL,
)

PLATFORMS: list[Platform] = [
    Platform.CAMERA,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SELECT,
]


def default_class_level(label: str) -> str:
    label = str(label or "").strip().lower()
    if label in {"person", "glare"}:
        return LEVEL_URGENT
    if label in {"car", "truck", "bicycle", "motorcycle", "bus"}:
        return LEVEL_URGENT
    return LEVEL_OFF
