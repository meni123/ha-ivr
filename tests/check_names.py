"""איתור שמות שאינם מוגדרים, בכל קבצי האינטגרציה.

נכתב אחרי ש-DEFAULT_EXIT_PHRASES נעשה בו שימוש בלי שיובא, וכל
חיבור WebSocket קרס. 172 הבדיקות שהיו קיימות לא תפסו את זה, כי
כולן בדקו מחרוזות בתוך הקוד ואף אחת לא ייבאה מודול בפועל.

בדיקת מחרוזות מוודאת שכתבתי משהו. הבדיקה הזו מוודאת שהוא ירוץ.

python3 tests/check_names.py
"""

from __future__ import annotations

import ast
import builtins
import pathlib
import sys

BUILTINS = set(dir(builtins)) | {
    "__name__", "__file__", "__doc__", "__package__", "__spec__",
}


def _bound_names(node: ast.AST) -> set[str]:
    """כל שם שנקשר בתוך הצומת — השמות, ייבואים, ארגומנטים, לולאות."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split(".")[0] for a in child.names}
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(child.name)
        elif isinstance(child, (ast.Name, ast.arg)):
            if isinstance(child, ast.arg):
                names.add(child.arg)
            elif isinstance(child.ctx, (ast.Store, ast.Del)):
                names.add(child.id)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            names.add(child.name)
        elif isinstance(child, ast.Global):
            names |= set(child.names)
    return names


def check(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    known = _bound_names(tree) | BUILTINS

    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
            continue
        if node.id not in known:
            problems.append(f"{path.name}:{node.lineno} שם לא מוגדר: {node.id}")
    return problems


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent / "custom_components"
    if not root.is_dir():
        root = pathlib.Path("custom_components")

    failures = []
    files = sorted(root.rglob("*.py"))
    for path in files:
        failures += check(path)

    for line in failures:
        print("FAIL", line)
    print(f"{'FAIL' if failures else 'PASS'} — נבדקו {len(files)} קבצים, "
          f"{len(failures)} שמות לא מוגדרים")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
