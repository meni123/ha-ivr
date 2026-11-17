"""שלושת קבצי התרגום תואמים, וכל מפתח שהקוד מבקש קיים בהם.

- אותם מפתחות ב-`strings.json`, ב-`translations/en.json` וב-`he.json`.
- אותם משתנים (`{name}`) בכל ערך, בכל השפות. משתנה חסר בעברית
  נופל רק כשההודעה מפורמטת — בזמן ריצה, אצל המשתמש.
- כל `step_id` שהקוד מציג, וכל סיבת `abort` שהוא מחזיר, מתורגמים.

python3 tests/check_strings.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "custom_components" / "ha_ivr"

FAIL = 0


def fail(message: str) -> None:
    global FAIL
    FAIL += 1
    print(f"FAIL {message}")


def flatten(node, prefix="") -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            out.update(flatten(value, f"{prefix}{key}."))
    else:
        out[prefix[:-1]] = str(node)
    return out


PLACEHOLDER = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")

files = {
    name: flatten(json.loads((BASE / name).read_text("utf-8")))
    for name in ("strings.json", "translations/en.json", "translations/he.json")
}
base = files["strings.json"]
for name, flat in files.items():
    if name == "strings.json":
        continue
    for key in sorted(set(base) - set(flat)):
        fail(f"{name}: חסר {key}")
    for key in sorted(set(flat) - set(base)):
        fail(f"{name}: מיותר {key}")
    for key in sorted(set(base) & set(flat)):
        want = set(PLACEHOLDER.findall(base[key]))
        got = set(PLACEHOLDER.findall(flat[key]))
        if want != got:
            fail(f"{name}: {key} — משתנים {sorted(got)} במקום {sorted(want)}")

# כל step_id וכל abort שבקוד מתורגם.
code = "\n".join(p.read_text("utf-8") for p in BASE.rglob("*.py"))
steps = set(re.findall(r'step_id\s*=\s*"([a-z_]+)"', code))
aborts = set(re.findall(r'async_abort\(\s*reason\s*=\s*"([a-z_]+)"', code))
aborts |= set(re.findall(r'reason\s*=\s*"([a-z_]+)"', code)) & {
    "reauth_successful", "reconfigure_successful", "unique_id_mismatch",
    "already_configured",
}
keys = set(base)
for step in sorted(steps):
    if not any(f".step.{step}." in k for k in keys):
        fail(f"step_id בלי תרגום: {step}")
for reason in sorted(aborts):
    if not any(k.endswith(f".abort.{reason}") for k in keys):
        fail(f"abort בלי תרגום: {reason}")

print(f"{'PASS' if not FAIL else 'FAIL'} — {len(base)} מפתחות, "
      f"{len(steps)} מסכים, {len(aborts)} סיבות סיום, {FAIL} בעיות")
sys.exit(1 if FAIL else 0)
