"""עורך התפריט — מה שלוח המקשים מציג, ומה שהוא משנה.

המודל נשאר תת-הרשומות, והעץ ממשיך להיבנות מהן בכל שיחה. כאן יש רק
שני תרגומים: מתת-הרשומות לתמונה של רמה אחת — תשעה מקשים ומה שהמתקשר
שומע — ומפעולה על מקש (הוספה, שם, הסרה, הזזה) לעדכון שלהן.

מה שהמתקשר שומע נלקח מהעץ האמיתי ולא משוחזר כאן, ולכן הלוח אינו יכול
להציג משהו שהטלפון לא יקריא.

שלושה סוגי רמות:

    menu      הראשי ותת-תפריט. מקש הוא תת-רשומה.
    plan      בתוך מכשיר או קבוצה. מקש הוא יכולת מהתוכנית.
    options   בתוך יכולת של בחירה. מקש הוא אפשרות.

כל שינוי קורא את מה שהוא צריך לגלות לפני שהוא כותב, וכותב ברצף אחד —
כך כמה עדכונים נסגרים בטעינה מחדש אחת.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

from . import menu as menu_mod
from . import registry
from . import smart as smart_mod
from . import tree as tree_mod
from .const import (
    CONF_ACTION,
    CONF_ACTION_DATA,
    CONF_CONFIRM_RISKY,
    CONF_DOMAIN,
    CONF_GOTO_TARGET,
    CONF_INTRO,
    CONF_LABEL,
    CONF_MENU_PATH,
    CONF_PLAN,
    CONF_TARGET,
    CONF_TARGET_ENTITY,
    DOMAIN,
    DOMAIN_NAMES,
    MENU_DIGITS,
    MENU_MAX_DEPTH,
    ASSISTANT_NAME,
    SUBENTRY_TYPE_ALERTS,
    SUBENTRY_TYPE_ASSISTANT,
    SUBENTRY_TYPE_GOTO,
    SUBENTRY_TYPE_GROUP,
    SUBENTRY_TYPE_ITEM,
    SUBENTRY_TYPE_SMART,
    SUBENTRY_TYPE_SUBMENU,
    domain_title,
    subentry_kind,
)
from .action_fields import (
    ENTITY_RANGE_ATTRIBUTES,
    action_is_usable,
    async_action_fields,
    async_action_name,
    entity_number_range,
    field_is_supported,
    field_label,
)
from .policy import available_actions, domain_is_blocked, domain_needs_confirmation
from .translations_he import translate_action, translate_field, translate_option

_LOGGER = logging.getLogger(__name__)

# סדר הקדימות על מקש אחד, כמו ב-`menu.build_config`: הראשון תופס.
_TREE_KINDS = (
    SUBENTRY_TYPE_SUBMENU,
    SUBENTRY_TYPE_ITEM,
    SUBENTRY_TYPE_SMART,
    SUBENTRY_TYPE_GROUP,
    SUBENTRY_TYPE_GOTO,
    SUBENTRY_TYPE_ASSISTANT,
    SUBENTRY_TYPE_ALERTS,
)

_TITLES = {
    SUBENTRY_TYPE_SUBMENU: "תת-תפריט",
    SUBENTRY_TYPE_GOTO: "מעבר לשלוחה",
    SUBENTRY_TYPE_ASSISTANT: ASSISTANT_NAME,
    SUBENTRY_TYPE_ALERTS: "התראות אחרונות",
}



class EditorError(Exception):
    """שינוי שאי אפשר לבצע. ההודעה מוצגת למשתמש כמות שהיא."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ----------------------------------------------------------------------
# מי יושב על איזה מקש
# ----------------------------------------------------------------------


@dataclass
class _Layout:
    owners: dict[str, Any] = field(default_factory=dict)
    """נתיב -> תת-הרשומה שתופסת אותו."""

    loose: list = field(default_factory=list)
    """תת-רשומות של התפריט שאינן נשמעות: בלי מקש, או על מקש תפוס."""


@dataclass
class _Spot:
    kind: str
    """root, sub, implicit, cap, option, empty או invalid."""

    sub: Any = None
    raw: dict | None = None
    index: int = -1


def _path_of(subentry) -> str:
    return menu_mod.normalize_path(subentry.data.get(CONF_MENU_PATH))


def _layout(entry: ConfigEntry) -> _Layout:
    layout = _Layout()
    for kind in _TREE_KINDS:
        for subentry in entry.subentries.values():
            if subentry_kind(subentry) != kind:
                continue
            path = _path_of(subentry)
            if not path or path in layout.owners:
                layout.loose.append(subentry)
            else:
                layout.owners[path] = subentry
    # פריט שנתלה מתחת למקש שאינו תפריט — אין דרך להגיע אליו.
    for path in sorted(layout.owners):
        parts = path.split("/")
        for depth in range(1, len(parts)):
            above = layout.owners.get("/".join(parts[:depth]))
            if above is not None and subentry_kind(above) != SUBENTRY_TYPE_SUBMENU:
                layout.loose.append(layout.owners.pop(path))
                break
    return layout


def _parts(path: object) -> tuple[str, ...]:
    raw = str(path or "").strip().strip("/")
    if not raw:
        return ()
    parts = tuple(raw.split("/"))
    if not all(len(p) == 1 and p in MENU_DIGITS for p in parts):
        raise EditorError("invalid_path", "מקש שאינו קיים")
    return parts


def _join(parts) -> str:
    return "/".join(parts)


def _plan(subentry) -> list[dict]:
    plan = subentry.data.get(CONF_PLAN)
    return [dict(e) for e in (plan or []) if isinstance(e, dict)]


def _plan_entry(subentry, digit: str) -> dict | None:
    for raw in _plan(subentry):
        if str(raw.get("digit", "")) == digit:
            return raw
    return None


def _options(hass: HomeAssistant, subentry, raw: dict) -> list[str]:
    """האפשרויות כפי שהן מוקראות כרגע, לפי הסדר."""
    entity_id = str(subentry.data.get(CONF_TARGET_ENTITY, "") or "")
    return menu_mod._live_options(hass, entity_id, str(raw.get("field", "")), raw)


