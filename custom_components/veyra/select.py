from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = entry.runtime_data
    classes = ((runtime.info.get("model") or {}).get("classes") or [])
    entities = []
    labels: set[str] = set()
    for item in classes:
        if isinstance(item, dict):
            label = str(item.get("name") or f"class_{item.get('id', '')}")
            class_id = item.get("id")
        else:
            label = str(item)
            class_id = None
        labels.add(label)
        entities.append(VeyraClassNotificationSelect(runtime, entry, label, class_id))

    # Glare Motion Guard is a security signal rather than a Coral model class,
    # but it uses the same notification-level control in Home Assistant.
    if "glare" not in labels:
        entities.append(VeyraClassNotificationSelect(runtime, entry, "glare", "glare"))
    async_add_entities(entities)


class VeyraClassNotificationSelect(VeyraEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bell-cog-outline"
    _attr_options = [LEVEL_TO_PL[level] for level in NOTIFICATION_LEVELS]

    def __init__(self, runtime, entry: ConfigEntry, label: str, class_id) -> None:
        super().__init__(runtime)
        self.entry = entry
        self.label = label
        self.class_id = class_id
        safe = "".join(ch if ch.isalnum() else "_" for ch in label.lower()).strip("_")
        self._attr_unique_id = f"{self.instance_id}_notification_level_{class_id if class_id is not None else safe}"
        self._attr_name = (
            "Powiadomienia · oślepianie kamery"
            if label == "glare"
            else f"Powiadomienia · {label}"
        )

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
