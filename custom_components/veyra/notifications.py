from __future__ import annotations

import json
import logging
import time
from typing import Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.components.mqtt.client import async_subscribe
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import VeyraApiError
from .const import (
    CONF_CLASS_LEVELS,
    CONF_NOTIFICATION_ALERT_REPEAT_SECONDS,
    CONF_NOTIFICATION_UPDATE_SECONDS,
    CONF_NOTIFY_TARGETS,
    DEFAULT_NOTIFICATION_ALERT_REPEAT_SECONDS,
    DEFAULT_NOTIFICATION_UPDATE_SECONDS,
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


def _snapshot_version(after: dict[str, Any]) -> int:
    snap = after.get("snapshot") or {}
    if isinstance(snap, dict):
        try:
            return int(snap.get("version") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


class VeyraNotificationManager:
    """Translate Veyra MQTT events into native Companion App notifications."""

    def __init__(self, hass: HomeAssistant, entry, runtime) -> None:
        self.hass = hass
        self.entry = entry
        self.runtime = runtime
        self._unsubscribe = None
        self._events: dict[str, dict[str, Any]] = {}

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
        self._events.clear()

    async def _mqtt_message(self, msg) -> None:
        try:
            payload = json.loads(msg.payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            _LOGGER.debug("Ignored malformed Veyra MQTT event")
            return
        if not isinstance(payload, dict):
            return

        event_type = str(payload.get("type") or "update")
        after = payload.get("after") or {}
        if not isinstance(after, dict):
            return
        event_id = str(after.get("id") or "")
        if not event_id:
            return

        if event_type == "end":
            self._events.pop(event_id, None)
            return
        if bool(after.get("false_positive", False)):
            return
        if after.get("notifications_enabled") is False:
            return

        label = str(after.get("label") or "object")
        level = self._class_level(label)
        if level == LEVEL_OFF:
            return

        seq = int(after.get("update_seq") or 0)
        state = self._events.setdefault(
            event_id,
            {"first_sent": False, "last_push": 0.0, "last_alert": 0.0, "last_seq": -1},
        )
        if seq <= int(state.get("last_seq", -1)) and event_type != "new":
            return

        now = time.monotonic()
        first = not bool(state.get("first_sent"))
        if not first:
            min_interval = float(
                self.entry.options.get(
                    CONF_NOTIFICATION_UPDATE_SECONDS, DEFAULT_NOTIFICATION_UPDATE_SECONDS
                )
            )
            if (now - float(state.get("last_push", 0.0))) < max(0.5, min_interval):
                state["last_seq"] = max(seq, int(state.get("last_seq", -1)))
                return

        alert_repeat = float(
            self.entry.options.get(
                CONF_NOTIFICATION_ALERT_REPEAT_SECONDS,
                DEFAULT_NOTIFICATION_ALERT_REPEAT_SECONDS,
            )
        )
        repeat_alert = (
            not first
            and level not in {LEVEL_OFF, LEVEL_SILENT}
            and alert_repeat > 0
            and (now - float(state.get("last_alert", 0.0))) >= alert_repeat
        )

        if first:
            send_level = level
        elif repeat_alert:
            send_level = LEVEL_URGENT if level in {LEVEL_URGENT, LEVEL_CRITICAL} else LEVEL_NORMAL
        else:
            send_level = LEVEL_SILENT

        await self._send(after, event_id, send_level, first=first, repeat_alert=repeat_alert)
        state["first_sent"] = True
        state["last_push"] = now
        if first or repeat_alert:
            state["last_alert"] = now
        state["last_seq"] = seq

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

    async def _send(
        self,
        after: dict[str, Any],
        event_id: str,
        level: str,
        *,
        first: bool,
        repeat_alert: bool,
    ) -> None:
        targets = self._targets()
        if not targets:
            _LOGGER.debug("No selected mobile_app notify targets available for Veyra")
            return

        camera = str(after.get("camera") or "kamera")
        label = str(after.get("label") or "obiekt")
        score = _score_percent(after.get("top_score", after.get("score")))
        title = self._title(label)
        message = self._camera_name(camera)
        if score is not None and score > 0:
            message += f"\n• pewność {score}%"

        data = self._payload(after, event_id, camera, level, first=first, repeat_alert=repeat_alert)
        call_data = {"title": title, "message": message, "data": data}
        current_services = self.hass.services.async_services().get("notify", {})
        for service in targets:
            if service not in current_services:
                continue
            try:
                await self.hass.services.async_call("notify", service, call_data, blocking=False)
            except HomeAssistantError as err:
                _LOGGER.warning("Unable to send Veyra notification via notify.%s: %s", service, err)

    def _payload(
        self,
        after: dict[str, Any],
        event_id: str,
        camera: str,
        level: str,
        *,
        first: bool,
        repeat_alert: bool,
    ) -> dict[str, Any]:
        version = _snapshot_version(after)
        image = f"/api/veyra/notifications/{self.entry.entry_id}/{event_id}/thumbnail.jpg?v={version}"
        try:
            when = int(float(after.get("start_time") or 0))
        except (TypeError, ValueError):
            when = 0

        data: dict[str, Any] = {
            "image": image,
            "tag": event_id,
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
            data.update(
                {
                    "push": {"interruption-level": "passive"},
                    "channel": "Veyra Ciche aktualizacje",
                    "importance": "low",
                    "alert_once": True,
                }
            )
        elif level == LEVEL_NORMAL:
            data.update(
                {
                    "push": {"interruption-level": "active", "sound": "default"},
                    "channel": "Veyra Aktualizacje" if repeat_alert else "Veyra",
                    "importance": "high" if repeat_alert else "default",
                    "vibrationPattern": "100, 450, 100, 450" if repeat_alert else "100, 250",
                    "alert_once": False,
                }
            )
        elif level == LEVEL_URGENT:
            data.update(
                {
                    "ttl": 0,
                    "priority": "high",
                    "push": {"interruption-level": "time-sensitive", "sound": "default"},
                    "channel": "Veyra Aktualizacje" if repeat_alert else "Veyra Security",
                    "importance": "high",
                    "vibrationPattern": "100, 500, 100, 500, 100" if repeat_alert else "100, 700, 100",
                    "alert_once": False,
                }
            )
        elif level == LEVEL_CRITICAL:
            data.pop("tag", None)
            data.update(
                {
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
                }
            )
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
        return web.Response(
            body=image,
            content_type="image/jpeg",
            headers={"Cache-Control": "no-store, max-age=0"},
        )
