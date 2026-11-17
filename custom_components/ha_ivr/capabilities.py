"""מה ישות יודעת לעשות, לפי אותם כללים ש-Home Assistant עצמו מפעיל.

`async_get_all_descriptions` מתאר כל פעולה לפי הדומיין שלה, אבל
לא כל ישות בדומיין תומכת בכל פעולה: לתריס בלי מיקום אין
`set_cover_position`, ולמנעול בלי OPEN אין `lock.open`. בקובץ
`services.yaml` של כל דומיין יש מסנן יעד (`target.entity`) ומסנן
לכל שדה (`filter`). מסך האוטומציות מפעיל אותם דרך
`get_services_for_target`, וכאן מפעילים אותם באותה צורה.

כאן גם ההחלטות שאינן תלויות בטלפון: האם פעולה דורשת קוד ואיך
מקישים אותו, ואילו שדות אפשר לאסוף בהקשה או רק כערך קבוע
שנקבע מראש בהגדרה.
"""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant, callback

_LOGGER = logging.getLogger(__name__)

# הפעולות ש-`group.*` קלאסי מקבל. ל-`group` אין פעולות ישות משלו,
# ו-HA מציע לו את שלוש אלה מ-`homeassistant` (יעד בלי מסנן). רשימה
# סגורה: שירות עתידי בלי מסנן לא ייכנס לקבוצה מעצמו.
GROUP_ACTIONS: tuple[str, ...] = ("turn_on", "turn_off", "toggle")
GROUP_ACTION_DOMAIN = "homeassistant"

# בוררים שאפשר להקיש בטלפון: בחירה, כן/לא, מספר.
DIALABLE_SELECTORS = frozenset({"select", "boolean", "number"})

# שדות שמחזיקים קוד גישה. לעולם אינם נשמרים, נרשמים או מוקראים.
CODE_FIELD = "code"

# מאפייני אפשרויות שאינם נגזרים מהכלל הכללי (`<f>s`, `<f>_list`,
# `available_<f>s`). השאר נמצאים מעצמם.
OPTION_ATTRIBUTES: dict[str, str] = {
    "hvac_mode": "hvac_modes",
    "preset_mode": "preset_modes",
    "fan_mode": "fan_modes",
    "swing_mode": "swing_modes",
    "swing_horizontal_mode": "swing_horizontal_modes",
    "humidity_mode": "available_modes",
    "mode": "available_modes",
    "option": "options",
    "source": "source_list",
    "sound_mode": "sound_mode_list",
    "effect": "effect_list",
    "operation_mode": "operation_list",
    "fan_speed": "fan_speed_list",
}


@dataclass(frozen=True)
class EntityInfo:
    """מה שהמסננים צריכים לדעת על ישות."""

    entity_id: str
    domain: str
    state: Any
    attributes: dict
    features: int
    device_class: str | None
    integration: str | None
    live: bool


def entity_info(hass: HomeAssistant, entity_id: str) -> EntityInfo | None:
    """הנתונים של ישות: מה-state, ומהרישום כשאין state.

    ישות `unavailable` שומרת את `supported_features` ואת מאפייני
    היכולת שלה (כך כותב אותם core), ולכן ה-state הוא המקור. הרישום
    משלים כשאין state כלל, או כשאינטגרציה אפסה את המסכה בניגוד
    לברירת המחדל של core.
    """
    if "." not in entity_id:
        return None
    domain = entity_id.split(".", 1)[0]
    state = hass.states.get(entity_id)
    registry_entry = _registry_entry(hass, entity_id)

    if state is None and registry_entry is None:
        return None

    attributes = dict(state.attributes) if state is not None else {}
    features = _as_int(attributes.get("supported_features"))
    device_class = attributes.get("device_class")
    live = state is not None

    if registry_entry is not None:
        reg_features = _as_int(getattr(registry_entry, "supported_features", 0))
        unavailable = state is None or state.state in ("unavailable", "unknown")
        if unavailable and not features and reg_features:
            features = reg_features
        if device_class is None:
            device_class = getattr(registry_entry, "device_class", None) or getattr(
                registry_entry, "original_device_class", None
            )
        if state is None and isinstance(getattr(registry_entry, "capabilities", None), dict):
            attributes = {**registry_entry.capabilities, **attributes}

    integration = getattr(registry_entry, "platform", None) if registry_entry else None
    return EntityInfo(
        entity_id=entity_id,
        domain=domain,
        state=state.state if state is not None else None,
        attributes=attributes,
        features=features,
        device_class=device_class,
        integration=integration,
        live=live,
    )


