"""הגנה מפני ניחוש קוד בטלפון.

שלוש רמות, כי כל אחת לבדה נעקפת:

- שיחה: שלוש דחיות ברצף נועלות את פעולות הקוד עד סוף השיחה.
- מתקשר: ניתוק וחיוג חוזר עוקפים את השיחה, ולכן נספר גם לפי
  המספר — חמש דחיות בעשר דקות חוסמות אותו לרבע שעה.
- רשומה: מספר חסוי או מזויף עוקף את המתקשר, ולכן נספר גם הכול
  יחד — עשר דחיות בעשר דקות חוסמות את פעולות הקוד בקו כולו לרבע
  שעה, ופותחות תיקון שמודיע לבעל הבית.

המונים בזיכרון בלבד ומתאפסים בהפעלה מחדש. נעילה שורדת-ריסטרט הייתה
עלולה לנעול את בעל הבית עצמו בלי דרך חזרה מהטלפון. הקוד עצמו אינו
נשמר כאן ואינו נרשם — רק עצם הדחייה.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CALL_LIMIT = 3
CALLER_LIMIT = 5
ENTRY_LIMIT = 10
WINDOW = 600.0
LOCKOUT = 900.0

_DATA_KEY = "ha_ivr_code_guard"


@dataclass
class _Guard:
    calls: dict[str, int] = field(default_factory=dict)
    callers: dict[str, list[float]] = field(default_factory=dict)
    entry: list[float] = field(default_factory=list)
    caller_until: dict[str, float] = field(default_factory=dict)
    entry_until: float = 0.0


def _guard(hass: HomeAssistant, entry_id: str) -> _Guard:
    store = hass.data.setdefault(_DATA_KEY, {})
    return store.setdefault(entry_id, _Guard())


def normalize_caller(raw: str) -> str:
    """מספר אחיד לשני צידי ההשוואה: בלי `sip:`, דומיין, קידומת 972 או 0."""
    text = str(raw or "").strip().lower()
    if text.startswith(("sip:", "sips:", "tel:")):
        text = text.split(":", 1)[1]
    text = text.split("@", 1)[0].split(";", 1)[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("972"):
        digits = digits[3:]
    return digits.lstrip("0")


def mask(caller: str) -> str:
    """המספר ליומן: רק ארבע הספרות האחרונות."""
    digits = normalize_caller(caller)
    return f"***{digits[-4:]}" if digits else "(חסוי)"


def blocked(hass: HomeAssistant, entry_id: str, call_id: str, caller: str) -> bool:
    """האם פעולות קוד חסומות עכשיו לשיחה, למתקשר או לקו."""
    guard = _guard(hass, entry_id)
    now = time.monotonic()
    if guard.entry_until > now:
        return True
    number = normalize_caller(caller)
    if number and guard.caller_until.get(number, 0) > now:
        return True
    return guard.calls.get(call_id, 0) >= CALL_LIMIT


def record_failure(hass: HomeAssistant, entry_id: str, call_id: str, caller: str) -> None:
    """קוד נדחה. נספר בשלוש הרמות, ונועל כשעוברים את הסף."""
    guard = _guard(hass, entry_id)
    now = time.monotonic()
    guard.calls[call_id] = guard.calls.get(call_id, 0) + 1

    number = normalize_caller(caller)
    if number:
        recent = [t for t in guard.callers.get(number, []) if now - t < WINDOW]
        recent.append(now)
        guard.callers[number] = recent
        if len(recent) >= CALLER_LIMIT and guard.caller_until.get(number, 0) <= now:
            guard.caller_until[number] = now + LOCKOUT
            _LOGGER.warning(
                "Code actions blocked for caller %s for %d minutes after %d rejected codes",
                mask(caller), LOCKOUT // 60, len(recent),
            )

    guard.entry = [t for t in guard.entry if now - t < WINDOW]
    guard.entry.append(now)
    if len(guard.entry) >= ENTRY_LIMIT and guard.entry_until <= now:
        guard.entry_until = now + LOCKOUT
        _LOGGER.warning(
            "Code actions blocked on this line for %d minutes after %d rejected codes",
            LOCKOUT // 60, len(guard.entry),
        )
        _open_issue(hass, entry_id)


def record_success(hass: HomeAssistant, entry_id: str, call_id: str) -> None:
    """קוד התקבל: המונה של השיחה מתאפס. המונים הארוכים נשארים."""
    _guard(hass, entry_id).calls.pop(call_id, None)


def clear(hass: HomeAssistant, entry_id: str) -> None:
    (hass.data.get(_DATA_KEY) or {}).pop(entry_id, None)


def _open_issue(hass: HomeAssistant, entry_id: str) -> None:
    try:
        from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

        ir.async_create_issue(
            hass,
            DOMAIN,
            f"code_lockout_{entry_id}",
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="code_lockout",
            translation_placeholders={"minutes": str(int(LOCKOUT // 60))},
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not open the lockout repair", exc_info=True)
