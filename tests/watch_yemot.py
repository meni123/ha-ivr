"""צפייה חיה בבקשות של ימות, עם הפרש הזמן בין הקשה להקשה.

הפרש הזמן הוא מה שמבדיל בין "המקש נקלט" לבין "פג הזמן": בקשה
שמגיעה שנייה אחרי ההקשה היא הקשה, בקשה שמגיעה אחרי כעשר שניות
היא פקיעת ההמתנה של שדה 5.

    python3 tests/watch_yemot.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime

import os

LOG = os.environ.get(
    "HA_LOG",
    os.path.join(os.environ.get("HA_CONFIG", "/config"), "home-assistant.log"),
)
LINE = re.compile(
    r"^(?P<ts>[\d-]+ [\d:.]+).*?(?P<drv>\w+) ← \[(?P<method>\w+)\] "
    r"נתיב=(?P<path>\S+) הקשה=(?P<digit>\S+) צעד=(?P<step>\d+)"
)


def main() -> None:
    want = sys.argv[1] if len(sys.argv) > 1 else "yemot"
    print(f"מאזין ל-{LOG} עבור {want}. Ctrl-C ליציאה.\n")
    print(f"{'שעה':<13}{'פער':>7}  {'נתיב':<12}{'הקשה':<8}{'צעד':<5}")
    print("-" * 50)

    proc = subprocess.Popen(
        ["tail", "-n", "0", "-F", LOG],
        stdout=subprocess.PIPE, text=True, bufsize=1,
    )
    prev: datetime | None = None
    assert proc.stdout is not None
    for raw in proc.stdout:
        match = LINE.match(raw)
        if not match or want not in match["drv"]:
            continue
        now = datetime.strptime(match["ts"], "%Y-%m-%d %H:%M:%S.%f")
        gap = f"{(now - prev).total_seconds():5.1f}ש" if prev else "   — "
        prev = now
        # פער של כעשר שניות הוא פקיעת המתנה, לא הקשה.
        flag = "  ← פקיעת המתנה?" if prev and gap.strip().startswith(("9", "10", "11")) else ""
        print(
            f"{now:%H:%M:%S.%f}"[:12].ljust(13)
            + f"{gap:>7}  {match['path']:<12}{match['digit']:<8}{match['step']:<5}{flag}"
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nיצאתי.")
