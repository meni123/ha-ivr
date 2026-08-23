"""השער בסטרימינג: כל מסלול יציאה מ-`_speak` חייב לפתוח אותו.

השער נסגר לפני שאנחנו מדברים (`_muted = True` ב-STT_VAD_END). מי
שיוצא מ-`_speak` בלי `await self._resume(...)` משאיר את הקלט סגור,
והשיחה מתה בשקט מוחלט — בלי שגיאה, בלי ניתוק, בלי שום סימן ביומן.

זה היה כלל במסמך. כלל שמסתמך על כך שמישהו יזכור אותו בעריכה
הבאה של פונקציה בת שישים שורה עם ארבעה מסלולי יציאה אינו כלל
אלא תקווה, ולכן הוא כאן.

**המכוון הוא `await` בלבד.** `async_create_task(self._resume())`
אינו נחשב: הוא מחזיר מיד, והשער נפתח מתישהו אחר כך או בכלל לא
אם המשימה נבלעת. ההבחנה הזו היא כל הערך של הבדיקה.

**מה שהבדיקה אינה מכסה:** פונקציות אחרות שנוגעות ב-`_muted`.
`_end_turn` פותח את השער בזוג מפורש ולא דרך `_resume`, וניתוח
זרימה מלא על הקובץ כולו היה מייצר התרעות שווא יותר משהיה מוצא
באגים. כאן נאכף החוזה במקום היחיד שבו הקוד עצמו מכריז עליו.

**היעד עבר ל-`satellite.py` ב-0.28.0.** `_speak` הלך אחרי הצינור,
ו-`stream.py` נשאר הסוקט בלבד — אין בו עוד שער לשמור עליו.

    python3 tests/check_gate.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "custom_components" / "ha_ivr" / "satellite.py"
GUARDED = "_speak"
OPENER = "_resume"

# הבלוק אינו נופל החוצה — הוא מסתיים ב-return או ב-raise.
EXITS = object()


def _opens_gate(node: ast.stmt) -> bool:
    """האם המשפט הוא `await self._resume(...)`."""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Await):
        return False
    call = node.value.value
    return (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == OPENER
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "self"
    )


def _analyze(body: list[ast.stmt], opened: bool, bad: list[int]):
    """מצב השער בסוף הבלוק, ורישום כל יציאה שמשאירה אותו סגור."""
    for stmt in body:
        if _opens_gate(stmt):
            opened = True
            continue

        if isinstance(stmt, ast.Return):
            if not opened:
                bad.append(stmt.lineno)
            return EXITS

        if isinstance(stmt, ast.Raise):
            # חריגה שיוצאת מהפונקציה אינה משאירה שער סגור בשקט:
            # הקורא רואה אותה ביומן. אינה נספרת ככשל.
            return EXITS

        if isinstance(stmt, ast.If):
            then = _analyze(stmt.body, opened, bad)
            other = _analyze(stmt.orelse, opened, bad) if stmt.orelse else opened
            if then is EXITS and other is EXITS:
                return EXITS
            if then is EXITS:
                opened = other
            elif other is EXITS:
                opened = then
            else:
                opened = then and other
            continue

        if isinstance(stmt, ast.Try):
            # שמרני: כל ענף נבדק מהמצב שלפני ה-try, ואחריו המצב
            # אינו נחשב פתוח — חריגה יכולה לקטוע את הגוף באמצע.
            for branch in (stmt.body, stmt.orelse, stmt.finalbody):
                if branch:
                    _analyze(branch, opened, bad)
            for handler in stmt.handlers:
                _analyze(handler.body, opened, bad)
            continue

        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            inner = _analyze(stmt.body, opened, bad)
            opened = opened if inner is EXITS else inner
            continue

        if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            # גוף שאולי אינו רץ כלל. מה שנפתח בתוכו אינו מובטח.
            _analyze(stmt.body, opened, bad)
            continue

    return opened


def main() -> int:
    tree = ast.parse(TARGET.read_text("utf-8"))
    target = next(
        (
            n for n in ast.walk(tree)
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
            and n.name == GUARDED
        ),
        None,
    )
    if target is None:
        print(f"FAIL — {GUARDED} אינה קיימת ב-{TARGET.name}. אם היא שונתה "
              f"את שמה, יש לעדכן כאן — לא למחוק את הבדיקה")
        return 1

    bad: list[int] = []
    end = _analyze(target.body, False, bad)
    if end is not EXITS and not end:
        bad.append(target.body[-1].lineno)

    if bad:
        print(f"FAIL — {GUARDED} יוצאת בלי לפתוח את השער:")
        for line in sorted(bad):
            print(f"  {TARGET.name}:{line}")
        print(f"\n  כל יציאה חייבת `await self.{OPENER}(...)` לפניה.")
        print("  בלעדיה הקלט נשאר סגור והשיחה מתה בשקט.")
        return 1

    print(f"PASS — כל מסלולי היציאה מ-{GUARDED} פותחים את השער")
    return 0


if __name__ == "__main__":
    sys.exit(main())
