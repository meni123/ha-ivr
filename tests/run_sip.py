"""הרצה אמיתית של קו ה-SIP הישיר, מול ספק מזויף על 127.0.0.1.

שלוש שכבות, כל אחת נבדקת כמו שהיא רצה:

* `sip` — הפרוטוקול עצמו: הודעות, אימות, SDP, ‏RTP ו-G.711.
* `sipline` — התעבורה, מול רשם ומרכזת מזויפים ב-UDP אמיתי: הרשמה,
  שיחה נכנסת, שמע ומקשים, חיוג החוצה, וכל דרך שבה שיחה נגמרת.
* `sipcall` והדרייבר — התפריט, העוזר הקולי וההתראות, מעל הקו.

python3 tests/run_sip.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import logging
import struct
import sys
import types
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_ha  # noqa: E402

fake_ha.install()

from custom_components.ha_ivr import (  # noqa: E402
    history, providers, sip, sipcall, sipline, view,
)
from custom_components.ha_ivr.audio import error_tone  # noqa: E402
from custom_components.ha_ivr.const import SATELLITES  # noqa: E402
from custom_components.ha_ivr.model import (  # noqa: E402
    GoTo, Prompt, Say, Terminal,
)
from custom_components.ha_ivr.outbound import OutboundError  # noqa: E402
from custom_components.ha_ivr.providers import sip as sipdrv  # noqa: E402
from custom_components.ha_ivr.sipline import SipError, SipLine  # noqa: E402

providers.ensure_registered()

PASS = FAIL = 0


def ok(name: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}")


def raises(fn, kind: str) -> bool:
    try:
        fn()
    except SipError as err:
        return err.kind == kind
    return False


# ======================================================================
print("== הודעות ==")
# ======================================================================
_REQ = (
    b"INVITE sip:109@10.0.0.5:5060 SIP/2.0\r\n"
    b"v: SIP/2.0/UDP 1.1.1.1:5060;branch=z9hG4bKaaa;rport, SIP/2.0/UDP 2.2.2.2;branch=z9hG4bKbbb\r\n"
    b'f: "Dan, the caller" <sip:972501234567@prov.test;user=phone>;tag=ft\r\n'
    b"t: <sip:109@prov.test>\r\n"
    b"i: call-1\r\n"
    b"CSeq: 7 INVITE\r\n"
    b"Record-Route: <sip:1.1.1.1;lr>,\r\n"
    b"  <sip:2.2.2.2;lr>\r\n"
    b"m: <sip:972501234567@1.1.1.1:5060>\r\n"
    b"c: application/sdp\r\n"
    b"l: 3\r\n\r\nv=0"
)
_m = sip.Message.parse(_REQ)
ok("בקשה מפוענחת", _m is not None and _m.method == "INVITE" and not _m.is_response)
ok("כותרות מקוצרות נפתחות",
   _m.call_id == "call-1" and _m.get("content-type") == "application/sdp")
ok("הענף של ה-Via הראשון", _m.branch == "z9hG4bKaaa")
ok("שני Via בשורה אחת הם שניים", len(_m.all("via")) == 2)
ok("שורת המשך מצטרפת לכותרת",
   _m.all("record-route") == ["<sip:1.1.1.1;lr>", "<sip:2.2.2.2;lr>"])
ok("CSeq", _m.cseq == (7, "INVITE"))
ok("הגוף", _m.body == "v=0")
ok("פסיק בתוך שם אינו מפצל", sip.split_list('"a, b" <sip:x@y>, <sip:z@w>') ==
   ['"a, b" <sip:x@y>', "<sip:z@w>"])
ok("תג, כתובת ומשתמש",
   sip.tag_of(_m.get("from")) == "ft"
   and sip.uri_of(_m.get("from")) == "sip:972501234567@prov.test;user=phone"
   and sip.user_of(_m.get("from")) == "972501234567")
ok("אין תג — מחרוזת ריקה", sip.tag_of(_m.get("to")) == "")
ok("מספר בינלאומי הופך למקומי", sipline.caller_of(_m) == "0501234567")
ok("זבל אינו הודעה",
   sip.Message.parse(b"hello") is None and sip.Message.parse(b"a b c\r\n\r\n") is None)

_r = sip.Message.parse(sip.response(_m, 200, "OK", to_tag="tt", contact="<sip:me@h>",
                                    body="v=0\r\n"))
ok("תשובה מפוענחת", _r.is_response and _r.status == 200 and _r.reason == "OK")
ok("התשובה מחזירה את כל ה-Via", _r.all("via") == _m.all("via"))
ok("התשובה מוסיפה תג ל-To", sip.tag_of(_r.get("to")) == "tt")
ok("מענה מחזיר את ה-Record-Route",
   _r.all("record-route") == _m.all("record-route"))
ok("100 אינו מחזיר Record-Route",
   not sip.Message.parse(sip.response(_m, 100, "Trying")).all("record-route"))
ok("אורך הגוף נכתב", _r.get("content-length") == "5")

# ======================================================================
print("\n== אימות ==")
# ======================================================================
# הדוגמה מ-RFC 2617, סעיף 3.5.
_rfc = sip.parse_challenge(
    'Digest realm="testrealm@host.com", qop="auth,auth-int", '
    'nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", '
    'opaque="5ccc069c403ebaf9f0171e9517f40e41"'
)
_auth = sip.authorization(
    _rfc, method="GET", uri="/dir/index.html", username="Mufasa",
    password="Circle Of Life", nc=1, cnonce="0a4f113b",
)
ok("הדוגמה מה-RFC", 'response="6629fae49393a05397450978507c4ef1"' in _auth)  # noleak
ok("opaque חוזר", 'opaque="5ccc069c403ebaf9f0171e9517f40e41"' in _auth)


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


_plain = sip.authorization(
    {"realm": "r", "nonce": "n"}, method="REGISTER", uri="sip:h",
    username="u", password="p",
)
ok("בלי qop — הנוסחה הישנה",
   f'response="{_md5(_md5("u:r:p") + ":n:" + _md5("REGISTER:sip:h"))}"' in _plain)
ok("אתגר שאינו Digest נדחה", sip.parse_challenge("Basic realm=x") is None)
ok("נבחר האתגר הראשון שאפשר לענות עליו",
   sip.pick_challenge([
       'Digest realm="r", nonce="a", algorithm=SHA-512',
       'Digest realm="r", nonce="b", algorithm=MD5',
   ])["nonce"] == "b")
ok("אין אתגר מתאים", sip.pick_challenge(["Basic realm=x"]) is None)

# ======================================================================
print("\n== SDP ==")
# ======================================================================
_OFFER = "\r\n".join([
    "v=0", "o=- 1 1 IN IP4 9.9.9.9", "s=-", "c=IN IP4 9.9.9.9", "t=0 0",
    "m=audio 40000 RTP/AVP 8 3 111 9 10 122 101",
    "a=rtpmap:8 PCMA/8000", "a=rtpmap:3 GSM/8000", "a=rtpmap:111 opus/48000/2",
    "a=rtpmap:101 telephone-event/8000", "a=fmtp:101 0-16", "a=sendrecv",
    "m=video 40002 RTP/AVP 96",
]) + "\r\n"
_o = sip.parse_sdp(_OFFER)
ok("הצעה מפוענחת",
   (_o.ip, _o.port, _o.event_pt, _o.secure) == ("9.9.9.9", 40000, 101, False))
ok("רק הקודקים של ערוץ השמע", _o.payloads == (8, 3, 111, 9, 10, 122, 101))
ok("A-law מועדף", sip.pick_payload(_o) == sip.PT_ALAW)
ok("µ-law כשאין A-law",
   sip.pick_payload(sip.parse_sdp(_OFFER.replace("AVP 8 3", "AVP 0 3"))) == sip.PT_ULAW)
ok("אין קודק משותף",
   sip.pick_payload(sip.parse_sdp(_OFFER.replace("AVP 8 3", "AVP 18 3"))) is None)
ok("כתובת בתוך ערוץ השמע גוברת",
   sip.parse_sdp(_OFFER.replace("a=sendrecv", "c=IN IP4 7.7.7.7")).ip == "7.7.7.7")
ok("ערוץ מוצפן מזוהה", sip.parse_sdp(_OFFER.replace("RTP/AVP 8", "RTP/SAVP 8")).secure)
ok("בלי ערוץ שמע — אין הצעה", sip.parse_sdp("v=0\r\nc=IN IP4 1.1.1.1\r\n") is None)
_mine = sip.parse_sdp(sip.build_sdp("10.0.0.5", 30000, payloads=(8,), event_pt=101))
ok("מה שנבנה נקרא בחזרה",
   (_mine.ip, _mine.port, _mine.payloads, _mine.event_pt)
   == ("10.0.0.5", 30000, (8, 101), 101))

# ======================================================================
print("\n== RTP ומקשים ==")
# ======================================================================
_p = sip.rtp_parse(sip.rtp_packet(8, 65536 + 5, 160, 1234, b"abc", True))
ok("חבילה נבנית ונקראת",
   (_p.pt, _p.seq, _p.ts, _p.payload, _p.marker) == (8, 5, 160, b"abc", True))
ok("ריפוד מוסר",
   sip.rtp_parse(bytes([0xA0, 8]) + bytes(10) + b"ab" + b"\0\x02").payload == b"ab")
ok("הרחבת כותרת מדולגת",
   sip.rtp_parse(bytes([0x90, 8]) + bytes(10) + b"\0\0\0\x01" + bytes(4) + b"xy")
   .payload == b"xy")
ok("חבילה קצרה או בגרסה אחרת נדחית",
   sip.rtp_parse(b"\x80\x08") is None and sip.rtp_parse(bytes(12)) is None)
ok("מקש ב-RFC 2833",
   sip.rtp_event(bytes([5, 0x8A, 0, 160])) == ("5", True, 160)
   and sip.rtp_event(bytes([11, 10, 0, 80])) == ("#", False, 80))
ok("אירוע שאינו מקש", sip.rtp_event(bytes([40, 0, 0, 0])) is None)
ok("מקש ב-INFO",
   sip.info_digit("application/dtmf-relay", "Signal=5\r\nDuration=160\r\n") == "5"
   and sip.info_digit("application/dtmf-relay", "Signal= #\r\n") == "#"
   and sip.info_digit("application/dtmf", "10") == "*"
   and sip.info_digit("text/plain", "5") is None)

# ======================================================================
print("\n== G.711 ==")
# ======================================================================
_all = struct.pack("<65536h", *range(-32768, 32768))
_codes = bytes(range(256))
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import audioop
except ImportError:  # פייתון 3.13 ומעלה
    audioop = None
if audioop is not None:
    ok("A-law זהה ל-audioop בכל דגימה",
       sip.encode(_all, sip.PT_ALAW) == audioop.lin2alaw(_all, 2))
    ok("µ-law זהה ל-audioop בכל דגימה",
       sip.encode(_all, sip.PT_ULAW) == audioop.lin2ulaw(_all, 2))
    ok("הפענוח זהה ל-audioop",
       sip.decode(_codes, sip.PT_ALAW) == audioop.alaw2lin(_codes, 2)
       and sip.decode(_codes, sip.PT_ULAW) == audioop.ulaw2lin(_codes, 2))
else:
    print("     (אין audioop בפייתון הזה; ההשוואה אליו מדולגת)")
ok("שקט מקודד לערך השקט",
   sip.encode(bytes(2), sip.PT_ALAW)[0] == sip.SILENCE[sip.PT_ALAW]
   and sip.encode(bytes(2), sip.PT_ULAW)[0] == sip.SILENCE[sip.PT_ULAW])
for _pt, _name in ((sip.PT_ALAW, "A-law"), (sip.PT_ULAW, "µ-law")):
    _back = struct.unpack("<65536h", sip.decode(sip.encode(_all, _pt), _pt))
    ok(f"{_name}: הלוך ושוב נשאר קרוב למקור",
       max(abs(a - b) for a, b in zip(_back, range(-32768, 32768))) <= 1024)
ok("בית בודד בסוף נזרק", len(sip.encode(bytes(5), sip.PT_ALAW)) == 2)


# ======================================================================
# הספק המזויף
# ======================================================================
USER, PASSWORD, REALM, NONCE = "109", "s3cret", "prov.test", "abc123"
HOST = "127.0.0.1"
TONE = struct.pack("<h", 9000) * 160 * 5  # עשירית שנייה שאינה שקט


class Media(asyncio.DatagramProtocol):
    """ערוץ השמע של הספק: מה שהקו שלח, ומה שנשלח אליו."""

    def __init__(self) -> None:
        self.packets: list[sip.Rtp] = []
        self.transport = None
        self.port = 0
        self._seq = 0
        self._ts = 0

    async def open(self) -> Media:
        loop = asyncio.get_running_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self, local_addr=(HOST, 0)
        )
        self.port = self.transport.get_extra_info("sockname")[1]
        return self

    def datagram_received(self, data, addr) -> None:
        packet = sip.rtp_parse(data)
        if packet is not None:
            self.packets.append(packet)

    def _send(self, pt: int, payload: bytes, to: int, *, same_ts: bool = False) -> None:
        self._seq += 1
        if not same_ts:
            self._ts += 160
        self.transport.sendto(
            sip.rtp_packet(pt, self._seq, self._ts, 77, payload), (HOST, to)
        )

    def audio(self, pcm: bytes, to: int, pt: int = sip.PT_ALAW) -> None:
        data = sip.encode(pcm, pt)
        for start in range(0, len(data), 160):
            self._send(pt, data[start:start + 160], to)

    def key(self, digit: str, to: int, pt: int = 101) -> None:
        """הקשה אחת, כמו שספק שולח אותה: כמה חבילות עם אותה חותמת."""
        code = "0123456789*#".index(digit)
        self._ts += 160
        for end in (0, 0, 0x80, 0x80):
            self._send(pt, bytes([code, end | 10, 0, 160]), to, same_ts=True)

    def voiced(self) -> int:
        """כמה חבילות שמע שאינן שקט הגיעו מהקו."""
        return sum(
            1 for p in self.packets
            if p.pt in sip.SILENCE and p.payload.strip(bytes([sip.SILENCE[p.pt]]))
        )

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()


@dataclasses.dataclass
class Leg:
    """שיחה שהספק פתח אל הקו."""

    call_id: str
    from_: str
    to: str
    target: str
    rtp_port: int
    media: Media
    cseq: int = 1


class Provider(asyncio.DatagramProtocol):
    """רשם, מרכזת שמחייגת אל הקו, ויעד לחיוג ממנו — בכתובת אחת."""

    def __init__(self) -> None:
        self.password = PASSWORD
        self.mode = "ok"  # מה עונים לחיוג מהקו: ok, busy, ring, late
        self.seen: list[sip.Message] = []
        self.registrations: list[int] = []
        self.contacts: dict = {}  # מי רשום כרגע, לפי סדר ההרשמה
        self.transport = None
        self.port = 0
        self.media: Media | None = None  # ערוץ השמע של חיוג מהקו
        self.dialed_rtp = 0
        self._replies: dict[str, asyncio.Queue] = {}
        self._invites: dict[str, sip.Message] = {}
        self._count = 0

    async def open(self) -> Provider:
        loop = asyncio.get_running_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: self, local_addr=(HOST, 0)
        )
        self.port = self.transport.get_extra_info("sockname")[1]
        self.media = await Media().open()
        return self

    def close(self) -> None:
        self.transport.close()
        self.media.close()

    @property
    def line_addr(self):
        """הכתובת של מי שנרשם אחרון ועדיין רשום — אליו מחייגים."""
        return next(reversed(self.contacts))

    def count(self, method: str) -> int:
        return sum(1 for m in self.seen if m.method == method)

    # ---- מה שמגיע מהקו ----

    def datagram_received(self, data, addr) -> None:
        if len(data) <= 4:
            return
        msg = sip.Message.parse(data)
        if msg is None:
            return
        if msg.is_response:
            self._replies.setdefault(msg.call_id, asyncio.Queue()).put_nowait(msg)
            return
        self.seen.append(msg)
        getattr(self, f"_on_{msg.method.lower()}", lambda *a: None)(msg, addr)

    def _reply(self, msg, addr, code, reason, **kwargs) -> None:
        self.transport.sendto(sip.response(msg, code, reason, **kwargs), addr)

    def _valid(self, header: str, method: str) -> bool:
        params = sip.parse_challenge(header) if header else None
        if not params or params.get("username") != USER:
            return False
        ha1 = _md5(f"{USER}:{REALM}:{self.password}")
        ha2 = _md5(f"{method}:{params.get('uri', '')}")
        if params.get("qop") == "auth":
            expected = _md5(
                f"{ha1}:{NONCE}:{params.get('nc')}:{params.get('cnonce')}:auth:{ha2}"
            )
        else:
            expected = _md5(f"{ha1}:{NONCE}:{ha2}")
        return params.get("response") == expected

    def _on_register(self, msg, addr) -> None:
        if not self._valid(msg.get("authorization"), "REGISTER"):
            self._reply(msg, addr, 401, "Unauthorized", extra=((
                "WWW-Authenticate",
                f'Digest realm="{REALM}", nonce="{NONCE}", qop="auth", algorithm=MD5',
            ),))
            return
        expires = int(msg.get("expires") or 0)
        self.registrations.append(expires)
        self.contacts.pop(addr, None)
        if expires:
            self.contacts[addr] = expires
        self._reply(msg, addr, 200, "OK",
                    contact=f"{msg.get('contact')};expires={expires}")

    def _answer(self, msg, addr) -> None:
        self._reply(
            msg, addr, 200, "OK", to_tag="pt",
            contact=f"<sip:far@{HOST}:{self.port}>",
            body=sip.build_sdp(HOST, self.media.port, payloads=(8,)),
        )

    def _on_invite(self, msg, addr) -> None:
        if not self._valid(msg.get("proxy-authorization"), "INVITE"):
            self._reply(msg, addr, 407, "Proxy Authentication Required", extra=((
                "Proxy-Authenticate", f'Digest realm="{REALM}", nonce="{NONCE}"',
            ),))
            return
        self._invites[msg.call_id] = msg
        self.dialed_rtp = sip.parse_sdp(msg.body).port
        self._reply(msg, addr, 100, "Trying")
        if self.mode == "busy":
            self._reply(msg, addr, 486, "Busy Here", to_tag="pt")
            return
        self._reply(msg, addr, 180, "Ringing", to_tag="pt")
        if self.mode == "ok":
            self._answer(msg, addr)

    def _on_cancel(self, msg, addr) -> None:
        self._reply(msg, addr, 200, "OK")
        invite = self._invites.get(msg.call_id)
        if invite is None:
            return
        if self.mode == "late":  # ענו בדיוק כשהקו ויתר
            self._answer(invite, addr)
        else:
            self._reply(invite, addr, 487, "Request Terminated", to_tag="pt")

    def _on_bye(self, msg, addr) -> None:
        self._reply(msg, addr, 200, "OK")

    # ---- מה שהספק יוזם ----

    async def _reply_to(self, call_id: str, status: int, method: str = "INVITE",
                        timeout: float = 3.0):
        queue = self._replies.setdefault(call_id, asyncio.Queue())
        async with asyncio.timeout(timeout):
            while True:
                msg = await queue.get()
                if msg.status == status and msg.cseq[1] == method:
                    return msg

    def invite(self, caller: str, call_id: str, media_port: int, *,
               source=None, offer: str | None = None) -> bytes:
        body = _OFFER.replace("9.9.9.9", HOST).replace("40000", str(media_port))
        data = sip.build(f"INVITE sip:{USER}@{HOST}:{self.line_addr[1]} SIP/2.0", [
            ("Via", f"SIP/2.0/UDP {HOST}:{self.port};branch=z9hG4bK{call_id}"),
            ("From", f"<sip:{caller}@{REALM}>;tag=ft"),
            ("To", f"<sip:{USER}@{REALM}>"),
            ("Call-ID", call_id),
            ("CSeq", "1 INVITE"),
            ("Contact", f"<sip:{caller}@{HOST}:{self.port}>"),
            ("Record-Route", f"<sip:{HOST}:{self.port};lr>"),
            ("Content-Type", "application/sdp"),
        ], body if offer is None else offer)
        (source or self.transport).sendto(data, self.line_addr)
        return data

    async def call(self, caller: str = "972501234567") -> Leg:
        """מחייג אל הקו וממתין למענה."""
        self._count += 1
        call_id = f"in{self._count}"
        media = await Media().open()
        self.invite(caller, call_id, media.port)
        answer = await self._reply_to(call_id, 200)
        leg = Leg(
            call_id=call_id, from_=f"<sip:{caller}@{REALM}>;tag=ft",
            to=answer.get("to"), target=sip.uri_of(answer.get("contact")),
            rtp_port=sip.parse_sdp(answer.body).port, media=media,
        )
        self._in_dialog(leg, "ACK", cseq=1)
        leg.answer = answer
        return leg

    def _in_dialog(self, leg: Leg, method: str, *, cseq: int | None = None,
                   kind: str = "", body: str = "") -> None:
        if cseq is None:
            leg.cseq += 1
            cseq = leg.cseq
        headers = [
            ("Via", f"SIP/2.0/UDP {HOST}:{self.port};branch=z9hG4bK{leg.call_id}{method}{cseq}"),
            ("From", leg.from_),
            ("To", leg.to),
            ("Call-ID", leg.call_id),
            ("CSeq", f"{cseq} {method}"),
        ]
        if kind:
            headers.append(("Content-Type", kind))
        self.transport.sendto(sip.build(f"{method} {leg.target} SIP/2.0", headers, body),
                              self.line_addr)

    async def bye(self, leg: Leg) -> None:
        self._in_dialog(leg, "BYE")
        await self._reply_to(leg.call_id, 200, "BYE")
        leg.media.close()

    async def info(self, leg: Leg, digit: str) -> None:
        self._in_dialog(leg, "INFO", kind="application/dtmf-relay",
                        body=f"Signal={digit}\r\nDuration=160\r\n")
        await self._reply_to(leg.call_id, 200, "INFO")


async def until(condition, timeout: float = 3.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if condition():
            return True
        await asyncio.sleep(0.01)
    return bool(condition())


async def sip_error(awaitable) -> SipError | None:
    try:
        await awaitable
    except SipError as err:
        return err
    return None


def new_line(prov: Provider, **kwargs) -> SipLine:
    return SipLine(server=HOST, port=prov.port, username=USER,
                   password=kwargs.pop("password", PASSWORD), **kwargs)


# ======================================================================
# הקו
# ======================================================================
async def test_line() -> None:
    print("\n== הרשמה ==")
    prov = await Provider().open()
    states: list[tuple[bool, str]] = []
    calls: list = []
    release = asyncio.Event()

    async def on_call(call) -> None:
        calls.append(call)
        await release.wait()

    line = new_line(prov, on_call=on_call,
                    on_state=lambda good, why: states.append((good, why)))
    await line.start()
    ok("הקו נרשם", await until(lambda: line.registered))
    ok("ההרשמה עברה אתגר ותשובה", prov.count("REGISTER") == 2)
    ok("נרשם לזמן שביקש", prov.registrations == [sipline.EXPIRES])
    ok("המצב דווח פעם אחת", states == [(True, "")])
    _reg = prov.seen[-1]
    ok("ה-Contact הוא הכתובת שממנה נרשם",
       f"@{HOST}:{prov.line_addr[1]}>" in _reg.get("contact"))
    ok("ה-Via מבקש rport", ";rport" in _reg.get("via"))

    trial = new_line(prov, password="wrong")
    await trial.start(keep=False)
    err = await sip_error(trial.check())
    await trial.stop()
    ok("סיסמה שגויה נדחית כ-auth", err is not None and err.kind == "auth")

    trial = new_line(prov)
    await trial.start(keep=False)
    before = len(prov.registrations)
    err = await sip_error(trial.check())
    await trial.stop()
    ok("הרשמת ניסיון מצליחה", err is None)
    ok("ומבטלת את עצמה", prov.registrations[before:] == [60, 0])

    closed = await Provider().open()
    port = closed.port
    closed.close()
    trial = SipLine(server=HOST, port=port, username=USER, password=PASSWORD)
    await trial.start(keep=False)
    err = await sip_error(trial.check(timeout=0.7))
    await trial.stop()
    ok("שרת שאינו עונה — unreachable", err is not None and err.kind == "unreachable")

    # ------------------------------------------------------------------
    print("\n== שיחה נכנסת ==")
    leg = await prov.call()
    ok("השיחה נענתה", len(calls) == 1 and calls[0].answered)
    call = calls[0]
    ok("המתקשר מזוהה", call.caller == "0501234567" and call.did == USER)
    ok("המענה בוחר A-law ומקשים", sip.parse_sdp(leg.answer.body).payloads == (8, 101))
    ok("המענה מחזיר Record-Route ו-Contact",
       leg.answer.all("record-route") and leg.answer.get("contact"))
    ok("ה-ACK התקבל", await until(lambda: call._acked.is_set()))
    ok("הקו משדר שקט עד שיש מה להשמיע",
       await until(lambda: len(leg.media.packets) >= 3) and leg.media.voiced() == 0)

    heard: list[bytes] = []
    call.on_audio = heard.append
    leg.media.audio(TONE, leg.rtp_port)
    ok("שמע מהמתקשר מגיע כ-PCM",
       await until(lambda: len(heard) == 5)
       and all(len(chunk) == 320 for chunk in heard)
       and abs(struct.unpack("<h", heard[0][:2])[0] - 9000) < 400)

    leg.media.key("5", leg.rtp_port)
    ok("מקש ב-RFC 2833 נקלט", await until(lambda: call.keys.qsize() == 1))
    await asyncio.sleep(0.05)
    ok("ארבע חבילות של אותה הקשה הן מקש אחד",
       call.keys.qsize() == 1 and call.keys.get_nowait() == "5")
    leg.media.key("5", leg.rtp_port)
    ok("אותה ספרה שוב היא הקשה חדשה",
       await until(lambda: call.keys.qsize() == 1) and call.keys.get_nowait() == "5")
    await prov.info(leg, "5")
    await asyncio.sleep(0.02)
    ok("אותו מקש שהגיע גם ב-INFO אינו נספר פעמיים", call.keys.qsize() == 0)
    await prov.info(leg, "#")
    ok("מקש ב-INFO נקלט",
       await until(lambda: call.keys.qsize() == 1) and call.keys.get_nowait() == "#")

    call.send(TONE * 4)
    ok("זמן ההשמעה נמדד לפי התור",
       0.3 < call.playout_end() - asyncio.get_running_loop().time() <= 0.4)
    ok("מה שנשלח נשמע אצל המתקשר", await until(lambda: leg.media.voiced() >= 15))
    ok("ובקודק שסוכם", all(p.pt == 8 for p in leg.media.packets))
    call.send(TONE * 20)
    call.flush()
    await asyncio.sleep(0.06)
    voiced = leg.media.voiced()
    await asyncio.sleep(0.1)
    ok("ניקוי התור משתיק מיד", leg.media.voiced() == voiced)

    prov.invite("972501234567", leg.call_id, leg.media.port)
    await asyncio.sleep(0.05)
    ok("INVITE חוזר אינו פותח שיחה שנייה", len(calls) == 1 and line.calls == 1)

    await prov.bye(leg)
    ok("ניתוק מהמתקשר מסיים את השיחה",
       call.ended.is_set() and call.reason == "remote hangup" and line.calls == 0)
    release.set()
    await asyncio.sleep(0.05)
    ok("ואינו נענה ב-BYE משלנו", prov.count("BYE") == 0)

    release.clear()
    leg = await prov.call("0542222222")
    ok("שיחה שנייה, אחרי הראשונה", len(calls) == 2 and calls[1].caller == "0542222222")
    release.set()
    ok("כשהטיפול בשיחה נגמר הקו מנתק",
       await until(lambda: prov.count("BYE") == 1) and calls[1].ended.is_set())
    _bye = prov.seen[-1]
    ok("ה-BYE הולך לפי ה-Record-Route ועם התגים הנכונים",
       _bye.all("route") == [f"<sip:{HOST}:{prov.port};lr>"]
       and sip.tag_of(_bye.get("to")) == "ft"
       and sip.tag_of(_bye.get("from")) == sip.tag_of(leg.to))
    leg.media.close()

    # ------------------------------------------------------------------
    print("\n== שיחות שאינן מתקבלות ==")
    release.clear()
    prov._count += 1
    prov.invite("0501111111", "nosdp", 0, offer="")
    ok("בלי הצעת שמע — 488", (await prov._reply_to("nosdp", 488)).status == 488)
    prov.invite("0501111111", "g729", 4000,
                offer=_OFFER.replace("AVP 8 3", "AVP 18 3"))
    ok("בלי קודק משותף — 488", (await prov._reply_to("g729", 488)).status == 488)

    small = new_line(prov, on_call=on_call, max_calls=1)
    await small.start()
    await until(lambda: small.registered)
    first = await prov.call()
    prov.invite("0501111111", "second", 4000)
    ok("מעבר למספר השיחות המותר — תפוס",
       (await prov._reply_to("second", 486)).status == 486)
    await prov.bye(first)
    await small.stop()
    release.set()

    stranger = await Provider().open()
    other, _ = await asyncio.get_running_loop().create_datagram_endpoint(
        lambda: stranger, local_addr=("127.0.0.2", 0)
    )
    before = len(calls)
    prov.invite("0501111111", "stranger", 4000, source=other)
    await asyncio.sleep(0.1)
    ok("מי שאינו הספק אינו מקבל שיחה, וגם לא תשובה",
       len(calls) == before and not stranger._replies)
    other.close()
    stranger.close()

    # ------------------------------------------------------------------
    print("\n== חיוג החוצה ==")
    prov.seen.clear()
    out = await line.dial("050-123 4567")
    ok("החיוג נענה", out.answered and out.direction == "out")
    _inv = [m for m in prov.seen if m.method == "INVITE"]
    ok("החיוג עבר אתגר ותשובה",
       len(_inv) == 2 and _inv[1].cseq[0] == _inv[0].cseq[0] + 1)
    ok("המספר נוקה מתווים",
       _inv[1].uri == f"sip:0501234567@{HOST}:{prov.port}")
    ok("הדחייה והמענה אושרו שניהם", await until(lambda: prov.count("ACK") == 2))
    _sdp = sip.parse_sdp(_inv[1].body)
    ok("ההצעה שלנו: A-law, ‏µ-law ומקשים", _sdp.payloads == (8, 0, 101))
    out.send(TONE * 3)
    ok("הנמען שומע את ההודעה", await until(lambda: prov.media.voiced() >= 10))
    prov.media.key("1", prov.dialed_rtp)
    ok("מקש מהנמען נקלט",
       await until(lambda: out.keys.qsize() == 1) and out.keys.get_nowait() == "1")
    await out.hangup()
    ok("ניתוק שלנו שולח BYE",
       prov.count("BYE") == 1 and out.ended.is_set() and line.calls == 0)
    ok("ה-BYE פונה ל-Contact של הנמען",
       prov.seen[-1].uri == f"sip:far@{HOST}:{prov.port}")

    prov.seen.clear()
    prov.mode = "busy"
    err = await sip_error(line.dial("0501234567"))
    ok("תפוס", err is not None and err.kind == "busy" and err.status == 486)
    ok("הדחייה אושרה והקו התפנה",
       await until(lambda: prov.count("ACK") == 2) and line.calls == 0)

    prov.seen.clear()
    prov.mode = "ring"
    err = await sip_error(line.dial("0501234567", ring_timeout=0.3))
    ok("אין מענה", err is not None and err.kind == "no_answer")
    ok("הצלצול בוטל", await until(lambda: prov.count("CANCEL") == 1))
    ok("וה-487 אושר", await until(lambda: prov.count("ACK") == 2))

    prov.seen.clear()
    prov.mode = "late"
    err = await sip_error(line.dial("0501234567", ring_timeout=0.3))
    ok("מענה שהגיע אחרי שוויתרנו נסגר ב-BYE",
       err is not None and await until(lambda: prov.count("BYE") == 1)
       and line.calls == 0)
    prov.mode = "ok"

    ok("מספר ריק אינו מחויג",
       (await sip_error(line.dial("abc"))).kind == "rejected")

    # ------------------------------------------------------------------
    print("\n== סגירה ==")
    release.clear()
    leg = await prov.call()
    prov.seen.clear()
    await line.stop()
    ok("סגירת הקו מנתקת שיחה פעילה", prov.count("BYE") == 1 and calls[-1].ended.is_set())
    ok("ומבטלת את ההרשמה", prov.registrations[-1] == 0 and not line.registered)
    release.set()
    leg.media.close()
    ok("קו סגור אינו מחייג",
       (await sip_error(line.dial("0501234567"))).kind == "unreachable")

    bad_states: list = []
    bad = new_line(prov, password="wrong",
                   on_state=lambda good, why: bad_states.append((good, why)))
    await bad.start()
    ok("סיסמה שגויה מדווחת מיד",
       await until(lambda: bad_states == [(False, "auth")]) and not bad.registered)
    await bad.stop()
    prov.close()


# ======================================================================
# השיחה
# ======================================================================
class FakeLine:
    """קו של הלוויין, כפי ש-`sipcall` רואה אותו."""

    entity_id = "assist_satellite.line_1"

    def __init__(self) -> None:
        self.session = None
        self.busy = False
        self.fail = False
        self.chunks: list[bytes] = []
        self.spoken: list[str] = []
        self.began = 0
        self.detached = 0

    def attach(self, session, rate) -> bool:
        if self.busy or self.session is not None:
            return False
        self.session = session
        return rate == 8000

    def detach(self, session) -> None:
        if self.session is session:
            self.session = None
            self.detached += 1

    def on_chunk(self, pcm: bytes) -> None:
        self.chunks.append(pcm)

    async def begin(self) -> None:
        self.began += 1

    async def request_leave(self) -> None:
        await self.session.leave()

    async def async_synthesize(self, text: str, rate: int) -> bytes:
        self.spoken.append(text)
        await asyncio.sleep(0)
        if self.fail:
            raise RuntimeError("the engine is down")
        return TONE


class FakeCall:
    """שיחה בלי רשת: מה שנשלח נרשם, וההשמעה מיידית."""

    def __init__(self) -> None:
        self.call_id = "fake-call"
        self.caller = "0501234567"
        self.did = USER
        self.direction = "in"
        self.keys: asyncio.Queue[str] = asyncio.Queue()
        self.ended = asyncio.Event()
        self.reason = ""
        self.on_audio = None
        self.sent: list[bytes] = []
        self.flushed = 0

    def send(self, pcm: bytes) -> None:
        self.sent.append(pcm)

    def flush(self) -> None:
        self.flushed += 1

    def playout_end(self) -> float:
        return asyncio.get_running_loop().time()

    async def hangup(self) -> None:
        self.reason = self.reason or "local hangup"
        self.ended.set()


class Entry(fake_ha.FakeEntry):
    def __init__(self, options=None) -> None:
        super().__init__(data={"token": "T", "provider": "sip"}, options=options)
        self.domain = "ha_ivr"
        self.background: list[asyncio.Task] = []

    def async_create_background_task(self, hass, coro, name):
        task = asyncio.get_running_loop().create_task(coro)
        self.background.append(task)
        return task


def new_home(options=None):
    entry = Entry(options)
    hass = fake_ha.FakeHass(entries=[entry])
    line = FakeLine()
    hass.data = {SATELLITES: {entry.entry_id: [line]}}
    return hass, entry, line


class Script:
    """תפריט מתוסרט במקום המנוע: מה חוזר לכל צעד, ומה התבקש."""

    def __init__(self, respond) -> None:
        self.asked: list = []
        self._respond = respond
        self._real = view.async_menu_step

    async def __call__(self, hass, entry, ctx):
        self.asked.append(ctx)
        return self._respond(ctx)

    def __enter__(self) -> Script:
        view.async_menu_step = self
        return self

    def __exit__(self, *exc) -> None:
        view.async_menu_step = self._real


def root(ctx, timeout: int = 1) -> Prompt:
    return Prompt([Say("text", "לעוזר הקולי הקש 9")], frozenset("19"),
                  tuple(ctx.path), ctx.step, timeout)


async def run_session(hass, entry, call) -> asyncio.Task:
    task = asyncio.ensure_future(sipcall.SipCallSession(hass, entry, call).run())
    await asyncio.sleep(0)
    return task


async def test_session() -> None:
    print("\n== מה מוקרא ==")
    ok("מספר נדבק למשפט שסביבו",
       sipcall.clips([Say("text", "הסלון כרגע"), Say("number", "23"),
                      Say("text", "מעלות"), Say("text", "למזגן הקש 1")])
       == ["הסלון כרגע 23 מעלות.", "למזגן, הקש 1."])
    ok("ספרות מוקראות אחת אחת",
       sipcall.clips([Say("text", "הקוד"), Say("digits", "407")]) == ["הקוד 4 0 7."])
    ok("קובץ ופריט ריק מדולגים",
       sipcall.clips([Say("file", "beep"), Say("text", ""), Say("text", "שלום.")])
       == ["שלום."])
    ok("מספר ראשון עומד בפני עצמו", sipcall.clips([Say("number", "7")]) == ["7."])

    # ------------------------------------------------------------------
    print("\n== תפריט ==")
    hass, entry, line = new_home()

    def simple(ctx):
        if ctx.digit == "1":
            return Terminal([Say("text", "בוצע")])
        if ctx.digit == "2":
            return Prompt([Say("text", "תת תפריט")], frozenset("1"), ("2",), ctx.step, 1)
        if ctx.digit is None and ctx.step - len(ctx.path) > 2:
            return Terminal([Say("text", "להתראות")])
        return root(ctx)

    history.clear()
    call = FakeCall()
    call.keys.put_nowait("1")  # הוקש עוד לפני שההקראה התחילה
    with Script(simple) as script:
        task = await run_session(hass, entry, call)
        await asyncio.wait_for(task, 3)
    ok("הצעד הראשון: שורש, בלי הקשה, צעד 1",
       (script.asked[0].path, script.asked[0].digit, script.asked[0].step) == ((), None, 1))
    ok("פרטי השיחה עוברים למנוע",
       (script.asked[0].caller, script.asked[0].did, script.asked[0].call_id)
       == ("0501234567", USER, "fake-call"))
    ok("ההקשה עוברת למנוע",
       (script.asked[1].path, script.asked[1].digit, script.asked[1].step) == ((), "1", 1))
    ok("הקשה קוטעת את ההשמעה", call.flushed == 1)
    ok("התוצאה מוקראת והשיחה נגמרת",
       line.spoken[-1] == "בוצע." and len(script.asked) == 2)
    kinds = [event["kind"] for event in history.snapshot()]
    ok("השיחה נרשמת ביומן", kinds[0] == "sip.start" and kinds[-1] == "sip.end")

    call = FakeCall()
    call.keys.put_nowait("2")
    with Script(simple) as script:
        task = await run_session(hass, entry, call)
        await asyncio.wait_for(task, 6)
    ok("בלי הקשה הצעד עולה והנתיב נשמר",
       [(c.path, c.digit, c.step) for c in script.asked]
       == [((), None, 1), ((), "2", 1), (("2",), None, 3), (("2",), None, 4)])
    ok("שיחה שננטשה מסתיימת בלהתראות", line.spoken[-1] == "להתראות.")

    call = FakeCall()
    with Script(simple):
        task = await run_session(hass, entry, call)
        await asyncio.sleep(0.05)
        call.reason = "remote hangup"
        call.ended.set()
        await asyncio.wait_for(task, 1)
    ok("ניתוק באמצע התפריט מסיים מיד", task.done() and task.exception() is None)

    line.fail = True
    call = FakeCall()
    call.keys.put_nowait("1")
    with Script(simple):
        await asyncio.wait_for(await run_session(hass, entry, call), 3)
    ok("כשההקראה נכשלת נשמע צליל שגיאה", error_tone(8000) in call.sent)
    line.fail = False

    def broken(ctx):
        raise RuntimeError("boom")

    call = FakeCall()
    logging.disable(logging.ERROR)  # החריגה נרשמת ביומן; כאן היא רק רעש
    with Script(broken):
        task = await run_session(hass, entry, call)
        await asyncio.wait_for(task, 1)
    logging.disable(logging.NOTSET)
    ok("כשל בתפריט אינו עף החוצה", task.exception() is None)

    # ------------------------------------------------------------------
    print("\n== העוזר הקולי ==")

    def assist(ctx):
        if ctx.digit == "9":
            return GoTo("assist", [Say("text", "מעביר אותך")])
        if ctx.digit == "1":
            return GoTo("200", [Say("text", "מעביר אותך")])
        return root(ctx, timeout=5)

    hass, entry, line = new_home()
    call = FakeCall()
    call.keys.put_nowait("9")
    with Script(assist) as script:
        task = await run_session(hass, entry, call)
        ok("המתקשר מחובר לעוזר",
           await until(lambda: line.began == 1) and line.session is not None)
        ok("ההודעה לפני המעבר מוקראת", line.spoken[-1] == "מעביר אותך.")
        call.on_audio(bytes(480))
        call.on_audio(TONE[:480])
        ok("השמע נחתך למסגרות של 320 בתים",
           len(line.chunks) == 3 and all(len(c) == 320 for c in line.chunks))
        await asyncio.sleep(0.25)
        ok("שתיקה בקו מושלמת במסגרות שקט",
           len(line.chunks) > 6 and line.chunks[-1] == bytes(320))
        sent = len(call.sent)
        await line.session.send_audio(TONE)
        ok("תשובת העוזר נשלחת למתקשר", call.sent[sent:] == [TONE])
        call.keys.put_nowait("5")
        await asyncio.sleep(0.05)
        ok("מקש רגיל אינו מוציא מהעוזר", line.session is not None)
        asked = len(script.asked)
        call.keys.put_nowait("#")
        ok("מקש היציאה מחזיר לתפריט",
           await until(lambda: line.detached == 1 and len(script.asked) > asked))
        ok("והתפריט מתחיל מהשורש",
           (script.asked[-1].path, script.asked[-1].digit, script.asked[-1].step)
           == ((), None, 1))
        ok("השמע כבר אינו הולך לעוזר", call.on_audio is None)

        call.keys.put_nowait("9")
        await until(lambda: line.began == 2)
        asked = len(script.asked)
        await line.session.close("silence")
        ok("עוזר שוויתר מחזיר לתפריט",
           await until(lambda: line.detached == 2 and len(script.asked) > asked))

        call.keys.put_nowait("9")
        await until(lambda: line.began == 3)
        asked = len(script.asked)
        await line.session.hung_up()
        await asyncio.wait_for(task, 1)
        ok("ניתוק בזמן העוזר מסיים את השיחה",
           line.detached == 3 and len(script.asked) == asked)

    line.busy = True
    call = FakeCall()
    call.keys.put_nowait("9")
    with Script(assist) as script:
        task = await run_session(hass, entry, call)
        ok("כשכל הקווים תפוסים — צליל שגיאה וחזרה לתפריט",
           await until(lambda: len(script.asked) == 3) and error_tone(8000) in call.sent)
        call.ended.set()
        await asyncio.wait_for(task, 1)
    line.busy = False

    call = FakeCall()
    call.keys.put_nowait("1")
    with Script(assist) as script:
        task = await run_session(hass, entry, call)
        ok("בקו ישיר כל מעבר מחבר לעוזר, יהיה היעד אשר יהיה",
           await until(lambda: line.began == 4) and len(script.asked) == 2)
        call.ended.set()
        await asyncio.wait_for(task, 1)

    hass, entry, line = new_home({"stream_exit_keys": "*, 0"})
    call = FakeCall()
    call.keys.put_nowait("9")
    with Script(assist):
        task = await run_session(hass, entry, call)
        await until(lambda: line.began == 1)
        call.keys.put_nowait("#")
        await asyncio.sleep(0.05)
        still = line.session is not None
        call.keys.put_nowait("0")
        ok("מקשי היציאה נקראים מההגדרות",
           still and await until(lambda: line.detached == 1))
        call.ended.set()
        await asyncio.wait_for(task, 1)

    # ------------------------------------------------------------------
    print("\n== מול מנוע התפריט האמיתי ==")
    hass, entry, line = new_home({"intro": "שלום"})
    entry.subentries = {"g": fake_ha.FakeSubentry(
        data={"menu_path": "9", "label": "עוזר קולי", "goto_target": "assist"},
        subentry_type="goto", title="9", subentry_id="g")}
    real = view.async_menu_step

    async def quick(hass, entry, ctx):
        action = await real(hass, entry, ctx)
        if isinstance(action, Prompt):
            action = dataclasses.replace(action, timeout=0)
        return action

    view.async_menu_step = quick
    try:
        call = FakeCall()
        call.keys.put_nowait("7")
        task = await run_session(hass, entry, call)
        ok("התפריט מוקרא", await until(lambda: any("9" in t for t in line.spoken)))
        ok("מקש שאינו בתפריט נענה",
           await until(lambda: any("בחירה שאינה קיימת" in t for t in line.spoken)))
        call.keys.put_nowait("9")
        ok("המקש של העוזר מחבר אליו", await until(lambda: line.began == 1))
        call.keys.put_nowait("#")
        await until(lambda: line.detached == 1)
        await asyncio.wait_for(task, 8)
        ok("תפריט שאיש אינו מקיש בו נסגר בלהתראות",
           line.spoken[-1] == "להתראות.")
    finally:
        view.async_menu_step = real

    entry.options = {"allowed_phones": ["0509999999"]}
    call = FakeCall()
    await asyncio.wait_for(await run_session(hass, entry, call), 3)
    ok("מספר שאינו מורשה נדחה גם כאן", line.spoken[-1] == "המספר שלך אינו מורשה.")


# ======================================================================
# הכול יחד: ספק מזויף → קו → שיחה → עוזר
# ======================================================================
async def test_stack() -> None:
    print("\n== שיחה מלאה, מהספק ועד העוזר ==")
    prov = await Provider().open()
    hass, entry, line = new_home()
    entry.options = {
        "sip_server": HOST, "sip_port": str(prov.port),
        "sip_username": USER, "sip_password": PASSWORD,
    }

    def menu_script(ctx):
        if ctx.digit == "9":
            return GoTo("assist", [Say("text", "מעביר אותך")])
        return root(ctx, timeout=5)

    fake_ha.ISSUES.clear()
    with Script(menu_script) as script:
        transport = await sipdrv.async_start_transport(hass, entry)
        ok("הדרייבר רושם את הקו", await until(lambda: transport.line.registered))
        ok("אין תקלה פתוחה", not fake_ha.ISSUES)

        leg = await prov.call()
        ok("המתקשר שומע את התפריט", await until(lambda: leg.media.voiced() >= 5))
        leg.media.key("9", leg.rtp_port)
        ok("מקש מהטלפון מחבר לעוזר", await until(lambda: line.began == 1))
        line.chunks.clear()
        leg.media.audio(TONE * 2, leg.rtp_port)
        ok("הדיבור של המתקשר מגיע לעוזר",
           await until(lambda: sum(1 for c in line.chunks if c.strip(b"\0")) == 10)
           and all(len(c) == 320 for c in line.chunks))
        await until(lambda: transport.line._calls
                    and not next(iter(transport.line._calls.values()))._out)
        voiced = leg.media.voiced()
        await line.session.send_audio(TONE * 3)
        ok("תשובת העוזר נשמעת בטלפון",
           await until(lambda: leg.media.voiced() >= voiced + 15))
        asked = len(script.asked)
        leg.media.key("#", leg.rtp_port)
        ok("סולמית מחזירה לתפריט",
           await until(lambda: line.detached == 1 and len(script.asked) > asked))
        await prov.bye(leg)
        ok("ניתוק מפנה את הקו", await until(lambda: transport.line.calls == 0))
        await asyncio.sleep(0.05)
        ok("והשיחה נרשמה ביומן עם סיבת הסיום",
           any(e["kind"] == "sip.end" and e.get("reason") == "remote hangup"
               for e in history.snapshot()))

    # ------------------------------------------------------------------
    print("\n== התראה יוצאת ==")
    prov.seen.clear()
    before = prov.media.voiced()
    await sipdrv.async_notify(hass, entry, "דלת הכניסה נפתחה", ["050-1234567"])
    ok("ההודעה מסונתזת לפני החיוג", line.spoken[-1] == "דלת הכניסה נפתחה.")
    ok("הנמען שומע אותה", await until(lambda: prov.media.voiced() >= before + 5, 4))
    await asyncio.wait_for(asyncio.gather(*entry.background), 5)
    ok("והשיחה נסגרת", prov.count("BYE") == 1 and transport.line.calls == 0)
    ok("והיומן אומר שההודעה הושמעה",
       [e["kind"] for e in history.snapshot() if e["kind"].startswith("sip.alert")][-2:]
       == ["sip.alert", "sip.alert_done"])

    prov.seen.clear()
    prov.mode = "busy"
    failed = await sipcall.async_deliver(
        transport.line, TONE, ["0501234567", "לא מספר", "0523333333"], "בדיקה")
    ok("מי שלא קיבל חוזר עם הסיבה",
       sorted(failed) == sorted([("לא מספר", "invalid"), ("0501234567", "busy"),
                                 ("0523333333", "busy")]))
    ok("ומי שלא קיבל אינו נרשם כמי ששמע",
       [e["kind"] for e in history.snapshot()][-2:]
       == ["sip.alert_failed", "sip.alert_failed"])
    prov.mode = "ok"

    async def key_of(awaitable) -> str:
        try:
            await awaitable
        except OutboundError as err:
            return err.key
        return ""

    ok("בלי מספר תקין — שגיאה ברורה",
       await key_of(sipdrv.async_notify(hass, entry, "x", ["abc"])) == "no_valid_numbers")
    line.fail = True
    ok("כשל בהקראה חוזר למי ששלח",
       await key_of(sipdrv.async_notify(hass, entry, "x", ["0501234567"]))
       == "alert_failed")
    line.fail = False

    # ------------------------------------------------------------------
    print("\n== הטופס והתקלות ==")

    class QuickLine(SipLine):
        async def check(self, timeout: float = 0.7) -> None:
            await super().check(0.7)

    sipdrv.SipLine = QuickLine
    good = dict(entry.options)
    before = prov.count("REGISTER")
    ok("פרטים שכבר רשומים אינם נבדקים שוב",
       await sipdrv.async_menu_errors(hass, good) == {}
       and prov.count("REGISTER") == before)
    ok("שדה חסר", await sipdrv.async_menu_errors(hass, {**good, "sip_username": " "})
       == {"sip_username": "sip_missing"})
    ok("סיסמה שגויה נעצרת בטופס",
       await sipdrv.async_menu_errors(hass, {**good, "sip_password": "wrong"})
       == {"sip_password": "sip_auth_failed"})
    closed = await Provider().open()
    port = closed.port
    closed.close()
    ok("שרת שאינו עונה נעצר בטופס",
       await sipdrv.async_menu_errors(hass, {**good, "sip_port": str(port)})
       == {"sip_server": "sip_unreachable"})

    await sipdrv.async_stop_transport(transport)
    ok("עצירה מבטלת את ההרשמה", prov.registrations[-1] == 0)
    ok("בלי קו רשום אין התראה",
       await key_of(sipdrv.async_notify(hass, entry, "x", ["0501234567"]))
       == "sip_not_registered")
    ok("פרטים נכונים עוברים בהרשמת ניסיון",
       await sipdrv.async_menu_errors(hass, good) == {}
       and prov.registrations[-2:] == [60, 0])

    saved = sipdrv.menu_save({
        "sip_server": f" {HOST}:5080 ", "sip_username": " 109 ",
        "sip_password": " p w ", "sip_port": "",
    })
    ok("שרת עם פורט מפוצל, והסיסמה נשמרת כמות שהיא",
       saved == {"sip_server": HOST, "sip_username": "109",
                 "sip_password": " p w ", "sip_port": "5080"})
    ok("פורט שאינו מספר חוזר לברירת המחדל",
       sipdrv.menu_save({"sip_server": "h", "sip_port": "abc"})["sip_port"] == "5060")
    ok("שדות הטופס",
       [marker.schema for marker in sipdrv.menu_fields({})]
       == ["sip_server", "sip_username", "sip_password", "sip_port"])
    ok("הסיסמה אינה נכתבת ביומן",
       history.redact("s3cret", "sip_password") == "***")

    entry.options = {**good, "sip_password": "wrong"}
    transport = await sipdrv.async_start_transport(hass, entry)
    issue = f"sip_line_{entry.entry_id}"
    ok("סיסמה שגויה פותחת תקלה",
       await until(lambda: issue in fake_ha.ISSUES)
       and fake_ha.ISSUES[issue]["translation_key"] == "sip_auth_failed"
       and fake_ha.ISSUES[issue]["translation_placeholders"] == {"server": HOST})
    await sipdrv.async_stop_transport(transport)
    ok("והיא נסגרת כשהקו נעצר", issue not in fake_ha.ISSUES)
    sipdrv.SipLine = SipLine
    prov.close()


async def main() -> None:
    await test_line()
    await test_session()
    await test_stack()


asyncio.run(main())

print(f"\n{'PASS' if not FAIL else 'FAIL'} — {PASS} עברו, {FAIL} נכשלו")
sys.exit(1 if FAIL else 0)
