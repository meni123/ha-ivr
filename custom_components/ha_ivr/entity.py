"""מחלקת בסיס לישויות המשויכות לפריט תפריט."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_ACTION, CONF_MENU_PATH, CONF_TARGET_ENTITY
from .menu import normalize_path


class IvrItemEntity(Entity):
    """כל פריט מקבל התקן משלו, מקושר להתקן הראשי."""

    _attr_has_entity_name = True

    def __init__(self, entry, subentry: ConfigSubentry) -> None:
        self._entry = entry
        self._subentry = subentry
        data = dict(subentry.data)
        self.path = normalize_path(data.get(CONF_MENU_PATH))
        self.digit = self.path.rsplit("/", 1)[-1] if self.path else ""
        self.target_entity = str(data.get(CONF_TARGET_ENTITY, ""))
        self.action = str(data.get(CONF_ACTION, "") or "")

        # הדומיין אחד לכל הספקים, והרשומה היא מה שמפריד ביניהם.
        self._attr_device_info = DeviceInfo(
            identifiers={(entry.domain, f"{entry.entry_id}_{subentry.subentry_id}")},
            name=subentry.title,
            manufacturer="IVR",
            model="פריט תפריט",
            via_device=(entry.domain, entry.entry_id),
        )

    @property
    def _unique_prefix(self) -> str:
        return f"{self._entry.entry_id}_{self._subentry.subentry_id}"
