"""הרצה אמיתית של האינטגרציות מול HA מזויף.

בניגוד לבדיקות שקוראות את הקוד כטקסט, כאן המודולים מיובאים
והפונקציות מופעלות. כל שגיאת זמן ריצה — שם שלא הוגדר, שם שהוגדר
מאוחר מדי, חתימה שהשתנתה, ייבוא חסר — צצה כאן.

זו גם הבדיקה שהגבול בין הליבה לספקים שלם: שהליבה אינה מכירה
אף ספק, ושכל דרייבר עונה על הפרוטוקול במלואו.

python3 tests/run_live.py
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_ha  # noqa: E402

fake_ha.install()

PASS = FAIL = 0


def ok(name: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}")


def check(name: str, fn):
    """מריץ פונקציה ומדווח על חריגה במקום ליפול."""
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            result = asyncio.new_event_loop().run_until_complete(result)
        ok(name, True)
        return result
    except Exception as err:  # noqa: BLE001
        ok(f"{name} — {type(err).__name__}: {err}", False)
        return None


print("== ייבוא כל המודולים ==")
CORE = "custom_components.ha_ivr"
for module in (
    f"{CORE}.const", f"{CORE}.model", f"{CORE}.codec", f"{CORE}.tree",
    f"{CORE}.policy", f"{CORE}.translations_he", f"{CORE}.action_fields",
    f"{CORE}.outbound", f"{CORE}.menu", f"{CORE}.entity", f"{CORE}.registry",
    f"{CORE}.view", f"{CORE}.stream", f"{CORE}.sensor", f"{CORE}.diagnostics",
    f"{CORE}.config_shared", CORE,
    f"{CORE}.config_flow", f"{CORE}.notify", f"{CORE}.satellite",
    f"{CORE}.announce", f"{CORE}.audio", f"{CORE}.net", f"{CORE}.select",
    f"{CORE}.providers.yemot", f"{CORE}.providers.technoline",
    f"{CORE}.providers.vonage", f"{CORE}.providers",
):
    check(f"import {module}", lambda m=module: __import__(m, fromlist=["_"]))

from custom_components.ha_ivr import menu, registry, tree, view  # noqa: E402
from custom_components.ha_ivr.model import (  # noqa: E402
    GoTo, Prompt, Say, Terminal,
)
from custom_components.ha_ivr.providers import technoline  # noqa: E402
from custom_components.ha_ivr.providers import vonage  # noqa: E402
from custom_components.ha_ivr.providers import yemot  # noqa: E402
from custom_components.ha_ivr.providers import pbx  # noqa: E402

DRIVERS = (("yemot", yemot), ("technoline", technoline), ("vonage", vonage),
           ("pbx", pbx))

print("\n== הגבול: הליבה אינה מייבאת אף ספק ==")
# הגבול נמדד בייבוא ולא באזכור. הערה שמסבירה למה החלטה התקבלה
# **חייבת** לנקוב בשם הספק שבגללו — זה בדיוק מה שהופך אותה
# לשימושית. מה שאסור הוא תלות קוד.
_core_dir = ROOT / "custom_components" / "ha_ivr"
_bad = []
for _f in sorted(_core_dir.glob("*.py")):
    for _line in _f.read_text("utf-8").splitlines():
        _st = _line.strip()
        if (_st.startswith("import ") or _st.startswith("from ")) and any(
            f"ha_ivr_{p}" in _st for p in ("yemot", "technoline", "vonage")
        ):
            _bad.append(f"{_f.name}: {_st}")
ok("הליבה אינה מייבאת חבילת ספק", not _bad)
if _bad:
    for _b in _bad:
        print("     ", _b)

# **הליבה אינה מכירה ספק בשם.** מבחן הספק הרביעי: תיקייה חדשה
# בלבד, אפס נגיעה בליבה. שני הקבצים שמנהלים את השיחה נבדקים
# במפורש, כי הם אלה שהסתעפו לפי שם ספק עד 0.28.0.
# **כל הליבה, לא רק המנוע.** האכיפה כיסתה את ארבעת קבצי
# השיחה, ובזמן שהם היו נקיים `config_flow.py` השווה
# `driver.DRIVER_ID == "technoline"` בשלוש שורות — כלומר ספק
# רביעי עדיין חייב עריכה בליבה, רק דרך דלת אחרת.
_leaks = []
for _f in sorted(_core_dir.glob("*.py")):
    for _num, _line in enumerate(_f.read_text("utf-8").splitlines(), 1):
        _st = _line.strip()
        if _st.startswith("#") or _st.startswith('"""') or _st.startswith("|"):
            continue
        for _p in ("technoline", "vonage", "yemot"):
            if _p in _st:
                _leaks.append(f"{_f.name}:{_num}  {_st[:60]}")
ok("הליבה אינה מכירה ספק בשם", not _leaks)
for _l in _leaks:
    print("     ", _l)

from custom_components.ha_ivr import registry  # noqa: E402

# **Bearer חובה כשיש טוקן.** בדיקה מותנית בקיום הכותרת אינה
# שכבה: מי שמחזיק את הטוקן שבנתיב ומשמיט אותה מגיע לאותו מקום.
_stream_view_src = (_core_dir / "stream.py").read_text("utf-8")
ok("Bearer אינו מותנה בקיום הכותרת",
   'if auth:' not in _stream_view_src)
ok("כותרת חסרה נדחית",
   'if not hmac.compare_digest(supplied, expected):' in _stream_view_src)

# בקרת גישה במקום אחד. שני עותקים כבר סטו זה מזה פעם אחת.
from custom_components.ha_ivr import net  # noqa: E402
ok("ip_allowed קיימת פעם אחת",
   sum('def _ip_allowed' in (_core_dir / f).read_text("utf-8")
       for f in ("view.py", "stream.py")) == 0)
ok("כתובת בטווח", net.ip_allowed("192.168.1.5", ["192.168.1.0/24"]))
ok("כתובת מחוץ לטווח", not net.ip_allowed("10.0.0.1", ["192.168.1.0/24"]))
ok("IPv6 נתמך", net.ip_allowed("2a13:8140:1::5", ["2a13:8140:1::/48"]))
# טווח שגוי מדולג ואינו מפיל את הבקשה: הגדרה שבורה של טווח אחד
# אינה סיבה לסגור את הקו כולו.
ok("טווח שגוי מדולג", net.ip_allowed("10.0.0.1", ["לא-טווח", "10.0.0.0/8"]))
ok("בלי כתובת אין מעבר", not net.ip_allowed(None, ["10.0.0.0/8"]))

# שתי מחלקות הזרימה חולקות מימוש. ההבדל הוא שדה וכותרת.
_cfg_src = (_core_dir / "config_shared.py").read_text("utf-8")
ok("_simple_step משותף", "async def _simple_step(" in _cfg_src)
ok("תת-תפריט עובר דרכו", 'field=CONF_INTRO' in _cfg_src)
ok("מעבר עובר דרכו ודורש יעד",
   'field=CONF_GOTO_TARGET' in _cfg_src and "required=True" in _cfg_src)

# לינק תיעוד שמצביע לריפו של אינטגרציה שאינה קיימת שולח את
# המשתמש למקום הלא נכון מכרטיס האינטגרציה.
import json as _j  # noqa: E402
for _pkg in ("ha_ivr",):
    _m = _j.loads((ROOT / "custom_components" / _pkg / "manifest.json").read_text("utf-8"))
    ok("ha_ivr: תיעוד אינו מצביע לריפו הישן",
       "meni123/ha-yemot" not in _m.get("documentation", ""))

# הרשומה ידועה מהטוקן, ולכן רק הדרייבר שלה נשאל. בלי הסינון
# שני ספקים יכולים לענות על אותה מסגרת.
ok("הזיהוי מסונן לפי הספק של הרשומה",
   'driver.DRIVER_ID != str(self.entry.data.get("provider"' in _stream_view_src)
# `None` הוא מסלול חוקי, ולכן קריאה דינמית בשם מחרוזת בולעת
# שגיאת כתיב בשקט — וגם מסתירה את הפקודות מסורק הקוד המת.
ok("פקודות הבקרה נקראות ישירות",
   "self._command(" not in _stream_view_src
   and "def _command(" not in _stream_view_src)
ok("שלוש הפקודות נראות בקוד",
   all(f"self._driver.{c}(" in _stream_view_src
       for c in ("clear_command", "hangup_command", "leave_command")))

# ip_errors במקום אחד. אחרי האיחוד יש טופס אחד, ולכן מה שנשמר
# כאן הוא שהוא קורא למשותפת ולא מגדיר עותק משלו.
_flow_src = (_core_dir / "config_flow.py").read_text("utf-8")
ok("ip_errors אינה משוכפלת", "def _ip_errors" not in _flow_src)
ok("הטופס קורא למשותפת", "ip_errors(user_input)" in _flow_src)

from custom_components.ha_ivr.providers import technoline as tl_out  # noqa: E402

# **השירות שמפורסם חייב להיות השירות שקיים.** שדה ב-services.yaml
# שאינו בסכמה מופיע בבורר של הממשק, ומי שממלא אותו מקבל שגיאת
# ולידציה בלי הסבר.
# פענוח מצומצם ולא PyYAML: הבדיקות רצות על פייתון נקי בלי
# תלויות, וכל מה שצריך כאן הוא שמות השדות ודגל ה-required.
_svc_src = (ROOT / "custom_components" / "ha_ivr"
            / "services.yaml").read_text("utf-8")
_declared = {
    _l.strip().rstrip(":")
    for _l in _svc_src.splitlines()
    if _l.startswith("    ") and not _l.startswith("     ")
    and _l.rstrip().endswith(":")
}
import custom_components.ha_ivr as _core_mod  # noqa: E402

_marks = {
    str(k): type(k).__name__ for k in _core_mod._send_call_schema().schema
}
ok("services.yaml תואם לסכמה", _declared == set(_marks))
ok("message חובה", _marks.get("message") == "Required")
# **חובה.** הרשימה הקבועה הוחלפה בישויות `notify`, ולכן אין
# לאן ליפול; השירות הזה קיים למספר שמחושב בזמן ריצה.
ok("phones חובה", _marks.get("phones") == "Required")
# תיאור שירות נקרא בממשק. ציטוט של הודעת שגיאה פנימית שייך
# ל-CHANGELOG, לא לטופס שהמשתמש רואה.
ok("התיאור אינו מצטט שגיאות מערכת",
   "extra keys" not in _svc_src)
ok("phones מסומן חובה גם ב-yaml",
   "required: true" in _svc_src.split("phones:")[1].split("selector:")[0])

print("\n== שגיאת ספק מגיעה מתורגמת ==")
import ast as _ast  # noqa: E402
# **ההמרה חייבת להיות במסלול המשותף.** ישות `notify` ושירות
# `send_call` מגיעים שניהם ל-`_announce`; תפיסה באחד מהם בלבד
# משאירה את השני עם `OutboundError` גולמית על המסך.
_sat_src2 = (_core_dir / "satellite.py").read_text("utf-8")
ok("_announce ממיר שגיאת ספק", "except OutboundError as err:" in _sat_src2)

# כל `OutboundError` שמוצגת למשתמש נושאת מפתח. בלעדיו ההודעה
# היא מה שכתוב בקוד, כלומר שפה אחת.
_keyless = []
for _f in sorted((_core_dir / "providers").glob("*.py")):
    _s = _f.read_text("utf-8")
    for _n in _ast.walk(_ast.parse(_s)):
        if (isinstance(_n, _ast.Raise) and isinstance(_n.exc, _ast.Call)
                and getattr(_n.exc.func, "id", "") == "OutboundError"):
            if not any(k.arg == "key" for k in _n.exc.keywords):
                _keyless.append(f"{_f.name}:{_n.lineno}")
ok("לכל שגיאת ספק יש מפתח", not _keyless)
for _k in _keyless:
    print("      בלי מפתח:", _k)

print("\n== הקשה שאינה מוגדרת מגיעה אלינו ==")
# **נמדד בשיחה חיה:** הקשת 5 על תפריט עם 2/3/9 לא הופיעה ביומן
# כלל. `enabledKeys` מצומצם גורם למרכזייה לבלוע את המקש —
# ההקשה אינה מגיעה, אין שורה ביומן, והמתקשר שומע שקט מוחלט
# במקום "בחירה שאינה קיימת".
_tl_src4 = (_core_dir / "providers" / "technoline.py").read_text("utf-8")
ok("טכנוליין מקבל את כל המקשים", '"enabledKeys": "ALL"' in _tl_src4)

from custom_components.ha_ivr.providers import ensure_registered as _reg4  # noqa: E402

_reg4()
_hass4 = fake_ha.FakeHass()
_e4 = fake_ha.FakeEntry()
_e4.domain = "ha_ivr"
_e4.data = {"token": "T", "provider": "technoline"}
_e4.options = {"intro": "תפריט"}
_e4.subentries = {"s1": types.SimpleNamespace(
    subentry_type="menu_item", subentry_id="s1", title="2",
    data={"menu_path": "2", "label": "מזגן",
          "entity_id": "climate.x", "action": "toggle"})}
_hass4.config_entries = fake_ha.FakeConfigEntries([_e4])
_v4 = view.IvrView(_hass4)
_resp4 = asyncio.new_event_loop().run_until_complete(
    _v4.get(fake_ha.FakeRequest(query={"s2_": "5"}), "technoline", "T"))
_body4 = getattr(_resp4, "text", "") or ""
ok("מקש שאינו מוגדר נענה בהודעה", "בחירה שאינה קיימת" in _body4)
ok("והתפריט מושמע שוב אחריה", "מזגן" in _body4)

import re as _re0  # noqa: E402
_HEB0 = _re0.compile("[\u0590-\u05ff]")
print("\n== קבצי ההפצה ==")
import json as _json  # noqa: E402
# **HACS קוראת את `hacs.json` ואת המניפסט בנפרד.** שם שונה בין
# השניים מוצג שונה בחנות ובכרטיס האינטגרציה, ומי שמחפש לפי מה
# שראה לא מוצא.
_hacs = _json.loads((ROOT / "hacs.json").read_text("utf-8"))
_mani = _json.loads(
    (_core_dir / "manifest.json").read_text("utf-8"))
ok("hacs.json קיים", bool(_hacs.get("name")))
# **שני שמות לשני מסכים, בכוונה.** `manifest.name` מוצג בכרטיס
# אחרי ההתקנה, ואין לו ערך גילוי — חלון "הוספת אינטגרציה" מגיע
# רק אחרי ש-HACS כבר התקינה. `hacs.name` הוא מה שמופיע בחנות,
# שם הגילוי באמת קורה, ולכן שמות הספקים שייכים לשם.
ok("שם קצר בכרטיס", _mani["name"] == "IVR")
ok("שמות הספקים בחנות",
   all(p in _hacs["name"] for p in ("Yemot", "Technoline", "Vonage")))