def _spot(hass: HomeAssistant, layout: _Layout, parts: tuple[str, ...]) -> _Spot:
    """מה נמצא בנתיב הזה."""
    if not parts:
        return _Spot("root")
    for depth in range(1, len(parts) + 1):
        subentry = layout.owners.get(_join(parts[:depth]))
        if subentry is None:
            continue
        rest = parts[depth:]
        if not rest:
            return _Spot("sub", subentry)
        kind = subentry_kind(subentry)
        if kind == SUBENTRY_TYPE_SUBMENU:
            continue
        if kind not in (SUBENTRY_TYPE_SMART, SUBENTRY_TYPE_GROUP):
            return _Spot("invalid")
        raw = _plan_entry(subentry, rest[0])
        if len(rest) == 1:
            return _Spot("cap", subentry, raw) if raw else _Spot("empty", subentry)
        if len(rest) == 2 and raw and raw.get("kind") == smart_mod.KIND_CHOICE:
            index = MENU_DIGITS.index(rest[1])
            if index < len(_options(hass, subentry, raw)):
                return _Spot("option", subentry, raw, index)
            return _Spot("empty", subentry, raw)
        return _Spot("invalid")
    prefix = f"{_join(parts)}/"
    if any(path.startswith(prefix) for path in layout.owners):
        return _Spot("implicit")
    return _Spot("empty")


def _level_kind(spot: _Spot) -> str:
    """סוג הרמה שהמקש הזה פותח, או ריק אם אינו רמה."""
    if spot.kind in ("root", "implicit"):
        return "menu"
    if spot.kind == "sub":
        kind = subentry_kind(spot.sub)
        if kind == SUBENTRY_TYPE_SUBMENU:
            return "menu"
        if kind in (SUBENTRY_TYPE_SMART, SUBENTRY_TYPE_GROUP):
            return "plan"
    if spot.kind == "cap" and spot.raw.get("kind") == smart_mod.KIND_CHOICE:
        return "options"
    return ""


# ----------------------------------------------------------------------
# התמונה
# ----------------------------------------------------------------------


def _driver_flags(entry: ConfigEntry) -> dict:
    driver = registry.for_entry(entry)
    goto = bool(getattr(driver, "SUPPORTS_GOTO", False))
    only_assistant = bool(getattr(driver, "GOTO_ONLY_ASSIST", False))
    return {
        "goto": goto,
        # מעבר לשלוחה שהמשתמש נוקב בה. אצל ספק בלי שלוחות כל מעבר
        # מגיע לעוזר הקולי, ואין מה לשאול.
        "extensions": goto and not only_assistant,
        "goto_hint": str(getattr(driver, "GOTO_TARGET_HINT", "") or ""),
        "assistant": goto and bool(getattr(driver, "SUPPORTS_STREAM", False)),
        "assistant_target": str(getattr(driver, "ASSIST_GOTO", "") or ""),
        "alerts": bool(getattr(driver, "async_notify", None)),
    }


def entries(hass: HomeAssistant) -> list[dict]:
    """הרשומות שאפשר לערוך, ומה שכל ספק יודע."""
    found = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        driver = registry.for_entry(entry)
        if driver is None:
            continue
        found.append(
            {
                "entry_id": entry.entry_id,
                "title": str(getattr(entry, "title", "") or getattr(driver, "NAME", "")),
                **_driver_flags(entry),
            }
        )
    return found


def _entity_name(hass: HomeAssistant, entity_id: str) -> str:
    return menu_mod._device_name(hass, entity_id)


def _group_target(subentry) -> dict:
    return {
        "domain": str(subentry.data.get(CONF_DOMAIN, "") or ""),
        "target": smart_mod.stored_target(subentry.data),
    }


def _default_name(hass: HomeAssistant, subentry) -> str:
    """השם שמופיע כשלא הוזן שם מוקרא."""
    kind = subentry_kind(subentry)
    if kind in _TITLES:
        return _TITLES[kind]
    if kind == SUBENTRY_TYPE_GROUP:
        return menu_mod._group_name(hass, _group_target(subentry))
    return _entity_name(hass, str(subentry.data.get(CONF_TARGET_ENTITY, "") or ""))


def _cap_name(raw: dict) -> str:
    action = str(raw.get("action", "") or "")
    stored = str(raw.get("label", "") or "").strip()
    if not stored or stored == action:
        return translate_action(action) if action else "הקראת מצב"
    return stored


def _cap_detail(kind: str, count: int, low: float, high: float) -> str:
    if kind == smart_mod.KIND_CHOICE:
        return _count(count, "אפשרות", "אפשרויות", feminine=True) if count else "אין אפשרויות"
    if kind == smart_mod.KIND_NUMBER:
        return f"הקשת מספר, {int(low)} עד {int(high)}"
    return ""


@dataclass
class _View:
    hass: HomeAssistant
    entry: ConfigEntry
    layout: _Layout
    root: Any
    flags: dict

    def spot(self, parts: tuple[str, ...]) -> _Spot:
        return _spot(self.hass, self.layout, parts)

    def filled(self, parts: tuple[str, ...]) -> int:
        """כמה מקשים תפוסים ברמה."""
        return sum(
            1 for d in MENU_DIGITS if self.spot((*parts, d)).kind not in ("empty", "invalid")
        )

    def key(self, parts: tuple[str, ...]) -> dict | None:
        """תיאור של מקש אחד, או None אם הוא ריק."""
        spot = self.spot(parts)
        if spot.kind in ("empty", "invalid", "root"):
            return None
        path = _join(parts)
        node = tree_mod.resolve(self.root, parts)
        out: dict[str, Any] = {
            "path": path,
            "digit": parts[-1],
            "enter": bool(_level_kind(spot)),
            "silent": node is None,
            "label": "",
            "detail": "",
        }

        if spot.kind == "implicit":
            return {**out, "kind": "submenu", "name": f"תפריט {path}",
                    "detail": _count(self.filled(parts), "מקש", "מקשים")}

        if spot.kind == "option":
            value = _options(self.hass, spot.sub, spot.raw)[spot.index]
            return {**out, "kind": "option", "name": translate_option(value),
                    "value": value}

        if spot.kind == "cap":
            raw = spot.raw
            kind = str(raw.get("kind", ""))
            return {
                **out,
                "kind": "cap",
                "cap": kind,
                "ident": str(raw.get("ident", "")),
                "name": _cap_name(raw),
                "label": _cap_name(raw),
                "detail": _cap_detail(
                    kind,
                    len(_options(self.hass, spot.sub, raw))
                    if kind == smart_mod.KIND_CHOICE else 0,
                    float(raw.get("min", 0) or 0),
                    float(raw.get("max", 0) or 0),
                ),
            }

        subentry = spot.sub
        data = subentry.data
        kind = subentry_kind(subentry)
        label = str(data.get(CONF_LABEL, "") or "").strip()
        out.update(id=subentry.subentry_id, label=label)
        said = node.say if node is not None and node.say else ""
        fallback = said or label or _default_name(self.hass, subentry)

        if kind == SUBENTRY_TYPE_SUBMENU:
            return {**out, "kind": "submenu", "name": label or f"תפריט {path}",
                    "detail": _count(self.filled(parts), "מקש", "מקשים")}

        if kind in (SUBENTRY_TYPE_ITEM, SUBENTRY_TYPE_SMART):
            entity_id = str(data.get(CONF_TARGET_ENTITY, "") or "")
            device = _entity_name(self.hass, entity_id)
            out.update(
                entity_id=entity_id,
                domain=entity_id.split(".", 1)[0],
                missing=self.hass.states.get(entity_id) is None,
            )
            if kind == SUBENTRY_TYPE_SMART:
                return {**out, "kind": "device", "name": fallback,
                        "detail": _count(len(_plan(subentry)), "פעולה", "פעולות", feminine=True)}
            stored = data.get(CONF_ACTION_DATA)
            does = translate_action(str(data.get(CONF_ACTION, "") or ""))
            if isinstance(stored, dict) and stored:
                does = f"{does}: " + ", ".join(
                    f"{translate_field(str(k))} {translate_option(str(v))}"
                    for k, v in stored.items()
                )
            return {**out, "kind": "action", "name": fallback, "detail": device,
                    "does": does}

        if kind == SUBENTRY_TYPE_GROUP:
            target = _group_target(subentry)
            count = len(
                smart_mod.match_entities(self.hass, target["domain"], target["target"])
            )
            return {**out, "kind": "group", "name": fallback,
                    "domain": target["domain"], "missing": count == 0,
                    "detail": _count(count, "מכשיר", "מכשירים")}

        if kind in (SUBENTRY_TYPE_GOTO, SUBENTRY_TYPE_ASSISTANT):
            target = str(data.get(CONF_GOTO_TARGET, "") or "")
            assistant = kind == SUBENTRY_TYPE_ASSISTANT
            return {**out, "kind": "assistant" if assistant else "goto",
                    "name": label or (ASSISTANT_NAME if assistant else "מעבר"),
                    "target": target,
                    "detail": "" if assistant else target,
                    "silent": node is None or not self.flags["goto"]}

        return {**out, "kind": "alerts", "name": fallback}


