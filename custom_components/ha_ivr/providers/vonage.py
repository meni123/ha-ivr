"""Vonage.

תפריט דרך NCCO וערוץ סטרימינג ב-16 קילוהרץ. אין מסלול שיחות
יוצאות, ולכן אין התראות ואין ישויות נמען.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from .. import history
from ..codec import PathCodec
from ..model import (
    Action, CallContext, GoTo, Say, Terminal,
)

_LOGGER = logging.getLogger(__name__)

DRIVER_ID = "vonage"

# ל-Vonage אין שלוחות. פריט "מעבר" מתורגם לחיבור ישיר לערוץ
# הסטרימינג, ולכן הוא כן מוצע.
SUPPORTS_GOTO = True

# ל-Vonage אין שלוחות. פריט "מעבר" מתורגם לחיבור ישיר לערוץ
# הסטרימינג, ולכן היעד אינו נקרא.
GOTO_TARGET_HINT = "לא בשימוש ב-Vonage — המעבר מחבר ישירות לעוזר הקולי"
# השם שמוצג בבורר הספק ובכותרת הרשומה.
NAME = "Vonage"

SUPPORTS_STREAM = True

# כתובת הסטרימינג אינה מוגדרת אצלם אלא נשלחת בתוך ה-NCCO בזמן
# השיחה, ולכן מסך ההגדרות אינו מציג אותה להעתקה.
STREAM_URL_AT_PROVIDER = False

# הקצב נבחר על ידינו ונשלח ב-NCCO; 16k מייתר את המרת הקצב.
NEEDS_RATE = True

# שם השדה בהגדרות שבו יושב קצב הדגימה המבוקש. השם הישן, שהיה
# ייחודי לספק, נקרא עדיין כדי שרשומה ותיקה לא תאבד את הערך.
CONF_RATE = "stream_rate"
CONF_RATE_LEGACY = "vonage_rate"

# ברירת המחדל. 16k מול הצינור פירושו אפס המרת קצב.
DEFAULT_RATE = 16000

# שם הפרמטר שנושא את המיקום ב-eventUrl. הערך שלו הוא שם הפרמטר
# מהמקודד, וההקשה עצמה מגיעה בגוף הבקשה.
POSITION_PARAM = "p"

CODEC = PathCodec()

# Vonage אינה צוברת ערכים: כל בקשה נושאת רק את הפרמטר שנשתל
# ב-eventUrl של הפעולה הקודמת. זה מספיק בדיוק מפני שהנתיב נמצא
# בשם הפרמטר עצמו — וזו הסיבה שהתכנון לא נשען על צבירה בשום ספק.
# התשובה היא JSON, ולכן אין כאן תווים אסורים כמו בימות.


def parse(params: dict[str, str], body: dict[str, Any] | None = None) -> CallContext:
    """פענוח בקשה נכנסת.

    שם הפרמטר מגיע ב-query string, וההקשה בגוף. מרכיבים אותם
    בחזרה לצורה שהמקודד מצפה לה.
    """
    body = body or {}
    name = str(params.get(POSITION_PARAM, ""))

    digits = ""
    dtmf = body.get("dtmf")
    if isinstance(dtmf, dict):
        digits = str(dtmf.get("digits", "") or "")
    elif isinstance(dtmf, str):
        digits = dtmf
    if not digits:
        digits = str(body.get("digits", "") or params.get("digits", "") or "")

    # בקשה בלי מיקום אינה בהכרח שגיאה: כשה-Event URL זהה
    # ל-Answer URL, גם אירועי הסטטוס (ringing/answered/completed)
    # נוחתים כאן. הרישום כולל גם את השאילתה וגם את הגוף, כי
    # בקשות GET נושאות את הנתונים בשאילתה בלבד.
    if not name:
        _LOGGER.debug(
            "Vonage: request with no position. query=%s | body=%s",
            {k: str(v)[:60] for k, v in params.items()} or "(empty)",
            {k: str(v)[:60] for k, v in body.items()} or "(empty)",
        )

    decoded = CODEC.decode({name: digits} if name else {})
    return CallContext(
        call_id=str(body.get("uuid", "") or params.get("uuid", "")),
        caller=str(body.get("from", "") or params.get("from", "")),
        did=str(body.get("to", "") or params.get("to", "")),
        path=decoded.path,
        digit=decoded.digit,
        step=decoded.step,
        hangup=str(body.get("status", "")).lower() in ("completed", "cancelled"),
        raw={**params, **{k: str(v) for k, v in body.items()}},
    )


def _talk(messages: list[Say], *, barge_in: bool = False) -> list[dict[str, Any]]:
    """פעולות talk. Vonage אינה מבדילה בין מספר לטקסט.

    say_number מפצל מספרים לפריטים נפרדים בגלל הנקודה של ימות.
    כאן אין בכך צורך, אבל גם אין נזק — מנוע ההקראה מקבל את אותו
    רצף מילים.
    """
    text = " ".join(m.data for m in messages if m.kind != "file").strip()
    if not text:
        return []
    action: dict[str, Any] = {"action": "talk", "text": text, "language": "he-IL"}
    if barge_in:
        action["bargeIn"] = True
    return [action]


def render(
    action: Action,
    *,
    callback_url: str = "",
    stream_url: str = "",
    stream_token: str = "",
    rate: int = 16000,
    after: Action | None = None,
) -> list[dict[str, Any]]:
    """בניית NCCO.

    callback_url היא הכתובת שאליה Vonage תפנה אחרי ההקשה.
    stream_url היא נקודת הקצה של העוזר הקולי, לפעולת GoTo.
    after היא פעולה שתתבצע כשהחיבור לעוזר נגמר. Vonage מריצה את
    פעולות ה-NCCO ברצף, וכשאין פעולה אחרי connect השיחה פשוט
    מתנתקת — אין כאן מקבילה ל-endGoTo של טכנוליין.
    """
    if isinstance(action, GoTo):
        # ל-Vonage אין שלוחות, ולכן פריט "מעבר" מתורגם כאן לחיבור
        # ישיר לערוץ הסטרימינג של העוזר. זה פשוט משני האחרים:
        # אין שלוחה נפרדת להגדיר, הפעולה מוחזרת מהתפריט עצמו.
        if not stream_url:
            _LOGGER.warning("Vonage: no streaming URL, cannot connect to the assistant")
            return _talk([Say("text", "האפשרות הזו אינה זמינה כרגע")])

        endpoint: dict[str, Any] = {
            "type": "websocket",
            "uri": stream_url,
            "content-type": f"audio/l16;rate={rate}",
        }
        if stream_token:
            # Vonage שולחת את הערך הזה כמו שהוא בלחיצת היד, ולכן
            # אותו טוקן שמאמת את שאר הנתיבים מאמת גם את הערוץ.
            endpoint["authorization"] = {
                "type": "custom",
                "value": f"Bearer {stream_token}",
            }
        ncco = [*_talk(action.messages), {"action": "connect", "endpoint": [endpoint]}]
        if after is not None:
            ncco += render(
                after,
                callback_url=callback_url,
                stream_url=stream_url,
                stream_token=stream_token,
                rate=rate,
            )
        return ncco

    if isinstance(action, Terminal):
        # NCCO שנגמר מסיים את השיחה מעצמו, ולכן אין פעולה נוספת.
        # קודם ישבו כאן שני ענפים שהחזירו בדיוק אותו דבר.
        return _talk(action.messages)

    name = CODEC.encode(action.step, action.at_path)
    query = urlencode({POSITION_PARAM: name})
    return [
        *_talk(action.messages, barge_in=True),
        {
            "action": "input",
            "type": ["dtmf"],
            "dtmf": {"maxDigits": 1, "timeOut": action.timeout},
            "eventUrl": [f"{callback_url}?{query}"],
        },
    ]


def respond(action: Action, cfg: dict | None = None):
    """בניית ה-NCCO ורישום מה נשלח.

    כתובת החזרה נבנית מהבקשה הנוכחית ולא מהגדרה, ולכן היא מגיעה
    מהליבה. הקצב נקבע בהגדרות ונקרא מכאן.
    """
    from aiohttp import web  # noqa: PLC0415

    c = cfg or {}
    options = c.get("options") or {}
    body = render(
        action,
        callback_url=c.get("callback_url", ""),
        stream_url=c.get("stream_url", ""),
        stream_token=c.get("token", ""),
        rate=int(
            options.get(CONF_RATE)
            or options.get(CONF_RATE_LEGACY)
            or DEFAULT_RATE
        ),
        after=c.get("after"),
    )
    history.record("menu.reply", driver=DRIVER_ID, body=body)
    return web.json_response(body)


# ----------------------------------------------------------------------
# ערוץ הסטרימינג — מה שהליבה שואלת אותנו
# ----------------------------------------------------------------------


def detect(payload: dict) -> dict | None:
    """מסגרת הפתיחה של הספק: מטא-דאטה עם `content-type`.

    Vonage אינה שולחת `type=start` אלא מסגרת שמתארת את פורמט
    האודיו, ואין בה מזהה שיחה ואין בה מספר מתקשר.
    """
    raw = str(payload.get("content-type", ""))
    if not raw:
        return None
    return {"call_id": "", "caller": "", "token": "", "rate": _rate(raw)}


def _rate(raw: str) -> int | None:
    """קצב הדגימה מתוך `audio/l16;rate=16000`."""
    for part in raw.replace(",", ";").split(";"):
        key, _, value = part.partition("=")
        if key.strip().lower() == "rate" and value.strip().isdigit():
            return int(value.strip())
    return None


def clear_command() -> dict:
    """ריקון חוצץ ההשמעה. Vonage מחזירה `websocket:cleared`."""
    return {"action": "clear"}


def hangup_command() -> dict | None:
    """אין פקודת ניתוק בערוץ. הליבה סוגרת את הסוקט."""
    return None


def leave_command(target: str) -> dict | None:
    """אין העברה בערוץ. היעד נקבע ב-NCCO, לא בזמן השיחה."""
    return None


# ----------------------------------------------------------------------
# שדות ההגדרה הייחודיים לספק
# ----------------------------------------------------------------------


def menu_fields(current: dict) -> dict:
    """אין. כל מה ש-Vonage צריכה נמצא בשדות המשותפים."""
    return {}


def menu_save(user_input: dict) -> dict:
    return {}


def default_ips() -> str:
    return ""
