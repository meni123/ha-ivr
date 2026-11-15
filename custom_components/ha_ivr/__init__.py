"""ha_ivr — תפריט טלפוני ועוזר קולי, מול ספקי טלפוניה או קו SIP ישיר.

אינטגרציה אחת, רשומה לכל ספק. מי שמפעיל שניים רואה שני כרטיסים
נפרדים תחת שורה אחת, וכל רשומה מחזיקה עץ תפריטים משלה, טוקן
משלה וישויות משלה.

מה שהספק מביא הוא הפורמט שלו בלבד — מודול אחד ב-`providers/`.
כל השאר משותף: המודל, המקודד, העץ, בניית התפריט מתת-הרשומות,
נקודת הקצה, גשר הסטרימינג, הצינור, ההתראות והמדיניות.

### מה נרשם

שתי נקודות קצה, פעם אחת לכל HA:

    /api/ha_ivr/{driver}/{token}    התפריט
    /api/ha_ivr/stream/{token}      העוזר הקולי

הניתוב הוא לפי המרשם ולא לפי ייבוא. הליבה אינה מכירה אף ספק
בשם, ובדיקה בשער נכשלת אם שם ספק מופיע בקוד הליבה.

### הפלטפורמות נגזרות מהיכולות

    SENSOR                      תמיד
    NOTIFY                      אם לספק יש `async_notify`
    ASSIST_SATELLITE, SELECT    אם `SUPPORTS_STREAM`

לימות אין ערוץ סטרימינג, ולכן אין לו לוויין, אין בוררים, ואין
מסך "עוזר קולי" בהגדרות. זה נגזר משורה אחת בדרייבר.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import logging
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ha_ivr"

# הספק של הרשומה, בשדה `data`. נקבע בשלב הראשון של הטופס.
CONF_PROVIDER = "provider"


def build_stamp() -> str:
    """זהות הקוד שרץ בפועל: גרסה ועוד טביעת אצבע של הקבצים.

    מספר הגרסה לבדו אינו מספיק: שני עותקים באותו מספר גרסה —
    אחד בתיקיית הפיתוח ואחד בתוך `custom_components` — יכולים
    להיות שונים זה מזה, ובלי הטביעה אין ביומן דרך לדעת מי מהם
    עונה לטלפון. אבחון מול הקוד הלא נכון גרוע מאין אבחון.

    הטביעה נגזרת מתוכן הקבצים ומשמותיהם, ולכן אינה יכולה להתפצל
    מהם: קובץ שנשאר מגרסה קודמת משנה אותה כמו שורה שהשתנתה.

    חוסמת קלט/פלט. יש לקרוא לה דרך executor ולא על לולאת האירועים.
    """
    import hashlib  # noqa: PLC0415
    import json  # noqa: PLC0415
    import pathlib  # noqa: PLC0415

    core = pathlib.Path(__file__).parent
    # החבילה כולה, כולל `providers/`: שינוי בדרייבר של ספק חייב
    # להזיז את החתימה, אחרת היומן מצהיר על אותה חתימה על קוד אחר.
    packages = [core]
    digest = hashlib.sha256()
    # כל העץ, לא רק קוד: `services.yaml`, המניפסט והתרגומים משנים
    # את מה שהמשתמש רואה ומה שהספק מקבל בדיוק כמו שורת פייתון.
    # מטמון בייטקוד מדולג — הוא נגזר, ומשתנה לפי גרסת המפרש.
    for pkg in packages:
        for path in sorted(pkg.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            digest.update(path.relative_to(core).as_posix().encode())
            digest.update(path.read_bytes())

    version = "?"
    try:
        manifest = json.loads((core / "manifest.json").read_text("utf-8"))
        version = str(manifest.get("version", "?"))
    except Exception:  # noqa: BLE001 — הטביעה שווה גם בלי המניפסט
        pass
    return f"{version}+{digest.hexdigest()[:8]}"


try:
    from homeassistant.core import HomeAssistant

    from homeassistant.config_entries import ConfigEntry, ConfigEntryState
    from homeassistant.const import Platform
    from homeassistant.core import ServiceCall, callback
    from homeassistant.exceptions import (
        ConfigEntryError,
        HomeAssistantError,
        ServiceValidationError,
    )
    from homeassistant.helpers import config_validation as cv

    from . import registry
    from .const import SATELLITES, SERVICE_SEND_CALL
    from .entity import ensure_parent_device
    from .outbound import OutboundError, clean_phones
    from .providers import ensure_registered as PROVIDERS_REGISTER
    from .stream import StreamView
    from .view import IvrView
except ImportError:  # pragma: no cover — בדיקות הליבה רצות בלי HA
    _HA = False
else:
    _HA = True


if _HA:

    # האינטגרציה מוגדרת רק מהממשק; שורה ב-configuration.yaml נדחית עם הודעה.
    CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

    @dataclass
    class IvrRuntime:
        """מה שהרשומה מחזיקה בזמן ריצה. נבנה מחדש בכל טעינה."""

        driver: Any
        platforms: list = field(default_factory=list)

    async def async_setup(hass: HomeAssistant, config: dict) -> bool:
        """רישום נקודות הקצה, פעם אחת לכל HA.

        נקרא בידי HA כשהאינטגרציה הראשונה שתלויה בליבה נטענת.
        השאר מקבלות אותן נקודות קצה בלי לרשום דבר — הניתוב פנימי,
        לפי המרשם.
        """
        if hass.data.get(DOMAIN, {}).get("views"):
            return True

        # כל הספקים נרשמים תמיד, בלי קשר לרשומות המוגדרות: כך
        # בורר הספק בטופס מלא, והמרשם הוא המקור היחיד לשאלה מי
        # קיים.
        PROVIDERS_REGISTER()

        stamp = await hass.async_add_executor_job(build_stamp)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["build"] = stamp
        hass.data[DOMAIN]["views"] = True

        hass.http.register_view(IvrView(hass))
        hass.http.register_view(StreamView(hass))

        # השירות של הדומיין ולא של רשומה: כך הוא קיים גם כשאין רשומה
        # טעונה, ומחזיר שגיאה ברורה במקום "שירות לא נמצא".
        hass.services.async_register(
            DOMAIN, SERVICE_SEND_CALL, _handle_send_call(hass),
            schema=_send_call_schema(),
        )

        # הלוח הוא נוחות. כשל ברישום שלו אינו מפיל את הקווים.
        try:
            from . import panel  # noqa: PLC0415

            await panel.async_register(hass, stamp)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("ha_ivr: the keypad panel could not be registered")
        _LOGGER.info(
            "ha_ivr %s is running: /api/ha_ivr/<provider>/<token> and streaming at /api/ha_ivr/stream/<token>",
            stamp,
        )
        return True


    async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        """המרת תת-רשומות שמורות לסוגים הקיימים.

        1.2: ישות חכמה הופכת למכשיר, ותפריט אזור לתת-תפריט. המזהה של
        כל תת-רשומה נשמר, ולסוגים האלה אין ישויות או התקנים, כך
        שההמרה אינה נוגעת בשום דבר מחוץ לרשומה.
        """
        if entry.version > 1:
            return False
        if entry.minor_version < 2:
            from homeassistant.config_entries import ConfigSubentry  # noqa: PLC0415

            from .menu import merged_type  # noqa: PLC0415

            for subentry in list(entry.subentries.values()):
                merged = merged_type(subentry)
                if merged is None:
                    continue
                kind, data = merged
                hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)
                hass.config_entries.async_add_subentry(
                    entry,
                    ConfigSubentry(
                        data=MappingProxyType(data),
                        subentry_type=kind,
                        title=subentry.title,
                        unique_id=subentry.unique_id,
                        subentry_id=subentry.subentry_id,
                    ),
                )
            hass.config_entries.async_update_entry(entry, minor_version=2)
        if entry.minor_version < 3:
            # 1.3: מעבר שהוא בעצם העוזר הקולי הופך לסוג העוזר.
            from homeassistant.config_entries import ConfigSubentry  # noqa: PLC0415

            from .const import SUBENTRY_TYPE_ASSISTANT  # noqa: PLC0415
            from .menu import assistant_type  # noqa: PLC0415

            driver = registry.for_entry(entry)
            for subentry in list(entry.subentries.values()):
                data = assistant_type(subentry, driver)
                if data is None:
                    continue
                hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)
                hass.config_entries.async_add_subentry(
                    entry,
                    ConfigSubentry(
                        data=MappingProxyType(data),
                        subentry_type=SUBENTRY_TYPE_ASSISTANT,
                        title=subentry.title,
                        unique_id=subentry.unique_id,
                        subentry_id=subentry.subentry_id,
                    ),
                )
            hass.config_entries.async_update_entry(entry, minor_version=3)
        if entry.minor_version < 4:
            _migrate_line_id(hass, entry)
            hass.config_entries.async_update_entry(entry, minor_version=4)
        return True

    @callback
    def _migrate_line_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """1.4: לקו שכל רשומה שלו נפרדת (SIP) יש unique_id לפי החשבון.

        אידמפוטנטי: רשומה שכבר יש לה מזהה אינה נוגעת. כפילות ישנה —
        שתי רשומות לאותו חשבון — אינה נפתרת כאן בשקט: המזהה לא נקבע,
        ונפתחת תקלה שמבקשת למחוק אחת מהן.
        """
        if entry.unique_id:
            return
        driver = registry.for_entry(entry)
        key = getattr(driver, "entry_key", None)
        if key is None or not getattr(driver, "MANY_ENTRIES", False):
            return
        line_id = str(key(copy.deepcopy(dict(entry.options))) or "")
        if not line_id.strip("@"):
            return
        other = next(
            (
                e for e in hass.config_entries.async_entries(DOMAIN)
                if e.entry_id != entry.entry_id and e.unique_id == line_id
            ),
            None,
        )
        if other is not None:
            from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

            _LOGGER.warning(
                "Entry %s duplicates the line of entry %s",
                entry.entry_id, other.entry_id,
            )
            ir.async_create_issue(
                hass, DOMAIN, f"duplicate_line_{entry.entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="duplicate_line",
                translation_placeholders={"line": line_id, "other": str(other.title)},
            )
            return
        hass.config_entries.async_update_entry(entry, unique_id=line_id)

    def _platforms(driver) -> list:
        """הפלטפורמות שהספק הזה מצדיק.

        נגזר מהיכולות ולא מרשימה קשיחה: ספק בלי ערוץ סטרימינג
        אינו מקבל לוויין ובוררים, וספק בלי מסלול יוצא אינו מקבל
        ישויות נמען. עדיף על ישות שנראית תקינה ונכשלת בשימוש.
        """
        platforms = [Platform.SENSOR]
        if getattr(driver, "async_notify", None) is not None:
            platforms.append(Platform.NOTIFY)
        if getattr(driver, "SUPPORTS_STREAM", False):
            platforms += [Platform.ASSIST_SATELLITE, Platform.SELECT]
        return platforms

    async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
        driver = registry.for_entry(entry)
        if driver is None:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="no_driver",
                translation_placeholders={
                    "provider": str(entry.data.get(CONF_PROVIDER, ""))
                },
            )

        platforms = _platforms(driver)
        entry.runtime_data = IvrRuntime(driver=driver, platforms=platforms)
        entry.async_on_unload(entry.add_update_listener(_reload))
        _shared_start(hass)

        # ההתקן הראשי קודם לפלטפורמות: כל ישות מקשרת אליו לפי מזהה.
        ensure_parent_device(hass, entry)

        await hass.config_entries.async_forward_entry_setups(entry, platforms)

        # תחבורה שאינה HTTP, אם הספק מגדיר אותה — מאזין ה-AudioSocket
        # של מרכזייה עצמית. הליבה אינה יודעת מהי; היא רק מרימה מה
        # שהדרייבר נותן, וסוגרת אותו ב-unload. ספק בלי תחבורה כזו לא
        # מושפע.
        # בדיקת תקינות של הספק, אם יש לו — למשל שמה שמוגדר כאן עוד
        # קיים בצד השני. רצה ברקע, ושוב כל `CHECK_INTERVAL`: מה שנמחק
        # שם נמחק בלי להודיע לנו.
        check = getattr(driver, "async_check", None)
        if check is not None:
            from homeassistant.helpers.event import (  # noqa: PLC0415
                async_track_time_interval,
            )

            async def _check(_now=None, check=check) -> None:
                await check(hass, entry)

            entry.async_create_background_task(
                hass, _check(), f"{DOMAIN} check {entry.entry_id}"
            )
            entry.async_on_unload(
                async_track_time_interval(hass, _check, driver.CHECK_INTERVAL)
            )

        start = getattr(driver, "async_start_transport", None)
        if start is not None:
            try:
                server = await start(hass, entry)
            except OSError as err:
                _LOGGER.error(
                    "Entry %s: the transport listener failed to start: %s",
                    entry.entry_id, err,
                )
            else:
                stop = getattr(driver, "async_stop_transport", None)
                entry.async_on_unload(lambda s=server, f=stop: _stop_transport(f, s))

    async def _stop_transport(stop, server) -> None:
        """סגירת התחבורה של הדרייבר ב-unload, אם הוגדרה."""
        if stop is not None:
            with contextlib.suppress(Exception):
                await stop(server)

    async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
        from . import dictation, history, security  # noqa: PLC0415
        from .view import reset_warnings  # noqa: PLC0415

        reset_warnings()
        runtime = getattr(entry, "runtime_data", None)
        if isinstance(runtime, IvrRuntime):
            platforms = runtime.platforms
        else:
            driver = registry.for_entry(entry)
            if driver is None:
                return
            platforms = _platforms(driver)
        await hass.config_entries.async_unload_platforms_or_raise(entry, platforms)

        # מה שבזיכרון של הרשומה: כרטיסי הכתבה וטיימרי הפקיעה שלהם,
        # ומוני החסימה של קודים. אחרי פריקה לא נשאר טיימר שלה.
        dictation.clear(hass, entry.entry_id)
        security.clear(hass, entry.entry_id)

        # הרשומה האחרונה: גם המאזינים המשותפים יורדים, וההיסטוריה
        # מתנקה כדי שאבחון לא יציג שיחות של הגדרה שכבר אינה.
        loaded = [
            e for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED
        ]
        if not loaded:
            _shared_stop(hass)
            history.clear()

    @callback
    def _shared_start(hass: HomeAssistant) -> None:
        """מה שמשותף לכל הרשומות: מטמון היכולות ותרגומי HA. פעם אחת."""
        shared = hass.data.setdefault(DOMAIN, {}).setdefault("shared", {})
        if shared.get("running"):
            return
        from . import capabilities as caps  # noqa: PLC0415
        from . import i18n  # noqa: PLC0415

        i18n.bind(hass)
        shared["cache_unsub"] = caps.async_setup_cache(hass)
        i18n.async_setup_refresh(hass)
        # התרגום נטען ברקע: עד שהוא מגיע, ההקראה נשענת על המילון המקומי.
        hass.async_create_background_task(
            i18n.async_load(hass), f"{DOMAIN} translations"
        )
        shared["running"] = True

    @callback
    def _shared_stop(hass: HomeAssistant) -> None:
        shared = (hass.data.get(DOMAIN) or {}).get("shared") or {}
        if not shared.get("running"):
            return
        from . import i18n  # noqa: PLC0415

        if unsub := shared.pop("cache_unsub", None):
            with contextlib.suppress(Exception):
                unsub()
        i18n.async_unload(hass)
        shared["running"] = False

    async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """טעינה מחדש אחת לכל רצף של עדכונים.

        לוח המקשים כותב כמה תת-רשומות בפעולה אחת — הזזת תפריט על
        כל מה שבתוכו — וכל כתיבה מעירה את המאזין. בלי האיחוד הרשומה
        הייתה נטענת מחדש פעם לכל כתיבה.
        """
        pending = hass.data[DOMAIN].setdefault("reloading", set())
        if entry.entry_id in pending:
            return
        pending.add(entry.entry_id)
        await asyncio.sleep(0)
        pending.discard(entry.entry_id)
        await hass.config_entries.async_reload(entry.entry_id)

    def _send_call_schema():
        import voluptuous as vol  # noqa: PLC0415
        from homeassistant.helpers import config_validation as cv  # noqa: PLC0415
        from homeassistant.helpers import selector  # noqa: PLC0415

        return vol.Schema(
            {
                vol.Required("config_entry_id"): selector.ConfigEntrySelector(
                    {"integration": DOMAIN}
                ),
                vol.Required("message"): cv.string,
                vol.Required("phones"): cv.string,
                vol.Optional("trunk"): cv.string,
                vol.Optional("caller_id"): cv.string,
                vol.Optional("retries"): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=5)
                ),
            }
        )

    def _handle_send_call(hass: HomeAssistant):
        """התראה קולית עם נמענים מפורשים.

        הרשומה מפורשת בקריאה: עם כמה רשומות באותו דומיין, שירות
        שאינו מקבל יעד היה בוחר אחת מהן שרירותית.
        """

        async def handle(call: ServiceCall) -> None:
            entry = hass.config_entries.async_get_entry(
                str(call.data["config_entry_id"])
            )
            if entry is None or entry.domain != DOMAIN:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="unknown_entry"
                )
            if entry.state is not ConfigEntryState.LOADED:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="entry_not_loaded",
                    translation_placeholders={"entry": str(entry.title)},
                )
            # `ConfigEntrySelector` אינו יודע לסנן לפי יכולת,
            # ולכן הבורר מציע גם ספק בלי מסלול יוצא. הבדיקה כאן
            # הופכת בחירה שגויה להודעה ברורה.
            driver = registry.for_entry(entry)
            if driver is None or getattr(driver, "async_notify", None) is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="provider_no_alerts",
                    translation_placeholders={
                        "provider": str(getattr(driver, "NAME", entry.title))
                    },
                )

            raw = str(call.data["phones"])
            phones = [p for p in clean_phones(raw).split(",") if p]
            if not phones:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="no_valid_numbers_in",
                    translation_placeholders={"input": raw},
                )
            from . import announce as announce_store  # noqa: PLC0415

            message = str(call.data["message"])
            announce_store.log_alert(hass, entry.entry_id, message, phones)
            try:
                # מסלול הסטרימינג — חיוג וחיבור הנמען לשלוחת הזרמה,
                # וההקראה נשלחת מ-HA — קיים רק לספק שמזרים (`async_announce`).
                # ספק שמחייג ומקריא בעצמו, כמו המרכזייה דרך ה-webhook,
                # אין לו satellite כזה; שם `send_call` עובר באותו מסלול
                # של ישות נמען יחיד — `async_notify` עם רשימת המספרים.
                if getattr(driver, "async_announce", None) is not None:
                    lines = (hass.data.get(SATELLITES) or {}).get(
                        entry.entry_id
                    ) or []
                    if not lines:
                        raise HomeAssistantError(
                            translation_domain=DOMAIN,
                            translation_key="no_satellite",
                        )
                    await lines[0].async_announce_message(message, phones)
                else:
                    trunk = str(call.data.get("trunk", "") or "")
                    caller_id = str(call.data.get("caller_id", "") or "")
                    await driver.async_notify(
                        hass, entry, message, phones,
                        trunk=trunk, caller_id=caller_id,
                        retries=int(call.data.get("retries", 0) or 0),
                    )
            except OutboundError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key=err.key or "outbound_failed",
                    translation_placeholders=err.placeholders
                    or {"error": str(err)},
                ) from err

        return handle
