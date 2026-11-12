"""זיהוי סוף דיבור בקו טלפון: שקט רצוף, לא שקט מצטבר.

ה-VAD של הצינור (`VoiceCommandSegmenter`) צובר שקט לאורך כל הפקודה. בקו
טלפון גם דיבור רציף מלא נפילות קצרות בהסתברות, ולכן השקט מצטבר עד הסף
והמתקשר נקטע באמצע משפט.

כאן הכלל הוא שקט *רצוף*: הפקודה נגמרת רק אחרי `silence` שניות שבהן אף
מקטע לא נשמע כדיבור. אותו מנוע הסתברות (`pymicro_vad`), כלל אחר.

מילה קצרה ("כן", "לא") אינה מעירה את המנוע: ההסתברות שלה בקו נשארת מתחת
ל-0.1. בלי מסלול נוסף הפקודה לא "מתחילה", ולכן גם לא נגמרת — והמתקשר
מחכה לתקרת הזמן של הצינור. לכן יש גם מסלול עוצמה: קול שבולט מעל רצפת
הרעש של הקו פותח פקודה, ואז היא נגמרת בשקט רצוף באותו אורך. כשהמנוע
עצמו פותח את הפקודה, העוצמה אינה משתתפת בכלל — ההתנהגות למשפט רגיל
לא השתנתה.

`step` טהור ונבדק בלי מנוע; `feed` חותך את האודיו למקטעי 10ms.
"""

from __future__ import annotations

from array import array
from typing import Callable

CHUNK_BYTES = 320  # 10ms של 16kHz, 16 ביט
CHUNK_SEC = 0.01

# מעל SPEECH — דיבור. מתחת ל-QUIET — שקט. ביניהם — לא זה ולא זה: לא
# מאפס את ספירת השקט, וגם לא מוסיף לה. הסף הנמוך לשקט שומר על סוף מילה
# חלש מלהיחשב שתיקה.
SPEECH = 0.5
QUIET = 0.3
# כמה דיבור רצוף פותח פקודה. רעש קצר בתחילת התור לא נחשב.
START_SEC = 0.2

# מסלול העוצמה. קול = RMS מעל פי LOUD_RATIO מרצפת הרעש (כ-16dB), וגם מעל
# LOUD_MIN (כ-‎-40dBFS), כדי שקו שקט לגמרי לא יהפוך כל רחש לדיבור.
LOUD_RATIO = 6.0
LOUD_MIN = 300.0
LOUD_START_SEC = 0.15
# רצפת הרעש: יורדת מיד לרמה נמוכה יותר, ועולה לאט (כ-10% לשנייה).
FLOOR_RISE = 1.001
FLOOR_START = 50.0

# הבורר "רגישות לסוף דיבור" → שניות של שקט רצוף.
SILENCE_BY_SENSITIVITY = {"aggressive": 0.5, "default": 0.8, "relaxed": 1.2}


def rms(chunk: bytes) -> float:
    samples = array("h")
    samples.frombytes(chunk[: len(chunk) - (len(chunk) % 2)])
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


class Endpointer:
    """סוף פקודה אחרי `silence` שניות של שקט רצוף מאז שהדיבור התחיל."""

    def __init__(self, silence: float, vad: Callable[[bytes], float] | None = None) -> None:
        self._need = silence
        self._vad = vad
        self._buf = b""
        self._speech = 0.0
        self._loud = 0.0
        self._quiet = 0.0
        self._floor = FLOOR_START
        self.started = False
        # True כשרק העוצמה פתחה את הפקודה (מילה קצרה שהמנוע לא שמע)
        self.by_energy = False

    def _is_loud(self, level: float | None) -> bool:
        if level is None:
            return False
        loud = level > max(self._floor * LOUD_RATIO, LOUD_MIN)
        self._floor = min(level, self._floor * FLOOR_RISE) if level > 0 else self._floor
        return loud

    def step(self, prob: float, level: float | None = None) -> bool:
        """מקטע אחד לפי ההסתברות שלו (ו-RMS, אם נמדד). True כשהפקודה נגמרה."""
        loud = self._is_loud(level)
        if not self.started:
            self._speech = self._speech + CHUNK_SEC if prob > SPEECH else 0.0
            self._loud = self._loud + CHUNK_SEC if loud else 0.0
            if self._speech >= START_SEC:
                self.started = True
            elif self._loud >= LOUD_START_SEC:
                self.started = self.by_energy = True
            return False
        if prob > SPEECH:
            # המנוע שמע דיבור — מכאן הוא לבדו מכריע, כמו בפקודה רגילה
            self.by_energy = False
            self._quiet = 0.0
        elif self.by_energy and loud:
            self._quiet = 0.0
        elif prob <= QUIET:
            self._quiet += CHUNK_SEC
        return self._quiet >= self._need

    def feed(self, audio: bytes) -> bool:
        """אודיו של 16kHz, בכל אורך. True כשהפקודה נגמרה."""
        if self._vad is None:
            return False
        self._buf += audio
        while len(self._buf) >= CHUNK_BYTES:
            chunk, self._buf = self._buf[:CHUNK_BYTES], self._buf[CHUNK_BYTES:]
            prob = self._vad(chunk)
            if self.step(prob if prob >= 0 else 0.0, rms(chunk)):
                return True
        return False


def make_vad() -> Callable[[bytes], float] | None:
    """מנוע ההסתברות של הצינור, או None אם אינו זמין בהתקנה."""
    try:
        from pymicro_vad import MicroVad  # noqa: PLC0415
    except ImportError:
        return None
    return MicroVad().Process10ms
