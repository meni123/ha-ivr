"""מדיניות ההרשאה לפעולות מרחוק.

מרכז במקום אחד את ההחלטה אילו פעולות מותרות, אילו חסומות ואילו
דורשות אישור. כל שאר הקוד, ה-View, הכפתור והטופס, נשען על הפונקציות
כאן, כדי שלא תיווצר סתירה בין המקומות השונים.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, SupportsResponse

from .const import BLOCKED_DOMAINS, CONFIRM_DOMAINS

# פעולות שאין טעם להציע אותן כפעולת שלוחה: תחזוקה פנימית, עריכת
# הגדרות, ותזמור של עוזר קולי. פעולות שרק מחזירות מידע אינן כאן:
# הן מסוננות לפי `SupportsResponse.ONLY` (ראו `available_actions`).
_NON_ACTIONABLE = frozenset(
    {
        "reload",
        "reload_config_entry",
        "reload_core_config",
        "set_location",
        "check_config",
        "save_persistent_states",
        # יצירה ומחיקה של הגדרות (סצנה חדשה, התראה מתמשכת).
        "create",
        "delete",
        "dismiss",
        "dismiss_all",
        # דיווח מיקום מאפליקציה, לא שליטה במכשיר.
        "see",
        # ה-IVR עצמו הוא המתקשר, ולכן הכרזה ללוויין באמצע שיחה חסרת
        # פשר.
        "announce",
        "start_conversation",
        "ask_question",
    }
)

# דומיינים שקבוצה שלהם חסרת פשר ומסוכנת. בתאורה "הכל כבוי" הוא
# פעולה קוהרנטית; בכפתורים אין שום דבר משותף בין החברים, ולחיצה
# על כולם בבת אחת עלולה להפעיל גם "Factory reset" וגם
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
        # משימת בינה דורשת הנחיה בטקסט, ומצלמה מציעה צילום לקובץ —
        # אין בהן דבר שמתקשר מפעיל יחד על כמה. כישות בודדת זמינות.
        "ai_task",
        "camera",
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
    domain_services = hass.services.async_services_for_domain(domain)
    return sorted(
        name
        for name in domain_services
        if name not in _NON_ACTIONABLE and not _read_only(hass, domain, name)
    )


def _read_only(hass: HomeAssistant, domain: str, action: str) -> bool:
    """פעולה שרק מחזירה מידע (`get_forecasts`, `get_items`).

    Home Assistant דוחה קריאה כזו בלי `return_response`, ולמתקשר
    אין דרך לשמוע את התשובה. ההכרזה היא של מי שרשם את הפעולה, ולכן
    היא חלה גם על פעולות של אינטגרציות שאיש לא מכיר כאן מראש.
    """
    return hass.services.supports_response(domain, action) == SupportsResponse.ONLY
