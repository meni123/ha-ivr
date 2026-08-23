"""התראה קולית ממתינה — הגשר בין השיגור לבין השיחה שחוזרת.

אצל טכנוליין אין דרך לשלוח הקלטה לתוך קמפיין: `audioText` נופל
במנוע ההקראה שלהם ו-`audioFile` אינו נקרא. מה שכן עובד הוא
`messagesType=extensionActivation`, שמחייג ומחבר את הנמען לשלוחת
הסטרימינג — כלומר האודיו אינו עובר דרכם כלל, אלא נכנס
באותו סוקט שמשרת את העוזר הקולי.

המחיר הוא ששיגור ההתראה והשמעתה הם שני אירועים נפרדים:

    async_announce  →  campaignRun  →  המרכזיה מחייגת  →  הנמען
    עונה  →  WebSocket נפתח אלינו  →  כאן מוצאים את מה שנשמר

ההתאמה בין השניים היא מספר הנמען, שמגיע בשדה `caller` של מסגרת
ה-`start`. היא אינה חסינה: מתקשר שיחייג בעצמו לשלוחת הסטרימינג
מאותו מספר, בחלון שבין השיגור למענה, יקבל את ההתראה במקום את
העוזר. שתי הגנות מצמצמות את החשיפה — החלון קצר (`DEFAULT_TTL`),
וההתראה נתפסת פעם אחת בלבד. שלוחת סטרימינג ייעודית להתראות
תהפוך את ההתאמה לוודאית, והיא תוספת אפשרית.

האחסון הוא תור לכל רשומה ולא סלוט יחיד, כי כמה התראות יכולות
להמתין יחד — שני חיישנים שנדלקים באותה דקה הם מקרה שכיח. התור
הוא FIFO גם לאותו מספר, כך שהסדר נשמר.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from .const import PENDING_ANNOUNCE

_LOGGER = logging.getLogger(__name__)

# כמה שניות ההתראה ממתינה לשיחה שתחזור. תשעים שניות מכסות מענה
# איטי ומשאירות את חלון ההתאמה קצר.
DEFAULT_TTL = 90.0

# כמה התראות יכולות להמתין יחד לרשומה. בלי תקרה, ספק שאינו
# מחייג כלל יצבור התראה לכל אוטומציה שרצה.
MAX_PENDING = 8


def _key(phone: str) -> str:
    """מספר מנורמל להשוואה.

    תשע הספרות האחרונות. הספק עשוי להחזיר את המספר עם קידומת
    בינלאומית או בלי אפס מוביל, והשוואת מחרוזות מלאה נכשלת על
    הבדל צורני.
    """
    digits = "".join(c for c in str(phone) if c.isdigit())
    return digits[-9:] if len(digits) >= 9 else digits


@dataclass
class Pending:
    """התראה ששוגרה וממתינה לשיחות.

    נתפסת פעם אחת לכל נמען ולא פעם אחת בסך הכול: התראה לשני
    מספרים מייצרת שתי שיחות נפרדות, ולעיתים בהפרש של שנייה.
    """

    pcm: bytes
    rate: int
    message: str
    phones: set[str]
    expires: float
    total: int = 0
    played: int = 0
    delivered: asyncio.Event = field(default_factory=asyncio.Event)
    error: str = ""

    def __post_init__(self) -> None:
        self.total = len(self.phones)

    def matches(self, caller: str) -> bool:
        key = _key(caller)
        return bool(key) and key in self.phones

    def take(self, caller: str) -> None:
        """סימון שהנמען הזה כבר נתפס, כדי שלא ייתפס פעמיים."""
        self.phones.discard(_key(caller))

    def mark_played(self) -> None:
        """השמעה אחת הסתיימה.

        ההמתנה נגמרת רק כשכל הנמענים שמעו. נמען שקו שלו תפוס
        אינו מגיע לכאן, ולכן ההמתנה נגמרת גם בפקיעה — ואז הדיווח
        הוא כמה מתוך כמה, ולא "נכשל".
        """
        # נספר מה שהושמע ולא מה שנתפס: `phones` מתרוקן ברגע
        # שהשיחה נענתה, לפני שההודעה התחילה.
        self.played += 1
        if self.played >= self.total:
            self.delivered.set()

    @property
    def summary(self) -> str:
        return f"{self.played} מתוך {self.total}"

    @property
    def expired(self) -> bool:
        return time.monotonic() > self.expires


def store(hass, entry_id: str, pcm: bytes, rate: int, message: str,
          phones, ttl: float = DEFAULT_TTL) -> Pending:
    """הוספת התראה לתור, לפני השיגור.

    הסדר מהותי: החיוג עשוי להיענות תוך שניות, ושמירה אחרי
    הקריאה לספק פותחת חלון שבו השיחה חוזרת ואין מה להשמיע.
    """
    pending = Pending(
        pcm=pcm,
        rate=rate,
        message=message,
        phones={_key(p) for p in phones if _key(p)},
        expires=time.monotonic() + ttl,
    )
    queue = hass.data.setdefault(PENDING_ANNOUNCE, {}).setdefault(entry_id, [])

    # ניקוי פגות תוקף בכל הוספה. אין טיימר ואין משימת רקע: התור
    # נקרא רק בשיגור ובמענה, ובשניהם ממילא עוברים עליו.
    expired = [p for p in queue if p.expired]
    for stale in expired:
        queue.remove(stale)
    if expired:
        _LOGGER.debug("Alert: %s pending alerts expired and were dropped", len(expired))

    # הישנה ביותר נזרקת, כי היא הקרובה ביותר לפוג ממילא.
    if len(queue) >= MAX_PENDING:
        dropped = queue.pop(0)
        dropped.error = (
            f"התור מלא ({MAX_PENDING} התראות ממתינות). ההתראה הוסרה "
            "לפני שנענתה."
        )
        dropped.delivered.set()  # משחרר את מי שממתין, עם השגיאה
        _LOGGER.warning("Alert: the queue is full, the oldest pending alert was removed")

    queue.append(pending)
    _LOGGER.debug(
        "Alert pending for entry %s, %s recipients, %s seconds. In queue: %s",
        entry_id, len(pending.phones), int(ttl), len(queue),
    )
    return pending


def claim(hass, entry_id: str, caller: str) -> Pending | None:
    """תפיסת ההתראה הממתינה, אם השיחה הזו היא שלה.

    נתפסת פעם אחת: שיחה שנייה מאותו מספר תקבל את העוזר ולא
    השמעה חוזרת.
    """
    queue = (hass.data.get(PENDING_ANNOUNCE) or {}).get(entry_id) or []

    for pending in list(queue):
        if pending.expired:
            queue.remove(pending)
            _LOGGER.debug("Pending alert expired, dropped")
            continue
        if pending.matches(caller):
            # הראשונה בתור שמתאימה, כדי לשמור על סדר השיגור.
            pending.take(caller)
            # יורדת מהתור רק כשכל הנמענים נתפסו. התראה לשני
            # מספרים חייבת לשרוד את המענה הראשון.
            if not pending.phones:
                queue.remove(pending)
            return pending

    _LOGGER.debug(
        "The call from %s is not the recipient of any pending alert "
        "(%s in queue), continuing to the assistant",
        caller or "(unknown)", len(queue),
    )
    return None


def drop(hass, entry_id: str, pending: Pending) -> None:
    """הסרת התראה מהתור, אם היא עדיין שם.

    נקראת ב-`finally` של השיגור: התראה שנתפסה כבר הוסרה ב-`claim`,
    וזו ההסרה של מי שפגה, נכשלה בשיגור, או שאיש לא ענה לה.
    """
    queue = (hass.data.get(PENDING_ANNOUNCE) or {}).get(entry_id) or []
    if pending in queue:
        queue.remove(pending)