def _registry_entry(hass: HomeAssistant, entity_id: str):
    try:
        from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

        return er.async_get(hass).async_get(entity_id)
    except Exception:  # noqa: BLE001 — רישום חסר אינו מפיל גילוי
        return None


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ----------------------------------------------------------------------
# מסנני היעד והשדות, כמו ב-core
# ----------------------------------------------------------------------


def resolve_feature(value: Any) -> int | None:
    """ערך של `supported_features` ממסנן: מספר, או שם כמו
    `light.LightEntityFeature.EFFECT` שנפתר לקבוע עצמו."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str) or value.count(".") != 2:
        return None
    domain, enum_name, member = value.split(".")
    try:
        module = importlib.import_module(f"homeassistant.components.{domain}")
        return int(getattr(getattr(module, enum_name), member))
    except Exception:  # noqa: BLE001 — שם שאינו נפתר אינו מתאים לאף ישות
        _LOGGER.debug("Unknown feature %s", value)
        return None


def features_match(required: Any, features: int) -> bool:
    """`supported_features` של מסנן: אחת מהרשימה צריכה להתקיים.

    איבר שהוא רשימה בעצמו הוא צירוף, וכל הביטים שלו נדרשים יחד.
    """
    if not required:
        return True
    options = required if isinstance(required, (list, tuple)) else [required]
    for option in options:
        parts = option if isinstance(option, (list, tuple)) else [option]
        mask = 0
        valid = True
        for part in parts:
            bit = resolve_feature(part)
            if bit is None:
                valid = False
                break
            mask |= bit
        if valid and features & mask == mask:
            return True
    return False


def _listify(value: Any) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple, set)) else [value]


def entity_filter_matches(entity_filter: dict, info: EntityInfo) -> bool:
    """מסנן ישות אחד מתוך `target.entity`."""
    if not isinstance(entity_filter, dict):
        return True
    if (domains := _listify(entity_filter.get("domain"))) and info.domain not in domains:
        return False
    if (integration := entity_filter.get("integration")) and info.integration != integration:
        return False
    if (classes := _listify(entity_filter.get("device_class"))) and info.device_class not in classes:
        return False
    return features_match(entity_filter.get("supported_features"), info.features)


def target_matches(description: dict, info: EntityInfo) -> bool:
    """האם יעד הפעולה מקבל את הישות. יעד בלי מסנן מקבל כל ישות."""
    target = description.get("target")
    if not isinstance(target, dict):
        return False
    filters = target.get("entity")
    if filters is None:
        return True
    filters = _listify(filters)
    if not filters:
        return True
    return any(entity_filter_matches(f, info) for f in filters)


def field_applies(spec: dict, info: EntityInfo | None) -> bool:
    """מסנן השדה (`filter`): לפי `supported_features` או לפי מאפיין."""
    flt = spec.get("filter") if isinstance(spec, dict) else None
    if not isinstance(flt, dict) or info is None:
        return True
    if "supported_features" in flt and not features_match(
        flt["supported_features"], info.features
    ):
        return False
    attributes = flt.get("attribute")
    if isinstance(attributes, dict):
        for name, allowed in attributes.items():
            value = info.attributes.get(name)
            allowed = _listify(allowed)
            values = _listify(value)
            if not any(v in allowed or str(v) in map(str, allowed) for v in values):
                return False
    return True


async def async_actions_for(
    hass: HomeAssistant, entity_id: str, descriptions: dict
) -> list[tuple[str, str]]:
    """הפעולות שהישות מקבלת, כזוגות (דומיין, פעולה).

    קודם הפונקציה של core שמשמשת את מסך האוטומציות. היא במודול
    פנימי, ולכן יש גיבוי שמפעיל את אותם מסננים מתוך התיאורים. הגיבוי
    משמש גם לישות לא זמינה: `entity_info` משלים לה את המסכה מהרישום,
    ו-core היה קורא את ה-state בלבד.
    """
    info = entity_info(hass, entity_id)
    if info is None:
        return []

    found: set[str] | None = None
    if info.live and info.state not in ("unavailable", "unknown"):
        try:
            from homeassistant.components.websocket_api.automation import (  # noqa: PLC0415
                async_get_services_for_target,
            )

            found = set(
                await async_get_services_for_target(
                    hass, {"entity_id": [entity_id]}, False
                )
            )
        except Exception:  # noqa: BLE001 — מודול פנימי; הגיבוי זהה בכללים
            _LOGGER.debug("Falling back to local target filters", exc_info=True)
            found = None

    if found is None:
        found = set()
        for svc_domain in {info.domain, GROUP_ACTION_DOMAIN}:
            for action, description in (descriptions.get(svc_domain) or {}).items():
                if isinstance(description, dict) and target_matches(description, info):
                    found.add(f"{svc_domain}.{action}")

    actions: list[tuple[str, str]] = []
    for full in sorted(found):
        svc_domain, _, action = full.partition(".")
        if svc_domain == info.domain or (
            info.domain == "group"
            and svc_domain == GROUP_ACTION_DOMAIN
            and action in GROUP_ACTIONS
        ):
            actions.append((svc_domain, action))
    return actions


# ----------------------------------------------------------------------
# אפשרויות של שדה
# ----------------------------------------------------------------------


def option_attribute(field_name: str, attributes: dict) -> str | None:
    """המאפיין שמחזיק את האפשרויות של שדה, אם הישות מדווחת עליו."""
    candidates = [
        OPTION_ATTRIBUTES.get(field_name),
        f"{field_name}s",
        f"{field_name}_list",
        f"available_{field_name}s",
    ]
    for name in candidates:
        if name and isinstance(attributes.get(name), (list, tuple)) and attributes.get(name):
            return name
    return None


def entity_options(field_name: str, attributes: dict) -> list[str]:
    name = option_attribute(field_name, attributes)
    if name is None:
        return []
    return [str(v) for v in attributes[name] if v is not None and str(v) != ""]


# ----------------------------------------------------------------------
# קוד גישה
# ----------------------------------------------------------------------

# אין צורך בקוד.
CODE_NONE = "none"
# קוד באורך קבוע — מקישים בדיוק `width` ספרות.
CODE_FIXED = "fixed"
# קוד באורך משתנה — מקישים ומסיימים בסולמית.
CODE_TERMINATED = "terminated"
# קוד שאינו ספרות בלבד. אי אפשר להקיש אותו בטלפון.
CODE_UNDIALABLE = "undialable"

MAX_CODE_LENGTH = 12

_FIXED_RE = re.compile(r"^\^?(?:\\d|\[0-9\])\{(\d+)\}\$$")
_RANGE_RE = re.compile(r"^\^?(?:\\d|\[0-9\])(?:\{(\d+),(\d*)\}|\+|\*)\$?$")
_PREFIX_RE = re.compile(r"^\^?(?:\\d|\[0-9\])\{(\d+)\}$")


@dataclass(frozen=True)
class CodeRule:
    kind: str
    width: int = 0
    min_len: int = 1
    max_len: int = MAX_CODE_LENGTH


def lock_code_rule(code_format: str | None, default_code: str | None) -> CodeRule:
    """איך מקישים קוד למנעול, לפי ה-regex שהמנעול מדווח.

    core בודק את הקוד ב-`re.match`, שמעגן רק את ההתחלה. לכן `\\d{4}`
    בלי `$` מקבל גם קוד ארוך יותר, ונחשב אורך משתנה.
    """
    if not code_format:
        return CodeRule(CODE_NONE)
    try:
        compiled = re.compile(code_format)
    except re.error:
        return CodeRule(CODE_UNDIALABLE)
    # קוד ברירת מחדל ברישום, שעובר את הבדיקה, פוטר מהקשה — כמו ב-core.
    if default_code and compiled.match(default_code):
        return CodeRule(CODE_NONE)
    if compiled.match(""):
        return CodeRule(CODE_NONE)

    text = code_format.strip()
    if match := _FIXED_RE.match(text):
        width = int(match.group(1))
        if 0 < width <= MAX_CODE_LENGTH:
            return CodeRule(CODE_FIXED, width=width, min_len=width, max_len=width)
    if match := _PREFIX_RE.match(text):
        low = int(match.group(1))
        return CodeRule(CODE_TERMINATED, min_len=max(1, low))
    if match := _RANGE_RE.match(text):
        low = int(match.group(1)) if match.group(1) else 1
        high = int(match.group(2)) if match.group(2) else MAX_CODE_LENGTH
        return CodeRule(CODE_TERMINATED, min_len=max(1, low),
                        max_len=min(high, MAX_CODE_LENGTH))

    # תבנית שלא פוענחה: ספרות בלבד עוברות? אז אורך משתנה.
    digit_samples = ("1234", "123456", "0000")
    other_samples = ("abcd", "12a4", "a")
    if any(compiled.match(s) for s in digit_samples) and not any(
        compiled.fullmatch(s) for s in other_samples
    ):
        return CodeRule(CODE_TERMINATED)
    return CodeRule(CODE_UNDIALABLE)


def alarm_code_rule(action: str, attributes: dict) -> CodeRule:
    """קוד לאזעקה. `code_format` כאן הוא "number" או "text", לא regex.

    דריכה דורשת קוד רק כש-`code_arm_required` דלוק; נטרול — כשיש
    `code_format`. core אינו בודק את הקוד בעצמו, הישות בודקת.
    """
    code_format = attributes.get("code_format")
    if not code_format:
        return CodeRule(CODE_NONE)
    if action.startswith("alarm_arm_") and not attributes.get("code_arm_required", True):
        return CodeRule(CODE_NONE)
    if action == "alarm_trigger" and not attributes.get("code_arm_required", True):
        return CodeRule(CODE_NONE)
    if str(code_format) == "number":
        return CodeRule(CODE_TERMINATED)
    return CodeRule(CODE_UNDIALABLE)


def code_rule(hass: HomeAssistant, info: EntityInfo, action: str, fields: dict) -> CodeRule:
    """האם הפעולה דורשת קוד, ואיך מקישים אותו."""
    if CODE_FIELD not in fields:
        return CodeRule(CODE_NONE)
    if info.domain == "alarm_control_panel":
        return alarm_code_rule(action, info.attributes)
    if info.domain == "lock":
        registry_entry = _registry_entry(hass, info.entity_id)
        options = getattr(registry_entry, "options", None) or {}
        default_code = (options.get("lock") or {}).get("default_code") if isinstance(options, dict) else None
        return lock_code_rule(info.attributes.get("code_format"), default_code)
    return CodeRule(CODE_NONE)


# ----------------------------------------------------------------------
# סיווג שדות
# ----------------------------------------------------------------------


def selector_kind(spec: dict) -> str:
    selector = spec.get("selector") if isinstance(spec, dict) else None
    if not isinstance(selector, dict) or not selector:
        return ""
    return next(iter(selector))


# ----------------------------------------------------------------------
# מטמון
# ----------------------------------------------------------------------

# כמה ישויות נשמרות. בית עם אלפי ישויות שנפתחות בבורר לא ינפח את
# הזיכרון לצמיתות; הישנה ביותר יוצאת.
CACHE_LIMIT = 500

# מאפיינים ששינוי בהם משנה את מה שהישות יודעת לעשות.
_RELEVANT = ("supported_features", "device_class", "code_format", "code_arm_required",
             "target_temp_step", "step", "min", "max", "options")
_RELEVANT_SUFFIX = ("_list", "_modes", "_temp", "_humidity")
_CACHE_KEY = "ha_ivr_capability_cache"


class CapabilityCache:
    """היכולות של כל ישות, עד שמשהו רלוונטי בה משתנה.

    הניקוי ממוקד: שינוי בישות מנקה רק אותה, ופעולה שנרשמה או הוסרה
    מנקה רק את הדומיין שלה. הבנייה מחדש עצלה — בפעם הבאה שמישהו
    שואל — ולכן סערת אירועים בעליית HA עולה רק מחיקות מהמילון.
    """

    def __init__(self, limit: int = CACHE_LIMIT) -> None:
        from collections import OrderedDict  # noqa: PLC0415

        self._items: OrderedDict[str, Any] = OrderedDict()
        self._limit = limit

    def get(self, entity_id: str) -> Any:
        value = self._items.get(entity_id)
        if value is not None:
            self._items.move_to_end(entity_id)
        return value

    def put(self, entity_id: str, value: Any) -> None:
        self._items[entity_id] = value
        self._items.move_to_end(entity_id)
        while len(self._items) > self._limit:
            self._items.popitem(last=False)

    def invalidate(self, entity_id: str) -> None:
        self._items.pop(entity_id, None)

    def invalidate_domain(self, domain: str) -> None:
        prefix = f"{domain}."
        for entity_id in [e for e in self._items if e.startswith(prefix)]:
            self._items.pop(entity_id, None)

    def clear(self) -> None:
        self._items.clear()

    def __contains__(self, entity_id: str) -> bool:
        return entity_id in self._items

    def __len__(self) -> int:
        return len(self._items)


def relevant_change(old, new) -> bool:
    """האם השינוי במצב משנה את היכולות — ולא רק את הערך הנוכחי."""
    if old is None or new is None:
        return True
    was_down = old.state in ("unavailable", "unknown")
    is_down = new.state in ("unavailable", "unknown")
    if was_down != is_down:
        # בחזרה לזמינות נטענים המאפיינים הדינמיים לראשונה.
        return True
    before, after = old.attributes, new.attributes
    keys = set(before) | set(after)
    for key in keys:
        if key in _RELEVANT or key.endswith(_RELEVANT_SUFFIX) or key.startswith(("min_", "max_")):
            if before.get(key) != after.get(key):
                return True
    return False


def cache(hass: HomeAssistant) -> CapabilityCache | None:
    return hass.data.get(_CACHE_KEY)


@callback
def async_setup_cache(hass: HomeAssistant):
    """מטמון אחד לכל ההתקנה, ומאזינים שמנקים אותו. מחזיר פונקציית ניתוק."""
    existing = hass.data.get(_CACHE_KEY)
    if existing is not None:
        return lambda: None

    store = CapabilityCache()
    hass.data[_CACHE_KEY] = store

    from homeassistant.const import (  # noqa: PLC0415
        EVENT_SERVICE_REGISTERED,
        EVENT_SERVICE_REMOVED,
        EVENT_STATE_CHANGED,
    )

    @callback
    def _state(event) -> None:
        entity_id = event.data.get("entity_id", "")
        if entity_id in store and relevant_change(
            event.data.get("old_state"), event.data.get("new_state")
        ):
            store.invalidate(entity_id)

    @callback
    def _service(event) -> None:
        store.invalidate_domain(str(event.data.get("domain", "")))
        # פעולות של `homeassistant` חלות על קבוצות.
        if event.data.get("domain") == GROUP_ACTION_DOMAIN:
            store.invalidate_domain("group")

    @callback
    def _entity_registry(event) -> None:
        store.invalidate(str(event.data.get("entity_id", "")))
        if old := event.data.get("old_entity_id"):
            store.invalidate(str(old))

    @callback
    def _device_registry(_event) -> None:
        # התקן שהושבת או שהשתנה — אין דרך זולה לדעת אילו ישויות שלו
        # במטמון בלי לעבור על הרישום. נדיר מספיק כדי לנקות הכול.
        store.clear()

    unsubs = [
        hass.bus.async_listen(EVENT_STATE_CHANGED, _state),
        hass.bus.async_listen(EVENT_SERVICE_REGISTERED, _service),
        hass.bus.async_listen(EVENT_SERVICE_REMOVED, _service),
        hass.bus.async_listen("entity_registry_updated", _entity_registry),
        hass.bus.async_listen("device_registry_updated", _device_registry),
    ]

    def _unsub() -> None:
        for unsub in unsubs:
            unsub()
        hass.data.pop(_CACHE_KEY, None)

    return _unsub