def _count(number: int, one: str, many: str, *, feminine: bool = False) -> str:
    if number == 0:
        return "ריק"
    if number == 1:
        return f"{one} {'אחת' if feminine else 'אחד'}"
    return f"{number} {many}"


def _view(hass: HomeAssistant, entry: ConfigEntry) -> _View:
    return _View(
        hass, entry, _layout(entry), menu_mod.build_tree(hass, entry),
        _driver_flags(entry),
    )


async def _capabilities(hass: HomeAssistant, subentry) -> list:
    """היכולות של מכשיר או של קבוצה, מגילוי חי."""
    if subentry_kind(subentry) == SUBENTRY_TYPE_GROUP:
        target = _group_target(subentry)
        return await smart_mod.async_discover_group(
            hass, target["domain"], target["target"]
        )
    return await smart_mod.async_discover(
        hass, str(subentry.data.get(CONF_TARGET_ENTITY, "") or "")
    )


def _cap_label(capability) -> str:
    detail = _cap_detail(
        capability.kind, len(capability.options),
        capability.minimum, capability.maximum,
    )
    return f"{capability.label} ({detail})" if detail else capability.label


def _cap_choice(capability) -> dict:
    """יכולת כפי שבוחרים אותה בהוספה, עם הערכים שאפשר להציע בה."""
    return {
        "ident": capability.ident,
        "label": _cap_label(capability),
        "name": capability.label,
        "options": [
            {"value": value, "label": capability.option_label(value)}
            for value in capability.options
        ] if capability.kind == smart_mod.KIND_CHOICE else [],
    }


def _picked(raw: object) -> dict[str, list[str]]:
    """בחירות שנשלחו מהלוח כמיפוי של מזהה לרשימה."""
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): [str(v) for v in values]
        for key, values in raw.items() if isinstance(values, (list, tuple))
    }


async def async_level(hass: HomeAssistant, entry: ConfigEntry, path: object = "") -> dict:
    """רמה אחת: המקשים, מה שהמתקשר שומע, ומה אפשר להוסיף."""
    parts = _parts(path)
    view = _view(hass, entry)
    spot = view.spot(parts)
    level = _level_kind(spot)
    if not level:
        raise EditorError("not_found", "הרמה הזו אינה קיימת עוד")

    keys = {digit: view.key((*parts, digit)) for digit in MENU_DIGITS}

    node = tree_mod.resolve(view.root, parts)
    heard: list[str] = []
    if node is not None and node.is_menu:
        prompt = tree_mod.prompt_for(
            node, parts, 0, supports_goto=view.flags["goto"]
        )
        heard = [say.data for say in prompt.messages if say.kind == "text"]

    intro = None
    if spot.kind == "root":
        intro = str(entry.options.get(CONF_INTRO, "") or "")
    elif spot.kind == "sub" and level == "menu":
        intro = str(spot.sub.data.get(CONF_INTRO, "") or "")

    addable = None
    if level == "plan":
        used = {str(e.get("ident", "")) for e in _plan(spot.sub)}
        addable = [
            {"ident": c.ident, "label": _cap_label(c)}
            for c in await _capabilities(hass, spot.sub)
            if c.ident not in used
        ]
    elif level == "options":
        addable = [
            {"value": value, "label": translate_option(value)}
            for value in (str(v) for v in spot.raw.get("excluded") or [])
        ]

    crumbs = [{"path": "", "name": "ראשי"}]
    for depth in range(1, len(parts) + 1):
        key = view.key(parts[:depth])
        crumbs.append({"path": _join(parts[:depth]), "name": key["name"] if key else "?"})

    return {
        "entry_id": entry.entry_id,
        "path": _join(parts),
        "kind": level,
        "self": view.key(parts),
        "crumbs": crumbs,
        "keys": keys,
        "heard": heard,
        "silent": bool(parts) and node is None,
        "intro": intro,
        "addable": addable,
        "can_add": len(parts) < MENU_MAX_DEPTH,
        "can_nest": len(parts) + 1 < MENU_MAX_DEPTH,
        "loose": [
            {"id": s.subentry_id, "title": str(s.title).split("— ", 1)[-1]}
            for s in view.layout.loose
        ],
    }


