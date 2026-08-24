"""טכנוליין.

תפריט DTMF, ערוץ סטרימינג דו-כיווני לעוזר הקולי, והתראות דרך
`campaignRun` עם `extensionActivation` — שמחייג ומחבר את הנמען
לשלוחת הסטרימינג, ולכן ההקראה נעשית ב-Home Assistant.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Final

import voluptuous as vol

from .. import history
from ..codec import TECHNOLINE_CODEC
from ..model import Action, CallContext, GoTo, Prompt, Say
from ..outbound import OutboundError

_LOGGER = logging.getLogger(__name__)

DRIVER_ID = "technoline"

# goTo מקבל מזהה שלוחה, ולכן פריט "מעבר" מוצע בתפריט.
SUPPORTS_GOTO = True

# `goTo` מקבל מזהה שלוחה, בעוד ה-`target` של `transfer_extension`
# הוא נתיב בעץ. שני דברים שונים באותה מערכת, ולכן הרמז מפורש.
GOTO_TARGET_HINT = "מזהה שלוחה אצל טכנוליין, למשל 200"

# יש ערוץ סטרימינג, ולכן מסך העוזר הקולי קיים באינטגרציה הזו.
# השם שמוצג בבורר הספק ובכותרת הרשומה.
NAME = "טכנוליין"

SUPPORTS_STREAM = True

# כתובת הסטרימינג מוגדרת בשלוחה אצלם, ולכן יש מה להדביק.
STREAM_URL_AT_PROVIDER = True

# מזהה הערוץ מגיע במסגרת הפתיחה ומאמת אותה, ולכן יש מה להזין.
NEEDS_CHANNEL_TOKEN = True

# יציאה מהעוזר היא `transfer_extension` לנתיב בעץ השלוחות.
NEEDS_RETURN_PATH = True


async def async_notify(
    hass, entry, message: str, phones: list[str], channel: str = "voice"
) -> None:
    """התראה לנמען: ההקראה של HA בערוץ הסטרימינג.

    `channel` מתקבל לאחידות עם שאר הדרייברים אך אינו בשימוש —
    לטכנוליין ערוץ אחד, ההזרמה. ראו `yemot.NOTIFY_CHANNELS`.

    עוברת דרך הלוויין, ולכן היא זהה בכל דבר ל-`send_call` —
    ההבדל היחיד הוא שהנמען מגיע מישות ולא משדה.
    """
    from ..const import SATELLITES  # noqa: PLC0415
    from homeassistant.exceptions import HomeAssistantError  # noqa: PLC0415

    lines = (hass.data.get(SATELLITES) or {}).get(entry.entry_id) or []
    if not lines:
        raise HomeAssistantError(
            translation_domain="ha_ivr",
            translation_key="no_satellite",
        )
    await lines[0].async_announce_message(message, phones)


# הערך שטכנוליין מחזירה כשפג הזמן ולא הוקש דבר.
TIMEOUT_VALUE = "ERROR"

# לא מתועדת מגבלה. הערך שמרני ומשמש לחיתוך בלבד.
MAX_MESSAGE_CHARS = 500

# התשובה היא JSON ולכן אין תווים אסורים — זה ההבדל הגדול מימות.
# קטיעת השמעה קיימת דרך ערוץ הבקרה של הסטרימינג
# (`{"type":"clear"}`) ולא דרך התפריט.

def _files(messages: list[Say]) -> list[dict[str, Any]]:
    """בניית מערך files.

    כל Say הופך לפריט נפרד. זה לא רק נאמנות למודל — התיעוד של
    טכנוליין ממליץ עליו במפורש: כל מחרוזת text ייחודית מתומללת
    פעם אחת ונשמרת בקאש, ולכן מקטעים קצרים וחוזרים עדיפים על
    משפט ארוך שמשתנה. פיצול המספרים שנדרש בימות בגלל הנקודה
    הוא בדיוק מה שמייעל את הקאש כאן.
    """
    out: list[dict[str, Any]] = []
    for item in messages:
        if item.kind == "text":
            out.append({"text": item.data[: MAX_MESSAGE_CHARS]})
        elif item.kind == "number":
            out.append({"number": item.data})
        elif item.kind == "digits":
            out.append({"digits": item.data})
        elif item.kind == "file":
            out.append({"fileName": item.data})
    return out


def parse(params: dict[str, str], body: dict | None = None) -> CallContext:
    """פענוח בקשה נכנסת.

    `body` מתקבל ואינו בשימוש: הנתיב וההקשה מגיעים בשם הפרמטר.
    החתימה אחידה לשלושת הדרייברים.
    """
    decoded = TECHNOLINE_CODEC.decode(params)
    digit = decoded.digit
    if digit == TIMEOUT_VALUE:
        # פג הזמן. הליבה תראה נתיב בלי הקשה ותשאל שוב מאותו מקום.
        digit = None
    return CallContext(
        call_id=params.get("PBXcallId", ""),
        caller=params.get("PBXphone", ""),
        did=params.get("PBXdid") or params.get("PBXnum", ""),
        path=decoded.path,
        digit=digit,
        step=decoded.step,
        hangup=params.get("PBXcallStatus") == "HANGUP",
        raw=params,
    )


def render(action: Action) -> list[dict[str, Any]]:
    """בניית גוף התשובה. תמיד מערך, גם למודול יחיד."""
    if isinstance(action, GoTo):
        chain: list[dict[str, Any]] = []
        if action.messages:
            chain.append(
                {"type": "simpleMessage", "files": _files(action.messages)}
            )
        chain.append({"type": "goTo", "goTo": action.target})
        return chain

    if isinstance(action, Prompt):
        return [
            {
                "type": "simpleMenu",
                "name": TECHNOLINE_CODEC.encode(action.step, action.at_path),
                # כל המקשים מועברים, לא רק המוגדרים. רשימה
                # מצומצמת גורמת למרכזייה לבלוע מקש שאינו בה:
                # ההקשה אינה מגיעה, אין שורה ביומן, והמתקשר שומע
                # שקט מוחלט. `ALL` הוא ברירת המחדל המתועדת, והוא
                # מעביר את הטיפול בבחירה שגויה לכאן — עם הודעה
                # קולית ומונה חזרות.
                "enabledKeys": "ALL",
                "timeout": action.timeout,
                "times": 3,
                "errorReturn": TIMEOUT_VALUE,
                # מוזיקה בזמן שהשרת מעבד — המקבילה של
                # api_wait_answer_music_on_hold בימות.
                "setMusic": "yes",
                "files": _files(action.messages),
            }
        ]

    # simpleMessage לבדו אינו מסיים: המרכזיה מנגנת ואז פונה שוב
    # לשרת. בלי פקודה שנייה בשרשרת נוצרת לולאה. לכן תמיד מצמידים
    # יעד מפורש.
    chain: list[dict[str, Any]] = [
        {"type": "simpleMessage", "files": _files(action.messages)}
    ]

    chain.append({"type": "hangup"})
    return chain


def respond(action: Action, cfg: dict | None = None):
    """בניית תשובת ה-HTTP בפורמט טכנוליין, ורישום מה נשלח."""
    from aiohttp import web  # noqa: PLC0415

    body = render(action)
    history.record("menu.reply", driver=DRIVER_ID, body=body)
    return web.json_response(body)


# ----------------------------------------------------------------------
# ערוץ הסטרימינג — מה שהליבה שואלת אותנו
# ----------------------------------------------------------------------


def detect(payload: dict) -> dict | None:
    """מסגרת הפתיחה של הספק: `{"type":"start", ...}`."""
    if str(payload.get("type", "")) != "start":
        return None
    return {
        "call_id": str(payload.get("callId", "")),
        "caller": str(payload.get("caller", "")),
        "token": str(payload.get("token", "")),
        "rate": _rate(str(payload.get("format", ""))),
    }


def _rate(raw: str) -> int | None:
    """קצב הדגימה מתוך `pcm16;rate=8000;ch=1`.

    נקרא ולא מונח: קצב אחר היה מייצר אודיו במהירות כפולה, כשל
    שנשמע כמו קולות צ׳יפמונק ולא כמו תקלה.
    """
    for part in raw.replace(",", ";").split(";"):
        key, _, value = part.partition("=")
        if key.strip().lower() == "rate" and value.strip().isdigit():
            return int(value.strip())
    return None


def clear_command() -> dict:
    """קטיעת השמעה. פקודת המשך — השיחה נמשכת."""
    return {"type": "clear"}


def hangup_command() -> dict:
    """ניתוק. פקודה סופית."""
    return {"type": "hangup"}


def leave_command(target: str) -> dict | None:
    """העברה לנתיב בעץ השלוחות.

    `target` הוא נתיב (`/`, `/2`) ולא מזהה שלוחה כמו ב-`goTo`.
    פקודה סופית: המרכזייה מנקזת עד 6 שניות אודיו, מבצעת, וסוגרת
    את הסוקט בעצמה — סגירה מצידנו קוטעת את משפט הסיום.

    בלי נתיב מוגדר אין מה לשלוח, והליבה סוגרת את הסוקט.
    """
    if not target:
        return None
    return {"type": "transfer_extension", "target": target}


# ---- קבועים של הספק ----

# שני האנדפוינטים יושבים על מארחים שונים. פנייה לאנדפוינט הנכון
# על המארח הלא נכון מתקבלת ונענית, ולכן הטעות אינה מתגלה כשגיאת
# רשת אלא כשגיאה לוגית של הספק.
#
#   campaignApi.php   https://api.tlivr.com
#   ivrFilesApi.php   https://app.tlivr.com
DEFAULT_CAMPAIGN_BASE: Final = "https://api.tlivr.com"
DEFAULT_FILES_BASE: Final = "https://app.tlivr.com"


# ---- שיחות יוצאות ----

TECHNOLINE_CAMPAIGN_PATH = "/campaignApi.php"
TECHNOLINE_FILES_PATH = "/ivrFilesApi.php"

def technoline_url(base: str, path: str) -> str:
    """כתובת מלאה מהבסיס המתאים לאנדפוינט."""
    default = (
        DEFAULT_FILES_BASE
        if path == TECHNOLINE_FILES_PATH
        else DEFAULT_CAMPAIGN_BASE
    )
    return f"{(base or default).rstrip('/')}{path}"


def _note(data: dict) -> str:
    """הסבר השגיאה מהספק.

    השדה אינו עקבי אצלם: `note` ברוב התשובות, `messige` בחלקן.
    """
    for field in ("note", "messige", "message"):
        value = data.get(field)
        if value:
            return str(value)
    return ""


def _raise_for_error(data: dict) -> None:
    """בדיקת `errorCode` בתשובה."""
    code = str(data.get("errorCode", ""))
    if code == "-99":
        raise OutboundError(
            "Technoline rejected the request: IP address not approved",
            key="provider_ip_denied",
        )
    if code == "-88":
        raise OutboundError(
            "Technoline returned -88, missing connection information",
            key="provider_missing_info",
            placeholders={"detail": _note(data)},
        )
    if code not in ("0", ""):
        raise OutboundError(
            f"Technoline rejected (errorCode {code})",
            key="provider_rejected",
            placeholders={"code": code, "detail": _note(data)},
        )


# ----------------------------------------------------------------------
# התראה קולית מהלוויין — `campaignRun` עם `extensionActivation`
# ----------------------------------------------------------------------

async def _stream_extension(hass, options: dict, api_key: str) -> str:
    """מזהה שלוחת הסטרימינג, מההגדרות או בגילוי.

    השלוחה היא היעד של `extensionActivation`, ולכן היא מה שמחבר
    את הנמען אלינו. מי שהגדיר אותה בטופס מקבל אותה; מי שלא —
    `foldersList` מחזיר את עץ השלוחות, ושלוחת `type=stream`
    היחידה בו היא התשובה.

    גילוי ולא ניחוש: אם נמצאו כמה, או אף אחת, הפעולה נעצרת
    ומבקשת הגדרה מפורשת. שלוחה שגויה כאן פירושה שיחה יוצאת
    שמגיעה למקום הלא נכון.
    """
    explicit = str(options.get("technoline_announce_extension", "") or "").strip()
    if explicit:
        return explicit

    from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
        async_get_clientsession,
    )

    url = technoline_url(
        str(options.get("technoline_files_base", "") or ""), TECHNOLINE_FILES_PATH
    )
    session = async_get_clientsession(hass)
    async with session.get(
        url, params={"action": "foldersList", "apiKey": api_key}
    ) as resp:
        raw = await resp.text()

    try:
        tree = json.loads(raw)
    except ValueError as err:
        raise OutboundError(
            "foldersList did not return JSON",
            key="provider_bad_response",
            placeholders={"body": raw[:200]},
        ) from err

    found: list[str] = []

    def walk(node) -> None:
        if not isinstance(node, dict):
            return
        for value in node.values():
            if not isinstance(value, dict):
                continue
            if value.get("type") == "stream" and value.get("id") is not None:
                found.append(str(value["id"]))
            walk(value.get("children") or {})

    walk(tree)

    if len(found) == 1:
        _LOGGER.info("Alert: discovered streaming extension %s", found[0])
        return found[0]
    raise OutboundError(
        f"found {len(found)} streaming extensions",
        key="extension_ambiguous",
        placeholders={"count": str(len(found))},
    )


async def async_announce(hass, entry, *, phones: list[str]) -> None:
    """שיגור התראה: חיוג שמחבר את הנמען לשלוחת הסטרימינג.

    `messagesType=extensionActivation` אינו משמיע דבר בעצמו —
    הוא מחייג ומכניס את הנמען לשלוחה. היתרון הוא שהאודיו אינו
    עובר דרך הספק כלל: מה שנשמע בקו הוא מה
    ש-`satellite.play_announcement` שולח לסוקט, בלי תקרת אורך
    ובלי מנוע הקראה זר. שני המצבים האחרים של `campaignRun`
    (`audioText` ו-`audioFile`) אינם עובדים.
    """
    from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
        async_get_clientsession,
    )

    options = dict(entry.options)

    api_key = str(options.get("technoline_api_key", "") or "").strip()
    if not api_key:
        raise OutboundError(
            "Technoline API key is missing", key="missing_api_key"
        )

    extension = await _stream_extension(hass, options, api_key)

    payload = {
        "action": "campaignRun",
        "apiKey": api_key,
        "messagesType": "extensionActivation",
        "extensionActivation": extension,
        "phones": ",".join(phones),
        # חובה לפי התיעוד, מינימום 5 דקות.
        "betweenRetries": 20,
        # ניסיון אחד בלבד: בחלוף 20 דקות ההתראה הממתינה כבר
        # פגה, והשיחה החוזרת הייתה מחברת את הנמען לעוזר הקולי
        # בלי הקשר.
        "dialRetries": 1,
        "title": "התראה מהבית החכם",
    }
    if bool(options.get("technoline_announce_hours", False)):
        # עצירה אוטומטית בין 23:00 ל-08:00. כבוי כברירת מחדל,
        # כי התראת בית שנחסמת בלילה מפספסת בדיוק את מה שהיא
        # נועדה לו.
        payload["reasonableHours"] = "yes"

    url = technoline_url(
        str(options.get("technoline_campaign_base", "") or ""),
        TECHNOLINE_CAMPAIGN_PATH,
    )
    masked = {**payload, "apiKey": f"***{api_key[-4:]}"}
    _LOGGER.info("Alert: dispatching to extension %s, %s recipients", extension, len(phones))
    _LOGGER.debug("Technoline <- [form] %s | %s", url, masked)
    history.record("technoline.announce", url=url, payload=masked)

    session = async_get_clientsession(hass)
    async with session.post(url, data=payload) as resp:
        raw = await resp.text()
        _LOGGER.debug("Technoline -> HTTP %s: %s", resp.status, raw[:600])
        history.record("technoline.response", status=resp.status, body=raw[:800])

    try:
        data = json.loads(raw)
    except ValueError as err:
        raise OutboundError(
            "the provider did not return JSON",
            key="provider_bad_response",
            placeholders={"body": raw[:200]},
        ) from err

    if not isinstance(data, dict):
        raise OutboundError(
            "the provider returned an unexpected structure",
            key="provider_bad_response",
            placeholders={"body": raw[:200]},
        )

    _raise_for_error(data)

    _LOGGER.info(
        "Alert dispatched, campaign %s, %s valid numbers, cost %s, "
        "balance %s. Waiting for the call",
        data.get("campaignId"), data.get("phones"),
        data.get("billing"), data.get("accountSum"),
    )
    return str(data.get("campaignId", "") or "")


async def async_call_outcome(hass, entry, campaign_id: str) -> str:
    """למה השיחה לא הגיעה — לפי הדוח של הספק.

    היומן המקומי יודע רק שאיש לא התקשר. `campaignReport` יודע אם
    חויג בכלל, אם הקו היה תפוס, ואם הנמען דחה — הבחנה שאוטומציה
    צריכה כדי להגיב: קו תפוס מצדיק מספר חלופי, מספר שגוי לא.

    שאילתת קריאה בלבד: אינה מחייגת ואינה מחייבת. רצה פעם אחת ורק
    בכשל, ולכן אינה מוסיפה השהיה למסלול התקין.
    """
    from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
        async_get_clientsession,
    )

    options = dict(entry.options)
    url = technoline_url(
        str(options.get("technoline_campaign_base", "") or ""),
        TECHNOLINE_CAMPAIGN_PATH,
    )
    payload = {
        "action": "campaignReport",
        "apiKey": str(options.get("technoline_api_key", "") or "").strip(),
        "campaignId": campaign_id,
    }

    session = async_get_clientsession(hass)
    async with session.post(url, data=payload) as resp:
        raw = await resp.text()
    _LOGGER.debug("Technoline -> campaign report %s: %s", campaign_id, raw[:400])

    try:
        data = json.loads(raw)
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""

    parts = []
    for call in data.get("calls") or []:
        if not isinstance(call, dict):
            continue
        if str(call.get("status", "")).upper() == "ANSWERED":
            continue
        # `q850Text` הוא ההסבר בעברית של הספק; `sipCode` הוא הקוד
        # הגולמי. שניהם נרשמים, כי מי שיקרא את זה בעוד חצי שנה
        # ירצה את הקוד ולא רק את התרגום.
        reason = str(call.get("q850Text") or call.get("sipText") or "").strip()
        code = str(call.get("sipCode") or "").strip()
        phone = str(call.get("phone") or "").strip()
        if reason or code:
            parts.append(f"{phone}: {reason or code}".strip(": "))
        elif phone:
            parts.append(f"{phone}: {call.get('status', 'לא נענה')}")

    return ", ".join(parts)


# ----------------------------------------------------------------------
# שדות ההגדרה הייחודיים לספק
# ----------------------------------------------------------------------


def menu_fields(current: dict) -> dict:
    def opt(key, default=""):
        return vol.Optional(
            key,
            description={"suggested_value": str(current.get(key, "") or default)},
        )

    return {
        opt("technoline_api_key"): str,
        opt("technoline_campaign_base", DEFAULT_CAMPAIGN_BASE): str,
        opt("technoline_files_base", DEFAULT_FILES_BASE): str,
        opt("technoline_announce_extension"): str,
        vol.Optional(
            "technoline_announce_hours",
            default=bool(current.get("technoline_announce_hours", False)),
        ): bool,
    }


def menu_save(user_input: dict) -> dict:
    return {
        "technoline_api_key": str(user_input.get("technoline_api_key", "") or ""),
        "technoline_campaign_base": str(
            user_input.get("technoline_campaign_base", "") or DEFAULT_CAMPAIGN_BASE
        ).strip(),
        "technoline_files_base": str(
            user_input.get("technoline_files_base", "") or DEFAULT_FILES_BASE
        ).strip(),
        "technoline_announce_extension": str(
            user_input.get("technoline_announce_extension", "") or ""
        ).strip(),
        "technoline_announce_hours": bool(
            user_input.get("technoline_announce_hours", False)
        ),
    }


def default_ips() -> str:
    return ""
