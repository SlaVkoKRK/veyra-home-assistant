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
    CONF_NOTIFICATION_UPDATE_SECONDS,
    CONF_NOTIFY_TARGETS,
    DEFAULT_NOTIFICATION_UPDATE_SECONDS,
    LEVEL_CRITICAL,
    LEVEL_NORMAL,
    LEVEL_OFF,
    LEVEL_SILENT,
    LEVEL_URGENT,
    default_class_level,
)

_LOGGER = logging.getLogger(__name__)


def _score_text(value: Any) -> str:
    try:
        v = float(value)
        if v <= 1.0:
            v *= 100.0
        return f"{v:.0f}%"
    except (TypeError, ValueError):
        return ""


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
            {"loud_sent": False, "last_push": 0.0, "last_seq": -1},
        )
        if seq <= int(state.get("last_seq", -1)) and event_type != "new":
            return

        now = time.monotonic()
        first = not bool(state.get("loud_sent"))
        if not first:
            min_interval = float(
                self.entry.options.get(
                    CONF_NOTIFICATION_UPDATE_SECONDS, DEFAULT_NOTIFICATION_UPDATE_SECONDS
                )
            )
            if (now - float(state.get("last_push", 0.0))) < max(0.5, min_interval):
                state["last_seq"] = max(seq, int(state.get("last_seq", -1)))
                return

        send_level = level if first else LEVEL_SILENT
        await self._send(after, event_id, send_level, first=first)
        state["loud_sent"] = True
        state["last_push"] = now
        state["last_seq"] = seq

    def _class_level(self, label: str) -> str:
        levels = self.entry.options.get(CONF_CLASS_LEVELS, {})
        if isinstance(levels, dict) and label in levels:
            return str(levels[label])
        return default_class_level(label)

    def _targets(self) -> list[str]:
        configured = self.entry.options.get(CONF_NOTIFY_TARGETS)
        if configured:
            return [str(x).replace("notify.", "") for x in configured]
        services = self.hass.services.async_services().get("notify", {})
        return sorted(str(name) for name in services if str(name).startswith("mobile_app_"))

    async def _send(self, after: dict[str, Any], event_id: str, level: str, *, first: bool) -> None:
        targets = self._targets()
        if not targets:
            _LOGGER.debug("No mobile_app notify targets available for Veyra")
            return

        camera = str(after.get("camera") or "kamera")
        label = str(after.get("label") or "obiekt")
        score = _score_text(after.get("top_score", after.get("score")))
        title = f"🚨 Veyra · {label}"
        message = f"{camera.replace('_', ' ').title()}"
        if score:
            message += f" · {score}"

        data = self._payload(event_id, camera, level, first=first)
        call_data = {"title": title, "message": message, "data": data}
        for service in targets:
            if service not in self.hass.services.async_services().get("notify", {}):
                continue
            try:
                await self.hass.services.async_call(
                    "notify", service, call_data, blocking=False
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Unable to send Veyra notification via notify.%s: %s", service, err)

    def _payload(self, event_id: str, camera: str, level: str, *, first: bool) -> dict[str, Any]:
        image = f"/api/veyra/notifications/{self.entry.entry_id}/{event_id}/thumbnail.jpg"
        tag = f"veyra_{event_id}"
        group = f"veyra_{camera}"
        data: dict[str, Any] = {"image": image, "group": group}

        if level == LEVEL_SILENT:
            data.update(
                {
                    "tag": tag,
                    "push": {"interruption-level": "passive"},
                    "channel": "Veyra Updates",
                    "importance": "low",
                }
            )
        elif level == LEVEL_NORMAL:
            data.update(
                {
                    "tag": tag,
                    "push": {"interruption-level": "active"},
                    "channel": "Veyra",
                    "importance": "default",
                }
            )
        elif level == LEVEL_URGENT:
            data.update(
                {
                    "tag": tag,
                    "ttl": 0,
                    "priority": "high",
                    "push": {"interruption-level": "time-sensitive"},
                    "channel": "Veyra Security",
                    "importance": "high",
                }
            )
        elif level == LEVEL_CRITICAL:
            data.update(
                {
                    "ttl": 0,
                    "priority": "high",
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
                }
            )
            if not first:
                data["tag"] = tag
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
