"""פרוטוקול SIP בלי רשת: הודעות, אימות, SDP, RTP ו-G.711.

כל מה שכאן הוא פונקציות טהורות — בלי סוקט, בלי asyncio ובלי Home
Assistant. התעבורה נמצאת ב-`sipline`, והשיחה עצמה ב-`sipcall`.

G.711 ממומש כאן בטבלאות: `audioop` הוסר מפייתון 3.13, והטבלאות נבנות
מאותו אלגוריתם בדיוק, כך שהתוצאה זהה לו בית-בבית.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import struct
from dataclasses import dataclass

USER_AGENT = "ha-ivr"
ALLOW = "INVITE, ACK, BYE, CANCEL, OPTIONS, INFO, UPDATE, NOTIFY"

PT_ULAW = 0
PT_ALAW = 8
FRAME = 160  # 20 אלפיות שנייה ב-8000 הרץ, בית לדגימה
RATE = 8000

_DIGITS = "0123456789*#ABCD"


def new_tag() -> str:
    return secrets.token_hex(6)


def new_branch() -> str:
    return "z9hG4bK" + secrets.token_hex(10)


def new_call_id() -> str:
    return secrets.token_hex(12)


# ---- הודעות ----

_COMPACT = {
    "v": "via", "f": "from", "t": "to", "i": "call-id", "m": "contact",
    "l": "content-length", "c": "content-type", "k": "supported",
    "s": "subject", "e": "content-encoding",
}
# כותרות שערך אחד שלהן יכול להכיל כמה פריטים מופרדים בפסיק.
_LISTS = {"via", "record-route", "route", "contact"}


def split_list(value: str) -> list[str]:
    """פיצול בפסיקים שאינם בתוך <> או מירכאות."""
    out, buf, angle, quote = [], [], 0, False
    for ch in value:
        if ch == '"':
            quote = not quote
        elif not quote and ch == "<":
            angle += 1
        elif not quote and ch == ">":
            angle = max(0, angle - 1)
        if ch == "," and not quote and not angle:
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf).strip())
    return [item for item in out if item]


class Message:
    """בקשה או תשובה אחת, אחרי פענוח."""

    __slots__ = ("start", "headers", "body", "is_response", "status",
                 "reason", "method", "uri")

    def __init__(self) -> None:
        self.start = ""
        self.headers: list[tuple[str, str]] = []
        self.body = ""
        self.is_response = False
        self.status = 0
        self.reason = ""
        self.method = ""
        self.uri = ""

    @classmethod
    def parse(cls, data: bytes) -> Message | None:
        head, _, body = data.partition(b"\r\n\r\n")
        lines = head.decode("utf-8", "replace").split("\r\n")
        parts = lines[0].split(" ", 2)
        if len(parts) < 3:
            return None
        msg = cls()
        msg.start = lines[0]
        if parts[0].upper().startswith("SIP/"):
            if not parts[1].isdigit():
                return None
            msg.is_response = True
            msg.status = int(parts[1])
            msg.reason = parts[2]
        elif parts[2].upper().startswith("SIP/"):
            msg.method = parts[0].upper()
            msg.uri = parts[1]
        else:
            return None
        for line in lines[1:]:
            if line[:1] in (" ", "\t") and msg.headers:  # המשך שורה
                name, value = msg.headers[-1]
                msg.headers[-1] = (name, f"{value} {line.strip()}")
                continue
            name, sep, value = line.partition(":")
            if not sep:
                continue
            name = name.strip().lower()
            msg.headers.append((_COMPACT.get(name, name), value.strip()))
        msg.body = body.decode("utf-8", "replace")
        return msg

    def get(self, name: str, default: str = "") -> str:
        for key, value in self.headers:
            if key == name:
                return value
        return default

    def all(self, name: str) -> list[str]:
        values = [value for key, value in self.headers if key == name]
        if name in _LISTS:
            return [item for value in values for item in split_list(value)]
        return values

    @property
    def call_id(self) -> str:
        return self.get("call-id")

    @property
    def cseq(self) -> tuple[int, str]:
        number, _, method = self.get("cseq").partition(" ")
        return (int(number) if number.strip().isdigit() else 0,
                method.strip().upper())

    @property
    def branch(self) -> str:
        via = self.all("via")
        found = re.search(r";\s*branch=([^;,\s]+)", via[0]) if via else None
        return found.group(1) if found else ""


def tag_of(header: str) -> str:
    found = re.search(r";\s*tag=([^;,\s>]+)", header.rpartition(">")[2]
                      if ">" in header else header)
    return found.group(1) if found else ""


def uri_of(header: str) -> str:
    """הכתובת שבכותרת From, To או Contact."""
    found = re.search(r"<([^>]+)>", header)
    return found.group(1) if found else header.split(";")[0].strip()


def user_of(header: str) -> str:
    """שם המשתמש שבכתובת: `sip:USER@host`."""
    uri = uri_of(header)
    found = re.match(r"(?i)(?:sips?|tel):([^@;>]*)@", uri)
    if found:
        return found.group(1).split(";")[0].split(":")[0]
    found = re.match(r"(?i)tel:([^;>]+)", uri)
    return found.group(1) if found else ""


def build(start: str, headers: list[tuple[str, str]], body: str = "") -> bytes:
    payload = body.encode()
    lines = [start, *(f"{name}: {value}" for name, value in headers)]
    lines.append(f"Content-Length: {len(payload)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + payload


def response(
    req: Message,
    code: int,
    reason: str,
    *,
    to_tag: str = "",
    contact: str = "",
    body: str = "",
    extra: tuple[tuple[str, str], ...] = (),
) -> bytes:
    """תשובה לבקשה: מחזירה את כל כותרות הניתוב כפי שהגיעו."""
    to = req.get("to")
    if to_tag and not tag_of(to):
        to += f";tag={to_tag}"
    headers = [("Via", via) for via in req.all("via")]
    if req.method == "INVITE" and 100 < code < 300:
        headers += [("Record-Route", r) for r in req.all("record-route")]
    headers += [
        ("From", req.get("from")),
        ("To", to),
        ("Call-ID", req.call_id),
        ("CSeq", req.get("cseq")),
    ]
    if contact:
        headers.append(("Contact", contact))
    headers.append(("User-Agent", USER_AGENT))
    headers += list(extra)
    if body:
        headers.append(("Content-Type", "application/sdp"))
    return build(f"SIP/2.0 {code} {reason}", headers, body)


# ---- אימות ----

_HASHES = {
    "MD5": hashlib.md5,
    "MD5-SESS": hashlib.md5,
    "SHA-256": hashlib.sha256,
    "SHA-256-SESS": hashlib.sha256,
}
_PARAM = re.compile(r'([\w-]+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^,\s]+))')


def parse_challenge(value: str) -> dict[str, str] | None:
    scheme, _, rest = value.strip().partition(" ")
    if scheme.lower() != "digest":
        return None
    return {key.lower(): quoted or bare
            for key, quoted, bare in _PARAM.findall(rest)}


def pick_challenge(values: list[str]) -> dict[str, str] | None:
    """האתגר הראשון שאנחנו יודעים לענות עליו."""
    for value in values:
        challenge = parse_challenge(value)
        if challenge is None or not challenge.get("nonce"):
            continue
        if challenge.get("algorithm", "MD5").upper() in _HASHES:
            return challenge
    return None


def authorization(
    challenge: dict[str, str],
    *,
    method: str,
    uri: str,
    username: str,
    password: str,
    nc: int = 1,
    cnonce: str = "",
) -> str:
    """ערך הכותרת Authorization לאתגר נתון."""
    algorithm = challenge.get("algorithm", "MD5")
    hasher = _HASHES[algorithm.upper()]

    def digest(text: str) -> str:
        return hasher(text.encode()).hexdigest()

    realm, nonce = challenge.get("realm", ""), challenge["nonce"]
    cnonce = cnonce or secrets.token_hex(8)
    ha1 = digest(f"{username}:{realm}:{password}")
    if algorithm.upper().endswith("-SESS"):
        ha1 = digest(f"{ha1}:{nonce}:{cnonce}")
    ha2 = digest(f"{method}:{uri}")
    out = (f'Digest username="{username}", realm="{realm}", '
           f'nonce="{nonce}", uri="{uri}", ')
    qop = [item.strip().lower() for item in challenge.get("qop", "").split(",")]
    if "auth" in qop:
        count = f"{nc:08x}"
        reply = digest(f"{ha1}:{nonce}:{count}:{cnonce}:auth:{ha2}")
        out += f'response="{reply}", qop=auth, nc={count}, cnonce="{cnonce}"'
    else:
        out += f'response="{digest(f"{ha1}:{nonce}:{ha2}")}"'
    if "opaque" in challenge:
        out += f', opaque="{challenge["opaque"]}"'
    return out + f", algorithm={algorithm}"


# ---- SDP ----

@dataclass(frozen=True)
class Sdp:
    ip: str
    port: int
    payloads: tuple[int, ...]
    event_pt: int | None
    secure: bool


def parse_sdp(body: str) -> Sdp | None:
    """ערוץ השמע הראשון בהצעה, או None כשאין."""
    ip, media_ip, port, payloads, event_pt, secure = "", "", 0, (), None, False
    in_audio = seen_audio = False
    for line in body.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if line.startswith("m="):
            if seen_audio:
                break
            parts = line[2:].split()
            if len(parts) >= 3 and parts[0] == "audio" and parts[1].split("/")[0].isdigit():
                in_audio = seen_audio = True
                port = int(parts[1].split("/")[0])
                secure = "SAVP" in parts[2].upper()
                payloads = tuple(int(p) for p in parts[3:] if p.isdigit())
            continue
        if line.startswith("c="):
            parts = line[2:].split()
            if len(parts) >= 3 and parts[1] == "IP4":
                if in_audio:
                    media_ip = parts[2].split("/")[0]
                elif not seen_audio:
                    ip = parts[2].split("/")[0]
        elif in_audio and line.startswith("a=rtpmap:"):
            found = re.match(r"a=rtpmap:(\d+)\s+telephone-event/8000", line, re.I)
            if found and event_pt is None:
                event_pt = int(found.group(1))
    if not seen_audio or not (media_ip or ip):
        return None
    return Sdp(media_ip or ip, port, payloads, event_pt, secure)


def pick_payload(offer: Sdp) -> int | None:
    """A-law אם הוצע, אחרת µ-law, אחרת אין קודק משותף."""
    for payload in (PT_ALAW, PT_ULAW):
        if payload in offer.payloads:
            return payload
    return None


_CODEC_NAMES = {PT_ALAW: "PCMA", PT_ULAW: "PCMU"}


def build_sdp(
    ip: str,
    port: int,
    *,
    payloads: tuple[int, ...] = (PT_ALAW, PT_ULAW),
    event_pt: int | None = 101,
    session: int = 0,
) -> str:
    formats = [*payloads] + ([event_pt] if event_pt is not None else [])
    lines = [
        "v=0",
        f"o=- {session} {session} IN IP4 {ip}",
        "s=ha-ivr",
        f"c=IN IP4 {ip}",
        "t=0 0",
        f"m=audio {port} RTP/AVP {' '.join(str(f) for f in formats)}",
        *(f"a=rtpmap:{p} {_CODEC_NAMES[p]}/8000" for p in payloads),
    ]
    if event_pt is not None:
        lines += [f"a=rtpmap:{event_pt} telephone-event/8000",
                  f"a=fmtp:{event_pt} 0-16"]
    lines += ["a=ptime:20", "a=sendrecv"]
    return "\r\n".join(lines) + "\r\n"


# ---- RTP ----

@dataclass(frozen=True)
class Rtp:
    pt: int
    seq: int
    ts: int
    payload: bytes
    marker: bool


def rtp_packet(pt: int, seq: int, ts: int, ssrc: int, payload: bytes,
               marker: bool = False) -> bytes:
    return struct.pack(
        "!BBHII", 0x80, (0x80 if marker else 0) | pt,
        seq & 0xFFFF, ts & 0xFFFFFFFF, ssrc & 0xFFFFFFFF,
    ) + payload


def rtp_parse(data: bytes) -> Rtp | None:
    if len(data) < 12 or data[0] >> 6 != 2:
        return None
    first, second, seq, ts = struct.unpack("!BBHI", data[:8])
    offset = 12 + 4 * (first & 0x0F)
    if first & 0x10:  # הרחבת כותרת
        if len(data) < offset + 4:
            return None
        offset += 4 + 4 * struct.unpack("!H", data[offset + 2:offset + 4])[0]
    end = len(data)
    if first & 0x20 and end > offset:  # ריפוד
        end -= data[-1]
    if end < offset:
        return None
    return Rtp(second & 0x7F, seq, ts, data[offset:end], bool(second & 0x80))


def rtp_event(payload: bytes) -> tuple[str, bool, int] | None:
    """מקש ב-RFC 2833: הספרה, האם זו חבילת הסיום, ומשך ההקשה."""
    if len(payload) < 4 or payload[0] >= len(_DIGITS):
        return None
    duration = struct.unpack("!H", payload[2:4])[0]
    return _DIGITS[payload[0]], bool(payload[1] & 0x80), duration


def info_digit(content_type: str, body: str) -> str | None:
    """מקש שנשלח בהודעת INFO במקום בערוץ השמע."""
    kind = content_type.split(";")[0].strip().lower()
    if kind == "application/dtmf-relay":
        found = re.search(r"(?im)^\s*signal\s*=\s*(\S+)", body)
        value = found.group(1) if found else ""
    elif kind == "application/dtmf":
        value = body.strip()
    else:
        return None
    if value.isdigit() and 10 <= int(value) <= 15:
        value = _DIGITS[int(value)]
    value = value.upper()
    return value if len(value) == 1 and value in _DIGITS else None


# ---- G.711 ----

_SEG_A = (0x1F, 0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF)
_SEG_U = (0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF)


def _segment(value: int, table: tuple[int, ...]) -> int:
    for index, top in enumerate(table):
        if value <= top:
            return index
    return len(table)


def _lin2alaw(value: int) -> int:  # 13 סיביות
    mask = 0xD5
    if value < 0:
        mask, value = 0x55, -value - 1
    seg = _segment(value, _SEG_A)
    if seg >= 8:
        return 0x7F ^ mask
    low = (value >> 1) if seg < 2 else (value >> seg)
    return ((seg << 4) | (low & 0x0F)) ^ mask


def _lin2ulaw(value: int) -> int:  # 14 סיביות
    mask = 0xFF
    if value < 0:
        mask, value = 0x7F, -value
    value = min(value, 8159) + 33
    seg = _segment(value, _SEG_U)
    if seg >= 8:
        return 0x7F ^ mask
    return ((seg << 4) | ((value >> (seg + 1)) & 0x0F)) ^ mask


def _alaw2lin(code: int) -> int:
    code ^= 0x55
    value = (code & 0x0F) << 4
    seg = (code & 0x70) >> 4
    if seg == 0:
        value += 8
    elif seg == 1:
        value += 0x108
    else:
        value = (value + 0x108) << (seg - 1)
    return value if code & 0x80 else -value


def _ulaw2lin(code: int) -> int:
    code = ~code & 0xFF
    value = (((code & 0x0F) << 3) + 0x84) << ((code & 0x70) >> 4)
    return (0x84 - value) if code & 0x80 else (value - 0x84)


_ENCODE = {
    PT_ALAW: bytes(_lin2alaw(v) for v in range(-4096, 4096)),
    PT_ULAW: bytes(_lin2ulaw(v) for v in range(-8192, 8192)),
}
_SHIFT = {PT_ALAW: (3, 4096), PT_ULAW: (2, 8192)}
_DECODE = {
    PT_ALAW: tuple(_alaw2lin(c) for c in range(256)),
    PT_ULAW: tuple(_ulaw2lin(c) for c in range(256)),
}
SILENCE = {PT_ALAW: 0xD5, PT_ULAW: 0xFF}


def encode(pcm: bytes, pt: int) -> bytes:
    """PCM של 16 סיביות (little endian) ל-G.711."""
    count = len(pcm) // 2
    table = _ENCODE[pt]
    shift, offset = _SHIFT[pt]
    samples = struct.unpack(f"<{count}h", pcm[:count * 2])
    return bytes([table[(s >> shift) + offset] for s in samples])


def decode(data: bytes, pt: int) -> bytes:
    """G.711 ל-PCM של 16 סיביות (little endian)."""
    table = _DECODE[pt]
    return struct.pack(f"<{len(data)}h", *[table[b] for b in data])
