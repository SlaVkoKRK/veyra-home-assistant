from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.components.mqtt.client import async_subscribe
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import VeyraApiError
from .const import (
    CONF_CLASS_LEVELS,
    CONF_NOTIFY_TARGETS,
    LEVEL_CRITICAL,
    LEVEL_NORMAL,
    LEVEL_OFF,
    LEVEL_SILENT,
    LEVEL_URGENT,
    default_class_level,
)

_LOGGER = logging.getLogger(__name__)

OBJECT_TITLES: dict[str, tuple[str, str]] = {
    "person": ("🚨", "Wykryto osobę"),
    "car": ("🚗", "Wykryto samochód"),
    "truck": ("🚚", "Wykryto ciężarówkę"),
    "bicycle": ("🚲", "Wykryto rower"),
    "motorcycle": ("🏍️", "Wykryto motocykl"),
    "airplane": ("✈️", "Wykryto samolot"),
    "bus": ("🚌", "Wykryto autobus"),
    "train": ("🚆", "Wykryto pociąg"),
    "boat": ("🚤", "Wykryto łódź"),
    "bird": ("🐦", "Wykryto ptaka"),
    "cat": ("🐈", "Wykryto kota"),
    "dog": ("🐕", "Wykryto psa"),
    "horse": ("🐎", "Wykryto konia"),
    "sheep": ("🐑", "Wykryto owcę"),
    "cow": ("🐄", "Wykryto krowę"),
    "elephant": ("🐘", "Wykryto słonia"),
    "bear": ("🐻", "Wykryto niedźwiedzia"),
    "glare": ("🔦", "Silne oślepianie kamery"),
}

DIRECT_TYPES = {"prealert", "confirmed", "repeat", "glare_approach"}


def _score_percent(value: Any) -> int | None:
    try:
        v = float(value)
        if v <= 1.0:
            v *= 100.0
        return round(v)
    except (TypeError, ValueError):
        return None


