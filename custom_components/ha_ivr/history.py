"""חוצץ טבעתי של האירועים האחרונים, לצורכי אבחון.

N הפעולות האחרונות נשמרות בזיכרון בלבד, מוכנות להגשה דרך
`diagnostics.py` — בלי גישת מעטפת לשרת ובלי תלות בסבב הלוגים.

אין כאן כתיבה לדיסק ואין השהיה: הוספה לתור חסום היא O(1), והיא
רצה גם בנתיב החם של השיחה.

סודות מוסתרים בכניסה ולא בהגשה, כדי שערך רגיש לא ישב בזיכרון
בצורתו המלאה.

המודול הזה לא מייבא דבר מהחבילה, כדי שכל מודול יוכל לייבא אותו
בלי לסגור מעגל.
"""

from __future__ import annotations

import re
from collections import deque
from datetime import datetime, timezone
from typing import Any

# כמה אירועים לשמור. מספיק כדי לכסות שיחה שלמה עם כמה סבבי תפריט,
# ומעט מכדי להכביד על הזיכרון או על קובץ האבחון.
MAX_EVENTS = 80

# מפתחות שערכם לא נשמר לעולם. ההשוואה חסרת רישיות ולפי הכלה, כדי
# לתפוס גם `technoline_api_key` וגם `apiKey`.
_SECRET_HINTS = ("token", "apikey", "api_key", "password", "secret", "bearer")

_PHONE = re.compile(r"\b(\d{2,4})(\d{3,})(\d{3})\b")

_events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)


def _mask_phone(text: str) -> str:
    """מסתיר את אמצע המספר ומשאיר קצוות לזיהוי.

    מספר הטלפון של המתקשר הוא מידע אישי, וקובץ אבחון נועד להישלח
    הלאה. הקצוות מספיקים כדי לזהות שמדובר באותו מתקשר בין אירועים.
    """
    return _PHONE.sub(lambda m: f"{m.group(1)}{'*' * len(m.group(2))}{m.group(3)}", text)


def redact(value: Any, key: str = "") -> Any:
    """ערך בטוח לשמירה."""
    if any(hint in key.lower() for hint in _SECRET_HINTS):
        text = str(value or "")
        return f"***{text[-4:]}" if len(text) > 4 else "***"
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, key) for v in value]
    if isinstance(value, str):
        return _mask_phone(value)
    return value


def record(kind: str, **fields: Any) -> None:
    """רישום אירוע. לעולם אינו זורק — אבחון לא מפיל שיחה."""
    try:
        _events.append(
            {
                "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "kind": kind,
                **{k: redact(v, k) for k, v in fields.items()},
            }
        )
    except Exception:  # noqa: BLE001
        pass


def snapshot() -> list[dict[str, Any]]:
    """העתק של האירועים, מהישן לחדש."""
    return list(_events)


def clear() -> None:
    """ניקוי. נקרא בפריקת הרשומה, כדי שאבחון לא יציג שיחות של הגדרה קודמת."""
    _events.clear()
