"""שיחות יוצאות — מה שמשותף לספקים.

הפרוטוקול עצמו אינו כאן. כל מודול ספק מביא את הכתובות, השדות
והשגיאות שלו, ומייבא מכאן את מה שזהה בכולם: סוג החריגה ותקינון
רשימת המספרים.
"""

from __future__ import annotations


class OutboundError(Exception):
    """כשל בשיחה יוצאת, עם טקסט שמוצג למשתמש.

    נושאת מפתח תרגום ולא רק מחרוזת: `key` מצביע למקטע
    `exceptions` ב-`strings.json`, ו-`placeholders` ממלא אותו.

    טקסט שמגיע מהספק אינו מתורגם — הוא נכנס כ-placeholder למפתח
    עוטף שכן מתורגם.
    """

    def __init__(self, message: str, key: str = "",
                 placeholders: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.key = key
        self.placeholders = placeholders or {}


def clean_phones(raw: str) -> str:
    """רשימת מספרים מופרדת בפסיקים.

    רשימת תפוצה בפורמט tzl:N עוברת כמו שהיא — היא אינה מספר.
    """
    parts = []
    for part in str(raw or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        parts.append(part if part.startswith("tzl:") else digits(part))
    return ",".join(p for p in parts if p)


def digits(value: str) -> str:
    return "".join(c for c in str(value) if c.isdigit())
