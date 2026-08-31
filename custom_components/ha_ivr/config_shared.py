"""חלקי טופס ההגדרה שאינם תלויים בספק.

בורר הנתיב, שלושת מסכי תת-הרשומות (פריט, תת-תפריט, מעבר) ומסך
העוזר הקולי זהים בשלושת הספקים — הם עוסקים בעץ ובצינור, לא
בפרוטוקול. הם יושבים כאן, וכל אינטגרציית ספק מייבאת אותם
ומוסיפה רק את שדות האישורים שלה.

בלי זה כל ספק היה נושא 428 שורות של טופס זהה, וכל שינוי בבורר
הנתיב היה שלוש עריכות.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .action_fields import (
    action_is_usable,
    async_action_fields,
    async_action_name,
    build_fields_schema,
    build_label_map,
)
from .const import (
    CONF_CHANNEL,
    CONF_TRUNK,
    CONF_STREAM_RATE,
    CONF_PHONE,
    CONF_ACTION,
    CONF_ACTION_DATA,
    CONF_CONFIRM_RISKY,
    CONF_GOTO_TARGET,
    CONF_INTRO,
    CONF_LABEL,
    CONF_MENU_PATH,
    CONF_STREAM_RETURN_PATH,
    CONF_TARGET_ENTITY,
    DEFAULT_EXIT_KEYS,
    DEFAULT_EXIT_PHRASES,
    DEFAULT_MAX_CALL_MINUTES,
    DEFAULT_STREAM_RETURN_PATH,
    MENU_DIGITS,
    MENU_MAX_DEPTH,
)
from .menu import next_free_path, normalize_path, submenu_paths, used_paths
from .outbound import clean_phones
from .policy import available_actions, domain_needs_confirmation

_LOGGER = logging.getLogger(__name__)

NONE_VALUE = "__none__"


def to_form(value: Any) -> str:
    """ערך ריק מוצג כאפשרות ״ללא״ ולא כשדה ריק."""
    return str(value) if value else NONE_VALUE


def from_form(value: Any) -> str:
    return "" if value in (None, NONE_VALUE) else str(value)


def csv_list(raw: Any) -> list[str]:
    return [p.strip() for p in str(raw or "").split(",") if p.strip()]


def bad_networks(values: list[str]) -> list[str]:
    """הערכים שאינם טווח IP תקין.

    האימות כאן ולא בזמן ריצה: טווח שגוי שנשמר גורם לכך שהבדיקה
    מדלגת עליו, ובמקרה שהוא היחיד — כל השיחות נחסמות. עדיף
    להיעצר בטופס, כשהמשתמש עוד רואה מה הקליד.
    """
    import ipaddress  # noqa: PLC0415

    bad = []
    for value in values:
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError:
            bad.append(value)
    return bad


def num(value, default: float) -> float:
    """ערך מספרי מההגדרות, בלי להיתלות בטיפוס שנשמר.

    `NumberSelector` מחזיר `float` וההגדרות עוברות סיבוב דרך
    JSON, ולכן אותו שדה יכול לחזור כ-`15`, כ-`15.0` או כמחרוזת
    `"15.0"`. `int("15.0")` נופל ב-`ValueError` ומפיל את כל
    המסך, לא רק את השדה.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def ip_errors(user_input: dict[str, Any]) -> dict[str, str]:
    """שגיאת טווח IP בטופס, אם יש.

    זהה בשלושת הספקים, ולכן כאן: טווח שגוי הוא אותה שגיאה בכל
    מקום, ושלושה עותקים פירושם ששיפור הניסוח מגיע לאחד מהם.
    """
    if bad_networks(csv_list(user_input.get("provider_ips"))):
        return {"provider_ips": "invalid_network"}
    return {}


