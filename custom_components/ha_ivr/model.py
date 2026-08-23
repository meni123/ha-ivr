"""המודל המשותף לכל הספקים.

שום דבר כאן אינו יודע מי הספק. הליבה בונה Prompt או Terminal,
והדרייבר מתרגם לפורמט שלו.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

# מקשים שהליבה שומרת לניווט ולעולם אינם חלק מהנתיב.
# שני מקשי ניווט קבועים, זהים בכל הספקים.
KEY_BACK = "0"
KEY_ROOT = "*"


@dataclass(frozen=True)
class CallContext:
    """בקשה נכנסת, אחרי פענוח, ובלי תלות בספק."""

    call_id: str
    caller: str
    did: str
    path: tuple[str, ...]
    digit: str | None
    step: int
    hangup: bool = False
    raw: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Say:
    """פריט השמעה בודד.

    `raw` הוא טקסט שאינו עובר את מסנן הספק. הוא קיים אך ורק לצורך
    בדיקת פרוטוקול — לגלות מה ספק עושה עם תו נתון. אין להשתמש בו
    בנתיב רגיל: הוא עוקף בכוונה את שומר הסף.
    """

    kind: Literal["text", "number", "digits", "file", "raw"]
    data: str


@dataclass(frozen=True)
class Prompt:
    """השמע ובקש הקשה."""

    messages: list[Say]
    allowed: frozenset[str]
    at_path: tuple[str, ...]
    step: int
    timeout: int = 10


@dataclass(frozen=True)
class Terminal:
    """השמע וסיים.

    אין הבחנה בין סיומים: כל סיום הוא ניתוק. חזרה לשורש נשקלה
    ונדחתה — היא הייתה רלוונטית רק למסלול נפילה של `CodecError`
    שאינו נגיש בפועל, כי עומק התפריט חסום ב-4 ושם הפרמטר לעולם
    אינו מתקרב למגבלת האורך.
    """

    messages: list[Say]


@dataclass(frozen=True)
class GoTo:
    """מעבר לשלוחה אחרת אצל הספק.

    נתמך בטכנוליין. בימות יש go_to_folder לנתיב, ולכן זה מתורגם
    שם לנתיב שלוחה במקום למזהה.
    """

    target: str
    messages: list[Say] = field(default_factory=list)


Action = Prompt | Terminal | GoTo


# ----------------------------------------------------------------------
# הקראת מספרים
# ----------------------------------------------------------------------


def say_number(
    value: float, *, decimal_word: str = "נקודה", minus_word: str = "מינוס"
) -> list[Say]:
    """פירוק מספר לפריטי השמעה, בלי נקודה ובלי מקף.

    בימות הנקודה היא מפריד בין הודעות, ולכן `21.5` בתוך טקסט קוטע
    את התשובה באמצע. הפירוק גם נשמע טוב יותר: מנוע ההקראה מקבל
    מספר שלם ומקריא אותו כמספר ולא כרצף ספרות.

    הסימן השלילי יוצא כמילה ולא כתו. פריט מסוג `number` אינו
    עובר במסנן של ימות, ומקף שיישאר בערך ייצא כ-`n--18` — מקף
    בתוך התוכן, שהוא בדיוק התו שמפריד בין הסוג לתוכן.
    """
    rounded = round(float(value), 1)
    prefix: list[Say] = []
    if rounded < 0:
        prefix = [Say("text", minus_word)]
        rounded = -rounded
    if rounded == int(rounded):
        return [*prefix, Say("number", str(int(rounded)))]
    whole, frac = f"{rounded:.1f}".split(".")
    return [
        *prefix,
        Say("number", whole),
        Say("text", decimal_word),
        Say("number", frac),
    ]
