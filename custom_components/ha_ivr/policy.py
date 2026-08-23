"""מדיניות ההרשאה לפעולות מרחוק.

מרכז במקום אחד את ההחלטה אילו פעולות מותרות, אילו חסומות ואילו
דורשות אישור. כל שאר הקוד, ה-View, הכפתור והטופס, נשען על הפונקציות
כאן, כדי שלא תיווצר סתירה בין המקומות השונים.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import BLOCKED_DOMAINS, CONFIRM_DOMAINS

# פעולות שאינן משנות מצב, ולכן אין טעם להציע אותן כפעולת שלוחה.
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
    }
)


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