def endpoint_urls(hass, entry, driver) -> dict[str, str]:
    """הכתובות המלאות להדבקה אצל הספק.

    הטוקן חלק מהנתיב, ולכן זה מה שצריך להעתיק — ואין שום מקום
    אחר בממשק שמציג אותו.

    מזהה הדרייבר הוא מה שקובע את הנתיב, ולכן הכתובת יציבה לאורך
    גרסאות.
    """
    driver_id = driver.DRIVER_ID
    token = str(entry.data.get("token", ""))
    # ספק שיושב ברשת המקומית פונה ל-HA בכתובת פנימית; ספק מתארח
    # פונה מהאינטרנט ולכן צריך את החיצונית. הבחירה לפי דגל על
    # הדרייבר, כדי שהליבה לא תכיר ספק בשמו.
    prefer_internal = getattr(driver, "PREFER_INTERNAL_URL", False)
    try:
        base = get_url(
            hass,
            prefer_external=not prefer_internal,
            allow_cloud=not prefer_internal,
        ).rstrip("/")
    except NoURLAvailableError:
        base = (
            "http://<כתובת HA הפנימית>"
            if prefer_internal
            else "https://<הכתובת החיצונית שלך>"
        )
    api = f"{base}/api/ha_ivr/{driver_id}/{token}"
    stream = (
        f"{base}/api/ha_ivr/stream/{token}"
        .replace("https://", "wss://")
        .replace("http://", "ws://")
    )

    # מוצגת רק כשיש מה להדביק. שלושה מצבים ולא שניים: ספק בלי
    # ערוץ כלל, ספק שיש בשלוחה שלו שדה לכתובת, וספק שהכתובת
    # נשלחת אליו בזמן השיחה — הצגתה אצל האחרון שולחת את המשתמש
    # לחפש שדה שאינו קיים.
    #
    # ההסבר עצמו אינו כאן אלא ב-`data_description` של שדה שרק
    # משתמשי הספק רואים, כי טקסט שנכנס כ-placeholder אינו עובר
    # תרגום — הוא ערך ולא מפתח.
    return {
        "api_url": api,
        "stream_url": (
            stream if getattr(driver, "STREAM_URL_AT_PROVIDER", False) else ""
        ),
    }


# בורר הצינור נמחק מהטופס ב-0.28.0. הוא לא היה חסר תועלת אלא
# חסר חיבור: `async_accept_pipeline_from_satellite` בונה בעצמה
# `pipeline_id=self._resolve_pipeline()`, שקורא מישות `select`
# ולא מההגדרות — כלומר מי שבחר כאן צינור קיבל את ברירת המחדל של
# HA בלי שום שורה ביומן. הבורר עבר ל-`select.py`, ושם הוא עובד.
#
# מאותה סיבה ירדו גם רגישות ה-VAD (ישות), מנוע ההרצה (אין עוד
# שניים), ותקרת השיחות המקבילות (מספר הקווים הוא מספר הישויות).
# `stream_noise` ו-`stream_gain` ירדו כי הצינור אינו מקבל אותם
# כלל מהלוויין — שניהם היו כבויים כברירת מחדל ממילא.


# בורר "ספקים פעילים" נמחק בפיצול. הוא היה קיים רק כדי להסתיר
# שדות של ספקים שאינם בשימוש מתוך טופס אחד משותף — ומאז שלכל
# ספק אינטגרציה משלו, מי שאינו מתקין אותה אינו רואה אותה בכלל.


