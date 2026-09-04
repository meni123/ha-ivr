"""ימות המשיח.

תפריט DTMF דרך `type=api`. אין ערוץ סטרימינג ולכן אין עוזר קולי;
ההתראות עוברות ב-API שלהם, שמקריא את הטקסט בעצמו.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from .. import history
from ..codec import YEMOT_CODEC
from ..model import (
    Action, CallContext, GoTo, Say, Terminal,
)
from ..outbound import OutboundError, clean_phones, digits

_LOGGER = logging.getLogger(__name__)

DRIVER_ID = "yemot"

# ימות יודעת go_to_folder, ולכן פריט "מעבר" מוצע בתפריט.
SUPPORTS_GOTO = True

# `goTo` של ימות מקבל מזהה שלוחה ולא נתיב.
GOTO_TARGET_HINT = "מזהה שלוחה אצל ימות, למשל 5 או 1/2"

# השם שמוצג בבורר הספק ובכותרת הרשומה.
NAME = "ימות המשיח"

SUPPORTS_STREAM = False

# האורך המרבי להודעה בודדת. לא מתועד אצלם — ערך שמרני לחיתוך.
MAX_MESSAGE_CHARS = 250

# תווים שחייבים מיפוי. הרשימה קצרה בכוונה: רוב סימני הפיסוק
# עוברים בשלום, ומיפוי שלהם היה משתיק תווים תקינים בלי סיבה.
_REPLACEMENTS = {
    # מפריד בין זוגות key=value בגוף התשובה. גורם לניתוק מיידי
    # בלי הקראה, גם בתוך `read`.
    "&": " ו",
    # מפריד בין ההודעות לשדות ב-`read`. ימות מפצלת על ה-= הראשון,
    # שדה 1 בולע את שאר ההודעות ואת כל השדות, והמתקשר מועבר
    # לשלוחה אקראית — כשל שקט, בלי הודעת שגיאה.
    "=": " שווה ",
    # שובר את מנוע ההקראה שלהם.
    '"': " ",
    # קוטעים את שארית התשובה, כולל go_to_folder.
    "\r": " ",
    "\n": " ",
}

# שיפור הקראה ולא בטיחות: הסימן בטוח לשליחה, אבל נשמע טוב יותר
# כמילה מאשר כסימן שמנוע ההקראה מדלג עליו בשקט.
_SPOKEN = {
    "%": " אחוז ",
}

# הנקודה מטופלת בנפרד, כי המשמעות שלה תלויה בהקשר. היא המפריד
# בין הודעות ברצף, ולכן חייבת להיעלם מהתוכן בכל מקרה — אבל
# התחליף שונה: נקודה עשרונית הופכת למילה "נקודה", וכל נקודה
# אחרת לרווח. נקודת סוף משפט שהייתה הופכת למילה נשמעת בקול
# ("הכל תקין נקודה"), ומספרים ממילא מפוצלים ב-`say_number`.
_DECIMAL_POINT = re.compile(r"(?<=\d)\.(?=\d)")

# מקף וגרש בטוחים באמצע מילה ולכן אינם ממופים: "סלון-מטבח" ו-ג'
# נשמעים כמו שנכתבו. מקף בתחילת התוכן הוא עניין אחר, כי `t-` הוא
# המפריד בין הסוג לתוכן — ראו `_lead`.

# מה שנשמע כשלא נשאר דבר אחרי הסינון. `t-` ריק הוא הודעה בלי
# תוכן, והתנהגות ימות עליה אינה מתועדת.
EMPTY_TEXT = "אין נתון"

_PREFIX = {"text": "t", "number": "n", "digits": "d", "file": "f", "raw": "t"}


def sanitize(text: str) -> str:
    """שומר סף אחרון על כל מחרוזת שיוצאת לימות.

    רץ בבונה התשובה ולא רק על טקסט שמקורו במשתמש: נקודה שדולפת
    מיחידת מידה, ממחרוזת גרסה או מכתובת IP קוטעת את השיחה באמצע
    המשפט.
    """
    out = str(text)
    # לפני שאר המיפויים: הנקודה בין ספרות הופכת למילה, וכל
    # נקודה אחרת לרווח.
    out = _DECIMAL_POINT.sub(" נקודה ", out)
    out = out.replace(".", " ")
    for bad, good in _REPLACEMENTS.items():
        out = out.replace(bad, good)
    for sign, word in _SPOKEN.items():
        out = out.replace(sign, word)
    out = " ".join(out.split()).lstrip("-").strip()
    return out[: MAX_MESSAGE_CHARS] or EMPTY_TEXT


def numeric(data: str) -> str:
    """שומר סף על ערך שנשלח כמספר או כרצף ספרות.

    פריטים אלה אינם עוברים ב-sanitize — הם נשלחים כמו שהם — ולכן
    כל תו שאינו ספרה שדולף לתוכם יוצא אל הקו. כך נוצר `n--18`
    ממספר שלילי. הסימן השלילי מטופל כמילה ב-say_number.

    מחרוזת בלי ספרות מחזירה ריק, והפריט יושמט לגמרי: ערך מומצא
    היה נשמע כמו נתון אמיתי.
    """
    return "".join(c for c in str(data) if c.isdigit())


def _render_messages(messages: list[Say]) -> str:
    """רצף הודעות. הנקודה כאן היא המפריד בין הפריטים."""
    parts = []
    for item in messages:
        prefix = _PREFIX[item.kind]
        if item.kind == "text":
            data = sanitize(item.data)
        elif item.kind in ("number", "digits"):
            data = numeric(item.data)
        else:
            # file נשלח כמו שהוא — נתיב אצל הספק, לא טקסט להקראה.
            # raw הוא בדיקת פרוטוקול ועוקף את המסנן בכוונה.
            data = str(item.data)
        if not data:
            continue
        parts.append(f"{prefix}-{data}")
    return ".".join(parts)


def parse(
    params: dict[str, str],
    body: dict | None = None,
    *,
    hangup_key: str = "hangup",
) -> CallContext:
    """פענוח בקשה נכנסת.

    `body` מתקבל ואינו בשימוש: ההקשה מגיעה בשם הפרמטר. החתימה
    אחידה לכל הדרייברים.
    """
    decoded = YEMOT_CODEC.decode(params)
    return CallContext(
        call_id=params.get("ApiCallId", ""),
        caller=params.get("ApiPhone", ""),
        did=params.get("ApiRealDID") or params.get("ApiDID", ""),
        path=decoded.path,
        digit=decoded.digit,
        step=decoded.step,
        hangup=params.get(hangup_key) == "yes",
        raw=params,
    )


def render(action: Action) -> str:
    """בניית מחרוזת התשובה בפורמט ימות."""
    if isinstance(action, GoTo):
        # go_to_folder מקבל כאן נתיב שלוחה. אותו שדה בטופס נושא
        # משמעות שונה בכל ספק.
        target = action.target if action.target.startswith("/") else f"/{action.target}"
        body = f"go_to_folder={target}"
        if action.messages:
            return f"id_list_message={_render_messages(action.messages)}&{body}"
        return body

    if isinstance(action, Terminal):
        # בלי אמפרסנד מסיים: התיעוד אינו מגדיר התנהגות לפעולה
        # ריקה. היעד הוא תמיד ניתוק.
        return (
            f"id_list_message={_render_messages(action.messages)}"
            "&go_to_folder=hangup"
        )

    name = YEMOT_CODEC.encode(action.step, action.at_path)
    # שדה 10 מגביל את המקשים המותרים. מיפוי השדות 7–10 אינו
    # מאושר מול התיעוד, ושינוי עיוור שלו עלול לפסול את השדה כולו
    # ולהפיל גם את הספרות המוגדרות — לא לשנות בלי מדידה בשיחה.
    allowed = "".join(sorted(action.allowed))

    # חמישה עשר שדות, לפי סעיף 4.3 של המפרט:
    #   1 שם  2 שימוש-חוזר  3 מקס  4 מין  5 המתנה  6 השמעה-חוזרת
    #   7 כוכבית  8 אפס  9 החלפה  10 מותרים  11-14 ריק  15 אישור
    #
    # שדה 6 = No הוא מה שמכבה בפועל את תפריט האישור; שדה 15 נשאר
    # כחגורת ביטחון.
    fields = f"{name},,1,1,{action.timeout},No,,,,{allowed},,,,,no"
    return f"read={_render_messages(action.messages)}={fields}"


def respond(action: Action, cfg: dict | None = None):
    """בניית תשובת ה-HTTP בפורמט ימות, ורישום מה נשלח.

    ימות מחזירה מחרוזת טקסט ולא JSON. ההבדל נעצר כאן: הליבה
    מקבלת `web.Response` ואינה יודעת מה בתוכה.
    """
    from aiohttp import web  # noqa: PLC0415

    text = render(action)
    history.record("menu.reply", driver=DRIVER_ID, body=text[:400])
    return web.Response(text=text, content_type="text/plain", charset="utf-8")


# הערוצים שימות יודעת להוציא בהם התראה. שיחה קולית עולה יחידה;
# SMS וצינתוק עולים עשירית יחידה — נמדד ואומת מול המחירון.
NOTIFY_CHANNELS = ("voice", "sms", "tzintuk")


async def async_notify(
    hass, entry, message: str, phones: list[str], channel: str = "voice",
    trunk: str = "", caller_id: str = "", retries: int = 0,
) -> None:
    """התראה לנמען, דרך ה-API של ימות, בערוץ שנבחר לנמען.

    `trunk` ו-`caller_id` מתקבלים לאחידות עם ממשק ההתראות ואינם
    בשימוש כאן — לימות אין טראנקים, והזיהוי היוצא נקבע אצל הספק.

    לא דרך הלוויין: אין ערוץ סטרימינג ולכן אין לאן להזרים הקראה.
    שיחה קולית מקריאה את הטקסט; SMS שולח אותו כטקסט; צינתוק מצלצל
    בלי תוכן, כתמריץ להתקשר פנימה ולשמוע.
    """
    options = dict(entry.options)
    joined = ",".join(phones)
    if channel == "sms":
        await async_send_sms(hass, options, {"message": message, "phones": joined})
    elif channel == "tzintuk":
        await async_send_tzintuk(hass, options, {"phones": joined})
    else:
        await async_send_call(hass, options, {"message": message, "phones": joined})


# ---- שיחות יוצאות ----

SEND_TTS_URL = "https://www.call2all.co.il/ym/api/SendTTS"
SEND_SMS_URL = "https://www.call2all.co.il/ym/api/SendSms"
TZINTUK_URL = "https://www.call2all.co.il/ym/api/RunTzintuk"


async def _api_post(hass, url: str, payload: dict, token: str) -> str:
    """POST לימות עם רישום ממוסך והמרת שגיאת HTTP.

    מקום אחד לרישום שיוצא ולתשובה שחוזרת, כדי שכל ערוץ יופיע
    ביומן ובהיסטוריה באותה צורה. הטוקן אינו נרשם.
    """
    from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
        async_get_clientsession,
    )

    masked = {**payload, "token": f"***{token[-4:]}" if token else "(empty)"}
    _LOGGER.debug("Yemot <- %s | %s", url, masked)
    history.record("yemot.request", url=url, payload=masked)
    session = async_get_clientsession(hass)
    async with session.post(url, data=payload) as resp:
        text = await resp.text()
        _LOGGER.info("Yemot -> HTTP %s: %s", resp.status, text[:400])
        history.record("yemot.response", status=resp.status, body=text[:400])
        if resp.status != 200:
            raise OutboundError(
                f"the provider returned HTTP {resp.status}",
                key="provider_http_error",
                placeholders={"status": str(resp.status), "body": text[:120]},
            )
    return text


def _require(options: dict, phones_in: str) -> tuple[str, str]:
    """הטוקן והמספרים המנוקים, או חריגה מתורגמת. משותף לכל ערוץ."""
    token = str(options.get("yemot_token", "") or "").strip()
    if not token:
        raise OutboundError(
            "Yemot management token is missing", key="missing_yemot_token"
        )
    phones = clean_phones(str(phones_in))
    if not phones:
        raise OutboundError("no valid phone numbers", key="no_valid_numbers")
    return token, phones


def _check_accepted_channel(text: str, phones: str, label: str) -> None:
    """הצלחת SMS/צינתוק: `responseStatus == OK`, וכשל חלקי כאזהרה."""
    import json  # noqa: PLC0415

    try:
        data = json.loads(text)
    except ValueError:
        _LOGGER.info("%s sent to %s", label, phones)
        return
    if data.get("responseStatus") != "OK":
        raise OutboundError(
            f"{label} was rejected by the provider",
            key="outbound_rejected",
            placeholders={"detail": str(data.get("message") or text[:120])},
        )
    if errors := (data.get("errors") or {}):
        _LOGGER.warning("Yemot %s: some recipients failed: %s", label, errors)
    _LOGGER.info("Yemot %s accepted for %s", label, phones)


async def async_send_sms(hass, options: dict, data: dict) -> None:
    """שליחת SMS — עשירית יחידה. הטקסט הוא ההתראה עצמה."""
    token, phones = _require(options, data["phones"])
    text = await _api_post(
        hass, SEND_SMS_URL,
        {"token": token, "phones": phones, "message": str(data["message"])},
        token,
    )
    _check_accepted_channel(text, phones, "SMS")


async def async_send_tzintuk(hass, options: dict, data: dict) -> None:
    """צינתוק — צלצול-ניתוק, עשירית יחידה, בלי תוכן."""
    token, phones = _require(options, data["phones"])
    text = await _api_post(
        hass, TZINTUK_URL, {"token": token, "phones": phones}, token
    )
    _check_accepted_channel(text, phones, "tzintuk")

async def async_send_call(hass, options: dict, data: dict) -> None:
    """חיוג והקראת טקסט."""
    token = str(options.get("yemot_token", "") or "").strip()
    if not token:
        raise OutboundError(
            "Yemot management token is missing", key="missing_yemot_token"
        )

    phones = clean_phones(str(data["phones"]))
    if not phones:
        raise OutboundError(
            "no valid phone numbers", key="no_valid_numbers"
        )

    payload: dict[str, Any] = {
        "token": token,
        "phones": phones,
        "ttsMessage": str(data["message"]),
    }
    if caller_id := str(data.get("caller_id", "") or ""):
        payload["callerId"] = digits(caller_id)

    from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
        async_get_clientsession,
    )

    # הבקשה נרשמת לפני השליחה, בלי הטוקן. בלי זה אי אפשר לדעת מה
    # באמת יצא — וזו הייתה הסיבה שלא ניתן היה לאבחן שיחה שצלצלה
    # אך לא השמיעה דבר.
    masked = {**payload, "token": f"***{token[-4:]}" if token else "(empty)"}
    _LOGGER.debug("Yemot <- %s | %s", SEND_TTS_URL, masked)
    history.record("yemot.request", url=SEND_TTS_URL, payload=masked)

    session = async_get_clientsession(hass)
    async with session.post(SEND_TTS_URL, data=payload) as resp:
        text = await resp.text()
        # נרשם גם בהצלחה: בלי זה, שיחה שדווחה כ"נשלחה" אינה
        # מותירה ראיה למה שימות ענתה בפועל.
        _LOGGER.info("Yemot -> HTTP %s: %s", resp.status, text[:400])
        history.record("yemot.response", status=resp.status, body=text[:400])
        if resp.status != 200:
            raise OutboundError(
                f"the provider returned HTTP {resp.status}",
                key="provider_http_error",
                placeholders={"status": str(resp.status), "body": text[:120]},
            )

    data = _check_accepted(text)
    _report(data, phones)


def _report(data: dict | None, phones: str) -> None:
    """סיכום מה שימות דיווחה, ולא רק "נשלחה".

    התשובה מפרטת כמה שיחות יצאו, אילו נכשלו, וכמה יחידות נשארו.
    בלי זה שליחה לחמישה נמענים שהצליחה לשלושה הייתה נראית ביומן
    כהצלחה מלאה, ואי אפשר היה לדעת מי לא קיבל.

    כשל חלקי הוא אזהרה ולא חריגה — מי שכן קיבל, קיבל, ולהפיל את
    הקריאה כולה היה מסתיר את זה.
    """
    if not isinstance(data, dict):
        _LOGGER.info("Outgoing call sent to %s", phones)
        return

    ok_calls = data.get("OKCalls")
    errors = data.get("ErrorCalls") or {}
    units = data.get("units")
    campaign = data.get("CampaignId")

    if ok_calls == 0:
        # `responseStatus` היה OK אבל אף שיחה לא יצאה. בלי הבדיקה
        # הזו זו הצלחה לכל דבר ביומן.
        raise OutboundError(
            "the request was accepted but no call was placed",
            key="no_call_placed",
            placeholders={"errors": str(errors or "")},
        )

    parts = [f"{ok_calls if ok_calls is not None else '?'} יצאו אל {phones}"]
    if units is not None:
        parts.append(f"יתרה {units} יחידות")
    if campaign:
        parts.append(f"קמפיין {campaign}")
    _LOGGER.info("Outgoing call: %s", ", ".join(parts))
    if errors:
        _LOGGER.warning("Yemot: some recipients failed: %s", errors)


def _check_accepted(text: str) -> dict | None:
    """האם ימות קיבלה את הבקשה, ומה היא החזירה.

    ימות מחזירה JSON עם `responseStatus`, וכשהשדה קיים הוא הקובע
    בהשוואה מדויקת. בלי JSON נעשית בדיקה טקסטואלית.

    ההשוואה חייבת להיות מדויקת ולא הכלה: `NOT_OK` מכיל `OK`,
    ולכן חיפוש הכלה מפרש תשובת דחייה כהצלחה.
    """
    import json  # noqa: PLC0415

    try:
        data = json.loads(text)
    except ValueError:
        data = None

    if isinstance(data, dict):
        for field in ("responseStatus", "status"):
            if field in data:
                if str(data[field]).strip().upper() == "OK":
                    return data
                raise OutboundError(
                    "the provider rejected the request",
                    key="provider_bad_response",
                    placeholders={
                        "body": str(data.get("message") or data[field])
                    },
                )

    upper = text.upper()
    if "NOT_OK" in upper or "NOT OK" in upper:
        raise OutboundError(
        "the provider rejected the request",
        key="provider_bad_response",
        placeholders={"body": text[:120]},
    )
    if "OK" in upper:
        return data if isinstance(data, dict) else None
    raise OutboundError(
        "the provider rejected the request",
        key="provider_bad_response",
        placeholders={"body": text[:120]},
    )


# ----------------------------------------------------------------------
# שדות ההגדרה הייחודיים לספק
# ----------------------------------------------------------------------

# טווח ה-IPv6 שממנו ימות פונה. IPv6 בלבד: אם תתווסף אי פעם
# יציאה ב-IPv4, סינון לפי הטווח הזה יחסום אותה.
DEFAULT_IPS = "2a13:8140:1::/48"


def menu_fields(current: dict) -> dict:
    """מה שנוסף לשדות המשותפים במסך התפריט."""
    return {
        vol.Optional(
            "yemot_token",
            description={"suggested_value": str(current.get("yemot_token", "") or "")},
        ): str,
    }


def menu_save(user_input: dict) -> dict:
    return {"yemot_token": str(user_input.get("yemot_token", "") or "")}


def default_ips() -> str:
    """טווח ברירת המחדל לרשימת ההיתר."""
    return DEFAULT_IPS