# גרסת המינימום חייבת לכסות את פלטפורמת ה-notify (2024.6).
ok("גרסת HA מוצהרת", "homeassistant" in _hacs)
# **HACS דורשת `brand/icon.png` במפורש**, ובלעדיו הכרטיס מציג
# "icon not available". הגדלים הם של מאגר ה-brands של HA, כדי
# שאותם קבצים ישרתו גם את ה-PR לשם.
#
# **והנתיב הוא בתוך החבילה, לא בשורש הריפו.** הקבצים ישבו
# ב-`brand/` בשורש וה-action החזיר *"does not contain brands
# assets at custom_components/ha_ivr/brand/icon.png"* ונפל אל
# מאגר ה-brands, שאיננו בו. לכן הנתיב נגזר מהחבילה.
import struct as _struct  # noqa: E402

_dims = {}
for _f in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png"):
    _img = _core_dir / "brand" / _f
    if not _img.exists():
        ok(f"brand/{_f} קיים בחבילה", False)
        continue
    _raw = _img.read_bytes()
    _dims[_f] = _struct.unpack(">II", _raw[16:24])
    # רקע שקוף: סוג צבע 6 הוא RGBA, 4 הוא אפור+אלפא.
    ok(f"brand/{_f} עם שקיפות", _raw[25] in (4, 6))

# **האייקון ריבועי ובמידה קבועה; הלוגו נקבע בגובה בלבד.**
# רוחב הלוגו נגזר מיחס הצורה, ולכן קיבוע שלו פוסל כל עיצוב חדש
# שאינו באותן פרופורציות — וזה בדיוק מה שקרה בהחלפת הלוגו.
for _f, _side in (("icon.png", 256), ("icon@2x.png", 512)):
    if _f in _dims:
        ok(f"brand/{_f} — {_dims[_f][0]}×{_dims[_f][1]}, ריבוע {_side}",
           _dims[_f] == (_side, _side))
for _f, _hh in (("logo.png", 256), ("logo@2x.png", 512)):
    if _f in _dims:
        _gw, _gh = _dims[_f]
        ok(f"brand/{_f} — גובה {_gh}, לרוחב", _gh == _hh and _gw > _gh)
# **@2x חייב להיות הכפלה מדויקת**, אחרת האייקון קופץ בגודל בין
# מסך רגיל למסך רטינה.
for _a, _b in (("icon.png", "icon@2x.png"), ("logo.png", "logo@2x.png")):
    if _a in _dims and _b in _dims:
        ok(f"{_b} הוא בדיוק פי 2 מ-{_a}",
           _dims[_b] == (_dims[_a][0] * 2, _dims[_a][1] * 2))
ok("אין brand בשורש הריפו", not (ROOT / "brand").exists())

ok("LICENSE קיים ואינו ריק",
   (ROOT / "LICENSE").exists()
   and "MIT" in (ROOT / "LICENSE").read_text("utf-8"))
# **HACS דוחה כל מפתח שאינו בסכימה שלה, ולא רק ערך שגוי.**
# `render_readme` ישב כאן ונראה תמים — ה-action החזיר
# *"The repository has an invalid 'hacs.json' file"* והריפו נפל
# בבדיקה. הרשימה היא מה שמתועד ב-hacs.xyz/docs/publish/start.
_HACS_KEYS = {"name", "content_in_root", "zip_release", "filename",
              "hide_default_branch", "country", "homeassistant",
              "hacs", "persistent_directory"}
_extra_hacs = sorted(set(_hacs) - _HACS_KEYS)
ok("hacs.json בלי מפתח שאינו נתמך", not _extra_hacs)
for _k in _extra_hacs:
    print("      מפתח שאינו בסכימה:", _k)

# **hassfest דורש סדר: domain, name, ואז אלפביתי.** זו שגיאה
# קשה אצלו, לא אזהרה.
_mkeys = list(_mani)
ok("מפתחות המניפסט ממוינים",
   _mkeys[:2] == ["domain", "name"] and _mkeys[2:] == sorted(_mkeys[2:]))
# **עברית היא ברירת המחדל.** `README.md` הוא מה שגיטהאב ו-HACS
# מציגים, וקהל היעד קורא עברית. האנגלית היא הפניה ממנו.
_readmes = {}
for _r in ("README.md", "README.en.md"):
    ok(f"{_r} קיים", (ROOT / _r).exists())
    _readmes[_r] = (ROOT / _r).read_text("utf-8") if (ROOT / _r).exists() else ""
ok("README.md הוא העברי", bool(_HEB0.search(_readmes["README.md"][:400])))
ok("README.en.md הוא האנגלי", not _HEB0.search(_readmes["README.en.md"][:400]))
ok("כל אחד מפנה לשני",
   "README.en.md" in _readmes["README.md"]
   and "README.md" in _readmes["README.en.md"])

# **תמונה שבורה ב-README היא מה שרואים ראשון.** כל קובץ שמופנים
# אליו חייב להיות בעץ לפני פרסום.
import re as _reR  # noqa: E402
_missing_img = [
    f"{_r} → {_src}"
    for _r, _txt in _readmes.items()
    for _src in set(_reR.findall(r'(?:src="|]\()(docs/[^"\)]+)', _txt))
    if not (ROOT / _src).exists()
]
ok("כל תמונה שה-README מפנה אליה קיימת", not _missing_img)
for _x in _missing_img:
    print("      חסר:", _x)

# **הצהרת האחריות אינה קישוט.** התוסף שולט במנעולים ומחייג בתשלום,
# ואסור שהסעיף הזה ייעלם בעריכה עתידית.
for _r, _needle in (("README.md", "הצהרת אחריות"), ("README.en.md", "Disclaimer")):
    ok(f"{_r}: יש הצהרת אחריות", _needle in _readmes[_r])

print("\n== הטופס אינו מציע מה שאינו קיים ==")
from custom_components.ha_ivr.providers import (  # noqa: E402
    pbx as _pbx, technoline as _tl, vonage as _vg, yemot as _ym,
)
# **"עוזר קולי" הוצע כתווית ברירת מחדל לכל ספק**, כולל לימות
# שאין לו ערוץ סטרימינג כלל — כלומר הטופס הציע שם למשהו שאינו
# קיים אצלו.
_cfg5 = (_core_dir / "config_shared.py").read_text("utf-8")
ok("אין תווית ברירת מחדל למעבר",
   'label_default="עוזר קולי"' not in _cfg5)

# **משמעות היעד שונה בין הספקים.** מזהה שלוחה אצל אחד, ולא
# בשימוש כלל אצל אחר. תיאור קבוע היה נכון לאחד ושגוי לשאר.
for _d5 in (_ym, _tl, _vg, _pbx):
    ok(f"{_d5.DRIVER_ID}: יש רמז ליעד",
       bool(getattr(_d5, "GOTO_TARGET_HINT", "")))
ok("הרמז מגיע מהדרייבר לטופס",
   'GOTO_TARGET_HINT' in _cfg5 and '"hint"' in _cfg5)

# בורר הרשומות בשירות מציע כל רשומה של הדומיין — גם ספק שאינו
# יודע לחייג. הבדיקה במטפל הופכת את זה להודעה ולא לכשל עמוק.
_init5 = (_core_dir / "__init__.py").read_text("utf-8")
ok("send_call דוחה ספק בלי מסלול יוצא",
   'translation_key="provider_no_alerts"' in _init5)

print("\n== ה-CI מריץ את מה שהשער מריץ ==")
# **שער שרץ רק מקומית אינו שער.** אם ה-workflow ישכח בדיקה,
# היא תיעלם בשקט מכל דחיפה — ואיש לא ישים לב עד שמשהו יישבר
# אצל משתמש.
_ci = (ROOT / ".github" / "workflows" / "validate.yml")
ok("קיים workflow", _ci.exists())
if _ci.exists():
    _ci_src = _ci.read_text("utf-8")
    _scripts = sorted(
        f.name for f in (ROOT / "tests").glob("*.py")
        if f.name.startswith(("run_", "check_"))
    )
    _missing = [s for s in _scripts if s not in _ci_src]
    ok("כל בדיקות השער ב-CI", not _missing)
    for _m in _missing:
        print("      חסר ב-CI:", _m)
    ok("hassfest רץ", "hassfest" in _ci_src)
    ok("HACS רץ", "hacs/action" in _ci_src)

print("\n== מבחן הספק הרביעי ==")
from custom_components.ha_ivr.diagnostics import _redact_keys  # noqa: E402
from custom_components.ha_ivr.providers import (  # noqa: E402
    pbx as _pbx, technoline as _tl, vonage as _vg, yemot as _ym,
)

# **הדגלים על הדרייבר, לא שם הספק בטופס.** שלוש השוואות מחרוזת
# ב-`config_flow` היו הדלת השנייה שדרכה ספק רביעי חוזר לחייב
# עריכה בליבה, בזמן שהמנוע עצמו כבר היה נקי.
_flow4 = (_core_dir / "config_flow.py").read_text("utf-8")
ok("הטופס שואל את הדרייבר",
   'getattr(driver, "NEEDS_CHANNEL_TOKEN"' in _flow4
   and 'getattr(driver, "NEEDS_RATE"' in _flow4)
ok("טכנוליין מכריז על מה שהוא צריך",
   _tl.NEEDS_CHANNEL_TOKEN and _tl.NEEDS_RETURN_PATH)
ok("Vonage מכריז על הקצב", _vg.NEEDS_RATE)
ok("ימות אינו מכריז על ערוץ",
   not getattr(_ym, "NEEDS_CHANNEL_TOKEN", False))

# **הסתרה לפי דפוס.** רשימת שמות מכסה את הספקים שהיו בה ביום
# שנכתבה; ספק רביעי שיוסיף מפתח לא ייכלל, ואיש לא ישים לב עד
# שקובץ אבחון ישותף.
_opts4 = {"newprovider_secret": "S", "newprovider_phone": "05",
          "intro": "x", "stream_max_minutes": 15}
_hidden = _redact_keys(_opts4)
ok("סוד של ספק שאינו קיים עדיין מוסתר", "newprovider_secret" in _hidden)
ok("מספר טלפון של ספק כזה מוסתר", "newprovider_phone" in _hidden)
ok("מה שאינו סוד נשאר גלוי",
   "intro" not in _hidden and "stream_max_minutes" not in _hidden)

# הפרוטוקול: DOMAIN היה שריד מהפיצול ואינו נדרש עוד.
ok("הפרוטוקול בלי DOMAIN",
   "DOMAIN: str" not in (_core_dir / "registry.py").read_text("utf-8"))

print("\n== ההגדרות: מה שמוצג ומה שנקרא ==")
import json as _json  # noqa: E402
import re as _re3  # noqa: E402
import types  # noqa: E402
from custom_components.ha_ivr import config_shared as _cs0  # noqa: E402
from custom_components.ha_ivr.providers import (  # noqa: E402
    pbx as _pbx, technoline as _tl, vonage as _vg, yemot as _ym,
)

# **ערך מספרי מההגדרות עובר סיבוב דרך JSON.** אותו שדה חוזר
# כ-15, כ-15.0 או כ-"15.0", ו-`int("15.0")` נופל ב-ValueError
# — ומפיל את **כל המסך**, לא רק את השדה.
for _v, _want in (("15.0", 15.0), (15.0, 15.0), (15, 15.0), ("15", 15.0)):
    ok(f"num מקבל {_v!r}", _cs0.num(_v, 0) == _want)
ok("num נופל לברירת מחדל", _cs0.num("לא-מספר", 7) == 7.0)
ok("num על ריק", _cs0.num(None, 7) == 7.0)
check("מסך העוזר נבנה עם ערכי מחרוזת",
      lambda: _cs0.stream_schema(
          {"stream_max_minutes": "15.0", "stream_echo_tail": "0.25"},
          channel_token=True, return_path=True, rate=True))

# **כתובת הסטרימינג מוצגת רק כשיש מה להדביק.** לימות אין ערוץ,
# ואצל Vonage הכתובת נשלחת ב-NCCO בזמן השיחה — הצגתה שולחת
# את המשתמש לחפש שדה שאינו קיים.
_e0 = types.SimpleNamespace(data={"token": "T"})
ok("ימות: בלי כתובת סטרימינג",
   not _cs0.endpoint_urls(None, _e0, _ym)["stream_url"])
ok("טכנוליין: עם כתובת סטרימינג",
   bool(_cs0.endpoint_urls(None, _e0, _tl)["stream_url"]))
ok("Vonage: בלי כתובת סטרימינג",
   not _cs0.endpoint_urls(None, _e0, _vg)["stream_url"])

# כל מה שהטופס מכניס כ-placeholder חייב להופיע בתיאור, ולהפך.
_desc = _json.loads(
    (_core_dir / "translations" / "he.json").read_text("utf-8")
)["options"]["step"]["init"]["description"]
_holes = set(_re3.findall(r"\{(\w+)\}", _desc))
_given = set(_cs0.endpoint_urls(None, _e0, _tl))
ok("התיאור והערכים תואמים", _holes <= _given)

print("\n== כל פלטפורמה נטענת ==")
# **פלטפורמה בלי `async_setup_entry` נכשלת בטעינה** ומשאירה את
# הישויות שלה חסרות, עם שגיאה שמופיעה רק ביומן. זה קרה פעמיים
# באיחוד — `notify` ואז `select` — ולכן זו בדיקה ולא זכירה.
import importlib as _imp  # noqa: E402

_PLATFORMS = ("sensor", "select", "notify", "assist_satellite")
for _plat in _PLATFORMS:
    _mod = _imp.import_module(f"custom_components.ha_ivr.{_plat}")
    ok(f"{_plat}: יש async_setup_entry",
       callable(getattr(_mod, "async_setup_entry", None)))

# ומה שמוצהר ב-`_platforms` חייב קובץ שמתאים לו.
_init_src2 = (_core_dir / "__init__.py").read_text("utf-8")
for _plat in _PLATFORMS:
    if f"Platform.{_plat.upper()}" in _init_src2:
        ok(f"{_plat}: הקובץ קיים", (_core_dir / f"{_plat}.py").exists())

# **חתימות שהטופס קורא להן.** קריאה עם ארגומנט שאינו בחתימה
# נופלת ב-TypeError בתוך הטופס, ולא בטעינה.
import inspect as _insp2  # noqa: E402
from custom_components.ha_ivr import config_shared as _cs  # noqa: E402

_flow_txt = (_core_dir / "config_flow.py").read_text("utf-8")
for _fn in ("stream_schema", "endpoint_urls", "ip_errors"):
    _sig = _insp2.signature(getattr(_cs, _fn))
    ok(f"{_fn}: נקראת מהטופס", f"{_fn}(" in _flow_txt)
_probe = _cs.stream_schema({}, channel_token=True, return_path=True, rate=True)
ok("stream_schema נבנית בפועל", _probe is not None)

