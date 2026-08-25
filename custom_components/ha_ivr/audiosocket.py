"""תחבורת AudioSocket — Asterisk מזרים את אודיו השיחה על TCP פשוט.

תאום של `stream.py`: שם התחבורה היא WebSocket מול ספק מתארח; כאן זו
פרוטוקול ה-TLV של AudioSocket מול Asterisk מקומי ברשת. שתי התחבורות
מניעות את אותו `IvrSatellite` דרך אותו חוזה session:

    session.send_audio(pcm)   — אודיו החוצה לקו
    session.hung_up()         — המתקשר ניתק
    session.leave()           — יציאה לתפריט
    session.exiting           — האם השיחה בדרך החוצה

והלוויין מונע דרך `attach` / `on_chunk` / `begin` / `detach`.

המלכוד: AudioSocket אינו נושא שום מטא-דאטה מלבד UUID בן 16 בתים.
לכן ha_ivr מייצר את ה-UUID כשהוא מחזיר `goto` לעוזר הקולי (`new_call`),
רושם `UUID → מתקשר`, ומחזיר אותו בתשובה. הדיאלפלן מריץ
`AudioSocket(${uuid},HA:port)`, ומסגרת ה-`0x01` פותרת את השיחה חזרה.
כך הזיהוי, ההרשאות והלוג נשארים ב-ha_ivr — לא בסוקט חסר-ההקשר.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import struct
import time
import uuid as uuidlib

from homeassistant.core import HomeAssistant

from . import history
from .const import SATELLITES

_LOGGER = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# הפרוטוקול — כל הודעה היא TLV: בית סוג, אורך uint16 big-endian, מטען.
# https://docs.asterisk.org/Configuration/Channel-Drivers/AudioSocket/

_TYPE_TERMINATE = 0x00  # ניתוק. מטען ריק.
_TYPE_UUID = 0x01       # מזהה השיחה, 16 בתים בינריים. פעם אחת בפתיחה.
_TYPE_DTMF = 0x03       # ספרת DTMF (בית ASCII). *לא אומת* — ראה run().
_TYPE_ERROR = 0xFF      # שגיאה מ-Asterisk.
_TYPE_AUDIO = 0x10      # אודיו slin 8kHz (צורת האפליקציה).
# מנהל הערוץ ב-slin16 (Dial(AudioSocket/…)) משדר בסוג 0x12, פריים 640
# בתים. ל-PSTN אין בכך תועלת — המקור 8kHz — ולכן המסלול הזה הוא 0x10.

_HEADER = struct.Struct(">BH")  # סוג (1) + אורך (2, big-endian)

# אפליקציית AudioSocket מזרימה slin 8kHz. מסגרת 20ms = 160 דגימות × 2.
RATE = 8000
FRAME_BYTES = 320
FRAME_SEC = 0.02
_SILENCE = b"\x00" * FRAME_BYTES


# ----------------------------------------------------------------------
# מיפוי UUID → שיחה. ha_ivr ממלא אותו כשהוא מחזיר goto, לפני שהסוקט נפתח.

_PENDING: dict[str, dict] = {}

# רישום שלא נפתח לו סוקט (goto רגיל לשלוחת SIP, לא לעוזר) יימחק אחרי
# הזמן הזה, כדי שהמילון לא יגדל. מרווח נדיב — שיחה יכולה להתעכב.
_PENDING_TTL = 120.0


def new_call(*, entry_id: str, caller: str) -> str:
    """UUID חדש לשיחת עוזר קולי, רשום ומוכן לחיבור ה-AudioSocket.

    נקרא מ-`pbx.respond` כשהתשובה היא `goto`. מוחזר לדיאלפלן, שמריץ
    איתו `AudioSocket()`; המסגרת הראשונה על הסוקט (`0x01`) נושאת את
    אותם 16 בתים, ו-`_resolve` מוצא בחזרה מי בקו.
    """
    call_uuid = str(uuidlib.uuid4())
    register_call(call_uuid, entry_id=entry_id, caller=caller)
    return call_uuid


def register_call(call_uuid: str, *, entry_id: str, caller: str) -> None:
    """רישום שיחה צפויה, לפני שה-AudioSocket מתחבר.

    המפתח הוא ה-UUID באותיות קטנות ובלי מקפים, כדי שיתאים ל-16 הבתים
    שמגיעים במסגרת `0x01`. רישומים ישנים שלא נפתח להם סוקט נמחקים כאן.
    """
    _prune()
    _PENDING[_norm(call_uuid)] = {
        "entry_id": entry_id,
        "caller": caller,
        "at": time.monotonic(),
    }


def _prune() -> None:
    cutoff = time.monotonic() - _PENDING_TTL
    for key in [k for k, v in _PENDING.items() if v["at"] < cutoff]:
        _PENDING.pop(key, None)


def _norm(call_uuid: str) -> str:
    return call_uuid.replace("-", "").lower().strip()


def _resolve(raw16: bytes) -> dict | None:
    """16 הבתים מהמסגרת → השיחה שנרשמה, אם קיימת."""
    return _PENDING.pop(raw16.hex(), None)


# ----------------------------------------------------------------------
# מסגור וקריאה


def _frame(msg_type: int, payload: bytes = b"") -> bytes:
    return _HEADER.pack(msg_type, len(payload)) + payload


async def _read_exact(reader: asyncio.StreamReader, n: int) -> bytes | None:
    """קריאת n בתים בדיוק, או None בסוף הזרם."""
    try:
        data = await reader.readexactly(n)
    except (asyncio.IncompleteReadError, ConnectionError):
        return None
    return data


async def _read_message(
    reader: asyncio.StreamReader,
) -> tuple[int, bytes] | None:
    """הודעת TLV אחת, או None בסוף הזרם."""
    head = await _read_exact(reader, _HEADER.size)
    if head is None:
        return None
    msg_type, length = _HEADER.unpack(head)
    payload = await _read_exact(reader, length) if length else b""
    if payload is None:
        return None
    return msg_type, payload


# ----------------------------------------------------------------------
# שיחה אחת


class AudioSocketSession:
    """שיחה אחת מצד ה-TCP: מסגרות פנימה, אודיו החוצה.

    מממש את חוזה ה-session שהלוויין מצפה לו, בדיוק כמו `_Session`
    ב-`stream.py`, אבל על סוקט TCP ופרוטוקול TLV.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self.hass = hass
        self._reader = reader
        self._writer = writer
        self._entry = None
        self._satellite = None
        self._caller = ""
        self._uuid = ""
        self._seen = 0
        self.exiting = False
        # תור השידור ולולאת הקיצוב. `send_audio` דוחף לכאן וחוזר
        # מיד; `_tx_loop` מוציא בקצב 20ms. כך הלוויין לא נחסם, והפריימים
        # יוצאים בקצב אמת כפי ש-Asterisk מצפה.
        self._tx: asyncio.Queue[bytes] = asyncio.Queue()
        self._tx_task: asyncio.Task | None = None

    # -- מחזור החיים ---------------------------------------------------

    def _lines(self) -> list:
        data = (self.hass.data.get(SATELLITES) or {}).get(
            self._entry.entry_id if self._entry else None
        )
        return list(data or [])

    async def run(self) -> None:
        """הלולאה: מסגרת נכנסת → פעולה, עד ניתוק.

        DTMF (`0x03`): מגיע כבית ASCII. כאן מקומו לטפל במקשי יציאה —
        `request_leave` על מקש מוסכם — אבל בשלב זה רק מתועד כדי לא
        להניח מדיניות. מקשי היציאה יושבים באפשרויות הרשומה.
        """
        try:
            while True:
                msg = await _read_message(self._reader)
                if msg is None:
                    break
                msg_type, payload = msg
                self._seen += 1

                if msg_type == _TYPE_UUID:
                    if not await self._on_uuid(payload):
                        break
                elif msg_type == _TYPE_AUDIO:
                    if self._satellite is not None:
                        self._satellite.on_chunk(payload)
                elif msg_type == _TYPE_DTMF:
                    _LOGGER.debug("AudioSocket: DTMF %r", payload[:1])
                    # TODO: אם payload במקשי היציאה → self._satellite.request_leave()
                elif msg_type == _TYPE_TERMINATE:
                    break
                elif msg_type == _TYPE_ERROR:
                    _LOGGER.warning("AudioSocket: error frame %r", payload[:1])
        finally:
            await self._teardown()

    async def _on_uuid(self, raw16: bytes) -> bool:
        """מסגרת ה-UUID: פותרת את השיחה, תופסת קו, ומתחילה.

        False מסיים את החיבור — UUID לא מוכר, או שכל הקווים תפוסים.
        """
        call = _resolve(raw16)
        if call is None:
            _LOGGER.warning(
                "AudioSocket: unknown UUID %s — no call was registered", raw16.hex()
            )
            return False

        self._uuid = raw16.hex()
        self._caller = str(call.get("caller") or "")
        entry_id = call.get("entry_id")
        self._entry = self.hass.config_entries.async_get_entry(entry_id)
        if self._entry is None:
            _LOGGER.error("AudioSocket: entry %s is gone", entry_id)
            return False

        lines = self._lines()
        if not lines:
            _LOGGER.error(
                "AudioSocket: no satellite entity for entry %s", entry_id
            )
            return False

        for line in lines:
            if line.attach(self, RATE):
                self._satellite = line
                break
        else:
            _LOGGER.warning("AudioSocket: all lines busy, rejecting %s", self._caller)
            # כאן אפשר להזריק צליל "עמוס" (error_tone) לפני הסגירה.
            return False

        _LOGGER.info(
            "AudioSocket: line %s for %s", self._satellite.entity_id, self._caller
        )
        history.record(
            "audiosocket.start", caller=self._caller, uuid=self._uuid[:12]
        )
        self._tx_task = asyncio.ensure_future(self._tx_loop())
        await self._satellite.begin()
        return True

    async def _teardown(self) -> None:
        if self._tx_task is not None:
            self._tx_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tx_task
            self._tx_task = None
        if self._satellite is not None:
            self._satellite.detach(self)
            self._satellite = None
        with contextlib.suppress(Exception):
            self._writer.close()
            await self._writer.wait_closed()
        history.record(
            "audiosocket.end",
            caller=self._caller or "(unidentified)",
            frames=self._seen,
            exiting=self.exiting,
        )

    # -- חוזה ה-session (הלוויין קורא לאלה) ---------------------------

    async def send_audio(self, pcm: bytes) -> None:
        """PCM החוצה — נדחף לתור השידור וחוזר מיד.

        הקיצוב ל-20ms הוא של `_tx_loop`, לא כאן: הלוויין קורא לזה ואז
        ישן את משך הקליפ (`satellite.py:_send_audio`), והלולאה מקצבת
        אותו החוצה באותו משך בדיוק — כך הזמנים מתיישרים בלי המתנה
        כפולה. שפיכה ישירה לסוקט הייתה מציפה את Asterisk.
        """
        for i in range(0, len(pcm), FRAME_BYTES):
            frame = pcm[i : i + FRAME_BYTES]
            if len(frame) < FRAME_BYTES:  # ריפוד המסגרת האחרונה לשקט
                frame = frame + _SILENCE[len(frame):]
            self._tx.put_nowait(frame)

    async def _tx_loop(self) -> None:
        """מוציא מסגרת כל 20ms, בשעון monotonic כדי למנוע drift.

        אחרי שקט ארוך השעון מתאפס ל-`now` כדי שלא ייווצר "מרדף" של
        פריימים שנצברו. תור ריק = לא שולחים כלום; Asterisk מקצב את
        ה-RTP למתקשר בעצמו, ושתיקה על הקו היא המצב הטבעי בין תורות.
        """
        loop = asyncio.get_running_loop()
        next_t = loop.time()
        try:
            while not self._writer.is_closing():
                try:
                    frame = await asyncio.wait_for(self._tx.get(), timeout=0.5)
                except TimeoutError:
                    next_t = loop.time()  # התור התרוקן — אפס את השעון
                    continue
                now = loop.time()
                if now < next_t:
                    await asyncio.sleep(next_t - now)
                elif now > next_t + FRAME_SEC:
                    next_t = now  # פיגור גדול — התייצב מחדש
                with contextlib.suppress(ConnectionError, RuntimeError):
                    self._writer.write(_frame(_TYPE_AUDIO, frame))
                    await self._writer.drain()
                next_t += FRAME_SEC
        except asyncio.CancelledError:
            raise

    async def hung_up(self) -> None:
        """המתקשר ניתק (זוהה מהיעדר אודיו). סוגר את הקו."""
        self.exiting = True
        with contextlib.suppress(Exception):
            self._writer.write(_frame(_TYPE_TERMINATE))
            await self._writer.drain()
            self._writer.close()

    async def leave(self) -> None:
        """יציאה לתפריט. במרכזייה עצמית אין 'תפריט' מעבר לשלוחה,
        ולכן ברירת המחדל היא לנתק בנקי — הדיאלפלן ממשיך מהיכן שקרא
        ל-AudioSocket. אם רוצים חזרה לתפריט, כאן שולחים 0x00 ונותנים
        לדיאלפלן להעביר ל-Goto."""
        self.exiting = True
        await self.hung_up()


