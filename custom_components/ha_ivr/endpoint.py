"""זיהוי סוף דיבור בקו טלפון: שקט רצוף, לא שקט מצטבר.

ה-VAD של הצינור (`VoiceCommandSegmenter`) צובר שקט לאורך כל הפקודה. בקו
טלפון גם דיבור רציף מלא נפילות קצרות בהסתברות, ולכן השקט מצטבר עד הסף
והמתקשר נקטע באמצע משפט.

כאן הכלל הוא שקט *רצוף*: הפקודה נגמרת רק אחרי `silence` שניות שבהן אף
מקטע לא נשמע כדיבור. אותו מנוע הסתברות (`pymicro_vad`), כלל אחר.

`step` טהור ונבדק בלי מנוע; `feed` חותך את האודיו למקטעי 10ms.
"""

from __future__ import annotations

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

# הבורר "רגישות לסוף דיבור" → שניות של שקט רצוף.
SILENCE_BY_SENSITIVITY = {"aggressive": 0.5, "default": 0.8, "relaxed": 1.2}


class Endpointer:
    """סוף פקודה אחרי `silence` שניות של שקט רצוף מאז שהדיבור התחיל."""

    def __init__(self, silence: float, vad: Callable[[bytes], float] | None = None) -> None:
        self._need = silence
        self._vad = vad
        self._buf = b""
        self._speech = 0.0
        self._quiet = 0.0
        self.started = False

    def step(self, prob: float) -> bool:
        """מקטע אחד לפי ההסתברות שלו. True כשהפקודה נגמרה."""
        if not self.started:
            self._speech = self._speech + CHUNK_SEC if prob > SPEECH else 0.0
            self.started = self._speech >= START_SEC
            return False
        if prob > SPEECH:
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
            if self.step(prob if prob >= 0 else 0.0):
                return True
        return False


def make_vad() -> Callable[[bytes], float] | None:
    """מנוע ההסתברות של הצינור, או None אם אינו זמין בהתקנה."""
    try:
        from pymicro_vad import MicroVad  # noqa: PLC0415
    except ImportError:
        return None
    return MicroVad().Process10ms