async def async_capabilities(hass: HomeAssistant, entity_id: str) -> dict:
    """מה מכשיר יודע לעשות, ומה מסומן כברירת מחדל.

    מכשיר שיש לו פעולה אחת בלבד — כפתור, סצנה — מקבל אותה ישר על המקש,
    בלי תפריט של פריט אחד והקראת מצב.
    """
    _check_entity(hass, entity_id)
    found = await smart_mod.async_discover(hass, entity_id)
    active = [c for c in found if c.kind != smart_mod.KIND_STATUS]
    single = len(active) == 1 and active[0].kind == smart_mod.KIND_SIMPLE
    return {
        "entity_id": entity_id,
        "name": _entity_name(hass, entity_id),
        "capabilities": [
            {
                **_cap_choice(c),
                "checked": (c is active[0]) if single else index < len(MENU_DIGITS),
            }
            for index, c in enumerate(found)
        ],
        # מקש עם ערך קבוע מוצע רק למכשיר שיש לו פעולה כזו.
        "fixed": bool(await _fixed_actions(hass, entity_id)),
    }


# ----------------------------------------------------------------------
# מקש עם ערך קבוע: "מזגן ל-24", "אור ל-30 אחוז"
# ----------------------------------------------------------------------


def _action_field(hass: HomeAssistant, entity_id: str, name: str, spec: dict) -> dict:
    """שדה אחד של פעולה, כפי שהלוח מצייר אותו."""
    selector = spec.get("selector") or {}
    out: dict[str, Any] = {
        "name": name,
        "label": field_label(name, spec),
        "required": bool(spec.get("required")),
    }
    if "number" in selector:
        config = selector["number"] or {}
        low, high = entity_number_range(hass, entity_id, name, config)
        step = config.get("step")
        out.update(
            type="number", min=low, max=high,
            step=float(step) if step not in (None, "any") else None,
            unit=str(config.get("unit_of_measurement") or ""),
        )
    elif "select" in selector:
        options = []
        for option in (selector["select"] or {}).get("options", []):
            value = str(option.get("value", "")) if isinstance(option, dict) else str(option)
            label = option.get("label") if isinstance(option, dict) else None
            options.append({"value": value, "label": str(label or translate_option(value))})
        out.update(type="select", options=options)
    elif "boolean" in selector:
        out["type"] = "boolean"
    else:
        out["type"] = "text"
    return out


async def _fixed_actions(hass: HomeAssistant, entity_id: str) -> list[dict]:
    """הפעולות של המכשיר שמקבלות ערך, עם השדות של כל אחת.

    פעולה בלי שדות אינה כאן: היא כבר מוצעת כיכולת רגילה של המכשיר.
    """
    domain = entity_id.split(".", 1)[0]
    found = []
    for action in available_actions(hass, domain):
        fields = await async_action_fields(hass, domain, action, entity_id)
        if not action_is_usable(fields):
            continue
        shown = [
            _action_field(hass, entity_id, name, spec)
            for name, spec in fields.items()
            if field_is_supported(spec)
        ]
        # שדה שהטווח שלו בא מהמכשיר, והמכשיר אינו מדווח עליו — המכשיר
        # אינו תומך בו. שדה חובה כזה מוריד את הפעולה כולה.
        blind = [
            f for f in shown
            if f["name"] in ENTITY_RANGE_ATTRIBUTES and f.get("min") is None
        ]
        if any(f["required"] for f in blind):
            continue
        shown = [f for f in shown if f not in blind]
        if shown:
            found.append({
                "action": action,
                "label": await async_action_name(hass, domain, action),
                "fields": shown,
            })
    return found


async def async_actions(hass: HomeAssistant, entity_id: str) -> dict:
    """מה אפשר לשים על מקש כפעולה אחת עם ערך שנקבע מראש."""
    _check_entity(hass, entity_id)
    return {
        "entity_id": entity_id,
        "name": _entity_name(hass, entity_id),
        "actions": await _fixed_actions(hass, entity_id),
    }


def _action_values(fields: list[dict], raw: object) -> dict:
    """הערכים שנשלחו מהלוח, אחרי בדיקה מול השדות של הפעולה."""
    given = raw if isinstance(raw, dict) else {}
    values: dict[str, Any] = {}
    for spec in fields:
        value = given.get(spec["name"])
        if value is None or value == "":
            if spec["required"]:
                raise EditorError("value_required", f"חסר ערך: {spec['label']}")
            continue
        if spec["type"] == "number":
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise EditorError(
                    "bad_value", f"{spec['label']}: צריך מספר"
                ) from None
            low, high = spec.get("min"), spec.get("max")
            if (low is not None and number < low) or (high is not None and number > high):
                raise EditorError(
                    "bad_value", f"{spec['label']}: בין {low:g} ל-{high:g}"
                    if low is not None and high is not None
                    else f"{spec['label']}: הערך מחוץ לטווח"
                )
            values[spec["name"]] = int(number) if number.is_integer() else number
        elif spec["type"] == "select":
            if str(value) not in {o["value"] for o in spec["options"]}:
                raise EditorError("bad_value", f"{spec['label']}: ערך שאינו ברשימה")
            values[spec["name"]] = str(value)
        elif spec["type"] == "boolean":
            values[spec["name"]] = value in (True, "true", "on", "1", 1)
        else:
            values[spec["name"]] = str(value).strip()
    if not values:
        raise EditorError("value_required", "צריך לקבוע לפחות ערך אחד")
    return values


def _values_text(fields: list[dict], values: dict) -> str:
    """"טמפרטורה 24" — הערכים כפי שקוראים אותם."""
    parts = []
    for spec in fields:
        if spec["name"] not in values:
            continue
        value = values[spec["name"]]
        if spec["type"] == "select":
            value = next(
                (o["label"] for o in spec["options"] if o["value"] == value), value
            )
        elif spec["type"] == "boolean":
            value = "כן" if value else "לא"
        parts.append(f"{spec['label']} {value}")
    return ", ".join(parts)


async def async_rooms(hass: HomeAssistant) -> list[dict]:
    """החדרים בבית, ומה אפשר להפעיל בכל אחד. "כל הבית" בסוף."""
    from homeassistant.helpers import area_registry as ar  # noqa: PLC0415

    usable: dict[str, bool] = {}
    places = [
        (str(area.id), str(area.name))
        for area in sorted(
            ar.async_get(hass).async_list_areas(), key=lambda a: str(a.name)
        )
    ]
    places.append(("", "כל הבית"))

    rooms = []
    for area_id, name in places:
        kinds = await smart_mod.async_domains_in(hass, _area_target(area_id), usable)
        kinds = [(d, n) for d, n in kinds if not domain_needs_confirmation(d)]
        if not kinds:
            continue
        rooms.append(
            {
                "area_id": area_id,
                "name": name,
                "kinds": [
                    {"domain": d, "name": domain_title(d), "count": n}
                    for d, n in kinds
                ],
            }
        )
    return rooms