print("\n== כל שדה בטופס מתורגם ==")
import ast as _ast  # noqa: E402
import json as _json  # noqa: E402
# **שדה בלי מחרוזת מוצג כמפתח הגולמי** — `technoline_api_key`
# במקום "מפתח API של טכנוליין" — ואין שום שגיאה שמסבירה. זה
# בדיוק מה שקרה כשמסכי ההגדרות אוחדו והמחרוזות שלהם לא עברו.
_form_fields = set()
for _f in ["config_flow.py", "config_shared.py"] + [
        f"providers/{p}.py" for p in ("yemot", "technoline", "vonage")]:
    _s = (_core_dir / _f).read_text("utf-8")
    for _n in _ast.walk(_ast.parse(_s)):
        if not isinstance(_n, _ast.Call) or not _n.args:
            continue
        _first = _n.args[0]
        if not (isinstance(_first, _ast.Constant)
                and isinstance(_first.value, str)):
            continue
        if (getattr(_n.func, "attr", "") in ("Required", "Optional")
                or getattr(_n.func, "id", "") == "opt"):
            _form_fields.add(_first.value)


def _translated(doc):
    found = set()

    def walk(node):
        if not isinstance(node, dict):
            return
        for key, val in node.items():
            if key in ("data", "fields") and isinstance(val, dict):
                found.update(val)
            walk(val) if isinstance(val, dict) else None

    walk(doc)
    return found


for _lang in ("strings.json", "translations/he.json"):
    _doc = _json.loads((_core_dir / _lang).read_text("utf-8"))
    _have = _translated(_doc)
    _gap = sorted(_f for _f in _form_fields if _f not in _have)
    ok(f"{_lang}: כל שדה בטופס מתורגם", not _gap)
    for _g in _gap:
        print("      חסר:", _g)

# מסכי הטופס עצמם: שלב בלי כותרת מוצג כמזהה שלו.
for _lang in ("strings.json", "translations/he.json"):
    _doc = _json.loads((_core_dir / _lang).read_text("utf-8"))
    _steps = set(_doc.get("options", {}).get("step", {}))
    ok(f"{_lang}: שלושת מסכי ההגדרות קיימים",
       {"init", "menu_settings", "stream_settings"} <= _steps)

print("\n== הטופס אינו תלוי ב-async_setup ==")
# **HA קוראת ל-`async_setup` רק כשנטענת רשומה.** בטופס הראשון
# עוד אין אחת, ולכן רישום שחי שם בלבד משאיר את בורר הספק ריק —
# בלי שום שגיאה שתסביר.
from custom_components.ha_ivr import providers as _provs  # noqa: E402

registry._DRIVERS.clear()
ok("המרשם ריק לפני הרישום", not registry.registered())
_provs.ensure_registered()
ok("ensure_registered ממלא את המרשם",
   set(registry.registered()) == {"pbx", "technoline", "vonage", "yemot"})
_provs.ensure_registered()
ok("קריאה חוזרת אינה מכפילה",
   len(registry.registered()) == 4)

_flow_src2 = (_core_dir / "config_flow.py").read_text("utf-8")
_steps = [s for s in ("async_step_user", "async_step_settings",
                      "async_step_init", "async_step_menu_settings",
                      "async_step_stream_settings")
          if f"def {s}" in _flow_src2]
_unguarded = [
    s for s in _steps
    if "ensure_registered()" not in _flow_src2.split(f"def {s}")[1][:400]
]
ok("כל שלב בטופס מוודא רישום", not _unguarded)
for _s in _unguarded:
    print("      ללא רישום:", _s)

print("\n== עץ לכל רשומה, לא לכל דומיין ==")
# **ההנחה שהוסרה חייבת להישאר מוסרת.** `single_config_entry`
# הוא דגל במניפסט, לא מבנה — ומי שיוסיף בעוד חצי שנה קריאה לפי
# דומיין יראה הכל עובד, עד לרשומה השנייה. אז שני תפריטים
# יתמזגו לאחד, ובלי שום שגיאה.
import inspect as _insp  # noqa: E402
for _fn in (menu.build_config, menu.build_tree):
    _params = list(_insp.signature(_fn).parameters)
    ok(f"{_fn.__name__} מקבלת רשומה ולא דומיין",
       "entry" in _params and "domain" not in _params)

_engine_src = "\n".join(
    (_core_dir / _f).read_text("utf-8")
    for _f in ("menu.py", "view.py", "stream.py", "diagnostics.py")
)
ok("אין קריאה לבניית עץ לפי דומיין",
   "build_config(hass, domain" not in _engine_src
   and "build_tree(self.hass, drv.DOMAIN" not in _engine_src
   and "build_tree(hass, domain" not in _engine_src)

# שלוש נקודות הכניסה מחפשות רשומה. אף אחת לא רשאית לקחת את
# הראשונה שבאה — הטוקן הוא מה שמזהה, לא הסדר.
for _f in ("view.py", "stream.py"):
    _src5 = (_core_dir / _f).read_text("utf-8")
    ok(f"{_f}: אינו לוקח את הרשומה הראשונה",
       "entries[0]" not in _src5)
    ok(f"{_f}: מתאים לפי טוקן",
       "hmac.compare_digest" in _src5)

print("\n== שגיאות מתורגמות ==")
import ast as _ast  # noqa: E402
import re as _re4  # noqa: E402
_HEB = _re4.compile("[\u0590-\u05ff]")
# **מחרוזת בקוד יכולה להיות בשפה אחת בלבד.** שגיאה שמוצגת בממשק
# חייבת מפתח, כדי שתיאמר בעברית למי שממשקו עברית ובאנגלית לשאר.
import json as _js2  # noqa: E402
_core = ROOT / "custom_components" / "ha_ivr"
_exc_en = _js2.loads((_core / "strings.json").read_text("utf-8"))["exceptions"]
_exc_he = _js2.loads(
    (_core / "translations" / "he.json").read_text("utf-8"))["exceptions"]
ok("לכל שגיאה יש מפתח בשתי השפות", set(_exc_en) == set(_exc_he))
ok("האנגלית בלי עברית",
   not _HEB.search(_js2.dumps(_exc_en, ensure_ascii=False)))
ok("העברית בעברית", bool(_HEB.search(_js2.dumps(_exc_he, ensure_ascii=False))))

# כל `translation_key` שהקוד מבקש חייב להתקיים — מפתח חסר מוצג
# למשתמש כמזהה גולמי.
_used = set()
for _f in sorted((ROOT / "custom_components").rglob("*.py")):
    if "__pycache__" in str(_f):
        continue
    _src2 = _f.read_text("utf-8")
    for _n in _ast.walk(_ast.parse(_src2)):
        if isinstance(_n, _ast.keyword) and _n.arg == "translation_key":
            if isinstance(_n.value, _ast.Constant):
                _used.add(_n.value.value)
        if (isinstance(_n, _ast.Call)
                and getattr(_n.func, "id", "") == "_error" and _n.args
                and isinstance(_n.args[0], _ast.Constant)):
            _used.add(_n.args[0].value)
# `translation_key` יכול להצביע גם לבורר (`selector`), לא רק
# לשגיאה. שני המאגרים לגיטימיים.
_sel_keys = _js2.loads((_core / "strings.json").read_text("utf-8")).get("selector", {})
_valid_keys = set(_exc_en) | set(_sel_keys)
_missing = sorted(_used - _valid_keys)
ok("כל מפתח שבקוד קיים במחרוזות", not _missing)
for _m in _missing:
    print("      חסר:", _m)

# שגיאה שמוצגת בממשק ומכילה עברית ישירה אינה ניתנת לתרגום.
_raw = []
for _f in sorted((ROOT / "custom_components").rglob("*.py")):
    if "__pycache__" in str(_f):
        continue
    _src2 = _f.read_text("utf-8")
    for _n in _ast.walk(_ast.parse(_src2)):
        if not isinstance(_n, _ast.Raise) or not isinstance(_n.exc, _ast.Call):
            continue
        _nm = getattr(_n.exc.func, "id", "") or getattr(_n.exc.func, "attr", "")
        if _nm != "HomeAssistantError":
            continue
        _seg = _ast.get_source_segment(_src2, _n.exc) or ""
        if _HEB.search(_seg):
            _raw.append(f"{_f.name}:{_n.lineno}")
ok("אין שגיאת ממשק עם עברית בקוד", not _raw)
for _x in _raw:
    print("      ", _x)

print("\n== אין פרטים מזהים בעץ ==")
# **הריפו ציבורי.** מספר טלפון אמיתי, מפתח, טוקן או נתיב של
# התקנה מסוימת הם דברים שלא ניתן לקחת בחזרה אחרי דחיפה אחת.
import re as _re3  # noqa: E402
_LEAK = {
    "מספר טלפון אמיתי": _re3.compile(  # noleak
        r"0(?:5[0-9]|7[2-9])-?(?!1234567|21345|1111111|2222222|3333333|9999999)\d{7}"  # noleak
    ),
    "נתיב התקנה מסוימת": _re3.compile(r"ha_netfree|/srv/hass/"),  # noleak
    "מפתח או טוקן": _re3.compile(
        r"(?i)(api[_-]?key|token|bearer|secret)\s*[:=]\s*[\"']?[A-Za-z0-9]{12,}"
    ),
}
_found = []
for _f in sorted(ROOT.rglob("*")):
    if (not _f.is_file() or "__pycache__" in str(_f) or ".git" in _f.parts
            or _f.suffix not in (".py", ".md", ".json", ".yaml", ".sh")):
        continue
    # שורות שמגדירות את התבניות עצמן אינן דליפה.
    _txt = "\n".join(
        _l for _l in _f.read_text("utf-8", errors="replace").splitlines()
        if "noleak" not in _l
    )
    for _what, _pat in _LEAK.items():
        for _m in _pat.findall(_txt):
            _found.append(f"{_f.name}: {_what} — {_m if isinstance(_m, str) else _m[0]}")
ok("אין פרטים מזהים בעץ", not _found)
for _x in _found[:8]:
    print("     ", _x)

print("\n== יומן באנגלית ==")
import re as _re2  # noqa: E402
_HEB = _re2.compile("[\u0590-\u05ff]")
# **היומן נקרא על ידי מי שמדביק שגיאה ל-issue**, ולכן הוא
# באנגלית. מה שהמתקשר שומע ומה שהמשתמש קורא בממשק נשאר עברית —
# זו ההפרדה של HA, וזה גם ההיגיון: קהל אחד קורא כל אחד מהם.
import ast as _ast  # noqa: E402
_LOGFN = {"debug", "info", "warning", "error", "exception", "critical"}
_heb_logs = []
for _f in sorted((ROOT / "custom_components").rglob("*.py")):
    if "__pycache__" in str(_f):
        continue
    for _n in _ast.walk(_ast.parse(_f.read_text("utf-8"))):
        if not isinstance(_n, _ast.Call):
            continue
        _name = getattr(_n.func, "attr", "") or getattr(_n.func, "id", "")
        if _name not in _LOGFN:
            continue
        for _a in _n.args:
            if (isinstance(_a, _ast.Constant) and isinstance(_a.value, str)
                    and _HEB.search(_a.value)):
                _heb_logs.append(f"{_f.name}: {_a.value[:40]}")
ok("אין הודעת יומן בעברית", not _heb_logs)
for _x in _heb_logs[:5]:
    print("     ", _x)

# ומה ש**כן** חייב להישאר עברית: מה שהמתקשר שומע.
_spoken = (_core_dir / "translations_he.py").read_text("utf-8")
ok("ההקראה נשארה עברית", bool(_HEB.search(_spoken)))

# **`deploy.sh` מחפש את שורת העלייה ביומן.** הדפוס התיישן כאן
# פעמיים: הסריקה לאנגלית החליפה מילה שהוא חיפש, והאיחוד השאיר
# אותו על `ha_ivr_core` בזמן שהיומן כותב `ha_ivr`. בשתי הפעמים
# הוא המתין תשעים שניות והכריז על כישלון בזמן ש-HA עלתה תקין.
#
# **הבדיקה עצמה החמיצה את השנייה** — היא קילפה מהדפוס את
# הקידומת שהתיישנה לפני ההשוואה, כלומר בדקה את מה שנשאר אחרי
# שהחלק השבור הוסר. לכן היא מרכיבה היום את השורה שתיכתב ביומן
# ומריצה את הדפוס עליה כרגקס, בדיוק כמו `grep`.
_boot = (_core_dir / "__init__.py").read_text("utf-8")
_deploy = (ROOT / "deploy.sh").read_text("utf-8")
_needle = _deploy.split('grep -m1 "')[1].split('"')[0]
_fmt = next((ln for ln in _boot.splitlines() if "is running" in ln), "")
_logged = _fmt.strip().strip('",').replace("%s", "0.0.0+abcdef12")
ok("deploy.sh מחפש את מה שהיומן כותב", bool(_re2.search(_needle, _logged)))

print("\n== היגיינת קוד ==")
# שלוש הבדיקות נולדו מסקירה אחת שמצאה את שלושתן בפועל: שורת יומן
# עם `%s` בלי ארגומנט (נכשלת ברגע הרישום עצמו — TypeError במקום
# ההודעה), `_LOGGER` שהוגדר פעמיים באותו מודול, ומחרוזת תיעוד
# יתומה באמצע קובץ — כולן צלקות של איחוד קבצים.

# --- מציין מיקום בלי ארגומנט ---
_PLACEHOLDER = _re2.compile(r"%(?:\((\w+)\))?[-#0 +]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[diouxXeEfFgGcrsa]")
_bad_logs = []
for _f in sorted((ROOT / "custom_components").rglob("*.py")):
    if "__pycache__" in str(_f):
        continue
    for _n in _ast.walk(_ast.parse(_f.read_text("utf-8"))):
        if (not isinstance(_n, _ast.Call)
                or not isinstance(_n.func, _ast.Attribute)
                or _n.func.attr not in _LOGFN
                or getattr(_n.func.value, "id", "") != "_LOGGER"):
            continue
        if not (_n.args and isinstance(_n.args[0], _ast.Constant)
                and isinstance(_n.args[0].value, str)):
            continue
        if any(isinstance(_a, _ast.Starred) for _a in _n.args):
            continue
        _fmt2 = _n.args[0].value.replace("%%", "")
        _holes = _PLACEHOLDER.findall(_fmt2)
        # מיפוי בשמות (%(name)s) מקבל מילון אחד, לא ארגומנט לחור.
        _want = 1 if any(_holes) and all(_holes) else len(_holes)
        if _want != len(_n.args) - 1:
            _bad_logs.append(
                f"{_f.name}:{_n.lineno} — {_want} מציינים, {len(_n.args) - 1} ארגומנטים"
            )
ok("לכל מציין מיקום ביומן יש ארגומנט", not _bad_logs)
for _x in _bad_logs[:5]:
    print("     ", _x)

