"""נמען התראה כישות `notify`.

פלטפורמת `notify` היא הממשק שדרכו כל מה שנבנה סביב התראות מגיע
לכאן: אינטגרציית `alert`, קבוצות `notify`, בוררי הישויות במסך
הסקריפטים, ובלופרינטים. שירות בדומיין ייעודי אינו נראה לאף אחד
מהם.

ישות לכל נמען, כי `async_send_message(message, title)` אינה
מקבלת נמען — הישות היא היעד. לכן כל נמען הוא תת-רשומה עם ישות
ושם משלו. השדה `phones` בשירות `send_call` משרת את המקרה ההפוך:
מספר שמחושב בזמן ריצה, מתבנית או מ-`person`.

הישות אינה יודעת איך מחייגים. היא קוראת ל-`async_notify` של
הדרייבר, ולכל ספק מסלול אחר: מי שיש לו ערוץ סטרימינג משמיע
הקראה של HA בסוקט, ומי שאין לו שולח טקסט ל-API שלו. ספק בלי
`async_notify` אינו מקבל ישויות כלל.
"""

from __future__ import annotations

import logging

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import registry
from .const import CONF_PHONE, SUBENTRY_TYPE_CONTACT

_LOGGER = logging.getLogger(__name__)


class IvrNotify(NotifyEntity):
    """נמען אחד. שליחה אליו מחייגת ומשמיעה."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:phone-message"

    def __init__(self, entry: ConfigEntry, subentry: ConfigSubentry) -> None:
        self._entry = entry
        self._subentry = subentry
        self._phone = str(dict(subentry.data).get(CONF_PHONE, ""))
        self._attr_unique_id = f"{entry.entry_id}_{subentry.subentry_id}_notify"
        # הישות היא המכשיר. עם `has_entity_name` שם הישות נדבק
        # לשם המכשיר, ושניהם זהים היו מייצרים מזהה כפול.
        # `None` מציין "אני המכשיר עצמו".
        self._attr_name = None
        self._attr_device_info = DeviceInfo(
            identifiers={(entry.domain, f"{entry.entry_id}_{subentry.subentry_id}")},
            name=subentry.title,
            manufacturer="IVR",
            model="נמען התראה",
            via_device=(entry.domain, entry.entry_id),
        )

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """חיוג לנמען והשמעת ההודעה.

        `title` נבלע בכוונה. בהתראה קולית אין כותרת — יש משפט
        שנשמע, והדבקת שתי מחרוזות הייתה מקריאה למתקשר טקסט
        שנועד למסך.
        """
        if not self._phone:
            raise HomeAssistantError(
                translation_domain="ha_ivr",
                translation_key="contact_no_phone",
                translation_placeholders={"name": str(self._subentry.title)},
            )
        await _notifier(self._entry)(
            self.hass, self._entry, message, [self._phone]
        )


def _notifier(entry):
    """`async_notify` של הדרייבר של הרשומה, או None."""
    driver = registry.for_entry(entry)
    return getattr(driver, "async_notify", None) if driver else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """ישות לכל נמען שהוגדר, אם הספק יודע לחייג."""
    if _notifier(entry) is None:
        _LOGGER.debug(
            "%s does not support outgoing alerts, no recipient entities", entry.domain
        )
        return

    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_CONTACT:
            continue
        async_add_entities(
            [IvrNotify(entry, subentry)], config_subentry_id=subentry_id
        )
