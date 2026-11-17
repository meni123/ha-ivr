"""הפעלת פעולה על ישות או על קבוצה, ומה לומר למתקשר על התוצאה.

כל הכשלים של הפעלה מגיעים לכאן, וכל אחד מקבל משפט משלו: "הפעולה
אינה קיימת עוד" אינו "המכשיר אינו תומך", ושניהם אינם "הערך אינו
תקין". המתקשר אינו רואה יומן, ולכן ההבחנה נעשית במה שהוא שומע.

סדר החריגות לפי ההיררכיה של `homeassistant.exceptions`:
`ServiceNotFound` ו-`ServiceNotSupported` יורשות מ-
`ServiceValidationError`, וזו ו-`Unauthorized` יורשות מ-
`HomeAssistantError`. לכן נתפסות מהספציפית לכללית.

אישור הביצוע: מחכים לשינוי מצב, וכשהפעולה קובעת ערך — לערך עצמו
במאפיין (בהירות, טמפרטורה, מיקום), לא רק ל-`state`. מצב מעבר
(`opening`, `locking`) הוא אישור שהפקודה התקבלה.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from collections.abc import Callable

from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, SERVICE_CALL_TIMEOUT, STATE_CHANGE_TIMEOUT

_LOGGER = logging.getLogger(__name__)

# כמה קריאות במקביל בקבוצה. מכשיר איטי אחד אינו מעכב את השאר, ובית
# עם חמישים נורות אינו מציף את הרשת בבת אחת.
GROUP_CONCURRENCY = 5

# מצבים שאומרים "הפקודה התקבלה ובביצוע".
TRANSITIONAL = frozenset({
    "opening", "closing", "locking", "unlocking", "arming", "disarming", "pending",
})

# דומיינים בלי מצב יעד: לחיצה, סצנה, הודעה. אין למה לחכות.
STATELESS = frozenset({
    "button", "input_button", "scene", "script", "notify", "tts", "conversation",
    "persistent_notification", "event", "todo", "calendar", "ai_task",
})
NO_WAIT_ACTIONS = frozenset({
    ("automation", "trigger"), ("remote", "send_command"), ("remote", "learn_command"),
    ("remote", "delete_command"), ("media_player", "play_media"),
    ("vacuum", "locate"), ("vacuum", "send_command"), ("camera", "snapshot"),
    ("update", "install"),
})

# שדות שהפעולה קובעת, והמאפיין שבו רואים שנקבעו: (מאפיין, המרה, סובלנות).
# None כמאפיין = ה-state עצמו.
_SCALE_PCT = 255 / 100
FIELD_TARGETS: dict[str, tuple[str | None, Callable[[float], float], float]] = {
    "brightness_pct": ("brightness", lambda v: round(_SCALE_PCT * v), 3),
    "brightness": ("brightness", lambda v: v, 3),
    "temperature": ("temperature", lambda v: v, 0.1),
    "target_temp_low": ("target_temp_low", lambda v: v, 0.1),
    "target_temp_high": ("target_temp_high", lambda v: v, 0.1),
    "humidity": ("humidity", lambda v: v, 1),
    "position": ("current_position", lambda v: v, 1),
    "tilt_position": ("current_tilt_position", lambda v: v, 1),
    "percentage": ("percentage", lambda v: v, 1),
    "volume_level": ("volume_level", lambda v: v, 0.02),
}
CHOICE_TARGETS: dict[str, str | None] = {
    "fan_mode": "fan_mode",
    "preset_mode": "preset_mode",
    "swing_mode": "swing_mode",
    "swing_horizontal_mode": "swing_horizontal_mode",
    "source": "source",
    "sound_mode": "sound_mode",
    "effect": "effect",
    "mode": "mode",
    "operation_mode": "operation_mode",
    "direction": "direction",
    "oscillating": "oscillating",
    "is_volume_muted": "is_volume_muted",
    "hvac_mode": None,
    "option": None,
}
# ערך 0 בשדות האלה מכבה: HA עובר ל-`turn_off`, ותריס במיקום 0 סגור.
ZERO_MEANS_OFF = {"brightness_pct": ("off",), "brightness": ("off",),
                  "percentage": ("off",), "position": ("closed", "closing")}

ACTION_TARGETS: dict[str, tuple[str, ...]] = {
    "turn_on": ("on",), "turn_off": ("off",),
    "lock": ("locked",), "unlock": ("unlocked", "open"), "open": ("open", "unlocked"),
    "open_cover": ("open",), "close_cover": ("closed",),
    "open_valve": ("open",), "close_valve": ("closed",),
    "alarm_disarm": ("disarmed",), "alarm_arm_home": ("armed_home",),
    "alarm_arm_away": ("armed_away",), "alarm_arm_night": ("armed_night",),
    "alarm_arm_vacation": ("armed_vacation",),
    "alarm_arm_custom_bypass": ("armed_custom_bypass",),
    "alarm_trigger": ("triggered",),
    "media_play": ("playing",), "media_pause": ("paused",),
    "start": ("cleaning",), "return_to_base": ("returning", "docked"),
    "start_mowing": ("mowing",), "dock": ("docked", "returning"),
}

# סטטוסים. המשמעות למתקשר נקבעת ב-`view`.
OK = "ok"
UNCONFIRMED = "unconfirmed"
TIMEOUT = "timeout"
UNAVAILABLE = "unavailable"
MISSING = "missing"
NOT_FOUND = "not_found"
NOT_SUPPORTED = "not_supported"
INVALID = "invalid"
SCHEMA = "schema"
UNAUTHORIZED = "unauthorized"
FAILED = "failed"
ERROR = "error"


@dataclass
class Outcome:
    """תוצאה של הפעלה, לישות אחת או לקבוצה."""

    status: str
    message: str = ""
    state: Any = None
    total: int = 0
    done: int = 0
    unavailable: int = 0
    failed: int = 0
    statuses: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.status in (OK, UNCONFIRMED, TIMEOUT)


def split_action(action: str, entity_domain: str) -> tuple[str, str]:
    """`homeassistant.turn_on` → ("homeassistant", "turn_on"). אחרת דומיין הישות."""
    if "." in action:
        domain, name = action.split(".", 1)
        return domain, name
    return entity_domain, action


def _exceptions():
    from homeassistant import exceptions as ha_exc  # noqa: PLC0415

    base = ha_exc.HomeAssistantError
    validation = getattr(ha_exc, "ServiceValidationError", base)
    return (
        getattr(ha_exc, "ServiceNotFound", None),
        getattr(ha_exc, "ServiceNotSupported", None),
        validation,
        getattr(ha_exc, "Unauthorized", None),
        base,
    )


def _is_schema_error(err: BaseException) -> bool:
    """שגיאת סכמה של voluptuous או של probatio (2026.9 ואילך)."""
    names = {cls.__name__ for cls in type(err).__mro__}
    module = type(err).__module__ or ""
    return bool(names & {"Invalid", "MultipleInvalid"}) or module.startswith(
        ("voluptuous", "probatio")
    )


def classify_error(hass: HomeAssistant, err: BaseException) -> tuple[str, str]:
    """הסטטוס וההודעה המתורגמת (אם יש) של חריגה, בסדר הנכון."""
    from . import i18n  # noqa: PLC0415

    not_found, not_supported, validation, unauthorized, base = _exceptions()
    message = i18n.exception_message(hass, err)
    if not_found is not None and isinstance(err, not_found):
        return NOT_FOUND, message
    if not_supported is not None and isinstance(err, not_supported):
        return NOT_SUPPORTED, message
    if isinstance(err, validation):
        return INVALID, message
    if unauthorized is not None and isinstance(err, unauthorized):
        return UNAUTHORIZED, message
    if isinstance(err, base):
        return FAILED, message
    if isinstance(err, TimeoutError):
        return TIMEOUT, ""
    if _is_schema_error(err):
        return SCHEMA, ""
    return ERROR, ""


def expected(action: str, data: dict, before) -> Callable[[Any], bool] | None:
    """תנאי שמזהה שהפעולה התבצעה, או None כשאין יעד ידוע."""
    for name, value in data.items():
        number = _num(value)
        if name in ZERO_MEANS_OFF and number == 0:
            states = ZERO_MEANS_OFF[name]
            return lambda s, states=states: s is not None and s.state in states
        if name in FIELD_TARGETS and number is not None:
            attr, convert, tolerance = FIELD_TARGETS[name]
            goal = convert(number)
            return lambda s, a=attr, g=goal, t=tolerance: (
                s is not None
                and (n := _num(s.attributes.get(a) if a else s.state)) is not None
                and abs(n - g) <= t + 1e-9
            )
        if name in CHOICE_TARGETS:
            attr = CHOICE_TARGETS[name]
            goal = str(value).lower()
            return lambda s, a=attr, g=goal: s is not None and str(
                s.attributes.get(a) if a else s.state
            ).lower() == g
    if action == "toggle" and before is not None:
        was = before.state
        return lambda s: s is not None and s.state != was
    if action in ACTION_TARGETS:
        states = ACTION_TARGETS[action]
        return lambda s: s is not None and s.state in states
    return None


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def needs_wait(domain: str, action: str) -> bool:
    return domain not in STATELESS and (domain, action) not in NO_WAIT_ACTIONS


def _safe_keys(data: dict) -> list[str]:
    """שמות השדות בלבד, ליומן. ערכים — קוד, טקסט מוכתב — לעולם לא."""
    return sorted(str(k) for k in data)


async def async_call_one(
    hass: HomeAssistant,
    entity_id: str,
    action: str,
    data: dict,
    *,
    entry_id: str = "",
) -> Outcome:
    """הפעלה על ישות אחת, והמתנה לאישור שהיא התבצעה."""
    entity_domain = entity_id.split(".", 1)[0]
    svc_domain, svc = split_action(action, entity_domain)

    before = hass.states.get(entity_id)
    if before is None:
        return Outcome(MISSING, total=1)
    # רק `unavailable` נחסם. `unknown` הוא מצב רגיל של כפתור או סצנה
    # שמעולם לא הופעלו, ושל מכשיר עם מצב משוער — ושם הפקודה היא בדיוק
    # מה שיקבע אותו.
    if before.state == "unavailable":
        return Outcome(UNAVAILABLE, state=before, total=1, unavailable=1)

    check = expected(svc, data, before)
    wait = needs_wait(entity_domain, svc)
    if check is not None and check(before) and svc != "toggle":
        # כבר במצב המבוקש. מפעילים בכל זאת (מכשיר עם מצב משוער
        # אולי טועה), אבל לא מחכים לשינוי שלא יבוא.
        wait = False

    future: asyncio.Future = asyncio.get_running_loop().create_future()
    unsub = None
    if wait:
        from homeassistant.helpers.event import async_track_state_change_event  # noqa: PLC0415

        @callback
        def _listener(event) -> None:
            new = event.data.get("new_state")
            if future.done():
                return
            if check is None or check(new) or (
                new is not None and new.state in TRANSITIONAL
            ):
                future.set_result(new)

        unsub = async_track_state_change_event(hass, [entity_id], _listener)

    try:
        try:
            async with asyncio.timeout(SERVICE_CALL_TIMEOUT):
                await hass.services.async_call(
                    svc_domain, svc, {"entity_id": entity_id, **data}, blocking=True
                )
        except Exception as err:  # noqa: BLE001 — מסווג ומוקרא, השיחה ממשיכה
            status, message = classify_error(hass, err)
            _log_failure(status, entity_id, svc_domain, svc, data, err)
            _report_issue(hass, entry_id, status, entity_id, f"{svc_domain}.{svc}")
            if status == TIMEOUT:
                return Outcome(TIMEOUT, state=hass.states.get(entity_id), total=1, done=1)
            return Outcome(status, message=message, state=hass.states.get(entity_id),
                           total=1, failed=1)

        _clear_issues(hass, entry_id, entity_id, f"{svc_domain}.{svc}")
        if not wait:
            # הרצת אוטומציה, סצנה או לחיצה אינן משנות מצב שיש טעם להקריא.
            # המתקשר שומע "בוצע", לא "האוטומציה כרגע מופעלת".
            return Outcome(OK, state=None, total=1, done=1)
        try:
            new = await asyncio.wait_for(asyncio.shield(future), STATE_CHANGE_TIMEOUT)
            return Outcome(OK, state=new or hass.states.get(entity_id), total=1, done=1)
        except TimeoutError:
            current = hass.states.get(entity_id)
            if check is None or check(current):
                return Outcome(OK, state=current, total=1, done=1)
            return Outcome(UNCONFIRMED, state=current, total=1, done=1)
    finally:
        if unsub is not None:
            unsub()
        if not future.done():
            future.cancel()


async def async_call_many(
    hass: HomeAssistant,
    entity_ids: list[str],
    action: str,
    data: dict,
    *,
    entry_id: str = "",
) -> Outcome:
    """פעולה על כל חברי הקבוצה, כל אחד בקריאה משלו ובמקביל.

    קריאה אחת לכולם הייתה נופלת כולה על מכשיר אחד תקוע, ובלי לדעת
    מי ביצע. כאן כל אחד נספר לחוד: "בוצע ב-3 מתוך 4, אחד לא זמין".
    """
    semaphore = asyncio.Semaphore(GROUP_CONCURRENCY)

    async def one(entity_id: str) -> Outcome:
        async with semaphore:
            return await async_call_one(hass, entity_id, action, data, entry_id=entry_id)

    results = await asyncio.gather(*(one(e) for e in entity_ids), return_exceptions=True)
    outcome = Outcome(OK, total=len(entity_ids))
    for result in results:
        if isinstance(result, BaseException):
            _LOGGER.error("A group member failed unexpectedly: %r", result)
            outcome.failed += 1
            outcome.statuses.append(ERROR)
            continue
        outcome.statuses.append(result.status)
        if result.status == UNAVAILABLE:
            outcome.unavailable += 1
        elif result.succeeded:
            outcome.done += 1
        elif result.status != MISSING:
            outcome.failed += 1
            outcome.message = outcome.message or result.message
    if outcome.done == 0:
        # אף אחד לא ביצע: הסטטוס הוא של הכשל הראשון, כדי שהמשפט יתאים.
        failures = [s for s in outcome.statuses if s not in (OK, UNCONFIRMED, TIMEOUT)]
        outcome.status = failures[0] if failures else MISSING
    return outcome


def _log_failure(status: str, entity_id: str, domain: str, action: str,
                 data: dict, err: BaseException) -> None:
    fields = _safe_keys(data)
    if status in (INVALID,):
        # שגיאת משתמש: ערך מחוץ לטווח, קוד שגוי. בלי traceback ובלי הערכים.
        _LOGGER.info("%s.%s on %s was rejected (fields %s): %s",
                     domain, action, entity_id, fields, type(err).__name__)
    elif status == ERROR:
        _LOGGER.error("%s.%s on %s failed unexpectedly (fields %s)",
                      domain, action, entity_id, fields, exc_info=err)
    elif status == TIMEOUT:
        _LOGGER.warning("%s.%s on %s did not finish in time", domain, action, entity_id)
    else:
        _LOGGER.warning("%s.%s on %s failed (%s, fields %s): %s",
                        domain, action, entity_id, status, fields, type(err).__name__)


# ----------------------------------------------------------------------
# תיקונים (Repairs)
# ----------------------------------------------------------------------

_ISSUE_KINDS = {NOT_FOUND: "action_missing", NOT_SUPPORTED: "action_unsupported",
                SCHEMA: "plan_drift"}


def _issue_id(kind: str, entity_id: str, action: str) -> str:
    return f"{kind}_{entity_id}_{action}".replace(".", "_")


def _report_issue(hass: HomeAssistant, entry_id: str, status: str,
                  entity_id: str, action: str) -> None:
    kind = _ISSUE_KINDS.get(status)
    if not kind:
        return
    try:
        from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

        ir.async_create_issue(
            hass,
            DOMAIN,
            _issue_id(kind, entity_id, action),
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=kind,
            translation_placeholders={"entity": entity_id, "action": action},
            data={"entry_id": entry_id},
        )
    except Exception:  # noqa: BLE001 — תיקון שלא נפתח אינו מפיל שיחה
        _LOGGER.debug("Could not open a repair issue", exc_info=True)


def _clear_issues(hass: HomeAssistant, entry_id: str, entity_id: str, action: str) -> None:
    try:
        from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

        for kind in _ISSUE_KINDS.values():
            ir.async_delete_issue(hass, DOMAIN, _issue_id(kind, entity_id, action))
    except Exception:  # noqa: BLE001
        pass