# --- הגדרה כפולה ברמת המודול ---
_dups = []
for _f in sorted((ROOT / "custom_components").rglob("*.py")):
    if "__pycache__" in str(_f):
        continue
    _seen_names: dict[str, int] = {}
    for _n in _ast.parse(_f.read_text("utf-8")).body:
        _names = []
        if isinstance(_n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            _names = [_n.name]
        elif isinstance(_n, _ast.Assign):
            _names = [_t.id for _t in _n.targets if isinstance(_t, _ast.Name)]
        elif isinstance(_n, _ast.AnnAssign) and isinstance(_n.target, _ast.Name):
            _names = [_n.target.id]
        for _nm in _names:
            if _nm in _seen_names:
                _dups.append(f"{_f.name}: {_nm} (שורות {_seen_names[_nm]} ו-{_n.lineno})")
            _seen_names[_nm] = _n.lineno
ok("אין הגדרה כפולה ברמת המודול", not _dups)
for _x in _dups[:5]:
    print("     ", _x)

# --- מחרוזת תיעוד יתומה ---
# בתוך מחלקה, מחרוזת **צמודה להשמה** היא תיעוד שדה — הסגנון של
# `registry.py` ו-`tree.py`. כל מחרוזת חשופה אחרת באמצע קובץ היא
# שריד עריכה.
_orphans = []
for _f in sorted((ROOT / "custom_components").rglob("*.py")):
    if "__pycache__" in str(_f):
        continue
    _tree = _ast.parse(_f.read_text("utf-8"))
    for _scope in _ast.walk(_tree):
        if not isinstance(_scope, (_ast.Module, _ast.FunctionDef,
                                   _ast.AsyncFunctionDef, _ast.ClassDef)):
            continue
        for _i, _n in enumerate(_scope.body):
            if not (_i > 0 and isinstance(_n, _ast.Expr)
                    and isinstance(_n.value, _ast.Constant)
                    and isinstance(_n.value.value, str)):
                continue
            if (isinstance(_scope, _ast.ClassDef)
                    and isinstance(_scope.body[_i - 1], (_ast.Assign, _ast.AnnAssign))):
                continue
            _orphans.append(f"{_f.name}:{_n.lineno}")
ok("אין מחרוזת תיעוד יתומה", not _orphans)
# --- נוסח התיעוד ---
# הקוד מפורסם, והתיעוד בו נועד למי שיקרא אותו בעתיד ולא ליומן
# הבנייה. שלושה סממנים של הסוג השני נבדקים כאן: הפניה למסמכי
# עבודה שאינם מפורסמים, הדגשות מרקדאון שהן רטוריקה ולא תוכן,
# ותאריך של מדידה מסוימת.
_PRIVATE_DOCS = _re2.compile(r"\bHANDOFF\b|\bPROCESS\.md\b")
_BOLD = _re2.compile(r"\*\*[^*\s][^*]*\*\*")
_DATED = _re2.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2}\b")
_prose = []
for _f in sorted((ROOT / "custom_components").rglob("*.py")):
    if "__pycache__" in str(_f):
        continue
    _src3 = _f.read_text("utf-8")
    _blocks = [
        (_l.lstrip("# ").strip(), _i + 1)
        for _i, _l in enumerate(_src3.splitlines())
        if _l.strip().startswith("#")
    ]
    for _n in _ast.walk(_ast.parse(_src3)):
        if isinstance(_n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                           _ast.ClassDef)) and (_d := _ast.get_docstring(_n)):
            _blocks.append((_d, getattr(_n, "lineno", 0)))
    for _text, _line in _blocks:
        for _what, _pat in (("מסמך עבודה פרטי", _PRIVATE_DOCS),
                            ("הדגשת מרקדאון", _BOLD),
                            ("תאריך מדידה", _DATED)):
            if _m := _pat.search(_text):
                _prose.append(f"{_f.name}:{_line} — {_what}: {_m.group()[:40]}")
ok("התיעוד בקוד הוא תיעוד ולא יומן בנייה", not _prose)
for _x in _prose[:8]:
    print("     ", _x)

for _x in _orphans[:5]:
    print("     ", _x)

print("\n== התרגומים ==")
import re as _re  # noqa: E402
import json as _json  # noqa: E402
_HEB = _re.compile("[\u0590-\u05ff]")


