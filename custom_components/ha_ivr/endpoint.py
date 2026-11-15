"""זיהוי סוף דיבור בקו טלפון: שקט רצוף, לא שקט מצטבר.

ה-VAD של הצינור (`VoiceCommandSegmenter`) צובר שקט לאורך כל הפקודה. בקו
טלפון גם דיבור רציף מלא נפילות קצרות בהסתברות, ולכן השקט מצטבר עד הסף
והמתקשר נקטע באמצע משפט.

כאן הכלל הוא שקט *רצוף*: הפקודה נגמרת רק אחרי `silence` שניות שבהן אף
מקטע לא נשמע כדיבור. אותו מנוע הסתברות (`pymicro_vad`), כלל אחר.

מילה קצרה ("כן", "לא") אינה מעירה את המנוע: ההסתברות שלה בקו נשארת מתחת
ל-0.1. בלי מסלול נוסף הפקודה לא "מתחילה", ולכן גם לא נגמרת. לכן יש גם
מסלול עוצמה: קול שבולט מעל רצפת הרעש של הקו פותח פקודה, ואז היא נגמרת
בשקט רצוף באותו אורך. כשהמנוע עצמו שומע דיבור, העוצמה אינה משתתפת בכלל.

עוצמה לבדה אינה מבדילה מילה מרעש, ולכן שלושה גבולות:
- קול חזק שנמשך `LOUD_MAX_SEC` בלי שהמנוע שמע דיבור אינו מילה אלא רעש
  בקו. הוא הופך לרצפה החדשה והפתיחה מתבטלת.
- הרצפה עוברת מתור לתור באותה שיחה (`floor`), כך שהקו נלמד פעם אחת.
- פקודה שהמנוע לא אישר נסגרת ב-`NO_SPEECH_SEC`, כמו קו שותק.

התקרות כאן ולא בצינור: ה-VAD שלו כבוי (ראו `satellite.py`), והתקרה שלו
— 15 שניות לכל פקודה — קוטעת הכתבה ארוכה. `MAX_TURN_SEC` הוא מה שמנוע
התמלול מרשה, ומ-`LAND_SEC` מספיקה הפסקה קצרה, כדי שהחיתוך ייפול בין
מילים ולא באמצע מילה.

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
# קול חזק רצוף באורך כזה, בלי דיבור לפי המנוע, הוא רעש בקו ולא מילה.
LOUD_MAX_SEC = 2.0
# רצפת הרעש: יורדת מיד לרמה נמוכה יותר, ועולה לאט (כ-10% לשנייה) אחרי
# רמה שאינה בולטת. קול בולט אינו מזיז אותה — דיבור אינו רעש רקע.
FLOOR_RISE = 1.001
FLOOR_START = 50.0

# תור שבו המנוע לא שמע דיבור נסגר כאן, כדי שהצינור לא יחכה לנצח.
NO_SPEECH_SEC = 15.0
# אורך פקודה מרבי. מנוע התמלול של Google Cloud ב-HA סוגר את הזרם אחרי
# 30 שניות ומחזיר שגיאה, ולכן עוצרים לפניו עם מרווח לתשובה שלו.
MAX_TURN_SEC = 25.0
# מכאן ועד התקרה די בהפסקה קצרה כדי לסיים.
LAND_SEC = 20.0
LAND_SILENCE = 0.3

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

    def __init__(
        self,
        silence: float,
        vad: Callable[[bytes], float] | None = None,
        floor: float | None = None,
    ) -> None:
        self._need = silence
        self._vad = vad
        self._buf = b""
        self._chunks = 0
        self._speech = 0.0
        self._loud = 0.0
        self._quiet = 0.0
        # רצפת הרעש של הקו. מי שמריץ כמה תורות באותה שיחה מעביר אותה הלאה.
        self.floor = FLOOR_START if floor is None else floor
        self.started = False
        # True כשרק העוצמה פתחה את הפקודה (מילה קצרה שהמנוע לא שמע)
        self.by_energy = False
        # למה התור נגמר: "silence", "no speech" או "max length"
        self.reason = ""

    @property
    def elapsed(self) -> float:
        """כמה אודיו עבר בתור, בשניות."""
        return self._chunks * CHUNK_SEC

    def _is_loud(self, level: float | None) -> bool:
        if not level:
            return False
        if level > max(self.floor * LOUD_RATIO, LOUD_MIN):
            return True
        self.floor = min(level, self.floor * FLOOR_RISE)
        return False

    def step(self, prob: float, level: float | None = None) -> bool:
        """מקטע אחד לפי ההסתברות שלו (ו-RMS, אם נמדד). True כשהתור נגמר."""
        self._chunks += 1
        loud = self._is_loud(level)
        if not self.started:
            self._speech = self._speech + CHUNK_SEC if prob > SPEECH else 0.0
            self._loud = self._loud + CHUNK_SEC if loud else 0.0
            if self._speech >= START_SEC:
                self.started = True
            elif self._loud >= LOUD_START_SEC:
                self.started = self.by_energy = True
                self._speech = 0.0
        elif prob > SPEECH:
            # המנוע שמע דיבור — מכאן הוא לבדו מכריע, כמו בפקודה רגילה
            self.by_energy = False
            self._quiet = 0.0
        elif self.by_energy and loud:
            self._quiet = 0.0
            self._loud += CHUNK_SEC
            if self._loud >= LOUD_MAX_SEC:
                # ארוך מדי למילה: זה הרעש של הקו, והפתיחה מתבטלת
                self.floor = level
                self.started = self.by_energy = False
                self._loud = 0.0
        else:
            self._loud = 0.0
            if prob <= QUIET:
                self._quiet += CHUNK_SEC
        self.reason = self._end_reason()
        return bool(self.reason)

    def _end_reason(self) -> str:
        elapsed = self.elapsed
        if self.started:
            need = self._need if elapsed < LAND_SEC else min(self._need, LAND_SILENCE)
            if self._quiet >= need:
                return "silence"
        if elapsed >= MAX_TURN_SEC:
            return "max length"
        # בלי אישור של המנוע. רצף דיבור שרק התחיל מקבל את הרגע שלו.
        confirmed = self.started and not self.by_energy
        if not confirmed and elapsed >= NO_SPEECH_SEC and not self._speech:
            return "no speech"
        return ""

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
