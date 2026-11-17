"""גילוי היכולות, קודים, הפעלה, שגיאות, הקראה ונעילה.

כל מה שנוסף כדי שהתפריט יציע רק מה שהמכשיר באמת יודע לעשות, ויגיד
למתקשר בדיוק מה קרה. רץ מול ה-HA המזויף, כמו `run_live.py`.

python3 tests/run_capabilities.py
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

from custom_components.ha_ivr import (  # noqa: E402
    call as call_mod,
    capabilities as caps,
    i18n,
    menu,
    security,
    smart,
    speech,
    tree,
)

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


def said(says) -> str:
    return " ".join(s.data for s in says)


# ======================================================================
print("\n== מסנני היעד והשדות, כמו ב-core ==")
# ======================================================================

COVER_POS = 4
LOCK_OPEN = 1
DESCRIPTIONS = {
    "cover": {
        "open_cover": {"target": {"entity": [{"domain": ["cover"],
                                              "supported_features": [1]}]}, "fields": {}},
        "close_cover": {"target": {"entity": [{"domain": ["cover"],
                                               "supported_features": [2]}]}, "fields": {}},
        "set_cover_position": {
            "target": {"entity": [{"domain": ["cover"], "supported_features": [COVER_POS]}]},
            "fields": {"position": {"required": True,
                                    "selector": {"number": {"min": 0, "max": 100}}}},
        },
    },
    "lock": {
        "lock": {"target": {"entity": [{"domain": ["lock"]}]},
                 "fields": {"code": {"selector": {"text": {}}}}},
        "unlock": {"target": {"entity": [{"domain": ["lock"]}]},
                   "fields": {"code": {"selector": {"text": {}}}}},
        "open": {"target": {"entity": [{"domain": ["lock"],
                                        "supported_features": [LOCK_OPEN]}]},
                 "fields": {"code": {"selector": {"text": {}}}}},
    },
    "alarm_control_panel": {
        "alarm_arm_away": {"target": {"entity": [{"domain": ["alarm_control_panel"]}]},
                           "fields": {"code": {"selector": {"text": {}}}}},
        "alarm_disarm": {"target": {"entity": [{"domain": ["alarm_control_panel"]}]},
                         "fields": {"code": {"selector": {"text": {}}}}},
    },
    "light": {
        "turn_on": {
            "target": {"entity": [{"domain": ["light"]}]},
            "fields": {
                "effect": {"filter": {"supported_features": [4]},
                           "selector": {"text": {}}},
                "brightness_pct": {"filter": {"attribute": {
                    "supported_color_modes": ["brightness", "hs"]}},
                    "selector": {"number": {"min": 0, "max": 100}}},
            },
        },
        "turn_off": {"target": {"entity": [{"domain": ["light"]}]}, "fields": {}},
    },
    "water_heater": {
        "set_operation_mode": {
            "target": {"entity": [{"domain": ["water_heater"]}]},
            "fields": {"operation_mode": {"required": True, "selector": {"text": {}}}},
        },
    },
    "notify": {
        "send_message": {
            "target": {"entity": [{"domain": ["notify"]}]},
            "fields": {"message": {"required": True, "selector": {"text": {}}},
                       "title": {"selector": {"text": {}}}},
        },
    },
    "media_player": {
        "play_media": {
            "target": {"entity": [{"domain": ["media_player"]}]},
            "fields": {"media": {"required": True, "selector": {"media": {}}}},
        },
    },
    # כמו ב-services.yaml של core (2026.11).
    "automation": {
        "turn_on": {"target": {"entity": {"domain": "automation"}}},
        "turn_off": {"target": {"entity": {"domain": "automation"}},
                     "fields": {"stop_actions": {"default": True,
                                                 "selector": {"boolean": None}}}},
        "toggle": {"target": {"entity": {"domain": "automation"}}},
        "trigger": {"target": {"entity": {"domain": "automation"}},
                    "fields": {"skip_condition": {"default": True,
                                                  "selector": {"boolean": None}}}},
        "reload": {},
    },
    "script": {
        "turn_on": {"target": {"entity": {"domain": "script"}}},
        "turn_off": {"target": {"entity": {"domain": "script"}}},
        "toggle": {"target": {"entity": {"domain": "script"}}},
    },
    "weather": {
        "get_forecasts": {"target": {"entity": {"domain": "weather"}},
                          "fields": {"type": {"required": True, "selector": {
                              "select": {"options": ["daily", "hourly"]}}}}},
    },
    "homeassistant": {
        "turn_on": {"target": {}, "fields": {}},
        "turn_off": {"target": {}, "fields": {}},
        "toggle": {"target": {}, "fields": {}},
        "update_entity": {"fields": {"entity_id": {"required": True}}},
    },
}

info_binary = caps.EntityInfo("cover.b", "cover", "closed", {}, 1 | 2, None, None, True)
info_pos = caps.EntityInfo("cover.p", "cover", "closed", {}, 1 | 2 | 4, None, None, True)
ok("תריס בלי מיקום אינו מקבל set_cover_position",
   not caps.target_matches(DESCRIPTIONS["cover"]["set_cover_position"], info_binary))
ok("תריס עם מיקום מקבל אותה",
   caps.target_matches(DESCRIPTIONS["cover"]["set_cover_position"], info_pos))
ok("יעד בלי מסנן מקבל כל ישות",
   caps.target_matches({"target": {}}, info_binary))
ok("פעולה בלי יעד אינה פעולת ישות",
   not caps.target_matches({"fields": {}}, info_binary))
ok("צירוף ביטים ברשימה פנימית דורש את כולם",
   caps.features_match([[1, 4]], 5) and not caps.features_match([[1, 4]], 1))
ok("שם תכונה שאינו נפתר אינו מתאים",
   not caps.features_match(["nope.Enum.X"], 255))

light = caps.EntityInfo("light.a", "light", "on",
                        {"supported_color_modes": ["onoff"]}, 0, None, None, True)
ok("שדה אפקט נופל בנורה בלי אפקטים",
   not caps.field_applies(DESCRIPTIONS["light"]["turn_on"]["fields"]["effect"], light))
ok("שדה בהירות נופל בנורה שאינה מתעמעמת",
   not caps.field_applies(DESCRIPTIONS["light"]["turn_on"]["fields"]["brightness_pct"], light))
dim = caps.EntityInfo("light.d", "light", "on",
                      {"supported_color_modes": ["brightness"]}, 0, None, None, True)
ok("ובנורה מתעמעמת נשאר",
   caps.field_applies(DESCRIPTIONS["light"]["turn_on"]["fields"]["brightness_pct"], dim))

# ======================================================================
print("\n== גילוי מלא דרך smart.async_discover ==")
# ======================================================================

hass = fake_ha.FakeHass({
    "cover.b": fake_ha.FakeState("closed", supported_features=3, friendly_name="תריס"),
    "cover.p": fake_ha.FakeState("open", supported_features=7, current_position=40),
    "lock.front": fake_ha.FakeState("locked", supported_features=0, code_format=r"^\d{4}$"),
    "lock.open": fake_ha.FakeState("locked", supported_features=1),
    "alarm_control_panel.home": fake_ha.FakeState(
        "disarmed", code_format="number", code_arm_required=False),
    "water_heater.boiler": fake_ha.FakeState(
        "eco", operation_list=["eco", "electric", "off"]),
    "notify.phone": fake_ha.FakeState("unknown"),
    "media_player.tv": fake_ha.FakeState("off"),
    "group.lights": fake_ha.FakeState("on", entity_id=["light.a"]),
    "automation.night": fake_ha.FakeState("on", friendly_name="לילה"),
    "script.coffee": fake_ha.FakeState("off", friendly_name="קפה"),
    "weather.home": fake_ha.FakeState("sunny"),
})
fake_ha.FakeServices.READ_ONLY = {("weather", "get_forecasts")}
hass.services.async_services = lambda: {
    d: {a: None for a in actions} for d, actions in DESCRIPTIONS.items()
}
hass.services.has_service = lambda d, a: a in DESCRIPTIONS.get(d, {})


async def _desc(_hass):
    return DESCRIPTIONS


import homeassistant.helpers.service as _svc  # noqa: E402

_svc.async_get_all_descriptions = _desc
smart.async_get_all_descriptions = _desc
import custom_components.ha_ivr.action_fields as _af  # noqa: E402

_af.async_get_all_descriptions = _desc


def discover(entity_id):
    return {c.ident: c for c in run(smart.async_discover(hass, entity_id))}


binary = discover("cover.b")
ok("תריס בינארי: פתיחה וסגירה", {"open_cover", "close_cover"} <= set(binary))
ok("תריס בינארי: בלי מיקום", "set_cover_position" not in binary)
ok("תריס עם מיקום: מיקום מוצע", "set_cover_position" in discover("cover.p"))

front = discover("lock.front")
ok("מנעול: נעילה ופתיחה מוצעות (השדה code אינו שדה הערך)",
   {"lock", "unlock"} <= set(front))
ok("מנעול בלי OPEN: אין open", "open" not in front)
ok("מנעול עם code_format באורך קבוע: קוד של 4 ספרות",
   front["unlock"].code == caps.CODE_FIXED and front["unlock"].code_width == 4)
ok("גם נעילה דורשת קוד, כמו ב-core", front["lock"].code == caps.CODE_FIXED)
ok("מנעול עם OPEN: open מוצע", "open" in discover("lock.open"))
ok("מנעול בלי code_format: בלי קוד", discover("lock.open")["unlock"].code == caps.CODE_NONE)

alarm = discover("alarm_control_panel.home")
ok("אזעקה: דריכה בלי קוד כש-code_arm_required כבוי",
   alarm["alarm_arm_away"].code == caps.CODE_NONE)
ok("אזעקה: נטרול עם קוד באורך משתנה", alarm["alarm_disarm"].code == caps.CODE_TERMINATED)

boiler = discover("water_heater.boiler")
ok("דוד: מצב הפעלה נמצא מ-operation_list",
   boiler.get("set_operation_mode") is not None
   and boiler["set_operation_mode"].kind == smart.KIND_CHOICE
   and boiler["set_operation_mode"].options == ("eco", "electric", "off"))

phone = discover("notify.phone")
ok("התראה: טקסט חובה הוא ערך קבוע (אין הקשה של טקסט)",
   phone["send_message"].kind == smart.KIND_FIXED)

auto = discover("automation.night")
ok("אוטומציה: הרצה, הפעלה, השבתה והחלפה",
   {"trigger", "turn_on", "turn_off", "toggle"} <= set(auto) and "reload" not in auto)
ok("הרצת אוטומציה היא פעולה פשוטה ולא שאלת כן/לא על התנאים",
   auto["trigger"].kind == smart.KIND_SIMPLE
   and auto["turn_off"].kind == smart.KIND_SIMPLE)
ok("ולכל פעולה של אוטומציה שם אחר",
   len({auto[a].label for a in ("trigger", "turn_on", "turn_off", "toggle")}) == 4
   and auto["trigger"].label == "הרצה עכשיו")
ok("תסריט: הרצה ועצירה",
   discover("script.coffee")["turn_on"].label == "הרצה"
   and discover("script.coffee")["turn_off"].label == "עצירה")
ok("set_ בלי שדה שאפשר להקיש הוא ערך קבוע ולא פעולה ריקה",
   run(smart._classify(hass, "climate", "set_temperature", {
       "target_temp_low": {"selector": {"number": {"min": 7, "max": 35}}},
       "target_temp_high": {"selector": {"number": {"min": 7, "max": 35}}},
   }, "climate.x")).kind == smart.KIND_FIXED)
ok("פעולה שרק מחזירה מידע אינה מוצעת (SupportsResponse.ONLY)",
   "get_forecasts" not in discover("weather.home"))
ok("מדיה: שדה media חובה הוא ערך קבוע בלבד",
   discover("media_player.tv")["play_media"].kind == smart.KIND_FIXED)

group = discover("group.lights")
ok("קבוצה קלאסית: הדלקה, כיבוי והחלפה מ-homeassistant",
   {"homeassistant.turn_on", "homeassistant.turn_off", "homeassistant.toggle"} <= set(group))
ok("ורק הן", not any(k.startswith("homeassistant.") and k.split(".")[1] not in
                     caps.GROUP_ACTIONS for k in group))

plan = smart.build_plan(list(front.values()), ["__status__", "lock", "unlock"])
ok("התוכנית שומרת איך מקישים את הקוד ולא קוד",
   plan[1]["code"] == {"kind": "fixed", "width": 4, "min": 4, "max": 4}
   and "1234" not in str(plan))
ok("ערך קבוע בלבד אינו נכנס לתוכנית",
   smart.build_plan([discover("media_player.tv")["play_media"]], ["play_media"]) == [])

# ======================================================================
print("\n== פענוח הקוד ==")
# ======================================================================

R = caps.lock_code_rule
ok(r"^\d{4}$ — אורך קבוע", R(r"^\d{4}$", None) == caps.CodeRule("fixed", 4, 4, 4))
ok(r"^[0-9]{4}$ — אורך קבוע", R(r"^[0-9]{4}$", None).kind == caps.CODE_FIXED)
ok(r"\d{4} בלי עוגן — אורך משתנה (re.match מעגן רק התחלה)",
   R(r"\d{4}", None).kind == caps.CODE_TERMINATED)
ok(r"^\d{4,6}$ — סולמית, 4 עד 6",
   (lambda r: r.kind == "terminated" and r.min_len == 4 and r.max_len == 6)(
       R(r"^\d{4,6}$", None)))
ok(".* — אי אפשר להקיש", R(".*", None).kind in (caps.CODE_NONE, caps.CODE_UNDIALABLE))
ok("[A-Za-z0-9]+ — אי אפשר להקיש", R("[A-Za-z0-9]+", None).kind == caps.CODE_UNDIALABLE)
ok("קוד ברירת מחדל ברישום פוטר", R(r"^\d{4}$", "1234").kind == caps.CODE_NONE)
ok("קוד ברירת מחדל שאינו תואם אינו פוטר", R(r"^\d{4}$", "12").kind == caps.CODE_FIXED)
ok("regex שבור — אי אפשר להקיש", R("[", None).kind == caps.CODE_UNDIALABLE)
ok("אזעקה text — אי אפשר להקיש",
   caps.alarm_code_rule("alarm_disarm", {"code_format": "text"}).kind == caps.CODE_UNDIALABLE)
ok("אזעקה number — אינו נבדק כ-regex",
   caps.alarm_code_rule("alarm_disarm", {"code_format": "number"}).kind == caps.CODE_TERMINATED)

# ======================================================================
print("\n== צמתי קוד בעץ, לפי הקו ==")
# ======================================================================

raw_fixed = {"digit": "1", "kind": "simple", "action": "unlock", "label": "פתיחה",
             "code": {"kind": "fixed", "width": 4, "min": 4, "max": 4}}
raw_term = {**raw_fixed, "code": {"kind": "terminated", "width": 0, "min": 4, "max": 6}}
node = menu._smart_child(hass, "lock.front", False, raw_fixed, {"terminator": False})
ok("קוד באורך קבוע נבנה בכל קו", node["collect"]["secret"] and node["collect"]["width"] == 4)
ok("קוד עם סולמית אינו נבנה בקו בלי סולמית",
   menu._smart_child(hass, "lock.front", False, raw_term, {"terminator": False}) is None)
term = menu._smart_child(hass, "lock.front", False, raw_term, {"terminator": True})
ok("ונבנה בקו עם סולמית", term["collect"]["max_len"] == 6)

collect = term["collect"]
ok("לפני 4 ספרות אין סולמית", "#" not in tree.valid_next_digits(collect, ("1", "2", "3")))
ok("אחרי 4 — יש", "#" in tree.valid_next_digits(collect, ("1", "2", "3", "4")))
ok("אחרי 6 — רק סולמית",
   tree.valid_next_digits(collect, tuple("123456")) == {"#"})
ok("סולמית משלימה", tree.code_complete(collect, tuple("1234"), "#"))
ok("4 ספרות בלי סולמית אינן משלימות", not tree.code_complete(collect, tuple("1234"), "4"))
ok("קוד 1111 נקלט כולו (אין סינון הקשה כפולה באיסוף)",
   tree.code_complete(node["collect"], tuple("1111"), "1"))

text_raw = {"digit": "2", "kind": "text", "action": "send_message", "label": "הודעה",
            "field": "message"}
ok("תוכנית ישנה עם הכתבה אינה נבנית, והספרה נשארת ריקה",
   menu._smart_child(hass, "notify.phone", False, text_raw, {}) is None)

# ======================================================================
print("\n== אימות ביצוע ==")
# ======================================================================

S = fake_ha.FakeState
check = call_mod.expected("turn_on", {"brightness_pct": 80}, S("on", brightness=128))
ok("בהירות 80% מאושרת ב-203 וב-205", check(S("on", brightness=203)) and check(S("on", brightness=205)))
ok("ולא ב-150", not check(S("on", brightness=150)))
zero = call_mod.expected("turn_on", {"brightness_pct": 0}, S("on", brightness=128))
ok("בהירות 0 מאושרת בכיבוי", zero(S("off")))
ok("מאוורר 0 מאושר בכיבוי", call_mod.expected("set_percentage", {"percentage": 0}, None)(S("off")))
pos0 = call_mod.expected("set_cover_position", {"position": 0}, None)
ok("מיקום 0 מאושר בסגור ובנסגר", pos0(S("closed")) and pos0(S("closing")))
temp = call_mod.expected("set_temperature", {"temperature": 22}, None)
ok("טמפרטורה בסובלנות", temp(S("cool", temperature=22.05)) and not temp(S("cool", temperature=23)))
ok("מצב מאוורר לפי המאפיין",
   call_mod.expected("set_fan_mode", {"fan_mode": "high"}, None)(S("cool", fan_mode="high")))
ok("toggle לפי שינוי מהמצב הקודם",
   call_mod.expected("toggle", {}, S("on"))(S("off")))
ok("כפתור אינו ממתין", not call_mod.needs_wait("button", "press"))

hass2 = fake_ha.FakeHass({"light.k": S("on", brightness=128)})


async def _set_after(entity_id, state, delay=0.05):
    await asyncio.sleep(delay)
    hass2.states.set(entity_id, state)


async def _scenario_ok():
    task = asyncio.ensure_future(_set_after("light.k", S("on", brightness=204)))
    outcome = await call_mod.async_call_one(hass2, "light.k", "turn_on", {"brightness_pct": 80})
    await task
    return outcome


ok("שינוי בהירות בנורה דולקת מאושר לפי המאפיין", run(_scenario_ok()).status == call_mod.OK)

hass2.states.set("light.k", S("on", brightness=204))
outcome = run(call_mod.async_call_one(hass2, "light.k", "turn_on", {"brightness_pct": 80}))
ok("ערך זהה לנוכחי — בלי המתנה", outcome.status == call_mod.OK)

hass2.states.set("light.u", S("unavailable"))
ok("ישות לא זמינה אינה נקראת",
   run(call_mod.async_call_one(hass2, "light.u", "turn_on", {})).status == call_mod.UNAVAILABLE)

# ======================================================================
print("\n== סיווג חריגות, לפי ההיררכיה של core ==")
# ======================================================================

import homeassistant.exceptions as ha_exc  # noqa: E402

for err, want in (
    (ha_exc.ServiceNotFound(), call_mod.NOT_FOUND),
    (ha_exc.ServiceNotSupported(), call_mod.NOT_SUPPORTED),
    (ha_exc.ServiceValidationError(), call_mod.INVALID),
    (ha_exc.Unauthorized(), call_mod.UNAUTHORIZED),
    (ha_exc.HomeAssistantError(), call_mod.FAILED),
    (TimeoutError(), call_mod.TIMEOUT),
    (type("Invalid", (Exception,), {})(), call_mod.SCHEMA),
    (RuntimeError(), call_mod.ERROR),
):
    ok(f"{type(err).__name__} → {want}", call_mod.classify_error(hass2, err)[0] == want)


class _Failing(fake_ha.FakeServices):
    def __init__(self, err):
        super().__init__()
        self.err = err

    async def async_call(self, *a, **k):
        raise self.err


fake_ha.ISSUES.clear()
hass2.services = _Failing(ha_exc.ServiceNotFound())
out = run(call_mod.async_call_one(hass2, "light.k", "turn_off", {}, entry_id="e1"))
ok("פעולה שנעלמה פותחת תיקון", out.status == call_mod.NOT_FOUND
   and any(k.startswith("action_missing") for k in fake_ha.ISSUES))
hass2.services = fake_ha.FakeServices()
run(call_mod.async_call_one(hass2, "light.k", "turn_off", {}, entry_id="e1"))
ok("והתיקון נסגר אחרי הצלחה", not any(k.startswith("action_missing") for k in fake_ha.ISSUES))

# קבוצה עם תקלה חלקית: כל אחד בקריאה משלו.
hass3 = fake_ha.FakeHass({"light.a": S("off"), "light.b": S("unavailable"), "light.c": S("off")})


class _OneFails(fake_ha.FakeServices):
    async def async_call(self, domain, service, data, blocking=False, return_response=False):
        self.calls.append((domain, service, dict(data)))
        if data["entity_id"] == "light.c":
            raise ha_exc.HomeAssistantError()


hass3.services = _OneFails()
grp = run(call_mod.async_call_many(hass3, ["light.a", "light.b", "light.c"], "turn_on", {}))
ok("קבוצה: אחד בוצע, אחד לא זמין, אחד נכשל",
   (grp.done, grp.unavailable, grp.failed, grp.total) == (1, 1, 1, 3))
ok("הלא זמין לא נקרא כלל",
   all(c[2]["entity_id"] != "light.b" for c in hass3.services.calls))

# ======================================================================
print("\n== הקראה ==")
# ======================================================================

i18n.bind(hass2)


def _with_id(state, entity_id):
    state.entity_id = entity_id
    return state


ok("בהירות 255 נאמרת כ-100 אחוז",
   "100" in said(speech.speak_state(_with_id(S("on", brightness=255), "light.x"))))
clim = _with_id(S("cool", hvac_action=None, current_temperature=24, temperature=22), "climate.s")
ok("מזגן בלי hvac_action אינו נופל", "22" in said(speech.speak_state(clim)))
rng = _with_id(S("heat_cool", target_temp_low=20, target_temp_high=24), "climate.r")
ok("מזגן בטווח מקריא את שני הגבולות",
   "20" in said(speech.speak_state(rng)) and "24" in said(speech.speak_state(rng)))
unk = _with_id(S("unknown", unit_of_measurement="°C"), "sensor.t")
ok("חיישן לא ידוע נאמר בלי יחידה", "מעלות" not in said(speech.speak_state(unk)))
precise = _with_id(S("23.400001", unit_of_measurement="°C"), "sensor.p")
precise.precision = 1
ok("עיגול לפי display_precision", "23.4" in said(speech.speak_state(precise))
   or "23 נקודה 4" in said(speech.speak_state(precise)))
ts = _with_id(S("2026-01-03T17:35:00+00:00", device_class="timestamp"), "sensor.ts")
spoken_ts = said(speech.speak_state(ts))
ok("timestamp בזמן מקומי (UTC+2 בבדיקה)", "19" in spoken_ts and "35" in spoken_ts)

fake_ha.TRANSLATIONS.update({
    ("he", "component.vacuum.entity_component._.state.cleaning"): "מנקה",
    ("he", "component.fan.entity_component._.state_attributes.preset_mode.state.sleep"): "שינה",
    ("en", "component.fan.entity_component._.state_attributes.preset_mode.state.sleep"): "Sleep",
    ("he", "component.x.services.do.name"): "Do it",
    ("en", "component.x.services.do.name"): "Do it",
})
run(i18n.async_load(hass2))
ok("תרגום רשמי למאפיין",
   i18n.attribute_value(hass2, "fan", "preset_mode", "sleep") == "שינה")
ok("ערך שזהה לאנגלית אינו נחשב תרגום", i18n.action_name(hass2, "x", "do") == "")

# ======================================================================
print("\n== נעילה מפני ניחוש ==")
# ======================================================================

h4 = fake_ha.FakeHass()
for _ in range(3):
    security.record_failure(h4, "e", "call1", "0501234567")
ok("שלוש דחיות נועלות את השיחה", security.blocked(h4, "e", "call1", "0501234567"))
ok("שיחה אחרת עדיין פתוחה", not security.blocked(h4, "e", "call2", "0501234567"))
for _ in range(2):
    security.record_failure(h4, "e", "call2", "+972-50-123-4567")
ok("חמש דחיות ממספר אחד חוסמות אותו גם בשיחה חדשה (מספר מנורמל)",
   security.blocked(h4, "e", "call3", "sip:0501234567@pbx"))
fake_ha.ISSUES.clear()
for i in range(10):
    security.record_failure(h4, "e2", f"c{i}", "")
ok("עשר דחיות ממספרים חסויים חוסמות את הקו ופותחות תיקון",
   security.blocked(h4, "e2", "new", "") and any("code_lockout" in k for k in fake_ha.ISSUES))
ok("המספר ביומן מוסתר", security.mask("0501234567") == "***4567")

ok("אוטומציה מוקראת כמופעלת או מושבתת, לא כדולקת",
   speech.state_word(types.SimpleNamespace(
       entity_id="automation.night", state="on", attributes={})) == "מופעלת"
   and speech.speak_word("off", "automation")[0].data == "מושבתת")
hrun = fake_ha.FakeHass({"automation.night": fake_ha.FakeState("on")})
trig = run(call_mod.async_call_one(hrun, "automation.night", "trigger", {}))
ok("אחרי הרצת אוטומציה שומעים 'בוצע', לא את המצב שלה",
   trig.status == call_mod.OK and trig.state is None
   and hrun.services.calls == [("automation", "trigger", {"entity_id": "automation.night"})])

from custom_components.ha_ivr.model import speakable  # noqa: E402

ok("שם עם אימוג'י מוקרא בלעדיו", speakable("הורדת טמפרטורה 👻") == "הורדת טמפרטורה")
ok("מעלות, מטבע וניקוד נשארים", speakable("שָׁלוֹם 30°C ₪5 ❤️") == "שָׁלוֹם 30°C ₪5")
ok("ספרה עם מקש-אימוג'י נשארת ספרה", speakable("1️⃣") == "1")
ok("תווית בעץ נקייה", tree.build({"say": "סלון 🛋️", "items": {}}).say == "סלון")

# ======================================================================
print(f"\n{'PASS' if not FAIL else 'FAIL'} — {PASS} עברו, {FAIL} נכשלו")
sys.exit(1 if FAIL else 0)
