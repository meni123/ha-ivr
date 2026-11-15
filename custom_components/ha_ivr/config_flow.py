"""טופס ההגדרה.

רשומה לכל ספק, אינטגרציה אחת. השלב הראשון בוחר ספק, וכל מה
שאחריו מציג את השדות שלו בלבד — כולל הסתרת מסך "עוזר קולי" אצל
ספק בלי ערוץ סטרימינג.

השדות המשותפים והמסכים של תת-הרשומות מגיעים מ-`config_shared`;
מה שייחודי לספק מגיע מהמודול שלו ב-`providers/`, דרך
`menu_fields` ו-`menu_save`.
"""

from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import registry
from .providers import ensure_registered
from .config_shared import (
    AlertsFlowHandler,
    AssistantFlowHandler,
    ContactFlowHandler,
    GoToFlowHandler,
    DeviceFlowHandler,
    SmartGroupFlowHandler,
    SubMenuFlowHandler,
    csv_list,
    endpoint_urls,
    from_form,
    ip_errors,
    stream_schema,
)
from .const import (
    CONF_INTRO,
    DOMAIN,
    SUBENTRY_TYPE_ALERTS,
    SUBENTRY_TYPE_CONTACT,
    SUBENTRY_TYPE_ASSISTANT,
    SUBENTRY_TYPE_GOTO,
    SUBENTRY_TYPE_ITEM,
    SUBENTRY_TYPE_GROUP,
    SUBENTRY_TYPE_SUBMENU,
)

CONF_PROVIDER = "provider"


def _provider_selector() -> SelectSelector:
    """בורר הספק, מתוך המרשם.

    ספק רביעי מופיע כאן מעצמו ברגע שהמודול שלו נטען — אין רשימה
    שנייה לתחזק.
    """
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(
                    value=d.DRIVER_ID, label=getattr(d, "NAME", d.DRIVER_ID)
                )
                for d in registry.all_drivers()
            ],
            mode=SelectSelectorMode.LIST,
            sort=False,
        )
    )


async def _menu_schema(hass, driver, current: dict[str, Any]) -> vol.Schema:
    """שדות התפריט: המשותפים, ואז מה שהספק מוסיף.

    ספק שצריך לשאול משהו כדי לבנות את השדות (למשל רשימת בחירה מהצד
    השני) מגדיר `async_menu_fields`; אחרת `menu_fields` הסינכרוני.
    """
    fields: dict[Any, Any] = {
        vol.Optional(
            CONF_INTRO, description={"suggested_value": current.get(CONF_INTRO, "")}
        ): str,
    }
    build = getattr(driver, "async_menu_fields", None)
    fields.update(
        await build(hass, current) if build else driver.menu_fields(current)
    )
    # טווחי IP מגינים על נקודת קצה; קו שהשיחה מגיעה בו עצמו אין לו כזו.
    if getattr(driver, "HAS_ENDPOINT", True):
        fields[
            vol.Optional(
                "provider_ips",
                description={
                    "suggested_value": ", ".join(current.get("allowed_ips") or [])
                    or driver.default_ips()
                },
            )
        ] = str
    fields[
        vol.Optional(
            "allowed_phones",
            description={
                "suggested_value": ", ".join(current.get("allowed_phones") or [])
            },
        )
    ] = str
    return vol.Schema(fields)


