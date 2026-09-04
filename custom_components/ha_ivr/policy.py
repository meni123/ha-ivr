"""מדיניות ההרשאה לפעולות מרחוק.

מרכז במקום אחד את ההחלטה אילו פעולות מותרות, אילו חסומות ואילו
דורשות אישור. כל שאר הקוד, ה-View, הכפתור והטופס, נשען על הפונקציות
כאן, כדי שלא תיווצר סתירה בין המקומות השונים.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import BLOCKED_DOMAINS, CONFIRM_DOMAINS

# פעולות שאין טעם להציע אותן כפעולת שלוחה: כאלה שאינן משנות מצב,
# כאלה שרק כותבות קובץ, וכאלה שהן תחזוקה פנימית. משותף לכולן
# שמתקשר שלוחץ עליהן בטלפון אינו יכול לדעת מה קרה.
_NON_ACTIONABLE = frozenset(
    {
        "reload",
        "reload_config_entry",
        "reload_core_config",
        "set_location",
        "check_config",
        "save_persistent_states",
        "create",
        "dismiss",
        "dismiss_all",
        # דיווח מיקום מאפליקציה, לא שליטה במכשיר.
        "see",
        # כותבות קובץ לדיסק. אין לכך ביטוי בשיחה.
        "snapshot",
        "record",
        # שאילתות קריאה בלבד.
        "get_events",
        "get_items",
        # תחזוקה ובקרת גרסאות. התקנת עדכון מתוך תפריט טלפוני,
        # בלי לראות במה מדובר ובלי דרך לחזור, אינה פעולה שראוי
        # להציע בהקשה אחת.
        "install",
        "skip",
        "clear_skipped",
        "clear_cache",
        # תחזית היא קריאה בלבד.
        "get_forecast",
        "get_forecasts",
        # תזמור של עוזר קולי, לא שליטה במכשיר. וגם: ה-IVR עצמו
        # הוא המתקשר, ולכן הכרזה ללוויין באמצע שיחה חסרת פשר.
        "announce",
        "start_conversation",
        "ask_question",
    }
)

# דומיינים שקבוצה שלהם חסרת פשר ומסוכנת. בתאורה "הכל כבוי" הוא
# פעולה קוהרנטית; בכפתורים אין שום דבר משותף בין החברים, ולחיצה
# על כולם בבת אחת מפעילה במקרה אחד אמיתי גם "Factory reset" וגם
# "Unlatch" שפותח את דלת הכניסה. אותו נימוק לתסריט, לסצנה
# ולאוטומציה: הרצת כל האוטומציות בבית בהקשה אחת אינה בקשה שמישהו
# מתכוון אליה.
#
# הישות הבודדת נשארת זמינה להם במלואה — שם בוחרים מכשיר אחד
# ויודעים בדיוק במה מדובר.
NOT_GROUPABLE = frozenset(
    {
        "button",
        "scene",
        "script",
        "automation",
        # הבוררים מסיבה אחרת: לא סכנה אלא חוסר משמעות. בורר של
        # מכשיר הוא הגדרה שלו — "מה יעשה השקע אחרי הפסקת חשמל",
        # "רמת רישום" — ובורר עזר נוצר ידנית למטרה מסוימת. שתי
        # הקבוצות הטרוגניות מעצם טבען, וקביעת אותו ערך לכולן אינה
        # פעולה שמישהו מבקש. כישות בודדת שניהם זמינים במלואם.
        "select",
        "input_select",
        # רשימות משימות נוצרות לנושאים שונים — קניות, תזכורות,
        # תור הודעות — ואין בין חברי הקבוצה דבר משותף. מה שנשאר
        # לקבץ הוא "מחק את שהושלמו", כי הוספת פריט דורשת טקסט,
        # ומחיקה בכל הרשימות בבת אחת אינה בקשה שמישהו מתכוון אליה.
        "todo",
    }
)


def domain_is_groupable(domain: str) -> bool:
    """האם ניתן להציע את הדומיין כקבוצה."""
    return domain not in NOT_GROUPABLE


def domain_is_blocked(domain: str) -> bool:
    """האם הדומיין חסום לחלוטין."""
    return domain in BLOCKED_DOMAINS


def domain_needs_confirmation(domain: str) -> bool:
    """האם הדומיין דורש אישור מפורש מהמשתמש."""
    return domain in CONFIRM_DOMAINS


def action_allowed(hass: HomeAssistant, domain: str, action: str) -> bool:
    """האם צירוף הדומיין והפעולה מותר להפעלה בכלל.

    דומיין חסום נדחה תמיד. פעולה שאינה קיימת ב-Home Assistant נדחית.
    דומיין שדורש אישור נחשב מותר כאן; בדיקת ההסכמה עצמה נעשית בנפרד,
    כדי שהודעת השגיאה למשתמש תהיה מדויקת.
    """
    if domain_is_blocked(domain):
        return False
    # has_service קיים ויציב בכל גרסאות Home Assistant.
    return hass.services.has_service(domain, action)


def available_actions(hass: HomeAssistant, domain: str) -> list[str]:
    """הפעולות שניתן להציע עבור דומיין, לפי מה ש-Home Assistant מכיר.

    זו הדרך הרשמית: במקום רשימה קבועה, שואלים את המערכת אילו פעולות
    הדומיין חושף בפועל. דומיין חסום מחזיר רשימה ריקה.
    """
    if domain_is_blocked(domain):
        return []
    # async_services מחזיר מילון של כל הדומיינים והשירותים שלהם.
    # זו הדרך היציבה לשאול אילו פעולות דומיין חושף בפועל.
    domain_services = hass.services.async_services().get(domain, {})
    actions = [name for name in domain_services if name not in _NON_ACTIONABLE]
    return sorted(actions)
