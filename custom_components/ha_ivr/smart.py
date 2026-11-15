"""ישות חכמה — גילוי אוטומטי של מה שמכשיר יודע לעשות.

בפריט רגיל המשתמש מגדיר כל פעולה בנפרד: מספר, פעולה, ערך. במזגן
זה עשרות פריטים, ולכוונון טמפרטורה זה פריט לכל מעלה — לא סביר.

כאן שואלים את Home Assistant מה המכשיר תומך בו, וממציאים ממנו
תפריט שלם. המשתמש רק מחריג את מה שאינו רוצה.

המספרים ננעלים בהגדרה ואינם מחושבים מחדש בכל שיחה. מכשיר יכול
לשנות את רשימת המצבים שלו אחרי עדכון של אינטגרציה, ואם המספרים
נגזרים ממנה בזמן אמת התפריט זז מתחת לרגלי המתקשר: אתמול 2 היה
קירור והיום הוא חימום. בטלפון אין מסך שיתפוס את זה, ולכן היציבות
כאן היא דרישת בטיחות ולא נוחות.

מה שכן נבדק בזמן שיחה הוא הזמינות: אפשרות שנעלמה מהמכשיר לא
תוצע. ואפשרות חדשה שהופיעה נוספת בסוף הרשימה — לעולם לא באמצע,
כדי שהמספרים הקיימים לא יזוזו.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any

from homeassistant.core import HomeAssistant

from homeassistant.helpers.service import async_get_all_descriptions

from . import capabilities as caps
from .action_fields import (
    async_action_fields,
    async_action_name,
    entity_number_range,
    field_is_supported,
)
from .const import MENU_DIGITS
from .policy import available_actions
from .translations_he import translate_option

_LOGGER = logging.getLogger(__name__)

# סוגי היכולות שהגילוי יודע לייצר.
# פעולה בלי פרמטרים — הדלקה, כיבוי, עצירה.
KIND_SIMPLE = "simple"
# הקראת המצב הנוכחי. אין לה פעולה.
KIND_STATUS = "status"
# פעולה עם שדה אחד שיש לו רשימת אפשרויות — תת-תפריט.
KIND_CHOICE = "choice"
# פעולה עם שדה מספרי בטווח ידוע — איסוף ספרות.
KIND_NUMBER = "number"
# פעולה שמקבלת טקסט חופשי — הכתבה בקול, רק בקו עם סטרימינג.
KIND_TEXT = "text"
# פעולה שיש בה שדה חובה שאי אפשר להקיש — שעה, צבע, מדיה. מוצעת
# רק כמקש עם ערך קבוע, שהמשתמש קובע בלוח. אינה נכנסת לתוכנית.
KIND_FIXED = "fixed"

# מזהה היכולת של הקראת המצב. אינו שם פעולה אמיתית, ולכן קבוע
# שמור שלא יתנגש עם שירות של Home Assistant.
STATUS_ID = "__status__"

# סדר מומלץ בתוך קבוצת הפעולות הפשוטות. הדלקה וכיבוי בראש כי הם
# הפעולות שמבקשים בפועל ברוב השיחות, והמתקשר לא צריך להאזין
# לרשימה שלמה כדי להגיע אליהן.
_ACTION_RANK: dict[str, int] = {
    "turn_on": 0,
    "turn_off": 1,
    "toggle": 2,
    "open_cover": 0,
    "close_cover": 1,
    "stop_cover": 2,
    "lock": 0,
    "unlock": 1,
    "open": 2,
    "start": 0,
    "stop": 1,
    "pause": 2,
    "return_to_base": 3,
    "media_play": 0,
    "media_pause": 1,
    "media_stop": 2,
}

# סדר הקבוצות: קודם הפעולות הפשוטות, אחריהן הקראת המצב, ואז
# הבחירות והערכים — שהם תמיד תת-תפריט או איסוף, כלומר ארוכים
# יותר להאזנה.
_KIND_RANK = {
    KIND_SIMPLE: 0, KIND_STATUS: 1, KIND_CHOICE: 2, KIND_NUMBER: 3,
    KIND_TEXT: 4, KIND_FIXED: 5,
}

# תחיליות שמוסרות משם הפעולה כדי למצוא את שדה הערך שלה:
# `set_hvac_mode` פועלת על השדה `hvac_mode`, `select_source` על
# `source`. זו המוסכמה בכל הדומיינים המובנים.
_FIELD_PREFIXES = ("set_", "select_")


@dataclass(frozen=True)
class Capability:
    """יכולת אחת שהתגלתה במכשיר.

    `ident` הוא המזהה היציב שנשמר בהגדרות — שם הפעולה, או
    `STATUS_ID` להקראת מצב. לפיו מתאימים בין מה שנשמר לבין מה
    שהתגלה מחדש.
    """

    ident: str
    kind: str
    label: str
    action: str = ""
    field_name: str = ""
    options: tuple[str, ...] = ()
    """אפשרויות הבחירה, בסדר שבו המכשיר מדווח עליהן."""

    minimum: float = 0.0
    maximum: float = 0.0
    width: int = 0
    """כמה ספרות בדיוק צריך להקיש. 0 = הטווח אינו ברוחב קבוע."""

    code: str = caps.CODE_NONE
    """האם הפעולה דורשת קוד, ואיך מקישים אותו. ראו `capabilities`."""
    code_width: int = 0
    code_min: int = 0
    code_max: int = 0

    max_length: int = 0
    """לטקסט מוכתב: האורך המרבי שהשדה מקבל. 0 = בלי מגבלה ידועה."""

    def option_label(self, value: str) -> str:
        return translate_option(value)


# ----------------------------------------------------------------------
# גילוי
# ----------------------------------------------------------------------


async def async_discover(
    hass: HomeAssistant, entity_id: str, descriptions: dict | None = None
) -> list[Capability]:
    """כל מה שהישות יודעת לעשות, בסדר המומלץ.

    נשען על אותו מידע שמסך האוטומציות מציג: הפעולות שהישות מקבלת
    לפי מסנני היעד של `services.yaml` (כולל `supported_features`),
    השדות שחלים עליה לפי מסנני השדות, והמאפיינים של הישות עצמה.
    אין כאן רשימה קבועה של מכשירים לתחזק.

    `descriptions` נשלף פעם אחת לאצווה ומועבר פנימה; בלעדיו נשלף כאן.
    """
    if "." not in entity_id:
        return []
    domain = entity_id.split(".", 1)[0]

    store = caps.cache(hass)
    if store is not None and (cached := store.get(entity_id)) is not None:
        return list(cached)

    found: list[Capability] = [
        Capability(ident=STATUS_ID, kind=KIND_STATUS, label="הקראת מצב")
    ]

    if descriptions is None:
        try:
            descriptions = await async_get_all_descriptions(hass)
        except Exception:  # noqa: BLE001 — בלי תיאורים נשארת הקראת המצב
            _LOGGER.debug("Could not load action descriptions", exc_info=True)
            descriptions = {}

    try:
        actions = await caps.async_actions_for(hass, entity_id, descriptions or {})
    except Exception:  # noqa: BLE001 — ישות אחת אינה מפילה תפריט שלם
        _LOGGER.debug("Could not list actions for %s", entity_id, exc_info=True)
        actions = []

    allowed = set(available_actions(hass, domain))
    info = caps.entity_info(hass, entity_id)
    for svc_domain, action in actions:
        if svc_domain == domain and action not in allowed:
            continue
        try:
            fields = await async_action_fields(hass, svc_domain, action, entity_id)
            capability = await _classify(
                hass, svc_domain, action, fields, entity_id, info
            )
        except Exception:  # noqa: BLE001 — פעולה אחת אינה מפילה את הגילוי
            _LOGGER.debug("Could not classify %s.%s", svc_domain, action, exc_info=True)
            continue
        if capability is None:
            continue
        if svc_domain != domain:
            full = f"{svc_domain}.{action}"
            capability = replace(capability, ident=full, action=full)
        found.append(capability)

    found.sort(key=_sort_key)
    if store is not None and descriptions:
        store.put(entity_id, tuple(found))
    return found


def _dialable(spec: dict[str, Any]) -> bool:
    """שדה שאפשר למלא בהקשה: בחירה עם אפשרויות, כן/לא, מספר."""
    kind = caps.selector_kind(spec)
    if kind == "select":
        return field_is_supported(spec)
    return kind in ("boolean", "number")


def _fixed_only(action: str, label: str) -> Capability:
    return Capability(ident=action, kind=KIND_FIXED, label=label, action=action)


async def _classify(
    hass: HomeAssistant,
    domain: str,
    action: str,
    fields: dict[str, dict[str, Any]],
    entity_id: str,
    info: caps.EntityInfo | None = None,
) -> Capability | None:
    """סיווג פעולה אחת ליכולת.

    שדה הקוד מטופל בנפרד: אינו "שדה הערך" של הפעולה, ונאסף בהקשה
    רגע לפני ההפעלה. שדה חובה שאי אפשר להקיש הופך את הפעולה לערך
    קבוע בלבד, ושדה טקסט — להכתבה. ניחוש כאן היה מייצר פריט שנשמע
    תקין ונכשל בהפעלה.
    """
    label = await async_action_name(hass, domain, action)
    rule = (
        caps.code_rule(hass, info, action, fields)
        if info is not None
        else caps.CodeRule(caps.CODE_NONE)
    )
    fields = {n: s for n, s in fields.items() if n != caps.CODE_FIELD}
    if rule.kind == caps.CODE_UNDIALABLE:
        # קוד של אותיות אינו ניתן להקשה. נשאר ערך קבוע בלוח.
        return _fixed_only(action, label)
    code_kwargs: dict[str, Any] = {}
    if rule.kind != caps.CODE_NONE:
        code_kwargs = {
            "code": rule.kind,
            "code_width": rule.width,
            "code_min": rule.min_len,
            "code_max": rule.max_len,
        }

    dialable = {n: s for n, s in fields.items() if _dialable(s)}
    required = [n for n, s in fields.items() if s.get("required")]

    # טקסט חופשי: הכתבה. שאר שדות החובה חייבים להיות ריקים.
    if text_field := caps.dictation_field(domain, action, fields):
        others = [n for n in required if n != text_field]
        if others or code_kwargs:
            return _fixed_only(action, label)
        selector = (fields[text_field].get("selector") or {}).get("text")
        max_length = 0
        if isinstance(selector, dict):
            try:
                max_length = int(selector.get("max") or 0)
            except (TypeError, ValueError):
                max_length = 0
        return Capability(
            ident=action, kind=KIND_TEXT, label=label, action=action,
            field_name=text_field, max_length=max_length,
        )

    # שדה חובה שאי אפשר להקיש, או יותר משדה חובה אחד: ערך קבוע.
    if any(n not in dialable for n in required) or len(required) > 1:
        return _fixed_only(action, label)

    primary = _primary_field(action, dialable, required)

    if primary is None:
        return Capability(
            ident=action, kind=KIND_SIMPLE, label=label, action=action, **code_kwargs
        )

    if code_kwargs:
        # קוד יחד עם ערך — שני איסופים ברצף. נדיר; ערך קבוע מספיק.
        return _fixed_only(action, label)

    selector = dialable[primary].get("selector") or {}

    if "select" in selector:
        options = tuple(
            str(o.get("value", "")) if isinstance(o, dict) else str(o)
            for o in (selector["select"] or {}).get("options", [])
        )
        options = tuple(o for o in options if o)
        if not options:
            return _fixed_only(action, label)
        return Capability(
            ident=action,
            kind=KIND_CHOICE,
            label=label,
            action=action,
            field_name=primary,
            options=options,
        )

    if "boolean" in selector:
        # שני מצבים הם בחירה לכל דבר, והמתקשר שומע "להפעלה הקש 1,
        # לביטול הקש 2" במקום לתהות מה הקשה בודדת עושה.
        return Capability(
            ident=action,
            kind=KIND_CHOICE,
            label=label,
            action=action,
            field_name=primary,
            options=("true", "false"),
        )

    if "number" in selector:
        low, high = entity_number_range(hass, entity_id, primary, selector["number"])
        if low is None or high is None or high <= low:
            return _fixed_only(action, label)
        width = _fixed_width(low, high)
        if not width:
            # טווח שאינו ברוחב קבוע — 5 היא ספרה אחת ו-100 הן שלוש,
            # ולכן אין נקודה שבה ידוע שהמתקשר סיים להקיש. במקום
            # מקש אישור, שאינו מאומת אצל כל הספקים, מוצעת רשימה
            # של ערכים עגולים. ראו `stepped_options`.
            step = _entity_step(hass, entity_id, selector["number"])
            steps = stepped_options(low, high, step=step)
            if not steps:
                return _fixed_only(action, label)
            return Capability(
                ident=action,
                kind=KIND_CHOICE,
                label=label,
                action=action,
                field_name=primary,
                options=steps,
                minimum=low,
                maximum=high,
            )
        return Capability(
            ident=action,
            kind=KIND_NUMBER,
            label=label,
            action=action,
            field_name=primary,
            minimum=low,
            maximum=high,
            width=width,
        )

    return _fixed_only(action, label)


def _entity_step(hass: HomeAssistant, entity_id: str, config: dict | None) -> float:
    """הצעד בין ערכים: מהישות אם היא מדווחת, אחרת מהתיאור."""
    state = hass.states.get(entity_id)
    attributes = state.attributes if state is not None else {}
    for name in ("target_temp_step", "step", "percentage_step"):
        try:
            value = float(attributes.get(name) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    try:
        value = float((config or {}).get("step") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value > 0 else 0


def _primary_field(
    action: str, supported: dict[str, dict[str, Any]], required: list[str]
) -> str | None:
    """שדה הערך של הפעולה, או None אם אינו חד-משמעי.

    `supported` כאן הוא רק מה שאפשר להקיש. שדה טקסט אופציונלי, כמו
    `code` במנעול או `message` בהתראה, לעולם אינו "השדה" — בלי זה
    מנעול היה נשאר בלי נעילה ופתיחה. שדה חובה יחיד הוא תמיד השדה.
    אחרת מנסים את המוסכמה של שם הפעולה (`set_fan_mode` על
    `fan_mode`), ולבסוף שדה אופציונלי יחיד. `light.turn_on` נופל
    לכאן עם עשרות שדות אופציונליים ואף אחד מהם אינו "השדה" — ולכן
    הוא נשאר הדלקה פשוטה, וזה בדיוק הרצוי.
    """
    if len(required) == 1:
        return required[0] if required[0] in supported else None

    stem = action
    for prefix in _FIELD_PREFIXES:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    if stem in supported:
        return stem

    if len(supported) == 1:
        return next(iter(supported))
    return None


# יותר משתי ספרות אינו מוצע כהקשה. עוצמה שבין 0 ל-100 הייתה
# דורשת שלוש, כלומר "020" עבור עשרים — מספיק מסורבל בטלפון כדי
# להעדיף רשימה של ערכים עגולים.
MAX_COLLECT_WIDTH = 2


def _fixed_width(low: float, high: float) -> int:
    """כמה ספרות יוקשו, לפי הגבול העליון. 0 = לא מתאים להקשה.

    כל הערכים נאמרים באותו אורך, ומי שרוצה מספר קטן מקיש אפס
    לפניו: בטווח 8 עד 30 מקישים 08. כך ידוע מתי המתקשר סיים בלי
    מקש אישור, גם כשהגבולות אינם באותו אורך — וזה המצב אצל רוב
    המזגנים, שמתחילים בספרה אחת ומסתיימים בשתיים.

    שלילי אינו ניתן להקשה בטלפון, ושבר אינו ניתן להקשה בספרות.
    """
    if low < 0:
        return 0
    lo, hi = int(low), int(high)
    if lo != low or hi != high or hi <= lo:
        return 0
    width = len(str(hi))
    return width if width <= MAX_COLLECT_WIDTH else 0


def stepped_options(
    low: float, high: float, count: int = 9, *, step: float = 0
) -> tuple[str, ...]:
    """ערכים עגולים בתוך טווח, לרשימה שמוקראת בטלפון.

    עוצמה שבין 0 ל-100 היא 101 ערכים, ואין דרך להציע אותם. תשעה
    ערכים בקפיצות עגולות הם מה שאפשר להקריא בשיחה, והמשתמש יכול
    להחריג מהם.
    """
    lo, hi = int(low), int(high)
    if hi <= lo:
        return ()
    span = hi - lo
    raw = span / (count - 1) if count > 1 else span
    # הצעד של הישות קובע את הכפולות: מזגן בקפיצות של 2 אינו
    # מקבל 21. צעד שבור (0.5) אינו משנה — הערכים כאן שלמים.
    base = int(step) if step and step >= 1 and float(step).is_integer() else 1
    # קפיצה עגולה: 5, 10, 25 וכדומה, ולא 12.5.
    for nice in (1, 2, 5, 10, 20, 25, 50, 100):
        if nice * base >= raw:
            jump = nice * base
            break
    else:
        jump = int(raw)
    values = list(range(lo, hi + 1, max(1, jump)))
    if values and values[-1] != hi:
        values.append(hi)
    return tuple(str(v) for v in values[:count])


def _sort_key(capability: Capability) -> tuple:
    return (
        _KIND_RANK.get(capability.kind, 9),
        _ACTION_RANK.get(capability.action, 50),
        capability.action,
    )


# ----------------------------------------------------------------------
# מהגילוי לתוכנית
# ----------------------------------------------------------------------


def build_plan(
    capabilities: list[Capability],
    chosen: list[str],
    option_choices: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """התוכנית שתישמר בהגדרות: יכולת, מספר, ואפשרויות.

    המספרים נקבעים כאן פעם אחת ונשמרים. מכאן ואילך הם אינם
    מחושבים מחדש, גם אם המכשיר ישנה את עצמו.
    """
    option_choices = option_choices or {}
    by_ident = {c.ident: c for c in capabilities}
    plan: list[dict[str, Any]] = []

    for ident in chosen:
        capability = by_ident.get(ident)
        # ערך קבוע בלבד אינו נכנס לתפריט של מכשיר: אין דרך להקיש לו
        # ערך. הוא נוסף מהלוח כמקש עם ערך קבוע.
        if capability is None or capability.kind == KIND_FIXED:
            continue
        if len(plan) >= len(MENU_DIGITS):
            _LOGGER.warning(
                "Only %s options fit in a menu level. The rest were dropped",
                len(MENU_DIGITS),
            )
            break

        entry: dict[str, Any] = {
            "digit": MENU_DIGITS[len(plan)],
            "ident": ident,
            "kind": capability.kind,
            "action": capability.action,
            "label": capability.label,
        }
        if capability.kind == KIND_CHOICE:
            picked = option_choices.get(ident)
            values = (
                [v for v in capability.options if v in set(picked)]
                if picked is not None
                else list(capability.options)
            )
            entry["field"] = capability.field_name
            entry["options"] = values[: len(MENU_DIGITS)]
            # מה שהוסר במפורש. אפשרות שאינה כאן ואינה ברשימה היא
            # חדשה, ותתווסף בסוף — ראו `merge_options`.
            entry["excluded"] = [v for v in capability.options if v not in values]
        elif capability.kind == KIND_NUMBER:
            entry["field"] = capability.field_name
            entry["min"] = capability.minimum
            entry["max"] = capability.maximum
            entry["width"] = capability.width
        elif capability.kind == KIND_TEXT:
            entry["field"] = capability.field_name
            if capability.max_length:
                entry["max_length"] = capability.max_length
        if capability.code != caps.CODE_NONE:
            # רק איך מקישים — הקוד עצמו לעולם אינו נשמר.
            entry["code"] = {
                "kind": capability.code,
                "width": capability.code_width,
                "min": capability.code_min,
                "max": capability.code_max,
            }
        plan.append(entry)

    return plan


def merge_options(stored: list[str], excluded: list[str], live: list[str]) -> list[str]:
    """האפשרויות להקראה: מה שנשמר, בלי מה שנעלם, ועם החדשות בסוף.

    הסדר של מה שנשמר נשמר במדויק — שם יושבים המספרים שהמתקשר
    כבר מכיר. אפשרות שהמכשיר כבר אינו מדווח עליה יורדת; אפשרות
    חדשה שלא הוחרגה נוספת בסוף, שם היא אינה מזיזה דבר.
    """
    live_set = set(live)
    kept = [v for v in stored if v in live_set]
    known = set(stored) | set(excluded)
    kept.extend(v for v in live if v not in known)
    return kept[: len(MENU_DIGITS)]


# ----------------------------------------------------------------------
# קבוצה: כל הישויות מסוג מסוים במרחב
# ----------------------------------------------------------------------


async def async_domain_is_usable(hass: HomeAssistant, domain: str) -> bool:
    """האם אפשר לבנות מהדומיין הזה תפריט שאפשר להקיש בו.

    נבדק בגילוי אמיתי על ישות מייצגת, ולא מול רשימה שחורה
    שצריך לתחזק: דומיין חדש ב-Home Assistant ייכנס או ייצא מעצמו.

    הישות נדרשת כי חלק מהיכולות תלויות בה — `hvac_mode` מגיע
    כבורר מצב ונעשה רשימה רק אחרי שקוראים את המאפיינים של המזגן,
    ובלי ישות היה נראה שלמיזוג אין מה להציע.

    הקראת מצב לבדה אינה נחשבת. קבוצה קיימת כדי לעשות משהו לכולם
    בבת אחת, ודומיין שאפשר רק להאזין לו — תמונה, אירוע, גרסה —
    היה ממלא את הבורר בלי להוסיף דבר. ישות בודדת עדיין זמינה לו,
    שם בוחרים אותה ישירות ובלי הבורר הזה.
    """
    states = hass.states.async_all([domain])
    if not states:
        return False
    found = await async_discover(hass, states[0].entity_id)
    return any(c.kind not in (KIND_STATUS, KIND_FIXED, KIND_TEXT) for c in found)


# מפתחות בחירת היעד, כפי ש-`TargetSelector` שומר אותם.
TARGET_KEYS = ("area_id", "floor_id", "label_id", "device_id", "entity_id")
TARGET_EXCLUDE = "exclude"
# יעד שנבנה משדות נפרדים (מרחב, קומה, תווית): כל שדה מצמצם, ולא מרחיב.
_MATCH_ALL = "_match_all"


def _ids(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if v]


def clean_target(value) -> dict:
    """בחירת יעד מהטופס, בלי מפתחות ריקים. החרגה ריקה אינה נשמרת."""
    if not isinstance(value, dict):
        return {}
    target = {key: ids for key in TARGET_KEYS if (ids := _ids(value.get(key)))}
    exclude = value.get(TARGET_EXCLUDE)
    if isinstance(exclude, dict):
        excluded = {key: ids for key in TARGET_KEYS if (ids := _ids(exclude.get(key)))}
        if excluded:
            target[TARGET_EXCLUDE] = excluded
    return target


def stored_target(data) -> dict:
    """היעד של קבוצה או של תפריט אזור, מהנתונים השמורים.

    רשומה בלי `CONF_TARGET` נושאת מרחב, קומה ותווית בשדות נפרדים,
    וכשיש יותר מאחד ההתאמה היא לכולם יחד. ההמרה שומרת על המשמעות.
    """
    from .const import CONF_AREA, CONF_FLOOR, CONF_LABEL_TARGET, CONF_TARGET  # noqa: PLC0415

    if isinstance(data.get(CONF_TARGET), dict):
        return clean_target(data[CONF_TARGET])
    target: dict = {}
    for key, conf in (
        ("area_id", CONF_AREA), ("floor_id", CONF_FLOOR), ("label_id", CONF_LABEL_TARGET),
    ):
        value = str(data.get(conf, "") or "")
        if value:
            target[key] = [value]
    if len(target) > 1:
        target[_MATCH_ALL] = True
    return target


def form_target(target: dict) -> dict:
    """היעד כפי שהבורר מציג אותו — בלי סימונים פנימיים."""
    return {k: v for k, v in target.items() if k != _MATCH_ALL}


def has_target(target: dict) -> bool:
    """האם נבחר משהו לכלול. החרגה לבדה אינה נחשבת."""
    return any(target.get(key) for key in TARGET_KEYS)


def _primary(hass: HomeAssistant, entity_ids) -> set[str]:
    """בלי ישויות מוסתרות ובלי ישויות הגדרה ואבחון — כמו במרחב."""
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    registry = er.async_get(hass)
    kept = set()
    for entity_id in entity_ids:
        entry = registry.async_get(entity_id)
        if entry is not None and (entry.hidden_by or entry.entity_category):
            continue
        kept.add(entity_id)
    return kept


def _resolve(hass: HomeAssistant, target: dict) -> set[str]:
    """כל הישויות שהיעד מכסה, מכל הסוגים, אחרי ההחרגות."""
    from homeassistant.helpers import target as target_helper  # noqa: PLC0415

    if target.get(_MATCH_ALL):
        parts = [
            _resolve(hass, {key: target[key]}) for key in TARGET_KEYS if target.get(key)
        ]
        return set.intersection(*parts) if parts else set()

    selection = target_helper.TargetSelection(target)
    if has_target(target):
        selected = target_helper.async_extract_referenced_entity_ids(hass, selection)
        return selected.referenced | selected.indirectly_referenced
    # בלי יעד — כל הבית, פחות ההחרגות
    everything = _primary(hass, (s.entity_id for s in hass.states.async_all()))
    return everything - target_helper.async_extract_excluded_entity_ids(hass, selection)


def match_entities(hass: HomeAssistant, domain: str, target: dict) -> list[str]:
    """הישויות מהסוג הזה שהיעד מכסה, כרגע.

    נפתר במנוע היעדים של Home Assistant — אותו אחד שמשמש שירות
    שמופעל על מרחב באוטומציה, כולל ההחרגות. מכשיר שנוסף למרחב
    מצטרף מעצמו, ומה שהוחרג נשאר בחוץ גם כשיתווספו אחרים.
    """
    if not domain:
        return []
    try:
        found = _resolve(hass, target)
    except Exception:  # noqa: BLE001 — יעד שאינו נפתר אינו מפיל תפריט
        _LOGGER.debug("Could not resolve %s in %s", domain, target, exc_info=True)
        return []
    prefix = f"{domain}."
    return sorted(
        e for e in found if e.startswith(prefix) and hass.states.get(e) is not None
    )


async def async_domains_in(
    hass: HomeAssistant, target: dict, usable: dict[str, bool] | None = None
) -> list[tuple[str, int]]:
    """סוגי הישויות שנמצאים ביעד, וכמה מכל סוג.

    זו הדרך ההפוכה לבחירת סוג מראש: קודם המקום, ומתוכו מה שיש בו.
    מוחזרים רק סוגים שאפשר לבנות מהם תפריט קבוצתי — הסינון הוא
    אותו סינון של בורר הסוג, ולכן אין כאן רשימה נפרדת לתחזק.
    """
    from .policy import domain_is_blocked, domain_is_groupable  # noqa: PLC0415

    try:
        resolved = _resolve(hass, target)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not resolve %s", target, exc_info=True)
        return []

    counts: dict[str, int] = {}
    for entity_id in resolved:
        if hass.states.get(entity_id) is None:
            continue
        domain = entity_id.split(".", 1)[0]
        counts[domain] = counts.get(domain, 0) + 1

    # גילוי אחד לכל סוג, גם כששואלים על כמה מקומות ברצף.
    usable = {} if usable is None else usable
    found: dict[str, int] = {}
    for domain, count in counts.items():
        if domain_is_blocked(domain) or not domain_is_groupable(domain):
            continue
        if not available_actions(hass, domain):
            continue
        if domain not in usable:
            usable[domain] = await async_domain_is_usable(hass, domain)
        if not usable[domain]:
            continue
        found[domain] = count
    return sorted(found.items())


async def async_discover_group(
    hass: HomeAssistant, domain: str, target: dict
) -> list[Capability]:
    """היכולות המשותפות לכל חברי הקבוצה.

    חיתוך ולא איחוד: אפשרות שרק חלק מהמכשירים תומכים בה הייתה
    נשמעת בתפריט ונכשלת בשקט אצל השאר. מזגן אחד עם מצב סיבוב
    ואחד בלי — המתקשר אינו יודע מי מהם ענה לו.
    """
    entity_ids = match_entities(hass, domain, target)
    if not entity_ids:
        return []

    try:
        descriptions = await async_get_all_descriptions(hass)
    except Exception:  # noqa: BLE001
        descriptions = {}
    per_entity: list[dict[str, Capability]] = []
    for entity_id in entity_ids:
        found = await async_discover(hass, entity_id, descriptions)
        per_entity.append({c.ident: c for c in found})

    shared = set(per_entity[0])
    for found in per_entity[1:]:
        shared &= set(found)

    merged = [
        _merge(ident, [found[ident] for found in per_entity])
        for ident in shared
    ]
    merged = [c for c in merged if c is not None]
    merged.sort(key=_sort_key)
    return merged


def _merge(ident: str, versions: list[Capability]) -> Capability | None:
    """יכולת אחת מכל הגרסאות שלה אצל חברי הקבוצה.

    בחירה: רק אפשרויות שכולם מכירים, בסדר של הראשון. מספר: הטווח
    הצר ביותר, כדי שכל ערך שיוקש יהיה חוקי אצל כולם — מזגן שמגיע
    ל-30 ואחד שמגיע ל-28 נותנים יחד 28.
    """
    first = versions[0]
    if any(v.kind != first.kind for v in versions):
        return None
    # קוד שונה בין החברים — אין הקשה אחת שמתאימה לכולם. וקבוצה
    # אינה מקבלת הכתבה או ערך קבוע: אלה של מכשיר בודד.
    if first.kind in (KIND_TEXT, KIND_FIXED):
        return None
    if any(
        (v.code, v.code_width) != (first.code, first.code_width) for v in versions
    ):
        return None

    if first.kind == KIND_CHOICE:
        common = set(first.options)
        for other in versions[1:]:
            common &= set(other.options)
        options = tuple(o for o in first.options if o in common)
        if not options:
            return None
        return replace(first, options=options)

    if first.kind == KIND_NUMBER:
        low = max(v.minimum for v in versions)
        high = min(v.maximum for v in versions)
        width = _fixed_width(low, high)
        if not width:
            return None
        return replace(first, minimum=low, maximum=high, width=width)

    return first