def stream_schema(
    current: dict[str, Any],
    *,
    channel_token: bool = False,
    return_path: bool = False,
    rate: bool = False,
) -> vol.Schema:
    """הגדרות העוזר הקולי בערוץ הסטרימינג.

    מסך נפרד מהתפריט. לתפריט ולעוזר אין שום הגדרה משותפת חוץ
    מהטוקן, ועשרה שדות במסך אחד הקשו למצוא כל דבר.

    מה שאינו כאן יושב בישויות: הצינור ורגישות ה-VAD הם ישויות
    `select` של הרשומה, כי זה המקום היחיד שממנו הצינור קורא
    אותם. כאן נשארו הצלילים, היציאה, ההד והתקרות.

    שלושת הדגלים מסננים לפי ספק. רוב השדות משותפים, אבל שלושה
    שייכים לספק אחד בלבד:

    | שדה | שייך ל | נקרא ב |
    |---|---|---|
    | `stream_channel_token` | טכנוליין | `_on_start`, מול מסגרת הפתיחה |
    | `stream_return_path` | טכנוליין | `leave`, ב-`transfer_extension` |
    | `stream_rate` | מי שבוחר קצב | בניית התשובה |

    לפני הסינון שלושתם הוצגו לשני הספקים, ומשתמש שהגדיר Vonage
    נשאל למזהה ערוץ שאין לו מאיפה לקחת — הוא נוצר אצל טכנוליין
    ונשלח רק במסגרת ה-`start` שלהם.
    """
    schema: dict[Any, Any] = {
        vol.Optional(
            "stream_tones", default=bool(current.get("stream_tones", True))
        ): bool,
        vol.Optional(
            "stream_exit",
            description={
                "suggested_value": str(
                    current.get("stream_exit", DEFAULT_EXIT_PHRASES)
                )
            },
        ): str,
        vol.Optional(
            "stream_exit_keys",
            description={
                "suggested_value": str(
                    current.get("stream_exit_keys", DEFAULT_EXIT_KEYS)
                )
            },
        ): str,
        vol.Required(
            "stream_max_minutes",
            default=int(num(current.get("stream_max_minutes"),
                            DEFAULT_MAX_CALL_MINUTES)),
        ): NumberSelector(
            NumberSelectorConfig(
                min=0, max=120, step=1, unit_of_measurement="דקות",
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            "stream_echo_tail",
            default=num(current.get("stream_echo_tail"), 0.25),
        ): NumberSelector(
            NumberSelectorConfig(
                min=0, max=2, step=0.05, unit_of_measurement="שניות",
                mode=NumberSelectorMode.BOX,
            )
        ),
    }

    # השדות תלויי-הספק, כל אחד רק אצל מי שקורא אותו.
    if channel_token:
        schema[
            vol.Optional(
                "stream_channel_token",
                description={
                    "suggested_value": str(
                        current.get("stream_channel_token", "") or ""
                    )
                },
            )
        ] = str
    if return_path:
        schema[
            vol.Optional(
                CONF_STREAM_RETURN_PATH,
                description={
                    "suggested_value": str(
                        current.get(
                            CONF_STREAM_RETURN_PATH, DEFAULT_STREAM_RETURN_PATH
                        )
                    )
                },
            )
        ] = str
    if rate:
        schema[
            vol.Required(
                CONF_STREAM_RATE,
                default=str(current.get(CONF_STREAM_RATE, 16000) or 16000),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value="16000", label="16 קילוהרץ (מומלץ)"),
                    SelectOptionDict(value="8000", label="8 קילוהרץ"),
                ],
                mode=SelectSelectorMode.DROPDOWN,
                sort=False,
            )
        )
    return vol.Schema(schema)

class _EditMixin:
    """הבחנה בין הוספה לעריכה, לכל זרימת תת-רשומה.

    מקום אחד בכוונה, ולא עותק בכל זרימה. אין להשתמש בשם
    `_reconfigure_subentry_id` — זה מאפיין ש-Home Assistant מגדיר
    בעצמו, ודריסה שלו מפילה כל הוספה ב-
    `ValueError: Source is user, expected reconfigure`.
    """

    def _target_hint(self) -> str:
        """מה להזין ביעד, לפי הספק של הרשומה."""
        from . import registry  # noqa: PLC0415

        try:
            driver = registry.for_entry(self._get_entry())
        except Exception:  # noqa: BLE001 — הטופס חשוב יותר מהרמז
            return ""
        return str(getattr(driver, "GOTO_TARGET_HINT", "") or "")

    def _editing_subentry_id(self) -> str:
        """מזהה תת-הרשומה הנערכת, או ריק בהוספה.

        אין לקרוא למתודה הזו `_reconfigure_subentry_id`: HA מגדיר
        מאפיין בשם הזה וקורא ממנו את המזהה, והגדרה מחדש שלו דורסת
        אותו ומפילה את שליפת תת-הרשומה.
        """
        context = getattr(self, "context", None) or {}
        return str(context.get("subentry_id", "") or "")


