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
    ContactFlowHandler,
    GoToFlowHandler,
    MenuItemFlowHandler,
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
    SUBENTRY_TYPE_GOTO,
    SUBENTRY_TYPE_ITEM,
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


def _menu_schema(driver, current: dict[str, Any]) -> vol.Schema:
    """שדות התפריט: המשותפים, ואז מה שהספק מוסיף."""
    fields: dict[Any, Any] = {
        vol.Optional(
            CONF_INTRO, description={"suggested_value": current.get(CONF_INTRO, "")}
        ): str,
    }
    fields.update(driver.menu_fields(current))
    fields.update(
        {
            vol.Optional(
                "provider_ips",
                description={
                    "suggested_value": ", ".join(current.get("allowed_ips") or [])
                    or driver.default_ips()
                },
            ): str,
            vol.Optional(
                "allowed_phones",
                description={
                    "suggested_value": ", ".join(current.get("allowed_phones") or [])
                },
            ): str,
        }
    )
    return vol.Schema(fields)


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

    def __init__(self) -> None:
        self._provider = ""

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        ensure_registered()
        if user_input is not None:
            self._provider = str(user_input[CONF_PROVIDER])
            # רשומה אחת לכל ספק: שתיים לאותו ספק היו חולקות
            # טוקן ושלוחה, והשיחה הייתה מגיעה לאחת מהן שרירותית.
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
            errors = ip_errors(user_input)
            if not errors:
                return self.async_create_entry(
                    title=getattr(driver, "NAME", self._provider),
                    data={
                        CONF_PROVIDER: self._provider,
                        "token": secrets.token_urlsafe(24),
                    },
                    options=_menu_save(driver, user_input),
                )

        return self.async_show_form(
            step_id="settings",
            data_schema=_menu_schema(driver, user_input or {}),
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
            SUBENTRY_TYPE_ITEM: MenuItemFlowHandler,
            SUBENTRY_TYPE_SUBMENU: SubMenuFlowHandler,
            SUBENTRY_TYPE_GOTO: GoToFlowHandler,
        }
        # נמען הוא תת-רשומה רק אצל מי שיודע לחייג. אצל ספק בלי
        # מסלול יוצא הכפתור היה יוצר ישות שנכשלת בשיחה.
        driver = registry.for_entry(config_entry)
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
        # הכתובות מוצגות במסך הראשון: זה המקום היחיד בממשק
        # שמראה את הטוקן, ומשם מעתיקים אותו להגדרה אצל הספק.
        return self.async_show_menu(
            step_id="init",
            menu_options=menu,
            description_placeholders=endpoint_urls(
                self.hass, self.config_entry, driver
            ),
        )

    async def async_step_menu_settings(self, user_input=None) -> ConfigFlowResult:
        ensure_registered()
        driver = registry.for_entry(self.config_entry)
        current = dict(self.config_entry.options)
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = ip_errors(user_input)
            if not errors:
                return self.async_create_entry(
                    data={**current, **_menu_save(driver, user_input)}
                )

        return self.async_show_form(
            step_id="menu_settings",
            data_schema=_menu_schema(driver, current),
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
