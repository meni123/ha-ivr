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

    target: dict = field(default_factory=dict)
    """יעד קבוצתי במקום ישות בודדת: `domain`, `area`, `floor`.

    נפתר לרשימת ישויות בזמן השיחה ולא בהגדרה, ולכן מכשיר שנוסף
    למרחב נכנס לתפריט מעצמו. ראו `smart.match_entities`.
    """

    goto: str = ""
    """שלוחת יעד אצל הספק. ריק = אינו צומת מעבר."""

    alerts: bool = False
    """צומת שמקריא את ההתראות האחרונות במקום להריץ פעולה."""

    collect: dict = field(default_factory=dict)
    """צומת שאוסף מספר במקום להציע אפשרויות.

    מכיל `action`, `field`, `min`, `max` ו-`width` — כמה ספרות
    בדיוק מקישים. הספרות שנאספו עד כה אינן כאן: הן נוסעות עם
    השיחה, כהמשך של הנתיב. ראו `smart.py` ואת הטיפול ב-`view`.
    """

    confirmed: bool = False
    """האם פעולה רגישה אושרה במפורש בטופס. נבדק שוב בזמן ריצה."""

    @property
    def is_menu(self) -> bool:
        return bool(self.items)

    @property
    def is_goto(self) -> bool:
        return bool(self.goto)

    @property
    def is_collect(self) -> bool:
        return bool(self.collect)

    @property
    def is_group(self) -> bool:
        return bool(self.target)


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
        target=dict(config.get("target") or {}),
        goto=str(config.get("goto", "") or ""),
        alerts=bool(config.get("alerts", False)),
        collect=dict(config.get("collect") or {}),
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


# ----------------------------------------------------------------------
# איסוף מספר
# ----------------------------------------------------------------------


def find_collector(
    root: Node, path: tuple[str, ...]
) -> tuple[Node, tuple[str, ...], tuple[str, ...]] | None:
    """צומת האיסוף שהמתקשר נמצא בתוכו, והספרות שכבר הקיש.

    הספרות שנאספו הן פשוט המשך הנתיב. אחרי הקשה ראשונה על צומת
    האיסוף שב-1/5, הנתיב שנשלח הוא 1/5/2 — וזה כל הזיכרון שיש.
    לכן מחפשים כאן אחורה: הצומת האחרון בדרך שהוא צומת איסוף,
    וכל מה שמימינו הוא מה שהמתקשר כבר הקיש.

    None אם אין צומת איסוף בנתיב, וזו הדרך הרגילה בכל שאר התפריט.
    """
    for cut in range(len(path), -1, -1):
        node = resolve(root, path[:cut])
        if node is not None and node.is_collect:
            return node, path[:cut], path[cut:]
    return None


def valid_next_digits(collect: dict, collected: tuple[str, ...]) -> set[str]:
    """הספרות שיכולות להמשיך את מה שהוקש ולהישאר בטווח.

    בטווח 16 עד 30 הספרה הראשונה יכולה להיות רק 1, 2 או 3. חסימה
    כאן עדיפה על קבלת 45 ואז הודעת שגיאה: המתקשר אינו רואה מסך,
    והקשה שאינה מתקבלת נענית מיד ב"בחירה שאינה קיימת".
    """
    width = int(collect.get("width") or 0)
    if width <= 0 or len(collected) >= width:
        return set()

    low = int(float(collect.get("min", 0)))
    high = int(float(collect.get("max", 0)))
    prefix = "".join(collected)
    allowed = set()
    for digit in "0123456789":
        candidate = prefix + digit
        # כל ערך שעדיין אפשר להשלים ממנו נחשב תקין. משלימים
        # באפסים לגבול התחתון ובתשיעיות לגבול העליון.
        lowest = int(candidate.ljust(width, "0"))
        highest = int(candidate.ljust(width, "9"))
        if highest >= low and lowest <= high:
            allowed.add(digit)
    return allowed


def collect_prompt(
    node: Node,
    path: tuple[str, ...],
    step: int,
    collected: tuple[str, ...],
    *,
    timeout: int = 10,
) -> Prompt:
    """השאלה שמבקשת את הספרה הבאה בצומת איסוף.

    הכוכבית מבטלת וחוזרת לתפריט. האפס הוא ספרה כאן ולא "חזרה" —
    בלעדיו אי אפשר להקיש 20 מעלות. זו החלטה מקומית לצומת הזה
    בלבד, כי רשימת המקשים נבנית לכל שאלה בנפרד.
    """
    allowed = valid_next_digits(node.collect, collected)
    width = int(node.collect.get("width") or 0)

    # בין הספרות אין הקראה כלל. מי שהקיש 2 וממתין לשנייה אינו
    # צריך לשמוע דבר — כל משפט כאן הוא השהיה לפני שהספרה הבאה
    # מתקבלת, וזו בדיוק ההרגשה של "המערכת איטית". הספק ממתין
    # לספרה גם בלי טקסט להשמיע.
    messages: list[Say] = []
    if not collected:
        low = int(float(node.collect.get("min", 0)))
        high = int(float(node.collect.get("max", 0)))
        messages.append(
            Say("text", f"{node.say}, בין {low} ל{high}")
        )
        messages.append(Say("text", f"הקש {width} ספרות"))
        # כל הערכים באותו אורך, ולכן ערך קצר מרופד באפס. בלי
        # המשפט הזה מי שרוצה 8 מעלות בטווח שמגיע ל-30 אינו יודע
        # שעליו להקיש 08, ומקיש 8 ואז ממתין לשווא.
        #
        # בלי פסיק לפני "הקש": ספק שמוסיף פיסוק בעצמו היה יוצר
        # פסיק כפול, ומנוע ההקראה עוצר עליו פעמיים.
        if len(str(low)) < width:
            messages.append(Say("text", "למספר קטן הקש אפס לפניו"))
        messages.append(Say("text", "לביטול הקש כוכבית"))

    return Prompt(
        messages=messages,
        allowed=frozenset(allowed | {KEY_ROOT}),
        at_path=(*path, *collected),
        step=step,
        timeout=timeout,
    )