class _PathMixin(_EditMixin):
    """משותף לפריט ולתת-תפריט: בורר נתיב ואימות."""

    def _taken(self) -> set[str]:
        try:
            return used_paths(self._get_entry(), exclude=self._editing_subentry_id())
        except Exception:  # noqa: BLE001 — הטופס חשוב יותר מהסימון
            _LOGGER.debug("Could not read the paths already in use", exc_info=True)
            return set()

    def _submenus(self, exclude_self: bool = False) -> dict[str, str]:
        try:
            return submenu_paths(
                self._get_entry(),
                exclude=self._editing_subentry_id() if exclude_self else "",
            )
        except Exception:  # noqa: BLE001
            return {}

    def _blocked_by_item(self, path: str) -> bool:
        """האם אחד ההורים הוא פריט ולא תת-תפריט."""
        submenus, items = self._submenus(), self._taken()
        parts = path.split("/")
        for depth in range(1, len(parts)):
            ancestor = "/".join(parts[:depth])
            if ancestor in items and ancestor not in submenus:
                return True
        return False

    def _path_selector(self, current: str = "", *, allow_none: bool = True):
        """כל המקומות הפנויים, בתפריט הראשי ובתתי-התפריטים."""
        taken, submenus = self._taken(), self._submenus()
        options: list[SelectOptionDict] = []
        if allow_none:
            options.append(
                SelectOptionDict(value=NONE_VALUE, label="ללא. אינו בתפריט")
            )

        def add_level(parent: str, prefix: str) -> None:
            if parent.count("/") + 2 > MENU_MAX_DEPTH:
                return
            for digit in MENU_DIGITS:
                path = f"{parent}/{digit}" if parent else digit
                if path in submenus:
                    continue
                suffix = " — תפוסה" if path in taken and path != current else ""
                options.append(
                    SelectOptionDict(value=path, label=f"{prefix}{digit}{suffix}")
                )

        add_level("", "תפריט ראשי, ספרה ")
        for path in sorted(submenus):
            name = submenus[path] or f"תפריט {path}"
            add_level(path, f"{name} ({path}), ספרה ")

        if current and current not in {o["value"] for o in options}:
            options.insert(0, SelectOptionDict(value=current, label=current))

        return SelectSelector(
            SelectSelectorConfig(
                options=options, mode=SelectSelectorMode.DROPDOWN, sort=False
            )
        )

    def _validate_path(self, raw: str, *, check_parent: bool) -> tuple[str, str]:
        """מחזיר (נתיב, קוד שגיאה)."""
        path = normalize_path(raw) if raw else ""
        if raw and not path:
            return "", "invalid_path"
        if path and path in self._taken():
            return path, "path_in_use"
        if path and check_parent and self._blocked_by_item(path):
            return path, "parent_is_item"
        return path, ""

    async def _simple_step(
        self,
        step_id: str,
        user_input,
        current: dict,
        *,
        field: str,
        title_default: str,
        required: bool = False,
    ) -> SubentryFlowResult:
        """מסך תת-רשומה של נתיב, תווית ושדה אחד.

        תת-תפריט ומעבר לשלוחה נבדלים בשדה הזה ובכותרת שנבנית,
        וכל השאר — ולידציית הנתיב, עדכון-או-יצירה, ובחירת הנתיב
        הפנוי הבא — זהה. `field` הוא שם השדה השלישי, `required`
        קובע אם ריק שלו הוא שגיאה, ו-`title_default` הוא מה
        שמופיע בכותרת כשאין תווית.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            raw = from_form(user_input.get(CONF_MENU_PATH)).strip()
            path, err = self._validate_path(raw, check_parent=True)
            if not path and not err:
                err = "invalid_path"
            value = str(user_input.get(field, "") or "").strip()
            if err:
                errors[CONF_MENU_PATH] = err
            elif required and not value:
                errors[field] = "target_required"
            else:
                data = {
                    CONF_MENU_PATH: path,
                    CONF_LABEL: str(user_input.get(CONF_LABEL, "") or "").strip(),
                    field: value,
                }
                title = f"{path} — {data[CONF_LABEL] or title_default}"
                if self._editing_subentry_id():
                    return self.async_update_and_abort(
                        self._get_entry(),
                        self._get_reconfigure_subentry(),
                        title=title,
                        data=data,
                    )
                return self.async_create_entry(title=title, data=data)

        current = user_input or current
        path = normalize_path(current.get(CONF_MENU_PATH, "")) or next_free_path(
            self._get_entry(), exclude=self._editing_subentry_id()
        )
        marker = vol.Required if required else vol.Optional
        return self.async_show_form(
            step_id=step_id,
            errors=errors,
            # הרמז מגיע מהדרייבר: משמעות היעד שונה בין הספקים,
            # ותיאור קבוע אחד היה נכון לאחד ושגוי לשאר.
            description_placeholders={"hint": self._target_hint()},
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MENU_PATH, default=to_form(path)
                    ): self._path_selector(path, allow_none=False),
                    vol.Optional(
                        CONF_LABEL,
                        description={
                            "suggested_value": str(current.get(CONF_LABEL, ""))
                        },
                    ): str,
                    marker(
                        field,
                        description={
                            "suggested_value": str(current.get(field, "") or "")
                        },
                    ): str,
                }
            ),
        )


class MenuItemFlowHandler(_PathMixin, ConfigSubentryFlow):
    """הוספה ועריכה של פריט.

    התהליך מפוצל: מכשיר ונתיב, אחר כך הפעולה, ורק אם לפעולה יש
    שדות מוצג מסך שלישי. הפיצול נדרש משום שסכמת טופס נבנית פעם
    אחת לפני הצגתו, ולכן אי אפשר להתאים אותה לבחירה באותו מסך.
    """

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}

    async def async_step_user(self, user_input=None) -> SubentryFlowResult:
        return await self._target_step("user", user_input)

    async def async_step_reconfigure(self, user_input=None) -> SubentryFlowResult:
        return await self._target_step(
            "reconfigure", user_input, dict(self._get_reconfigure_subentry().data)
        )

    async def _target_step(
        self, step_id: str, user_input, current: dict | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            path, err = self._validate_path(
                from_form(user_input.get(CONF_MENU_PATH)).strip(), check_parent=True
            )
            if err:
                errors[CONF_MENU_PATH] = err
            else:
                self._pending = {
                    CONF_TARGET_ENTITY: str(user_input[CONF_TARGET_ENTITY]),
                    CONF_MENU_PATH: path,
                    CONF_LABEL: str(user_input.get(CONF_LABEL, "") or "").strip(),
                }
                return await self.async_step_action()

        current = user_input or current or {}
        path = normalize_path(current.get(CONF_MENU_PATH, "")) or next_free_path(
            self._get_entry(), exclude=self._editing_subentry_id()
        )
        return self.async_show_form(
            step_id=step_id,
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TARGET_ENTITY,
                        description={
                            "suggested_value": current.get(CONF_TARGET_ENTITY, "")
                        },
                    ): EntitySelector(EntitySelectorConfig(multiple=False)),
                    vol.Required(
                        CONF_MENU_PATH, default=to_form(path)
                    ): self._path_selector(path),
                    # description ולא default — עם default אי אפשר
                    # לנקות שדה טקסט שכבר יש בו ערך.
                    vol.Optional(
                        CONF_LABEL,
                        description={
                            "suggested_value": str(current.get(CONF_LABEL, "") or "")
                        },
                    ): str,
                }
            ),
        )

    # ---- שלב שני: פעולה ----

    async def async_step_action(self, user_input=None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        entity_id = str(self._pending.get(CONF_TARGET_ENTITY, ""))
        domain = entity_id.split(".", 1)[0] if "." in entity_id else ""

        if user_input is not None:
            action = from_form(user_input.get(CONF_ACTION))
            confirmed = bool(user_input.get(CONF_CONFIRM_RISKY, False))
            if action and domain_needs_confirmation(domain) and not confirmed:
                errors[CONF_CONFIRM_RISKY] = "confirm_required"
            else:
                self._pending[CONF_ACTION] = action
                self._pending[CONF_CONFIRM_RISKY] = confirmed
                if await self._needs_params(entity_id, action):
                    return await self.async_step_params()
                return self._finish({})

        schema: dict[Any, Any] = {
            vol.Required(CONF_ACTION, default=NONE_VALUE): await self._action_selector(
                entity_id
            )
        }
        if domain and domain_needs_confirmation(domain):
            schema[vol.Optional(CONF_CONFIRM_RISKY, default=False)] = bool

        return self.async_show_form(
            step_id="action",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"entity": entity_id},
        )

    async def _action_selector(self, entity_id: str):
        """רק פעולות שהמכשיר באמת תומך בהן, נשלפות מ-HA."""
        options = [SelectOptionDict(value=NONE_VALUE, label="רק הקראת סטטוס")]
        domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
        if domain:
            for name in available_actions(self.hass, domain):
                fields = await async_action_fields(self.hass, domain, name, entity_id)
                if not action_is_usable(fields):
                    continue
                label = await async_action_name(self.hass, domain, name)
                if build_fields_schema(fields) is not None:
                    label = f"{label} …"
                options.append(SelectOptionDict(value=name, label=label))
        return SelectSelector(
            SelectSelectorConfig(
                options=options, mode=SelectSelectorMode.DROPDOWN, sort=False
            )
        )

    # ---- שלב שלישי: ערכי הפעולה ----

    async def async_step_params(self, user_input=None) -> SubentryFlowResult:
        entity_id = str(self._pending.get(CONF_TARGET_ENTITY, ""))
        action = str(self._pending.get(CONF_ACTION, ""))
        domain = entity_id.split(".", 1)[0] if "." in entity_id else ""

        if user_input is not None:
            fields = await async_action_fields(self.hass, domain, action, entity_id)
            labels = build_label_map(fields)
            return self._finish(
                {
                    labels.get(k, k): v
                    for k, v in user_input.items()
                    if v is not None and v != ""
                }
            )

        fields = await async_action_fields(self.hass, domain, action, entity_id)
        schema = build_fields_schema(fields)
        if schema is None:
            return self._finish({})
        return self.async_show_form(
            step_id="params",
            data_schema=schema,
            description_placeholders={"action": action, "entity": entity_id},
        )

    async def _needs_params(self, entity_id: str, action: str) -> bool:
        if not action or "." not in entity_id:
            return False
        domain = entity_id.split(".", 1)[0]
        fields = await async_action_fields(self.hass, domain, action, entity_id)
        return build_fields_schema(fields) is not None

    def _finish(self, action_data: dict) -> SubentryFlowResult:
        p = self._pending
        entity_id = str(p.get(CONF_TARGET_ENTITY, ""))
        data = {
            CONF_TARGET_ENTITY: entity_id,
            CONF_MENU_PATH: str(p.get(CONF_MENU_PATH, "")),
            CONF_LABEL: str(p.get(CONF_LABEL, "")),
            CONF_ACTION: str(p.get(CONF_ACTION, "")),
            CONF_CONFIRM_RISKY: bool(p.get(CONF_CONFIRM_RISKY, False)),
            CONF_ACTION_DATA: action_data,
        }
        label = data[CONF_LABEL]
        if not label:
            state = self.hass.states.get(entity_id)
            label = str(
                (state.attributes.get("friendly_name") if state else None) or entity_id
            )
        path = data[CONF_MENU_PATH]
        title = f"{path} — {label}" if path else label

        if self._editing_subentry_id():
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                title=title,
                data=data,
            )
        return self.async_create_entry(title=title, data=data)


# ----------------------------------------------------------------------
# תת-תפריט
# ----------------------------------------------------------------------


class ContactFlowHandler(_EditMixin, ConfigSubentryFlow):
    """נמען להתראה קולית: שם ומספר.

    אין כאן נתיב בתפריט — נמען אינו פריט בעץ אלא יעד. השם הוא
    מה שיופיע כישות `notify`, ולכן הוא מה שייבחר באוטומציה.
    """

    async def async_step_user(self, user_input=None) -> SubentryFlowResult:
        return await self._step("user", user_input, {})

    async def async_step_reconfigure(self, user_input=None) -> SubentryFlowResult:
        return await self._step(
            "reconfigure", user_input, dict(self._get_reconfigure_subentry().data)
        )

    async def _step(self, step_id, user_input, current) -> SubentryFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            name = str(user_input.get(CONF_LABEL, "") or "").strip()
            phone = clean_phones(str(user_input.get(CONF_PHONE, "") or ""))
            if not name:
                errors[CONF_LABEL] = "name_required"
            elif not phone:
                # מספר שאינו תקין נעצר כאן ולא בשיגור: נמען בלי
                # מספר שמיש הוא ישות שנראית תקינה ונכשלת בשיחה.
                errors[CONF_PHONE] = "invalid_phone"
            else:
                data = {CONF_LABEL: name, CONF_PHONE: phone}
                if CONF_CHANNEL in user_input:
                    data[CONF_CHANNEL] = str(user_input[CONF_CHANNEL])
                trunk = str(user_input.get(CONF_TRUNK, "") or "").strip()
                if trunk:
                    data[CONF_TRUNK] = trunk
                if self._editing_subentry_id():
                    return self.async_update_and_abort(
                        self._get_entry(),
                        self._get_reconfigure_subentry(),
                        title=name,
                        data=data,
                    )
                return self.async_create_entry(title=name, data=data)

        current = user_input or current
        fields = {
            vol.Required(
                CONF_LABEL,
                description={
                    "suggested_value": str(current.get(CONF_LABEL, "") or "")
                },
            ): str,
            vol.Required(
                CONF_PHONE,
                description={
                    "suggested_value": str(current.get(CONF_PHONE, "") or "")
                },
            ): str,
        }
        # בורר הערוץ מופיע רק לספק שמצהיר יותר מדרך אחת. ספק בלי
        # `NOTIFY_CHANNELS` — טכנוליין — שולח בקול בלבד, ואין מה
        # לבחור.
        if len(self._notify_channels()) > 1:
            fields[
                vol.Required(
                    CONF_CHANNEL,
                    default=str(current.get(CONF_CHANNEL, "voice") or "voice"),
                )
            ] = SelectSelector(
                SelectSelectorConfig(
                    options=list(self._notify_channels()),
                    mode=SelectSelectorMode.LIST,
                    translation_key="notify_channel",
                    sort=False,
                )
            )
        # שדה טראנק אופציונלי, רק לספק שמחייג דרך טראנק (המרכזייה):
        # נמען שיוצא בזיהוי אחר. ריק חוזר לטראנק ברירת המחדל.
        if self._supports_trunk():
            fields[
                vol.Optional(
                    CONF_TRUNK,
                    description={
                        "suggested_value": str(current.get(CONF_TRUNK, "") or "")
                    },
                )
            ] = str
        return self.async_show_form(
            step_id=step_id, errors=errors, data_schema=vol.Schema(fields)
        )

    def _supports_trunk(self) -> bool:
        """האם הדרייבר מציע בחירת טראנק יוצא לנמען."""
        from . import registry  # noqa: PLC0415

        try:
            driver = registry.for_entry(self._get_entry())
        except Exception:  # noqa: BLE001 — הטופס חשוב יותר מהשדה
            return False
        return bool(getattr(driver, "SUPPORTS_TRUNK", False))

    def _notify_channels(self) -> tuple[str, ...]:
        """מזהי הערוצים של הדרייבר, או `("voice",)` אם אין."""
        from . import registry  # noqa: PLC0415

        try:
            driver = registry.for_entry(self._get_entry())
        except Exception:  # noqa: BLE001 — הטופס חשוב יותר מהבורר
            return ("voice",)
        return tuple(getattr(driver, "NOTIFY_CHANNELS", ("voice",)))


class AlertsFlowHandler(_PathMixin, ConfigSubentryFlow):
    """שלוחה שמקריאה את ההתראות האחרונות שנשלחו.

    אין כאן מכשיר ואין פעולה — צומת שמקריא את יומן ההתראות.
    השדה `intro` הוא הפרומפט שנאמר לפני הרשימה.
    """

    async def async_step_user(self, user_input=None) -> SubentryFlowResult:
        return await self._step("user", user_input, {})

    async def async_step_reconfigure(self, user_input=None) -> SubentryFlowResult:
        return await self._step(
            "reconfigure", user_input, dict(self._get_reconfigure_subentry().data)
        )

    async def _step(self, step_id, user_input, current) -> SubentryFlowResult:
        return await self._simple_step(
            step_id, user_input, current,
            field=CONF_INTRO,
            title_default="התראות אחרונות",
        )


class SubMenuFlowHandler(_PathMixin, ConfigSubentryFlow):
    """הוספה ועריכה של תת-תפריט."""

    async def async_step_user(self, user_input=None) -> SubentryFlowResult:
        return await self._step("user", user_input, {})

    async def async_step_reconfigure(self, user_input=None) -> SubentryFlowResult:
        return await self._step(
            "reconfigure", user_input, dict(self._get_reconfigure_subentry().data)
        )

    async def _step(self, step_id, user_input, current) -> SubentryFlowResult:
        return await self._simple_step(
            step_id, user_input, current,
            field=CONF_INTRO,
            title_default="תת-תפריט",
        )


# ----------------------------------------------------------------------
# העברה ליעד SIP
# ----------------------------------------------------------------------


class GoToFlowHandler(_PathMixin, ConfigSubentryFlow):
    """פריט שמעביר לשלוחה אחרת אצל הספק.

    השימוש המרכזי: שלוחת הסטרימינג של העוזר הקולי. המתקשר מקיש,
    נוחת בעוזר, ואומר "תפריט ראשי" כדי לחזור — החזרה מוגדרת בשדה
    "שלוחה למעבר בסיום" של אותה שלוחה אצל הספק.

    סוג נפרד ולא שדה בפריט הרגיל: אין כאן מכשיר ואין פעולה.
    """

    async def async_step_user(self, user_input=None) -> SubentryFlowResult:
        return await self._step("user", user_input, {})

    async def async_step_reconfigure(self, user_input=None) -> SubentryFlowResult:
        return await self._step(
            "reconfigure", user_input, dict(self._get_reconfigure_subentry().data)
        )

    async def _step(self, step_id, user_input, current) -> SubentryFlowResult:
        # בלי ברירת מחדל לתווית: היא הייתה מוצעת גם לספק שאין
        # לו את היעד שהיא מתארת.
        #
        # היעד חובה: פריט מעבר בלי שלוחה מוליך לשומקום.
        return await self._simple_step(
            step_id, user_input, current,
            field=CONF_GOTO_TARGET,
            title_default="מעבר לשלוחה",
            required=True,
        )
