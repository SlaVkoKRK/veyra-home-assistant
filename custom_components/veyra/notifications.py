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
}


def _score_percent(value: Any) -> int | None:
    try:
        v = float(value)
        if v <= 1.0:
            v *= 100.0
        return round(v)
    except (TypeError, ValueError):
        return None


def _notification_version(after: dict[str, Any]) -> int:
    current = after.get("notification") or {}
    if isinstance(current, dict):
        try:
            version = int(current.get("version") or 0)
            if version > 0:
                return version
        except (TypeError, ValueError):
            pass
    try:
        return int(after.get("update_seq") or 0)
    except (TypeError, ValueError):
        return 0


class VeyraNotificationManager:
    """Forward every Veyra new/update MQTT event to Companion devices."""

    def __init__(self, hass: HomeAssistant, entry, runtime) -> None:
        self.hass = hass
        self.entry = entry
        self.runtime = runtime
        self._unsubscribe = None

    async def async_start(self) -> None:
        topic = str((((self.runtime.info or {}).get("mqtt") or {}).get("events_topic") or "ainvr/events"))
        try:
            self._unsubscribe = await async_subscribe(self.hass, topic, self._mqtt_message, qos=1)
            _LOGGER.info("Veyra built-in notifications listening on MQTT %s", topic)
        except (HomeAssistantError, KeyError) as err:
            _LOGGER.warning(
                "Veyra built-in push notifications are inactive because Home Assistant MQTT is not ready: %s",
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
            _LOGGER.debug("Ignored malformed Veyra MQTT event")
            return
        if not isinstance(payload, dict):
            return

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

        await self._send(after, event_id, level)

    def _class_level(self, label: str) -> str:
        levels = self.entry.options.get(CONF_CLASS_LEVELS, {})
        if isinstance(levels, dict) and label in levels:
            return str(levels[label])
        return default_class_level(label)

    def _targets(self) -> list[str]:
        services = self.hass.services.async_services().get("notify", {})
        available = sorted(str(name) for name in services if str(name).startswith("mobile_app_"))
        if CONF_NOTIFY_TARGETS not in self.entry.options:
            return available
        configured = self.entry.options.get(CONF_NOTIFY_TARGETS, []) or []
        return [
            str(x).replace("notify.", "")
            for x in configured
            if str(x).replace("notify.", "") in available
        ]

    def _camera_name(self, camera_id: str) -> str:
        for item in (self.runtime.info.get("cameras") or []):
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

    async def _send(self, after: dict[str, Any], event_id: str, level: str) -> None:
        targets = self._targets()
        if not targets:
            _LOGGER.debug("No selected mobile_app notify targets available for Veyra")
            return

        camera = str(after.get("camera") or "kamera")
        label = str(after.get("label") or "obiekt")
        # Current raw detector confidence, not the lifetime max (top_score).
        score = _score_percent(after.get("score", after.get("top_score")))
        title = self._title(label)
        message = self._camera_name(camera)
        if score is not None and score > 0:
            message += f"\n• pewność {score}%"

        data = self._payload(after, event_id, camera, level)
        call_data = {"title": title, "message": message, "data": data}
        current_services = self.hass.services.async_services().get("notify", {})
        for service in targets:
            if service not in current_services:
                continue
            try:
                await self.hass.services.async_call("notify", service, call_data, blocking=False)
            except HomeAssistantError as err:
                _LOGGER.warning("Unable to send Veyra notification via notify.%s: %s", service, err)

    def _payload(self, after: dict[str, Any], event_id: str, camera: str, level: str) -> dict[str, Any]:
        version = _notification_version(after)
        image = (
            f"/api/veyra/notifications/{self.entry.entry_id}/{event_id}/"
            f"{version}/current.jpg"
        )
        try:
            when = int(float(after.get("start_time") or 0))
        except (TypeError, ValueError):
            when = 0

        data: dict[str, Any] = {
            "image": image,
            "tag": f"veyra_{event_id}",
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
        if when > 0:
            data["when"] = when

        if level == LEVEL_SILENT:
            data.update({
                "push": {"interruption-level": "passive"},
                "channel": "Veyra Ciche",
                "importance": "low",
                "alert_once": True,
            })
        elif level == LEVEL_NORMAL:
            data.update({
                "push": {"interruption-level": "active", "sound": "default"},
                "channel": "Veyra",
                "importance": "default",
                "vibrationPattern": "100, 250",
                "alert_once": False,
            })
        elif level == LEVEL_URGENT:
            data.update({
                "ttl": 0,
                "priority": "high",
                "push": {"interruption-level": "time-sensitive", "sound": "default"},
                "channel": "Veyra Security",
                "importance": "high",
                "vibrationPattern": "100, 700, 100",
                "alert_once": False,
            })
        elif level == LEVEL_CRITICAL:
            data.update({
                "ttl": 0,
                "priority": "high",
                "push": {
                    "interruption-level": "critical",
                    "sound": {"name": "default", "critical": 1, "volume": 1.0},
                },
                "channel": "alarm_stream",
                "importance": "max",
                "vibrationPattern": "100, 900, 100, 900, 100",
                "alert_once": False,
            })
        return data


class VeyraThumbnailView(HomeAssistantView):
    url = "/api/veyra/notifications/{entry_id}/{event_id}/thumbnail.jpg"
    name = "api:veyra:notifications:thumbnail"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str, event_id: str) -> web.Response:
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
        return web.Response(body=image, content_type="image/jpeg", headers={"Cache-Control": "no-store"})


class VeyraCurrentNotificationView(HomeAssistantView):
    # Version is deliberately part of the path. iOS/Companion cannot reuse the
    # previous attachment URL when a Veyra event is updated.
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