# ----------------------------------------------------------------------
# הרמת השרת


async def async_start(
    hass: HomeAssistant, host: str, port: int
) -> asyncio.AbstractServer:
    """מאזין TCP ל-AudioSocket. חיבור = שיחה = `AudioSocketSession.run`.

    מורם פעם אחת מ-`async_setup_entry` דרך `pbx.async_start_transport`,
    ונסגר ב-`async_stop`. ברירת המחדל היא האזנה על loopback — כשה-HA
    וה-Asterisk על אותה קופסה. למרכזייה במארח אחר מגדירים כתובת LAN,
    ומגנים בפיירוול: הפרוטוקול נטול הצפנה ואימות מעבר ל-UUID.
    """

    async def _on_connect(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        # TCP_NODELAY: מסגרות 20ms קטנות; בלי זה Nagle היה מאגד אותן
        # ומוסיף השהיה. חיוני לזרם אודיו בזמן אמת.
        sock = writer.get_extra_info("socket")
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        _LOGGER.debug("AudioSocket: connection from %s", peer)
        session = AudioSocketSession(hass, reader, writer)
        with contextlib.suppress(Exception):
            await session.run()

    server = await asyncio.start_server(_on_connect, host, port)
    _LOGGER.info("AudioSocket: listening on %s:%s", host, port)
    return server


async def async_stop(server: asyncio.AbstractServer | None) -> None:
    """סגירת המאזין. חיבורים פעילים נסגרים כשהשיחה מסתיימת."""
    if server is None:
        return
    server.close()
    with contextlib.suppress(Exception):
        await server.wait_closed()
