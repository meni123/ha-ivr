"""הקראת מצב של ישות: המילה, ומה שחשוב לשמוע לצדה.

"מזגן סלון על קירור" אינו מספיק למי שהתקשר כדי לדעת אם חם בבית.
לכן לכל דומיין יש תקציר קצר: טמפרטורה נוכחית ומכוונת במזגן, בהירות
בנורה, מיקום בתריס. התקציר קצר בכוונה — כל משפט נוסף הוא עוד זמן
האזנה.

המילה של המצב מגיעה קודם מהניסוח המקומי (נכתב להקראה), אחר כך
מהתרגום הרשמי של HA לפי `translation_key` ו-`device_class`, ובסוף
הערך עצמו. מספרים לעולם אינם טקסט — ראו `say_number`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from . import i18n
from .model import Say, say_number
from .translations_he import translate_option, translate_unit

_LOGGER = logging.getLogger(__name__)

# ניסוח מקומי למצבים הנפוצים, כפי שנשמעים טוב בטלפון.
STATE_WORDS: dict[str, str] = {
    "on": "דולק", "off": "כבוי", "locked": "נעול", "unlocked": "לא נעול",
    "locking": "ננעל", "unlocking": "נפתח", "jammed": "תקוע",
    "open": "פתוח", "closed": "סגור", "opening": "נפתח", "closing": "נסגר",
    "cool": "על קירור", "heat": "על חימום", "fan_only": "על אוורור",
    "dry": "על ייבוש", "auto": "על אוטומטי", "heat_cool": "על חימום וקירור",
    "idle": "ממתין", "playing": "מנגן", "paused": "מושהה", "home": "בבית",
    "not_home": "מחוץ לבית", "unavailable": "לא זמין", "unknown": "לא ידוע",
    "armed_home": "דרוך בבית", "armed_away": "דרוך מחוץ לבית",
    "armed_night": "דרוך ללילה", "armed_vacation": "דרוך לחופשה",
    "armed_custom_bypass": "דרוך עם עקיפה", "disarmed": "מנוטרל",
    "arming": "בדריכה", "disarming": "בנטרול", "pending": "ממתין", "triggered": "הופעל",
    "cleaning": "מנקה", "docked": "בעגינה", "returning": "חוזר לעגינה",
    "mowing": "מכסח", "error": "בתקלה",
}

# מצבים שהמשמעות שלהם תלויה בדומיין. אוטומציה "דולקת" היא אוטומציה
# מופעלת, ותסריט "דולק" הוא תסריט שרץ עכשיו.
DOMAIN_STATE_WORDS: dict[tuple[str, str], str] = {
    ("automation", "on"): "מופעלת",
    ("automation", "off"): "מושבתת",
    ("script", "on"): "רץ",
    ("script", "off"): "לא רץ",
}

# מילים שאחריהן אין טעם להקריא יחידה או תקציר.
NO_DETAIL = frozenset({"unavailable", "unknown"})

_MONTHS = (
    "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
    "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר",
)

# יחידות שכבר נרשמו ביומן כלא מתורגמות. פעם אחת לכל יחידה.
_UNKNOWN_UNITS: set[str] = set()


def _domain(state) -> str:
    entity_id = str(getattr(state, "entity_id", "") or "")
    return entity_id.split(".", 1)[0] if "." in entity_id else ""


def _registry(hass, entity_id: str):
    if hass is None or not entity_id:
        return None
    try:
        from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

        return er.async_get(hass).async_get(entity_id)
    except Exception:  # noqa: BLE001
        return None


def state_word(state, hass=None) -> str:
    """המצב כמילה. ריק אם הוא מספר (ונאמר כמספר)."""
    hass = hass or i18n.bound()
    raw = str(state.state)
    lowered = raw.lower()
    domain = _domain(state)
    if found := DOMAIN_STATE_WORDS.get((domain, lowered)):
        return found
    if lowered in STATE_WORDS:
        return STATE_WORDS[lowered]

    if hass is not None and domain:
        entry = _registry(hass, getattr(state, "entity_id", ""))
        found = i18n.state_name(
            hass,
            domain,
            raw,
            device_class=state.attributes.get("device_class"),
            platform=getattr(entry, "platform", None),
            translation_key=getattr(entry, "translation_key", None),
        )
        if found:
            return found

    translated = translate_option(raw, domain)
    if translated != raw:
        return translated
    if _number(raw) is not None:
        return ""
    return raw


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unit_words(unit: str) -> list[Say]:
    unit = str(unit or "").strip()
    if not unit:
        return []
    spoken = translate_unit(unit)
    if spoken:
        return [Say("text", spoken)]
    if unit not in _UNKNOWN_UNITS:
        # לא מוקרא, אבל כן נרשם: המילון גדל לפי מה שבאמת מופיע
        # אצל המשתמש, במקום לנחש מראש רשימת יחידות.
        _UNKNOWN_UNITS.add(unit)
        _LOGGER.info(
            "Unit of measurement with no translation, so it is not spoken: "
            "%r. It can be added to UNIT_NAMES in translations_he.py",
            unit,
        )
    return []


def _rounded(hass, state) -> float | None:
    """הערך המספרי, מעוגל כמו בממשק (`display_precision`)."""
    value = _number(state.state)
    if value is None:
        return None
    if hass is not None and _domain(state) == "sensor":
        try:
            from homeassistant.components.sensor import (  # noqa: PLC0415
                async_rounded_state,
            )

            rounded = _number(async_rounded_state(hass, state.entity_id, state))
            if rounded is not None:
                return rounded
        except Exception:  # noqa: BLE001 — בלי העיגול של HA, עיגול רגיל
            pass
    return value


def say_time(value: Any, now: datetime | None = None) -> list[Say]:
    """זמן מוחלט בזמן המקומי: "היום בשעה 19 ו-35", "אתמול", או תאריך."""
    try:
        from homeassistant.util import dt as dt_util  # noqa: PLC0415

        parsed = value if isinstance(value, datetime) else dt_util.parse_datetime(str(value))
        if parsed is None:
            return []
        local = dt_util.as_local(parsed)
        now = dt_util.as_local(now or dt_util.now())
    except Exception:  # noqa: BLE001 — בלי עזרי הזמן של HA אין הקראה
        return []

    says: list[Say] = []
    days = (local.date() - now.date()).days
    if days == 0:
        says.append(Say("text", "היום"))
    elif days == -1:
        says.append(Say("text", "אתמול"))
    elif days == 1:
        says.append(Say("text", "מחר"))
    else:
        says.extend(say_number(local.day))
        says.append(Say("text", f"ב{_MONTHS[local.month - 1]}"))
        if local.year != now.year:
            says.extend(say_number(local.year))
    says.append(Say("text", "בשעה"))
    says.extend(say_number(local.hour))
    if local.minute:
        says.append(Say("text", "ו"))
        says.extend(say_number(local.minute))
        says.append(Say("text", "דקות"))
    return says


def _percent(value: Any) -> list[Say]:
    number = _number(value)
    if number is None:
        return []
    return [*say_number(round(number)), Say("text", "אחוז")]


def _degrees(value: Any) -> list[Say]:
    number = _number(value)
    if number is None:
        return []
    return [*say_number(number), Say("text", "מעלות")]


def details(state, hass=None) -> list[Say]:
    """התקציר שאחרי המילה — לפי הדומיין, ורק מה שקיים."""
    raw = str(state.state).lower()
    if raw in NO_DETAIL:
        return []
    domain = _domain(state)
    attrs = state.attributes
    out: list[Say] = []

    if domain == "light" and raw == "on":
        brightness = _number(attrs.get("brightness"))
        if brightness is not None:
            # 0..255 ב-HA. 100 אחוז הם 255.
            out += [Say("text", "בהירות"), *_percent(brightness * 100 / 255)]
    elif domain == "climate":
        action = attrs.get("hvac_action")
        if action is not None and str(action) not in ("off", "idle"):
            word = translate_option(str(action), "climate", "hvac_action")
            if word != str(action):
                out.append(Say("text", word))
        if (current := _number(attrs.get("current_temperature"))) is not None:
            out += [Say("text", "הטמפרטורה בחדר"), *_degrees(current)]
        if raw != "off":
            low, high = attrs.get("target_temp_low"), attrs.get("target_temp_high")
            target = attrs.get("temperature")
            if _number(target) is not None:
                out += [Say("text", "מכוון ל"), *_degrees(target)]
            elif _number(low) is not None and _number(high) is not None:
                out += [Say("text", "מכוון בין"), *say_number(float(low)),
                        Say("text", "ל"), *_degrees(high)]
    elif domain == "water_heater":
        if (target := _number(attrs.get("temperature"))) is not None:
            out += [Say("text", "מכוון ל"), *_degrees(target)]
    elif domain == "humidifier" and raw == "on":
        if (target := _number(attrs.get("humidity"))) is not None:
            out += [Say("text", "לחות מכוונת"), *_percent(target)]
    elif domain == "cover":
        position = _number(attrs.get("current_position"))
        if position is not None and raw not in ("closed",) and 0 < position < 100:
            out += [Say("text", "במיקום"), *_percent(position)]
    elif domain == "valve":
        position = _number(attrs.get("current_position"))
        if position is not None and 0 < position < 100:
            out += [Say("text", "במיקום"), *_percent(position)]
    elif domain == "fan" and raw == "on":
        if (percentage := _number(attrs.get("percentage"))) is not None:
            out += [Say("text", "מהירות"), *_percent(percentage)]
    elif domain == "media_player" and raw in ("playing", "paused", "on", "buffering"):
        title = str(attrs.get("media_title") or "").strip()
        if title:
            out.append(Say("text", title[:80]))
        volume = _number(attrs.get("volume_level"))
        if volume is not None:
            out += [Say("text", "עוצמה"), *_percent(volume * 100)]
    elif domain == "vacuum" and (battery := _number(attrs.get("battery_level"))) is not None:
        out += [Say("text", "סוללה"), *_percent(battery)]
    return out


def speak_state(state, hass=None) -> list[Say]:
    """מצב ישות כפריטי השמעה: מילה או מספר עם יחידה, ותקציר."""
    hass = hass or i18n.bound()
    raw = str(state.state)
    domain = _domain(state)
    device_class = state.attributes.get("device_class")

    if raw.lower() not in NO_DETAIL:
        # זמן: חיישן זמן, או ישות תאריך ושעה.
        if device_class in ("timestamp", "uptime") or domain in ("datetime",):
            if spoken := say_time(raw):
                return spoken
        if domain in ("date", "input_datetime") and len(raw) == 10:
            if spoken := say_time(f"{raw}T00:00:00"):
                # רק התאריך — בלי "בשעה 0".
                return spoken[: max(1, len(spoken) - 2)]

    word = state_word(state, hass)
    if word:
        return [Say("text", word), *details(state, hass)]

    number = _rounded(hass, state)
    if number is None:
        return [Say("text", raw)]
    parts = list(say_number(number))
    parts += _unit_words(state.attributes.get("unit_of_measurement", ""))
    return parts


def speak_word(raw: str, domain: str = "") -> list[Say]:
    """מילת המצב בלבד, בלי יחידות — לסיכום של קבוצה."""
    lowered = raw.lower()
    if found := DOMAIN_STATE_WORDS.get((domain, lowered)):
        return [Say("text", found)]
    if lowered in STATE_WORDS:
        return [Say("text", STATE_WORDS[lowered])]
    hass = i18n.bound()
    if hass is not None and domain and (found := i18n.state_name(hass, domain, raw)):
        return [Say("text", found)]
    translated = translate_option(raw, domain)
    return [Say("text", translated if translated != raw else raw)]
