from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory

from .const import CONF_CLASS_LEVELS, NOTIFICATION_LEVELS, default_class_level
from .entity import VeyraEntity

PARALLEL_UPDATES = 0

LEVEL_TO_PL = {
    "off": "Wyłączone",
    "silent": "Ciche",
    "normal": "Normalne",
    "urgent": "Pilne",
    "critical": "Krytyczne",
}
PL_TO_LEVEL = {value: key for key, value in LEVEL_TO_PL.items()}


def _notification_unique_id(instance_id: str, label: str, class_id) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in label.lower()).strip("_")
    token = class_id if class_id is not None else safe
    return f"{instance_id}_notification_level_{token}"


def _model_class_map(runtime) -> dict[str, Any]:
    """Return model label -> class id without assuming a fixed class set."""
    result: dict[str, Any] = {}
    classes = ((runtime.info.get("model") or {}).get("classes") or [])
    for item in classes:
        if isinstance(item, dict):
            label = str(item.get("name") or f"class_{item.get('id', '')}").strip()
            class_id = item.get("id")
        else:
            label = str(item).strip()
            class_id = None
        if label:
            result[label] = class_id
    return result


def _selected_labels(runtime) -> set[str] | None:
    """Union classes enabled on at least one Veyra camera.

    ``None`` means that CORE is too old to expose ``detect_classes``. In that
    case the platform falls back to all model classes for backwards
    compatibility instead of making every notification selector disappear.
    """
    data = runtime.coordinator.data or {}
    cameras = data.get("cameras") or {}
    if not isinstance(cameras, dict):
        return None

    found_capability = False
    labels: set[str] = set()
    for camera_data in cameras.values():
        if not isinstance(camera_data, dict) or "detect_classes" not in camera_data:
            continue
        found_capability = True
        raw = camera_data.get("detect_classes") or []
        if isinstance(raw, str):
            raw = [raw]
        for item in raw:
            label = str(item).strip()
            if label:
                labels.add(label)

    return labels if found_capability else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Callable,
) -> None:
    manager = VeyraNotificationSelectManager(hass, entry, async_add_entities)
    await manager.async_start()


class VeyraNotificationSelectManager:
    """Keep notification selectors in sync with classes selected in Veyra."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, async_add_entities: Callable) -> None:
        self.hass = hass
        self.entry = entry
        self.runtime = entry.runtime_data
        self.async_add_entities = async_add_entities
        self._entities: dict[str, VeyraClassNotificationSelect] = {}
        self._lock = asyncio.Lock()
        self._unsub = None
        self._stopped = False

    async def async_start(self) -> None:
        # Glare is a security signal, not a model class. It is always present and
        # intentionally added first so its configuration stays at the top.
        glare = VeyraClassNotificationSelect(self.runtime, self.entry, "glare", "glare")
        self._entities["glare"] = glare
        self.async_add_entities([glare])

        await self._async_sync()
        self._unsub = self.runtime.coordinator.async_add_listener(self._schedule_sync)
        self.entry.async_on_unload(self._unload)

    def _schedule_sync(self) -> None:
        if self._stopped:
            return
        self.hass.async_create_task(self._async_sync())

    def _unload(self) -> None:
        self._stopped = True
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    async def _async_sync(self) -> None:
        if self._stopped:
            return
        async with self._lock:
            class_map = _model_class_map(self.runtime)
            selected = _selected_labels(self.runtime)
            if selected is None:
                desired = set(class_map)
            else:
                # Keep only model classes, but tolerate a custom class reported by
                # CORE even if model metadata has not refreshed yet.
                desired = {str(label) for label in selected if str(label) and str(label) != "glare"}

            current = set(self._entities) - {"glare"}

            # Also clean stale registry entries left by older integration versions,
            # which used to register every model class on startup. Do not remove a
            # registry row while the matching entity object is still mounted; live
            # removals below handle those in the correct order.
            registry = er.async_get(self.hass)
            allowed_unique_ids = {
                _notification_unique_id(self._entities["glare"].instance_id, "glare", "glare")
            }
            for label in desired:
                allowed_unique_ids.add(
                    _notification_unique_id(
                        self._entities["glare"].instance_id,
                        label,
                        class_map.get(label),
                    )
                )
            prefix = f"{self._entities['glare'].instance_id}_notification_level_"
            mounted_entity_ids = {
                entity.entity_id
                for entity in self._entities.values()
                if entity.entity_id
            }
            for reg_entry in er.async_entries_for_config_entry(registry, self.entry.entry_id):
                if (
                    reg_entry.domain == "select"
                    and str(reg_entry.unique_id).startswith(prefix)
                    and reg_entry.unique_id not in allowed_unique_ids
                    and reg_entry.entity_id not in mounted_entity_ids
                ):
                    registry.async_remove(reg_entry.entity_id)

            # Remove first. If a class disappears from all cameras, its entity is
            # removed from the entity registry as well, not merely marked unavailable.
            for label in sorted(current - desired):
                entity = self._entities.pop(label, None)
                if entity is None:
                    continue
                entity_id = entity.entity_id
                await entity.async_remove()
                if entity_id and registry.async_get(entity_id) is not None:
                    registry.async_remove(entity_id)

            additions: list[VeyraClassNotificationSelect] = []
            for label in sorted(desired - current, key=str.casefold):
                entity = VeyraClassNotificationSelect(
                    self.runtime,
                    self.entry,
                    label,
                    class_map.get(label),
                )
                self._entities[label] = entity
                additions.append(entity)

            if additions:
                self.async_add_entities(additions)


class VeyraClassNotificationSelect(VeyraEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = [LEVEL_TO_PL[level] for level in NOTIFICATION_LEVELS]

    def __init__(self, runtime, entry: ConfigEntry, label: str, class_id) -> None:
        super().__init__(runtime)
        self.entry = entry
        self.label = label
        self.class_id = class_id
        self._attr_unique_id = _notification_unique_id(
            self.instance_id, label, class_id
        )
        if label == "glare":
            # The name also sorts before the regular "Powiadomienia · ..."
            # selectors in HA's standard entity lists.
            self._attr_name = "Oślepianie kamery · powiadomienia"
            self._attr_icon = "mdi:car-light-high"
        else:
            self._attr_name = f"Powiadomienia · {label}"
            self._attr_icon = "mdi:bell-cog-outline"

    @property
    def current_option(self) -> str:
        levels = self.entry.options.get(CONF_CLASS_LEVELS, {})
        if isinstance(levels, dict) and self.label in levels:
            value = str(levels[self.label])
            if value in NOTIFICATION_LEVELS:
                return LEVEL_TO_PL[value]
        return LEVEL_TO_PL[default_class_level(self.label)]

    async def async_select_option(self, option: str) -> None:
        internal = PL_TO_LEVEL.get(option)
        if internal not in NOTIFICATION_LEVELS:
            return
        options = dict(self.entry.options)
        levels = dict(options.get(CONF_CLASS_LEVELS, {}) or {})
        levels[self.label] = internal
        options[CONF_CLASS_LEVELS] = levels
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self.async_write_ha_state()
