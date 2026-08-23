"""חיישני שיחות עבור פריטי התפריט."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import SUBENTRY_TYPE_ITEM, signal_call_received
from .entity import IvrItemEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """חיישן לכל פריט."""
    # ההתקן ההורה נוצר מפורשות. בלעדיו כל via_device מצביע להתקן
    # שאינו קיים, HA מזהיר, וההתנהגות אמורה להפסיק לעבוד בגרסה
    # עתידית.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(entry.domain, entry.entry_id)},
        # שם הספק נכנס לשם ההתקן: בלעדיו כל הרשומות נקראות
        # "תפריט טלפוני", ו-HA מפרידה ביניהן במספרים בלבד —
        # מזהי ישויות כמו `_2` ו-`_2_2` שאי אפשר לזהות לפיהם
        # למי הם שייכים.
        #
        # מזהי הישויות הקיימות אינם משתנים מזה: הם נקבעו ברישום
        # ונשארים. השם משפיע על מה שנוצר מכאן והלאה, ועל מה
        # שמוצג במסך ההתקן.
        name=f"תפריט טלפוני — {entry.title}",
        manufacturer="IVR",
        model="שכבת ספק",
        entry_type=DeviceEntryType.SERVICE,
    )

    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_ITEM:
            continue
        async_add_entities(
            [LastCallSensor(entry, subentry), CallCountSensor(entry, subentry)],
            config_subentry_id=subentry_id,
        )


class _CallTracking(IvrItemEntity, SensorEntity):
    """בסיס לחיישן שמתעדכן בעת בחירה בתפריט.

    אין להוסיף כאן את RestoreEntity. RestoreSensor יורשת מ-SensorEntity
    ואחר כך מ-RestoreEntity, ולכן הוספה כאן בסדר ההפוך יוצרת סדר
    ירושה בלתי אפשרי וכשל בייבוא המודול.
    """

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_call_received(self._entry.entry_id),
                self._handle,
            )
        )

    @callback
    def _handle(self, path: str) -> None:
        """טיפול בבחירה, אם היא שייכת לפריט הזה.

        ההשוואה לפי הנתיב המלא. ספרה בודדת חוזרת בכל רמה ולכן
        אינה מזהה פריט.
        """
        if str(path) != self.path:
            return
        self._on_call()
        self.async_write_ha_state()

    def _on_call(self) -> None:
        raise NotImplementedError


class LastCallSensor(_CallTracking, RestoreSensor):
    """מועד הבחירה האחרונה בפריט."""

    _attr_translation_key = "last_call"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: ConfigEntry, subentry: ConfigSubentry) -> None:
        super().__init__(entry, subentry)
        self._attr_unique_id = f"{self._unique_prefix}_last_call"
        self._value: datetime | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            if isinstance(last.native_value, datetime):
                self._value = last.native_value

    @property
    def native_value(self) -> datetime | None:
        return self._value

    def _on_call(self) -> None:
        self._value = dt_util.utcnow()


class CallCountSensor(_CallTracking, RestoreEntity):
    """מספר הפעמים שהפריט נבחר."""

    _attr_translation_key = "call_count"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "בחירות"

    def __init__(self, entry: ConfigEntry, subentry: ConfigSubentry) -> None:
        super().__init__(entry, subentry)
        self._attr_unique_id = f"{self._unique_prefix}_call_count"
        self._count = 0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            try:
                self._count = int(float(last.state))
            except (TypeError, ValueError):
                self._count = 0

    @property
    def native_value(self) -> int:
        return self._count

    def _on_call(self) -> None:
        self._count += 1
