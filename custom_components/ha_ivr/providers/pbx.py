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

# העוזר הקולי מטופל ב-voip של HA, לא בערוץ סטרימינג שלנו.
SUPPORTS_STREAM = False


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
    """
    parts = [
        str(item.data)
        for item in messages
        if item.kind in ("text", "raw", "number", "digits") and item.data
    ]
    return " ".join(parts)


def render(action: Action) -> dict[str, Any]:
    """פעולה → JSON נקי: מה לומר, אם זה תפריט, ואם לנתק."""
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
        return {
            "say": _say(action.messages),
            "menu": False,
            "goto": action.target,
            "hangup": False,
        }
    # Terminal — השמע וסיים.
    return {"say": _say(action.messages), "menu": False, "hangup": True}


def respond(action: Action, cfg: dict | None = None):
    """בניית תשובת ה-HTTP, ורישום מה נשלח."""
    from aiohttp import web  # noqa: PLC0415

    body = render(action)
    history.record("menu.reply", driver=DRIVER_ID, body=body)
    return web.json_response(body)


# ----------------------------------------------------------------------
# התראות — ha_ivr הוא המקור, המרכזייה מחייגת


async def async_notify(
    hass, entry, message: str, phones: list[str], channel: str = "voice"
) -> None:
    """התראה: POST ל-`call_trigger` שרץ במרכזייה, שמחייג ומשמיע.

    הנמענים מוגדרים כישויות `notify` כאן, וההתראה נשלחת דרך אותו
    webhook ש-call_trigger כבר חושף — במקום `rest_command` או
    `shell_command` ב-`configuration.yaml`. המרכזייה מסנתזת הקראה
    מקומית ומחייגת דרך הטראנק שנבחר.

    `channel` מתקבל לאחידות ואינו בשימוש — למרכזייה ערוץ יוצא אחד.
    """
    options = dict(entry.options)
    url = str(options.get("pbx_alert_url", "") or "").strip()
    trunk = str(options.get("pbx_trunk", "") or "").strip()
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


def menu_fields(current: dict) -> dict:
    """שדות ההתראות — כתובת ה-webhook של המרכזייה, הטראנק, והסוד.

    התפריט עצמו אינו זקוק לדבר; אלה משמשים רק את `async_notify`.
    """
    def opt(key: str):
        return vol.Optional(
            key, description={"suggested_value": str(current.get(key, "") or "")}
        )

    return {opt(key): str for key in _ALERT_KEYS}


def menu_save(user_input: dict) -> dict:
    return {key: str(user_input.get(key, "") or "") for key in _ALERT_KEYS}