def _area_target(area_id: str) -> dict:
    return {"area_id": [area_id]} if area_id else {}


def _place_target(args: dict) -> dict:
    """המקום שנשלח מהלוח: חדר אחד, או בחירה של כמה מקומות עם החרגות."""
    if "target" not in args:
        return _area_target(str(args.get("area_id", "") or ""))
    chosen = args.get("target")
    chosen = dict(chosen) if isinstance(chosen, dict) else {}
    excluded = [str(e) for e in args.get("exclude") or [] if e]
    if excluded:
        chosen[smart_mod.TARGET_EXCLUDE] = {"entity_id": excluded}
    return smart_mod.clean_target(chosen)


def _named(items) -> list[dict]:
    return [
        {"id": str(item_id), "name": str(name)}
        for item_id, name in sorted(items, key=lambda pair: str(pair[1]))
    ]


def async_places(hass: HomeAssistant) -> dict:
    """מה אפשר לצרף למקום אחד: קומות, חדרים ותוויות."""
    from homeassistant.helpers import area_registry as ar  # noqa: PLC0415
    from homeassistant.helpers import floor_registry as fr  # noqa: PLC0415
    from homeassistant.helpers import label_registry as lr  # noqa: PLC0415

    return {
        "floors": _named(
            (f.floor_id, f.name) for f in fr.async_get(hass).async_list_floors()
        ),
        "areas": _named((a.id, a.name) for a in ar.async_get(hass).async_list_areas()),
        "labels": _named(
            (label.label_id, label.name)
            for label in lr.async_get(hass).async_list_labels()
        ),
    }


async def async_place(hass: HomeAssistant, args: dict) -> dict:
    """מה יש במקום שנבחר: הסוגים, והמכשירים שאפשר להשאיר בחוץ."""
    target = _place_target(args)
    kinds = [
        (d, n) for d, n in await smart_mod.async_domains_in(hass, target)
        if not domain_needs_confirmation(d)
    ]
    members = [
        {"entity_id": entity_id, "name": _entity_name(hass, entity_id), "domain": domain}
        for domain, _count in kinds
        for entity_id in smart_mod.match_entities(hass, domain, target)
    ]
    return {
        "name": menu_mod.place_name(hass, target) or "כל הבית",
        "target": {k: v for k, v in target.items() if k != smart_mod.TARGET_EXCLUDE},
        "kinds": [
            {"domain": d, "name": domain_title(d), "count": n} for d, n in kinds
        ],
        "members": sorted(members, key=lambda m: (m["domain"], m["name"])),
    }


async def async_place_functions(hass: HomeAssistant, args: dict) -> dict:
    """מה אפשר לעשות בכל סוג במקום — מה שמשותף למכשירים שנשארו בו."""
    target = _place_target(args)
    wanted = args.get("domains")
    kinds = []
    for domain, _count in await smart_mod.async_domains_in(hass, target):
        if wanted is not None and domain not in set(wanted):
            continue
        if domain_needs_confirmation(domain):
            continue
        found = await smart_mod.async_discover_group(hass, domain, target)
        if found:
            kinds.append({
                "domain": domain,
                "name": domain_title(domain),
                "capabilities": [_cap_choice(c) for c in found[: len(MENU_DIGITS)]],
            })
    return {"kinds": kinds}


# ----------------------------------------------------------------------
# כתיבה
# ----------------------------------------------------------------------


def _create(hass: HomeAssistant, entry: ConfigEntry, kind: str, title: str, data: dict) -> None:
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data=MappingProxyType(data), subentry_type=kind,
            title=title, unique_id=None,
        ),
    )


def _write(hass: HomeAssistant, entry: ConfigEntry, subentry, data: dict, title: str | None = None) -> None:
    changes: dict[str, Any] = {"data": data}
    if title is not None:
        changes["title"] = title
    hass.config_entries.async_update_subentry(entry, subentry, **changes)


def _retitle(title: object, path: str) -> str:
    return f"{path} — {str(title).split('— ', 1)[-1]}"


def _check_entity(hass: HomeAssistant, entity_id: str) -> None:
    domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
    if not domain or hass.states.get(entity_id) is None:
        raise EditorError("no_entity", "המכשיר לא נמצא")
    if domain_is_blocked(domain) or domain_needs_confirmation(domain):
        raise EditorError("blocked", "את המכשיר הזה אי אפשר להפעיל מהלוח")


def _free_slot(hass: HomeAssistant, entry: ConfigEntry, path: object) -> tuple[str, ...]:
    """מקש פנוי ברמת תפריט, או שגיאה."""
    parts = _parts(path)
    if not parts or len(parts) > MENU_MAX_DEPTH:
        raise EditorError("invalid_path", "אי אפשר להוסיף כאן מקש")
    layout = _layout(entry)
    if _level_kind(_spot(hass, layout, parts[:-1])) != "menu":
        raise EditorError("not_a_menu", "אי אפשר להוסיף כאן מקש")
    if _spot(hass, layout, parts).kind != "empty":
        raise EditorError("taken", f"מקש {parts[-1]} כבר תפוס")
    return parts


def add_place_menu(
    hass: HomeAssistant,
    entry: ConfigEntry,
    base: str,
    name: str,
    target: dict,
    plans: dict[str, list],
    *,
    confirmed: bool = False,
) -> int:
    """תת-תפריט למקום, וקבוצה לכל סוג מכשיר תחתיו. מחזיר כמה נוצרו."""
    _create(
        hass, entry, SUBENTRY_TYPE_SUBMENU, f"{base} — {name}",
        {CONF_MENU_PATH: base, CONF_LABEL: name, CONF_INTRO: ""},
    )
    made = 0
    for domain, plan in plans.items():
        if not plan:
            continue
        if made >= len(MENU_DIGITS):
            _LOGGER.warning(
                "Only %s kinds fit under one menu level. The rest were dropped",
                len(MENU_DIGITS),
            )
            break
        path = f"{base}/{MENU_DIGITS[made]}"
        made += 1
        _create(
            hass, entry, SUBENTRY_TYPE_GROUP,
            f"{path} — {DOMAIN_NAMES.get(domain, domain)}",
            {
                CONF_DOMAIN: domain,
                CONF_TARGET: target,
                CONF_MENU_PATH: path,
                CONF_LABEL: "",
                CONF_CONFIRM_RISKY: confirmed and domain_needs_confirmation(domain),
                CONF_PLAN: plan,
            },
        )
    return made


