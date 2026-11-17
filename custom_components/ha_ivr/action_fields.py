"""שליפת תיאורי הפעולות מ-Home Assistant ובניית שדות טופס מהם.

Home Assistant מתאר כל פעולה יחד עם השדות שלה והבורר המתאים לכל שדה,
וזה בדיוק המידע שמסך האוטומציות משתמש בו. כאן נשלף אותו מידע ומומר
לשדות של טופס ההגדרה, בלי רשימות מקומיות לתחזק.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    selector as ha_selector,
)
from homeassistant.helpers.service import async_get_all_descriptions

from .capabilities import entity_info, entity_options, field_applies
from .translations_he import translate_action, translate_field, translate_option

_LOGGER = logging.getLogger(__name__)

# שדות שאינם רלוונטיים לשלוחה: המכשיר כבר נבחר בשלב קודם.
IGNORED_FIELDS = frozenset({"entity_id", "device_id", "area_id", "target", "label_id"})

# שדה קוד אינו מוצג בטופס ואינו נשמר לעולם. הוא נאסף בהקשה בשיחה.
SECRET_FIELDS = frozenset({"code"})

# שדות שהטווח שלהם נקבע לפי הישות ולא לפי התיאור הגנרי. תיאור
# `climate.set_temperature` מכריז על 0 עד 250 — הטווח התיאורטי של
# השירות — בעוד שהמזגן עצמו מדווח 16 עד 30. ההפרש קריטי: רק טווח
# אמיתי יודע כמה ספרות המתקשר עומד להקיש.
ENTITY_RANGE_ATTRIBUTES: dict[str, tuple[str, str]] = {
    "temperature": ("min_temp", "max_temp"),
    "target_temp_high": ("min_temp", "max_temp"),
    "target_temp_low": ("min_temp", "max_temp"),
    "humidity": ("min_humidity", "max_humidity"),
}


# ישויות שהערך שלהן מספר בטווח שהן עצמן מדווחות.
NUMBER_DOMAINS = frozenset({"number", "input_number"})


def entity_number_range(
    hass: HomeAssistant, entity_id: str, field: str, config: dict[str, Any] | None
) -> tuple[float | None, float | None]:
    """הטווח של שדה מספרי, מהישות אם היא מדווחת עליו.

    מעדיף את מה שהמכשיר מדווח על פני התיאור הגנרי של השירות.
    נופל בחזרה לתיאור, ולבסוף ל-None כשאין טווח כלל — שדה בלי
    גבולות אינו ניתן להקראה כתפריט.
    """
    config = config or {}
    low = config.get("min")
    high = config.get("max")

    if attributes := ENTITY_RANGE_ATTRIBUTES.get(field):
        # לשדות האלה הטווח הגנרי חסר משמעות — `set_temperature`
        # מכריז 0 עד 250, שהוא הטווח של השירות ולא של המזגן. אם
        # המכשיר אינו מדווח על שלו, אין טווח: עדיף לא להציע את
        # הפעולה מאשר להציע רשימה שאיש לא ביקש.
        state = hass.states.get(entity_id)
        low_attr = state.attributes.get(attributes[0]) if state else None
        high_attr = state.attributes.get(attributes[1]) if state else None
        if low_attr is None or high_attr is None:
            return None, None
        low, high = low_attr, high_attr

    try:
        return (
            None if low is None else float(low),
            None if high is None else float(high),
        )
    except (TypeError, ValueError):
        return None, None



async def async_action_fields(
    hass: HomeAssistant, domain: str, action: str, entity_id: str = ""
) -> dict[str, dict[str, Any]]:
    """החזרת תיאורי השדות של פעולה, ללא שדות היעד.

    מחזיר מילון של שם השדה ומאפייניו. מילון ריק פירושו שהפעולה
    אינה דורשת פרמטרים ואפשר להפעילה כמות שהיא.

    כאשר מועבר מזהה ישות, רשימות הבחירה מושלמות ממאפייני הישות,
    כך שיוצגו רק האפשרויות שהמכשיר הספציפי תומך בהן.
    """
    try:
        descriptions = await async_get_all_descriptions(hass)
    except Exception as err:  # noqa: BLE001 - כשל כאן לא יפיל את הטופס
        _LOGGER.debug("Could not load action descriptions: %s", err)
        return {}

    description = descriptions.get(domain, {}).get(action)
    if not isinstance(description, dict):
        return {}


    info = entity_info(hass, entity_id) if entity_id else None
    fields: dict[str, dict[str, Any]] = {}
    for name, spec in _flatten_fields(description.get("fields", {})).items():
        if name in IGNORED_FIELDS or not isinstance(spec, dict):
            continue
        # מסנן השדה של `services.yaml`: שדה אפקט רק לנורה עם אפקטים,
        # שדה מיקום רק לתריס עם מיקום — כמו בטופס של HA.
        if not field_applies(spec, info):
            continue
        fields[name] = spec

    if entity_id:
        fields = enrich_with_entity_options(hass, entity_id, fields)
    return fields


def _flatten_fields(raw: Any) -> dict[str, Any]:
    """פירוק שדות המקובצים בקטעים מתקפלים למבנה שטוח.

    Home Assistant מאפשר לקבץ שדות בקטעים לצורכי תצוגה בלבד, ונתוני
    הקריאה נשארים שטוחים. לכן הקיבוץ מפורק כאן.
    """
    result: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return result

    for name, spec in raw.items():
        if isinstance(spec, dict) and "fields" in spec and "selector" not in spec:
            result.update(_flatten_fields(spec["fields"]))
        else:
            result[name] = spec
    return result


def field_is_supported(spec: dict[str, Any]) -> bool:
    """האם ניתן להציג את השדה בטופס ההגדרה.

    כל בורר של Home Assistant מוצג בטופס כמו במסך האוטומציות. היוצא
    מן הכלל: בורר בחירה בלי אפשרויות, כשהן תלויות בישות שאינה מדווחת
    עליהן — רשימה ריקה אינה שדה.
    """
    selector = spec.get("selector")
    if not isinstance(selector, dict) or not selector:
        return False
    if "select" in selector:
        config = selector.get("select") or {}
        return bool(config.get("options"))
    return True


def action_is_usable(fields: dict[str, dict[str, Any]]) -> bool:
    """האם ניתן להציע את הפעולה בבורר.

    פעולה שימושית אם אין לה שדות חובה, או שכל שדות החובה שלה ניתנים
    להצגה. פעולה שיש לה שדה חובה מסוג שאיננו תומכים בו מסוננת, כדי
    שלא נציע למשתמש פעולה שתיכשל בהפעלה.
    """
    for spec in fields.values():
        if spec.get("required") and not field_is_supported(spec):
            return False
    return True


def build_field_selector(spec: dict[str, Any]) -> Any:
    """המרת תיאור שדה של Home Assistant לבורר של טופס ההגדרה."""
    selector = spec.get("selector") or {}

    if "number" in selector:
        config = selector["number"] or {}
        kwargs: dict[str, Any] = {}
        if (minimum := config.get("min")) is not None:
            kwargs["min"] = float(minimum)
        if (maximum := config.get("max")) is not None:
            kwargs["max"] = float(maximum)
        if (step := config.get("step")) is not None and step != "any":
            kwargs["step"] = float(step)
        if unit := config.get("unit_of_measurement"):
            kwargs["unit_of_measurement"] = str(unit)
        # תיבת מספר ולא מחוון, כדי שערכים מדויקים יהיו קלים להזנה.
        kwargs["mode"] = NumberSelectorMode.BOX
        return NumberSelector(NumberSelectorConfig(**kwargs))

    if "select" in selector:
        config = selector["select"] or {}
        options: list[SelectOptionDict] = []
        for option in config.get("options", []):
            if isinstance(option, str):
                options.append(
                    SelectOptionDict(value=option, label=translate_option(option))
                )
            elif isinstance(option, dict):
                value = str(option.get("value", ""))
                # תווית שכבר תורגמה בשלב ההעשרה נשמרת כמות שהיא.
                label = option.get("label")
                options.append(
                    SelectOptionDict(
                        value=value,
                        label=str(label) if label else translate_option(value),
                    )
                )
        return SelectSelector(
            SelectSelectorConfig(
                options=options,
                mode=SelectSelectorMode.DROPDOWN,
                custom_value=bool(config.get("custom_value", False)),
            )
        )

    if "boolean" in selector:
        return BooleanSelector()

    # שאר הבוררים (שעה, צבע, משך, מדיה, אובייקט) כמו שהם, בבורר של HA.
    try:
        return ha_selector(selector)
    except (vol.Invalid, KeyError, TypeError):
        return TextSelector()


def build_fields_schema(
    fields: dict[str, dict[str, Any]], current: dict[str, Any] | None = None
) -> vol.Schema | None:
    """בניית סכמה עבור שדות הפעולה, או None אם אין מה להציג.

    מפתחות הסכמה הם התוויות המתורגמות של Home Assistant, כך שהטופס
    מוצג בעברית בלי צורך בתרגום ידני. ההמרה חזרה לשמות הטכניים
    נעשית באמצעות build_label_map.
    """
    current = current or {}
    schema_dict: dict[Any, Any] = {}

    for label, name in build_label_map(fields).items():
        spec = fields[name]

        existing = current.get(name, current.get(label))
        default = existing if existing is not None else spec.get("default")

        marker: Any
        if spec.get("required"):
            marker = (
                vol.Required(label, default=default)
                if default is not None
                else vol.Required(label)
            )
        else:
            marker = vol.Optional(label, description={"suggested_value": default})

        schema_dict[marker] = build_field_selector(spec)

    return vol.Schema(schema_dict) if schema_dict else None


def enrich_with_entity_options(
    hass: HomeAssistant, entity_id: str, fields: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """השלמת אפשרויות בחירה מתוך מאפייני הישות.

    חלק מהשדות, כמו מצב מיזוג, אינם מגיעים עם רשימת אפשרויות בתיאור
    הגנרי, משום שהיא תלויה בישות. כאן נקראת הרשימה מהישות עצמה, כך
    שיוצגו רק המצבים שהמכשיר הספציפי באמת תומך בהם. המאפיין נמצא
    לפי המפה ולפי הכלל הכללי (`<f>s`, `<f>_list`, `available_<f>s`).
    """
    state = hass.states.get(entity_id)
    if state is None:
        return fields

    attributes = dict(state.attributes)
    domain = entity_id.split(".", 1)[0]
    enriched: dict[str, dict[str, Any]] = {}
    for name, spec in fields.items():
        spec = dict(spec)
        # ערך של ישות מספר: התיאור מכריז על טקסט, אבל הישות מדווחת
        # טווח וצעד. כך `number.set_value` נאסף בהקשה כמו טמפרטורה.
        if domain in NUMBER_DOMAINS and name == "value":
            low, high = attributes.get("min"), attributes.get("max")
            if low is not None and high is not None:
                number: dict[str, Any] = {"min": low, "max": high}
                if attributes.get("step") is not None:
                    number["step"] = attributes["step"]
                spec["selector"] = {"number": number}
        values = entity_options(name, attributes)
        if values:
            translation_key = ""
            selector = spec.get("selector")
            if isinstance(selector, dict) and isinstance(selector.get("select"), dict):
                translation_key = str(selector["select"].get("translation_key") or "")
            spec["selector"] = {
                "select": {
                    "options": [
                        {
                            "value": value,
                            "label": translate_option(
                                value, domain, name, translation_key
                            ),
                        }
                        for value in values
                    ],
                    **({"translation_key": translation_key} if translation_key else {}),
                }
            }
        enriched[name] = spec

    return enriched


async def async_action_name(
    hass: HomeAssistant, domain: str, action: str
) -> str:
    """השם המתורגם של הפעולה, כפי שמוצג במסך האוטומציות.

    Home Assistant מתרגם את שמות הפעולות והשדות לשפת הממשק, ולכן
    אין צורך בתרגום מקומי.
    """
    translated = translate_action(action, domain)
    if translated != action:
        return translated
    # התיאור הגולמי (`name` ב-services.yaml) הוא באנגלית ואינו מתורגם
    # בצד השרת, ולכן אינו מוקרא. שם קריא מהמזהה עדיף על אנגלית.
    return readable(action)


def readable(ident: str) -> str:
    """מזהה טכני כטקסט: בלי קווים תחתונים, בלי הדומיין."""
    return str(ident).rsplit(".", 1)[-1].replace("_", " ").strip()


def field_label(
    name: str, spec: dict[str, Any], domain: str = "", action: str = ""
) -> str:
    """תווית השדה בעברית.

    Home Assistant מחזיר בצד השרת מפתחות טכניים בלבד, ולכן התרגום
    מגיע מהמילון המקומי. שדה שאינו מתורגם מוצג בשם שהתקבל
    מהתיאור, ולבסוף בשם הטכני.
    """
    translated = translate_field(name, domain, action)
    if translated != name:
        return translated
    label = spec.get("name")
    return str(label) if label else name


def build_label_map(fields: dict[str, dict[str, Any]]) -> dict[str, str]:
    """מיפוי מהתווית המוצגת אל שם השדה הטכני.

    תוויות השדות בטופס הגדרה נשלפות מקובץ התרגום הסטטי, ולכן שדות
    דינמיים לא יכולים לקבל תרגום משם. הפתרון הוא להשתמש בתווית
    המתורגמת של Home Assistant כמפתח השדה עצמו, משום שמפתח שאין לו
    תרגום מוצג כמות שהוא. המיפוי הזה מחזיר את הערכים לשמם הטכני
    בעת השמירה.
    """
    labels: dict[str, str] = {}
    used: set[str] = set()

    for name, spec in fields.items():
        if name in SECRET_FIELDS or not field_is_supported(spec):
            continue
        label = field_label(name, spec)
        # במקרה נדיר של שתי תוויות זהות, נשמר ייחוד לפי השם הטכני.
        if label in used:
            label = f"{label} ({name})"
        used.add(label)
        labels[label] = name

    return labels
