"""Home Assistant מזויף, כדי שאפשר יהיה להריץ את הקוד באמת.

עד היום כל הבדיקות קראו את הקוד כטקסט. זה תפס הרבה, אבל לא תפס
`UnboundLocalError` — שם שהוגדר בפונקציה אבל מאוחר מדי, ונופל רק
כשהשורה מתבצעת בפועל.

כאן נבנה מספיק מ-HA כדי שהמודולים ייובאו ושהפונקציות ירוצו: hass
מזויף עם states, services ו-bus, בקשה מזויפת, ותשובות HTTP.
לא מדובר בהתקנה אמיתית — אין לולאת אירועים של HA, אין רישום
ישויות ואין מסד נתונים. מה שכן: הקוד רץ, ושגיאות זמן ריצה צצות
כאן במקום בשיחת טלפון.

python3 tests/fake_ha.py
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# שלד המודולים של homeassistant
# ----------------------------------------------------------------------


def _module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


class _Marker:
    """מציין שדה של voluptuous. השם שמור ב-`schema`, כמו במקור.

    `Required` ו-`Optional` הם תת-מחלקות נפרדות ולא כינוי אחד:
    ההבדל ביניהן הוא מה שקובע אם שדה חייב להישלח, ובדיקה שאינה
    יכולה להבחין ביניהן אינה יכולה לאמת חוזה של שירות.
    """

    def __init__(self, schema, default=None, description=None, **kwargs) -> None:
        self.schema = schema
        self.default = default
        self.description = description or {}

    def __str__(self) -> str:
        return str(self.schema)

    def __hash__(self) -> int:
        return hash(self.schema)

    def __eq__(self, other) -> bool:
        return getattr(other, "schema", other) == self.schema

    def __repr__(self) -> str:
        return f"<{self.schema}>"


class _Schema:
    """סכמה מזויפת ששומרת את המילון, כדי שאפשר יהיה לבדוק אותו."""

    def __init__(self, schema=None, **kwargs) -> None:
        self.schema = schema if schema is not None else {}

    def __call__(self, data):
        return data

    def __repr__(self) -> str:
        return f"Schema({list(self.schema)})"


class _Any:
    """מחליף כל מחלקה או פונקציה שאיננו צריכים באמת."""

    def __init__(self, *args, **kwargs) -> None:
        self.args, self.kwargs = args, kwargs

    def __call__(self, *args, **kwargs):
        return _Any(*args, **kwargs)

    def __getattr__(self, item):
        return _Any()

    def __eq__(self, other):
        return isinstance(other, _Any)

    def __hash__(self):
        return id(type(self))


def _passthrough(func=None, **_kwargs):
    return func if func is not None else (lambda f: f)


class FakeResponse:
    """תשובת HTTP מזויפת, כדי לבדוק מה הקוד מחזיר."""

    def __init__(self, text="", status=200, content_type="", body=None,
                 **extra) -> None:
        self.text, self.status = text, status
        self.content_type, self.body = content_type, body
        # charset וכל שדה אחר ש-aiohttp מקבל. נשמרים כדי שאפשר
        # יהיה לבדוק אותם, ולא מפילים את הבנייה.
        self.extra = extra

    def __repr__(self) -> str:
        return f"<Response {self.status} {self.content_type} {self.text[:60]!r}>"


def _json_response(data, **kwargs):
    import json as _json

    return FakeResponse(text=_json.dumps(data, ensure_ascii=False),
                        content_type="application/json", body=data, **kwargs)


def install() -> None:
    """רישום כל המודולים שהאינטגרציה מייבאת."""
    # aiohttp אינו מותקן כאן ואין רשת להתקין אותו. מזויף עד לרמה
    # שמאפשרת לייבא ולהריץ — התשובות נבדקות כאובייקטים.
    web = types.SimpleNamespace(
        Response=FakeResponse,
        json_response=_json_response,
        WebSocketResponse=_Any,
        StreamResponse=_Any,
        Request=_Any,
    )
    _module("aiohttp", web=web,
            WSMsgType=types.SimpleNamespace(BINARY="BINARY", TEXT="TEXT",
                                            ERROR="ERROR"),
            ClientSession=_Any)
    _module("aiohttp.web", **vars(web))

    # voluptuous מזויף אך **ניתן לבדיקה**: הסכמה שומרת את המילון
    # והמצייני שומרים את שם השדה. כשהכול היה `_Any`, בוני הטפסים
    # לא היו ניתנים להרצה כלל — 1,100 שורות של config_flow שאף
    # בדיקה לא נגעה בהן, וטעות בהן מתגלה רק כשמשתמש פותח את המסך.
    _module("homeassistant.components.notify",
            NotifyEntity=type("NotifyEntity", (), {"hass": None}))

    _module("voluptuous", Schema=_Schema,
            Required=type("Required", (_Marker,), {}),
            Optional=type("Optional", (_Marker,), {}),
            Self=_Any, ALLOW_EXTRA=object(), Invalid=type("Invalid", (Exception,), {}))

    ha = _module("homeassistant")
    ha.__path__ = []
    _module("homeassistant.core", HomeAssistant=_Any, Context=_Any,
            callback=_passthrough, ServiceCall=_Any, Event=_Any)
    _module("homeassistant.exceptions",
            HomeAssistantError=type("HomeAssistantError", (Exception,), {}))
    _module("homeassistant.const", Platform=types.SimpleNamespace(
        SENSOR="sensor", ASSIST_SATELLITE="assist_satellite", SELECT="select",
        NOTIFY="notify"))
    # ConfigFlow מוגדר עם domain=... בשורת המחלקה, ולכן הבסיס
    # חייב לקבל ארגומנטים ב-__init_subclass__.
    class _FlowBase:
        def __init_subclass__(cls, **kwargs) -> None:
            super().__init_subclass__()

        def __init__(self, *a, **k) -> None:
            self.hass = None
            self.context = {}

        def __getattr__(self, item):
            return _Any()

    _module("homeassistant.config_entries", ConfigEntry=_Any, ConfigFlow=_FlowBase,
            ConfigFlowResult=dict, ConfigSubentryFlow=_FlowBase,
            ConfigSubentry=_Any, OptionsFlow=_FlowBase, SubentryFlowResult=dict)

    # חבילה ולא מודול, אחרת ייבוא של תת-מודול נכשל.
    helpers = _module("homeassistant.helpers")
    helpers.__path__ = []
    _module("homeassistant.helpers.service", async_get_all_descriptions=_Any)
    _module("homeassistant.helpers.intent", async_get=_Any)
    _module("homeassistant.helpers.template", Template=_Any)
    _module("homeassistant.helpers.config_validation",
            string=str, entity_id=str, boolean=bool)
    # מצייני המצב הם קבועים ולא מחלקות. כשהם היו `_Any` כמו השאר,
    # כל ניסיון לבנות סכמה אמיתית נפל על `SelectSelectorMode.DROPDOWN`
    # — ולכן אף בדיקה לא הריצה את בוני הטפסים בפועל.
    _mode = types.SimpleNamespace(DROPDOWN="dropdown", LIST="list", BOX="box",
                                  SLIDER="slider")
    _module("homeassistant.helpers.selector", **{
        **{n: _Any for n in (
            "EntitySelector", "EntitySelectorConfig", "SelectOptionDict",
            "SelectSelector", "SelectSelectorConfig",
            "NumberSelector", "NumberSelectorConfig",
            "BooleanSelector", "BooleanSelectorConfig",
            "TextSelector", "TextSelectorConfig", "TextSelectorType",
            "ObjectSelector", "AttributeSelector", "ConfigEntrySelector",
        )},
        "SelectSelectorMode": _mode,
        "NumberSelectorMode": _mode,
    })
    _module("homeassistant.helpers.entity", Entity=object)
    _module("homeassistant.helpers.device_registry",
            DeviceInfo=dict, DeviceEntryType=types.SimpleNamespace(SERVICE="service"),
            async_get=_Any)
    _module("homeassistant.helpers.entity_platform", AddEntitiesCallback=_Any)
    _module("homeassistant.helpers.restore_state", RestoreEntity=object)
    _module("homeassistant.helpers.dispatcher",
            async_dispatcher_send=lambda *a, **k: None,
            async_dispatcher_connect=lambda *a, **k: (lambda: None))
    _module("homeassistant.helpers.event",
            async_track_state_change_event=lambda *a, **k: (lambda: None))
    _module("homeassistant.helpers.network", get_url=lambda *a, **k: "https://ha.test",
            NoURLAvailableError=type("NoURLAvailableError", (Exception,), {}))
    _module("homeassistant.helpers.aiohttp_client",
            async_get_clientsession=lambda *a, **k: _Any())
    class _EntityRegistry:
        """מרשם מינימלי: רק החיפוש שהלוויין עושה בו."""

        def __init__(self):
            self.entities = {}

        def async_get_entity_id(self, domain, platform, unique_id):
            return self.entities.get((domain, platform, unique_id))

    _registry = _EntityRegistry()
    _module("homeassistant.helpers.entity_registry",
            async_get=lambda hass: _registry)
    _module("homeassistant.util", dt=types.SimpleNamespace(utcnow=lambda: None))
    _module("homeassistant.util.dt", utcnow=lambda: None)

    comps = _module("homeassistant.components")
    comps.__path__ = []
    _module("homeassistant.components.http", HomeAssistantView=object)
    # קבועי פורמט ההקראה. הלוויין מבקש דרכם WAV בקצב של הספק —
    # בלעדיהם הצינור מחזיר mp3, וזה בדיוק מה שהתגלה בשיחה.
    _module(
        "homeassistant.components.tts",
        ATTR_PREFERRED_FORMAT="preferred_format",
        ATTR_PREFERRED_SAMPLE_RATE="preferred_sample_rate",
        ATTR_PREFERRED_SAMPLE_CHANNELS="preferred_sample_channels",
        ATTR_PREFERRED_SAMPLE_BYTES="preferred_sample_bytes",
        async_get_stream=lambda hass, token: None,
    )
    # האבחון מסתיר סודות דרך העוזר של HA. מחיקה אמיתית ולא
    # זהות: בדיקה שמאמתת הסתרה חייבת לראות ערך מוסתר.
    _module(
        "homeassistant.components.diagnostics",
        async_redact_data=lambda data, keys: {
            k: ("**REDACTED**" if k in keys else v) for k, v in dict(data).items()
        },
    )
    _module("homeassistant.components.sensor", RestoreSensor=object,
            SensorEntity=object,
            SensorDeviceClass=types.SimpleNamespace(TIMESTAMP="timestamp"),
            SensorStateClass=types.SimpleNamespace(TOTAL_INCREASING="total_increasing"))
    _module("homeassistant.components.stt", **{
        n: _Any for n in ("AudioBitRates", "AudioChannels", "AudioCodecs",
                          "AudioFormats", "AudioSampleRates", "SpeechMetadata")
    })
    class _PipelineSelect:
        def __init__(self, hass, domain, unique_id_prefix, index=0):
            self.hass = hass
            self._attr_unique_id = f"{unique_id_prefix}-pipeline"

    class _VadSelect:
        def __init__(self, hass, unique_id_prefix):
            self.hass = hass
            self._attr_unique_id = f"{unique_id_prefix}-vad_sensitivity"

    _module("homeassistant.components.assist_pipeline",
            PipelineEvent=_Any, PipelineEventType=_Any, AudioSettings=_Any,
            async_pipeline_from_audio_stream=_Any, async_get_pipelines=lambda h: [],
            AssistPipelineSelect=_PipelineSelect, VadSensitivitySelect=_VadSelect)
    _module("homeassistant.components.assist_pipeline.vad", VadSensitivity=_Any)

    # לוויין Assist. `AssistSatelliteEntity` מזויפת כמחלקה אמיתית
    # ולא כ-`_Any`, כדי ש-`IvrSatellite` תוכל לרשת ממנה ושהבדיקות
    # יריצו את הקשירה, השחרור והעברת האירועים בפועל.
    class _Satellite:
        entity_id = "assist_satellite.fake"
        _attr_tts_options = None
        _attr_supported_features = 0
        _conversation_id = None

        state = "idle"

        # מה ש-`Entity` נותנת באמת. בלי אלה אי אפשר לבדוק את
        # מזהי הקווים, וזה בדיוק מה שקובע אם ישות קיימת נשארת
        # שלה או הופכת ליתומה במרשם.
        @property
        def unique_id(self):
            return self._attr_unique_id

        @property
        def name(self):
            return self._attr_name

        @property
        def supported_features(self):
            return self._attr_supported_features

        @property
        def tts_options(self):
            return self._attr_tts_options

        def tts_response_finished(self):
            self.state = "idle"

        async def async_accept_pipeline_from_satellite(self, audio_stream, **kw):
            return None

    _module(
        "homeassistant.components.assist_satellite",
        AssistSatelliteEntity=_Satellite,
        AssistSatelliteConfiguration=lambda **kw: types.SimpleNamespace(**kw),
        AssistSatelliteEntityFeature=types.SimpleNamespace(ANNOUNCE=1),
        AssistSatelliteAnnouncement=lambda **kw: types.SimpleNamespace(**kw),
        SatelliteBusyError=type("SatelliteBusyError", (Exception,), {}),
    )

    ha.core = sys.modules["homeassistant.core"]
    ha.helpers = helpers
    ha.components = comps


# ----------------------------------------------------------------------
# עצמים מזויפים להרצה
# ----------------------------------------------------------------------


class FakeState:
    def __init__(self, state, **attributes) -> None:
        self.state = state
        self.attributes = attributes


class FakeStates:
    def __init__(self, mapping=None) -> None:
        self._states = dict(mapping or {})

    def get(self, entity_id):
        return self._states.get(entity_id)


class FakeServices:
    def __init__(self) -> None:
        self.calls = []

    def has_service(self, *a):
        return False

    def async_register(self, *a, **k):
        return None

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, dict(data)))


class FakeBus:
    def __init__(self) -> None:
        self.events = []

    def async_fire(self, event_type, data):
        self.events.append((event_type, dict(data)))


class FakeEntry:
    def __init__(self, data=None, options=None) -> None:
        self.entry_id = "entry1"
        self.data = dict(data or {"token": "T"})
        self.options = dict(options or {})
        self.subentries = {}


class FakeConfigEntries:
    def __init__(self, entries) -> None:
        self._entries = entries

    def async_entries(self, domain):
        return list(self._entries)


class FakeHass:
    def __init__(self, states=None, entries=None) -> None:
        self.states = FakeStates(states)
        self.services = FakeServices()
        self.bus = FakeBus()
        self.config_entries = FakeConfigEntries(entries or [FakeEntry()])
        self.loop = asyncio.get_event_loop_policy().new_event_loop()
        self.tasks = []

    def async_create_task(self, coro):
        # לא מריצים; רק סוגרים כדי שלא תישאר אזהרת coroutine.
        coro.close()
        self.tasks.append(coro)
        return None


class FakeURL:
    def __init__(self, text) -> None:
        self._text = text

    def with_query(self, _q):
        return self._text

    def __str__(self):
        return self._text


class FakeRequest:
    def __init__(self, query=None, headers=None, remote="1.2.3.4",
                 url="https://ha.test/api/ha_ivr/yemot/T", method="GET") -> None:
        self.query = dict(query or {})
        self.headers = dict(headers or {})
        self.remote = remote
        self.url = FakeURL(url)
        self.method = method
