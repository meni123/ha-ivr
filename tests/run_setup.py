"""טעינה ופריקה, reauth ו-reconfigure, המיגרציה לגרסה 1.4, והאבחון.

רץ מול ה-HA המזויף, כמו `run_live.py`.

python3 tests/run_setup.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_ha  # noqa: E402

fake_ha.install()

import custom_components.ha_ivr as core  # noqa: E402
from custom_components.ha_ivr import (  # noqa: E402
    config_flow as cf,
    diagnostics,
    dictation,
    i18n,
    registry,
    security,
)
from custom_components.ha_ivr import capabilities as caps  # noqa: E402
from custom_components.ha_ivr.providers import ensure_registered  # noqa: E402

PASS = FAIL = 0


def ok(name: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}")


LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)


def run(coro):
    return LOOP.run_until_complete(coro)


ensure_registered()
SIP = registry.get("sip")


class Bus(fake_ha.FakeBus):
    """אוטובוס עם מאזינים, כדי לספור מה נשאר רשום אחרי פריקה."""

    def __init__(self) -> None:
        super().__init__()
        self.listeners: list = []

    def async_listen(self, event_type, handler):
        item = (event_type, handler)
        self.listeners.append(item)

        def _remove() -> None:
            if item in self.listeners:
                self.listeners.remove(item)
        return _remove


def sip_entry(entry_id: str, user: str = "100", server: str = "sip.example.com",
              unique_id=None, state="loaded"):
    entry = fake_ha.FakeEntry(
        data={"provider": "sip", "token": "T"},
        options={"sip_server": server, "sip_username": user,
                 "sip_password": "pw", "sip_port": "5060"},
    )
    entry.entry_id = entry_id
    entry.unique_id = unique_id
    entry.title = f"SIP {user}"
    entry.state = state
    entry.minor_version = 3
    entry.version = 1
    return entry


# ----------------------------------------------------------------------
# מזהה הקו
# ----------------------------------------------------------------------

ok("מזהה קו SIP לפי החשבון, בלי פורט",
   cf._line_id(SIP, {"sip_server": "SIP.Example.com:5062", "sip_username": "7"})
   == "7@sip.example.com")
ok("חשבון ריק אינו מזהה", cf._line_id(SIP, {}) is None)
ok("ספק עם רשומה אחת אינו מקבל מזהה קו",
   cf._line_id(registry.get("yemot"), {"sip_username": "1"}) is None)
ok("הגרסה של הרשומה היא 1.4", cf.IvrConfigFlow.MINOR_VERSION == 4)

# ----------------------------------------------------------------------
# מיגרציה
# ----------------------------------------------------------------------

fake_ha.ISSUES.clear()
first = sip_entry("e1")
hass = fake_ha.FakeHass(entries=[first])
core._migrate_line_id(hass, first)
ok("מיגרציה: קו SIP מקבל unique_id", first.unique_id == "100@sip.example.com")
before = dict(first.options)
core._migrate_line_id(hass, first)
ok("מיגרציה אידמפוטנטית", first.unique_id == "100@sip.example.com"
   and first.options == before)

second = sip_entry("e2")
hass2 = fake_ha.FakeHass(entries=[first, second])
core._migrate_line_id(hass2, second)
ok("כפילות ישנה: המזהה לא נקבע", second.unique_id is None)
ok("ונפתחת תקלה duplicate_line",
   fake_ha.ISSUES.get("duplicate_line_e2", {}).get("translation_key") == "duplicate_line")

yemot = fake_ha.FakeEntry(data={"provider": "yemot", "token": "T"})
yemot.unique_id = None
core._migrate_line_id(fake_ha.FakeHass(entries=[yemot]), yemot)
ok("מיגרציה אינה נוגעת בספק אחר", yemot.unique_id is None)

migrated = sip_entry("e3", user="300")
mhass = fake_ha.FakeHass(entries=[migrated])
ok("async_migrate_entry מקדם ל-1.4", run(core.async_migrate_entry(mhass, migrated))
   and migrated.minor_version == 4 and migrated.unique_id == "300@sip.example.com")

# ----------------------------------------------------------------------
# reauth ו-reconfigure
# ----------------------------------------------------------------------


class Abort(Exception):
    pass


class Flow(cf.IvrConfigFlow):
    """הזרימה, עם מה שהבסיס של HA נותן — כמו ב-core."""

    def __init__(self, hass, entry, source) -> None:
        super().__init__()
        self.hass = hass
        self.source = source
        self.unique_id = None
        self._entry = entry

    def _get_reauth_entry(self):
        return self._entry

    def _get_reconfigure_entry(self):
        return self._entry

    async def async_set_unique_id(self, unique_id=None, **_kw):
        self.unique_id = unique_id

    def _abort_if_unique_id_mismatch(self, *, reason="unique_id_mismatch", **_kw):
        if self._entry.unique_id != self.unique_id:
            raise Abort(reason)

    def async_update_and_abort(self, entry, *, options=None, **_kw):
        # כמו ב-core: עדכון בלי טעינה; המאזין של הרשומה הוא שטוען.
        changed = self.hass.config_entries.async_update_entry(entry, options=options)
        self.updated = changed
        return {"type": "abort", "reason": f"{self.source}_successful"}

    def async_show_form(self, **kw):
        return {"type": "form", **kw}

    def async_abort(self, *, reason, **_kw):
        return {"type": "abort", "reason": reason}


async def _no_errors(hass, user_input):
    return {}


async def _auth_failed(hass, user_input):
    return {"sip_password": "sip_auth_failed"}


real_errors = SIP.async_menu_errors
SIP.async_menu_errors = _no_errors

entry = sip_entry("r1", unique_id="100@sip.example.com")
rhass = fake_ha.FakeHass(entries=[entry])
rhass.config_entries.reloads.clear()

flow = Flow(rhass, entry, "reauth")
form = run(flow.async_step_reauth({}))
ok("reauth מציג טופס עם הסיסמה בלבד",
   form["type"] == "form" and form["step_id"] == "reauth_confirm"
   and [str(k) for k in form["data_schema"].schema] == ["sip_password"])

flow = Flow(rhass, entry, "reauth")
result = run(flow.async_step_reauth_confirm({"sip_password": "pw"}))
ok("reauth בלי שינוי: טעינה אחת דרך async_schedule_reload",
   result["reason"] == "reauth_successful" and rhass.config_entries.reloads == ["r1"]
   and flow.updated is False)

rhass.config_entries.reloads.clear()
flow = Flow(rhass, entry, "reauth")
result = run(flow.async_step_reauth_confirm({"sip_password": "new"}))
ok("reauth עם שינוי: אין טעינה מהזרימה, המאזין טוען פעם אחת",
   result["reason"] == "reauth_successful" and rhass.config_entries.reloads == []
   and flow.updated is True and entry.options["sip_password"] == "new")

SIP.async_menu_errors = _auth_failed
flow = Flow(rhass, entry, "reauth")
result = run(flow.async_step_reauth_confirm({"sip_password": "bad"}))
ok("סיסמה שנדחית בניסיון נעצרת בטופס",
   result["type"] == "form" and result["errors"] == {"sip_password": "sip_auth_failed"}
   and entry.options["sip_password"] == "new")
SIP.async_menu_errors = _no_errors

flow = Flow(rhass, entry, "reconfigure")
try:
    run(flow.async_step_reconfigure({"sip_server": "sip.example.com",
                                     "sip_username": "999", "sip_password": "x"}))
    mismatch = False
except Abort as err:
    mismatch = str(err) == "unique_id_mismatch"
ok("reconfigure לחשבון אחר נעצר ב-unique_id_mismatch",
   mismatch and entry.options["sip_username"] == "100")

flow = Flow(rhass, entry, "reconfigure")
result = run(flow.async_step_reconfigure({"sip_server": "sip.example.com",
                                          "sip_username": "100", "sip_password": "z",
                                          "sip_port": "5070"}))
ok("reconfigure לאותו חשבון נשמר בלי טעינה ישירה",
   result["reason"] == "reconfigure_successful" and entry.options["sip_port"] == "5070"
   and rhass.config_entries.reloads == [])

form = run(Flow(rhass, entry, "reconfigure").async_step_reconfigure())
ok("reconfigure מציג את הערכים הנוכחיים",
   form["step_id"] == "reconfigure")

yentry = fake_ha.FakeEntry(data={"provider": "yemot", "token": "T"})
ok("reauth לספק בלי פרטי התחברות נסגר בהודעה",
   run(Flow(fake_ha.FakeHass(entries=[yentry]), yentry, "reauth")
       .async_step_reauth_confirm())["reason"] == "reauth_unsupported")
SIP.async_menu_errors = real_errors

# ----------------------------------------------------------------------
# המשותף לכל הרשומות: עולה פעם אחת, יורד עם האחרונה
# ----------------------------------------------------------------------

shass = fake_ha.FakeHass()
shass.bus = Bus()
shass.async_create_background_task = lambda coro, name=None: coro.close()
core._shared_start(shass)
listening = len(shass.bus.listeners)
core._shared_start(shass)
ok("המאזינים המשותפים נרשמים פעם אחת",
   listening > 0 and len(shass.bus.listeners) == listening)
ok("המטמון ו-i18n קיימים", caps.cache(shass) is not None and i18n.bound() is shass)
core._shared_stop(shass)
ok("אחרי עצירה אין מאזין רשום", shass.bus.listeners == [])
ok("והמטמון נמחק", caps.cache(shass) is None)

# ----------------------------------------------------------------------
# פריקה: כרטיסים וטיימרים
# ----------------------------------------------------------------------


class _Node:
    entity = "todo.list"
    action = "todo.add_item"
    dictate = {"field": "item", "max_length": 0}
    data = {}
    say = "רשימה"


class _Ctx:
    call_id = "c1"
    caller = "0501234567"


uhass = fake_ha.FakeHass()
uentry = sip_entry("u1")
uentry.subentries = {}
dictation.async_start(uhass, uentry, _Node(), "1", _Ctx())
ok("כרטיס נשמר", len(dictation._store(uhass)) == 1)
security.record_failure(uhass, "u1", "c1", "0501234567")
dictation.clear(uhass, "u1")
security.clear(uhass, "u1")
ok("ניקוי של הרשומה: אין כרטיס ואין טיימר",
   dictation._store(uhass) == {})
ok("ואין מונה חסימה", "u1" not in (uhass.data.get(security._DATA_KEY) or {}))

# הפריקה עצמה: הרשומה האחרונה מורידה גם את המשותף.
lhass = fake_ha.FakeHass()
lhass.bus = Bus()
lhass.async_create_background_task = lambda coro, name=None: coro.close()
lentry = sip_entry("l1")
lentry.subentries = {}
lhass.config_entries = fake_ha.FakeConfigEntries([lentry])
unloaded = []


async def _unload_platforms(entry, platforms):
    unloaded.append(list(platforms))


lhass.config_entries.async_unload_platforms_or_raise = _unload_platforms
lentry.runtime_data = core.IvrRuntime(driver=SIP, platforms=["sensor"])
core._shared_start(lhass)
dictation.async_start(lhass, lentry, _Node(), "1", _Ctx())
run(core.async_unload_entry(lhass, lentry))
ok("unload פורק את הפלטפורמות מ-runtime_data", unloaded == [["sensor"]])
ok("unload מנקה כרטיסים", dictation._store(lhass) == {})
ok("unload של האחרונה: אין מאזין ואין מטמון",
   lhass.bus.listeners == [] and caps.cache(lhass) is None)

# ----------------------------------------------------------------------
# אבחון
# ----------------------------------------------------------------------

sample = {
    "label": "להתקשר ל-050-123-4567",
    "uri": "sip:100@sip.example.com",
    "nested": ({"x": "+972501234567"}, {"sip:200@host": 1}),
    "set": {"0522222222"},
    "when": "2026-11-15 12:00:00",
    "ip": "192.168.1.20",
    "phones": ["0501111111"],
    "count": 12345678901,
    "entity": "light.kitchen_2",
}
clean = diagnostics.scrub(sample)
flat = str(clean)
ok("טלפון בטקסט חופשי מוסתר", "4567" not in clean["label"])
ok("כתובת SIP מוסתרת", "sip.example.com" not in clean["uri"])
ok("הסתרה בתוך tuple ובמפתח", "972501234567" not in flat and "sip:200" not in flat)
ok("הסתרה בתוך set", "0522222222" not in flat)
ok("מפתח אישי מוסתר כולו", clean["phones"] == diagnostics.REDACTED)
ok("תאריך, כתובת IP ומזהה ישות נשארים",
   clean["when"] == sample["when"] and clean["ip"] == sample["ip"]
   and clean["entity"] == sample["entity"])
ok("מספר שאינו מחרוזת נשאר", clean["count"] == sample["count"])
ok("ערכים קבועים בעץ מוצגים כשמות שדות בלבד",
   diagnostics._tree_summary({"say": "x", "data": {"message": "0501234567"}})["data"]
   == ["message"])

print()
print(f"{'PASS' if not FAIL else 'FAIL'} — {PASS} עברו, {FAIL} נכשלו")
sys.exit(1 if FAIL else 0)
