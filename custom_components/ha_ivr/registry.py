"""מרשם הדרייברים.

הליבה אינה מכירה אף ספק בשם. כל דרייבר רושם את עצמו כאן בטעינה,
והניתוב הוא לפי מזהה הדרייבר שבכתובת `/api/ha_ivr/<driver>/<token>`.

הוספת ספק היא קובץ אחד תחת `providers/`, בלי נגיעה בליבה. הבדיקה
`tests/run_live.py` נכשלת אם שם של ספק מופיע בקוד הליבה.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

_LOGGER = logging.getLogger(__name__)


class Driver(Protocol):
    """מה שאינטגרציית ספק חייבת לספק."""

    DRIVER_ID: str
    """המזהה שבכתובת, למשל `yemot`."""

    SUPPORTS_GOTO: bool
    """האם הספק יודע להעביר לשלוחה או לערוץ אחר."""

    def parse(self, params: dict[str, str], body: dict[str, Any]) -> Any:
        """בקשה נכנסת ל-CallContext. שני הארגומנטים תמיד מועברים.

        ספק שההקשה שלו נמצאת בשם הפרמטר מתעלם מ-`body`; ספק
        שמחזיר אותה בגוף בלבד זקוק לו. החתימה אחידה לכולם.
        """

    def detect(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """מסגרת הפתיחה של הספק, אם זו שלו.

        מוחזר מילון עם `call_id`, `caller`, `token` ו-`rate`, או
        `None` אם המסגרת אינה שלו. הליבה שואלת את כל הדרייברים
        ולוקחת את הראשון שעונה.

        רלוונטי רק לספק עם `SUPPORTS_STREAM`.
        """

    def clear_command(self) -> dict[str, Any] | None:
        """פקודת קטיעת השמעה, או `None` אם אין לספק כזו."""

    def hangup_command(self) -> dict[str, Any] | None:
        """פקודת ניתוק סופית, או `None` — ואז הסוקט נסגר מצידנו."""

    def leave_command(self, target: str) -> dict[str, Any] | None:
        """פקודת יציאה ליעד בעץ, או `None` — ואז הסוקט נסגר."""

    def respond(self, action: Any, cfg: dict[str, Any]) -> Any:
        """Action ל-web.Response, בפורמט של הספק.

        הדרייבר בונה את התשובה ורושם אותה לחוצץ האבחון.
        """


_DRIVERS: dict[str, Driver] = {}


def register(driver: Driver) -> None:
    """רישום דרייבר. נקרא מ-`async_setup` של אינטגרציית הספק."""
    _DRIVERS[driver.DRIVER_ID] = driver
    _LOGGER.debug("Registered driver %s", driver.DRIVER_ID)


def get(driver_id: str) -> Driver | None:
    return _DRIVERS.get(driver_id)


def registered() -> list[str]:
    return sorted(_DRIVERS)


def for_entry(entry) -> Driver | None:
    """הדרייבר של הרשומה, לפי הספק שנבחר בטופס.

    הרשומה נושאת את הספק ולא הדומיין: הדומיין אחד לכל הספקים,
    ולכן השוואה לפיו הייתה מתאימה כל דרייבר לכל רשומה.
    """
    return _DRIVERS.get(str(entry.data.get("provider", "")))


def all_drivers() -> list[Driver]:
    """כל הדרייברים הרשומים, לפי סדר המזהה."""
    return [_DRIVERS[k] for k in sorted(_DRIVERS)]


def with_stream() -> list[Driver]:
    """הדרייברים שיש להם ערוץ סטרימינג."""
    return [d for d in all_drivers() if getattr(d, "SUPPORTS_STREAM", False)]