async def _room_plans(
    hass: HomeAssistant, target: dict, wanted=None, idents: dict | None = None
) -> dict[str, list]:
    """תוכנית לכל סוג מכשיר במקום, מגילוי חי.

    `idents` מצמצם סוג למה שנבחר בו; סוג שאינו שם מקבל את כל מה שמשותף
    לחברים שלו.
    """
    plans: dict[str, list] = {}
    for domain, _members in await smart_mod.async_domains_in(hass, target):
        if wanted is not None and domain not in set(wanted):
            continue
        if domain_needs_confirmation(domain):
            continue
        found = await smart_mod.async_discover_group(hass, domain, target)
        keep = set(idents[domain]) if idents and domain in idents else None
        chosen = [c.ident for c in found if keep is None or c.ident in keep]
        plan = smart_mod.build_plan(found, chosen[: len(MENU_DIGITS)])
        if plan:
            plans[domain] = plan
    return plans


def _place_room(
    hass: HomeAssistant,
    entry: ConfigEntry,
    parts: tuple[str, ...],
    name: str,
    target: dict,
    plans: dict[str, list],
) -> None:
    """מקום על מקש: סוג אחד יושב עליו ישר, כמה סוגים — תפריט."""
    slot = _join(parts)
    if len(plans) == 1:
        ((domain, plan),) = plans.items()
        default = menu_mod._group_name(hass, {"domain": domain, "target": target})
        _create(
            hass, entry, SUBENTRY_TYPE_GROUP, f"{slot} — {name or default}",
            {
                CONF_DOMAIN: domain,
                CONF_TARGET: target,
                CONF_MENU_PATH: slot,
                CONF_LABEL: name,
                CONF_CONFIRM_RISKY: False,
                CONF_PLAN: plan,
            },
        )
        return
    if len(parts) >= MENU_MAX_DEPTH:
        raise EditorError("too_deep", "אין מקום לתפריט נוסף בעומק הזה")
    add_place_menu(
        hass, entry, slot,
        name or menu_mod.place_name(hass, target) or "כל הבית",
        target, plans,
    )


async def async_build(
    hass: HomeAssistant, entry: ConfigEntry, path: object, area_ids: list
) -> int:
    """תפריט שלם בבת אחת: כל חדר שנבחר על המקש הפנוי הבא."""
    parts = _parts(path)
    found = []
    for area_id in [str(a or "") for a in area_ids]:
        target = _area_target(area_id)
        plans = await _room_plans(hass, target)
        if plans:
            found.append((target, plans))

    layout = _layout(entry)
    if _level_kind(_spot(hass, layout, parts)) != "menu":
        raise EditorError("not_a_menu", "אי אפשר להוסיף כאן מקש")
    free = [
        d for d in MENU_DIGITS if _spot(hass, layout, (*parts, d)).kind == "empty"
    ]
    for digit, (target, plans) in zip(free, found):
        _place_room(hass, entry, (*parts, digit), "", target, plans)
    return min(len(free), len(found))


async def async_add(
    hass: HomeAssistant, entry: ConfigEntry, path: object, what: str, **args: Any
) -> None:
    """מקש חדש. `what` הוא מה שהמשתמש בחר שיקרה בהקשה."""
    name = str(args.get("name", "") or "").strip()
    flags = _driver_flags(entry)

    if what == "capability":
        await _add_capability(hass, entry, _parts(path), str(args.get("ident", "")))
        return
    if what == "option":
        _add_option(hass, entry, _parts(path), str(args.get("value", "")))
        return

    _free_slot(hass, entry, path)

    if what == "device":
        entity_id = str(args.get("entity_id", "") or "")
        _check_entity(hass, entity_id)
        found = await smart_mod.async_discover(hass, entity_id)
        wanted = args.get("idents")
        chosen = [
            c.ident for c in found if wanted is None or c.ident in set(wanted)
        ][: len(MENU_DIGITS)]
        if not chosen:
            raise EditorError("nothing_chosen", "לא נבחרה אף פעולה")
        slot = _join(_free_slot(hass, entry, path))
        data: dict[str, Any] = {
            CONF_TARGET_ENTITY: entity_id,
            CONF_MENU_PATH: slot,
            CONF_LABEL: name,
            CONF_CONFIRM_RISKY: False,
        }
        only = next(c for c in found if c.ident == chosen[0])
        if len(chosen) == 1 and only.kind in (
            smart_mod.KIND_SIMPLE, smart_mod.KIND_STATUS,
        ):
            data[CONF_ACTION] = only.action
            data[CONF_ACTION_DATA] = {}
        else:
            data[CONF_PLAN] = smart_mod.build_plan(
                found, chosen, _picked(args.get("options")) or None
            )
        _create(
            hass, entry, SUBENTRY_TYPE_ITEM,
            f"{slot} — {name or _entity_name(hass, entity_id)}", data,
        )
        return

    if what == "action":
        entity_id = str(args.get("entity_id", "") or "")
        _check_entity(hass, entity_id)
        action = str(args.get("action", "") or "")
        chosen = next(
            (a for a in await _fixed_actions(hass, entity_id) if a["action"] == action),
            None,
        )
        if chosen is None:
            raise EditorError("unsupported", "המכשיר אינו תומך בפעולה הזו")
        values = _action_values(chosen["fields"], args.get("data"))
        slot = _join(_free_slot(hass, entry, path))
        # בלי שם, המתקשר היה שומע רק את שם המכשיר — ולא מה המקש עושה.
        spoken = name or (
            f"{_entity_name(hass, entity_id)}, {_values_text(chosen['fields'], values)}"
        )
        _create(
            hass, entry, SUBENTRY_TYPE_ITEM, f"{slot} — {spoken}",
            {
                CONF_TARGET_ENTITY: entity_id,
                CONF_MENU_PATH: slot,
                CONF_LABEL: spoken,
                CONF_CONFIRM_RISKY: False,
                CONF_ACTION: action,
                CONF_ACTION_DATA: values,
            },
        )
        return

    if what == "room":
        target = _place_target(args)
        plans = await _room_plans(
            hass, target, args.get("domains"), _picked(args.get("idents")) or None
        )
        if not plans:
            raise EditorError("empty_room", "אין כאן מכשירים שאפשר להפעיל בטלפון")
        _place_room(hass, entry, _free_slot(hass, entry, path), name, target, plans)
        return

    slot = _join(_free_slot(hass, entry, path))

    if what == "submenu":
        if not name:
            raise EditorError("name_required", "צריך שם לתפריט")
        if len(_parts(slot)) >= MENU_MAX_DEPTH:
            raise EditorError("too_deep", "אין מקום לתפריט נוסף בעומק הזה")
        _create(
            hass, entry, SUBENTRY_TYPE_SUBMENU, f"{slot} — {name}",
            {CONF_MENU_PATH: slot, CONF_LABEL: name, CONF_INTRO: ""},
        )
        return

    if what in ("goto", "assistant"):
        if not flags["assistant" if what == "assistant" else "extensions"]:
            raise EditorError("unsupported", "הספק הזה אינו תומך בכך")
        target = str(args.get("target", "") or "").strip()
        kind = SUBENTRY_TYPE_GOTO
        if what == "assistant":
            kind = SUBENTRY_TYPE_ASSISTANT
            # יעד קבוע של הספק גובר על מה שנשלח: אין שם מה לבחור.
            target = flags["assistant_target"] or target
        if not target:
            raise EditorError("target_required", "צריך יעד למעבר")
        _create(
            hass, entry, kind, f"{slot} — {name or _TITLES[kind]}",
            {CONF_MENU_PATH: slot, CONF_LABEL: name, CONF_GOTO_TARGET: target},
        )
        return

    if what == "alerts":
        if not flags["alerts"]:
            raise EditorError("unsupported", "הספק הזה אינו תומך בכך")
        _create(
            hass, entry, SUBENTRY_TYPE_ALERTS,
            f"{slot} — {name or _TITLES[SUBENTRY_TYPE_ALERTS]}",
            {CONF_MENU_PATH: slot, CONF_LABEL: name, CONF_INTRO: ""},
        )
        return

    raise EditorError("unknown", "סוג מקש שאינו מוכר")


