"""בניית עץ התפריטים מתת-הרשומות של האינטגרציה.

העץ אינו נשמר בשום מקום — לא אצל הספק ולא בקובץ. הוא נבנה מחדש
בכל שיחה מתוך תת-הרשומות, ולכן הוא תמיד משקף את ההגדרות העדכניות.

נתיב הוא רצף ספרות מופרד בלוכסן: "2" הוא הספרה 2 בתפריט הראשי,
"1/3" היא הספרה 3 בתוך תת-התפריט שנפתח בהקשה על 1.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import smart as smart_mod
from . import tree as tree_mod
from .action_fields import ENTITY_OPTION_ATTRIBUTES
from .model import say_number
from .translations_he import field_unit, translate_action, translate_field, translate_option
from .const import (
    DOMAIN_NAMES,
    CONF_ACTION,
    CONF_ACTION_DATA,
    CONF_CONFIRM_RISKY,
    CONF_INTRO,
    CONF_LABEL,
    CONF_MENU_PATH,
    CONF_TARGET_ENTITY,
    MENU_DIGITS,
    MENU_MAX_DEPTH,
    CONF_AREA,
    CONF_DOMAIN,
    CONF_FLOOR,
    CONF_LABEL_TARGET,
    CONF_GOTO_TARGET,
    CONF_PLAN,
    SUBENTRY_TYPE_GROUP,
    SUBENTRY_TYPE_ITEM,
    SUBENTRY_TYPE_SMART,
    SUBENTRY_TYPE_SUBMENU,
    SUBENTRY_TYPE_GOTO,
    SUBENTRY_TYPE_ALERTS,
)

_LOGGER = logging.getLogger(__name__)


def normalize_path(raw: object) -> str:
    """ניקוי נתיב לצורה תקנית, או מחרוזת ריקה אם אינו תקין."""
    parts = [p.strip() for p in str(raw or "").strip().strip("/").split("/")]
    parts = [p for p in parts if p]
    if not parts or len(parts) > MENU_MAX_DEPTH:
        return ""
    if not all(p in MENU_DIGITS for p in parts):
        return ""
    return "/".join(parts)

def _dig(root: dict, parts: list[str]) -> dict:
    """הצומת בנתיב, ויצירת צמתי ביניים חסרים בדרך."""
    node = root
    for part in parts:
        node = node.setdefault("items", {}).setdefault(part, {})
    return node


def _prune(node: dict) -> bool:
    """הסרת ענפים ריקים. מחזיר True אם נשאר משהו להקריא.

    ענף בלי פריטים מתחתיו לא יוקרא כלל — הקשה עליו הייתה מחזירה
    את המתקשר בלי שקרה דבר. הוא ממשיך להופיע בטופס ההגדרה,
    ויוקרא ברגע שיתווסף אליו פריט.
    """
    items = node.get("items") or {}
    for digit in list(items):
        if not _prune(items[digit]):
            del items[digit]
    if not items:
        node.pop("items", None)
    return (
        bool(node.get("entity"))
        or bool(node.get("goto"))
        or bool(node.get("alerts"))
        or bool(node.get("collect"))
        or bool(node.get("target"))
        or bool(node.get("items"))
    )


def build_config(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """מבנה מקונן מתוך תת-הרשומות של רשומה אחת.

    הרשומה ולא הדומיין: לכל רשומה עץ משלה, ותפריט שנבנה באחת
    אינו נראה באחרת. בנייה לפי דומיין הייתה מערבבת את התפריטים
    של כל הרשומות בלי שום שגיאה.
    """
    root: dict = {}
    taken: set[str] = set()

    root.setdefault("intro", str(entry.options.get(CONF_INTRO, "") or ""))

    # תתי-תפריטים תחילה, כדי שהשם וההקדמה יהיו במקום כשהפריטים
    # נתלים תחתיהם.
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_SUBMENU:
            continue
        path = normalize_path(subentry.data.get(CONF_MENU_PATH))
        if not path:
            continue
        node = _dig(root, path.split("/"))
        node["say"] = str(subentry.data.get(CONF_LABEL, "") or f"תפריט {path}")
        if intro := str(subentry.data.get(CONF_INTRO, "") or ""):
            node["intro"] = intro

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_ITEM:
            continue
        data = subentry.data
        path = normalize_path(data.get(CONF_MENU_PATH))
        if not path:
            continue
        if path in taken:
            _LOGGER.warning(
                "Path %s is assigned to more than one item. Only the first is used",
                path,
            )
            continue
        taken.add(path)

        stored = data.get(CONF_ACTION_DATA)
        node = _dig(root, path.split("/"))
        label = str(data.get(CONF_LABEL, "") or "").strip()
        node["_label"] = bool(label)
        node["say"] = label
        node["entity"] = str(data.get(CONF_TARGET_ENTITY, ""))
        node["action"] = str(data.get(CONF_ACTION, "") or "")
        node["data"] = dict(stored) if isinstance(stored, dict) else {}
        node["confirmed"] = bool(data.get(CONF_CONFIRM_RISKY, False))

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_SMART:
            continue
        data = subentry.data
        path = normalize_path(data.get(CONF_MENU_PATH))
        if not path:
            continue
        if path in taken:
            # שקט כאן פירושו ישות שנשמרה ואינה נשמעת בשיחה, בלי
            # שום סימן לכך. קורה כשעריכה נשמרה כרשומה חדשה במקום
            # לדרוס את הקיימת.
            _LOGGER.warning(
                "Path %s is assigned to more than one item. Only the first is used",
                path,
            )
            continue
        taken.add(path)
        _expand_smart(hass, _dig(root, path.split("/")), data)

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_GROUP:
            continue
        data = subentry.data
        path = normalize_path(data.get(CONF_MENU_PATH))
        if not path:
            continue
        if path in taken:
            _LOGGER.warning(
                "Path %s is assigned to more than one item. Only the first is used",
                path,
            )
            continue
        taken.add(path)
        _expand_group(hass, _dig(root, path.split("/")), data)

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_GOTO:
            continue
        data = subentry.data
        path = normalize_path(data.get(CONF_MENU_PATH))
        if not path or path in taken:
            continue
        taken.add(path)
        node = _dig(root, path.split("/"))
        node["say"] = str(data.get(CONF_LABEL, "") or "מעבר")
        node["goto"] = str(data.get(CONF_GOTO_TARGET, ""))

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_ALERTS:
            continue
        data = subentry.data
        path = normalize_path(data.get(CONF_MENU_PATH))
        if not path or path in taken:
            continue
        taken.add(path)
        node = _dig(root, path.split("/"))
        node["say"] = str(data.get(CONF_LABEL, "") or "התראות אחרונות")
        node["alerts"] = True
        if intro := str(data.get(CONF_INTRO, "") or ""):
            node["intro"] = intro

    _apply_spoken_names(hass, root)
    _prune(root)

    return root


def build_tree(hass: HomeAssistant, entry: ConfigEntry):
    """העץ המוכן להגשה בשיחה."""
    return tree_mod.build(build_config(hass, entry))


def _action_phrase(action: str, data: dict) -> str:
    """תיאור הפעולה בעברית, כולל הערכים הקבועים שלה.

    בלי זה כל הפריטים של אותו מכשיר נשמעים זהים בתפריט, והמתקשר
    צריך לנחש מה כל אחד מהם עושה: "למזגן סלון הקש 1, למזגן סלון
    הקש 2". עם זה הוא שומע "להדלקה הקש 1, לכיבוי הקש 2".
    """
    if not action:
        return "סטטוס"

    phrase = translate_action(action)

    details = []
    for field, value in (data or {}).items():
        if isinstance(value, bool) or value in (None, ""):
            continue
        if isinstance(value, (list, tuple)):
            continue
        if isinstance(value, str):
            text = translate_option(value)
        else:
            # דרך say_number ולא בעיצוב ישיר: כך הנקודה העשרונית
            # יוצאת כמילה כבר כאן ולא נשענת על המסנן של ימות,
            # והסימן השלילי נשמר — עיצוב ישיר של -5 היה מגיע
            # למסנן כמקף, והמסנן ממיר מקף לרווח. כלומר המינוס
            # פשוט נעלם, והמתקשר שומע "5 מעלות".
            unit = field_unit(field)
            try:
                spoken = " ".join(part.data for part in say_number(float(value)))
            except (TypeError, ValueError):
                # ערך שאינו מספרי בשדה שאינו מחרוזת. נדיר, אבל כאן
                # נבנה כל העץ — חריגה כאן משתיקה את כל התפריט.
                spoken = str(value)
            text = f"{spoken} {unit}".strip()
        # שם השדה מיותר כשהוא כבר נאמר בשם הפעולה, למשל
        # "מצב מיזוג" עם השדה hvac_mode.
        name = translate_field(field)
        details.append(text if name in phrase else f"{name} {text}")

    return f"{phrase} {' '.join(details)}".strip() if details else phrase


def _device_name(hass, entity_id: str) -> str:
    """שם המכשיר כפי שהוא מוצג ב-Home Assistant."""
    state = hass.states.get(entity_id)
    name = state.attributes.get("friendly_name") if state else None
    return str(name) if name else entity_id


def _apply_spoken_names(hass, root: dict) -> None:
    """קביעת השם המוקרא לכל פריט, לפי ההקשר של הרמה שלו.

    שם שהוזן ידנית תמיד גובר. אחרת השם נבנה מהפעולה, ושם המכשיר
    מצורף אליו רק כשיש ברמה יותר ממכשיר אחד — בתת-תפריט המוקדש
    למזגן אחד, "להדלקה הקש 1" ברור יותר מ"להדלקה של מזגן סלון
    הקש 1".

    מחושב כאן ולא בזמן קריאת תת-הרשומה, כי הוא תלוי באחים:
    אי אפשר לדעת אם הרמה מוקדשת למכשיר אחד בלי לראות את כולה.
    """

    def walk(node: dict, depth: int) -> None:
        items = node.get("items") or {}
        entities = {
            c["entity"] for c in items.values() if c.get("entity")
        }
        dedicated = depth > 0 and len(entities) == 1

        for child in items.values():
            walk(child, depth + 1)
            if child.get("_label") or not child.get("entity"):
                continue
            phrase = _action_phrase(
                str(child.get("action") or ""), child.get("data") or {}
            )
            if dedicated:
                child["say"] = phrase
            else:
                device = _device_name(hass, child["entity"])
                child["say"] = (
                    device
                    if not child.get("action")
                    else f"{phrase} של {device}"
                )

    walk(root, 0)



# ----------------------------------------------------------------------
# ישות חכמה
# ----------------------------------------------------------------------


def _expand_smart(hass, node: dict, data) -> None:
    """הרחבת תוכנית של ישות חכמה לענף שלם בעץ.

    המספרים מגיעים מהתוכנית השמורה ואינם מחושבים כאן. מה שכן
    נבדק מול המכשיר החי הוא רשימת האפשרויות: מה שנעלם יורד, ומה
    שנוסף מצטרף בסוף — כך שהמספרים הקיימים אינם זזים.
    """
    entity_id = str(data.get(CONF_TARGET_ENTITY, ""))
    confirmed = bool(data.get(CONF_CONFIRM_RISKY, False))
    label = str(data.get(CONF_LABEL, "") or "").strip()

    node["say"] = label or _device_name(hass, entity_id)
    node["_label"] = True

    plan = data.get(CONF_PLAN)
    if not isinstance(plan, (list, tuple)):
        return

    for raw in plan:
        if not isinstance(raw, dict):
            continue
        digit = str(raw.get("digit", ""))
        if digit not in MENU_DIGITS:
            continue
        child = _smart_child(hass, entity_id, confirmed, raw)
        if child is not None:
            node.setdefault("items", {})[digit] = child


def _smart_child(hass, entity_id: str, confirmed: bool, raw: dict) -> dict | None:
    """צומת אחד מתוך התוכנית, לפי סוג היכולת."""
    kind = str(raw.get("kind", ""))
    action = str(raw.get("action", "") or "")
    # `_label` על כל צומת שנוצר כאן: השם כבר מדויק, ואסור
    # ל-`_apply_spoken_names` לדרוס אותו בשם שנגזר מהפעולה.
    base = {
        "say": str(raw.get("label", "") or action),
        "_label": True,
        "entity": entity_id,
        "confirmed": confirmed,
    }

    if kind == smart_mod.KIND_STATUS:
        return {**base, "action": "", "data": {}}

    if kind == smart_mod.KIND_SIMPLE:
        return {**base, "action": action, "data": {}}

    if kind == smart_mod.KIND_CHOICE:
        field_name = str(raw.get("field", ""))
        options = _live_options(hass, entity_id, field_name, raw)
        if not options:
            return None
        items = {}
        for index, value in enumerate(options[: len(MENU_DIGITS)]):
            items[MENU_DIGITS[index]] = {
                **base,
                "say": translate_option(value),
                "action": action,
                "data": {field_name: _typed(value)},
            }
        return {**base, "items": items}

    if kind == smart_mod.KIND_NUMBER:
        width = int(raw.get("width") or 0)
        if width <= 0:
            return None
        return {
            **base,
            "action": action,
            "data": {},
            "collect": {
                "field": str(raw.get("field", "")),
                "min": float(raw.get("min", 0)),
                "max": float(raw.get("max", 0)),
                "width": width,
            },
        }

    return None


def _expand_group(hass, node: dict, data) -> None:
    """הרחבת תוכנית של קבוצה — כל האורות במטבח וכדומה.

    זהה בצורתה להרחבת ישות בודדת, אלא שבמקום `entity` הצומת נושא
    `target`, והוא נפתר לרשימת ישויות רק בזמן השיחה. מכשיר שנוסף
    למרחב מצטרף מעצמו, ולכן כאן לא נשמר שום מזהה ישות.
    """
    target = {
        "domain": str(data.get(CONF_DOMAIN, "") or ""),
        "area": str(data.get(CONF_AREA, "") or ""),
        "floor": str(data.get(CONF_FLOOR, "") or ""),
        "label": str(data.get(CONF_LABEL_TARGET, "") or ""),
    }
    if not target["domain"]:
        return

    confirmed = bool(data.get(CONF_CONFIRM_RISKY, False))
    # שם הקבוצה נישא ביעד ולא רק ב-`say` של הצומת העליון. צומת
    # הבן נושא את שם הפעולה שלו ("הקראת מצב"), ובלי זה הדיווח היה
    # יוצא "הקראת מצב כרגע" במקום "התאורה במטבח כרגע".
    target["name"] = (
        str(data.get(CONF_LABEL, "") or "").strip() or _group_name(hass, target)
    )
    node["say"] = target["name"]
    node["_label"] = True
    node["target"] = target

    plan = data.get(CONF_PLAN)
    if not isinstance(plan, (list, tuple)):
        return

    for raw in plan:
        if not isinstance(raw, dict):
            continue
        digit = str(raw.get("digit", ""))
        if digit not in MENU_DIGITS:
            continue
        child = _smart_child(hass, "", confirmed, raw)
        if child is None:
            continue
        _apply_target(child, target)
        node.setdefault("items", {})[digit] = child


def _apply_target(node: dict, target: dict) -> None:
    """השתלת היעד בצומת ובכל צאצאיו.

    תת-תפריט של בחירה מייצר ילדים, וגם הם צריכים לדעת על מי הם
    פועלים — היעד אינו נשמר במקום אחד ונקרא ממנו, כי כל צומת
    מופעל בפני עצמו.
    """
    node["target"] = target
    node.pop("entity", None)
    for child in (node.get("items") or {}).values():
        _apply_target(child, target)


def _group_name(hass, target: dict) -> str:
    """שם מדובר ליעד, כשלא הוזן שם ידני."""
    domain = DOMAIN_NAMES.get(target["domain"], target["domain"])
    where = ""
    if target.get("area"):
        where = _area_name(hass, target["area"])
    elif target.get("floor"):
        where = _floor_name(hass, target["floor"])
    elif target.get("label"):
        where = _label_name(hass, target["label"])
    return f"{domain} ב{where}".strip() if where else f"{domain} בבית"


def _area_name(hass, area_id: str) -> str:
    try:
        from homeassistant.helpers import area_registry as ar  # noqa: PLC0415

        entry = ar.async_get(hass).async_get_area(area_id)
        return entry.name if entry else area_id
    except Exception:  # noqa: BLE001 — שם חסר אינו שובר תפריט
        return area_id


def _label_name(hass, label_id: str) -> str:
    try:
        from homeassistant.helpers import label_registry as lr  # noqa: PLC0415

        entry = lr.async_get(hass).async_get_label(label_id)
        return entry.name if entry else label_id
    except Exception:  # noqa: BLE001
        return label_id


def _floor_name(hass, floor_id: str) -> str:
    try:
        from homeassistant.helpers import floor_registry as fr  # noqa: PLC0415

        entry = fr.async_get(hass).async_get_floor(floor_id)
        return entry.name if entry else floor_id
    except Exception:  # noqa: BLE001
        return floor_id


def _live_options(hass, entity_id: str, field_name: str, raw: dict) -> list[str]:
    """האפשרויות להקראה — השמורות, מסוננות מול המכשיר החי.

    כשהמכשיר אינו מדווח על הרשימה (כבוי, לא זמין, או שדה שאין לו
    מאפיין מקביל), נשארות השמורות. עדיף תפריט שלם מתפריט שנעלם
    כשהמזגן כבוי.
    """
    stored = [str(v) for v in (raw.get("options") or [])]
    excluded = [str(v) for v in (raw.get("excluded") or [])]

    attribute = ENTITY_OPTION_ATTRIBUTES.get(field_name)
    if not attribute:
        return stored

    state = hass.states.get(entity_id)
    if state is None:
        return stored
    live = state.attributes.get(attribute)
    if not isinstance(live, (list, tuple)) or not live:
        return stored

    return smart_mod.merge_options(stored, excluded, [str(v) for v in live])


def _typed(value: str):
    """ערך מחרוזת חזרה לטיפוס שהשירות מצפה לו.

    האפשרויות נשמרות כמחרוזות, אבל `oscillate` מצפה לבוליאני
    ו-`set_percentage` למספר. שירות שמקבל מחרוזת במקום מספר
    נכשל באימות הסכמה, והמתקשר שומע "אירעה שגיאה".
    """
    lowered = value.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number == int(number) else number


# ----------------------------------------------------------------------
# עזרים לטופס
# ----------------------------------------------------------------------


def used_paths(entry: ConfigEntry, exclude: str = "") -> set[str]:
    """הנתיבים התפוסים, לאימות בטופס."""
    taken: set[str] = set()
    for subentry in entry.subentries.values():
        # כל סוג שתופס מקום בעץ חייב להופיע כאן. סוג שנשכח נראה
        # בטופס כמיקום פנוי, והמשתמש מציב עליו פריט שני — שנבלע
        # בשקט, כי בבנייה רק הראשון נלקח.
        if subentry.subentry_type not in (
            SUBENTRY_TYPE_ITEM,
            SUBENTRY_TYPE_SMART,
            SUBENTRY_TYPE_GROUP,
            SUBENTRY_TYPE_SUBMENU,
            SUBENTRY_TYPE_GOTO,
            SUBENTRY_TYPE_ALERTS,
        ):
            continue
        if subentry.subentry_id == exclude:
            continue
        if path := normalize_path(subentry.data.get(CONF_MENU_PATH)):
            taken.add(path)
    return taken


def submenu_paths(entry: ConfigEntry, exclude: str = "") -> dict[str, str]:
    """תתי-התפריטים שהוגדרו, כמיפוי נתיב לשם."""
    found: dict[str, str] = {}
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_SUBMENU:
            continue
        if subentry.subentry_id == exclude:
            continue
        if path := normalize_path(subentry.data.get(CONF_MENU_PATH)):
            found[path] = str(subentry.data.get(CONF_LABEL, "") or "")
    return found


def next_free_path(entry: ConfigEntry, parent: str = "", exclude: str = "") -> str:
    """הספרה הפנויה הבאה ברמה, כברירת מחדל בטופס."""
    taken = used_paths(entry, exclude)
    prefix = f"{parent}/" if parent else ""
    for digit in MENU_DIGITS:
        if f"{prefix}{digit}" not in taken:
            return f"{prefix}{digit}"
    return ""
