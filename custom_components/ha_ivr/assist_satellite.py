"""ישויות הלוויין — קו לכל שיחה מקבילה.

`AssistSatelliteEntity` מחזיקה משימת צינור אחת, ו-
`_cancel_running_pipeline` רצה בתחילת כל קבלה — שתי שיחות על
אותה ישות פירושן שהשנייה הורגת את הראשונה. לכן המקביליות היא
במספר הישויות ולא בתקרה מספרית.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SATELLITES, STREAM_LINES
from .satellite import IvrSatellite


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """הקווים של הרשומה, ורישום שלהם כדי שהגשר ימצא אותם."""
    lines = [IvrSatellite(entry, index) for index in range(STREAM_LINES)]
    hass.data.setdefault(SATELLITES, {})[entry.entry_id] = lines

    @callback
    def _forget() -> None:
        """חייבת להחזיר None.

        `_async_process_on_unload` מנסה להפוך ערך מוחזר למשימה
        ונופל ב-`TypeError: a coroutine was expected`. הפריקה
        נעצרת באמצע, והלוויין נעלם אחרי כל שינוי הגדרות.
        """
        hass.data.get(SATELLITES, {}).pop(entry.entry_id, None)

    entry.async_on_unload(_forget)
    async_add_entities(lines)
