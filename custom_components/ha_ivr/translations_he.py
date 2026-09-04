"""תרגום לעברית של שמות פעולות, שדות וערכים.

Home Assistant מחזיר בצד השרת את המפתחות הטכניים בלבד. התרגום שמוצג
במסך האוטומציות נעשה בצד הלקוח, מקובצי התרגום של הממשק, ולכן אין דרך
לקבל אותו מהשרת. המילונים כאן מספקים תרגום למה שנמצא בשימוש נפוץ.

מפתח שאינו מופיע כאן מוצג בשמו הטכני, וזו נפילה חזרה תקינה.
"""

from __future__ import annotations

from typing import Final

# --- שמות פעולות ---
ACTION_NAMES: Final[dict[str, str]] = {
    # כללי
    "turn_on": "הדלקה",
    "turn_off": "כיבוי",
    "toggle": "החלפת מצב",
    "reload": "טעינה מחדש",
    "press": "לחיצה",
    "trigger": "הפעלה",
    # תריסים
    "open_cover": "פתיחת תריס",
    "close_cover": "סגירת תריס",
    "stop_cover": "עצירת תריס",
    "set_cover_position": "כוונון מיקום תריס",
    "open_cover_tilt": "פתיחת הטיה",
    "close_cover_tilt": "סגירת הטיה",
    "set_cover_tilt_position": "כוונון הטיה",
    # מנעולים
    "lock": "נעילה",
    "unlock": "פתיחת נעילה",
    "open": "פתיחה",
    # מיזוג
    "set_temperature": "כוונון טמפרטורה",
    "set_hvac_mode": "מצב מיזוג",
    "set_fan_mode": "מצב מאוורר",
    "set_preset_mode": "מצב מוגדר מראש",
    "set_swing_mode": "מצב סיבוב",
    "set_humidity": "כוונון לחות",
    "set_aux_heat": "חימום עזר",
    # מאווררים
    "set_percentage": "כוונון עוצמה",
    "set_direction": "כיוון סיבוב",
    "oscillate": "תנועה מצד לצד",
    # מדיה
    "media_play": "נגינה",
    "media_pause": "השהיה",
    "media_stop": "עצירה",
    "media_next_track": "הרצועה הבאה",
    "media_previous_track": "הרצועה הקודמת",
    "volume_set": "כוונון עוצמת קול",
    "volume_up": "הגברת עוצמה",
    "volume_down": "הנמכת עוצמה",
    "volume_mute": "השתקה",
    "select_source": "בחירת מקור",
    "select_sound_mode": "מצב שמע",
    # שואב אבק
    "start": "הפעלה",
    "pause": "השהיה",
    "stop": "עצירה",
    "return_to_base": "חזרה לעמדת טעינה",
    "locate": "איתור",
    "clean_spot": "ניקוי נקודתי",
    "set_fan_speed": "עוצמת שאיבה",
    # ערכים ובוררים
    "select_option": "בחירת אפשרות",
    "select_next": "האפשרות הבאה",
    "select_previous": "האפשרות הקודמת",
    "set_value": "כוונון ערך",
    "increment": "הגדלה",
    "decrement": "הקטנה",
    # מים וסירנה
    "set_operation_mode": "מצב הפעלה",
    "set_away_mode": "מצב יציאה",
}

# --- שמות שדות ---
FIELD_NAMES: Final[dict[str, str]] = {
    "temperature": "טמפרטורה",
    "target_temp_high": "טמפרטורה עליונה",
    "target_temp_low": "טמפרטורה תחתונה",
    "hvac_mode": "מצב מיזוג",
    "fan_mode": "מצב מאוורר",
    "preset_mode": "מצב מוגדר מראש",
    "swing_mode": "מצב סיבוב",
    "humidity": "לחות",
    "position": "מיקום",
    "tilt_position": "מיקום הטיה",
    "brightness": "בהירות",
    "brightness_pct": "בהירות באחוזים",
    "color_temp": "גוון לבן",
    "color_name": "צבע",
    "rgb_color": "צבע",
    "effect": "אפקט",
    "transition": "משך מעבר",
    "flash": "הבהוב",
    "percentage": "אחוז",
    "direction": "כיוון",
    "oscillating": "תנועה מצד לצד",
    "volume_level": "עוצמת קול",
    "is_volume_muted": "מושתק",
    "source": "מקור",
    "sound_mode": "מצב שמע",
    "media_content_id": "מזהה תוכן",
    "media_content_type": "סוג תוכן",
    "option": "אפשרות",
    "value": "ערך",
    "fan_speed": "עוצמת שאיבה",
    "operation_mode": "מצב הפעלה",
    "away_mode": "מצב יציאה",
    "aux_heat": "חימום עזר",
    "message": "הודעה",
    "duration": "משך",
    "tone": "צליל",
}

