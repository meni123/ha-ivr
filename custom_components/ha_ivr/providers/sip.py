"""קו SIP ישיר — Home Assistant נרשם לקו בעצמו, בלי מרכזייה באמצע.

מזינים שרת, שם משתמש וסיסמה של קו SIP רגיל, מכל ספק. HA נרשם אליו
כמו טלפון, עונה לשיחות, מקריא את התפריט, מחבר לעוזר הקולי ומחייג
התראות — הכול מתוך התהליך שלו. אין נקודת קצה ואין כתובת להדביק אצל
הספק: השיחה מגיעה בקו עצמו.

UDP, ‏G.711, ומקשים ב-RFC 2833 או ב-SIP INFO. בלי הצפנה ובלי TCP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from .. import history
from ..model import Action, CallContext
from ..outbound import OutboundError
from ..sipline import SipError, SipLine

_LOGGER = logging.getLogger(__name__)

DRIVER_ID = "sip"

NAME = "קו SIP ישיר"

# השיחה אינה מגיעה ב-HTTP, ולכן אין כתובת, טוקן או טווחי IP להגדיר.
HAS_ENDPOINT = False

# המעבר היחיד הוא לעוזר הקולי, שרץ כאן באותה שיחה.
SUPPORTS_GOTO = True
GOTO_ONLY_ASSIST = True
ASSIST_GOTO = "assist"
GOTO_TARGET_HINT = "לא בשימוש בקו ישיר — המעבר מחבר ישירות לעוזר הקולי"

SUPPORTS_STREAM = True

DEFAULT_PORT = 5060

_KEYS = ("sip_server", "sip_username", "sip_password", "sip_port")

# למה נמען לא קיבל את ההתראה, כפי שזה נכתב ביומן.
_WHY = {
    "busy": "תפוס",
    "no_answer": "לא ענה",
    "rejected": "נדחה",
    "unreachable": "אין קשר לספק",
    "auth": "ההזדהות נדחתה",
    "invalid": "מספר לא תקין",
}


@dataclass
class _Transport:
    hass: Any
    entry_id: str
    line: SipLine


# הקו של כל רשומה, כדי שההתראות יחייגו דרך ההרשמה שכבר קיימת.
_LINES: dict[str, SipLine] = {}


def parse(params: dict[str, str], body: dict | None = None) -> CallContext:
    """אין בקשות נכנסות ב-HTTP; ההקשר נבנה ב-`sipcall` מהשיחה עצמה."""
    raise NotImplementedError("the SIP line has no HTTP endpoint")


def respond(action: Action, cfg: dict | None = None) -> Action:
    """הפעולה חוזרת כמות שהיא — מי שמשמיע אותה הוא `sipcall`."""
    history.record("menu.reply", driver=DRIVER_ID, body=type(action).__name__)
    return action


# ----------------------------------------------------------------------
# הגדרות


def _settings(options: dict) -> dict[str, Any]:
    server = str(options.get("sip_server", "") or "").strip()
    port = options.get("sip_port")
    # מי שהדביק "שרת:פורט" בשדה אחד התכוון לדבר הברור.
    if server.count(":") == 1 and server.rsplit(":", 1)[1].isdigit():
        server, port = server.rsplit(":", 1)
    try:
        port = int(float(port or DEFAULT_PORT))
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    if not 0 < port < 65536:
        port = DEFAULT_PORT
    return {
        "server": server,
        "username": str(options.get("sip_username", "") or "").strip(),
        "password": str(options.get("sip_password", "") or ""),
        "port": port,
    }


def default_ips() -> str:
    return ""


def menu_fields(current: dict) -> dict:
    from homeassistant.helpers.selector import (  # noqa: PLC0415
        TextSelector, TextSelectorConfig, TextSelectorType,
    )

    def field(key: str, default: str = "", required: bool = True):
        marker = vol.Required if required else vol.Optional
        return marker(
            key, description={"suggested_value": str(current.get(key, "") or default)}
        )

    return {
        field("sip_server"): str,
        field("sip_username"): str,
        field("sip_password"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        field("sip_port", str(DEFAULT_PORT), required=False): str,
    }


async def async_menu_errors(hass, user_input: dict) -> dict[str, str]:
    """הרשמת ניסיון: פרטים שגויים נעצרים בטופס ולא בשיחה הראשונה."""
    settings = _settings(user_input)
    for key in ("server", "username", "password"):
        if not settings[key]:
            return {f"sip_{key}": "sip_missing"}
    # אותם פרטים שכבר רשומים עכשיו אינם צריכים הוכחה נוספת.
    if any(
        line.registered and line.settings == settings for line in _LINES.values()
    ):
        return {}
    trial = SipLine(**settings)
    try:
        await trial.start(keep=False)
        await trial.check()
    except SipError as err:
        _LOGGER.info("SIP line: the trial registration failed: %s", err)
        if err.kind == "auth":
            return {"sip_password": "sip_auth_failed"}
        return {"sip_server": "sip_unreachable"}
    except OSError as err:
        _LOGGER.info("SIP line: the trial registration failed: %s", err)
        return {"sip_server": "sip_unreachable"}
    finally:
        await trial.stop()
    return {}


def menu_save(user_input: dict) -> dict:
    settings = _settings(user_input)
    return {
        "sip_server": settings["server"],
        "sip_username": settings["username"],
        "sip_password": settings["password"],
        "sip_port": str(settings["port"]),
    }


# ----------------------------------------------------------------------
# הקו עצמו


async def async_start_transport(hass, entry) -> _Transport:
    """נרשם לקו ומתחיל לענות. נקרא פעם אחת מ-async_setup_entry."""
    from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

    from .. import sipcall  # noqa: PLC0415
    from ..const import DOMAIN  # noqa: PLC0415

    settings = _settings(dict(entry.options))
    issue_id = f"sip_line_{entry.entry_id}"

    def on_state(ok: bool, reason: str) -> None:
        history.record("sip.line", registered=ok, reason=reason)
        if ok:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
            return
        _LOGGER.warning("SIP line: not registered (%s)", reason)
        ir.async_create_issue(
            hass, DOMAIN, issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=(
                "sip_auth_failed" if reason == "auth" else "sip_unreachable"
            ),
            translation_placeholders={"server": settings["server"]},
        )

    async def on_call(call) -> None:
        await sipcall.SipCallSession(hass, entry, call).run()

    line = SipLine(**settings, on_call=on_call, on_state=on_state)
    await line.start()
    _LINES[entry.entry_id] = line
    return _Transport(hass, entry.entry_id, line)


async def async_stop_transport(transport: _Transport) -> None:
    """ביטול ההרשמה וסגירת השיחות ב-unload."""
    from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

    from ..const import DOMAIN  # noqa: PLC0415

    if _LINES.get(transport.entry_id) is transport.line:
        del _LINES[transport.entry_id]
    await transport.line.stop()
    ir.async_delete_issue(
        transport.hass, DOMAIN, f"sip_line_{transport.entry_id}"
    )


# ----------------------------------------------------------------------
# התראות


async def async_notify(
    hass, entry, message: str, phones: list[str], channel: str = "voice",
    trunk: str = "", caller_id: str = "", retries: int = 0,
) -> None:
    """התראה: HA מחייג בקו עצמו ומשמיע את ההודעה.

    ההקראה מסונתזת לפני החיוג, וכשל בה חוזר מיד למי ששלח. החיוג עצמו
    רץ ברקע — צלצול של עד 45 שניות אינו מעכב את האוטומציה, ומי שלא
    ענה נרשם ביומן. `channel`, `trunk`, `caller_id` ו-`retries`
    מתקבלים לאחידות ואינם בשימוש: לקו אחד יש זיהוי אחד.
    """
    from .. import sipcall  # noqa: PLC0415

    line = _LINES.get(entry.entry_id)
    if line is None or not line.registered:
        raise OutboundError(
            "the SIP line is not registered", key="sip_not_registered"
        )
    if not any(c.isdigit() for raw in phones for c in str(raw)):
        raise OutboundError("no valid phone numbers", key="no_valid_numbers")

    pcm = await sipcall.async_speech(hass, entry, message)

    async def deliver() -> None:
        failed = await sipcall.async_deliver(line, pcm, phones, str(message))
        if failed:
            _LOGGER.warning(
                "SIP line: the alert did not reach %s",
                ", ".join(f"{p[-4:]} ({_WHY.get(why, why)})" for p, why in failed),
            )

    entry.async_create_background_task(
        hass, deliver(), f"ha_ivr sip alert {entry.entry_id}"
    )
