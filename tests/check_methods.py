#!/usr/bin/env python3
"""שער: כל `self._x` שמחלקה קוראת לו חייב להתקיים עליה או על אב שלה.

נכתב אחרי שארבע מתודות אבדו ממחלקת בסיס בעריכה שהזיזה בלוק קוד,
ו-501 בדיקות עברו על טופס שנופל ב-`AttributeError` בשימוש ראשון.
הבדיקות מריצות את הליבה ולא את זרימת ההגדרה, ולכן אף אחת מהן לא
נגעה בקוד הזה.

נבדק סטטית ולא בייבוא, כדי שהשער ירוץ בלי Home Assistant מותקן.
ירושה נפתרת כלפי מעלה בלבד: מתודה שמוגדרת רק במחלקה יורשת אינה
נחשבת, וזה בדיוק הכשל שנתפס כאן. מה שמחלקות של Home Assistant
מספקות רשום ב-INHERITED.
"""

from __future__ import annotations

import ast
import pathlib
import sys

# מה שמגיע מ-Home Assistant עצמו ואינו מוגדר אצלנו.
INHERITED = {
    # ConfigSubentryFlow
    "_get_entry", "_get_reconfigure_subentry", "_get_reconfigure_entry",
    "_abort_if_unique_id_configured", "_async_handle_step",
    # AssistSatelliteEntity
    "_resolve_announcement_media_id", "_cancel_running_pipeline",
}


def _classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}


def _defined_on(node: ast.ClassDef) -> set[str]:
    """שמות שהמחלקה מגדירה בעצמה — מתודות, ושדות שנקבעים ב-__init__."""
    found = set()
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.add(child.name)
        elif isinstance(child, ast.Assign):
            found |= {t.id for t in child.targets if isinstance(t, ast.Name)}
        elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            found.add(child.target.id)
    # שדות שנוצרים בגוף כל מתודה: self.x = ...
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and isinstance(sub.ctx, ast.Store):
            if isinstance(sub.value, ast.Name) and sub.value.id == "self":
                found.add(sub.attr)
    return found


def _available(name: str, classes: dict[str, ast.ClassDef]) -> tuple[set[str], bool]:
    """כל מה שזמין למחלקה, והאם שרשרת הירושה שלה שלמה בקובץ."""
    node = classes.get(name)
    if node is None:
        return set(), False
    found = _defined_on(node)
    complete = True
    for base in node.bases:
        if not isinstance(base, ast.Name):
            continue
        if base.id in classes:
            inherited, ok = _available(base.id, classes)
            found |= inherited
            complete = complete and ok
        else:
            complete = False
    return found, complete


def check(path: pathlib.Path, classes: dict[str, ast.ClassDef]) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    own = _classes(tree)
    problems: list[str] = []

    for name, node in own.items():
        available, _ = _available(name, classes)
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Attribute) or not isinstance(sub.ctx, ast.Load):
                continue
            if not (isinstance(sub.value, ast.Name) and sub.value.id == "self"):
                continue
            if not sub.attr.startswith("_") or sub.attr.startswith("__"):
                continue
            if sub.attr in available or sub.attr in INHERITED:
                continue
            problems.append(
                f"{path.name}:{sub.lineno} {name}.self.{sub.attr} אינו מוגדר"
            )
    return problems


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent / "custom_components"
    if not root.is_dir():
        root = pathlib.Path("custom_components")

    failures: list[str] = []
    files = sorted(root.rglob("*.py"))

    # מפת מחלקות של החבילה כולה. בסיס יכול לשבת בקובץ אחר —
    # `IvrItemEntity` ב-entity.py הוא הבסיס של החיישנים — ובלי
    # המפה הזו כל שדה שהוא מגדיר נראה חסר.
    classes: dict[str, ast.ClassDef] = {}
    for path in files:
        classes.update(_classes(ast.parse(path.read_text(encoding="utf-8"), str(path))))

    for path in files:
        failures += check(path, classes)

    for line in failures:
        print("FAIL", line)
    print(f"{'FAIL' if failures else 'PASS'} — נבדקו {len(files)} קבצים, "
          f"{len(failures)} מתודות חסרות")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
