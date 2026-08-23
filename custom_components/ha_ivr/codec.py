"""נשיאת המיקום בעץ, בלי מצב בצד השרת.

שם הפרמטר שנשלח לספק מכיל את הנתיב שממנו נשאלה השאלה. הספק
מחזיר אותו יחד עם ההקשה, ומכאן משוחזר המיקום החדש. אין מילון
בזיכרון, ולכן שיחה שורדת ריסטרט של Home Assistant.

    encode(step=3, path=("1","2"))  ->  "s3_1x2"
    decode({"s3_1x2": "7"})         ->  path=("1","2") digit="7" step=4

כל דרייבר מחזיק מופע משלו. אם ספק מגביל את התווים המותרים בשם
הפרמטר, משנים כאן את האלפבית ולא נוגעים בשום דרייבר.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import KEY_BACK, KEY_ROOT


class CodecError(Exception):
    """הנתיב אינו ניתן לקידוד באילוצים של הספק הזה."""


@dataclass(frozen=True)
class Decoded:
    path: tuple[str, ...]
    digit: str | None
    step: int


@dataclass(frozen=True)
class PathCodec:
    """מקודד ומפענח מיקום, לפי אילוצי הספק."""

    prefix: str = "s"
    sep: str = "_"
    joiner: str = "x"
    max_len: int = 64

    symbols: dict[str, str] = field(
        default_factory=lambda: {KEY_BACK: "a", KEY_ROOT: "b"}
    )
    """מקשים שאינם ספרות. שמורים לניווט ואינם אמורים להגיע לנתיב,
    אבל המיפוי קיים כדי שלא ניפול אם כן."""

    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        alphabet = {self.sep, self.joiner, *self.symbols.values()}
        if len(alphabet) != 2 + len(self.symbols):
            raise ValueError("מפריד, מחבר וסמלים חייבים להיות שונים זה מזה")

    @property
    def _pattern(self) -> re.Pattern[str]:
        syms = "".join(re.escape(v) for v in self.symbols.values())
        return re.compile(
            rf"{re.escape(self.prefix)}(\d+){re.escape(self.sep)}"
            rf"([0-9{re.escape(self.joiner)}{syms}]*)"
        )

    # ------------------------------------------------------------------

    def encode(self, step: int, path: tuple[str, ...]) -> str:
        """בניית שם הפרמטר עבור שאלה שנשאלת מהנתיב הנתון."""
        segments = [self.symbols.get(part, part) for part in path]
        name = f"{self.prefix}{step}{self.sep}{self.joiner.join(segments)}"
        if len(name) > self.max_len:
            raise CodecError(
                f"הנתיב {'/'.join(path)} חורג ממגבלת {self.max_len} התווים "
                f"של הספק"
            )
        return name

    def decode(self, params: dict[str, str]) -> Decoded:
        """שחזור המיקום מתוך הפרמטרים שהספק החזיר.

        נלקח הצעד הגבוה ביותר. ספק שצובר ערכים ישלח את כל
        ההיסטוריה, וספק שאינו צובר ישלח רק את האחרון — לשניהם
        התוצאה זהה, כי הנתיב נמצא בשם עצמו.
        """
        pattern = self._pattern
        found: list[tuple[int, str, str]] = []
        for key, value in params.items():
            match = pattern.fullmatch(key)
            if match:
                found.append((int(match.group(1)), match.group(2), value))

        if not found:
            return Decoded(path=(), digit=None, step=1)

        step, encoded_path, digit = max(found, key=lambda item: item[0])
        reverse = {v: k for k, v in self.symbols.items()}
        path = tuple(
            reverse.get(part, part)
            for part in encoded_path.split(self.joiner)
            if part
        )
        return Decoded(path=path, digit=digit or None, step=step + 1)


# ימות: אין מגבלה ידועה על שם הפרמטר.
YEMOT_CODEC = PathCodec()

# טכנוליין: האילוצים על שדה name טרם התקבלו מהספק.
# אם יתברר שקו תחתון אסור, להחליף sep. אם יש מגבלת אורך, לעדכן
# max_len — תיזרק CodecError במקום קטיעה שקטה.
TECHNOLINE_CODEC = PathCodec()
