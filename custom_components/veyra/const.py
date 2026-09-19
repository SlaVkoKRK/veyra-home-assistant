from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "veyra"
DEFAULT_PORT = 8080
DEFAULT_SCAN_INTERVAL = 2
DEFAULT_NOTIFICATION_UPDATE_SECONDS = 2.0
DEFAULT_NOTIFICATION_ALERT_REPEAT_SECONDS = 5.0

CONF_NOTIFY_TARGETS = "notify_targets"
CONF_CLASS_LEVELS = "class_levels"
CONF_NOTIFICATION_UPDATE_SECONDS = "notification_update_seconds"
CONF_NOTIFICATION_ALERT_REPEAT_SECONDS = "notification_alert_repeat_seconds"

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
    if label == "person":
        return LEVEL_URGENT
    if label in {"car", "truck", "bicycle", "motorcycle", "bus"}:
        return LEVEL_URGENT
    return LEVEL_OFF
