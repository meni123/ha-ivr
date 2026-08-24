"""הספקים.

מודול אחד לספק. הליבה אינה מכירה אף אחד מהם בשם אלא שואלת את
המרשם, ולכן ספק רביעי הוא קובץ נוסף כאן ושורה ב-`PROVIDERS`.
"""

from __future__ import annotations

from . import pbx, technoline, vonage, yemot

PROVIDERS = (yemot, technoline, vonage, pbx)


def ensure_registered() -> None:
    """רישום כל הספקים במרשם, פעם אחת.

    אינו יכול לחיות ב-`async_setup` בלבד: HA קוראת לה רק כשנטענת
    רשומה, ובטופס הראשון עוד אין אחת — הבורר היה נבנה ממרשם ריק
    ומוצג ריק בלי שגיאה.

    `register` דורסת לפי מזהה, ולכן קריאה חוזרת אינה עולה דבר.
    """
    from .. import registry  # noqa: PLC0415

    for provider in PROVIDERS:
        registry.register(provider)
