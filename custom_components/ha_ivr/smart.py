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

from .action_fields import (
    async_action_fields,
    async_action_name,
    entity_number_range,
    field_is_supported,
)
from .const import MENU_DIGITS
from .policy import available_actions
from .translations_he import translate_action, translate_option

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
_KIND_RANK = {KIND_SIMPLE: 0, KIND_STATUS: 1, KIND_CHOICE: 2, KIND_NUMBER: 3}

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

    def option_label(self, value: str) -> str:
        return translate_option(value)


@dataclass
class PlanEntry:
    """יכולת שנבחרה, עם המספר שננעל לה."""

    digit: str
    capability: Capability
    options: tuple[str, ...] = ()
    """אפשרויות שנבחרו, בסדר שנקבע. ריק ביכולת שאינה בחירה."""


# ----------------------------------------------------------------------
# גילוי
# ----------------------------------------------------------------------


async def async_discover(
    hass: HomeAssistant, entity_id: str
) -> list[Capability]:
    """כל מה שהישות יודעת לעשות, בסדר המומלץ.

    נשען על אותו מידע שמסך האוטומציות מציג: השירותים שהדומיין
    חושף, השדות של כל שירות, והמאפיינים של הישות עצמה. אין כאן
    רשימה קבועה של מכשירים לתחזק.
    """
    if "." not in entity_id:
        return []
    domain = entity_id.split(".", 1)[0]

    found: list[Capability] = [
        Capability(ident=STATUS_ID, kind=KIND_STATUS, label="הקראת מצב")
    ]

    for action in available_actions(hass, domain):
        fields = await async_action_fields(hass, domain, action, entity_id)
        capability = await _classify(hass, domain, action, fields, entity_id)
        if capability is not None:
            found.append(capability)

    found.sort(key=_sort_key)
    return found


async def _classify(
    hass: HomeAssistant,
    domain: str,
    action: str,
    fields: dict[str, dict[str, Any]],
    entity_id: str,
) -> Capability | None:
    """סיווג פעולה אחת ליכולת, או None אם אינה מתאימה לגילוי.

    פעולה שיש לה יותר משדה חובה אחד, או ששדה הערך שלה אינו חד-
    משמעי, נשארת מחוץ לגילוי בכוונה — אפשר להוסיף אותה כפריט רגיל
    עם הערכים שהמשתמש בוחר. ניחוש כאן היה מייצר פריט שנשמע תקין
    ונכשל בהפעלה.
    """
    supported = {n: s for n, s in fields.items() if field_is_supported(s)}
    required = [n for n, s in fields.items() if s.get("required")]

    # שדה חובה שאיננו יודעים להציג — הפעולה תיכשל, ולכן אינה מוצעת.
    if any(n not in supported for n in required):
        return None
    if len(required) > 1:
        return None

    label = await async_action_name(hass, domain, action)
    primary = _primary_field(action, supported, required)

    if primary is None:
        # אין שדה ערך מובהק. אם יש שדות חובה, אי אפשר להפעיל בלעדיהם.
        if required:
            return None
        return Capability(
            ident=action, kind=KIND_SIMPLE, label=label, action=action
        )

    selector = supported[primary].get("selector") or {}

    if "select" in selector:
        options = tuple(
            str(o.get("value", "")) if isinstance(o, dict) else str(o)
            for o in (selector["select"] or {}).get("options", [])
        )
        options = tuple(o for o in options if o)
        if not options:
            return None
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
            return None
        width = _fixed_width(low, high)
        if not width:
            # טווח שאינו ברוחב קבוע — 5 היא ספרה אחת ו-100 הן שלוש,
            # ולכן אין נקודה שבה ידוע שהמתקשר סיים להקיש. במקום
            # מקש אישור, שאינו מאומת אצל כל הספקים, מוצעת רשימה
            # של ערכים עגולים. ראו `stepped_options`.
            steps = stepped_options(low, high)
            if not steps:
                return None
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

    return None


def _primary_field(
    action: str, supported: dict[str, dict[str, Any]], required: list[str]
) -> str | None:
    """שדה הערך של הפעולה, או None אם אינו חד-משמעי.

    שדה חובה יחיד הוא תמיד השדה. אחרת מנסים את המוסכמה של שם
    הפעולה (`set_fan_mode` על `fan_mode`), ולבסוף שדה אופציונלי
    יחיד. `light.turn_on` נופל לכאן עם עשרות שדות אופציונליים
    ואף אחד מהם אינו "השדה" — ולכן הוא נשאר הדלקה פשוטה, וזה
    בדיוק הרצוי.
    """
    if len(required) == 1:
        return required[0]

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


def stepped_options(low: float, high: float, count: int = 9) -> tuple[str, ...]:
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
    # קפיצה עגולה: 5, 10, 25 וכדומה, ולא 12.5.
    for nice in (1, 2, 5, 10, 20, 25, 50, 100):
        if nice >= raw:
            step = nice
            break
    else:
        step = int(raw)
    values = list(range(lo, hi + 1, max(1, step)))
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
        if capability is None:
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
    return any(c.kind != KIND_STATUS for c in found)