def _notification_version(data: dict[str, Any]) -> int:
    try:
        value = int(data.get("snapshot_version") or 0)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass

    current = data.get("notification") or {}
    if isinstance(current, dict):
        try:
            value = int(current.get("version") or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass

    try:
        return int(data.get("update_seq") or 0)
    except (TypeError, ValueError):
        return 0


def _repeat_number(data: dict[str, Any]) -> int:
    try:
        return max(1, int(data.get("repeat") or 1))
    except (TypeError, ValueError):
        return 1


def _percent(value: Any) -> int | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 1.0:
        v *= 100.0
    return max(0, min(999, round(v)))


class VeyraNotificationManager:
    """Forward Veyra's native notification lifecycle to Companion App.

    Veyra CORE owns cadence and false-positive filtering. The integration does
    not debounce or rate-limit valid alarms. Native CORE publishes
    prealert/confirmed/repeat and Glare Motion Guard alarms on
    mqtt.notifications_topic; older CORE builds are still supported through the
    Frigate-style events topic.
    """

    def __init__(self, hass: HomeAssistant, entry, runtime) -> None:
        self.hass = hass
        self.entry = entry
        self.runtime = runtime
        self._unsubscribe = None
        self._direct_notifications = False

    async def async_start(self) -> None:
        mqtt_info = (self.runtime.info or {}).get("mqtt") or {}
        notifications_topic = str(mqtt_info.get("notifications_topic") or "").strip()
        if notifications_topic:
            topic = notifications_topic
            self._direct_notifications = True
        else:
            topic = str(mqtt_info.get("events_topic") or "ainvr/events")
            self._direct_notifications = False

        try:
            self._unsubscribe = await async_subscribe(
                self.hass, topic, self._mqtt_message, qos=1
            )
            _LOGGER.info(
                "Veyra notifications listening on MQTT %s (%s protocol)",
                topic,
                "native" if self._direct_notifications else "legacy events",
            )
        except (HomeAssistantError, KeyError) as err:
            _LOGGER.warning(
                "Veyra push notifications are inactive because Home Assistant MQTT is not ready: %s",
                err,
            )

    async def async_stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    async def _mqtt_message(self, msg) -> None:
        try:
            payload = json.loads(msg.payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            _LOGGER.debug("Ignored malformed Veyra MQTT message")
            return
        if not isinstance(payload, dict):
            return

        if self._direct_notifications:
            await self._handle_native(payload)
        else:
            await self._handle_legacy_event(payload)

    async def _handle_native(self, payload: dict[str, Any]) -> None:
        kind = str(payload.get("type") or "").strip().lower()
        if kind not in DIRECT_TYPES:
            return

        event_id = str(payload.get("id") or "")
        if not event_id:
            return

        label = str(payload.get("label") or "object")
        level = self._class_level(label)
        if level == LEVEL_OFF:
            return

        await self._send(payload, event_id, level, kind=kind)

    async def _handle_legacy_event(self, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("type") or "update")
        if event_type not in {"new", "update"}:
            return

        after = payload.get("after") or {}
        if not isinstance(after, dict):
            return
        event_id = str(after.get("id") or "")
        if not event_id:
            return
        if bool(after.get("false_positive", False)):
            return
        if after.get("notifications_enabled") is False:
            return

        label = str(after.get("label") or "object")
        level = self._class_level(label)
        if level == LEVEL_OFF:
            return

        await self._send(after, event_id, level, kind=event_type)

    def _class_level(self, label: str) -> str:
        levels = self.entry.options.get(CONF_CLASS_LEVELS, {})
        if isinstance(levels, dict) and label in levels:
            return str(levels[label])
        return default_class_level(label)

    def _targets(self) -> list[str]:
        services = self.hass.services.async_services().get("notify", {})
        available = sorted(
            str(name) for name in services if str(name).startswith("mobile_app_")
        )
        if CONF_NOTIFY_TARGETS not in self.entry.options:
            return available
        configured = self.entry.options.get(CONF_NOTIFY_TARGETS, []) or []
        return [
            str(x).replace("notify.", "")
            for x in configured
            if str(x).replace("notify.", "") in available
        ]

    def _camera_name(self, camera_id: str) -> str:
        for item in self.runtime.info.get("cameras") or []:
            if not isinstance(item, dict) or str(item.get("id") or "") != camera_id:
                continue
            value = item.get("name") or item.get("display_name") or item.get("friendly_name")
            if value:
                return str(value)
        return camera_id.replace("_", " ").title()

    @staticmethod
    def _title(label: str) -> str:
        if label in OBJECT_TITLES:
            emoji, text = OBJECT_TITLES[label]
            return f"{emoji} {text}"
        return f"📹 Wykryto: {label}"

    async def _send(
        self,
        data: dict[str, Any],
        event_id: str,
        level: str,
        *,
        kind: str,
    ) -> bool:
        targets = self._targets()
        if not targets:
            _LOGGER.debug("No selected mobile_app notify targets available for Veyra")
            return False

        camera = str(data.get("camera") or "kamera")
        label = str(data.get("label") or "obiekt")
        repeat = _repeat_number(data)

        if kind == "glare_approach":
            title = "🚨 Ktoś zbliża się i oślepia kamerę"
            message = self._camera_name(camera)
            message += "\n• wykryto ruchome, rosnące źródło silnego światła"
            growth = data.get("growth")
            overlap = _percent(data.get("motion_overlap"))
            try:
                if growth is not None and float(growth) > 1.0:
                    message += f"\n• wzrost glare {float(growth):.2f}×"
            except (TypeError, ValueError):
                pass
            if overlap is not None:
                message += f"\n• zgodność z ruchem {overlap}%"
        else:
            score = _score_percent(
                data.get("snapshot_score", data.get("score", data.get("top_score")))
            )
            title = self._title(label)
            message = self._camera_name(camera)
            if score is not None and score > 0:
                message += f"\n• pewność {score}%"
            if kind == "repeat" or repeat > 2:
                message += f"\n• alarm {repeat}"

        notification_data = self._payload(
            data, event_id, camera, level, kind=kind, repeat=repeat
        )
        call_data = {"title": title, "message": message, "data": notification_data}
        current_services = self.hass.services.async_services().get("notify", {})
        sent = False
        for service in targets:
            if service not in current_services:
                continue
            try:
                await self.hass.services.async_call(
                    "notify", service, call_data, blocking=False
                )
                sent = True
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "Unable to send Veyra notification via notify.%s: %s",
                    service,
                    err,
                )
        return sent

    def _payload(
        self,
        data: dict[str, Any],
        event_id: str,
        camera: str,
        level: str,
        *,
        kind: str,
        repeat: int,
    ) -> dict[str, Any]:
        version = _notification_version(data)
        image = (
            f"/api/veyra/notifications/{self.entry.entry_id}/{event_id}/"
            f"{version}/current.jpg"
        )
        try:
            when = int(float(data.get("notification_time") or data.get("start_time") or 0))
        except (TypeError, ValueError):
            when = 0

        if kind == "prealert":
            tag = f"veyra_{event_id}_prealert"
        elif kind == "confirmed":
            tag = f"veyra_{event_id}_confirmed"
        elif kind == "repeat":
            tag = f"veyra_{event_id}_repeat_{repeat}"
        elif kind == "glare_approach":
            tag = f"veyra_{camera}_glare_{event_id}"
        else:
            tag = f"veyra_{event_id}"

        payload: dict[str, Any] = {
            "tag": tag,
            "group": f"veyra_{camera}",
            "url": "/lovelace/monitoring",
            "actions": [
                {
                    "action": "URI",
                    "title": "📹 Podgląd kamer",
                    "uri": "/lovelace/monitoring",
                }
            ],
        }
        # Glare Motion Guard is not a persisted gallery event. Do not point the
        # Companion App at an event-image URL that cannot exist; the alert still
        # opens the live monitoring view immediately.
        if kind != "glare_approach":
            payload["image"] = image
        if when > 0:
            payload["when"] = when

        if level == LEVEL_SILENT:
            payload.update(
                {
                    "push": {"interruption-level": "passive"},
                    "channel": "Veyra Ciche",
                    "importance": "low",
                    "alert_once": True,
                }
            )
            return payload

        payload.update(
            {
                "ttl": 0,
                "priority": "high",
                "vibrationPattern": "100, 700, 100, 700, 100",
                "alert_once": False,
            }
        )

        if level == LEVEL_NORMAL:
            payload.update(
                {
                    "push": {
                        "interruption-level": "active",
                        "sound": "default",
                    },
                    "channel": "Veyra Alerts v2",
                    "importance": "high",
                }
            )
        elif level == LEVEL_URGENT:
            payload.update(
                {
                    "push": {
                        "interruption-level": "time-sensitive",
                        "sound": "default",
                    },
                    "channel": "Veyra Security v2",
                    "importance": "max",
                }
            )
        elif level == LEVEL_CRITICAL:
            payload.update(
                {
                    "push": {
                        "interruption-level": "critical",
                        "sound": {
                            "name": "default",
                            "critical": 1,
                            "volume": 1.0,
                        },
                    },
                    "channel": "alarm_stream",
                    "importance": "max",
                    "vibrationPattern": "100, 900, 100, 900, 100",
                }
            )
        return payload


class VeyraThumbnailView(HomeAssistantView):
    url = "/api/veyra/notifications/{entry_id}/{event_id}/thumbnail.jpg"
    name = "api:veyra:notifications:thumbnail"
    requires_auth = True

    async def get(
        self, request: web.Request, entry_id: str, event_id: str
    ) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or getattr(entry, "runtime_data", None) is None:
            raise web.HTTPNotFound()
        try:
            image = await entry.runtime_data.api.async_event_thumbnail(event_id)
        except VeyraApiError:
            raise web.HTTPNotFound() from None
        if not image:
            raise web.HTTPNotFound()
        return web.Response(
            body=image,
            content_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )


class VeyraCurrentNotificationView(HomeAssistantView):
    url = "/api/veyra/notifications/{entry_id}/{event_id}/{version}/current.jpg"
    name = "api:veyra:notifications:current"
    requires_auth = True

    async def get(
        self,
        request: web.Request,
        entry_id: str,
        event_id: str,
        version: str,
    ) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or getattr(entry, "runtime_data", None) is None:
            raise web.HTTPNotFound()
        try:
            image = await entry.runtime_data.api.async_event_current_image(event_id)
        except VeyraApiError:
            raise web.HTTPNotFound() from None
        if not image:
            raise web.HTTPNotFound()
        return web.Response(
            body=image,
            content_type="image/jpeg",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
