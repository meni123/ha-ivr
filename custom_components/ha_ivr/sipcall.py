"""שיחה בקו SIP ישיר.

כאן HA עצמו עונה לטלפון: מקריא את התפריט, אוסף הקשות, ומחבר את
המתקשר לעוזר הקולי. `sipline` נותן שיחה עם שמע ומקשים; מנוע התפריט
והלוויין הם אותם אלה שמשרתים את שאר המסלולים, ולכן התפריט שנבנה
בלוח המקשים נשמע כאן בדיוק כמו בכל מקום אחר.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from homeassistant.core import HomeAssistant

from . import history
from .audio import error_tone
from .config_shared import num
from .const import DEFAULT_EXIT_KEYS, DEFAULT_MAX_CALL_MINUTES, SATELLITES
from .model import CallContext, GoTo, Prompt, Say, spell_long_digits
from .outbound import OutboundError
from .sipline import Call, SipError, SipLine

_LOGGER = logging.getLogger(__name__)

RATE = 8000
FRAME_BYTES = 320  # 20 אלפיות שנייה של PCM, מה שהלוויין מצפה לקבל
FRAME_SEC = 0.02
_SILENT_FRAME = bytes(FRAME_BYTES)
# הפסקה קצרה בין משפט למשפט, כדי שאפשרויות התפריט לא יישמעו כרצף אחד.
_GAP = bytes(int(RATE * 0.25) * 2)
# מכשיר שמפסיק לשדר כשהמתקשר שותק: מעבר לפער הזה משלימים שקט בעצמנו.
_FILL_AFTER = 0.1
# המתנה אחרי שהנמען ענה, עד שהטלפון מגיע לאוזן.
_ANSWER_DELAY = 1.0
RING_TIMEOUT = 45.0
_ALERTS_AT_ONCE = 2


def clips(messages: list[Say]) -> list[str]:
    """פריטי ההשמעה → משפטים להקראה.

    מספר נדבק למה שלפניו, ומה שאחריו נדבק אליו: "הסלון כרגע", 23,
    "מעלות" הם משפט אחד ולא שלושה. כל פריט אחר הוא משפט משלו, עם
    פסיק לפני "הקש" ונקודה בסופו — הפיסוק הוא מה שנותן למנוע
    ההקראה את המנגינה.
    """
    out: list[str] = []
    glue = False
    for item in messages:
        if item.kind == "file" or not item.data:
            continue
        if item.kind in ("number", "digits"):
            text = str(item.data).strip()
            if item.kind == "digits":
                text = " ".join(text)
            if out:
                out[-1] = f"{out[-1]} {text}"
            else:
                out.append(text)
            glue = True
            continue
        text = spell_long_digits(item.data).strip()
        if not text:
            continue
        if glue and out:
            out[-1] = f"{out[-1]} {text}"
        else:
            out.append(text)
        glue = False
    return [
        text.replace(" הקש ", ", הקש ").rstrip("., ") + "."
        for text in out
        if text.strip("., ")
    ]


def _lines(hass: HomeAssistant, entry) -> list:
    return list((hass.data.get(SATELLITES) or {}).get(entry.entry_id) or [])


async def async_synthesize(hass: HomeAssistant, entry, text: str) -> bytes:
    """טקסט → PCM בקצב הקו, בקול של העוזר שנבחר לרשומה."""
    lines = _lines(hass, entry)
    if not lines:
        raise OutboundError(
            "there is no satellite entity for this entry", key="no_satellite"
        )
    return await lines[0].async_synthesize(text, RATE)


class _AssistSession:
    """מה שהלוויין רואה מהשיחה בזמן שהמתקשר מדבר עם העוזר."""

    def __init__(self, call: Call) -> None:
        self._call = call
        self.exiting = False
        # המתקשר ניתק, להבדיל מיציאה חזרה לתפריט.
        self.gone = False
        self.done = asyncio.Event()

    def playout_end(self) -> float:
        return self._call.playout_end()

    async def send_audio(self, pcm: bytes) -> None:
        self._call.send(pcm)

    async def hung_up(self) -> None:
        self.exiting = True
        self.gone = True
        self.done.set()

    async def leave(self) -> None:
        self.exiting = True
        self.done.set()

    async def close(self, reason: str) -> None:
        """העוזר ויתר — שתיקה ממושכת או כשל. חוזרים לתפריט, והוא
        כבר יודע לסיים שיחה שאיש אינו מקיש בה."""
        history.record("sip.assist_closed", reason=reason)
        self.exiting = True
        self.done.set()


class SipCallSession:
    """שיחה נכנסת אחת, מהמענה ועד הניתוק."""

    def __init__(self, hass: HomeAssistant, entry, call: Call) -> None:
        self.hass = hass
        self._entry = entry
        self._call = call
        self._loop = asyncio.get_running_loop()

    async def run(self) -> None:
        call = self._call
        history.record("sip.start", caller=call.caller, call_id=call.call_id[:12])
        _LOGGER.info("SIP line: call from %s", call.caller[-4:] or "(unidentified)")
        menu = asyncio.ensure_future(self._menu())
        ended = asyncio.ensure_future(call.ended.wait())
        try:
            await asyncio.wait({menu, ended}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (menu, ended):
                if not task.done():
                    task.cancel()
            results = await asyncio.gather(menu, ended, return_exceptions=True)
            if isinstance(results[0], Exception):
                _LOGGER.error(
                    "SIP line: the call failed", exc_info=results[0]
                )
            history.record(
                "sip.end", caller=call.caller, reason=call.reason or "menu ended"
            )

    # ---- התפריט ----

    async def _menu(self) -> None:
        from .view import async_menu_step  # noqa: PLC0415

        call = self._call
        path: tuple[str, ...] = ()
        digit: str | None = None
        empties = 0
        while not call.ended.is_set():
            ctx = CallContext(
                call_id=call.call_id,
                caller=call.caller,
                did=call.did,
                path=path,
                digit=digit,
                # הצעד עולה בכל סיבוב בלי הקשה; כך המנוע סופר השמעות
                # חוזרות ומסיים שיחה שננטשה.
                step=len(path) + 1 + empties,
            )
            action = await async_menu_step(self.hass, self._entry, ctx)

            if isinstance(action, Prompt):
                path = tuple(action.at_path)
                key = await self._ask(action)
                if key is None:
                    digit = None
                    empties += 1
                else:
                    digit = key
                    empties = 0
                continue

            await self._speak(action.messages)
            await self._played()
            if not isinstance(action, GoTo):
                return  # סיום: הושמע, ומנתקים.

            # בקו ישיר אין שלוחות: כל מעבר מחבר לעוזר הקולי, יהיה היעד
            # שנכתב בפריט אשר יהיה.
            if await self._assist():
                return
            path, digit, empties = (), None, 0
            self._drop_keys()

    def _drop_keys(self) -> None:
        keys = self._call.keys
        while not keys.empty():
            keys.get_nowait()

    async def _ask(self, prompt: Prompt) -> str | None:
        """משמיע ומחכה להקשה. הקשה באמצע ההשמעה קוטעת אותה."""
        call = self._call
        speak = asyncio.ensure_future(self._speak(prompt.messages))
        key = asyncio.ensure_future(call.keys.get())
        try:
            await asyncio.wait({speak, key}, return_when=asyncio.FIRST_COMPLETED)
            if not key.done():
                # ההקראה כבר בתור; הזמן להקיש נמדד מסופה.
                wait = max(0.0, call.playout_end() - self._loop.time())
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        asyncio.shield(key), wait + max(1, prompt.timeout)
                    )
            if key.done() and not key.cancelled():
                call.flush()
                return key.result()
            return None
        finally:
            for task in (speak, key):
                if not task.done():
                    task.cancel()
            await asyncio.gather(speak, key, return_exceptions=True)

    async def _speak(self, messages: list[Say]) -> None:
        """מסנתז הכול במקביל ומשמיע לפי הסדר — המשפט הראשון יוצא
        לקו בלי לחכות לאחרון."""
        texts = clips(messages)
        if not texts:
            return
        tasks = [asyncio.ensure_future(self._synth(text)) for text in texts]
        try:
            for task in tasks:
                pcm = await task
                self._call.send(pcm)
                self._call.send(_GAP)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _synth(self, text: str) -> bytes:
        try:
            return await async_synthesize(self.hass, self._entry, text)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            # צליל שגיאה במקום שתיקה: המתקשר יודע שמשהו לא הוקרא.
            _LOGGER.error("SIP line: the speech failed: %s", err)
            return error_tone(RATE)

    async def _played(self) -> None:
        """עד שכל מה שנשלח לקו נשמע, או שהשיחה נגמרה."""
        call = self._call
        while not call.ended.is_set():
            left = call.playout_end() - self._loop.time()
            if left <= 0:
                return
            await asyncio.sleep(min(left, 0.2))

    # ---- העוזר הקולי ----

    async def _assist(self) -> bool:
        """מחבר את המתקשר לעוזר. True אם השיחה נגמרה שם."""
        call = self._call
        session = _AssistSession(call)
        line = next(
            (ln for ln in _lines(self.hass, self._entry) if ln.attach(session, RATE)),
            None,
        )
        if line is None:
            _LOGGER.warning("SIP line: every assistant line is busy")
            call.send(error_tone(RATE))
            await self._played()
            return False

        options = self._entry.options
        exit_keys = {
            c
            for c in str(options.get("stream_exit_keys", DEFAULT_EXIT_KEYS) or "")
            if not c.isspace() and c != ","
        }
        minutes = int(num(options.get("stream_max_minutes"), DEFAULT_MAX_CALL_MINUTES))

        loop = self._loop
        last = loop.time()
        pending = b""

        def on_audio(pcm: bytes) -> None:
            nonlocal last, pending
            last = loop.time()
            pending += pcm
            while len(pending) >= FRAME_BYTES:
                line.on_chunk(pending[:FRAME_BYTES])
                pending = pending[FRAME_BYTES:]

        async def fill() -> None:
            # בלי זה שתיקה של המתקשר נראית ללוויין כקו שנפל, וסוף
            # הדיבור אינו מזוהה כי אין מסגרות שקט למדוד.
            while True:
                await asyncio.sleep(FRAME_SEC)
                if loop.time() - last > _FILL_AFTER:
                    line.on_chunk(_SILENT_FRAME)

        self._drop_keys()
        call.on_audio = on_audio
        filler = asyncio.ensure_future(fill())
        history.record("sip.assist", caller=call.caller, line=line.entity_id)
        try:
            await line.begin()
            async with asyncio.timeout(minutes * 60 if minutes > 0 else None):
                await self._assist_keys(session, line, exit_keys)
        except TimeoutError:
            _LOGGER.info("SIP line: the assistant call reached %d minutes", minutes)
            session.exiting = True
            session.gone = True
        finally:
            call.on_audio = None
            filler.cancel()
            await asyncio.gather(filler, return_exceptions=True)
            line.detach(session)
        if session.gone:
            return True
        await self._played()
        return call.ended.is_set()

    async def _assist_keys(self, session: _AssistSession, line, exit_keys: set[str]) -> None:
        call = self._call
        done = asyncio.ensure_future(session.done.wait())
        try:
            while not done.done():
                key = asyncio.ensure_future(call.keys.get())
                try:
                    await asyncio.wait(
                        {key, done}, return_when=asyncio.FIRST_COMPLETED
                    )
                finally:
                    if not key.done():
                        key.cancel()
                        await asyncio.gather(key, return_exceptions=True)
                if key.done() and not key.cancelled() and key.result() in exit_keys:
                    await line.request_leave()
        finally:
            if not done.done():
                done.cancel()
            await asyncio.gather(done, return_exceptions=True)


# ----------------------------------------------------------------------
# התראה יוצאת


async def _deliver(line: SipLine, phone: str, pcm: bytes) -> None:
    """חיוג לנמען אחד, השמעה, וניתוק. זורק SipError כשלא נענה."""
    call = await line.dial(phone, ring_timeout=RING_TIMEOUT)
    loop = asyncio.get_running_loop()
    try:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(call.ended.wait(), _ANSWER_DELAY)
        call.send(pcm)
        while not call.ended.is_set():
            left = call.playout_end() - loop.time()
            if left <= 0:
                break
            await asyncio.sleep(min(left, 0.2))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(call.ended.wait(), 0.5)
    finally:
        await call.hangup()


async def async_speech(hass: HomeAssistant, entry, message: str) -> bytes:
    """ההודעה כשמע מוכן לקו. זורק כשההקראה נכשלת."""
    text = " ".join(clips([Say("text", str(message))]))
    try:
        pcm = await async_synthesize(hass, entry, text)
    except OutboundError:
        raise
    except Exception as err:  # noqa: BLE001
        raise OutboundError(
            f"the speech failed: {err}", key="alert_failed",
            placeholders={"detail": str(err)},
        ) from err
    if not pcm:
        raise OutboundError("the speech came back empty", key="speech_not_wav")
    return pcm


async def async_deliver(
    line: SipLine, pcm: bytes, phones: list[str], message: str = ""
) -> list[tuple[str, str]]:
    """מחייג לנמענים ומשמיע להם את ההודעה, שניים בכל פעם — קו אחד
    אינו נושא יותר שיחות במקביל אצל רוב הספקים.

    מחזיר את מי שלא קיבל, עם הסיבה: `busy`, `no_answer`, `rejected`,
    `unreachable`, `auth`, או `invalid` למספר בלי ספרות.
    """
    numbers = ["".join(c for c in str(raw) if c.isdigit()) for raw in phones]
    failed = [(str(raw), "invalid") for raw, n in zip(phones, numbers) if not n]
    slots = asyncio.Semaphore(_ALERTS_AT_ONCE)

    async def one(number: str) -> tuple[str, str] | None:
        history.record("sip.alert", phone=number, text=message[:60])
        try:
            async with slots:
                await _deliver(line, number, pcm)
        except SipError as err:
            _LOGGER.info("SIP line: the call to %s failed: %s", number[-4:], err)
            history.record("sip.alert_failed", phone=number, why=err.kind)
            return (number, err.kind)
        # בלי השורה הזאת התראה שנשמעה והתראה שנקטעה באמצע נראות אותו דבר.
        history.record("sip.alert_done", phone=number)
        return None

    results = await asyncio.gather(*(one(n) for n in numbers if n))
    return failed + [r for r in results if r is not None]