def _plan_level(hass: HomeAssistant, entry: ConfigEntry, parts: tuple[str, ...]) -> _Spot:
    """הרמה שמעל מקש של יכולת."""
    if not parts:
        raise EditorError("invalid_path", "מקש שאינו קיים")
    above = _spot(hass, _layout(entry), parts[:-1])
    if _level_kind(above) != "plan":
        raise EditorError("not_a_menu", "אי אפשר להוסיף כאן מקש")
    return above


async def _add_capability(
    hass: HomeAssistant, entry: ConfigEntry, parts: tuple[str, ...], ident: str
) -> None:
    subentry = _plan_level(hass, entry, parts).sub
    found = await _capabilities(hass, subentry)
    subentry = _plan_level(hass, entry, parts).sub
    plan = _plan(subentry)
    if any(str(e.get("digit", "")) == parts[-1] for e in plan):
        raise EditorError("taken", f"מקש {parts[-1]} כבר תפוס")
    if any(str(e.get("ident", "")) == ident for e in plan):
        raise EditorError("taken", "הפעולה הזו כבר בתפריט")
    made = smart_mod.build_plan(found, [ident])
    if not made:
        raise EditorError("no_capability", "הפעולה הזו אינה זמינה עוד")
    plan.append({**made[0], "digit": parts[-1]})
    plan.sort(key=lambda e: str(e.get("digit", "")))
    _write(hass, entry, subentry, {**subentry.data, CONF_PLAN: plan})


def _options_level(hass: HomeAssistant, entry: ConfigEntry, parts: tuple[str, ...]) -> _Spot:
    if len(parts) < 2:
        raise EditorError("invalid_path", "מקש שאינו קיים")
    above = _spot(hass, _layout(entry), parts[:-1])
    if _level_kind(above) != "options":
        raise EditorError("not_a_menu", "אי אפשר לשנות כאן")
    return above


def _write_options(
    hass: HomeAssistant, entry: ConfigEntry, spot: _Spot, options: list[str]
) -> None:
    """שמירת סדר האפשרויות; מה שירד נרשם כמוחרג, כדי שלא יחזור מעצמו."""
    known = [
        *_options(hass, spot.sub, spot.raw),
        *(str(v) for v in spot.raw.get("excluded") or []),
    ]
    excluded = list(dict.fromkeys(v for v in known if v not in options))
    plan = [
        {**raw, "options": options, "excluded": excluded}
        if str(raw.get("digit", "")) == str(spot.raw.get("digit", ""))
        else raw
        for raw in _plan(spot.sub)
    ]
    _write(hass, entry, spot.sub, {**spot.sub.data, CONF_PLAN: plan})


def _add_option(
    hass: HomeAssistant, entry: ConfigEntry, parts: tuple[str, ...], value: str
) -> None:
    spot = _options_level(hass, entry, parts)
    options = _options(hass, spot.sub, spot.raw)
    if not value or value in options:
        raise EditorError("taken", "האפשרות הזו כבר בתפריט")
    if len(options) >= len(MENU_DIGITS):
        raise EditorError("full", "אין מקש פנוי")
    _write_options(hass, entry, spot, [*options, value])


def _under(entry: ConfigEntry, path: str) -> list:
    """כל מה שתלוי מתחת לנתיב."""
    prefix = f"{path}/"
    return [
        s for s in entry.subentries.values()
        if subentry_kind(s) in _TREE_KINDS and _path_of(s).startswith(prefix)
    ]


def _loose(entry: ConfigEntry, subentry_id: str):
    for subentry in _layout(entry).loose:
        if subentry.subentry_id == subentry_id:
            return subentry
    raise EditorError("not_found", "הפריט אינו קיים עוד")


def rename(hass: HomeAssistant, entry: ConfigEntry, path: object, name: str) -> None:
    """שם מוקרא חדש. שם ריק מחזיר את ברירת המחדל."""
    parts = _parts(path)
    name = str(name or "").strip()
    spot = _spot(hass, _layout(entry), parts)

    if spot.kind == "implicit":
        if not name:
            raise EditorError("name_required", "צריך שם לתפריט")
        slot = _join(parts)
        _create(
            hass, entry, SUBENTRY_TYPE_SUBMENU, f"{slot} — {name}",
            {CONF_MENU_PATH: slot, CONF_LABEL: name, CONF_INTRO: ""},
        )
        return

    if spot.kind == "cap":
        if not name:
            raise EditorError("name_required", "צריך שם לפעולה")
        plan = [
            {**raw, "label": name}
            if str(raw.get("digit", "")) == parts[-1] else raw
            for raw in _plan(spot.sub)
        ]
        _write(hass, entry, spot.sub, {**spot.sub.data, CONF_PLAN: plan})
        return

    if spot.kind != "sub":
        raise EditorError("not_found", "אי אפשר לשנות את השם של המקש הזה")

    subentry = spot.sub
    if subentry_kind(subentry) == SUBENTRY_TYPE_SUBMENU and not name:
        raise EditorError("name_required", "צריך שם לתפריט")
    _write(
        hass, entry, subentry, {**subentry.data, CONF_LABEL: name},
        f"{_join(parts)} — {name or _default_name(hass, subentry)}",
    )


