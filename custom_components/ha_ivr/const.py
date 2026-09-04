"""קבועים."""

from typing import Final

# דומיין הליבה. אין לו כרטיס בממשק ואין לו רשומת הגדרה — הוא
# תלות של אינטגרציות הספקים ונטען אוטומטית איתן.
DOMAIN: Final = "ha_ivr"

SERVICE_SEND_CALL: Final = "send_call"

# מפתח ב-hass.data שמחזיק את ישויות הלוויין לפי מזהה רשומה.
# הגשר צריך למצוא את הישות של הרשומה שהטוקן שייך לה, והישות
# נוצרת בפלטפורמה של הספק — hass.data הוא המפגש ביניהם.
SATELLITES: Final = "ha_ivr_satellites"

# התראה ששוגרה וממתינה לשיחה שתחזור. ראו `announce.py`.
PENDING_ANNOUNCE: Final = "ha_ivr_pending_announce"

# יומן ההתראות האחרונות שנשלחו, להקראה בשלוחת "התראות אחרונות".
# בזיכרון בלבד — התראות הן זמניות, ואיבודן בהפעלה מחדש סביר.
ALERT_LOG: Final = "ha_ivr_alert_log"

SUBENTRY_TYPE_ITEM: Final = "menu_item"
SUBENTRY_TYPE_SUBMENU: Final = "submenu"
SUBENTRY_TYPE_GOTO: Final = "goto"
# ישות שהתפריט שלה נבנה מהיכולות שהמכשיר מדווח עליהן, במקום
# פריט ידני לכל פעולה. ראו `smart.py`.
SUBENTRY_TYPE_SMART: Final = "smart_entity"
# קבוצה: כל הישויות מסוג מסוים במרחב, בקומה או בכל הבית. אותו
# מנגנון גילוי, אלא שהיכולות הן החיתוך של כל החברים. ראו `smart.py`.
SUBENTRY_TYPE_GROUP: Final = "smart_group"
# שלוחה שמקריאה את ההתראות האחרונות שנשלחו. ראו `announce.log_alert`.
SUBENTRY_TYPE_ALERTS: Final = "alerts"

# נמען להתראה קולית. תת-רשומה ולא שדה, כדי שכל נמען יהיה ישות
# `notify` משלו ויהיה בר-בחירה בממשק, בקבוצות התראה ובבלופרינטים.
SUBENTRY_TYPE_CONTACT: Final = "contact"
CONF_PHONE: Final = "phone"
# ערוץ ההתראה לנמען: שיחה קולית, SMS או צינתוק. נגזר מהיכולת
# `NOTIFY_CHANNELS` של הדרייבר; ספק בלי היכולת שולח בקול בלבד.
CONF_CHANNEL: Final = "channel"
# טראנק יוצא לנמען יחיד, override על טראנק ברירת המחדל של הרשומה.
# מופיע רק לספק שמצהיר `SUPPORTS_TRUNK` (המרכזייה), ומשמש לשליחה
# עם זיהוי יוצא אחר. ריק = טראנק ברירת המחדל.
CONF_TRUNK: Final = "trunk"
# מספר מציג (caller ID) לשיחה היוצאת. מופיע רק לספק שמצהיר
# `SUPPORTS_CALLER_ID`, וחייב להיות זיהוי שהספק מאשר. ריק = הזיהוי
# שהספק/הטראנק נותן כברירת מחדל.
CONF_CALLER_ID: Final = "caller_id"
# כמה פעמים לחזור ולחייג אם לא ענו. 0 = פעם אחת בלבד, כמו אצל שאר
# הספקים. מופיע רק לספק שמצהיר `SUPPORTS_RETRIES`.
CONF_RETRIES: Final = "retries"

CONF_TARGET_ENTITY: Final = "entity_id"
CONF_ACTION: Final = "action"
CONF_ACTION_DATA: Final = "action_data"
# התוכנית של ישות חכמה: היכולות שנבחרו, והמספר שננעל לכל אחת.
# נשמרת ואינה מחושבת מחדש — מספר שזז הוא תקלת בטיחות בטלפון.
CONF_PLAN: Final = "plan"
# יעד הקבוצה. סוג הישות הוא חלק מהיעד ולא קישוט: "אורות במטבח"
# ולא "הכל במטבח", כדי שמנעול שישויך למרחב לא ייכנס לתפריט
# הטלפוני בלי שאיש החליט על כך.
CONF_DOMAIN: Final = "target_domain"
CONF_AREA: Final = "target_area"
CONF_FLOOR: Final = "target_floor"
# תווית כיעד. `async_match_targets` אינו מכיר תוויות, ולכן הסינון
# לפיהן נעשה בנפרד — ראו `smart.match_entities`.
CONF_LABEL_TARGET: Final = "target_label"
CONF_CONFIRM_RISKY: Final = "confirm_risky"
CONF_MENU_PATH: Final = "menu_path"
CONF_LABEL: Final = "label"
CONF_INTRO: Final = "intro"

# מעבר לשלוחה אחרת אצל הספק, למשל שלוחת הסטרימינג של העוזר.
CONF_GOTO_TARGET: Final = "goto_target"

