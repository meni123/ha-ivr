"""אודיו: צלילי חיווי, המרת קצב, וחילוץ PCM מ-WAV.

מודול משותף לישות ולסוקט, שכן שניהם נוגעים באודיו.

שום דבר כאן אינו תלוי בספק: קצב הדגימה מגיע כארגומנט בכל
פונקציה, כי הוא נקרא ממסגרת הפתיחה של השיחה ואינו קבוע.
"""

from __future__ import annotations

import math
from array import array


# ברירת מחדל. הקצב האמיתי מגיע במסגרת ה-start בשדה format,
# בצורה "pcm16;rate=8000;ch=1".
PROVIDER_RATE = 8000
# הקצב שצינור ה-STT של Home Assistant עובד בו.
PIPELINE_RATE = 16000

# זמן המתנה נוסף אחרי סיום ההשמעה, לפני פתיחת הקלט. ההד חוזר
# מהקו באיחור קטן, ובלי החלון הזה הוא נכנס לתור ומזוהה כדיבור.
DEFAULT_ECHO_TAIL = 0.25


# ----------------------------------------------------------------------
# צלילי חיווי
# ----------------------------------------------------------------------


def tone(rate: int, *steps: tuple[int, int], volume: float = 0.38) -> bytes:
    """צליל מרצף (תדר, מילישניות), כ-PCM 16 ביט מונו.

    נוצר בקוד ולא מקובץ: קובץ מחייב אירוח, נתיב מדיה, והמרה
    לקצב שהספק שולח. סינוס הוא עשר שורות ותמיד בקצב הנכון.

    לכל מקטע יש עלייה ודעיכה של 5 מילישניות. בלעדיהן נשמע נקישה
    חדה בקצוות, שעל קו טלפון בולטת יותר מהצליל עצמו.
    """
    out = array("h")
    fade = max(1, int(rate * 0.005))
    for freq, ms in steps:
        count = int(rate * ms / 1000)
        if freq <= 0:
            # שקט מכוון בין שני צלילים. בלעדיו הם נשמעים כצליל
            # אחד מתפתל, ולא כשני צפצופים שאפשר לספור.
            out.extend([0] * count)
            continue
        for i in range(count):
            env = min(1.0, min(i, count - i - 1) / fade)
            out.append(
                int(32767 * volume * env * math.sin(2 * math.pi * freq * i / rate))
            )
    return out.tobytes()


def listen_tone(rate: int) -> bytes:
    """שני צלילים עולים — דבר עכשיו."""
    return tone(rate, (700, 110), (0, 40), (1100, 150))


def error_tone(rate: int) -> bytes:
    """שלושה צלילים נמוכים — משהו נכשל, אפשר לנסות שוב.

    בלי חיווי כזה כשל משאיר את המתקשר בשקט מוחלט: הוא אינו יודע
    אם לא נשמע, אם השיחה נפלה, או אם עליו לחזור על עצמו. בלוג
    אחד זה מה שהרג שיחה שלמה.
    """
    return tone(rate, (520, 90), (0, 60), (520, 90), (0, 60), (400, 140))


def thinking_tone(rate: int) -> bytes:
    """שני צלילים יורדים — נקלט, מעבד."""
    return tone(rate, (700, 80), (0, 30), (450, 110))


# ----------------------------------------------------------------------
# המרת קצב דגימה
# ----------------------------------------------------------------------


