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

DRIVERS = (("yemot", yemot), ("technoline", technoline), ("vonage", vonage))

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
    technoline as _tl, vonage as _vg, yemot as _ym,
)
# **"עוזר קולי" הוצע כתווית ברירת מחדל לכל ספק**, כולל לימות
# שאין לו ערוץ סטרימינג כלל — כלומר הטופס הציע שם למשהו שאינו
# קיים אצלו.
_cfg5 = (_core_dir / "config_shared.py").read_text("utf-8")
ok("אין תווית ברירת מחדל למעבר",
   'label_default="עוזר קולי"' not in _cfg5)

# **משמעות היעד שונה בין הספקים.** מזהה שלוחה אצל אחד, ולא
# בשימוש כלל אצל אחר. תיאור קבוע היה נכון לאחד ושגוי לשאר.
for _d5 in (_ym, _tl, _vg):
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
    technoline as _tl, vonage as _vg, yemot as _ym,
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
    technoline as _tl, vonage as _vg, yemot as _ym,
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
   set(registry.registered()) == {"technoline", "vonage", "yemot"})
_provs.ensure_registered()
ok("קריאה חוזרת אינה מכפילה",
   len(registry.registered()) == 3)

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
ok("שלושתם רשומים", registry.registered() == ["technoline", "vonage", "yemot"])
# המרשם עונה על מה שהיו רשימות קשיחות ב-const: מי קיים, למי יש
# סטרימינג, ואיך קוראים לו.
ok("שאילתת הסטרימינג על המרשם",
   {d.DRIVER_ID for d in registry.with_stream()} == {"technoline", "vonage"})
ok("שאילתה על כל הדרייברים",
   {d.DRIVER_ID for d in registry.all_drivers()}
   == {"technoline", "vonage", "yemot"})
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

print(f"\n{'FAIL' if FAIL else 'PASS'} — {PASS} עברו, {FAIL} נכשלו")
sys.exit(1 if FAIL else 0)