def _line_taken(hass, driver, user_input: dict[str, Any], skip: str) -> bool:
    """האם הקו שבטופס כבר מוגדר ברשומה אחרת של אותו ספק."""
    key = getattr(driver, "entry_key", None)
    if key is None:
        return False
    mine = key(driver.menu_save(user_input))
    return any(
        entry.entry_id != skip
        and entry.data.get(CONF_PROVIDER) == driver.DRIVER_ID
        and key(dict(entry.options)) == mine
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


async def _menu_errors(
    hass, driver, user_input: dict[str, Any], skip: str = ""
) -> dict[str, str]:
    """שגיאות הטופס: טווחי IP, קו כפול, ומה שהספק בודק בעצמו.

    `skip` היא הרשומה שנערכת עכשיו — היא אינה כפילות של עצמה.
    """
    errors = ip_errors(user_input)
    if not errors and _line_taken(hass, driver, user_input, skip):
        errors["base"] = "line_exists"
    check = getattr(driver, "async_menu_errors", None)
    if check is not None and not errors:
        errors.update(await check(hass, user_input))
    return errors


def _menu_save(driver, user_input: dict[str, Any]) -> dict[str, Any]:
    saved = {
        CONF_INTRO: user_input.get(CONF_INTRO, ""),
        "allowed_ips": csv_list(user_input.get("provider_ips")),
        "allowed_phones": csv_list(user_input.get("allowed_phones")),
    }
    saved.update(driver.menu_save(user_input))
    return saved


class IvrConfigFlow(ConfigFlow, domain=DOMAIN):
    """הגדרה ראשונית: איזה ספק, ואז השדות שלו."""

    VERSION = 1
    # 2: ישות חכמה ותפריט אזור אוחדו לתוך מכשיר ותת-תפריט.
    # 3: העוזר הקולי הוא סוג משלו ולא מעבר עם יעד מוסכם.
    MINOR_VERSION = 3

    def __init__(self) -> None:
        self._provider = ""

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        ensure_registered()
        if user_input is not None:
            self._provider = str(user_input[CONF_PROVIDER])
            # רשומה אחת לכל ספק: שתיים לאותו ספק היו חולקות
            # טוקן ושלוחה, והשיחה הייתה מגיעה לאחת מהן שרירותית.
            # ספק שכל רשומה שלו היא קו נפרד מכריז על כך בעצמו.
            driver = registry.get(self._provider)
            if not getattr(driver, "MANY_ENTRIES", False):
                await self.async_set_unique_id(self._provider)
                self._abort_if_unique_id_configured()
            return await self.async_step_settings()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_PROVIDER): _provider_selector()}),
        )

    async def async_step_settings(self, user_input=None) -> ConfigFlowResult:
        ensure_registered()
        driver = registry.get(self._provider)
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await _menu_errors(self.hass, driver, user_input)
            if not errors:
                saved = _menu_save(driver, user_input)
                title = getattr(driver, "entry_title", None)
                return self.async_create_entry(
                    title=(
                        title(saved) if title is not None
                        else getattr(driver, "NAME", self._provider)
                    ),
                    data={
                        CONF_PROVIDER: self._provider,
                        "token": secrets.token_urlsafe(24),
                    },
                    options=saved,
                )

        return self.async_show_form(
            step_id="settings",
            data_schema=await _menu_schema(self.hass, driver, user_input or {}),
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_options_flow(cls, config_entry: ConfigEntry) -> OptionsFlow:
        return IvrOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        ensure_registered()
        types: dict[str, type[ConfigSubentryFlow]] = {
            SUBENTRY_TYPE_ITEM: DeviceFlowHandler,
            SUBENTRY_TYPE_GROUP: SmartGroupFlowHandler,
            SUBENTRY_TYPE_SUBMENU: SubMenuFlowHandler,
        }
        driver = registry.for_entry(config_entry)
        # כל כפתור מופיע רק אצל ספק שיש לו מה לעשות איתו: עוזר קולי
        # למי שיש לו ערוץ שמע, ומעבר לשלוחה למי שיש לו שלוחות.
        if getattr(driver, "SUPPORTS_GOTO", False):
            if getattr(driver, "SUPPORTS_STREAM", False):
                types[SUBENTRY_TYPE_ASSISTANT] = AssistantFlowHandler
            if not getattr(driver, "GOTO_ONLY_ASSIST", False):
                types[SUBENTRY_TYPE_GOTO] = GoToFlowHandler
        # נמען הוא תת-רשומה רק אצל מי שיודע לחייג. אצל ספק בלי
        # מסלול יוצא הכפתור היה יוצר ישות שנכשלת בשיחה.
        if driver is not None and getattr(driver, "async_notify", None):
            types[SUBENTRY_TYPE_CONTACT] = ContactFlowHandler
            # שלוחת ההתראות מקריאה מה שנשלח, ולכן היא רלוונטית רק
            # למי שיודע לשלוח התראות.
            types[SUBENTRY_TYPE_ALERTS] = AlertsFlowHandler
        return types


class IvrOptionsFlow(OptionsFlow):
    """שני מסכים: התפריט, והעוזר הקולי למי שיש לו."""

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        ensure_registered()
        driver = registry.for_entry(self.config_entry)
        menu = ["menu_settings"]
        if getattr(driver, "SUPPORTS_STREAM", False):
            menu.append("stream_settings")
        if not getattr(driver, "HAS_ENDPOINT", True):
            return await self.async_step_line()
        # החלפת הטוקן זמינה לכל ספק: הוא הסוד שמגן על נקודת הקצה,
        # וטוקן שדלף מחליפים.
        menu.append("regenerate_token")
        # הכתובות מוצגות במסך הראשון: זה המקום היחיד בממשק
        # שמראה את הטוקן, ומשם מעתיקים אותו להגדרה אצל הספק.
        return self.async_show_menu(
            step_id="init",
            menu_options=menu,
            description_placeholders=endpoint_urls(
                self.hass, self.config_entry, driver
            ),
        )

    async def async_step_line(self, user_input=None) -> ConfigFlowResult:
        """המסך הראשון של קו בלי נקודת קצה: אין כתובת להציג ואין טוקן להחליף."""
        ensure_registered()
        driver = registry.for_entry(self.config_entry)
        menu = ["menu_settings"]
        if getattr(driver, "SUPPORTS_STREAM", False):
            menu.append("stream_settings")
        return self.async_show_menu(step_id="line", menu_options=menu)

    async def async_step_regenerate_token(
        self, user_input=None
    ) -> ConfigFlowResult:
        """יצירת טוקן חדש לנקודת הקצה, למקרה שהישן דלף.

        הטוקן מגן על נקודת הקצה — מי שמחזיק בו יכול להריץ את
        התפריט. אחרי החלפה יש לעדכן את הכתובת החדשה אצל הספק,
        אחרת השיחות ייעצרו: הטוקן הישן מפסיק לעבוד מיד.
        """
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    "token": secrets.token_urlsafe(24),
                },
            )
            return self.async_abort(reason="token_regenerated")

        return self.async_show_form(
            step_id="regenerate_token", data_schema=vol.Schema({})
        )

    async def async_step_menu_settings(self, user_input=None) -> ConfigFlowResult:
        ensure_registered()
        driver = registry.for_entry(self.config_entry)
        current = dict(self.config_entry.options)
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await _menu_errors(
                self.hass, driver, user_input, self.config_entry.entry_id
            )
            if not errors:
                return self.async_create_entry(
                    data={**current, **_menu_save(driver, user_input)}
                )

        return self.async_show_form(
            step_id="menu_settings",
            data_schema=await _menu_schema(
                self.hass, driver, {**current, **(user_input or {})}
            ),
            errors=errors,
        )

    async def async_step_stream_settings(self, user_input=None) -> ConfigFlowResult:
        ensure_registered()
        driver = registry.for_entry(self.config_entry)
        current = dict(self.config_entry.options)

        if user_input is not None:
            merged = {**current, **{k: from_form(v) for k, v in user_input.items()}}
            return self.async_create_entry(data=merged)

        return self.async_show_form(
            step_id="stream_settings",
            data_schema=stream_schema(
                current,
                # לפי דגלים על הדרייבר ולא לפי שם ספק, כדי
                # שספק חדש לא יחייב עריכה כאן.
                channel_token=getattr(driver, "NEEDS_CHANNEL_TOKEN", False),
                return_path=getattr(driver, "NEEDS_RETURN_PATH", False),
                rate=getattr(driver, "NEEDS_RATE", False),
            ),
        )