def resample(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """המרת PCM 16 ביט מונו בין קצבי דגימה, באינטרפולציה לינארית.

    מומש כאן ולא דרך audioop: המודול הזה הוסר מהספרייה התקנית
    בפייתון 3.13, ותלות בו שוברת את האינטגרציה בגרסאות חדשות
    של Home Assistant בלי שום אזהרה מוקדמת.

    אינטרפולציה לינארית מספיקה כאן. איכות הקו היא 8kHz בכל מקרה,
    והצוואר האמיתי הוא הטלפון ולא המרת הקצב.
    """
    if src_rate == dst_rate or not pcm:
        return pcm

    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return b""

    count = max(1, round(len(samples) * dst_rate / src_rate))
    step = (len(samples) - 1) / count if count > 1 else 0
    out = array("h", bytes(count * 2))

    for i in range(count):
        pos = i * step
        left = int(pos)
        right = min(left + 1, len(samples) - 1)
        frac = pos - left
        out[i] = int(samples[left] + (samples[right] - samples[left]) * frac)

    return out.tobytes()


# הכפלת קצב 8k→16k לזיהוי הדיבור: אפסים בין הדגימות ומסנן מעביר-נמוכים
# (sinc בחלון האנינג). אינטרפולציה לינארית משאירה בתדרים הגבוהים תמונות
# של הספקטרום, ופוגעת בדיוק התמלול.
UP2_TAPS = 31


def _up2_taps() -> list[float]:
    centre = (UP2_TAPS - 1) / 2
    taps = []
    for i in range(UP2_TAPS):
        x = i - centre
        sinc = 1.0 if x == 0 else math.sin(math.pi * x / 2) / (math.pi * x / 2)
        taps.append(sinc * (0.5 - 0.5 * math.cos(2 * math.pi * i / (UP2_TAPS - 1))))
    return taps


class Upsampler2x:
    """הכפלת קצב עם מסנן, לזרם של מסגרות. שומר את זנב המסנן בין מסגרות.

    דורש numpy (קיים בכל התקנת HA). בלעדיו `available` כבוי, והקורא
    נשאר עם `resample` הלינארי.
    """

    def __init__(self) -> None:
        try:
            import numpy as np  # noqa: PLC0415
        except ImportError:
            self._np = None
            return
        self._np = np
        self._taps = np.array(_up2_taps())
        self._hist = np.zeros(UP2_TAPS - 1)

    @property
    def available(self) -> bool:
        return self._np is not None

    def process(self, pcm: bytes) -> bytes:
        np = self._np
        samples = np.frombuffer(pcm[: len(pcm) - (len(pcm) % 2)], dtype="<i2")
        if not samples.size:
            return b""
        up = np.zeros(samples.size * 2)
        up[::2] = samples
        joined = np.concatenate((self._hist, up))
        out = np.convolve(joined, self._taps, mode="valid")
        self._hist = joined[-(UP2_TAPS - 1):]
        return np.clip(np.rint(out), -32768, 32767).astype("<i2").tobytes()


def strip_wav(data: bytes) -> tuple[bytes, int]:
    """חילוץ ה-PCM והקצב מקובץ WAV, בלי wave ובלי קובץ זמני."""
    if len(data) < 44 or data[:4] != b"RIFF":
        return b"", PIPELINE_RATE

    rate = PIPELINE_RATE
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        body = pos + 8
        if chunk_id == b"fmt " and body + 8 <= len(data):
            rate = int.from_bytes(data[body + 4 : body + 8], "little") or PIPELINE_RATE
        elif chunk_id == b"data":
            if size == 0:
                # כותרת של הקראה בזרימה: האורך לא ידוע כשהיא נכתבת,
                # ולכן הוא 0, וה-PCM כולו אחריה. בלי זה הקראה מלאה
                # שנאספה מזרימה חוזרת ריקה, והשיחה שותקת.
                size = len(data) - body
            pcm = data[body : body + size]
            return pcm[: len(pcm) - (len(pcm) % 2)], rate
        pos = body + size + (size % 2)
    return b"", rate


def wav_data_start(head: bytes) -> tuple[int, int] | None:
    """תחילת ה-PCM בהקראה שמגיעה בזרימה: (קצב, היסט).

    `None` כשעוד לא הגיעה כותרת שלמה, ו-`(0, -1)` כשזה אינו WAV.
    בזרימה הכותרת מגיעה ראשונה ואחריה PCM ללא סוף ידוע, ולכן
    `strip_wav` — שמחכה לקובץ שלם — אינו מתאים כאן.
    """
    if len(head) < 12:
        return None
    if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        return 0, -1
    rate = PIPELINE_RATE
    pos = 12
    while pos + 8 <= len(head):
        chunk_id = head[pos : pos + 4]
        size = int.from_bytes(head[pos + 4 : pos + 8], "little")
        body = pos + 8
        if chunk_id == b"data":
            return rate, body
        if chunk_id == b"fmt " and body + 8 <= len(head):
            rate = int.from_bytes(head[body + 4 : body + 8], "little") or PIPELINE_RATE
        pos = body + size + (size % 2)
    return None


def wav_format(data: bytes) -> tuple[int, int, int]:
    """קצב, ערוצים ועומק סיביות מתוך מקטע ה-`fmt`.

    `strip_wav` מחזיר קצב בלבד, כי זה מה שההשמעה צריכה. כאן
    נקראות גם ההנחות שלה — מונו ו-16 ביט — כדי שהפרה שלהן
    תדווח במקום להישמע כרעש.

    `(0, 0, 0)` כשאין מקטע `fmt` תקין.
    """
    if len(data) < 44 or data[:4] != b"RIFF":
        return 0, 0, 0
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        body = pos + 8
        if chunk_id == b"fmt " and body + 16 <= len(data):
            channels = int.from_bytes(data[body + 2 : body + 4], "little")
            rate = int.from_bytes(data[body + 4 : body + 8], "little")
            bits = int.from_bytes(data[body + 14 : body + 16], "little")
            return rate, channels, bits
        pos = body + size + (size % 2)
    return 0, 0, 0