def update(hass: HomeAssistant, entry: ConfigEntry, path: object, **args: Any) -> None:
    """משפט הפתיחה של רמה, או היעד של מעבר."""
    parts = _parts(path)
    spot = _spot(hass, _layout(entry), parts)

    if "intro" in args:
        intro = str(args.get("intro") or "").strip()
        if spot.kind == "root":
            hass.config_entries.async_update_entry(
                entry, options={**entry.options, CONF_INTRO: intro}
            )
            return
        if spot.kind != "sub" or subentry_kind(spot.sub) not in (
            SUBENTRY_TYPE_SUBMENU, SUBENTRY_TYPE_ALERTS,
        ):
            raise EditorError("not_found", "לרמה הזו אין משפט פתיחה")
        _write(hass, entry, spot.sub, {**spot.sub.data, CONF_INTRO: intro})
        return

    if "target" in args:
        target = str(args.get("target") or "").strip()
        kind = subentry_kind(spot.sub) if spot.kind == "sub" else ""
        if kind not in (SUBENTRY_TYPE_GOTO, SUBENTRY_TYPE_ASSISTANT):
            raise EditorError("not_found", "המקש הזה אינו מעבר")
        flags = _driver_flags(entry)
        # יעד של עוזר נערך רק היכן שהמשתמש הוא שקבע אותו.
        if (
            flags["assistant_target"]
            if kind == SUBENTRY_TYPE_ASSISTANT
            else not flags["extensions"]
        ):
            raise EditorError("unsupported", "הספק הזה אינו תומך בכך")
        if not target:
            raise EditorError("target_required", "צריך יעד למעבר")
        _write(hass, entry, spot.sub, {**spot.sub.data, CONF_GOTO_TARGET: target})


def remove(
    hass: HomeAssistant, entry: ConfigEntry, path: object = "", subentry_id: str = ""
) -> None:
    """הסרת מקש. תפריט נמחק עם כל מה שבתוכו."""
    if subentry_id:
        hass.config_entries.async_remove_subentry(
            entry, _loose(entry, subentry_id).subentry_id
        )
        return

    parts = _parts(path)
    spot = _spot(hass, _layout(entry), parts)

    if spot.kind == "cap":
        plan = [r for r in _plan(spot.sub) if str(r.get("digit", "")) != parts[-1]]
        _write(hass, entry, spot.sub, {**spot.sub.data, CONF_PLAN: plan})
        return

    if spot.kind == "option":
        above = _options_level(hass, entry, parts)
        options = _options(hass, above.sub, above.raw)
        del options[spot.index]
        _write_options(hass, entry, above, options)
        return

    if spot.kind not in ("sub", "implicit"):
        raise EditorError("not_found", "המקש כבר ריק")

    doomed = []
    if _level_kind(spot) == "menu":
        doomed = [s.subentry_id for s in _under(entry, _join(parts))]
    if spot.kind == "sub":
        doomed.append(spot.sub.subentry_id)
    for ident in doomed:
        hass.config_entries.async_remove_subentry(entry, ident)


def move(
    hass: HomeAssistant,
    entry: ConfigEntry,
    to: object,
    path: object = "",
    subentry_id: str = "",
) -> None:
    """העברת מקש למקום אחר. על מקש תפוס באותה רמה — השניים מתחלפים."""
    dest = _parts(to)
    if not dest:
        raise EditorError("invalid_path", "מקש שאינו קיים")
    layout = _layout(entry)

    if subentry_id:
        subentry = _loose(entry, subentry_id)
        slot = _join(_free_slot(hass, entry, to))
        _write(
            hass, entry, subentry, {**subentry.data, CONF_MENU_PATH: slot},
            _retitle(subentry.title, slot),
        )
        return

    src = _parts(path)
    if src == dest:
        return
    spot = _spot(hass, layout, src)
    same_level = src[:-1] == dest[:-1]

    if spot.kind == "cap":
        if not same_level:
            raise EditorError("other_level", "פעולה של מכשיר זזה רק בתוך התפריט שלו")
        plan = _plan(spot.sub)
        for raw in plan:
            digit = str(raw.get("digit", ""))
            if digit == src[-1]:
                raw["digit"] = dest[-1]
            elif digit == dest[-1]:
                raw["digit"] = src[-1]
        plan.sort(key=lambda e: str(e.get("digit", "")))
        _write(hass, entry, spot.sub, {**spot.sub.data, CONF_PLAN: plan})
        return

    if spot.kind == "option":
        if not same_level:
            raise EditorError("other_level", "אפשרות זזה רק בתוך התפריט שלה")
        above = _options_level(hass, entry, src)
        options = _options(hass, above.sub, above.raw)
        target = min(MENU_DIGITS.index(dest[-1]), len(options) - 1)
        options[spot.index], options[target] = options[target], options[spot.index]
        _write_options(hass, entry, above, options)
        return

    if spot.kind not in ("sub", "implicit"):
        raise EditorError("not_found", "אין מה להעביר")

    if dest[: len(src)] == src:
        raise EditorError("into_itself", "אי אפשר להעביר תפריט לתוך עצמו")
    if _level_kind(_spot(hass, layout, dest[:-1])) != "menu":
        raise EditorError("not_a_menu", "אי אפשר להעביר לכאן")
    there = _spot(hass, layout, dest)
    swap = there.kind in ("sub", "implicit")
    if swap and not same_level:
        raise EditorError("taken", f"מקש {dest[-1]} כבר תפוס")
    if not swap and there.kind != "empty":
        raise EditorError("taken", f"מקש {dest[-1]} כבר תפוס")

    old, new = _join(src), _join(dest)
    moves: list[tuple[Any, str]] = []
    for subentry in entry.subentries.values():
        if subentry_kind(subentry) not in _TREE_KINDS:
            continue
        current = _path_of(subentry)
        if current == old or current.startswith(f"{old}/"):
            moves.append((subentry, new + current[len(old):]))
        elif swap and (current == new or current.startswith(f"{new}/")):
            moves.append((subentry, old + current[len(new):]))
    if any(len(target.split("/")) > MENU_MAX_DEPTH for _s, target in moves):
        raise EditorError("too_deep", "התפריט עמוק מדי למקום הזה")
    for subentry, target in moves:
        _write(
            hass, entry, subentry, {**subentry.data, CONF_MENU_PATH: target},
            _retitle(subentry.title, target),
        )
