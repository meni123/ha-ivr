"""בקרת גישה לפי כתובת — מקום אחד לשתי נקודות הקצה.

התפריט וערוץ הסטרימינג מקבלים בקשות מאותם שרתים ובודקים את אותו
דבר. זו בקרת אבטחה, ושני עותקים שלה פירושם שתיקון באחד אינו
מגיע לשני.
"""

from __future__ import annotations

import ipaddress
import logging

_LOGGER = logging.getLogger(__name__)

# טווחים שגויים שכבר דווחו. בלי הזיכרון הזה, טווח שגוי בהגדרות
# מייצר שורת שגיאה בכל בקשה — כלומר מציף את היומן בדיוק כשצריך
# לקרוא אותו.
_BAD_NETWORKS: set[str] = set()


def forget_bad_networks() -> None:
    """איפוס הזיכרון, כדי ששינוי הגדרות ידווח מחדש."""
    _BAD_NETWORKS.clear()


def ip_allowed(remote: str | None, networks) -> bool:
    """האם הכתובת נמצאת באחד הטווחים.

    רשימה ריקה נבדקת אצל הקורא ולא כאן: המשמעות של "בלי טווחים"
    היא החלטת מדיניות של נקודת הקצה, לא של הבדיקה.

    טווח שגוי בהגדרות מדולג ואינו מפיל את הבקשה — הגדרה שבורה
    של טווח אחד אינה סיבה לסגור את הקו כולו.
    """
    if not remote:
        return False
    try:
        addr = ipaddress.ip_address(remote)
    except ValueError:
        return False

    for raw in networks:
        try:
            network = ipaddress.ip_network(raw, strict=False)
        except ValueError:
            if raw not in _BAD_NETWORKS:
                _BAD_NETWORKS.add(str(raw))
                _LOGGER.error("Invalid IP range in the options, skipping it: %r", raw)
            continue
        if addr in network:
            return True
    return False
