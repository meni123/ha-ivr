"""התרגומים הרשמיים של Home Assistant, לשימוש סינכרוני בזמן שיחה.

`helpers.translation.async_get_translations` מחזיר את שמות הפעולות,
השדות, האפשרויות, המצבים והודעות השגיאה כפי שהם מוצגים בממשק.
הוא אסינכרוני, ושיחה בונה את העץ בקריאה סינכרונית, ולכן התרגומים
נטענים מראש לזיכרון ומתרעננים כשרכיב חדש עולה או כשהשפה משתנה.

התפריט הטלפוני מוקרא בעברית, ולכן כל ההקראה בעברית. HA משלים מפתח
חסר באנגלית, ומילה באנגלית באמצע משפט בעברית נשמעת כתקלה. לכן
ערך שזהה לאנגלית ויש בו אותיות לטיניות נחשב חסר, וההקראה עוברת
למילון המקומי (`translations_he`) או לשם מנורמל.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .model import speakable

_LOGGER = logging.getLogger(__name__)

# שפת ההקראה. כל המשפטים הקבועים בתפריט בעברית.
SPOKEN_LANGUAGE = "he"

CATEGORIES = ("services", "entity_component", "entity", "selector", "exceptions")

_DATA_KEY = "ha_ivr_i18n"
_LATIN = re.compile(r"[A-Za-z]")


def _store(hass: HomeAssistant) -> dict[str, Any]:
    return hass.data.setdefault(_DATA_KEY, {"he": {}, "en": {}, "unsub": None})


async def async_load(hass: HomeAssistant) -> None:
    """טעינה (או רענון) של כל הקטגוריות, בעברית ובאנגלית להשוואה."""
    try:
        from homeassistant.helpers.translation import (  # noqa: PLC0415
            async_get_translations,
        )
    except ImportError:
        return
    store = _store(hass)
    for language in (SPOKEN_LANGUAGE, "en"):
        merged: dict[str, str] = {}
        for category in CATEGORIES:
            try:
                merged.update(await async_get_translations(hass, language, category))
            except Exception:  # noqa: BLE001 — קטגוריה חסרה אינה מפילה הקראה
                _LOGGER.debug("Could not load %s translations (%s)", category, language,
                              exc_info=True)
        store[language] = merged


@callback
def async_setup_refresh(hass: HomeAssistant) -> None:
    """רענון כשרכיב חדש עולה. פעם אחת לכל ההתקנה, עם השהיה קצרה."""
    store = _store(hass)
    if store.get("unsub") is not None:
        return
    try:
        from homeassistant.const import (  # noqa: PLC0415
            EVENT_COMPONENT_LOADED,
            EVENT_CORE_CONFIG_UPDATE,
        )
        from homeassistant.helpers.event import async_call_later  # noqa: PLC0415
    except ImportError:
        return

    pending: dict[str, Any] = {"cancel": None}

    @callback
    def _schedule(_event=None) -> None:
        if pending["cancel"] is not None:
            pending["cancel"]()

        @callback
        def _run(_now) -> None:
            pending["cancel"] = None
            hass.async_create_task(async_load(hass), eager_start=True)

        # עלייה של HA מעלה מאות רכיבים בשניות. השהיה מאחדת אותם.
        pending["cancel"] = async_call_later(hass, 2.0, _run)

    unsubs = [
        hass.bus.async_listen(EVENT_COMPONENT_LOADED, _schedule),
        hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, _schedule),
    ]

    def _unsub() -> None:
        for unsub in unsubs:
            unsub()
        if pending["cancel"] is not None:
            pending["cancel"]()
        store["unsub"] = None

    store["unsub"] = _unsub


@callback
def async_unload(hass: HomeAssistant) -> None:
    store = hass.data.get(_DATA_KEY)
    if store and store.get("unsub") is not None:
        store["unsub"]()
    hass.data.pop(_DATA_KEY, None)


def _lookup(hass: HomeAssistant, key: str) -> str:
    """ערך בעברית, או ריק אם הוא חסר או שהוא בעצם האנגלית."""
    store = hass.data.get(_DATA_KEY)
    if not store:
        return ""
    value = store.get(SPOKEN_LANGUAGE, {}).get(key, "")
    if not value:
        return ""
    english = store.get("en", {}).get(key, "")
    if english and value == english and _LATIN.search(value):
        return ""
    return speakable(value)


# ----------------------------------------------------------------------
# שמות
# ----------------------------------------------------------------------


def action_name(hass: HomeAssistant, domain: str, action: str) -> str:
    return _lookup(hass, f"component.{domain}.services.{action}.name")


def field_name(hass: HomeAssistant, domain: str, action: str, field: str) -> str:
    return _lookup(hass, f"component.{domain}.services.{action}.fields.{field}.name")


def option_label(hass: HomeAssistant, domain: str, translation_key: str, value: str) -> str:
    if not translation_key:
        return ""
    return _lookup(hass, f"component.{domain}.selector.{translation_key}.options.{value}")


def state_name(
    hass: HomeAssistant,
    domain: str,
    state: str,
    *,
    device_class: str | None = None,
    platform: str | None = None,
    translation_key: str | None = None,
) -> str:
    """שם המצב, כמו בכרטיס של הישות בממשק."""
    if platform and translation_key:
        if found := _lookup(
            hass, f"component.{platform}.entity.{domain}.{translation_key}.state.{state}"
        ):
            return found
    if device_class:
        if found := _lookup(
            hass, f"component.{domain}.entity_component.{device_class}.state.{state}"
        ):
            return found
    return _lookup(hass, f"component.{domain}.entity_component._.state.{state}")


def attribute_value(
    hass: HomeAssistant,
    domain: str,
    attribute: str,
    value: str,
    *,
    device_class: str | None = None,
    platform: str | None = None,
    translation_key: str | None = None,
) -> str:
    """ערך של מאפיין: מצב מזגן, כיוון מאוורר, מצב הכנה."""
    if platform and translation_key:
        if found := _lookup(
            hass,
            f"component.{platform}.entity.{domain}.{translation_key}"
            f".state_attributes.{attribute}.state.{value}",
        ):
            return found
    for dc in (device_class, "_"):
        if not dc:
            continue
        if found := _lookup(
            hass,
            f"component.{domain}.entity_component.{dc}"
            f".state_attributes.{attribute}.state.{value}",
        ):
            return found
    return ""


def exception_message(hass: HomeAssistant, err: BaseException) -> str:
    """ההודעה המתורגמת של חריגה מתורגמת, או ריק.

    רק החלק המתורגם ולא `str(err)`: הודעה גולמית היא לרוב טקסט
    באנגלית שנועד למפתחים, ואין מקומה בהקראה.
    """
    domain = getattr(err, "translation_domain", None)
    key = getattr(err, "translation_key", None)
    if not domain or not key:
        return ""
    template = _lookup(hass, f"component.{domain}.exceptions.{key}.message")
    if not template:
        return ""
    placeholders = getattr(err, "translation_placeholders", None) or {}
    try:
        return template.format(**{k: str(v) for k, v in placeholders.items()})
    except (KeyError, IndexError, ValueError):
        return template


# ----------------------------------------------------------------------
# גישה בלי hass, לקוד שאין לו אותו בהישג יד
# ----------------------------------------------------------------------

# יש מופע אחד של Home Assistant בתהליך. פונקציות התרגום הישנות
# נקראות בלי hass מעשרות מקומות, ולכן הן נשענות על הקישור הזה.
_BOUND: list[HomeAssistant] = []


@callback
def bind(hass: HomeAssistant) -> None:
    _BOUND[:] = [hass]


def bound() -> HomeAssistant | None:
    return _BOUND[0] if _BOUND else None


def spoken_action(domain: str, action: str) -> str:
    hass = bound()
    return action_name(hass, domain, action) if hass and domain else ""


def spoken_field(domain: str, action: str, field: str) -> str:
    hass = bound()
    return field_name(hass, domain, action, field) if hass and domain else ""


def spoken_option(domain: str, field: str, value: str, translation_key: str = "") -> str:
    """ערך של בחירה, לפי ההקשר: מאפיין הישות, מצב הישות, או הבורר."""
    hass = bound()
    if hass is None or not domain:
        return ""
    if field:
        if found := attribute_value(hass, domain, field, value):
            return found
    # מצב מיזוג הוא גם מצב הישות; בחירה של `select` היא מצבה.
    if field in ("hvac_mode", "option", "operation_mode") or not field:
        if found := state_name(hass, domain, value):
            return found
    if found := option_label(hass, domain, translation_key or field, value):
        return found
    return ""
