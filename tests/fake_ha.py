"""Home Assistant מזויף, כדי שאפשר יהיה להריץ את הקוד באמת.

בדיקה שקוראת את הקוד כטקסט אינה תופסת `UnboundLocalError` — שם
שהוגדר בפונקציה אבל מאוחר מדי, ונופל רק כשהשורה מתבצעת בפועל.

כאן נבנה מספיק מ-HA כדי שהמודולים ייובאו ושהפונקציות ירוצו: hass
מזויף עם states, services ו-bus, בקשה מזויפת, ותשובות HTTP.
לא מדובר בהתקנה אמיתית — אין לולאת אירועים של HA, אין רישום
ישויות ואין מסד נתונים. מה שכן: הקוד רץ, ושגיאות זמן ריצה צצות
כאן במקום בשיחת טלפון.

python3 tests/fake_ha.py
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# שלד המודולים של homeassistant
# ----------------------------------------------------------------------


ISSUES: dict = {}
PANELS: list = []
# תרגומים מזויפים: (שפה, מפתח מלא) -> ערך. בדיקה ממלאת לפי הצורך.
TRANSLATIONS: dict = {}
# מאזיני שינוי מצב: entity_id -> רשימת callbacks. `FakeStates.set` מפעיל.
STATE_LISTENERS: dict = {}


@dataclasses.dataclass(frozen=True)
class AudioSettings:
    """כמו במקור: ה-VAD של הצינור דולק אלא אם ביקשו אחרת."""

    is_vad_enabled: bool = True
    silence_seconds: float = 0.7


# ההגדרות שכל הרצת צינור של הלוויין המזויף קיבלה, לפי הסדר.
ACCEPTED: list = []


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
    # והמציינים שומרים את שם השדה. כ-`_Any` בוני הטפסים אינם
    # ניתנים להרצה כלל, וטעות בהם מתגלה רק כשמשתמש פותח את המסך.
    _module("homeassistant.components.notify",
            NotifyEntity=type("NotifyEntity", (), {"hass": None}))

    # `All`, `Coerce` ו-`Range` הם מאמתי ערך ולא מצייני שדה, ולכן די
    # בגרסה שמריצה את ההמרה: הבדיקות בוחנות את צורת הסכמה ואת שמות
    # השדות, לא את הודעות השגיאה של voluptuous.
    def _coerce(type_):
        return type_

    def _all(*validators):
        def run(value):
            for validator in validators:
                value = validator(value)
            return value
        return run

    def _range(**_kwargs):
        return lambda value: value

    _module("voluptuous", Schema=_Schema,
            Required=type("Required", (_Marker,), {}),
            Optional=type("Optional", (_Marker,), {}),
            All=_all, Coerce=_coerce, Range=_range,
            Self=_Any, ALLOW_EXTRA=object(), Invalid=type("Invalid", (Exception,), {}))

    ha = _module("homeassistant")
    ha.__path__ = []
    _module("homeassistant.core", HomeAssistant=_Any, Context=_Any,
            callback=_passthrough, ServiceCall=_Any, Event=_Any)
    # ההיררכיה כמו ב-core: ServiceNotFound ו-ServiceNotSupported יורשות
    # מ-ServiceValidationError, וזו ו-Unauthorized מ-HomeAssistantError.
    class _HAE(Exception):
        def __init__(self, *args, translation_domain=None, translation_key=None,
                     translation_placeholders=None):
            super().__init__(*args)
            self.translation_domain = translation_domain
            self.translation_key = translation_key
            self.translation_placeholders = translation_placeholders

    _hae = type("HomeAssistantError", (_HAE,), {})
    _sve = type("ServiceValidationError", (_hae,), {})
    _module("homeassistant.exceptions",
            HomeAssistantError=_hae,
            ServiceValidationError=_sve,
            ServiceNotFound=type("ServiceNotFound", (_sve,), {}),
            ServiceNotSupported=type("ServiceNotSupported", (_sve,), {}),
            Unauthorized=type("Unauthorized", (_hae,), {}),
            ConfigEntryError=type("ConfigEntryError", (_hae,), {}),
            ConfigEntryAuthFailed=type("ConfigEntryAuthFailed", (_hae,), {}),
            ConfigEntryNotReady=type("ConfigEntryNotReady", (_hae,), {}))
    _module("homeassistant.const", Platform=types.SimpleNamespace(
        SENSOR="sensor", ASSIST_SATELLITE="assist_satellite", SELECT="select",
        NOTIFY="notify"),
        EVENT_COMPONENT_LOADED="component_loaded",
        EVENT_CORE_CONFIG_UPDATE="core_config_updated",
        EVENT_STATE_CHANGED="state_changed",
        EVENT_SERVICE_REGISTERED="service_registered",
        EVENT_SERVICE_REMOVED="service_removed")
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
            ConfigEntryState=types.SimpleNamespace(
                LOADED="loaded", NOT_LOADED="not_loaded", SETUP_ERROR="setup_error"),
            ConfigFlowResult=dict, ConfigSubentryFlow=_FlowBase,
            ConfigSubentry=FakeSubentry, OptionsFlow=_FlowBase,
            SubentryFlowResult=dict)

    # חבילה ולא מודול, אחרת ייבוא של תת-מודול נכשל.
    helpers = _module("homeassistant.helpers")
    helpers.__path__ = []
    _module("homeassistant.helpers.service", async_get_all_descriptions=_Any)
    _module("homeassistant.helpers.intent", async_get=_Any)
    _module("homeassistant.helpers.template", Template=_Any)
    _module("homeassistant.helpers.target",
            TargetSelection=FakeTargetSelection,
            async_extract_referenced_entity_ids=fake_extract_referenced,
            async_extract_excluded_entity_ids=fake_extract_excluded)
    _module("homeassistant.helpers.config_validation",
            string=str, entity_id=str, boolean=bool,
            config_entry_only_config_schema=lambda domain: ("config_entry_only", domain))
    # מצייני המצב הם קבועים ולא מחלקות. כ-`_Any` כמו השאר, כל
    # בנייה של סכמה אמיתית נופלת על `SelectSelectorMode.DROPDOWN`,
    # ואף בדיקה אינה מריצה את בוני הטפסים בפועל.
    _mode = types.SimpleNamespace(DROPDOWN="dropdown", LIST="list", BOX="box",
                                  SLIDER="slider")
    _module("homeassistant.helpers.selector", **{
        **{n: _Any for n in (
            "EntitySelector", "EntitySelectorConfig", "SelectOptionDict",
            "TargetSelector", "TargetSelectorConfig", "EntityFilterSelectorConfig",
            "SelectSelector", "SelectSelectorConfig",
            "NumberSelector", "NumberSelectorConfig",
            "BooleanSelector", "BooleanSelectorConfig",
            "TextSelector", "TextSelectorConfig", "TextSelectorType",
            "ObjectSelector", "AttributeSelector", "ConfigEntrySelector",
            "AreaSelector", "AreaSelectorConfig",
            "FloorSelector", "FloorSelectorConfig",
            "LabelSelector", "LabelSelectorConfig",
        )},
        "TextSelectorType": types.SimpleNamespace(
            TEXT="text", PASSWORD="password", EMAIL="email", URL="url", TEL="tel"),
        "SelectSelectorMode": _mode,
        "NumberSelectorMode": _mode,
    })
    _module("homeassistant.helpers.entity", Entity=object)
    _module("homeassistant.helpers.area_registry", async_get=_Any)
    _module("homeassistant.helpers.label_registry", async_get=_Any)
    _module("homeassistant.helpers.floor_registry", async_get=_Any)
    _module("homeassistant.helpers.device_registry",
            DeviceInfo=dict, DeviceEntryType=types.SimpleNamespace(SERVICE="service"),
            async_get=_Any,
            async_get_effective_area_id=lambda hass, device: device.area_id)
    _module("homeassistant.helpers.entity_platform", AddEntitiesCallback=_Any,
            AddConfigEntryEntitiesCallback=_Any)
    _module("homeassistant.helpers.restore_state", RestoreEntity=object)
    _module("homeassistant.helpers.dispatcher",
            async_dispatcher_send=lambda *a, **k: None,
            async_dispatcher_connect=lambda *a, **k: (lambda: None))
    def _track(hass, entity_ids, action, *a, **k):
        ids = [entity_ids] if isinstance(entity_ids, str) else list(entity_ids)
        for entity_id in ids:
            STATE_LISTENERS.setdefault(entity_id, []).append(action)

        def _remove():
            for entity_id in ids:
                with __import__("contextlib").suppress(ValueError):
                    STATE_LISTENERS.get(entity_id, []).remove(action)
        return _remove

    def _call_later(hass, delay, action):
        loop = asyncio.get_event_loop()
        handle = loop.call_later(delay, lambda: action(None))
        return handle.cancel

    _module("homeassistant.helpers.event",
            async_track_state_change_event=_track,
            async_call_later=_call_later,
            async_track_time_interval=lambda *a, **k: (lambda: None))

    async def _get_translations(hass, language, category, integrations=None,
                                config_flow=None):
        return {k: v for (lang, k), v in TRANSLATIONS.items()
                if lang == language and f".{category}." in k}

    _module("homeassistant.helpers.translation",
            async_get_translations=_get_translations)
    _module("homeassistant.helpers.network", get_url=lambda *a, **k: "https://ha.test",
            NoURLAvailableError=type("NoURLAvailableError", (Exception,), {}))
    _module("homeassistant.helpers.aiohttp_client",
            async_get_clientsession=lambda *a, **k: _Any())
    # תיקונים (repairs): נרשמים במילון, כדי שבדיקה תראה מה נפתח ונסגר.
    ISSUES.clear()
    _module("homeassistant.helpers.issue_registry",
            IssueSeverity=types.SimpleNamespace(ERROR="error", WARNING="warning"),
            async_create_issue=lambda hass, domain, issue_id, **kw:
                ISSUES.__setitem__(issue_id, kw),
            async_delete_issue=lambda hass, domain, issue_id:
                ISSUES.pop(issue_id, None))
    class _EntityRegistry:
        """מרשם מינימלי: רק החיפוש שהלוויין עושה בו."""

        def __init__(self):
            self.entities = {}

        def async_get_entity_id(self, domain, platform, unique_id):
            return self.entities.get((domain, platform, unique_id))

        def async_get(self, entity_id):
            return None

    _registry = _EntityRegistry()
    _module("homeassistant.helpers.entity_registry",
            async_get=lambda hass: _registry)
    import datetime as _dt

    _tz = _dt.timezone(_dt.timedelta(hours=2))

    def _parse(value, raise_on_error=False):
        try:
            return _dt.datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _as_local(value):
        return value.astimezone(_tz) if value.tzinfo else value.replace(tzinfo=_tz)

    _dtmod = types.SimpleNamespace(
        utcnow=lambda: _dt.datetime.now(_dt.timezone.utc),
        now=lambda: _dt.datetime.now(_tz),
        parse_datetime=_parse,
        as_local=_as_local,
    )
    _module("homeassistant.util", dt=_dtmod)
    _module("homeassistant.util.dt", **vars(_dtmod))

    comps = _module("homeassistant.components")
    comps.__path__ = []
    _module("homeassistant.components.http", HomeAssistantView=object,
            StaticPathConfig=lambda *a, **k: (a, k))
    # לוח המקשים: הרישום נשמר כדי שבדיקה תראה מה נרשם, והמעטרים של
    # פקודת ה-WebSocket שקופים — הפקודה נבדקת דרך `panel.async_run`.
    PANELS.clear()

    async def _register_panel(hass, **kwargs):
        PANELS.append(kwargs)

    _module("homeassistant.components.panel_custom",
            async_register_panel=_register_panel)
    _module("homeassistant.components.websocket_api",
            websocket_command=lambda schema: (lambda func: func),
            require_admin=_passthrough, async_response=_passthrough,
            async_register_command=lambda hass, command: None)
    # קבועי פורמט ההקראה. הלוויין מבקש דרכם WAV בקצב של הספק —
    # בלעדיהם הצינור מחזיר mp3.
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
    def _rounded(hass, entity_id, state):
        # כמו ב-core: לפי `display_precision` שבאפשרויות של הרישום.
        precision = getattr(state, "precision", None)
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return state.state
        return str(round(value, precision)) if precision is not None else state.state

    _module("homeassistant.components.sensor", RestoreSensor=object,
            async_rounded_state=_rounded,
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
            PipelineStage=types.SimpleNamespace(STT="stt", INTENT="intent", TTS="tts"),
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
            # כמו ב-Entity: שם מפורש, אחרת השם לפי translation_key.
            if hasattr(self, "_attr_name"):
                return self._attr_name
            key = getattr(self, "_attr_translation_key", None)
            extra = getattr(self, "_attr_translation_placeholders", None) or {}
            return f"{key}{''.join(f':{v}' for v in extra.values())}" if key else None

        @property
        def supported_features(self):
            return self._attr_supported_features

        @property
        def tts_options(self):
            return self._attr_tts_options

        def tts_response_finished(self):
            self.state = "idle"

        def _resolve_vad_sensitivity(self):
            return 0.7

        async def async_accept_pipeline_from_satellite(
            self, audio_stream, start_stage="stt", end_stage="tts",
            wake_word_phrase=None, *, context=None
        ):
            # כמו במקור: ההגדרות נבנות כאן, ואין דרך להעביר אותן מבחוץ.
            ACCEPTED.append(
                AudioSettings(silence_seconds=self._resolve_vad_sensitivity())
            )
            async for _ in audio_stream:
                pass

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


# מה שהבדיקה מזריקה: מיפוי (מפתח יעד, מזהה) לרשימת ישויות,
# למשל ("area_id", "mtbh"). החרגה נפתרת באותו מיפוי.
TARGETS: dict = {}


class FakeTargetSelection:
    def __init__(self, config) -> None:
        self.config = dict(config)


def _target_ids(config) -> set:
    found = set()
    for key in ("area_id", "floor_id", "label_id", "device_id"):
        for ident in config.get(key) or ():
            found |= set(TARGETS.get((key, ident), ()))
    return found


def fake_extract_referenced(hass, selection, *a, **k):
    config = selection.config
    direct = set(config.get("entity_id") or ())
    excluded = _target_ids(config.get("exclude") or {}) | set(
        (config.get("exclude") or {}).get("entity_id") or ()
    )
    return types.SimpleNamespace(
        referenced=direct - excluded,
        indirectly_referenced=_target_ids(config) - direct - excluded,
    )


def fake_extract_excluded(hass, selection, *a, **k):
    exclude = selection.config.get("exclude") or {}
    return _target_ids(exclude) | set(exclude.get("entity_id") or ())


class FakeState:
    def __init__(self, state, **attributes) -> None:
        self.state = state
        self.attributes = attributes
        self.entity_id = ""


class FakeStates:
    def __init__(self, mapping=None) -> None:
        self._states = dict(mapping or {})
        for entity_id, state in self._states.items():
            if getattr(state, "entity_id", None) == "":
                state.entity_id = entity_id

    def get(self, entity_id):
        return self._states.get(entity_id)

    def set(self, entity_id, state) -> None:
        """שינוי מצב, עם אירוע למאזינים — כמו `state_changed` אמיתי."""
        old = self._states.get(entity_id)
        if getattr(state, "entity_id", None) == "":
            state.entity_id = entity_id
        self._states[entity_id] = state
        event = types.SimpleNamespace(
            data={"entity_id": entity_id, "old_state": old, "new_state": state})
        for listener in list(STATE_LISTENERS.get(entity_id, [])):
            listener(event)

    def async_all(self, domain=None):
        return [
            types.SimpleNamespace(entity_id=e, state=s.state, attributes=s.attributes)
            for e, s in self._states.items()
            if domain is None or e.split(".", 1)[0] in ([domain] if isinstance(domain, str) else domain)
        ]


class FakeServices:
    def __init__(self) -> None:
        self.calls = []

    def has_service(self, *a):
        return False

    def async_register(self, *a, **k):
        return None

    # תשובות לשירותי תגובה, שהבדיקה מזריקה: (domain, service) -> dict.
    RESPONSES: dict = {}

    async def async_call(self, domain, service, data, blocking=False,
                         return_response=False):
        self.calls.append((domain, service, dict(data)))
        if return_response:
            return self.RESPONSES.get((domain, service), {})
        return None


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
        self.unique_id = None
        self.title = "IVR"
        self.domain = "ha_ivr"
        self.reauths = 0
        self.unloads = []

    def async_start_reauth(self, hass, context=None, data=None):
        self.reauths += 1

    def async_on_unload(self, func):
        self.unloads.append(func)


class FakeSubentry:
    """תת-רשומה, עם אותם שדות שהליבה קוראת מהאמיתית."""

    _count = 0

    def __init__(self, *, data, subentry_type, title, unique_id=None,
                 subentry_id=None) -> None:
        FakeSubentry._count += 1
        self.data = data
        self.subentry_type = subentry_type
        self.title = title
        self.unique_id = unique_id
        self.subentry_id = subentry_id or f"sub{FakeSubentry._count}"


class FakeConfigEntries:
    """הרשומות, וכתיבת תת-רשומות כמו ב-HA: עדכון מחליף את העצם."""

    def __init__(self, entries) -> None:
        self._entries = entries
        self.writes = 0

    def async_entries(self, domain):
        return list(self._entries)

    def async_add_subentry(self, entry, subentry):
        self.writes += 1
        entry.subentries[subentry.subentry_id] = subentry
        return True

    def async_update_subentry(self, entry, subentry, *, data=None, title=None,
                              unique_id=None):
        self.writes += 1
        entry.subentries[subentry.subentry_id] = FakeSubentry(
            data=subentry.data if data is None else data,
            subentry_type=subentry.subentry_type,
            title=subentry.title if title is None else title,
            unique_id=subentry.unique_id,
            subentry_id=subentry.subentry_id,
        )
        return True

    def async_remove_subentry(self, entry, subentry_id):
        self.writes += 1
        del entry.subentries[subentry_id]
        return True

    def async_update_entry(self, entry, *, data=None, options=None, unique_id=None,
                           minor_version=None, **_kw):
        """כמו ב-HA: מחזיר אם משהו השתנה בפועל."""
        self.writes += 1
        changed = False
        if data is not None and dict(data) != dict(entry.data):
            entry.data, changed = dict(data), True
        if options is not None and dict(options) != dict(entry.options):
            entry.options, changed = dict(options), True
        if unique_id is not None and unique_id != getattr(entry, "unique_id", None):
            entry.unique_id, changed = unique_id, True
        if minor_version is not None:
            entry.minor_version = minor_version
        return changed

    reloads: list = []

    def async_schedule_reload(self, entry_id):
        self.reloads.append(entry_id)

    def async_get_entry(self, entry_id):
        return next((e for e in self._entries if e.entry_id == entry_id), None)


class FakeHass:
    def __init__(self, states=None, entries=None) -> None:
        self.states = FakeStates(states)
        self.services = FakeServices()
        self.bus = FakeBus()
        self.config_entries = FakeConfigEntries(entries or [FakeEntry()])
        self.data: dict = {}
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