# --- ערכי בחירה נפוצים ---
OPTION_NAMES: Final[dict[str, str]] = {
    # מצבי מיזוג
    "off": "כבוי",
    "on": "דולק",
    "auto": "אוטומטי",
    "cool": "קירור",
    "heat": "חימום",
    "heat_cool": "חימום וקירור",
    "dry": "ייבוש",
    "fan_only": "אוורור בלבד",
    # עוצמות
    "low": "נמוך",
    "medium": "בינוני",
    "high": "גבוה",
    "middle": "אמצעי",
    "focus": "ממוקד",
    "diffuse": "מפוזר",
    # מצבים מוגדרים מראש
    "none": "ללא",
    "eco": "חסכוני",
    "away": "יציאה",
    "boost": "מוגבר",
    "comfort": "נוחות",
    "home": "בית",
    "sleep": "שינה",
    "activity": "פעילות",
    "medium low": "בינוני נמוך",
    "medium_low": "בינוני נמוך",
    "medium high": "בינוני גבוה",
    "medium_high": "בינוני גבוה",
    "quiet": "שקט",
    "silent": "שקט",
    "turbo": "מוגבר",
    "strong": "חזק",
    "max": "מרבי",
    "min": "מזערי",
    # סיבוב
    "vertical": "אנכי",
    "horizontal": "אופקי",
    "both": "שניהם",
    "default": "ברירת מחדל",
    "swing": "סיבוב",
    "full_swing": "סיבוב מלא",
    "fixed": "קבוע",
    "fixed_upper": "קבוע למעלה",
    "fixed_upper_middle": "קבוע למעלה באמצע",
    "fixed_middle": "קבוע באמצע",
    "fixed_lower_middle": "קבוע למטה באמצע",
    "fixed_lower": "קבוע למטה",
    "swing_upper": "סיבוב למעלה",
    "swing_upper_middle": "סיבוב למעלה באמצע",
    "swing_middle": "סיבוב באמצע",
    "swing_lower_middle": "סיבוב למטה באמצע",
    "swing_lower": "סיבוב למטה",
    # כיוון
    "forward": "קדימה",
    "reverse": "אחורה",
    # הבהוב
    "short": "קצר",
    "long": "ארוך",
}


# יחידות שנאמרות אחרי ערך מספרי, כדי שההקראה לא תישמע קטועה.
FIELD_UNITS: Final[dict[str, str]] = {
    "temperature": "מעלות",
    "target_temp_high": "מעלות",
    "target_temp_low": "מעלות",
    "humidity": "אחוז",
    "brightness_pct": "אחוז",
    "percentage": "אחוז",
    "position": "אחוז",
    "tilt_position": "אחוז",
    "volume_level": "אחוז",
    "transition": "שניות",
}


