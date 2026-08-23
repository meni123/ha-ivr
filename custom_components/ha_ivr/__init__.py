"""ha_ivr — תפריט טלפוני ועוזר קולי, מול שלושה ספקי טלפוניה.

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

import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ha_ivr"

# הספק של הרשומה, בשדה `data`. נקבע בשלב הראשון של הטופס.
CONF_PROVIDER = "provider"


def build_stamp() -> str:
    """זהות הקוד שרץ בפועל: גרסה ועוד טביעת אצבע של הקבצים.

    מספר הגרסה לבדו אינו מספיק. שני עותקים שסומנו שניהם `0.23.0`
    נמצאו שונים זה מזה ביותר ממאה שורות — אחד בתיקיית הפיתוח ואחד
    בתוך `custom_components` — ומהיומן לא הייתה שום דרך לדעת מי
    מהם עונה לטלפון. אבחון מול הקוד הלא נכון גרוע מאין אבחון.

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

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.const import Platform
    from homeassistant.core import ServiceCall
    from homeassistant.exceptions import HomeAssistantError

    from . import registry
    from .const import SATELLITES, SERVICE_SEND_CALL
    from .outbound import OutboundError, clean_phones
    from .providers import ensure_registered as PROVIDERS_REGISTER
    from .stream import StreamView
    from .view import IvrView
except ImportError:  # pragma: no cover — בדיקות הליבה רצות בלי HA
    _HA = False
else:
    _HA = True


if _HA:

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
        _LOGGER.info(
            "ha_ivr %s is running: /api/ha_ivr/<provider>/<token> and streaming at /api/ha_ivr/stream/<token>",
            stamp,
        )
        return True


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

    async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        driver = registry.for_entry(entry)
        if driver is None:
            _LOGGER.error(
                "Entry %s names an unknown provider: %r",
                entry.entry_id, entry.data.get(CONF_PROVIDER),
            )
            return False

        entry.async_on_unload(entry.add_update_listener(_reload))

        if not hass.services.has_service(DOMAIN, SERVICE_SEND_CALL):
            hass.services.async_register(
                DOMAIN, SERVICE_SEND_CALL, _handle_send_call(hass),
                schema=_send_call_schema(),
            )

        await hass.config_entries.async_forward_entry_setups(
            entry, _platforms(driver)
        )
        return True

    async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        from .view import reset_warnings  # noqa: PLC0415

        reset_warnings()
        driver = registry.for_entry(entry)
        if driver is None:
            return True

        unloaded = await hass.config_entries.async_unload_platforms(
            entry, _platforms(driver)
        )
        # השירות יורד רק עם הרשומה האחרונה: הוא של הדומיין, לא
        # של הרשומה, ומי שמסיר ספק אחד מתוך שניים עדיין צריך אותו.
        if unloaded and len(hass.config_entries.async_entries(DOMAIN)) <= 1:
            hass.services.async_remove(DOMAIN, SERVICE_SEND_CALL)
        return unloaded

    async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
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
            if entry is None:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="unknown_entry"
                )
            # `ConfigEntrySelector` אינו יודע לסנן לפי יכולת,
            # ולכן הבורר מציע גם ספק בלי מסלול יוצא. הבדיקה כאן
            # הופכת בחירה שגויה להודעה ברורה.
            driver = registry.for_entry(entry)
            if driver is None or getattr(driver, "async_notify", None) is None:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="provider_no_alerts",
                    translation_placeholders={
                        "provider": str(getattr(driver, "NAME", entry.title))
                    },
                )

            lines = (hass.data.get(SATELLITES) or {}).get(entry.entry_id) or []
            if not lines:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="no_satellite"
                )
            raw = str(call.data["phones"])
            phones = [p for p in clean_phones(raw).split(",") if p]
            if not phones:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="no_valid_numbers_in",
                    translation_placeholders={"input": raw},
                )
            try:
                await lines[0].async_announce_message(
                    str(call.data["message"]), phones
                )
            except OutboundError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key=err.key or "outbound_failed",
                    translation_placeholders=err.placeholders
                    or {"error": str(err)},
                ) from err

        return handle
