"""אבחון — כפתור "הורד אבחון" בכרטיס האינטגרציה.

הכל נאסף למקום אחד שאפשר להוריד בלחיצה ולצרף לדיווח, בלי גישת
מעטפת לשרת ובלי תלות בסבב הלוגים.

מה שנאסף: ההגדרות בלי סודות, עץ התפריטים כפי שהוא נבנה בפועל
ולא כפי שהוגדר, החליפין האחרונים מול הספקים, ומצב הסביבה.

עץ התפריטים הוא החלק החשוב: הוא נבנה מחדש בכל שיחה מתת-הרשומות,
ולכן פער בין מה שהמשתמש חושב שהגדיר לבין מה שהמתקשר שומע אינו
נראה בשום מקום אחר.
"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import history
from . import menu as menu_mod
from . import registry
from .const import DOMAIN

# הסתרה לפי דפוס ולא לפי רשימת שמות: הטוקן הוא הסוד שמגן על
# נקודת הקצה, וקובץ אבחון ששותף בלעדיו הוא מפתח לתפריט. רשימת
# שמות מכסה רק את הספקים שהיו בה ביום שנכתבה, וספק חדש שיוסיף
# מפתח לא ייכלל בה.
#
# אותו רעיון כמו ב-`history._SECRET_HINTS`.
_SECRET_HINTS = ("token", "apikey", "api_key", "password", "secret", "bearer")

# מידע אישי שאינו סוד אך אינו שייך לקובץ ששותף. גם כאן דפוס
# ולא רשימה: כל שדה שמכיל מספרי טלפון, מאיזה ספק שיהיה.
_PERSONAL_HINTS = ("phone", "allowed_phones", "caller")


def _redact_keys(data: dict) -> set[str]:
    """כל מפתח שנראה כסוד או כמידע אישי, בכל עומק."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                low = str(key).lower()
                if any(h in low for h in _SECRET_HINTS + _PERSONAL_HINTS):
                    found.add(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


REDACTED = "**REDACTED**"

# ערכים שנראים כמו טלפון או כתובת SIP, בכל מקום ובכל שם מפתח.
# `async_redact_data` מסתיר רק לפי שם המפתח, ואינו נכנס ל-tuple או
# ל-set. מספר שנכנס לשם של פריט או לטקסט חופשי היה עובר.
_SIP_URI = re.compile(r"\bsips?:[^\s\"'<>]+", re.IGNORECASE)
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d\- ]{6,}\d(?![\w.])")


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _phone(match: re.Match) -> str:
    found = match.group()
    digits = sum(ch.isdigit() for ch in found)
    # תאריך ושעה אינם טלפון; מספר טלפון הוא 9 עד 15 ספרות.
    if _DATE.match(found) or not 9 <= digits <= 15:
        return found
    return REDACTED


def _scrub_text(text: str) -> str:
    text = _SIP_URI.sub(REDACTED, text)
    return _PHONE.sub(_phone, text)


def scrub(node: Any) -> Any:
    """הסתרה רקורסיבית: מפתחות וערכים, גם בתוך tuple, set ו-frozenset."""
    if isinstance(node, dict):
        out: dict = {}
        for key, value in node.items():
            low = str(key).lower()
            if any(h in low for h in _SECRET_HINTS + _PERSONAL_HINTS):
                out[_scrub_key(key)] = REDACTED
            else:
                out[_scrub_key(key)] = scrub(value)
        return out
    if isinstance(node, (list, tuple)):
        return [scrub(item) for item in node]
    if isinstance(node, (set, frozenset)):
        return sorted((scrub(item) for item in node), key=str)
    if isinstance(node, str):
        return _scrub_text(node)
    return node


def _scrub_key(key: Any) -> Any:
    return _scrub_text(key) if isinstance(key, str) else key


def _tree_summary(node: dict, depth: int = 0) -> dict[str, Any]:
    """העץ בצורה קריאה, בלי לחשוף שמות ידידותיים מיותרים."""
    out: dict[str, Any] = {
        "say": node.get("say", ""),
        "type": (
            "goto" if node.get("goto")
            else "menu" if node.get("items")
            else "leaf"
        ),
    }
    if entity := node.get("entity"):
        out["entity"] = entity
    if action := node.get("action"):
        out["action"] = action
    if data := node.get("data"):
        # ערכים קבועים של פעולה יכולים להיות טקסט חופשי — הודעה, מספר.
        # הם מוצגים רק כשמות השדות.
        out["data"] = sorted(str(k) for k in data) if isinstance(data, dict) else REDACTED
    if items := node.get("items"):
        out["items"] = {key: _tree_summary(child, depth + 1)
                        for key, child in sorted(items.items())}
    return out


def _capabilities(driver) -> dict:
    """הדגלים שהדרייבר מכריז עליהם.

    נקרא מהדרייבר ולא מרשימה בקוד: דגל חדש מופיע באבחון ביום
    שהוא נוסף, בלי שאיש יזכור לעדכן כאן.
    """
    if driver is None:
        return {}
    return {
        name: getattr(driver, name)
        for name in sorted(dir(driver))
        if name.isupper() and isinstance(getattr(driver, name), (bool, str))
        and not name.startswith("_")
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """כל מה שצריך כדי לאבחן שיחה, בלי סודות."""
    options = dict(entry.options)

    # העץ נבנה כאן באותה דרך בדיוק שבה הוא נבנה בשיחה. אם הבנייה
    # נכשלת — זו עצמה התשובה, ולכן הכשל נתפס ומוצג ולא מפיל את
    # האבחון.
    try:
        tree = _tree_summary(menu_mod.build_config(hass, entry))
        tree_error = None
    except Exception as err:  # noqa: BLE001
        tree, tree_error = {}, f"{type(err).__name__}: {err}"

    subentries: dict[str, int] = {}
    for subentry in entry.subentries.values():
        subentries[subentry.subentry_type] = subentries.get(
            subentry.subentry_type, 0
        ) + 1

    # אותה טביעה שנרשמת ביומן בטעינה. בקובץ אבחון היא עונה על
    # השאלה הראשונה שצריך לשאול: איזה קוד בכלל רץ כאן.
    from . import build_stamp  # noqa: PLC0415

    build = hass.data.get(DOMAIN, {}).get("build")

    if not build:
        build = await hass.async_add_executor_job(build_stamp)

    return scrub({
        "build": build,
        "entry": {
            "version": entry.version,
            "title": entry.title,
            "data": async_redact_data(
                dict(entry.data), _redact_keys(dict(entry.data))
            ),
            "options": async_redact_data(options, _redact_keys(options)),
        },
        # הגדרות הספק, בלי לדעת מי הוא: `options` כבר מוסתר
        # מסודות ב-`_redact_keys`, וכל שדה שספק יוסיף מופיע כאן
        # מעצמו.
        "provider": {
            "id": str(entry.data.get("provider", "")),
            "registered": registry.registered(),
            "capabilities": _capabilities(registry.for_entry(entry)),
        },
        "menu": {
            "subentries": subentries,
            "tree": tree,
            "build_error": tree_error,
        },
        # החלק שמחליף את גרירת היומן.
        "recent": history.snapshot(),
        "recent_capacity": history.MAX_EVENTS,
    })