# יחידות המידה כפי שהן מגיעות ב-unit_of_measurement של הישות.
# בלי המילון הזה הסימן נשלח כמו שהוא להקראה: "kWh" נשמע כאותיות
# באנגלית, ו-"µg/m³" הוא רצף תווים שאיש אינו יודע מה ימות עושה
# איתו. המפתחות באותיות קטנות — ההשוואה מנרמלת.
UNIT_NAMES: Final[dict[str, str]] = {
    "°c": "מעלות", "c": "מעלות", "℃": "מעלות",
    "°f": "מעלות פרנהייט", "f": "מעלות פרנהייט", "℉": "מעלות פרנהייט",
    "°": "מעלות", "k": "קלווין",
    "%": "אחוזים",
    "w": "ואט", "kw": "קילוואט", "mw": "מגהוואט",
    "wh": "ואט שעה", "kwh": "קילוואט שעה", "mwh": "מגהוואט שעה",
    "v": "וולט", "mv": "מיליוולט", "a": "אמפר", "ma": "מיליאמפר",
    "va": "וולט אמפר", "hz": "הרץ", "ohm": "אוהם",
    "pa": "פסקל", "hpa": "הקטופסקל", "kpa": "קילופסקל",
    "bar": "בר", "mbar": "מילי בר", "psi": "פי אס איי",
    "mm": "מילימטרים", "cm": "סנטימטרים", "m": "מטרים", "km": "קילומטרים",
    "mi": "מיילים", "ft": "רגל", "in": "אינץ",
    "km/h": "קילומטר לשעה", "m/s": "מטר לשנייה", "mph": "מייל לשעה",
    "l": "ליטר", "ml": "מיליליטר", "m³": "מטר מעוקב", "m3": "מטר מעוקב",
    "l/min": "ליטר לדקה",
    "ppm": "חלקיקים למיליון", "ppb": "חלקיקים למיליארד",
    "µg/m³": "מיקרוגרם למטר מעוקב", "mg/m³": "מיליגרם למטר מעוקב",
    "db": "דציבל", "dba": "דציבל", "lx": "לוקס", "lm": "לומן",
    "s": "שניות", "sec": "שניות", "min": "דקות", "h": "שעות",
    "d": "ימים", "ms": "מילישניות",
    "b": "בייט", "kb": "קילובייט", "mb": "מגהבייט",
    "gb": "גיגהבייט", "tb": "טרהבייט",
    "kbit/s": "קילוביט לשנייה", "mbit/s": "מגהביט לשנייה",
    "kb/s": "קילובייט לשנייה", "mb/s": "מגהבייט לשנייה",
    "steps": "צעדים", "kg": "קילוגרם", "g": "גרם", "lb": "ליברות",
}


def translate_unit(unit: str) -> str:
    """יחידת המידה בעברית, או ריק אם אינה מוכרת.

    ריק ולא הסימן הגולמי: בימות כל תו שאינו אות או ספרה הוא סיכון,
    ושתיקה עדיפה על הקראת סימן. מי שקורא רושם ליומן את מה שלא
    תורגם, כדי שהמילון יגדל לפי מה שבאמת מופיע אצל המשתמש.
    """
    return UNIT_NAMES.get(str(unit).strip().lower(), "")


def field_unit(field: str) -> str:
    """היחידה שתיאמר אחרי ערך מספרי של השדה, אם יש."""
    return FIELD_UNITS.get(field, "")


def translate_action(action: str) -> str:
    """שם הפעולה בעברית, או השם הטכני אם אין תרגום."""
    return ACTION_NAMES.get(action, action)


def translate_field(field: str) -> str:
    """שם השדה בעברית, או השם הטכני אם אין תרגום."""
    return FIELD_NAMES.get(field, field)


def translate_option(option: str) -> str:
    """ערך בחירה בעברית, או הערך המקורי אם אין תרגום.

    מכשירים מדווחים על אותו ערך בשתי צורות — `medium low` ו-
    `medium_low` — ולכן גם הקו התחתון וגם הרווח מנוסים. ערך
    מורכב שאין לו תרגום שלם מתורגם חלק-חלק, כך ש-`fan_high`
    יוצא "מאוורר גבוה" ולא נשאר באנגלית באמצע התפריט.
    """
    raw = str(option)
    lowered = raw.lower().strip()
    if found := OPTION_NAMES.get(lowered):
        return found
    swapped = lowered.replace("_", " ") if "_" in lowered else lowered.replace(" ", "_")
    if found := OPTION_NAMES.get(swapped):
        return found

    parts = lowered.replace("_", " ").split()
    if len(parts) > 1:
        translated = [OPTION_NAMES.get(part, part) for part in parts]
        # רק אם כל חלק תורגם. תערובת של עברית ואנגלית באותו פריט
        # נשמעת גרוע יותר מאנגלית עקבית.
        if all(t != p for t, p in zip(translated, parts)):
            return " ".join(translated)
    return raw
