"""קו SIP אחד: הרשמה אצל הספק, שיחות נכנסות ויוצאות, וערוץ השמע.

Home Assistant נרשם לקו בעצמו, כמו טלפון — בלי מרכזייה באמצע. כאן
נמצאת התעבורה בלבד: UDP, G.711 ומקשים ב-RFC 2833. מה שקורה בתוך
השיחה (תפריט, הקראה, עוזר קולי) שייך ל-`sipcall`.

הקובץ אינו תלוי ב-Home Assistant, ולכן נבדק מול שרת מזויף על
127.0.0.1 בלי שום דבר מסביב.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import secrets
import socket
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from . import sip

_LOGGER = logging.getLogger(__name__)

T1 = 0.5          # שידור חוזר ראשון
T2 = 4.0          # תקרת המרווח בין שידורים חוזרים
TIMEOUT = 32.0    # ויתור על בקשה שלא נענתה
EXPIRES = 300
KEEPALIVE = 20.0  # שומר על הפתח ב-NAT פתוח בין הרשמה להרשמה
BACKOFF = (5, 10, 20, 40, 60)
RTP_TIMEOUT = 60.0  # רשת ביטחון לניתוק שלא הגיע
FRAME_SEC = 0.02


class SipError(Exception):
    """כשל מול הספק. `kind` אומר איזה: auth, unreachable, rejected, busy, no_answer."""

    def __init__(self, message: str, *, status: int = 0, kind: str = "rejected") -> None:
        super().__init__(message)
        self.status = status
        self.kind = kind


def _failure_kind(status: int) -> str:
    if status in (401, 403, 407):
        return "auth"
    if status in (486, 600, 603):
        return "busy"
    if status in (408, 480, 487):
        return "no_answer"
    return "rejected"


def caller_of(msg: sip.Message) -> str:
    """מספר המתקשר, בצורה שבה הוא נכתב ברשימת המורשים."""
    for name in ("from", "p-asserted-identity", "remote-party-id"):
        number = re.sub(r"\D", "", sip.user_of(msg.get(name)))
        if number:
            if number.startswith("972") and len(number) >= 11:
                number = "0" + number[3:]
            return number
    return ""


@dataclass
class _Dialog:
    """מה שצריך כדי לשלוח בקשה בתוך שיחה קיימת."""

    call_id: str
    local: str
    remote: str
    target: str
    routes: list[str]
    addr: tuple[str, int]
    cseq: int


@dataclass(frozen=True)
class _Invite:
    """ה-INVITE ששלחנו, כדי לאשר או לבטל אותו גם אחרי שוויתרנו."""

    uri: str
    via: str
    from_: str
    to: str
    call_id: str
    cseq: int


class _Txn:
    __slots__ = ("method", "queue")

    def __init__(self, method: str) -> None:
        self.method = method
        self.queue: asyncio.Queue[sip.Message] = asyncio.Queue()


class _SipProtocol(asyncio.DatagramProtocol):
    def __init__(self, line: SipLine) -> None:
        self._line = line

    def datagram_received(self, data: bytes, addr) -> None:
        self._line._on_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("SIP line: socket error: %s", exc)


class _RtpProtocol(asyncio.DatagramProtocol):
    def __init__(self, call: Call) -> None:
        self._call = call

    def datagram_received(self, data: bytes, addr) -> None:
        self._call._on_rtp(data, addr)

    def error_received(self, exc: Exception) -> None:
        pass


class Call:
    """שיחה אחת: מקשים נכנסים, שמע לשני הכיוונים, וניתוק."""

    def __init__(self, line: SipLine, *, call_id: str, caller: str, did: str,
                 direction: str) -> None:
        self._line = line
        self.call_id = call_id
        self.caller = caller
        self.did = did
        self.direction = direction
        self.keys: asyncio.Queue[str] = asyncio.Queue()
        self.ended = asyncio.Event()
        self.reason = ""
        self.answered = False
        # נקרא על כל חבילת שמע, עם PCM של 16 סיביות ב-8000 הרץ.
        self.on_audio: Callable[[bytes], None] | None = None

        self._loop = asyncio.get_running_loop()
        self._transport: asyncio.DatagramTransport | None = None
        self._port = 0
        self._pt = sip.PT_ALAW
        self._event_pt: int | None = None
        self._remote: tuple[str, int] | None = None
        self._latched: tuple[str, int] | None = None
        self._last_rx = 0.0
        self._out: deque[bytes] = deque()
        self._tx_task: asyncio.Task | None = None
        self._last_event: tuple[str, int] | None = None
        self._last_key = ("", "", 0.0)

        self._session = secrets.randbits(31)
        self._local_tag = sip.new_tag()
        self._dialog: _Dialog | None = None
        self._acked = asyncio.Event()
        self._ack: tuple[bytes, tuple[str, int]] | None = None
        self._cancelled = False

    # ---- שמע יוצא ----

    def send(self, pcm: bytes) -> None:
        """PCM של 16 סיביות ב-8000 הרץ, לתור ההשמעה."""
        if self.ended.is_set() or not pcm:
            return
        data = sip.encode(pcm, self._pt)
        pad = bytes([sip.SILENCE[self._pt]])
        for start in range(0, len(data), sip.FRAME):
            self._out.append(data[start:start + sip.FRAME].ljust(sip.FRAME, pad))

    def flush(self) -> None:
        """מה שטרם הושמע נזרק — המתקשר הקיש באמצע."""
        self._out.clear()

    def playout_end(self) -> float:
        """הרגע, בשעון הלולאה, שבו התור יסיים להתנגן."""
        return self._loop.time() + len(self._out) * FRAME_SEC

    async def hangup(self) -> None:
        dialog, self._dialog = self._dialog, None
        self._finish("local hangup")
        if dialog is not None:
            await self._line._bye(dialog)

    # ---- פנימי ----

    async def _open_media(self) -> None:
        self._transport, _ = await self._loop.create_datagram_endpoint(
            lambda: _RtpProtocol(self), local_addr=("0.0.0.0", 0)
        )
        self._port = self._transport.get_extra_info("sockname")[1]
        self._last_rx = self._loop.time()

    def _start_media(self, remote: tuple[str, int], pt: int,
                     event_pt: int | None) -> None:
        self._pt = pt
        self._event_pt = event_pt
        if remote[1] and remote[0] != "0.0.0.0":
            self._remote = remote
            self._latched = None
        if self._tx_task is None:
            self._tx_task = self._line._spawn(self._tx_loop())

    async def _tx_loop(self) -> None:
        """חבילה כל 20 אלפיות שנייה, תמיד — שמע מהתור או שקט.

        הרצף הקבוע הוא גם מה שמחזיק את הפתח ב-NAT פתוח, וגם מה
        שמלמד את שרת המדיה של הספק לאן לשלוח את השמע של המתקשר.
        """
        loop = self._loop
        seq = secrets.randbits(15)
        ts = secrets.randbits(30)
        ssrc = secrets.randbits(32)
        silence = bytes([sip.SILENCE[self._pt]]) * sip.FRAME
        first = True
        next_at = loop.time()
        while not self.ended.is_set():
            now = loop.time()
            if now - self._last_rx > RTP_TIMEOUT:
                _LOGGER.info("SIP line: no audio for %ds, hanging up", RTP_TIMEOUT)
                self._line._spawn(self.hangup())
                return
            if self._remote is not None and self._transport is not None:
                payload = self._out.popleft() if self._out else silence
                self._transport.sendto(
                    sip.rtp_packet(self._pt, seq, ts, ssrc, payload, first),
                    self._remote,
                )
                first = False
                seq += 1
                ts += sip.FRAME
            next_at += FRAME_SEC
            delay = next_at - loop.time()
            if delay < -0.2:  # הלולאה נתקעה; לא רודפים אחרי מה שאבד
                next_at = loop.time()
                delay = 0.0
            await asyncio.sleep(max(0.0, delay))

    def _on_rtp(self, data: bytes, addr) -> None:
        packet = sip.rtp_parse(data)
        if packet is None or self.ended.is_set():
            return
        now = self._loop.time()
        addr = (addr[0], addr[1])
        if addr != self._latched:
            # עונים לאן שממנו השמע מגיע בפועל, לא למה שנכתב ב-SDP.
            # מקור אחר מחליף את הנוכחי רק אם הנוכחי השתתק.
            if self._latched is not None and now - self._last_rx < 1.0:
                return
            self._latched = self._remote = addr
        self._last_rx = now
        if packet.pt == self._event_pt:
            event = sip.rtp_event(packet.payload)
            # הקשה אחת נשלחת בכמה חבילות עם אותה חותמת זמן.
            if event and (event[0], packet.ts) != self._last_event:
                self._last_event = (event[0], packet.ts)
                self._key(event[0], "rtp")
            return
        if packet.pt in sip.SILENCE and packet.payload and self.on_audio is not None:
            try:
                self.on_audio(sip.decode(packet.payload, packet.pt))
            except Exception:  # noqa: BLE001
                _LOGGER.exception("SIP line: the audio handler failed")

    def _key(self, digit: str, source: str) -> None:
        """מקש מהמתקשר. ספק ששולח כל מקש בשתי דרכים נספר פעם אחת."""
        now = self._loop.time()
        last, origin, at = self._last_key
        if digit == last and source != origin and now - at < 1.0:
            return
        self._last_key = (digit, source, now)
        self.keys.put_nowait(digit)

    def _finish(self, reason: str) -> None:
        if self.ended.is_set():
            return
        self.reason = reason
        self.ended.set()
        self.on_audio = None
        self._out.clear()
        if self._tx_task is not None:
            self._tx_task.cancel()
        if self._transport is not None:
            self._transport.close()
        self._line._calls.pop(self.call_id, None)


class SipLine:
    """הרשמה לקו אחד, וכל השיחות שעוברות בו."""

    def __init__(
        self,
        *,
        server: str,
        username: str,
        password: str,
        port: int = 5060,
        on_call: Callable[[Call], Awaitable[None]] | None = None,
        on_state: Callable[[bool, str], None] | None = None,
        max_calls: int = 4,
    ) -> None:
        self._server = server.strip()
        self._port = int(port or 5060)
        self._username = username
        self._password = password
        self._on_call = on_call
        self._on_state = on_state
        self._max_calls = max_calls

        self._domain = self._server if self._port == 5060 else f"{self._server}:{self._port}"
        self._aor = f"sip:{self._username}@{self._domain}"
        self._transport: asyncio.DatagramTransport | None = None
        self._local_ip = "0.0.0.0"
        self._local_port = 0
        self._addr: tuple[str, int] | None = None
        self._peers: set[str] = set()
        self._strangers: set[str] = set()

        self._pending: dict[str, _Txn] = {}
        self._zombies: dict[str, tuple[float, _Invite, tuple[str, int]]] = {}
        self._replies: dict[tuple[str, int, str], tuple[float, bytes]] = {}
        self._calls: dict[str, Call] = {}
        self._tasks: list[asyncio.Task] = []
        self._spawned: set[asyncio.Task] = set()

        self._expires = EXPIRES
        self._reg_call_id = sip.new_call_id()
        self._reg_tag = sip.new_tag()
        self._reg_cseq = 0
        self._reported: bool | None = None
        self.registered = False
        self.reason = ""

    # ---- חיים ----

    async def start(self, *, keep: bool = True) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _SipProtocol(self), local_addr=("0.0.0.0", 0)
        )
        self._local_port = self._transport.get_extra_info("sockname")[1]
        if keep:
            self._tasks = [
                loop.create_task(self._keep_registered()),
                loop.create_task(self._keepalive()),
            ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        for call in list(self._calls.values()):
            with contextlib.suppress(Exception):
                await call.hangup()
        if self.registered and self._addr is not None:
            with contextlib.suppress(SipError):
                await self._register(0, timeout=2.0)
        self.registered = False
        spawned = list(self._spawned)
        for task in spawned:
            task.cancel()
        await asyncio.gather(*spawned, return_exceptions=True)
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    async def check(self, timeout: float = 6.0) -> None:
        """הרשמת ניסיון: מצליחה, או זורקת SipError שמסביר למה לא."""
        await self._resolve()
        await self._register(60, timeout=timeout)
        with contextlib.suppress(SipError):
            await self._register(0, timeout=2.0)

    @property
    def calls(self) -> int:
        return len(self._calls)

    @property
    def settings(self) -> dict:
        """הפרטים שהקו נרשם איתם, להשוואה מול טופס שנשמר שוב."""
        return {
            "server": self._server, "username": self._username,
            "password": self._password, "port": self._port,
        }

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.get_running_loop().create_task(coro)
        self._spawned.add(task)
        task.add_done_callback(self._spawned.discard)
        return task

    # ---- הרשמה ----

    async def _resolve(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(
                self._server, self._port, family=socket.AF_INET,
                type=socket.SOCK_DGRAM,
            )
            ips = list(dict.fromkeys(info[4][0] for info in infos))
            if not ips:
                raise OSError("no address")
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect((ips[0], self._port))
                self._local_ip = probe.getsockname()[0]
            finally:
                probe.close()
        except OSError as err:
            raise SipError(
                f"Cannot reach {self._server}: {err}", kind="unreachable"
            ) from err
        self._addr = (ips[0], self._port)
        self._peers = set(ips)

    @property
    def _contact(self) -> str:
        return f"<sip:{self._username}@{self._local_ip}:{self._local_port}>"

    def _via(self, branch: str) -> str:
        return f"SIP/2.0/UDP {self._local_ip}:{self._local_port};branch={branch};rport"

    def _auth(self, auth, method: str, uri: str) -> list[tuple[str, str]]:
        if auth is None:
            return []
        name, challenge = auth
        return [(name, sip.authorization(
            challenge, method=method, uri=uri,
            username=self._username, password=self._password,
        ))]

    async def _register(self, expires: int, *, timeout: float = TIMEOUT) -> int:
        """הרשמה אחת (או ביטול, עם 0). מחזירה לכמה שניות היא תקפה."""
        uri = f"sip:{self._domain}"
        resp = None
        for _ in range(2):
            asked = expires

            def make(auth, asked=asked):
                self._reg_cseq += 1
                branch = sip.new_branch()
                headers = [
                    ("Via", self._via(branch)),
                    ("Max-Forwards", "70"),
                    ("From", f"<{self._aor}>;tag={self._reg_tag}"),
                    ("To", f"<{self._aor}>"),
                    ("Call-ID", self._reg_call_id),
                    ("CSeq", f"{self._reg_cseq} REGISTER"),
                    ("Contact", self._contact),
                    ("Expires", str(asked)),
                    ("User-Agent", sip.USER_AGENT),
                    *self._auth(auth, "REGISTER", uri),
                ]
                return sip.build(f"REGISTER {uri} SIP/2.0", headers), branch, None

            resp = await self._request("REGISTER", make, self._addr, timeout=timeout)
            minimum = resp.get("min-expires")
            if resp.status == 423 and expires and minimum.isdigit():
                expires = self._expires = int(minimum)
                continue
            break
        if not 200 <= resp.status < 300:
            kind = "auth" if resp.status in (401, 403, 404, 407) else "rejected"
            raise SipError(
                f"Registration refused: {resp.status} {resp.reason}",
                status=resp.status, kind=kind,
            )
        for contact in resp.all("contact"):
            if f"@{self._local_ip}:{self._local_port}" in contact:
                found = re.search(r";\s*expires=(\d+)", contact)
                if found:
                    return int(found.group(1))
        granted = resp.get("expires")
        return int(granted) if granted.isdigit() else expires

    async def _keep_registered(self) -> None:
        """נרשם, מרענן לפני שההרשמה פגה, ומנסה שוב כשהיא נכשלת."""
        failures = 0
        while True:
            try:
                if self._addr is None:
                    await self._resolve()
                granted = await self._register(self._expires)
            except SipError as err:
                failures += 1
                self.registered = False
                self.reason = str(err)
                if failures == 1:
                    _LOGGER.warning(
                        "SIP line: registration at %s failed: %s", self._server, err
                    )
                if err.kind == "unreachable":
                    self._addr = None  # הכתובת תיבדק מחדש בניסיון הבא
                # כשל רשת רגעי אינו תקלה. סיסמה שגויה — כן, ומיד.
                if failures == 3 or err.kind == "auth":
                    self._report(False, err.kind)
                delay = BACKOFF[min(failures, len(BACKOFF)) - 1]
            except Exception:  # noqa: BLE001
                _LOGGER.exception("SIP line: registration crashed")
                delay = BACKOFF[-1]
            else:
                if not self.registered:
                    _LOGGER.info("SIP line: registered at %s", self._server)
                failures = 0
                self.registered = True
                self.reason = ""
                self._report(True, "")
                delay = max(15.0, min(granted, self._expires) / 2)
            await asyncio.sleep(delay)

    def _report(self, ok: bool, reason: str) -> None:
        if self._reported is ok or self._on_state is None:
            return
        self._reported = ok
        try:
            self._on_state(ok, reason)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("SIP line: the state handler failed")

    async def _keepalive(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(KEEPALIVE)
            if self._addr is not None:
                self._send(b"\r\n\r\n", self._addr)
            now = loop.time()
            for cache in (self._zombies, self._replies):
                for key in [k for k, v in cache.items() if v[0] < now]:
                    del cache[key]

    # ---- בקשות יוצאות ----

    def _send(self, data: bytes, addr) -> None:
        if self._transport is not None:
            self._transport.sendto(data, addr)

    async def _transact(
        self, data: bytes, branch: str, method: str, addr, *,
        timeout: float = TIMEOUT, ring: float = 0.0,
        invite: _Invite | None = None, on_progress=None,
    ) -> sip.Message:
        """שולח בקשה, חוזר עליה עד שנענית, ומחזיר את התשובה הסופית."""
        loop = asyncio.get_running_loop()
        txn = self._pending[branch] = _Txn(method)
        resend = True
        interval = T1
        deadline = loop.time() + timeout
        self._send(data, addr)
        try:
            while True:
                left = deadline - loop.time()
                if left <= 0:
                    if resend:
                        raise SipError("No answer from the server", kind="unreachable")
                    raise SipError("No answer", status=408, kind="no_answer")
                try:
                    msg = await asyncio.wait_for(
                        txn.queue.get(), min(interval, left) if resend else left
                    )
                except asyncio.TimeoutError:
                    if resend and loop.time() < deadline:
                        self._send(data, addr)
                        interval = min(interval * 2, T2)
                    continue
                if msg.status < 200:
                    if invite is not None:
                        if resend:  # השרת קיבל; מכאן ממתינים למענה
                            resend = False
                            deadline = loop.time() + ring
                        if on_progress is not None:
                            on_progress(msg)
                    continue
                if invite is not None and msg.status >= 300:
                    self._ack_failure(invite, msg, addr)
                return msg
        except (SipError, asyncio.CancelledError):
            if invite is not None:
                # ויתרנו באמצע הצלצול. מבטלים, ומשאירים רישום כדי
                # לאשר את התשובה הסופית כשתגיע.
                self._zombies[branch] = (loop.time() + TIMEOUT, invite, addr)
                if not resend:
                    self._send(self._cancel(invite), addr)
            raise
        finally:
            if self._pending.get(branch) is txn:
                del self._pending[branch]

    async def _request(self, method: str, make, addr, *, timeout: float = TIMEOUT,
                       ring: float = 0.0, on_progress=None) -> sip.Message:
        """בקשה עם אימות: `make(auth)` בונה אותה מחדש לכל ניסיון."""
        auth = None
        answered = False
        while True:
            data, branch, invite = make(auth)
            resp = await self._transact(
                data, branch, method, addr, timeout=timeout, ring=ring,
                invite=invite, on_progress=on_progress,
            )
            if resp.status not in (401, 407):
                return resp
            proxy = resp.status == 407
            challenge = sip.pick_challenge(
                resp.all("proxy-authenticate" if proxy else "www-authenticate")
            )
            stale = (challenge or {}).get("stale", "").lower() == "true"
            if challenge is None or (answered and not stale):
                raise SipError(
                    "The server rejected the username or password",
                    status=resp.status, kind="auth",
                )
            answered = True
            auth = ("Proxy-Authorization" if proxy else "Authorization", challenge)

    def _ack_failure(self, invite: _Invite, resp: sip.Message, addr) -> None:
        self._send(sip.build(f"ACK {invite.uri} SIP/2.0", [
            ("Via", invite.via),
            ("Max-Forwards", "70"),
            ("From", invite.from_),
            ("To", resp.get("to") or invite.to),
            ("Call-ID", invite.call_id),
            ("CSeq", f"{invite.cseq} ACK"),
        ]), addr)

    def _cancel(self, invite: _Invite) -> bytes:
        return sip.build(f"CANCEL {invite.uri} SIP/2.0", [
            ("Via", invite.via),
            ("Max-Forwards", "70"),
            ("From", invite.from_),
            ("To", invite.to),
            ("Call-ID", invite.call_id),
            ("CSeq", f"{invite.cseq} CANCEL"),
        ])

    def _ack_answer(self, invite: _Invite, resp: sip.Message, addr) -> tuple[bytes, _Dialog]:
        """אישור למענה, והשיחה שנוצרה ממנו."""
        contact = resp.get("contact")
        target = sip.uri_of(contact) if contact else invite.uri
        routes = list(reversed(resp.all("record-route")))
        dialog = _Dialog(
            call_id=invite.call_id, local=invite.from_, remote=resp.get("to"),
            target=target, routes=routes, addr=addr, cseq=invite.cseq,
        )
        ack = sip.build(f"ACK {target} SIP/2.0", [
            ("Via", self._via(sip.new_branch())),
            ("Max-Forwards", "70"),
            *(("Route", route) for route in routes),
            ("From", invite.from_),
            ("To", resp.get("to")),
            ("Call-ID", invite.call_id),
            ("CSeq", f"{invite.cseq} ACK"),
            ("User-Agent", sip.USER_AGENT),
        ])
        self._send(ack, addr)
        return ack, dialog

    async def _in_dialog(self, dialog: _Dialog, method: str, *,
                         timeout: float = 4.0) -> sip.Message:
        def make(auth):
            dialog.cseq += 1
            branch = sip.new_branch()
            headers = [
                ("Via", self._via(branch)),
                ("Max-Forwards", "70"),
                *(("Route", route) for route in dialog.routes),
                ("From", dialog.local),
                ("To", dialog.remote),
                ("Call-ID", dialog.call_id),
                ("CSeq", f"{dialog.cseq} {method}"),
                ("User-Agent", sip.USER_AGENT),
                *self._auth(auth, method, dialog.target),
            ]
            return sip.build(f"{method} {dialog.target} SIP/2.0", headers), branch, None

        return await self._request(method, make, dialog.addr, timeout=timeout)

    async def _bye(self, dialog: _Dialog) -> None:
        with contextlib.suppress(SipError):
            await self._in_dialog(dialog, "BYE")

    async def dial(self, number: str, *, ring_timeout: float = 45.0) -> Call:
        """חיוג החוצה. חוזר כשהצד השני ענה, או זורק SipError."""
        number = re.sub(r"[^0-9+*#]", "", str(number))
        if not number:
            raise SipError("No number to dial", kind="rejected")
        if self._addr is None or self._transport is None:
            raise SipError("The line is not connected", kind="unreachable")
        if len(self._calls) >= self._max_calls:
            raise SipError("All lines are busy", kind="busy")

        addr = self._addr
        call = Call(self, call_id=sip.new_call_id(), caller=number, did="",
                    direction="out")
        self._calls[call.call_id] = call
        try:
            await call._open_media()
            target = f"sip:{number}@{self._domain}"
            from_ = f"<{self._aor}>;tag={call._local_tag}"
            body = sip.build_sdp(self._local_ip, call._port, session=call._session)
            last: list[_Invite] = []

            def make(auth):
                cseq = len(last) + 1
                branch = sip.new_branch()
                via = self._via(branch)
                headers = [
                    ("Via", via),
                    ("Max-Forwards", "70"),
                    ("From", from_),
                    ("To", f"<{target}>"),
                    ("Call-ID", call.call_id),
                    ("CSeq", f"{cseq} INVITE"),
                    ("Contact", self._contact),
                    ("User-Agent", sip.USER_AGENT),
                    ("Allow", sip.ALLOW),
                    *self._auth(auth, "INVITE", target),
                    ("Content-Type", "application/sdp"),
                ]
                invite = _Invite(target, via, from_, f"<{target}>", call.call_id, cseq)
                last.append(invite)
                return sip.build(f"INVITE {target} SIP/2.0", headers, body), branch, invite

            def progress(msg: sip.Message) -> None:
                if msg.body:  # צלצול מהרשת, לפני המענה
                    self._apply_answer(call, msg.body)

            resp = await self._request(
                "INVITE", make, addr, ring=ring_timeout, on_progress=progress
            )
            if not 200 <= resp.status < 300:
                raise SipError(
                    f"The call was refused: {resp.status} {resp.reason}",
                    status=resp.status, kind=_failure_kind(resp.status),
                )
            ack, call._dialog = self._ack_answer(last[-1], resp, addr)
            call._ack = (ack, addr)
            if not self._apply_answer(call, resp.body):
                await call.hangup()
                raise SipError("The call was answered with no usable audio",
                               kind="rejected")
            call.answered = True
            return call
        except BaseException:
            call._finish("failed")
            raise

    def _apply_answer(self, call: Call, body: str) -> bool:
        answer = sip.parse_sdp(body)
        payload = sip.pick_payload(answer) if answer else None
        if answer is None or payload is None or answer.secure:
            return False
        call._start_media((answer.ip, answer.port), payload, answer.event_pt)
        return True

    # ---- מה שמגיע מהספק ----

    def _on_datagram(self, data: bytes, addr) -> None:
        if len(data) <= 4:  # שמירת קשר
            return
        if addr[0] not in self._peers:
            # הפורט פתוח לעולם. מי שאינו הספק שנרשמנו אצלו לא מקבל
            # תשובה — לא שיחה, ואפילו לא סימן שיש כאן מישהו.
            if addr[0] not in self._strangers and len(self._strangers) < 50:
                self._strangers.add(addr[0])
                _LOGGER.warning(
                    "SIP line: ignoring a message from %s, which is not the provider",
                    addr[0],
                )
            return
        msg = sip.Message.parse(data)
        if msg is None:
            return
        try:
            if msg.is_response:
                self._on_response(msg, addr)
            else:
                self._on_request(msg, addr)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("SIP line: could not handle %s", msg.start)

    def _on_response(self, msg: sip.Message, addr) -> None:
        method = msg.cseq[1]
        txn = self._pending.get(msg.branch)
        if txn is not None and txn.method == method:
            txn.queue.put_nowait(msg)
            return
        if method != "INVITE" or msg.status < 200:
            return
        # תשובה סופית ל-INVITE שכבר אין מי שממתין לה.
        call = self._calls.get(msg.call_id)
        if call is not None and call._ack is not None and msg.status < 300:
            self._send(*call._ack)  # ה-ACK שלנו אבד בדרך
            return
        zombie = self._zombies.get(msg.branch)
        if zombie is None:
            return
        _, invite, to = zombie
        if msg.status >= 300:
            self._ack_failure(invite, msg, to)
            return
        # ענו אחרי שוויתרנו: מאשרים ומנתקים, אחרת הקו נשאר פתוח.
        _, dialog = self._ack_answer(invite, msg, to)
        del self._zombies[msg.branch]
        self._spawn(self._bye(dialog))

    def _reply(self, msg: sip.Message, addr, code: int, reason: str, **kwargs) -> bytes:
        data = sip.response(msg, code, reason, **kwargs)
        self._send(data, addr)
        loop = asyncio.get_running_loop()
        self._replies[(msg.call_id, msg.cseq[0], msg.method)] = (
            loop.time() + TIMEOUT, data,
        )
        return data

    def _on_request(self, msg: sip.Message, addr) -> None:
        method = msg.method
        call = self._calls.get(msg.call_id)
        if method == "ACK":
            if call is not None:
                call._acked.set()
            return
        cached = self._replies.get((msg.call_id, msg.cseq[0], method))
        if cached is not None:  # אותה בקשה שוב: אותה תשובה שוב
            self._send(cached[1], addr)
            return

        if method == "INVITE":
            self._on_invite(msg, addr, call)
        elif method == "BYE":
            if call is None:
                self._reply(msg, addr, 481, "Call Does Not Exist")
                return
            self._reply(msg, addr, 200, "OK")
            call._dialog = None
            call._finish("remote hangup")
        elif method == "CANCEL":
            if call is None:
                self._reply(msg, addr, 481, "Call Does Not Exist")
                return
            if not call.answered:
                call._cancelled = True
            self._reply(msg, addr, 200, "OK")
        elif method == "INFO":
            self._reply(msg, addr, 200, "OK")
            digit = sip.info_digit(msg.get("content-type"), msg.body)
            if digit and call is not None:
                call._key(digit, "info")
        elif method == "UPDATE" and call is not None and msg.body:
            self._renegotiate(call, msg, addr)
        elif method in ("OPTIONS", "NOTIFY", "UPDATE", "PRACK", "MESSAGE"):
            self._reply(msg, addr, 200, "OK", extra=(("Allow", sip.ALLOW),))
        else:
            self._reply(msg, addr, 501, "Not Implemented",
                        extra=(("Allow", sip.ALLOW),))

    def _on_invite(self, msg: sip.Message, addr, call: Call | None) -> None:
        if sip.tag_of(msg.get("to")):
            if call is None:
                self._reply(msg, addr, 481, "Call Does Not Exist")
            else:
                self._renegotiate(call, msg, addr)
            return
        if call is not None:
            return  # אותה שיחה שהגיעה בדרך נוספת
        offer = sip.parse_sdp(msg.body)
        payload = sip.pick_payload(offer) if offer else None
        # שיחה שנדחתה נכתבת ביומן: בלי זה קו שאינו עונה נראה כמו קו
        # שהספק לא שלח אליו כלום.
        if offer is None or payload is None or offer.secure or not offer.port:
            if offer is None or not offer.port:
                why = "no audio in the offer"
            elif offer.secure:
                why = "the provider asked for encrypted audio"
            else:
                why = f"no G.711 in the offer (payloads {list(offer.payloads)})"
            _LOGGER.warning(
                "SIP line: refused a call from %s: %s", caller_of(msg)[-4:], why
            )
            self._reply(msg, addr, 488, "Not Acceptable Here")
            return
        if self._on_call is None or len(self._calls) >= self._max_calls:
            _LOGGER.warning(
                "SIP line: refused a call from %s: the line is full",
                caller_of(msg)[-4:],
            )
            self._reply(msg, addr, 486, "Busy Here")
            return
        call = Call(self, call_id=msg.call_id, caller=caller_of(msg),
                    did=sip.user_of(msg.get("to")), direction="in")
        self._calls[call.call_id] = call
        # נשמר מיד, כדי ששידור חוזר של ה-INVITE לא יפתח שיחה שנייה.
        self._reply(msg, addr, 100, "Trying")
        self._spawn(self._accept(call, msg, addr, offer, payload))

    async def _accept(self, call: Call, msg: sip.Message, addr, offer: sip.Sdp,
                      payload: int) -> None:
        try:
            await call._open_media()
        except OSError:
            _LOGGER.exception("SIP line: could not open an audio socket")
            self._reply(msg, addr, 500, "Server Internal Error")
            call._finish("failed")
            return
        tag = call._local_tag
        if call._cancelled:
            self._reply(msg, addr, 487, "Request Terminated", to_tag=tag)
            call._finish("cancelled")
            return
        self._reply(msg, addr, 180, "Ringing", to_tag=tag)
        body = sip.build_sdp(
            self._local_ip, call._port, payloads=(payload,),
            event_pt=offer.event_pt, session=call._session,
        )
        answer = self._reply(
            msg, addr, 200, "OK", to_tag=tag, contact=self._contact, body=body,
            extra=(("Allow", sip.ALLOW),),
        )
        contact = msg.get("contact")
        call._dialog = _Dialog(
            call_id=call.call_id,
            local=f"{msg.get('to')};tag={tag}",
            remote=msg.get("from"),
            target=sip.uri_of(contact or msg.get("from")),
            routes=msg.all("record-route"),
            addr=(addr[0], addr[1]),
            cseq=secrets.randbelow(1000) + 1,
        )
        call._start_media((offer.ip, offer.port), payload, offer.event_pt)
        call.answered = True
        self._spawn(self._run_call(call))

        # המענה חוזר עד שהספק מאשר שקיבל אותו.
        interval, waited = T1, 0.0
        while not call.ended.is_set():
            try:
                await asyncio.wait_for(call._acked.wait(), interval)
                return
            except asyncio.TimeoutError:
                waited += interval
                if waited >= TIMEOUT:
                    _LOGGER.warning("SIP line: the answer was never acknowledged")
                    await call.hangup()
                    return
                self._send(answer, addr)
                interval = min(interval * 2, T2)

    async def _run_call(self, call: Call) -> None:
        try:
            await self._on_call(call)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("SIP line: the call handler failed")
        finally:
            await call.hangup()

    def _renegotiate(self, call: Call, msg: sip.Message, addr) -> None:
        """הספק מעדכן את השיחה באמצע — בדרך כלל כתובת שמע חדשה."""
        offer = sip.parse_sdp(msg.body) if msg.body else None
        if offer is not None and offer.port and offer.ip != "0.0.0.0":
            call._remote = (offer.ip, offer.port)
            call._latched = None
        body = sip.build_sdp(
            self._local_ip, call._port, payloads=(call._pt,),
            event_pt=call._event_pt, session=call._session,
        )
        self._reply(msg, addr, 200, "OK", contact=self._contact, body=body)
