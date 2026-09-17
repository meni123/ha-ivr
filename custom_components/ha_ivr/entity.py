"""מחלקת בסיס לישויות המשויכות לפריט תפריט."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_ACTION, CONF_MENU_PATH, CONF_TARGET_ENTITY
from .menu import normalize_path

# `via_device` (זוג מזהים) הוצא משימוש לטובת `via_device_id` (מזהה
# רישום). גרסאות ישנות אינן מכירות את החדש, ולכן הבחירה לפי מה
# ש-DeviceInfo של הגרסה הרצה מצהיר.
_VIA_BY_ID = "via_device_id" in getattr(DeviceInfo, "__annotations__", {})


def ensure_parent_device(hass, entry) -> str:
    """ההתקן הראשי של הרשומה; נוצר אם חסר. מחזיר את מזהה הרישום.

    נקרא לפני הפלטפורמות, כדי שכל ישות תמצא אותו. בלעדיו כל
    קישור-ילד מצביע להתקן שאינו קיים ו-HA מזהיר.
    """
    # שם הספק נכנס לשם ההתקן: בלעדיו כל הרשומות נקראות
    # "תפריט טלפוני", ו-HA מפרידה ביניהן במספרים בלבד —
    # מזהי ישויות כמו `_2` ו-`_2_2` שאי אפשר לזהות לפיהם
    # למי הם שייכים.
    #
    # מזהי הישויות הקיימות אינם משתנים מזה: הם נקבעו ברישום
    # ונשארים. השם משפיע על מה שנוצר מכאן והלאה, ועל מה
    # שמוצג במסך ההתקן.
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(entry.domain, entry.entry_id)},
        name=f"תפריט טלפוני — {entry.title}",
        manufacturer="IVR",
        model="שכבת ספק",
        entry_type=DeviceEntryType.SERVICE,
    )
    return device.id


def child_device_info(hass, entry, subentry: ConfigSubentry, model: str) -> DeviceInfo:
    """התקן משלו לפריט, מקושר להתקן הראשי."""
    info = DeviceInfo(
        identifiers={(entry.domain, f"{entry.entry_id}_{subentry.subentry_id}")},
        name=subentry.title,
        manufacturer="IVR",
        model=model,
    )
    if _VIA_BY_ID:
        info["via_device_id"] = ensure_parent_device(hass, entry)
    else:
        info["via_device"] = (entry.domain, entry.entry_id)
    return info


class IvrItemEntity(Entity):
    """כל פריט מקבל התקן משלו, מקושר להתקן הראשי."""

    _attr_has_entity_name = True
    _device_model = "פריט תפריט"

    def __init__(self, entry, subentry: ConfigSubentry) -> None:
        self._entry = entry
        self._subentry = subentry
        data = dict(subentry.data)
        self.path = normalize_path(data.get(CONF_MENU_PATH))
        self.digit = self.path.rsplit("/", 1)[-1] if self.path else ""
        self.target_entity = str(data.get(CONF_TARGET_ENTITY, ""))
        self.action = str(data.get(CONF_ACTION, "") or "")


    @property
    def device_info(self) -> DeviceInfo:
        # property ולא `_attr_`: מזהה ההורה דורש את הרישום, ו-`hass`
        # קיים רק אחרי ההוספה לפלטפורמה. הדומיין אחד לכל הספקים,
        # והרשומה היא מה שמפריד ביניהם.
        return child_device_info(
            self.hass, self._entry, self._subentry, self._device_model
        )

    @property
    def _unique_prefix(self) -> str:
        return f"{self._entry.entry_id}_{self._subentry.subentry_id}"