# ספרות בלבד. כוכבית וסולמית שמורות לניווט (ראו model.KEY_BACK).
MENU_DIGITS: Final = "123456789"
MENU_MAX_DEPTH: Final = 4

# --- מדיניות דומיינים ---
BLOCKED_DOMAINS: Final = frozenset(
    {"hassio", "backup", "recorder", "system_log", "persistent_notification"}
)
CONFIRM_DOMAINS: Final = frozenset(
    {"shell_command", "python_script", "homeassistant"}
)

# --- אותות ואירועים ---
# האות מזוהה לפי רשומה: הנתיב "1/2" קיים אצל כל הספקים, ואות
# גלובלי היה מעדכן את החיישנים של כולם בבחירה אחת.
def signal_call_received(entry_id: str) -> str:
    return f"ha_ivr_call_received_{entry_id}"


# האירוע בשם אחד לכל הספקים; הספק מגיע בתוך המטען.
EVENT_CALL_RECEIVED: Final = "ha_ivr_call_received"

# --- תזמונים ---
# קריאת שירות שנתקעת חוסמת את הבקשה עד שהספק מוותר, ולכן יש לה
# תקרה נפרדת מההמתנה לשינוי מצב.
SERVICE_CALL_TIMEOUT: Final = 8.0
STATE_CHANGE_TIMEOUT: Final = 3.0

# כמה פעמים להשמיע תפריט בלי הקשה לפני ניתוק.
MENU_MAX_REPEATS: Final = 3

# כמה שיחות עוזר קולי במקביל, כלומר כמה ישויות לוויין לרשומה.
# קבוע בקוד ולא שדה בטופס: ישויות נוצרות בטעינת הפלטפורמה, ושדה
# היה מחייב טעינה מחדש בכל שינוי ומשאיר ישות יתומה במרשם בכל
# הקטנה.
#
# זו גם התקרה מול ניצול לרעה: מי שהשיג את הטוקן יכול לפתוח
# חיבורים ולשרוף תקציב STT ומודל. מעבר למספר הזה החיבור נדחה.
STREAM_LINES: Final = 2

# תקרת אורך שיחה בדקות. שיחה שנשארת פתוחה מחזיקה קו, ולכן
# צריכה סוף גם אם אף אחד לא מדבר.
DEFAULT_MAX_CALL_MINUTES: Final = 15

# ביטויים שסוגרים את ערוץ הסטרימינג. היעד שאליו המתקשר מועבר
# נקבע בשדה "שלוחה למעבר בסיום" בהגדרות השלוחה אצל הספק.
DEFAULT_EXIT_PHRASES: Final = "חזור לתפריט, תפריט ראשי, חזרה לתפריט, להתראות, ביי"

# מקשים שסוגרים את ערוץ הסטרימינג, כמו הכוכבית בתפריט. מהיר
# ואמין יותר ממילה: אינו תלוי בזיהוי דיבור ואינו נכשל על רעש.
DEFAULT_EXIT_KEYS: Final = "#"

# קצב הדגימה המבוקש, אצל ספק שמאפשר לבחור.
CONF_STREAM_RATE: Final = "stream_rate"

# נתיב ה-IVR שאליו מועבר המתקשר ביציאה מהעוזר.
# `transfer_extension` מקבל נתיב בעץ השלוחות ("/2", "/sales") ולא
# מזהה שלוחה כמו `goTo`. ריק = סגירת הסוקט והסתמכות על endGoTo.
CONF_STREAM_RETURN_PATH: Final = "stream_return_path"
DEFAULT_STREAM_RETURN_PATH: Final = "/"

# שמות מדוברים לפי דומיין, למזהים אטומים כמו light.0x00124b0022
# שאחרת מוקראים כרצף תווים חסר משמעות.
DOMAIN_NAMES: Final = {
    "climate": "המזגן",
    "light": "התאורה",
    "switch": "המתג",
    "lock": "המנעול",
    "cover": "התריס",
    "fan": "המאוורר",
    "sensor": "החיישן",
    "binary_sensor": "החיישן",
    "media_player": "הנגן",
    "vacuum": "שואב האבק",
    "water_heater": "דוד המים",
    "scene": "הסצנה",
    "script": "התסריט",
    "automation": "האוטומציה",
    "button": "הכפתור",
    "input_boolean": "מתג עזר",
    "input_select": "בורר עזר",
    "input_number": "מספר עזר",
    "input_text": "טקסט עזר",
    "select": "בורר אפשרויות",
    "number": "המספר",
    "text": "הטקסט",
    "humidifier": "המאדה",
    "siren": "הסירנה",
    "valve": "השסתום",
    "lawn_mower": "מכסחת הדשא",
    "remote": "השלט",
    "camera": "המצלמה",
    "calendar": "היומן",
    "todo": "רשימת המשימות",
    "weather": "מזג האוויר",
    "person": "האדם",
    "device_tracker": "מאתר המכשיר",
    "alarm_control_panel": "מערכת האזעקה",
    "update": "העדכון",
    "event": "האירוע",
    "image": "התמונה",
    "notify": "ההתראה",
    "conversation": "השיחה",
    "assist_satellite": "לוויין העוזר",
    "ai_task": "משימת הבינה",
    "stt": "זיהוי הדיבור",
    "tts": "ההקראה",
    "vacuum": "שואב האבק",
}
