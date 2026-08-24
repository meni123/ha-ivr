"""עץ התפריטים. חי בזיכרון של Home Assistant, לא אצל הספק.

צומת הוא או תפריט (יש לו items) או פעולה (יש לו entity).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import KEY_BACK, KEY_ROOT, Prompt, Say


def lamed(name: str) -> str:
    """צירוף אות ל לשם.

    ניסיתי לטפל כאן במיזוג ל+ה — "להעוזר" צריך להיות
    "לעוזר". אבל אי אפשר להבחין בין ה׳ הידיעה לבין ה׳
    שהיא שורש המילה בלי מורפולוגיה של ממש: "הדלקה"
    הפכה ל"דלקה". ניחוש שמקלקל מילים תקינות גרוע
    מניסוח מסורבל, ולכן הצירוף נשאר פשוט.

    הפתרון בצד המשתמש: שם מוקרא נכתב בלי ה׳ הידיעה —
    "עוזר קולי" ולא "העוזר הקולי". כך גם ברירות המחדל.
    """
    return f"ל{name.strip()}"


@dataclass(frozen=True)
class Node:
    """צומת בעץ."""

    say: str = ""
    """מה שמוקרא כשמציעים את הצומת בתפריט ההורה."""

    intro: str | None = None
    """משפט פתיחה שמושמע בכניסה לתפריט הזה."""

    items: dict[str, "Node"] = field(default_factory=dict)

    entity: str | None = None
    action: str | None = None
    data: dict = field(default_factory=dict)

    goto: str = ""
    """שלוחת יעד אצל הספק. ריק = אינו צומת מעבר."""

    alerts: bool = False
    """צומת שמקריא את ההתראות האחרונות במקום להריץ פעולה."""

    confirmed: bool = False
    """האם פעולה רגישה אושרה במפורש בטופס. נבדק שוב בזמן ריצה."""

    @property
    def is_menu(self) -> bool:
        return bool(self.items)

    @property
    def is_goto(self) -> bool:
        return bool(self.goto)


def build(config: dict) -> Node:
    """בניית עץ מקונפיגורציה."""
    items = {
        str(key): build(value) for key, value in (config.get("items") or {}).items()
    }
    return Node(
        say=str(config.get("say", "")),
        intro=config.get("intro"),
        items=items,
        entity=config.get("entity"),
        action=config.get("action"),
        data=dict(config.get("data") or {}),
        goto=str(config.get("goto", "") or ""),
        alerts=bool(config.get("alerts", False)),
        confirmed=bool(config.get("confirmed", False)),
    )


def resolve(root: Node, path: tuple[str, ...]) -> Node | None:
    """הליכה בעץ לפי נתיב. None אם הנתיב אינו קיים."""
    node = root
    for part in path:
        child = node.items.get(part)
        if child is None:
            return None
        node = child
    return node


def navigate(
    root: Node, path: tuple[str, ...], digit: str | None
) -> tuple[tuple[str, ...], Node] | None:
    """המיקום החדש אחרי הקשה.

    מחזיר None אם ההקשה אינה חוקית — הליבה תשאל שוב מאותו מקום.
    """
    if digit is None:
        node = resolve(root, path)
        return (path, node) if node else ((), root)

    if digit == KEY_ROOT:
        return (), root
    if digit == KEY_BACK:
        parent = path[:-1]
        node = resolve(root, parent)
        return (parent, node) if node else ((), root)

    new_path = (*path, digit)
    node = resolve(root, new_path)
    return (new_path, node) if node else None


def prompt_for(
    node: Node,
    path: tuple[str, ...],
    step: int,
    *,
    timeout: int = 10,
    supports_goto: bool = True,
) -> Prompt:
    """בניית שאלת תפריט עבור צומת.

    כל פריט הוא Say נפרד ולא משפט אחד ארוך. בימות זה מונע נקודות
    בתוך טקסט, ובטכנוליין זה מייעל את הקאש של ההקראה — כל מקטע
    קצר נשמר בנפרד ומוגש שוב בשיחה הבאה.
    """
    messages: list[Say] = []
    if node.intro:
        messages.append(Say("text", node.intro))

    allowed = set()
    for key, child in sorted(node.items.items()):
        # פריט מעבר מוסתר בקו שאינו תומך בו, במקום להציע
        # למתקשר אפשרות שתיכשל.
        if child.is_goto and not supports_goto:
            continue
        # תת-תפריט מוכרז אחרת מפריט, כדי שהמתקשר ידע שהוא נכנס
        # לרשימה נוספת ולא מפעיל משהו.
        if child.is_menu:
            messages.append(Say("text", f"לתפריט {child.say} הקש {key}"))
        else:
            messages.append(Say("text", f"{lamed(child.say)} הקש {key}"))
        allowed.add(key)

    if path:
        messages.append(Say("text", f"לחזרה הקש {KEY_BACK}"))
        allowed.add(KEY_BACK)
        if len(path) > 1:
            messages.append(Say("text", "לתפריט הראשי הקש כוכבית"))
            allowed.add(KEY_ROOT)

    return Prompt(
        messages=messages,
        allowed=frozenset(allowed),
        at_path=path,
        step=step,
        timeout=timeout,
    )
