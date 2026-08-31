"""מרכזייה עצמית — Asterisk, FreeSWITCH, או כל PBX שמריץ את הגשר.

בניגוד לספקים המתארחים, כאן שני הקצוות שלנו: הגשר שרץ במרכזייה
שולח בקשה נקייה ומקבל תשובה נקייה. אין פורמט לא-מתועד לגלות דרך
שיחות חיות — החוזה מוגדר כאן, פעם אחת.

בשלב זה התפריט בלבד עובר דרך ha_ivr: הגשר שולח את מספר
המתקשר, הנתיב וההקשה, ומקבל טקסט להקראה ואת המקשים התקפים. העוזר
הקולי נשאר ב-`voip` של HA, וההתראות נשלחות מהמרכזייה. לכן אין כאן
ערוץ סטרימינג ואין מסלול יוצא.

### החוזה

בקשה (הגשר → ha_ivr), גוף JSON:

    {"caller": "0501234567", "path": "1/2", "digit": "3", "step": 4}

תשובה (ha_ivr → הגשר):

    {"say": "...", "menu": true, "keys": ["1","2","a"],
     "path": "1/2/3", "timeout": 10, "hangup": false}

`menu` אמת = לאסוף ספרה ולשלוח שוב מאותו `path`. `hangup` אמת =
לנתק אחרי ההקראה. `goto` (אם קיים) = להעביר להקשר במרכזייה.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from .. import history
from ..model import Action, CallContext, GoTo, Prompt, Say, Terminal
from ..outbound import OutboundError

_LOGGER = logging.getLogger(__name__)

DRIVER_ID = "pbx"

# השם שמוצג בבורר הספק ובכותרת הרשומה.
NAME = "מרכזייה עצמית"

# מעבר במרכזייה = `Goto` להקשר dialplan או שלוחת SIP.
SUPPORTS_GOTO = True
GOTO_TARGET_HINT = "יעד מעבר במרכזייה — הקשר dialplan או שלוחת SIP, למשל ha-assist"

# העוזר הקולי רץ דרך מנוע הלוויין של ha_ivr, כמו אצל הספקים המתארחים,
# אבל התחבורה היא AudioSocket על TCP במקום WebSocket: Asterisk מזרים
# את אודיו השיחה ל-`audiosocket.py`, והוא מזין ל-Assist ומחזיר הקראה.
# הדגל טוען את פלטפורמת הלוויין; `STREAM_URL_AT_PROVIDER` נשאר כבוי,
# ולכן אין כתובת wss להעתקה — החיבור מגיע מהדיאלפלן, לא מכתובת.
SUPPORTS_STREAM = True

# המרכזייה מחייגת דרך טראנק, וטראנק שונה נותן זיהוי יוצא שונה. הדגל
# פותח שדה טראנק אופציונלי לכל נמען ובשירות `send_call`, מעל טראנק
# ברירת המחדל של הרשומה. ספק בלי טראנקים אינו מצהיר עליו.
SUPPORTS_TRUNK = True

# פורט ברירת המחדל שעליו `audiosocket.py` מאזין. ההאזנה על loopback
# כברירת מחדל — HA ו-Asterisk על אותה קופסה — ומשתנה ב`הגדרות התפריט`
# למרכזייה במארח אחר.
AUDIOSOCKET_DEFAULT_HOST = "127.0.0.1"
AUDIOSOCKET_DEFAULT_PORT = 9010

# הגשר יושב ברשת המקומית ופונה ל-HA בכתובת פנימית — לא החיצונית
# שהספקים המתארחים פונים אליה מהאינטרנט. הדגל אומר לליבה להציג את
# הכתובת הפנימית להעתקה, ומשקף את היתרון: אין צורך בכתובת חיצונית.
PREFER_INTERNAL_URL = True


def parse(params: dict[str, str], body: dict | None = None) -> CallContext:
    """בקשה נכנסת מהגשר.

    הנתיב וההקשה מגיעים כשדות מפורשים ולא בשם הפרמטר: הגשר מחזיק
    את מצב השיחה ושולח אותו, ולכן אין צורך בקידוד חסר-המצב שנדרש
    מול ספק שרק מהדהד שם פרמטר. `params` ו-`body` ממוזגים כדי
    שהגשר יוכל לשלוח או בגוף או בשאילתה.
    """
    data = {**(params or {}), **(body or {})}
    path = tuple(p for p in str(data.get("path", "") or "").split("/") if p)
    digit = str(data.get("digit", "") or "").strip() or None
    try:
        step = int(data.get("step", 1) or 1)
    except (TypeError, ValueError):
        step = 1
    return CallContext(
        call_id=str(data.get("call_id", "")),
        caller=str(data.get("caller", "")),
        did=str(data.get("did", "")),
        path=path,
        digit=digit,
        step=step,
        hangup=str(data.get("hangup", "")).lower() in ("1", "true", "yes"),
        raw=data,
    )


def _say(messages: list[Say]) -> str:
    """שיטוח המסרים לטקסט אחד. הגשר מקריא אותו מקומית ב-TTS שלו.

    מספר נשלח כמחרוזת ספרות — מנוע ההקראה של הגשר קורא אותו כמספר.
    `file` מדולג: הוא נתיב אצל ספק, לא רלוונטי לגשר שמקבל טקסט.

    כל פריט הופך למשפט משלו — פסיק לפני "הקש", ונקודה בין הפריטים.
    מנוע ה-TTS המקומי מפסק לפי סימני פיסוק; בלי זה כל התפריט נשמע
    כמשפט אחד רצוף ("לתפריט מזגן הקש 1 לעוזר הקש 3...") בלי הפסקה
    בין האפשרויות. הפיצול למסרים נפרד נשמר לספקים אחרים; כאן, שם
    הכול מתאחד למחרוזת אחת, הפיסוק הוא מה שנותן את המנגינה.
    """
    parts = [
        str(item.data)
        for item in messages
        if item.kind in ("text", "raw", "number", "digits") and item.data
    ]
    if not parts:
        return ""
    parts = [p.replace(" הקש ", ", הקש ").rstrip("., ") for p in parts]
    return ". ".join(parts) + "."


def render(action: Action, uuid: str | None = None) -> dict[str, Any]:
    """פעולה → JSON נקי: מה לומר, אם זה תפריט, ואם לנתק.

    `uuid` מצורף ל-`goto`: אם היעד הוא הקשר העוזר הקולי, הדיאלפלן
    מריץ איתו `AudioSocket()`. יעד שאינו העוזר (שלוחת SIP) פשוט
    מתעלם ממנו.
    """
    if isinstance(action, Prompt):
        return {
            "say": _say(action.messages),
            "menu": True,
            "keys": sorted(action.allowed),
            "path": "/".join(action.at_path),
            "timeout": action.timeout,
            "hangup": False,
        }
    if isinstance(action, GoTo):
        body = {
            "say": _say(action.messages),
            "menu": False,
            "goto": action.target,
            "hangup": False,
        }
        if uuid:
            body["uuid"] = uuid
        return body
    # Terminal — השמע וסיים.
    return {"say": _say(action.messages), "menu": False, "hangup": True}


def respond(action: Action, cfg: dict | None = None):
    """בניית תשובת ה-HTTP, ורישום מה נשלח.

    כשהתשובה היא `goto`, נרשם UUID לעוזר הקולי ומצורף לתשובה: הדיאלפלן
    יעביר אותו ל-AudioSocket, ומסגרת הפתיחה תפתור אותו חזרה למתקשר.
    """
    from aiohttp import web  # noqa: PLC0415

    cfg = cfg or {}
    uuid = None
    if isinstance(action, GoTo) and cfg.get("entry_id"):
        from .. import audiosocket  # noqa: PLC0415

        uuid = audiosocket.new_call(
            entry_id=str(cfg["entry_id"]), caller=str(cfg.get("caller", ""))
        )
    body = render(action, uuid=uuid)
    history.record("menu.reply", driver=DRIVER_ID, body=body)
    return web.json_response(body)


# ----------------------------------------------------------------------
# התראות — ha_ivr הוא המקור, המרכזייה מחייגת


async def async_notify(
    hass, entry, message: str, phones: list[str], channel: str = "voice",
    trunk: str = "",
) -> None:
    """התראה: POST ל-`call_trigger` שרץ במרכזייה, שמחייג ומשמיע.

    הנמענים מוגדרים כישויות `notify` כאן, וההתראה נשלחת דרך אותו
    webhook ש-call_trigger כבר חושף — במקום `rest_command` או
    `shell_command` ב-`configuration.yaml`. המרכזייה מסנתזת הקראה
    מקומית ומחייגת דרך הטראנק שנבחר.

    `trunk` דורס את טראנק ברירת המחדל של הרשומה — נמען או שליחה
    יכולים לצאת בזיהוי אחר. ריק חוזר ל-`pbx_trunk`.

    `channel` מתקבל לאחידות ואינו בשימוש — למרכזייה ערוץ יוצא אחד.
    """
    options = dict(entry.options)
    url = str(options.get("pbx_alert_url", "") or "").strip()
    trunk = str(trunk or "").strip() or str(
        options.get("pbx_trunk", "") or ""
    ).strip()
    secret = str(options.get("pbx_alert_secret", "") or "")
    if not url:
        raise OutboundError(
            "the PBX alert webhook is not configured", key="pbx_no_alert_url"
        )
    if not trunk:
        raise OutboundError(
            "the PBX outbound trunk is not configured", key="pbx_no_trunk"
        )

    from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
        async_get_clientsession,
    )

    session = async_get_clientsession(hass)
    headers = {"X-Alert-Secret": secret} if secret else {}
    failed: list[str] = []
    for raw in phones:
        digits = "".join(c for c in str(raw) if c.isdigit())
        if not digits:
            failed.append(str(raw))
            continue
        payload = {"phone": digits, "trunk": trunk, "text": str(message)}
        masked = {**payload, "text": str(message)[:60]}
        history.record("pbx.alert", url=url, payload=masked)
        try:
            async with session.post(
                url, json=payload, headers=headers, timeout=10
            ) as resp:
                body = await resp.text()
                _LOGGER.info(
                    "PBX alert -> HTTP %s for %s: %s",
                    resp.status, digits[-4:], body[:120],
                )
                if resp.status != 200:
                    failed.append(digits)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("PBX alert to %s failed: %s", digits[-4:], err)
            failed.append(digits)

    # כשל חלקי הוא אזהרה — מי שקיבל, קיבל. כשל מלא הוא חריגה.
    if failed and len(failed) == len(phones):
        raise OutboundError(
            "the PBX alert service did not accept the call",
            key="pbx_alert_failed",
            placeholders={"failed": ", ".join(f[-4:] for f in failed)},
        )
    if failed:
        _LOGGER.warning("PBX: some recipients failed: %s", failed)


def default_ips() -> str:
    """הגשר יושב ברשת המקומית, בכתובת שמשתנה מהתקנה להתקנה. אין
    טווח ברירת מחדל — הטוקן הוא מה שמגן על נקודת הקצה."""
    return ""


_ALERT_KEYS = ("pbx_alert_url", "pbx_trunk", "pbx_alert_secret")

# שדות שיש להם ערך התחלתי משמעותי (בניגוד להתראות שריקות בטבע): כתובת
# ההאזנה של מאזין ה-AudioSocket לעוזר הקולי.
_FIELD_DEFAULTS = {
    "pbx_audiosocket_host": AUDIOSOCKET_DEFAULT_HOST,
    "pbx_audiosocket_port": str(AUDIOSOCKET_DEFAULT_PORT),
}
_MENU_KEYS = _ALERT_KEYS + tuple(_FIELD_DEFAULTS)


def menu_fields(current: dict) -> dict:
    """שדות הרשומה: התראות (webhook, טראנק, סוד) והאזנת ה-AudioSocket.

    התפריט עצמו אינו זקוק לדבר; אלה משמשים את `async_notify` ואת
    מאזין העוזר הקולי.
    """
    def opt(key: str):
        default = _FIELD_DEFAULTS.get(key, "")
        return vol.Optional(
            key,
            description={"suggested_value": str(current.get(key, "") or default)},
        )

    return {opt(key): str for key in _MENU_KEYS}


def menu_save(user_input: dict) -> dict:
    saved: dict[str, str] = {}
    for key in _MENU_KEYS:
        value = str(user_input.get(key, "") or "")
        # שדה כתובת שנשאר ריק חוזר לברירת המחדל, כדי שהמאזין תמיד יעלה.
        saved[key] = value or _FIELD_DEFAULTS.get(key, "")
    return saved


async def async_start_transport(hass, entry):
    """מרים את מאזין ה-AudioSocket לרשומה. נקרא פעם אחת מ-async_setup_entry.

    השרת משותף להגדרה — יש רשומת pbx אחת (unique_id לפי ספק). ה-UUID
    שנרשם ב-`respond` הוא שמפנה כל שיחה חזרה לרשומה ולמתקשר.
    """
    from .. import audiosocket  # noqa: PLC0415

    options = dict(entry.options)
    host = str(
        options.get("pbx_audiosocket_host", "") or AUDIOSOCKET_DEFAULT_HOST
    ).strip()
    try:
        port = int(
            options.get("pbx_audiosocket_port", AUDIOSOCKET_DEFAULT_PORT)
            or AUDIOSOCKET_DEFAULT_PORT
        )
    except (TypeError, ValueError):
        port = AUDIOSOCKET_DEFAULT_PORT
    return await audiosocket.async_start(hass, host, port)


async def async_stop_transport(server) -> None:
    """סגירת המאזין ב-unload."""
    from .. import audiosocket  # noqa: PLC0415

    await audiosocket.async_stop(server)
