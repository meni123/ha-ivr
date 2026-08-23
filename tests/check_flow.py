"""איתור שימוש במשתנה מקומי לפני שהוגדר.

נכתב אחרי ש-`action` נקרא בשורת יומן שיושבת מעל ההשמה שלו, וכל
קריאה ל-send_call נפלה ב-UnboundLocalError. הקומפילציה עוברת,
`check_names` עובר — כי השם *כן* מוגדר בפונקציה, רק מאוחר מדי.
זה נופל בזמן ריצה בלבד.

הבדיקה סורקת כל פונקציה, עוקבת אחרי סדר השורות, ומדווחת על שם
מקומי שנקרא לפני ההשמה הראשונה שלו.

מגבלה מוכרת: הניתוח לינארי לפי מספר שורה ואינו מבין לולאות —
שימוש בסוף לולאה בערך שהושם בתחילתה ידווח כתקין, וזה נכון; אך
משתנה שמושם רק בענף אחד של תנאי לא ידווח. זו בדיקה לדפוס אחד
ספציפי, לא מנתח זרימה מלא.

python3 tests/check_flow.py
"""

from __future__ import annotations

import ast
import builtins
import pathlib
import sys

SAFE = set(dir(builtins)) | {"self", "cls"}


class _Function(ast.NodeVisitor):
    """אוסף השמות וקריאות בתוך פונקציה אחת, לפי סדר השורות."""

    def __init__(self) -> None:
        self.assigned: dict[str, int] = {}
        self.used: list[tuple[str, int]] = []
        self.globals: set[str] = set()
        self.comprehension: set[str] = set()

    def visit_comprehension_targets(self, node) -> None:
        """שמות שנקשרים בתוך comprehension.

        ב-{k: v for k, v in items} ה-Name של k ו-v מופיעים בשורה
        שלפני ה-Store שלהם, וההשוואה הלינארית מסמנת אותם בטעות.
        הם חיים בהיקף משלהם ולעולם אינם הבאג שאנחנו מחפשים.
        """
        for gen in getattr(node, "generators", []):
            for sub in ast.walk(gen.target):
                if isinstance(sub, ast.Name):
                    self.comprehension.add(sub.id)
        self.generic_visit(node)

    visit_ListComp = visit_SetComp = visit_DictComp = visit_comprehension_targets
    visit_GeneratorExp = visit_comprehension_targets

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.assigned.setdefault(node.id, node.lineno)
        else:
            self.used.append((node.id, node.lineno))

    def visit_arg(self, node: ast.arg) -> None:
        self.assigned.setdefault(node.arg, node.lineno)

    def visit_Global(self, node: ast.Global) -> None:
        self.globals |= set(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.globals |= set(node.names)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.assigned.setdefault((alias.asname or alias.name).split(".")[0], node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.assigned.setdefault(alias.asname or alias.name, node.lineno)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.assigned.setdefault(node.name, node.lineno)
        self.generic_visit(node)

    def _nested(self, node) -> None:
        # פונקציה מקוננת היא שם שהוגדר; גופה נבדק בנפרד.
        self.assigned.setdefault(node.name, node.lineno)

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _nested


def _module_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {
                (a.asname or a.name).split(".")[0] for a in node.names
            }
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    names.add(sub.id)
        elif isinstance(node, ast.If):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(sub.name)
                elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                    names |= {(a.asname or a.name).split(".")[0] for a in sub.names}
                elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                    names.add(sub.id)
    return names


def check(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    outer = _module_names(tree) | SAFE
    problems = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        walker = _Function()
        # הארגומנטים נרשמים ראשונים. בגרסה הראשונה הם נרשמו
        # אחרי הגוף, ו-setdefault כבר קיבע שם של פרמטר שהושם
        # מחדש בגוף — כל השמה כזו דווחה כשגיאה.
        for arg in ast.walk(node.args):
            walker.visit(arg)
        for child in node.body:
            walker.visit(child)

        for name, line in walker.used:
            if name in outer or name in walker.globals:
                continue
            if name in walker.comprehension:
                continue
            first = walker.assigned.get(name)
            if first is not None and line < first:
                problems.append(
                    f"{path.name}:{line} {name} נקרא לפני ההשמה שלו בשורה {first} "
                    f"(בתוך {node.name})"
                )
    return problems


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent / "custom_components"
    if not root.is_dir():
        root = pathlib.Path("custom_components")

    failures = []
    files = sorted(root.rglob("*.py"))
    for path in files:
        failures += check(path)

    for line in sorted(set(failures)):
        print("FAIL", line)
    print(f"{'FAIL' if failures else 'PASS'} — נבדקו {len(files)} קבצים, "
          f"{len(set(failures))} שימושים לפני השמה")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
