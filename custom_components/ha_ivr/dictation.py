"""הכתבה בקול: טקסט חופשי לפעולה, דרך שלוחת הסטרימינג.

אין דרך להקיש "קנה חלב" בטלפון. בקו עם סטרימינג המתקשר עובר מהתפריט
לשלוחת העוזר, אומר את הטקסט, שומע אותו בחזרה, ומאשר בהקשה. רק אז
הפעולה מופעלת, והוא חוזר לתפריט.

התפריט והסטרימינג הם שני חיבורים נפרדים אצל הספק. מה שמחבר ביניהם
הוא כרטיס חד-פעמי: התפריט שומר אותו ומעביר את המתקשר, והסטרימינג
שולף אותו לפי מזהה השיחה או לפי מספר המתקשר. הכרטיס פג אחרי שתי
דקות גם אם איש לא שלף אותו — למשל כשהמתקשר ניתק בדיוק בהעברה.

הטקסט המוכתב אינו נרשם ביומן מעל debug, ואינו נשמר.
"""

from __future__ import annotations

import contextlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .const import CONF_GOTO_TARGET, SUBENTRY_TYPE_ASSISTANT, subentry_kind
from .model import GoTo, Say
from .security import normalize_caller

_LOGGER = logging.getLogger(__name__)

TICKET_TTL = 120.0
_DATA_KEY = "ha_ivr_dictation"


@dataclass
class Ticket:
    ticket_id: str
    entry_id: str
    entity_id: str
    action: str
    field: str
    data: dict
    max_length: int
    call_id: str
    caller: str
    label: str
    created: float = field(default_factory=time.monotonic)
    cancel: Any = None


def _store(hass: HomeAssistant) -> dict[str, Ticket]:
    return hass.data.setdefault(_DATA_KEY, {})


def _assistant_target(entry) -> str:
    """שלוחת הסטרימינג: היעד של פריט העוזר הקולי בתפריט."""
    for subentry in entry.subentries.values():
        if subentry_kind(subentry) == SUBENTRY_TYPE_ASSISTANT:
            target = str(subentry.data.get(CONF_GOTO_TARGET, "") or "").strip()
            if target:
                return target
    return ""


@callback
def async_start(hass: HomeAssistant, entry, node, path, ctx) -> GoTo | None:
    """שמירת כרטיס והעברה לשלוחת הסטרימינג. None אם אין לאן."""
    from . import registry  # noqa: PLC0415

    driver = registry.for_entry(entry)
    if not getattr(driver, "SUPPORTS_STREAM", False):
        return None
    target = _assistant_target(entry)
    if not target and getattr(driver, "DRIVER_ID", "") == "sip":
        # בקו ישיר כל מעבר מחבר לעוזר, בלי שלוחה.
        target = "assistant"
    if not target or not node.entity:
        return None

    store = _store(hass)
    caller = normalize_caller(ctx.caller)
    # כרטיס קודם של אותו מתקשר מבוטל: רק ההקשה האחרונה בתוקף.
    for old in [t for t in store.values() if t.entry_id == entry.entry_id and (
        (ctx.call_id and t.call_id == ctx.call_id) or (caller and t.caller == caller)
    )]:
        _discard(hass, old.ticket_id)

    ticket = Ticket(
        ticket_id=secrets.token_hex(8),
        entry_id=entry.entry_id,
        entity_id=str(node.entity),
        action=str(node.action or ""),
        field=str(node.dictate.get("field", "")),
        data=dict(node.data or {}),
        max_length=int(node.dictate.get("max_length") or 0),
        call_id=str(ctx.call_id or ""),
        caller=caller,
        label=str(node.say or ""),
    )
    store[ticket.ticket_id] = ticket
    try:
        from homeassistant.helpers.event import async_call_later  # noqa: PLC0415

        ticket.cancel = async_call_later(
            hass, TICKET_TTL, lambda _now, tid=ticket.ticket_id: _discard(hass, tid)
        )
    except Exception:  # noqa: BLE001 — בלי טיימר, הפקיעה נבדקת בשליפה
        ticket.cancel = None
    _LOGGER.debug("Dictation ticket for %s.%s", node.entity, ticket.action)
    return GoTo(target=target, messages=[Say("text", "מעביר להכתבה")])


@callback
def _discard(hass: HomeAssistant, ticket_id: str) -> None:
    ticket = _store(hass).pop(ticket_id, None)
    if ticket is not None and ticket.cancel is not None:
        with contextlib.suppress(Exception):
            ticket.cancel()


@callback
def claim(hass: HomeAssistant, entry_id: str, call_id: str, caller: str) -> Ticket | None:
    """שליפה אטומית של הכרטיס של השיחה הזו. לפי מזהה השיחה, אחרת לפי המספר."""
    store = _store(hass)
    now = time.monotonic()
    for stale in [t.ticket_id for t in store.values() if now - t.created > TICKET_TTL]:
        _discard(hass, stale)

    number = normalize_caller(caller)
    candidates = [t for t in store.values() if t.entry_id == entry_id]
    match = next((t for t in candidates if call_id and t.call_id == call_id), None)
    if match is None and number:
        match = next((t for t in candidates if t.caller == number), None)
    if match is None:
        return None
    _discard(hass, match.ticket_id)
    return match


@callback
def clear(hass: HomeAssistant, entry_id: str) -> None:
    """פריקה: כל הכרטיסים של הרשומה, וטיימרי הפקיעה שלהם."""
    for ticket_id in [t.ticket_id for t in _store(hass).values() if t.entry_id == entry_id]:
        _discard(hass, ticket_id)


def clean(text: str) -> str:
    """תמלול בלי רווחים ופיסוק בקצוות. ריק = לא נאמר דבר."""
    return " ".join(str(text or "").split()).strip(" .,!?;:-–—\n\t")