def entity_labels(hass: HomeAssistant, entity_id: str) -> set[str]:
    """כל התוויות שחלות על הישות — שלה, של המכשיר, ושל המרחב.

    תווית מוצמדת בפועל למכשיר ולא לישות ברוב המקרים, ולכן בדיקה
    של הישות בלבד הייתה מחזירה ריק כמעט תמיד. זו גם ההתנהגות של
    Home Assistant עצמו כשמפעילים שירות על תווית.
    """
    try:
        from homeassistant.helpers import area_registry as ar  # noqa: PLC0415
        from homeassistant.helpers import device_registry as dr  # noqa: PLC0415
        from homeassistant.helpers import entity_registry as er  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return set()

    entry = er.async_get(hass).async_get(entity_id)
    if entry is None:
        return set()

    labels = set(entry.labels or ())
    device = None
    if entry.device_id:
        device = dr.async_get(hass).async_get(entry.device_id)
        if device is not None:
            labels |= set(device.labels or ())

    area_id = entry.area_id or (device.area_id if device is not None else None)
    if area_id:
        area = ar.async_get(hass).async_get_area(area_id)
        if area is not None:
            labels |= set(area.labels or ())
    return labels


def resolve_label(hass: HomeAssistant, label: str) -> str:
    """מזהה התווית, גם כשהתקבל שמה."""
    try:
        from homeassistant.helpers import label_registry as lr  # noqa: PLC0415

        registry = lr.async_get(hass)
    except Exception:  # noqa: BLE001
        return label
    if registry.async_get_label(label) is not None:
        return label
    found = registry.async_get_label_by_name(label)
    return found.label_id if found is not None else label


def match_entities(
    hass: HomeAssistant,
    domain: str,
    area: str = "",
    floor: str = "",
    states: list[str] | None = None,
    label: str = "",
) -> list[str]:
    """הישויות שהיעד מכסה, כרגע.

    נשען על מנוע ההתאמה של Home Assistant עצמו — אותו אחד שהעוזר
    מריץ ב"הדלק את האורות במטבח". הוא מטפל גם במה שקל לפספס:
    ישות ששייכת למרחב דרך המכשיר שלה ולא ישירות, כינויים למרחב,
    וקומה שמכילה כמה מרחבים.

    `assistant=None` במכוון: כך היעד אינו כפוף להגדרות החשיפה של
    Assist. מי שבנה תפריט טלפוני כבר החליט מה בתוכו.
    """
    if not domain:
        return []
    try:
        from homeassistant.helpers import intent as intent_helper  # noqa: PLC0415

        result = intent_helper.async_match_targets(
            hass,
            intent_helper.MatchTargetsConstraints(
                domains=[domain],
                area_name=area or None,
                floor_name=floor or None,
                states=states or None,
                assistant=None,
            ),
        )
    except Exception:  # noqa: BLE001 — יעד שאינו נפתר אינו מפיל תפריט
        _LOGGER.debug("Could not match %s in %s/%s", domain, area, floor, exc_info=True)
        return []
    if not result.is_match:
        # הסיבה ולא רק "ריק": יעד שאינו מתאים נשמע בטלפון כ"אין
        # מכשירים", וזה נראה זהה בין מרחב שהתרוקן, מרחב שנמחק,
        # ודומיין שאין בו כלום. היומן צריך להבחין ביניהם.
        _LOGGER.debug(
            "No match for %s in area=%r floor=%r: %s",
            domain, area, floor, getattr(result, "no_match_reason", None),
        )
        return []
    found = sorted(state.entity_id for state in result.states)
    if not label:
        return found

    # התוויות אינן חלק מ-`MatchTargetsConstraints`, ולכן מסננים
    # אותן כאן, אחרי שהמנוע של Home Assistant עשה את שלו.
    wanted = resolve_label(hass, label)
    kept = [e for e in found if wanted in entity_labels(hass, e)]
    if not kept:
        _LOGGER.debug("No %s carries label %r in area=%r", domain, label, area)
    return kept


async def async_discover_group(
    hass: HomeAssistant, domain: str, area: str = "", floor: str = "",
    label: str = "",
) -> list[Capability]:
    """היכולות המשותפות לכל חברי הקבוצה.

    חיתוך ולא איחוד: אפשרות שרק חלק מהמכשירים תומכים בה הייתה
    נשמעת בתפריט ונכשלת בשקט אצל השאר. מזגן אחד עם מצב סיבוב
    ואחד בלי — המתקשר אינו יודע מי מהם ענה לו.
    """
    entity_ids = match_entities(hass, domain, area, floor, label=label)
    if not entity_ids:
        return []

    per_entity: list[dict[str, Capability]] = []
    for entity_id in entity_ids:
        found = await async_discover(hass, entity_id)
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
