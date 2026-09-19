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

# Notification flood protection / temporary per-camera mute.
CONF_FLOOD_MUTE_ENABLED = "flood_mute_enabled"
CONF_FLOOD_MUTE_THRESHOLD = "flood_mute_threshold"
CONF_FLOOD_MUTE_WINDOW_SECONDS = "flood_mute_window_seconds"
CONF_FLOOD_MUTE_DURATION_MINUTES = "flood_mute_duration_minutes"

DEFAULT_FLOOD_MUTE_ENABLED = True
DEFAULT_FLOOD_MUTE_THRESHOLD = 12
DEFAULT_FLOOD_MUTE_WINDOW_SECONDS = 90
DEFAULT_FLOOD_MUTE_DURATION_MINUTES = 15
# Do not repeatedly ask about the same camera when the user chooses to keep it active.
DEFAULT_FLOOD_MUTE_OFFER_COOLDOWN_SECONDS = 15 * 60

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