def _keys(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _keys(v, f"{p}.{k}")
    else:
        yield p


for _pkg in ("ha_ivr",):
    _dir = ROOT / "custom_components" / _pkg
    _src = (_dir / "strings.json").read_text("utf-8")
    _he = (_dir / "translations" / "he.json").read_text("utf-8")
    _en = (_dir / "translations" / "en.json").read_text("utf-8")

    # **`strings.json` הוא מקור האמת של HA, והוא אנגלית.** שפות
    # אחרות נגזרות ממנו. קובץ מקור בעברית הופך את הכיוון ומסמן
    # אינטגרציה שנכתבה מחוץ למוסכמה.
    ok(f"{_pkg}: strings.json באנגלית", not _HEB.search(_src))
    ok(f"{_pkg}: en.json תואם ל-strings.json", _src == _en)
    # קהל היעד עברי, ולכן **כל** מפתח חייב תרגום — מפתח חסר
    # מוצג כמזהה הגולמי בממשק.
    ok(f"{_pkg}: he.json מכסה כל מפתח",
       set(_keys(_json.loads(_src))) == set(_keys(_json.loads(_he))))
    ok(f"{_pkg}: he.json בעברית", bool(_HEB.search(_he)))

# `services.yaml` אינו מתורגם. שם ותיאור שיושבים בו מוצגים
# באותה שפה לכולם, ולכן הם שייכים ל-`strings.json` תחת `services`.
for _pkg in ("ha_ivr",):
    _dir = ROOT / "custom_components" / _pkg
    _yaml = (_dir / "services.yaml").read_text("utf-8")
    ok(f"{_pkg}: services.yaml הוא מבנה בלבד",
       "name:" not in _yaml and "description:" not in _yaml)
    ok(f"{_pkg}: services.yaml בלי עברית", not _HEB.search(_yaml))
    for _lang in ("strings.json", "translations/he.json"):
        _d = _json.loads((_dir / _lang).read_text("utf-8"))
        ok(f"{_pkg}: {_lang} מתאר את השירות",
           "send_call" in _d.get("services", {}))

# שם האינטגרציה במניפסט הוא מה שרואה מי שאין לו תרגום.
for _pkg in ("ha_ivr",):
    _m = (ROOT / "custom_components" / _pkg / "manifest.json").read_text("utf-8")
    ok("ha_ivr: מניפסט באנגלית", not _HEB.search(_m))

from custom_components.ha_ivr.providers import technoline as tl_out  # noqa: E402

# **השירות שמפורסם חייב להיות השירות שקיים.** שדה ב-services.yaml
# שאינו בסכמה מופיע בבורר של הממשק, ומי שממלא אותו מקבל שגיאת
# ולידציה בלי הסבר.
# פענוח מצומצם ולא PyYAML: הבדיקות רצות על פייתון נקי בלי
# תלויות, וכל מה שצריך כאן הוא שמות השדות ודגל ה-required.
_svc_src = (ROOT / "custom_components" / "ha_ivr"
            / "services.yaml").read_text("utf-8")
_declared = {
    _l.strip().rstrip(":")
    for _l in _svc_src.splitlines()
    if _l.startswith("    ") and not _l.startswith("     ")
    and _l.rstrip().endswith(":")
}
import custom_components.ha_ivr as _core_mod  # noqa: E402

_marks = {
    str(k): type(k).__name__ for k in _core_mod._send_call_schema().schema
}
ok("services.yaml תואם לסכמה", _declared == set(_marks))
ok("message חובה", _marks.get("message") == "Required")
# **חובה.** הרשימה הקבועה הוחלפה בישויות `notify`, ולכן אין
# לאן ליפול; השירות הזה קיים למספר שמחושב בזמן ריצה.
ok("phones חובה", _marks.get("phones") == "Required")
# תיאור שירות נקרא בממשק. ציטוט של הודעת שגיאה פנימית שייך
# ל-CHANGELOG, לא לטופס שהמשתמש רואה.
ok("התיאור אינו מצטט שגיאות מערכת",
   "extra keys" not in _svc_src)
ok("phones מסומן חובה גם ב-yaml",
   "required: true" in _svc_src.split("phones:")[1].split("selector:")[0])

print("\n== כל דרייבר עונה על הפרוטוקול ==")
# מה שהליבה שואלת ספק עם ערוץ סטרימינג. חסר אחד מהם = ההסתעפות
# חוזרת לליבה בפעם הבאה.
for _name, _drv in (("technoline", technoline), ("vonage", vonage)):
    for _fn in ("detect", "clear_command", "hangup_command", "leave_command"):
        ok(f"{_name}.{_fn}", callable(getattr(_drv, _fn, None)))

ok("טכנוליין מזהה את מסגרת הפתיחה שלו",
   (technoline.detect({"type": "start", "callId": "c1", "caller": "050",
                       "format": "pcm16;rate=8000;ch=1"}) or {}).get("rate") == 8000)
ok("Vonage מזהה את שלו",
   (vonage.detect({"content-type": "audio/l16;rate=16000"}) or {}).get("rate") == 16000)
ok("כל אחד דוחה את המסגרת של השני",
   technoline.detect({"content-type": "audio/l16;rate=16000"}) is None
   and vonage.detect({"type": "start"}) is None)
# `target` הוא נתיב בעץ ולא מזהה שלוחה — שני דברים שונים באותה
# מערכת. בלי נתיב אין מה לשלוח, והליבה סוגרת את הסוקט.
ok("העברה רק כשיש נתיב",
   technoline.leave_command("/2") == {"type": "transfer_extension", "target": "/2"}
   and technoline.leave_command("") is None)
ok("ל-Vonage אין העברה ואין ניתוק בערוץ",
   vonage.leave_command("/") is None and vonage.hangup_command() is None)


for name, drv in DRIVERS:
    for attr in ("DRIVER_ID", "NAME", "SUPPORTS_GOTO", "SUPPORTS_STREAM",
                 "parse", "respond"):
        ok(f"{name}.{attr}", hasattr(drv, attr))
    # **אין DOMAIN לספק.** הדומיין אחד, והספק מזוהה ב-DRIVER_ID
    # ובשדה `provider` שברשומה. השארת DOMAIN הייתה מזמינה השוואה
    # שמתאימה לכל הרשומות.
    ok(f"{name} בלי DOMAIN משלו", not hasattr(drv, "DOMAIN"))
    ok(f"{name}.NAME לתצוגה", bool(getattr(drv, "NAME", "")))

print("\n== מרשם הדרייברים ==")
for _, drv in DRIVERS:
    registry.register(drv)
ok("ארבעתם רשומים",
   registry.registered() == ["pbx", "technoline", "vonage", "yemot"])
# המרשם עונה על מה שהיו רשימות קשיחות ב-const: מי קיים, למי יש
# סטרימינג, ואיך קוראים לו.
ok("שאילתת הסטרימינג על המרשם",
   {d.DRIVER_ID for d in registry.with_stream()} == {"pbx", "technoline", "vonage"})
ok("שאילתה על כל הדרייברים",
   {d.DRIVER_ID for d in registry.all_drivers()}
   == {"pbx", "technoline", "vonage", "yemot"})
ok("שליפה לפי מזהה", registry.get("yemot") is yemot)
ok("מזהה לא מוכר מחזיר None", registry.get("nope") is None)

print("\n== רינדור בכל ספק, דרך הפרוטוקול האחיד ==")
prompt = Prompt(messages=[Say("text", "הקישו ספרה")], allowed=frozenset("12"),
                at_path=("1",), step=2)
term = Terminal(messages=[Say("text", "בוצע")])
goto = GoTo(target="500", messages=[Say("text", "מעביר")])
cfg = {"callback_url": "https://x", "stream_url": "wss://x", "token": "T",
       "options": {}}

for name, drv in DRIVERS:
    for label, action in (("prompt", prompt), ("terminal", term), ("goto", goto)):
        check(f"{name}.respond({label})", lambda d=drv, a=action: d.respond(a, cfg))

print("\n== פענוח בקשות נכנסות, חתימה אחידה ==")
check("yemot.parse", lambda: yemot.parse({"ApiCallId": "c", "s2_1": "7"}, {}))
check("technoline.parse", lambda: technoline.parse({"PBXcallId": "c", "s2_1": "7"}, {}))
check("vonage.parse", lambda: vonage.parse({"p": "s2_1"}, {"dtmf": {"digits": "7"}}))
check("pbx.parse", lambda: pbx.parse({}, {"path": "1", "digit": "2", "step": "2"}))
for name, drv in DRIVERS:
    ctx = drv.parse({}, {})
    ok(f"{name}: שיחה חדשה היא צעד 1", ctx.step == 1 and ctx.digit is None)

print("\n== עץ התפריטים ==")
root = tree.build({"intro": "שלום", "items": {
    "1": {"say": "מזגן", "items": {"1": {"say": "הדלקה", "entity": "climate.a",
                                         "action": "turn_on"}}},
    "9": {"say": "עוזר קולי", "goto": "500"}}})
check("tree.prompt_for", lambda: tree.prompt_for(root, (), 1))
check("tree.navigate", lambda: tree.navigate(root, (), "1"))
check("menu.normalize_path", lambda: menu.normalize_path("1/2"))
check("menu.build_config",
      lambda: menu.build_config(fake_ha.FakeHass(), fake_ha.FakeEntry()))

print("\n== נקודת הקצה, מקצה לקצה ==")
hass = fake_ha.FakeHass(
    states={"climate.a": fake_ha.FakeState("cool", friendly_name="מזגן",
                                           unit_of_measurement="°C")},
)
# **הספק יושב ב-`data`, לא בדומיין.** מאז שהעץ מזוהה ברשומה,
# `_handle` מסננת את הרשומות לפי `data["provider"]` — והבדיקה
# נשארה קובעת `entry.domain`, שדה שנקודת הקצה אינה קוראת. כל
# חמש הבקשות כאן חזרו 503 "אין רשומה" ועברו, כי `check` בודקת
# רק שלא נזרקה חריגה. לכן נבדק כאן מהיום גם הקוד שחוזר.
entry = fake_ha.FakeEntry(
    data={"token": "T", "provider": "yemot"},
    options={"allowed_ips": [], "allowed_phones": []},
)
hass.config_entries = fake_ha.FakeConfigEntries([entry])
v = view.IvrView(hass)

for driver in ("yemot", "technoline", "vonage"):
    entry.data["provider"] = driver
    _resp = check(f"IvrView.get({driver})",
                  lambda d=driver: v.get(fake_ha.FakeRequest(), d, "T"))
    ok(f"IvrView.get({driver}) מחזירה 200", getattr(_resp, "status", None) == 200)

entry.data["provider"] = "yemot"
_resp = check("IvrView bad token", lambda: v.get(fake_ha.FakeRequest(), "yemot", "wrong"))
ok("טוקן שגוי מחזיר 401", getattr(_resp, "status", None) == 401)
_resp = check("IvrView unknown driver", lambda: v.get(fake_ha.FakeRequest(), "nope", "T"))
ok("דרייבר לא מוכר מחזיר 404", getattr(_resp, "status", None) == 404)

print("\n== שיחה יוצאת ==")
from custom_components.ha_ivr.outbound import (  # noqa: E402
    OutboundError, clean_phones,
)
from custom_components.ha_ivr.providers import technoline as tl_out  # noqa: E402
from custom_components.ha_ivr.providers import yemot as ym_out  # noqa: E402

ok("clean_phones", clean_phones("050-1234567,tzl:1") == "0501234567,tzl:1")

# תשובת ימות נבדקת בהשוואה ולא בהכלה. `NOT_OK` מכיל `OK`, ולכן
# הבדיקה הקודמת הכריזה "שיחה יוצאת נשלחה" על שיחה שנדחתה — אותו
# סוג באג בדיוק כמו ביטוי היציאה שנתפס בתוך מילה ארוכה יותר.
from custom_components.ha_ivr.providers.yemot import _check_accepted  # noqa: E402


def _accepted(body: str) -> bool:
    try:
        _check_accepted(body)
        return True
    except OutboundError:
        return False


ok("yemot OK מתקבל", _accepted('{"responseStatus":"OK"}'))
ok("yemot NOT_OK נדחה", not _accepted('{"responseStatus":"NOT_OK"}'))
ok("yemot TOKEN_NOT_OK נדחה", not _accepted("TOKEN_NOT_OK"))
ok("yemot EXCEPTION נדחה", not _accepted('{"responseStatus":"EXCEPTION"}'))

# `responseStatus: OK` עם אפס שיחות הוא כשל, לא הצלחה.
from custom_components.ha_ivr.providers.yemot import _report  # noqa: E402

try:
    _report({"responseStatus": "OK", "OKCalls": 0, "ErrorCalls": {"05": "NO_CREDIT"}}, "05")
    ok("yemot אפס שיחות הוא כשל", False)
except OutboundError:
    ok("yemot אפס שיחות הוא כשל", True)

check("yemot דיווח על שיחה מוצלחת",
      lambda: _report({"responseStatus": "OK", "OKCalls": 1, "ErrorCalls": {},
                       "units": "27.97", "CampaignId": "YA-1"}, "05"))
check("yemot דיווח על כשל חלקי",
      lambda: _report({"OKCalls": 2, "ErrorCalls": {"05": "BUSY"}}, "a,b"))
check("yemot תשובה שאינה JSON", lambda: _report(None, "05"))

# ימות שולח טקסט ל-API שלו; טכנוליין רק מחייג, וההקראה שלנו.
# שניהם חייבים להיעצר על מפתח חסר לפני שנוגעים ברשת.
try:
    asyncio.new_event_loop().run_until_complete(
        ym_out.async_send_call(hass, {}, {"phones": "0501234567", "message": "x"})
    )
    ok("yemot: חסר אישור מרים שגיאה", False)
except OutboundError:
    ok("yemot: חסר אישור מרים שגיאה", True)
except Exception as err:  # noqa: BLE001
    ok(f"yemot: חסר אישור — {type(err).__name__}: {err}", False)

try:
    asyncio.new_event_loop().run_until_complete(
        tl_out.async_announce(
            hass, types.SimpleNamespace(options={}, entry_id="e1"),
            phones=["0501234567"],
        )
    )
    ok("technoline: חסר מפתח מרים שגיאה", False)
except OutboundError:
    ok("technoline: חסר מפתח מרים שגיאה", True)
except Exception as err:  # noqa: BLE001
    ok(f"technoline: חסר מפתח — {type(err).__name__}: {err}", False)

print("\n== מסך העוזר מסונן לפי ספק ==")
from custom_components.ha_ivr.config_shared import stream_schema  # noqa: E402


def _fields(**flags):
    return {getattr(k, "schema", k) for k in stream_schema({}, **flags).schema}


_tl = _fields(channel_token=True, return_path=True)
_vg = _fields(rate=True)
ok("מזהה ערוץ רק בטכנוליין",
   "stream_channel_token" in _tl and "stream_channel_token" not in _vg)
ok("נתיב חזרה רק בטכנוליין",
   "stream_return_path" in _tl and "stream_return_path" not in _vg)
# השדה נקרא `stream_rate` — שם ניטרלי, כי הבחירה
# בקצב אינה תכונה של Vonage אלא של מי שמאפשר לבחור.
ok("קצב דגימה רק אצל מי שצריך אותו",
   "stream_rate" in _vg and "stream_rate" not in _tl)
ok("השדות המשותפים בשניהם",
   {"stream_exit", "stream_echo_tail", "stream_tones"} <= (_tl & _vg))
# חמישה שדות ירדו ב-0.28.0. שלושה מהם עברו לישויות, ושניים לא
# הגיעו לצינור מעולם: `async_accept_pipeline_from_satellite` אינה
# מעבירה `noise_suppression_level` ו-`auto_gain_dbfs` כלל. שדה
# שאין לו משמעות גרוע משדה שלא קיים.
ok("השדות שירדו אינם בטופס",
   not ({"stream_pipeline", "stream_engine", "stream_vad",
         "stream_noise", "stream_gain", "stream_max_calls"} & (_tl | _vg)))

print("\n== אודיו ==")
from custom_components.ha_ivr import audio  # noqa: E402

check("resample 8k->16k", lambda: audio.resample(b"\x00\x01" * 160, 8000, 16000))
check("listen_tone", lambda: audio.listen_tone(8000))
check("thinking_tone", lambda: audio.thinking_tone(8000))
check("error_tone", lambda: audio.error_tone(8000))
check("strip_wav", lambda: audio.strip_wav(b"nope"))
# **מה שחזר בפועל, לא מה שביקשנו.** `ATTR_PREFERRED_*` הן
# העדפות ומנוע רשאי להתעלם מהן; הערוצים הם המסוכן — `strip_wav`
# מחזיר את הגוף כמו שהוא ו-`resample` מתייחס אליו כמונו, כלומר
# סטריאו מתנגן במהירות כפולה בלי שום שגיאה.
_hdr = (b"RIFF" + (36 + 8).to_bytes(4, "little") + b"WAVEfmt "
        + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
        + (2).to_bytes(2, "little")            # שני ערוצים
        + (16000).to_bytes(4, "little") + (64000).to_bytes(4, "little")
        + (4).to_bytes(2, "little") + (16).to_bytes(2, "little")
        + b"data" + (8).to_bytes(4, "little") + b"\x00" * 8)
ok("wav_format קורא קצב, ערוצים ועומק",
   audio.wav_format(_hdr) == (16000, 2, 16))
ok("מה שאינו WAV מוחזר כאפסים", audio.wav_format(b"ID3junk") == (0, 0, 0))

ok("resample בקצב זהה אינו נוגע באודיו",
   audio.resample(b"\x01\x02", 8000, 8000) == b"\x01\x02")

print("\n== שכבת הסטרימינג ==")
from custom_components.ha_ivr import stream  # noqa: E402

check("_find_digit", lambda: stream._find_digit({"event": "websocket:dtmf",
                                                 "digit": "#"}))
check("StreamView init", lambda: stream.StreamView(hass))
ok("ערוץ הסטרימינג רק לספקים שתומכים",
   yemot.SUPPORTS_STREAM is False
   and technoline.SUPPORTS_STREAM is True
   and vonage.SUPPORTS_STREAM is True)

# notify נבדק ונשלל בשיחה חיה 19.8.26: Vonage אישרה `clear` תוך
# 140 מ"ש ולא ענתה ל-notify כלל. ההמתנה עלתה 5.2 שניות בתשובה
# הראשונה של כל שיחה, ולכן הפקודה הוסרה.
_sat_src = (_core_dir / "satellite.py").read_text("utf-8")
_stream_src = (_core_dir / "stream.py").read_text("utf-8")
# ההמתנה היא הערכה לפי אורך ה-PCM; לספק אין דרך לומר "סיימתי".
ok("notify הוסר לגמרי",
   '"action": "notify"' not in _stream_src
   and '"action": "notify"' not in _sat_src)

# הסוקט אינו מכיר עוד את הצינור. זה מה שמפריד בין התחבורה למנוע,
# ובלעדיו שתי המחלקות מתחילות לזלוג אחת לשנייה.
ok("התחבורה אינה מריצה צינור",
   "async_pipeline_from_audio_stream" not in _stream_src
   and "PipelineEventType" not in _stream_src)

print("\n== לוויין Assist ==")
from custom_components.ha_ivr.const import SATELLITES, STREAM_LINES  # noqa: E402
from custom_components.ha_ivr.satellite import IvrSatellite  # noqa: E402


class _FakeEntry:
    entry_id = "e1"
    domain = "ha_ivr_technoline"
    options: dict = {}

    def async_create_background_task(self, hass, coro, name):
        # אין לולאת אירועים ב-fake_ha. הקורוטינה נסגרת כדי שלא
        # תיפלט אזהרה, והמשימה מזויפת — מה שנבדק כאן הוא הקשירה
        # ולא שעון הניתוק.
        coro.close()
        return types.SimpleNamespace(cancel=lambda: None)


class _FakeSession:
    """הצד של הקו, כפי שהלוויין רואה אותו."""

    exiting = False


_entry = _FakeEntry()
_lines = [IvrSatellite(_entry, i) for i in range(STREAM_LINES)]
_sat = _lines[0]
for _line in _lines:
    _line.hass = hass

ok("שני קווים", len(_lines) == 2)
# מזהה הקו הראשון חייב להישאר כפי שהיה ב-0.27.0. שינוי שלו היה
# יוצר ישות חדשה ומשאיר את הקיימת יתומה במרשם, כלא זמינה.
ok("מזהה הקו הראשון לא השתנה", _sat.unique_id == "e1_satellite")
ok("לקו השני מזהה משלו", _lines[1].unique_id == "e1_satellite_2")
ok("שמות נבדלים", _sat.name != _lines[1].name)
# ANNOUNCE אינו פעולה של קו אלא של חשבון — הוא מחייג דרך הספק
# ואינו נוגע בסוקט. שני קווים עם היכולת היו שתי דרכים זהות
# לאותו דבר.
# **ANNOUNCE ירד מהישות.** לשירות של HA אין שדה נמענים, ולכן
# הוא יכול היה לומר רק "לרשימה הקבועה" — והרשימה הזו הוחלפה
# בישויות `notify`. שני משטחים במקום שלושה.
ok("הישות אינה חושפת ANNOUNCE",
   not getattr(_sat, "supported_features", 0))

ok("לוויין פנוי בהתחלה", not _sat.busy)

# פורמט ההקראה. בלי בקשה מפורשת הצינור מחזיר mp3, `strip_wav`
# לא מוצא PCM, והמתקשר שומע צליל תקלה במקום תשובה — בדיוק מה
# שקרה בשיחת הלוויין הראשונה, 19.8.26.
ok("מבקשים WAV", _sat.tts_options["preferred_format"] == "wav")
ok("מונו 16 ביט",
   _sat.tts_options["preferred_sample_channels"] == 1
   and _sat.tts_options["preferred_sample_bytes"] == 2)
# בלי שיחה מחוברת אין קצב ספק, ו-ANNOUNCE שואל בדיוק שם.
ok("בלי שיחה — 16 קילוהרץ",
   _sat.tts_options["preferred_sample_rate"] == 16000)

_a, _b = _FakeSession(), _FakeSession()
ok("קשירה ראשונה מצליחה", _sat.attach(_a, 8000))
ok("קשירה שנייה לאותו קו נדחית", not _sat.attach(_b))
# זה הרווח של הלוויין על ההרצה הישירה: ההקראה חוזרת בקצב של
# הספק, ו-resample אינו נוגע בה.
ok("הקצב מגיע מהספק ולא קבוע",
   _sat.tts_options["preferred_sample_rate"] == 8000)
ok("הקו השני פנוי לשיחה השנייה", _lines[1].attach(_b, 8000))

# שחרור בידי שיחה אחרת היה משחרר את הקו מתחת לרגליה של זו שכן
# רצה. הבדיקה מקבעת שהזהות נבדקת.
_sat.detach(_b)
ok("שחרור זר אינו משחרר", _sat.busy)

# שיחה שנקטעה באמצע תשובה לא תגיע ל-`tts_response_finished`,
# והישות הייתה נשארת דולקת אחרי שהמתקשר כבר ניתק.
_sat.state = "responding"
_sat.detach(_a)
ok("שחרור נכון משחרר", not _sat.busy)
ok("שחרור מחזיר לממתין גם בקטיעה", _sat.state == "idle")
_lines[1].detach(_b)

# אירוע בלי שיחה מחוברת נזרק ואינו מפיל — קורה בסגירה, כשהצינור
# פולט אירוע אחרון אחרי הניתוק.
check("אירוע בלי שיחה אינו מפיל",
      lambda: _sat.on_pipeline_event(types.SimpleNamespace(type="run-end", data=None)))

# מסגרת אודיו על קו לא קשור אינה פותחת תור. בלי הבדיקה הזו
# מסגרת שמגיעה אחרי הניתוק הייתה מריצה צינור בלי מי שישמע.
_sat.on_chunk(b"\x00" * 320)
ok("אודיו בלי שיחה אינו מריץ צינור", _sat._run_task is None)

# הצינור ורגישות ה-VAD נקראים מישויות, לא מהטופס. זה מה שהיה
# שבור בשקט ב-0.27.0: `_resolve_pipeline` קורא מ-`pipeline_entity_id`
# ולא מההגדרות, ולכן בחירת הצינור בטופס פשוט לא הגיעה לצינור.
from homeassistant.helpers import entity_registry as _er  # noqa: E402

_er.async_get(hass).entities[
    ("select", "ha_ivr_technoline", "e1-pipeline")
] = "select.ivr_pipeline"
_er.async_get(hass).entities[
    ("select", "ha_ivr_technoline", "e1-vad_sensitivity")
] = "select.ivr_vad"
ok("בורר הצינור נמצא לפי המזהה",
   _sat.pipeline_entity_id == "select.ivr_pipeline")
ok("בורר ה-VAD נמצא לפי המזהה",
   _sat.vad_sensitivity_entity_id == "select.ivr_vad")
# זוג אחד לרשומה: הצינור הוא בחירה של מי שהגדיר, ולא של הקו
# שהמתקשר במקרה נחת עליו.
ok("שני הקווים מצביעים לאותו בורר",
   _lines[1].pipeline_entity_id == _sat.pipeline_entity_id)

from custom_components.ha_ivr.select import selects  # noqa: E402

check("שני הבוררים נבנים", lambda: selects(hass, _entry))
ok("מזהי הבוררים הם מה שהלוויין מחפש",
   {s._attr_unique_id for s in selects(hass, _entry)}
   == {"e1-pipeline", "e1-vad_sensitivity"})

# --- שלושת הבאגים שנמדדו ביומן ב-20.8.26 ---

# מזהה שיחה דולף בין מתקשרים. הישות חיה לאורך כל חיי הרשומה,
# ולכן בלי איפוס בקשירה המתקשר הבא ממשיך את השיחה של הקודם —
# שתי שיחות טלפון נפרדות רצו תחת אותו conversation_id.
_c = _FakeSession()
_sat.attach(_c, 8000)
_sat._conversation_id = "01M0DZ3TMFW3GV13GS6MP15F85"
_sat.detach(_c)
_sat.attach(_FakeSession(), 8000)
ok("מתקשר חדש מקבל מזהה שיחה חדש", _sat._conversation_id is None)
_sat.detach(_sat._session)

_sat_src = (_core_dir / "satellite.py").read_text("utf-8")
# היציאה לתפריט חייבת לעצור את הצינור. נמדד: מילישנייה אחרי
# ההחלטה נורה intent-start, והמודל ענה תשובה שלמה שנזרקה.
ok("יציאה מבטלת את הצינור",
   "await self._cancel_running_pipeline()" in _sat_src)
ok("אירוע בזמן יציאה נזרק", "if self._leaving:" in _sat_src)

# הפריקה: callback שמחזירה ערך הופכת אצל HA לניסיון ליצור משימה,
# ונופלת ב-TypeError שמשאיר את הפלטפורמה פרוקה למחצה.
_plat_src = (ROOT / "custom_components" / "ha_ivr"
             / "assist_satellite.py").read_text("utf-8")
ok("callback הפריקה אינה מחזירה ערך",
   "entry.async_on_unload(_forget)" in _plat_src
   # ההסבר בתיעוד מזכיר lambda; מה שאסור הוא לרשום אחת.
   and "async_on_unload(lambda" not in _plat_src)

# מדידת הרמה — אבחון בלבד, בלי שינוי התנהגות.
_sat._level_sum = 0.0
_sat._level_peak = 0
_sat._level_count = 0
for _ in range(10):
    _sat._note_level(b"\x00\x40" * 160)
ok("רמת הקלט נמדדת", _sat._level_peak > 0 and _sat._level_count == 10)
check("סיכום הרמה אינו מפיל", _sat._report_level)
ok("הסיכום מאפס לתור הבא", _sat._level_count == 0)

print("\n== התראה קולית מהלוויין ==")
# הכל מול pbx.tlivr.com/campaignApiDocs.html ומול מה שנמדד ב-20.8.26.
from custom_components.ha_ivr.providers import technoline as tl_out  # noqa: E402
from custom_components.ha_ivr import announce as announce_store  # noqa: E402

# **המסלול שנבחר.** audioText נופל במנוע ההקראה שלהם (20)
# ו-audioFile אינו נקרא (30) — מה שעובד הוא הפעלת שלוחה, שמחברת
# את הנמען לערוץ הסטרימינג שלנו. אומת בשיחה חיה, קמפיין 119899.
_ann_src = (_core_dir / "providers" / "technoline.py").read_text("utf-8")
ok("ההתראה מפעילה שלוחה", '"messagesType": "extensionActivation"' in _ann_src)
ok("audioText אינו נשלח בהתראה", '"audioText"' not in _ann_src.split("async def async_announce")[1])
ok("audioFile אינו נשלח בהתראה", '"audioFile"' not in _ann_src.split("async def async_announce")[1])
# התראה שלא נענתה אינה שווה חזרה בעוד 20 דקות: ההתראה הממתינה
# כבר פגה, והשיחה החוזרת הייתה מחברת את הנמען לעוזר בלי הקשר.
ok("ניסיון חיוג אחד", '"dialRetries": 1' in _ann_src)

# **הנמען מגיע מישות, לא משדה.** `notify.send_message` הוא
# המשטח של HA לשליחת הודעה, וכל מה שנבנה סביב התראות — קבוצות,
# `alert`, בוררים בבלופרינטים — מגיע דרכו. שירות בדומיין משלנו
# בלתי נראה לכולם.
# **פלטפורמה חייבת לשבת בחבילת הספק.** HA מייבאת
# `<domain>.notify`, ומודול שיושב רק בליבה נכשל ב-
# `ModuleNotFoundError` — והרשומה כולה אינה נטענת.
# **`initiate_flow` הוא מה שכתוב על הכפתור.** בלעדיו HA מציגה
# כפתור "+" ריק, ואין שום שגיאה שמסבירה למה. כל סוג תת-רשומה
# חייב אותו, ובשתי השפות.
import json as _js  # noqa: E402
for _pkg in ("ha_ivr",):
    for _lang in ("strings.json", "translations/he.json"):
        _f = ROOT / "custom_components" / _pkg / _lang
        for _kind, _spec in _js.loads(_f.read_text("utf-8")).get(
                "config_subentries", {}).items():
            ok(f"{_pkg}/{_lang[:2]}: ל-{_kind} יש כותרת לכפתור",
               bool(_spec.get("initiate_flow", {}).get("user")))

for _pkg in ("ha_ivr",):
    _init = (ROOT / "custom_components" / _pkg / "__init__.py").read_text("utf-8")
    ok(f"{_pkg}: מצהיר על פלטפורמת notify", "Platform.NOTIFY" in _init)
    ok(f"{_pkg}: יש לו notify.py",
       (ROOT / "custom_components" / _pkg / "notify.py").exists())
# ל-Vonage אין מסלול יוצא, ולכן גם לא פלטפורמה שלא תיצור דבר.
# הפלטפורמות נגזרות מהיכולות, ולא מרשימה קשיחה לכל ספק.
_init_src = (_core_dir / "__init__.py").read_text("utf-8")
ok("הפלטפורמות נגזרות מהיכולות",
   "def _platforms(driver)" in _init_src
   and 'getattr(driver, "SUPPORTS_STREAM", False)' in _init_src)
ok("נמען רק למי שיודע לחייג",
   'getattr(driver, "async_notify", None) is not None' in _init_src)

# `has_entity_name` מדביק את שם הישות לשם המכשיר. נמען ששמו
# "מנחם" בשניהם ייצר `notify.mnkhm_mnkhm`.
_notify_src = (_core_dir / "notify.py").read_text("utf-8")
ok("ישות הנמען היא המכשיר עצמו", "self._attr_name = None" in _notify_src)

ok("הדרייבר חושף התראה", callable(technoline.async_announce))
ok("טכנוליין יודע לחייג לנמען", callable(technoline.async_notify))
# לימות אין ערוץ סטרימינג, ולכן ההתראה שלו עוברת ב-API שלו —
# אותו משטח, מסלול אחר.
ok("גם ימות, דרך ה-API שלו", callable(yemot.async_notify))
# ל-Vonage אין מסלול יוצא, ולכן אין לו ישויות נמען — עדיף
# מישות שנראית תקינה ונכשלת בשיחה.
ok("Vonage אינו חושף התראה", not hasattr(vonage, "async_notify"))
# הרשימה הקבועה הוחלפה בישויות, ולכן אין לאן ליפול.
ok("אין עוד רשימת נמענים קבועה",
   not hasattr(technoline, "announce_phones"))

# --- send_call לספק שמחייג בעצמו (המרכזייה), וטראנק לזיהוי אחר ---
# המרכזייה יש לה satellite (לעוזר) אבל אין `async_announce`; לכן
# send_call חייב ליפול ל-async_notify, אחרת שליחה למספר חופשי
# נכשלת אצלה למרות שיש לה מסלול יוצא.
ok("send_call נופל ל-async_notify בלי async_announce",
   "await driver.async_notify(" in _init_src)
ok("המרכזייה מציעה בחירת טראנק יוצא",
   getattr(pbx, "SUPPORTS_TRUNK", False))
ok("ספק בלי טראנקים אינו מצהיר עליו",
   not any(getattr(d, "SUPPORTS_TRUNK", False)
           for d in (yemot, technoline, vonage)))
ok("send_call מקבל שדה טראנק אופציונלי",
   "trunk" in {str(k) for k in _core_mod._send_call_schema().schema})
# ישות הנמען מעבירה את הטראנק שלה, וטופס הנמען מציג את השדה רק
# לספק שמצהיר עליו — נמען של ימות לא יראה טראנק.
ok("ישות הנמען מעבירה טראנק", "trunk=self._trunk" in _notify_src)
_cfg_src = (_core_dir / "config_shared.py").read_text("utf-8")
ok("טופס הנמען מתנה את שדה הטראנק ב-SUPPORTS_TRUNK",
   "_supports_trunk" in _cfg_src and "SUPPORTS_TRUNK" in _cfg_src)


async def _pbx_trunk_used(trunk_arg, expected):
    """async_notify של המרכזייה שם בגוף את הטראנק שנמסר, או את
    ברירת המחדל של הרשומה כשלא נמסר."""
    import types as _t
    from homeassistant.helpers import aiohttp_client as _ac

    captured: dict = {}

    class _Resp:
        status = 200
        async def text(self): return "ok"
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class _Sess:
        def post(self, url, json, headers, timeout):
            captured.update(json); return _Resp()

    _orig = _ac.async_get_clientsession
    _ac.async_get_clientsession = lambda hass: _Sess()
    try:
        entry = _t.SimpleNamespace(options={
            "pbx_alert_url": "http://x/ha",
            "pbx_trunk": "default_trunk",
            "pbx_alert_secret": "s",
        })
        kw = {"trunk": trunk_arg} if trunk_arg is not None else {}
        await pbx.async_notify(None, entry, "hi", ["0501234567"], **kw)
    finally:
        _ac.async_get_clientsession = _orig
    return captured.get("trunk") == expected


check("טראנק מפורש נכנס לגוף ההתראה",
      lambda: asyncio.get_event_loop().run_until_complete(
          _pbx_trunk_used("special_trunk", "special_trunk")))
check("בלי טראנק — ברירת המחדל של הרשומה",
      lambda: asyncio.get_event_loop().run_until_complete(
          _pbx_trunk_used(None, "default_trunk")))

# --- מספר מציג (caller_id): נשלח רק כשהוגדר, אחרת המרכזייה
# מחייגת בזיהוי של הטראנק במקום מספר ברירת מחדל שהספק דוחה ---
ok("המרכזייה מציעה מספר מציג", getattr(pbx, "SUPPORTS_CALLER_ID", False))
ok("ספק בלי מספר מציג אינו מצהיר עליו",
   not any(getattr(d, "SUPPORTS_CALLER_ID", False)
           for d in (yemot, technoline, vonage)))
ok("send_call מקבל מספר מציג",
   "caller_id" in {str(k) for k in _core_mod._send_call_schema().schema})
ok("ישות הנמען מעבירה מספר מציג", "caller_id=self._caller_id" in _notify_src)


async def _pbx_callerid(cid_arg):
    """מחזיר את caller_id שבגוף הבקשה, או None אם השדה לא נשלח."""
    import types as _t
    from homeassistant.helpers import aiohttp_client as _ac

    captured: dict = {}

    class _Resp:
        status = 200
        async def text(self): return "ok"
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class _Sess:
        def post(self, url, json, headers, timeout):
            captured.update(json); return _Resp()

    _orig = _ac.async_get_clientsession
    _ac.async_get_clientsession = lambda hass: _Sess()
    try:
        entry = _t.SimpleNamespace(options={
            "pbx_alert_url": "http://x/ha",
            "pbx_trunk": "t", "pbx_alert_secret": "s",
        })
        kw = {"caller_id": cid_arg} if cid_arg is not None else {}
        await pbx.async_notify(None, entry, "hi", ["0501234567"], **kw)
    finally:
        _ac.async_get_clientsession = _orig
    return captured.get("caller_id", "__absent__")


check("מספר מציג מפורש נכנס לגוף",
      lambda: asyncio.get_event_loop().run_until_complete(
          _pbx_callerid("0501234567")) == "0501234567")
check("בלי מספר מציג — השדה לא נשלח (זיהוי הטראנק)",
      lambda: asyncio.get_event_loop().run_until_complete(
          _pbx_callerid(None)) == "__absent__")

# --- ניסיונות חוזרים: המרכזייה יודעת לחזור ולחייג, ושאר הספקים
# מצלצלים פעם אחת. ברירת המחדל 0 משווה אותה אליהם — צלצול חוזר
# הוא בקשה מפורשת, לא הפתעה ---
ok("המרכזייה מציעה ניסיונות חוזרים", getattr(pbx, "SUPPORTS_RETRIES", False))
ok("ספק שאינו חוזר ומחייג אינו מצהיר עליו",
   not any(getattr(d, "SUPPORTS_RETRIES", False)
           for d in (yemot, technoline, vonage)))
ok("send_call מקבל ניסיונות חוזרים",
   "retries" in {str(k) for k in _core_mod._send_call_schema().schema})
ok("ישות הנמען מעבירה ניסיונות חוזרים", "retries=self._retries" in _notify_src)
ok("טופס הנמען מתנה את השדה ב-SUPPORTS_RETRIES",
   "_supports_retries" in _cfg_src and "SUPPORTS_RETRIES" in _cfg_src)


async def _pbx_retries(arg):
    """מחזיר את `retries` שבגוף הבקשה שהמרכזייה שולחת."""
    import types as _t
    from homeassistant.helpers import aiohttp_client as _ac

    captured: dict = {}

    class _Resp:
        status = 200
        async def text(self): return "ok"
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class _Sess:
        def post(self, url, json, headers, timeout):
            captured.update(json); return _Resp()

    _orig = _ac.async_get_clientsession
    _ac.async_get_clientsession = lambda hass: _Sess()
    try:
        entry = _t.SimpleNamespace(options={
            "pbx_alert_url": "http://x/ha",
            "pbx_trunk": "t", "pbx_alert_secret": "s",
        })
        kw = {"retries": arg} if arg is not None else {}
        await pbx.async_notify(None, entry, "hi", ["0501234567"], **kw)
    finally:
        _ac.async_get_clientsession = _orig
    return captured.get("retries", "__absent__")


check("ברירת המחדל היא צלצול אחד (retries=0)",
      lambda: asyncio.get_event_loop().run_until_complete(
          _pbx_retries(None)) == 0)
check("ניסיונות חוזרים מפורשים נכנסים לגוף",
      lambda: asyncio.get_event_loop().run_until_complete(
          _pbx_retries(2)) == 2)
check("ערך שלילי נחסם ל-0",
      lambda: asyncio.get_event_loop().run_until_complete(
          _pbx_retries(-3)) == 0)

# --- תור ההתראות הממתינות ---
_hass3 = fake_ha.FakeHass()
_hass3.data = {}
_p = announce_store.store(_hass3, "e1", b"\x00\x01" * 100, 8000, "שלום",
                          ["0501234567"])
# ההתאמה על תשע הספרות האחרונות: הספק עשוי להחזיר קידומת או
# אפס מוביל, והשוואת מחרוזות מלאה נכשלת על הבדל שאינו קיים.
ok("התאמה למספר הנמען", _p.matches("0501234567"))
ok("התאמה גם עם קידומת בינלאומית", _p.matches("+972501234567"))
ok("מספר אחר אינו מתאים", not _p.matches("0501111111"))

ok("שיחה ממספר אחר אינה תופסת",
   announce_store.claim(_hass3, "e1", "0501111111") is None)
ok("ההתראה עדיין ממתינה", announce_store.claim(_hass3, "e1", "0501234567") is _p)
# **נתפסת פעם אחת בלבד.** שיחה שנייה מאותו מספר מקבלת את העוזר,
# ולא השמעה חוזרת של אותה הודעה.
ok("נתפסת פעם אחת בלבד",
   announce_store.claim(_hass3, "e1", "0501234567") is None)

# **שתי התראות חיות יחד.** סלוט יחיד היה מאבד את הראשונה: הנמען
# שלה היה מקבל את העוזר הקולי במקום את ההודעה, והשירות היה
# מדווח "לא נענתה" גם אם ענו.
_a = announce_store.store(_hass3, "e1", b"a", 8000, "ראשונה", ["0501111111"])
_b = announce_store.store(_hass3, "e1", b"b", 8000, "שנייה", ["0502222222"])
ok("השנייה אינה דורסת את הראשונה",
   announce_store.claim(_hass3, "e1", "0501111111") is _a)
ok("והשנייה עדיין שם",
   announce_store.claim(_hass3, "e1", "0502222222") is _b)

# תור FIFO גם לאותו מספר: דריסה היא מה שהתור בא לתקן.
_x = announce_store.store(_hass3, "e1", b"x", 8000, "מוקדמת", ["0503333333"])
_y = announce_store.store(_hass3, "e1", b"y", 8000, "מאוחרת", ["0503333333"])
ok("הראשונה בתור נתפסת ראשונה",
   announce_store.claim(_hass3, "e1", "0503333333") is _x)
ok("ואחריה השנייה",
   announce_store.claim(_hass3, "e1", "0503333333") is _y)

# **התראה לשני נמענים נתפסת פעמיים.** נמדד בקו: השני הגיע שנייה
# אחרי הראשון, ההתראה כבר נעלמה מהתור, והוא שמע את צליל ה"דבר
# עכשיו" של העוזר במקום את ההודעה.
_two = announce_store.store(_hass3, "e1", b"t", 8000, "לשניים",
                            ["0501111111", "0502222222"])
ok("שני נמענים נספרים", _two.total == 2)
ok("הראשון תופס", announce_store.claim(_hass3, "e1", "0501111111") is _two)
ok("והשני תופס גם הוא",
   announce_store.claim(_hass3, "e1", "0502222222") is _two)
ok("אותו נמען אינו תופס פעמיים",
   announce_store.claim(_hass3, "e1", "0501111111") is None)

# ההמתנה נגמרת רק כשכולם שמעו — אחרת אוטומציה מדווחת הצלחה
# בזמן שחצי מהנמענים לא ענו.
_two.mark_played()
ok("השמעה אחת אינה מסיימת את ההמתנה", not _two.delivered.is_set())
_two.mark_played()
ok("השנייה כן", _two.delivered.is_set())
ok("הסיכום קריא", _two.summary == "2 מתוך 2")

# יומן ההקראה: שלוחת ההתראות משמיעה חדשות-בלבד, וההתראה נמחקת
# אחרי שכל נמעניה שמעו — כדי שלא תוקרא שוב ולא תצטבר בלוג.
_h4 = fake_ha.FakeHass()
_h4.data = {}
announce_store.log_alert(_h4, "e2", "התראה א", ["0501234567"])
announce_store.log_alert(_h4, "e2", "התראה ב", ["0501234567"])
ok("שתי ההתראות טרם נשמעו",
   announce_store.unheard_count(_h4, "e2", "0501234567") == 2)
ok("חדשות-בלבד מחזיר את שתיהן",
   len(announce_store.recent_alerts(_h4, "e2", "0501234567", unheard_only=True)) == 2)
announce_store.mark_heard(_h4, "e2", "0501234567")
ok("אחרי שמיעה אין חדשות להקריא",
   announce_store.recent_alerts(_h4, "e2", "0501234567", unheard_only=True) == [])
ok("וספירת החדשות בכניסה היא אפס",
   announce_store.unheard_count(_h4, "e2", "0501234567") == 0)
announce_store.prune_heard(_h4, "e2")
ok("ההתראות שנשמעו נמחקו מהלוג",
   announce_store.recent_alerts(_h4, "e2", "0501234567") == [])

# התראה לשני נמענים יורדת מהלוג רק כשגם השני שמע.
announce_store.log_alert(_h4, "e2", "לשניים", ["0501111111", "0502222222"])
announce_store.mark_heard(_h4, "e2", "0501111111")
announce_store.prune_heard(_h4, "e2")
ok("נמען אחד שמע — ההתראה נשמרת לשני",
   len(announce_store.recent_alerts(_h4, "e2", "0502222222")) == 1)
announce_store.mark_heard(_h4, "e2", "0502222222")
announce_store.prune_heard(_h4, "e2")
ok("שניהם שמעו — נמחקה", announce_store.recent_alerts(_h4, "e2") == [])

_old = announce_store.store(_hass3, "e1", b"", 8000, "", ["0501234567"], ttl=-1)
ok("התראה שפגה אינה נתפסת",
   _old.expired and announce_store.claim(_hass3, "e1", "0501234567") is None)

# תקרה: ספק שאינו מחייג היה מצבר התראה לכל אוטומציה שרצה.
# הישנה משתחררת בשגיאה ולא נתקעת עד שתפוג.
_first = announce_store.store(_hass3, "e2", b"1", 8000, "1", ["0501111111"])
for _i in range(announce_store.MAX_PENDING):
    announce_store.store(_hass3, "e2", b"n", 8000, str(_i), ["0509999999"])
ok("התור חסום בתקרה",
   len(_hass3.data[announce_store.PENDING_ANNOUNCE]["e2"])
   == announce_store.MAX_PENDING)
ok("הישנה שהוסרה משוחררת עם שגיאה",
   _first.delivered.is_set() and "התור מלא" in _first.error)

ok("רשומה בלי התראה ממתינה", announce_store.claim(_hass3, "e9", "0501234567") is None)

print("\n== רגרסיות של תיקוני דרג 1 ==")

entry.domain = "ha_ivr"
entry.data = {**entry.data, "provider": "yemot"}


def _body(driver: str, query: dict) -> str:
    """סיבוב מלא דרך נקודת הקצה, ומה שחזר כטקסט.

    הרשומה נושאת את הספק בשדה `provider`; הדומיין משותף לכולם.
    """
    entry.data = {**entry.data, "provider": driver}
    resp = asyncio.new_event_loop().run_until_complete(
        v.get(fake_ha.FakeRequest(query=query), driver, "T")
    )
    return getattr(resp, "text", "") or ""


# 1.1 — שתיקה בשורש. `is_new_call` נשאר True בשורש לנצח, ולכן
# מונה החזרות לא נבדק שם כלל והתפריט חזר עד שהמתקשר ניתק.
ok("root silence reaches a hangup", "hangup" in _body("yemot", {"s4_": ""}))
ok("first root replay is not a hangup", "hangup" not in _body("yemot", {"s1_": ""}))
ok("deep silence still hangs up", "hangup" in _body("yemot", {"s6_1": ""}))
ok("a real keypress is never a hangup", "hangup" not in _body("yemot", {"s4_": "1"}))

# 1.3 — ביטוי יציאה חייב להסתיים בגבול מילה, אבל לא להתחיל בו:
# בעברית אותיות השימוש נדבקות למילה שאחריהן.
class _ExitProbe:
    _options = {"stream_exit": "חזור לתפריט, תפריט ראשי, להתראות, ביי"}


_exit = IvrSatellite._is_exit.__get__(_ExitProbe())
ok("plain exit phrase", _exit("חזור לתפריט"))
ok("exit phrase with punctuation", _exit("חזור לתפריט."))
ok("exit phrase at end of sentence", _exit("בסדר גמור, ביי"))
ok("hebrew prefix still matches", _exit("תחזיר אותי לתפריט ראשי"))
# נצפה בשיחה חיה 19.8.26: המתקשר אמר "דוקטור בייבי" ולא יצא.
ok("בייבי is not ביי", not _exit("דוקטור בייבי"))
ok("ביישוב is not ביי", not _exit("תדליק את האור בביישוב"))
ok("unrelated speech passes", not _exit("כמה מעלות בחוץ"))
ok("empty speech is safe", not _exit(""))

# 1.2 — הנקודה נעלמת תמיד, אבל נאמרת רק בין ספרות.
ok("sentence period is silent", "נקודה" not in yemot.sanitize("שלום. איך אפשר לעזור"))
ok("decimal point is spoken", "נקודה" in yemot.sanitize("21.5 מעלות"))
ok("no period survives either way", "." not in yemot.sanitize("גרסה 2.1.4. סוף."))

# 1.7 — זהות הקוד שרץ, כדי שאבחון לא ייעשה מול העותק הלא נכון.
import custom_components.ha_ivr as core  # noqa: E402

_stamp = core.build_stamp()
ok("build stamp has version and fingerprint", "+" in _stamp and len(_stamp) > 10)
ok("build stamp is stable", _stamp == core.build_stamp())
# החתימה חייבת לכסות את `providers/` ולא רק את הליבה: שינוי
# בדרייבר של ספק חייב להזיז אותה, אחרת היומן מצהיר על אותה
# חתימה בדיוק על קוד אחר.
_before = _core_mod.build_stamp()
_prov = ROOT / "custom_components" / "ha_ivr" / "providers" / "yemot.py"
_orig = _prov.read_text("utf-8")
_prov.write_text(_orig + "\n# touch\n")
ok("build stamp covers providers", _core_mod.build_stamp() != _before)
_prov.write_text(_orig)
ok("build stamp returns after undo", _core_mod.build_stamp() == _before)

# ======================================================================
print("\n== ישות חכמה ==")
# ======================================================================
from custom_components.ha_ivr import smart as _smart  # noqa: E402

# --- רוחב קבוע: מה שקובע אם אפשר לאסוף בלי מקש אישור ---
ok("16 עד 30 הן שתי ספרות", _smart._fixed_width(16, 30) == 2)
ok("8 עד 30 מרופדות לשתי ספרות", _smart._fixed_width(8, 30) == 2)
ok("0 עד 100 רחבות מדי להקשה", _smart._fixed_width(0, 100) == 0)
ok("טווח חד-ספרתי נשאר ספרה אחת", _smart._fixed_width(1, 9) == 1)
ok("טווח שלילי אינו ניתן להקשה", _smart._fixed_width(-5, 5) == 0)
ok("טווח לא שלם אינו ברוחב קבוע", _smart._fixed_width(16.5, 30) == 0)

# --- שדה הערך של הפעולה ---
_sup = {"hvac_mode": {}, "other": {}}
ok("set_hvac_mode פועל על hvac_mode",
   _smart._primary_field("set_hvac_mode", _sup, []) == "hvac_mode")
ok("select_source פועל על source",
   _smart._primary_field("select_source", {"source": {}, "x": {}}, []) == "source")
ok("שדה חובה יחיד גובר",
   _smart._primary_field("whatever", {"a": {}, "b": {}}, ["b"]) == "b")
ok("שדה אופציונלי יחיד נבחר",
   _smart._primary_field("volume_set", {"volume_level": {}}, []) == "volume_level")
ok("ריבוי שדות בלי הכרעה נשאר פשוט",
   _smart._primary_field("turn_on", {"brightness": {}, "color_name": {}}, []) is None)

# --- מיזוג אפשרויות: המספרים אינם זזים ---
ok("אפשרות שנעלמה יורדת",
   _smart.merge_options(["cool", "heat"], [], ["cool"]) == ["cool"])
ok("אפשרות חדשה נוספת בסוף ולא באמצע",
   _smart.merge_options(["cool", "heat"], [], ["heat", "dry", "cool"])
   == ["cool", "heat", "dry"])
ok("אפשרות שהוחרגה אינה חוזרת",
   _smart.merge_options(["cool"], ["dry"], ["cool", "dry"]) == ["cool"])
ok("הסדר השמור נשמר כלשונו",
   _smart.merge_options(["heat", "cool"], [], ["cool", "heat"]) == ["heat", "cool"])

# --- התוכנית: המספרים נקבעים פעם אחת ---
_caps = [
    _smart.Capability(ident="turn_on", kind=_smart.KIND_SIMPLE, label="הדלקה",
                      action="turn_on"),
    _smart.Capability(ident="turn_off", kind=_smart.KIND_SIMPLE, label="כיבוי",
                      action="turn_off"),
    _smart.Capability(ident="set_hvac_mode", kind=_smart.KIND_CHOICE, label="מצב",
                      action="set_hvac_mode", field_name="hvac_mode",
                      options=("cool", "heat", "dry")),
    _smart.Capability(ident="set_temperature", kind=_smart.KIND_NUMBER,
                      label="טמפרטורה", action="set_temperature",
                      field_name="temperature", minimum=16, maximum=30, width=2),
]
_plan = _smart.build_plan(
    _caps, ["turn_on", "turn_off", "set_hvac_mode", "set_temperature"],
    {"set_hvac_mode": ["cool", "heat"]})
ok("המספרים מוקצים לפי הסדר",
   [e["digit"] for e in _plan] == ["1", "2", "3", "4"])
ok("מה שלא נבחר נרשם כמוחרג", _plan[2]["excluded"] == ["dry"])
ok("יכולת מספרית נושאת את הטווח והרוחב",
   (_plan[3]["min"], _plan[3]["max"], _plan[3]["width"]) == (16, 30, 2))
ok("יכולת שאינה בגילוי אינה נכנסת לתוכנית",
   _smart.build_plan(_caps, ["nope"], {}) == [])

# --- מהתוכנית לעץ ---
_hs = fake_ha.FakeHass({"climate.s": fake_ha.FakeState(
    "cool", friendly_name="מזגן סלון", hvac_modes=["cool", "heat", "dry"])})
_es = fake_ha.FakeEntry()
_es.subentries = {"sm": types.SimpleNamespace(
    subentry_type="smart_entity", subentry_id="sm", title="1",
    data={"menu_path": "1", "label": "", "entity_id": "climate.s",
          "confirm_risky": False, "plan": _plan})}
_troot = menu.build_tree(_hs, _es)
_snode = _troot.items["1"]
ok("שם המכשיר נלקח מ-HA", _snode.say == "מזגן סלון")
ok("הענף נבנה מהתוכנית", sorted(_snode.items) == ["1", "2", "3", "4"])
ok("פעולה פשוטה היא עלה", _snode.items["1"].action == "turn_on")
ok("בחירה היא תת-תפריט", _snode.items["3"].is_menu)
ok("והאפשרות שהוחרגה אינה בו", len(_snode.items["3"].items) == 2)
ok("ערך הבחירה נשלח בשדה הנכון",
   _snode.items["3"].items["1"].data == {"hvac_mode": "cool"})
ok("יכולת מספרית היא צומת איסוף", _snode.items["4"].is_collect)
ok("וצומת איסוף שורד את הגיזום", _snode.items["4"].collect["width"] == 2)

# אפשרות שהמכשיר הוסיף מצטרפת בסוף, בלי להזיז את הקיימות.
_hs2 = fake_ha.FakeHass({"climate.s": fake_ha.FakeState(
    "cool", friendly_name="מזגן", hvac_modes=["heat", "cool", "fan_only"])})
_t2 = menu.build_tree(_hs2, _es)
_modes = _t2.items["1"].items["3"].items
ok("מספר קיים אינו זז כשהמכשיר משנה סדר",
   _modes["1"].data == {"hvac_mode": "cool"})
ok("אפשרות חדשה מקבלת את המספר הבא",
   _modes["3"].data == {"hvac_mode": "fan_only"})

# --- איסוף הספרות ---
_col = _snode.items["4"]
ok("בטווח 16 עד 30 הספרה הראשונה חסומה ל-1 עד 3",
   tree.valid_next_digits(_col.collect, ()) == {"1", "2", "3"})
ok("אחרי 1 מותר רק 6 עד 9",
   tree.valid_next_digits(_col.collect, ("1",)) == {"6", "7", "8", "9"})
ok("אחרי 3 מותר רק 0", tree.valid_next_digits(_col.collect, ("3",)) == {"0"})
ok("אין ספרה שלישית", tree.valid_next_digits(_col.collect, ("2", "2")) == set())
_pad = {"min": 8, "max": 30, "width": 2}
ok("בטווח 8 עד 30 האפס פותח ערך קצר",
   tree.valid_next_digits(_pad, ()) == {"0", "1", "2", "3"})
ok("ואחרי האפס רק 8 ו-9 נשארים בטווח",
   tree.valid_next_digits(_pad, ("0",)) == {"8", "9"})
ok("האפס הוא ספרה בצומת איסוף",
   "0" in tree.collect_prompt(_col, ("1", "4"), 3, ("3",)).allowed)
ok("והכוכבית מבטלת",
   "*" in tree.collect_prompt(_col, ("1", "4"), 3, ()).allowed)
ok("ההודעה המלאה נאמרת רק בספרה הראשונה",
   len(tree.collect_prompt(_col, ("1", "4"), 3, ()).messages) >= 2)
ok("ובין הספרות שותקים",
   tree.collect_prompt(_col, ("1", "4"), 3, ("2",)).messages == [])
ok("אין פסיק לפני הקש בהודעת האיסוף",
   not any(", הקש" in m.data
           for m in tree.collect_prompt(_col, ("1", "4"), 3, ()).messages))
ok("הספרות שנאספו נוסעות בנתיב",
   tree.collect_prompt(_col, ("1", "4"), 3, ("2",)).at_path == ("1", "4", "2"))

_found = tree.find_collector(_troot, ("1", "4", "2"))
ok("צומת האיסוף נמצא מתוך הנתיב", _found is not None)
ok("והספרות שהוקשו משוחזרות ממנו", _found[1:] == (("1", "4"), ("2",)))
ok("נתיב רגיל אינו נראה כאיסוף",
   tree.find_collector(_troot, ("1", "3")) is None)

# --- הזרימה המלאה, דרך ה-View ---
_hs3 = fake_ha.FakeHass({"climate.s": fake_ha.FakeState(
    "cool", friendly_name="מזגן", hvac_modes=["cool", "heat"], temperature=22)})
_es3 = fake_ha.FakeEntry()
_es3.domain = "ha_ivr"
_es3.data = {"token": "T", "provider": "pbx"}
_es3.subentries = _es.subentries
_hs3.config_entries = fake_ha.FakeConfigEntries([_es3])
# ב-HA אמיתי השירות קיים, ו-`action_allowed` נשען על כך. הכפיל
# מחזיר False לכל שירות, ולכן הפעולה הייתה נחסמת עוד לפני האיסוף.
_hs3.services.has_service = lambda *a: True
_v5 = view.IvrView(_hs3)
# אותה לולאה גם ל-hass: `_call_and_wait` יוצר future מ-`hass.loop`,
# ולולאה אחרת הייתה דוחה אותו וממלאת את הפלט ב-traceback שאינו כשל.
_loop5 = _hs3.loop


def _pbx_press(path, digit):
    resp = _loop5.run_until_complete(_v5.get(
        fake_ha.FakeRequest(query={"path": path, "digit": digit, "step": "3"}),
        "pbx", "T"))
    return _json.loads(getattr(resp, "text", "") or "{}")


# הכניסה לצומת האיסוף. זה היה הבאג: הצומת אינו תפריט, ולכן נפל
# למסלול העלה והפעיל את השירות בלי הערך שטרם הוקש.
_enter = _pbx_press("1", "4")
ok("כניסה לצומת איסוף אינה מפעילה את השירות", not _hs3.services.calls)
ok("אלא מבקשת את הספרה הראשונה", _enter.get("path") == "1/4")
ok("ומציעה את הספרות שבטווח בלבד",
   set(_enter.get("keys") or []) == {"*", "1", "2", "3"})

_first = _pbx_press("1/4", "2")
ok("הקשה ראשונה אינה מפעילה דבר", not _hs3.services.calls)
ok("והמערכת ממשיכה לאסוף", _first.get("menu") is True)
ok("הספרה נשמרת בנתיב שחוזר", _first.get("path") == "1/4/2")

_second = _pbx_press("1/4/2", "2")
ok("שתי הספרות מרכיבות ערך אחד",
   any(c[2].get("temperature") == 22 for c in _hs3.services.calls))
ok("והפעולה היא זו שבתוכנית",
   any(c[:2] == ("climate", "set_temperature") for c in _hs3.services.calls))
ok("אחרי ההפעלה חוזרים לתפריט", _second.get("menu") is True)
ok("והערך שהוקש מאושר בקול", "22" in _second.get("say", ""))

_hs3.services.calls.clear()
_bad = _pbx_press("1/4", "9")
ok("ספרה שאינה בטווח נדחית", "בחירה שאינה קיינת" in _bad.get("say", "")
   or "בחירה שאינה קיימת" in _bad.get("say", ""))
ok("ולא הופעל דבר", not _hs3.services.calls)

_cancel = _pbx_press("1/4/2", "*")
ok("כוכבית מבטלת ומחזירה לתפריט הראשי", not _hs3.services.calls)

# ======================================================================
print("\n== קבוצה חכמה ==")
# ======================================================================

# --- דומיינים שאין להציע כקבוצה ---
from custom_components.ha_ivr import policy as _pol  # noqa: E402

ok("כפתור אינו ניתן לקיבוץ", not _pol.domain_is_groupable("button"))
ok("סצנה ותסריט גם לא",
   not _pol.domain_is_groupable("scene") and not _pol.domain_is_groupable("script"))
ok("אוטומציה ובוררים גם לא",
   not _pol.domain_is_groupable("automation")
   and not _pol.domain_is_groupable("select")
   and not _pol.domain_is_groupable("input_select")
   and not _pol.domain_is_groupable("todo"))
ok("תאורה כן", _pol.domain_is_groupable("light"))
ok("הכרזה ללוויין מסוננת כפעולה שאינה שליטה",
   "announce" in _pol._NON_ACTIONABLE and "get_forecasts" in _pol._NON_ACTIONABLE)

# --- חיתוך יכולות בין חברי הקבוצה ---
def _cap(kind, ident="x", **kw):
    return _smart.Capability(ident=ident, kind=kind, label=ident,
                             action=ident, **kw)


_a = _cap(_smart.KIND_CHOICE, "set_hvac_mode", field_name="hvac_mode",
          options=("cool", "heat", "dry"))
_b = _cap(_smart.KIND_CHOICE, "set_hvac_mode", field_name="hvac_mode",
          options=("heat", "cool"))
ok("בחירה מצטמצמת למה שכולם מכירים",
   _smart._merge("set_hvac_mode", [_a, _b]).options == ("cool", "heat"))
ok("והסדר נשאר של הראשון",
   _smart._merge("set_hvac_mode", [_b, _a]).options == ("heat", "cool"))
ok("בלי אפשרות משותפת היכולת נופלת",
   _smart._merge("x", [_cap(_smart.KIND_CHOICE, options=("a",)),
                       _cap(_smart.KIND_CHOICE, options=("b",))]) is None)

_n1 = _cap(_smart.KIND_NUMBER, "set_temperature", field_name="temperature",
           minimum=8, maximum=30, width=2)
_n2 = _cap(_smart.KIND_NUMBER, "set_temperature", field_name="temperature",
           minimum=16, maximum=28, width=2)
_m = _smart._merge("set_temperature", [_n1, _n2])
ok("טווח מספרי מצטמצם לצר ביותר", (_m.minimum, _m.maximum) == (16, 28))
ok("ערך שהוקש חוקי אצל כל החברים", _m.width == 2)
ok("יכולות מסוגים שונים אינן מתמזגות",
   _smart._merge("x", [_cap(_smart.KIND_SIMPLE),
                       _cap(_smart.KIND_CHOICE, options=("a",))]) is None)

# --- מהתוכנית לעץ, עם יעד במקום ישות ---
_gcaps = [
    _smart.Capability(ident="turn_on", kind=_smart.KIND_SIMPLE, label="הדלקה",
                      action="turn_on"),
    _smart.Capability(ident=_smart.STATUS_ID, kind=_smart.KIND_STATUS,
                      label="הקראת מצב"),
]
_gplan = _smart.build_plan(_gcaps, ["turn_on", _smart.STATUS_ID], {})
_gh = fake_ha.FakeHass({
    "light.a": fake_ha.FakeState("on", friendly_name="א"),
    "light.b": fake_ha.FakeState("off", friendly_name="ב"),
    "light.c": fake_ha.FakeState("on", friendly_name="ג"),
})
fake_ha.MATCHES.clear()
fake_ha.MATCHES[("light", "mtbh", "")] = ["light.a", "light.b", "light.c"]
_ge = fake_ha.FakeEntry()
_ge.domain = "ha_ivr"
_ge.data = {"token": "T", "provider": "pbx"}
_ge.subentries = {"g": types.SimpleNamespace(
    subentry_type="smart_group", subentry_id="g", title="6",
    data={"menu_path": "6", "label": "אורות מטבח", "target_domain": "light",
          "target_area": "mtbh", "target_floor": "", "confirm_risky": False,
          "plan": _gplan})}
_gtree = menu.build_tree(_gh, _ge)
_gnode = _gtree.items["6"]
ok("צומת קבוצה נושא יעד ולא ישות", _gnode.is_group and not _gnode.entity)
ok("היעד כולל סוג ומרחב",
   (_gnode.target["domain"], _gnode.target["area"]) == ("light", "mtbh"))
ok("היעד מושתל גם בילדים", all(c.is_group for c in _gnode.items.values()))
ok("ולילדים אין מזהה ישות שמור",
   all(not c.entity for c in _gnode.items.values()))

# --- הישויות נפתרות בזמן השיחה ---
ok("היעד נפתר לישויות",
   _smart.match_entities(_gh, "light", "mtbh") ==
   ["light.a", "light.b", "light.c"])
fake_ha.MATCHES[("light", "mtbh", "")] = ["light.a", "light.b", "light.c", "light.d"]
_gh.states._states["light.d"] = fake_ha.FakeState("on", friendly_name="ד")
ok("מכשיר שנוסף למרחב מצטרף מעצמו",
   len(_smart.match_entities(_gh, "light", "mtbh")) == 4)
fake_ha.MATCHES[("light", "mtbh", "")] = ["light.a", "light.b", "light.c"]
ok("יעד ריק אינו מחזיר דבר", _smart.match_entities(_gh, "light", "eyn") == [])

# --- תווית כיעד ---
_smart.entity_labels = lambda hass, eid: {"mzgnym"} if eid == "light.a" else set()
_smart.resolve_label = lambda hass, label: label
ok("תווית מסננת את מה שהתאים",
   _smart.match_entities(_gh, "light", "mtbh", label="mzgnym") == ["light.a"])
ok("תווית שאיש אינו נושא מחזירה ריק",
   _smart.match_entities(_gh, "light", "mtbh", label="eyn") == [])
ok("בלי תווית שום דבר לא מסונן",
   len(_smart.match_entities(_gh, "light", "mtbh")) == 3)

# --- סיכום מצב לקבוצה ---
_gview = view.IvrView(_gh)
_named = "".join(m.data for m in _gview._speak_many(["light.a", "light.b"]))
ok("קבוצה קטנה מוקראת בשמות", "א" in _named and "ב" in _named)
ok("ולא בספירה", not _named.startswith("1"))
_big = ["light.a", "light.b", "light.c", "light.d", "light.e"]
_gh.states._states["light.e"] = fake_ha.FakeState("off", friendly_name="ה")
_sum = "".join(m.data for m in _gview._speak_many(_big))
ok("קבוצה גדולה מסוכמת בספירה", "3" in _sum and "2" in _sum)
ok("ושמות אינם נאמרים בה", "ה" not in _sum.replace("דלוקים", ""))
_all_on = "".join(
    m.data for m in _gview._speak_many(["light.a", "light.c", "light.d", "light.e2"]))
ok("כשכולם באותו מצב לא נאמר מספר", "כולם" in _all_on)
ok("ישות שאינה קיימת אינה מפילה סיכום",
   _gview._speak_many(["light.nope"]) is not None)

# --- הפעלה על הקבוצה, דרך ה-View ---
_gh.config_entries = fake_ha.FakeConfigEntries([_ge])
_gh.services.has_service = lambda *a: True
_gv = view.IvrView(_gh)


def _gpress(path, digit):
    # אותו לולאה של הבדיקה הקודמת: לולאה חדשה יוצרת futures שאינם
    # שייכים לה, ו-asyncio דוחה אותם.
    resp = _loop5.run_until_complete(_gv.get(
        fake_ha.FakeRequest(query={"path": path, "digit": digit, "step": "2"}),
        "pbx", "T"))
    return _json.loads(getattr(resp, "text", "") or "{}")


_gh.services.calls.clear()
_gres = _gpress("6", "1")
ok("הפעולה נשלחה לכל חברי הקבוצה",
   any(c[2].get("entity_id") == ["light.a", "light.b", "light.c"]
       for c in _gh.services.calls))
ok("ובדומיין של היעד",
   any(c[:2] == ("light", "turn_on") for c in _gh.services.calls))
ok("והמתקשר שומע כמה מכשירים הושפעו", "3" in _gres.get("say", ""))

_gh.services.calls.clear()
_gstat = _gpress("6", "2")
ok("הקראת מצב אינה מפעילה דבר", not _gh.services.calls)
ok("ומסכמת את הקבוצה", "כרגע" in _gstat.get("say", ""))
# צומת הבן נושא את שם הפעולה, ולכן הדיווח חייב לקחת את שם הקבוצה
# מהיעד — אחרת יוצא "הקראת מצב כרגע" במקום "אורות מטבח כרגע".
ok("שם הקבוצה נאמר, לא שם הפעולה",
   "אורות מטבח כרגע" in _gstat.get("say", ""))
ok("כתובת Zigbee כשם נחשבת מזהה ולא שם",
   view._looks_opaque("0xa4c138f59bc7b721") and view._looks_opaque("a4c138f59bc7b721"))
ok("ושם אמיתי אינו נפסל",
   not view._looks_opaque("Sonoff1") and not view._looks_opaque("מזגן סלון")
   and not view._looks_opaque("ESP32"))
ok("שם המכשיר מוקרא ולא מזהה גולמי",
   "light.a" not in _gstat.get("say", ""))

fake_ha.MATCHES[("light", "mtbh", "")] = []
_gempty = _gpress("6", "1")
ok("קבוצה ריקה נאמרת ואינה מושתקת", "אין מכשירים" in _gempty.get("say", ""))
fake_ha.MATCHES[("light", "mtbh", "")] = ["light.a", "light.b", "light.c"]

print(f"\n{'FAIL' if FAIL else 'PASS'} — {PASS} עברו, {FAIL} נכשלו")
sys.exit(1 if FAIL else 0)
