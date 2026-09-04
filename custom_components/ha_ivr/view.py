"""נקודת הקצה. אחת לכל הספקים — הדרייבר רק מפענח ומרנדר."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import logging
from dataclasses import replace

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    DOMAIN,
    DOMAIN_NAMES,
    EVENT_CALL_RECEIVED,
    MENU_MAX_REPEATS,
    SERVICE_CALL_TIMEOUT,
    STATE_CHANGE_TIMEOUT,
    signal_call_received,
)
from .policy import action_allowed, domain_needs_confirmation
from .translations_he import field_unit, translate_option, translate_unit

from . import history
from . import net
from . import registry
from .codec import CodecError
from . import menu as menu_mod
from . import tree as tree_mod
from .model import KEY_ROOT, GoTo, Say, Terminal, say_number

_LOGGER = logging.getLogger(__name__)

# עד כמה חברים מוקראים בשמם. מעבר לזה עוברים לספירה: רשימה של
# שמות ומצבים ארוכה מדי להאזנה בטלפון, ומי שמקשיב לא יזכור אותה.
NAME_EACH_UP_TO = 3

_STATES = {
    "on": "דולק", "off": "כבוי", "locked": "נעול", "unlocked": "לא נעול",
    "open": "פתוח", "closed": "סגור", "opening": "נפתח", "closing": "נסגר",
    "cool": "על קירור", "heat": "על חימום", "fan_only": "על אוורור",
    "dry": "על ייבוש", "auto": "על אוטומטי", "idle": "ממתין",
    "playing": "מנגן", "paused": "מושהה", "home": "בבית",
    "not_home": "מחוץ לבית", "unavailable": "לא זמין", "unknown": "לא ידוע",
}

# יחידות שכבר נרשמו ביומן כלא מתורגמות. פעם אחת לכל יחידה,
# אחרת כל הקראת חיישן מייצרת שורה.
_UNKNOWN_UNITS: set[str] = set()


class IvrView(HomeAssistantView):
    """מקבלת בקשות מכל ספק ומחזירה את הפעולה הבאה."""

    url = "/api/ha_ivr/{driver}/{token}"
    name = "api:ha_ivr"
    # הספקים אינם יכולים לשלוח כותרת Authorization של HA.
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _entry(self, entries, token: str):
        """הרשומה שהטוקן שייך לה, מבין רשומות הספק.

        הטוקן מזהה את הרשומה ולא הדומיין: כשיש כמה רשומות לאותו
        דומיין, בחירה לפי הדומיין הייתה מוליכה לרשומה שרירותית —
        כלומר בקשה תקינה נבדקת מול טוקן של רשומה אחרת ונדחית.

        השוואה בזמן קבוע, כמו בערוץ הסטרימינג.
        """
        for entry in entries:
            expected = str(entry.data.get("token", ""))
            if expected and hmac.compare_digest(str(token), expected):
                return entry
        return None

    async def get(self, request, driver: str, token: str):
        return await self._handle(request, driver, token, dict(request.query), {})

    async def post(self, request, driver: str, token: str):
        # Vonage שולחת JSON בגוף ולא טופס, ומעבירה את ההקשה שם.
        # לכן הגוף נשמר כמו שהוא ולא נמעך לתוך הפרמטרים.
        body: dict = {}
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            try:
                body = {k: str(v) for k, v in (await request.post()).items()}
            except Exception:  # noqa: BLE001
                body = {}
        if not isinstance(body, dict):
            body = {}
        merged = {**dict(request.query), **{k: str(v) for k, v in body.items()}}
        return await self._handle(request, driver, token, merged, body)

    # ------------------------------------------------------------------

    async def _handle(
        self, request, driver_id: str, token: str, params: dict, body: dict | None = None
    ):
        drv = registry.get(driver_id)
        if drv is None:
            _LOGGER.warning(
                "Received a request for %s, but its integration is not installed. Registered: %s",
            driver_id, ", ".join(registry.registered()) or "(none)",
            )
            return web.Response(status=404, text="Unknown driver")

        # שתי תשובות לשני כשלים שונים: "אין רשומה" הוא 503 ואומר
        # למתקין שהאינטגרציה לא הוגדרה, ו"הטוקן אינו מתאים" הוא
        # 401. תשובה אחת לשניהם מטעה את שני המקרים.
        entries = [
            e for e in self.hass.config_entries.async_entries(DOMAIN)
            if str(e.data.get("provider", "")) == drv.DRIVER_ID
        ]
        if not entries:
            return web.Response(status=503, text="Not configured")

        entry = self._entry(entries, token)
        if entry is None:
            _LOGGER.warning("Bad token from %s", request.remote)
            return web.Response(status=401, text="Unauthorized")

        opts = entry.options
        # מה שכל ספק צריך, בלי שהליבה תדע מי צריך מה. הגדרות
        # ייחודיות נקראות בדרייבר עצמו מתוך `options`.
        cfg = {
            "callback_url": str(request.url.with_query(None)),
            "token": token,
            "stream_url": _stream_url(request, token),
            "options": dict(opts),
            # הזהות של הרשומה, לדרייבר שצריך לרשום מצב לשיחה (למשל
            # מיפוי UUID של AudioSocket). המתקשר מתווסף אחרי `parse`.
            "entry_id": entry.entry_id,
        }
        # רשימה שטוחה: לרשומה יש ספק אחד, ולכן אין מילון שממפה
        # ספק לטווחים.
        allowed = list(opts.get("allowed_ips") or [])
        if allowed and not net.ip_allowed(request.remote, allowed):
            _LOGGER.warning(
                "Blocked a request from %s for %s. If Home Assistant sits behind a proxy, set use_x_forwarded_for and trusted_proxies",
            request.remote, driver_id,
            )
            return web.Response(status=403, text="Forbidden")

        # חתימה אחת לשלושת הדרייברים. מי שאינו צריך את הגוף
        # מתעלם ממנו.
        ctx = drv.parse(params, body or {})
        cfg["caller"] = ctx.caller

        if ctx.hangup:
            # מגיעה עם אותם פרמטרים כמו הבקשה שלפניה, ולכן נראית
            # ביומן כהקשה חוזרת אם לא מבדילים.
            _LOGGER.debug("%s <- hangup, caller=%s", driver_id, ctx.caller)
            return _reply(drv, None)

        _LOGGER.debug(
            "%s <- [%s] path=%s key=%s step=%s caller=%s from=%s",
            driver_id, request.method, ctx.path or "(שורש)", ctx.digit,
            ctx.step, ctx.caller, request.remote,
        )
        _warn_if_proxied(driver_id, request.remote, bool(allowed))
        history.record(
            "menu.request",
            driver=driver_id,
            path="/".join(ctx.path) or "(שורש)",
            digit=ctx.digit,
            step=ctx.step,
            caller=ctx.caller,
            remote=request.remote,
        )

        phones = opts.get("allowed_phones") or []
        if phones and _digits(ctx.caller) not in {_digits(p) for p in phones}:
            _LOGGER.warning("Blocked a call from %s", ctx.caller)
            return _reply(
                drv,
                Terminal([Say("text", "המספר שלך אינו מורשה")]),
                cfg,
            )

        # נבנה מחדש בכל בקשה, ולכן משקף תמיד את ההגדרות
        # העדכניות. לכל רשומה עץ משלה.
        root = menu_mod.build_tree(self.hass, entry)
        moved = tree_mod.navigate(root, ctx.path, ctx.digit)

        # אין הקשה: התפריט מושמע שוב, עד למספר החזרות המרבי. בלי
        # זה שיחה נטושה מקריאה את התפריט עד שהמתקשר מנתק.
        #
        # הצעד הוא מה שמבדיל ולא הנתיב: בשורש הנתיב ריק גם
        # בסיבוב החמישי בלי הקשה. שיחה חדשה היא צעד 1, וכל
        # השמעה חוזרת גבוהה ממנו — בשורש ובעומק כאחד.
        if ctx.digit is None and ctx.step > 1:
            repeats = _repeats(ctx.step, ctx.path)
            if repeats >= MENU_MAX_REPEATS:
                _LOGGER.debug(
                    "%s: %s replays with no key press, hanging up", driver_id, repeats
                )
                return _reply(
                    drv, Terminal([Say("text", "להתראות")]), cfg
                )

        # צומת איסוף מספר: ההקשה היא ספרה של ערך, לא בחירה בתפריט.
        # נבדק לפני הניווט, כי הספרות הנאספות אינן ילדים בעץ אלא
        # המשך של הנתיב — ו-`navigate` היה פוסל אותן כבחירה שגויה.
        if (found := tree_mod.find_collector(root, ctx.path)) is not None:
            return await self._collect_digit(drv, entry, driver_id, root, ctx, cfg, found)

        if moved is None:
            # הקשה שאינה בתפריט. שואלים שוב מאותו מקום.
            node = tree_mod.resolve(root, ctx.path) or root
            prompt = tree_mod.prompt_for(
                node,
                ctx.path,
                ctx.step,
                supports_goto=drv.SUPPORTS_GOTO,
            )
            # להשמיע שהבחירה שגויה. בלי זה המתקשר לא יודע אם טעה
            # או שההקשה פשוט לא נקלטה.
            return _reply(
                drv,
                replace(
                    prompt,
                    messages=[Say("text", "בחירה שאינה קיימת"), *prompt.messages],
                ),
                cfg,
            )

        supports = drv.SUPPORTS_GOTO

        path, node = moved
        if node.is_menu:
            prompt = tree_mod.prompt_for(
                node, path, ctx.step, supports_goto=supports
            )
            # בכניסה לשורש, אם למתקשר יש התראות שטרם שמע — הכרזה
            # לפני התפריט. כך צינתוק זול הופך לזרימה שלמה: פינג
            # יוצא, המתקשר חוזר, ומיד יודע שממתינה לו התראה.
            # רק בשורש ורק פעם אחת (`mark_heard` בשלוחת ההקראה).
            if not path:
                from . import announce as announce_store  # noqa: PLC0415

                pending = announce_store.unheard_count(
                    self.hass, entry.entry_id, ctx.caller
                )
                if pending:
                    word = "התראה חדשה" if pending == 1 else f"{pending} התראות חדשות"
                    prompt = replace(
                        prompt,
                        messages=[Say("text", f"יש לך {word}"), *prompt.messages],
                    )
            return _reply(drv, prompt, cfg)

        if node.is_goto:
            goto = GoTo(target=node.goto, messages=[Say("text", "מעביר אותך")])
            # אין צירוף תפריט אחרי ה-connect ב-Vonage.
            #
            # ניסיתי זאת כמקבילה ל-endGoTo, אבל Vonage סוגרת את
            # ה-connect מיד ועוברת לפעולה הבאה — המתקשר "הועף"
            # לתפריט ברגע שביקש את העוזר, והתפריט נכנס ללולאה
            # שהחזיקה שלושה חיבורי סטרימינג במקביל.
            #
            # היציאה מהעוזר נעשית בסגירת הערוץ מצדנו: ביטוי יציאה
            # או מקש. אחריה Vonage מסיימת את השיחה.
            return _reply(drv, goto, cfg)

        # צומת איסוף מספר. לא עלה: הפעלה בלי הערך שטרם הוקש הייתה
        # קוראת לשירות בלי פרמטר, נכשלת, ומשמיעה "אירעה שגיאה"
        # לפני שהמתקשר בכלל הספיק להקיש.
        if node.is_collect:
            return _reply(
                drv, tree_mod.collect_prompt(node, path, ctx.step, ()), cfg
            )

        # עלה. מבצעים, ואז מחזירים את תפריט ההורה עם התוצאה בראשו.
        #
        # לא לנווט לשום מקום. ניווט אחרי פעולה יצר לולאה: השלוחה
        # שלוחת ה-API יושבת בשורש, ולכן go_to_folder=/ החזיר
        # אליה עצמה
        # שוב ושוב. בטכנוליין המקבילה הייתה ניתוק אחרי כל פעולה.
        # תשובה אחת בלי ניווט פותרת את שתיהן, וגם חוסכת סיבוב שרת.
        if node.alerts:
            # שלוחת "התראות אחרונות": מקריאה את היומן במקום להריץ
            # פעולה. מסוננת לפי מספר המתקשר — כל אחד שומע את שלו.
            result = self._say_alerts(entry, node, ctx.caller)
        else:
            self._report_call(entry, driver_id, path, node)
            result = await self._run_leaf(node)

        parent_path = path[:-1]
        parent = tree_mod.resolve(root, parent_path) or root
        prompt = tree_mod.prompt_for(
            parent, parent_path, ctx.step, supports_goto=supports
        )
        return _reply(
            drv, replace(prompt, messages=[*result, *prompt.messages]), cfg
        )

    async def _collect_digit(self, drv, entry, driver_id, root, ctx, cfg, found):
        """הספרה הבאה בצומת איסוף, ובסוף — הפעלה עם הערך שהורכב.

        אין כאן שום זיכרון בצד השרת. הספרות שכבר הוקשו הגיעו
        בנתיב, והספרות שיוקשו ימשיכו לנסוע בו. שיחה באמצע הקשת
        מספר שורדת ריסטרט בדיוק כמו כל שאר התפריט.
        """
        node, base, collected = found
        width = int(node.collect.get("width") or 0)

        # כוכבית מבטלת. אפס הוא ספרה כאן ולא "חזרה" — בלעדיו אי
        # אפשר להקיש 20 מעלות.
        if ctx.digit == KEY_ROOT:
            prompt = tree_mod.prompt_for(
                root, (), ctx.step, supports_goto=drv.SUPPORTS_GOTO
            )
            return _reply(drv, prompt, cfg)

        # פג הזמן באמצע הקשה. מתחילים את המספר מהתחלה עם ההודעה
        # המלאה, ולא ממשיכים בשקט — המתקשר אינו יודע כמה ספרות
        # נקלטו, והמשך שקט היה משאיר אותו מנחש. מונה החזרות של
        # התפריט חל גם כאן, ולכן שיחה נטושה מתנתקת כרגיל.
        if ctx.digit is None:
            return _reply(
                drv, tree_mod.collect_prompt(node, base, ctx.step, ()), cfg
            )

        if ctx.digit not in tree_mod.valid_next_digits(node.collect, collected):
            prompt = tree_mod.collect_prompt(node, base, ctx.step, collected)
            return _reply(
                drv,
                replace(
                    prompt,
                    messages=[Say("text", "בחירה שאינה קיימת"), *prompt.messages],
                ),
                cfg,
            )

        collected = (*collected, ctx.digit)
        if len(collected) < width:
            return _reply(
                drv,
                tree_mod.collect_prompt(node, base, ctx.step, collected),
                cfg,
            )

        value = int("".join(collected))
        field_name = str(node.collect.get("field", ""))
        leaf = replace(node, data={field_name: value}, collect={})

        self._report_call(entry, driver_id, base, leaf)
        result = await self._run_leaf(leaf)

        # אישור הערך שהוקש, לפני הקראת המצב. בלי זה מי שכיוון 22
        # מעלות במזגן כבוי שומע "כבוי" בלבד ואינו יודע אם ההקשה
        # שלו נקלטה.
        unit = field_unit(field_name)
        confirmation = [Say("text", node.say), *say_number(value)]
        if unit:
            confirmation.append(Say("text", unit))
        result = [*confirmation, *result]

        parent_path = base[:-1]
        parent = tree_mod.resolve(root, parent_path) or root
        prompt = tree_mod.prompt_for(
            parent, parent_path, ctx.step, supports_goto=drv.SUPPORTS_GOTO
        )
        return _reply(
            drv, replace(prompt, messages=[*result, *prompt.messages]), cfg
        )

    def _say_alerts(self, entry, node, caller: str) -> list[Say]:
        """ההתראות של המתקשר, מהחדשה לישנה.

        מסוננות לפי מספרו: התראה מיועדת לאדם מסוים, ולכן מי
        שמתקשר שומע את שלו בלבד ולא של אחר. גם צינתוק — שאין בו
        תוכן בשיחה עצמה — מותיר כאן את הטקסט, ולכן שלוחה זו הופכת
        צינתוק זול (עשירית יחידה) למערכת התראות מלאה.
        """
        from . import announce as announce_store  # noqa: PLC0415

        items = announce_store.recent_alerts(
            self.hass, entry.entry_id, caller, unheard_only=True
        )
        if not items:
            return [Say("text", "אין התראות חדשות עבורך")]
        prompt = (node.intro or "").strip() or "ההתראות שלך"
        says = [Say("text", prompt)]
        for alert in items:
            says.append(Say("text", str(alert.text)))
        # הושמעו — לא יוכרזו ולא יוקראו שוב, ומי שכל נמעניה שמעו
        # יורדת מהלוג כדי שלא יצטבר.
        announce_store.mark_heard(self.hass, entry.entry_id, caller)
        announce_store.prune_heard(self.hass, entry.entry_id)
        return says

    # ------------------------------------------------------------------

    def _friendly_name(self, entity_id: str, state) -> str:
        """שם קריא למכשיר.

        מזהה טכני מוקרא כרצף אותיות חסר משמעות, ולכן נעשה ניסיון
        למצוא שם במרשם הישויות, ורק אחר כך לגזור שם מהמזהה.
        """
        name = state.attributes.get("friendly_name") if state else None
        # שם ידידותי אינו בהכרח ידידותי. מכשיר Zigbee שלא נתנו לו
        # שם מגיע עם כתובת ה-MAC שלו כשם, ו-0xa4c138f59bc7b721
        # מוקרא כרצף אותיות וספרות חסר משמעות — בדיוק מה שהבדיקה
        # הזו נועדה למנוע במזהה הישות.
        if name and not _looks_opaque(str(name)):
            return str(name)

        try:
            from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

            entry = er.async_get(self.hass).async_get(entity_id)
            if entry:
                for candidate in (entry.name, entry.original_name):
                    if candidate:
                        return str(candidate)
        except Exception:  # noqa: BLE001 — נפילה חזרה לגזירה מהמזהה
            pass

        object_id = entity_id.split(".", 1)[-1]
        readable = object_id.replace("_", " ").strip()
        if len(readable) >= 6 and not any(ch.isspace() for ch in readable):
            if sum(ch.isdigit() for ch in readable) >= 2:
                return DOMAIN_NAMES.get(entity_id.split(".", 1)[0], readable)
        return readable

    def _report_call(self, entry, driver_id: str, path: tuple[str, ...], node) -> None:
        """הודעה לחיישנים ולמנוע האוטומציות על בחירה בתפריט.

        הנתיב ולא הספרה: מאז תתי-התפריטים הספרה אינה ייחודית,
        ופריט ב-1/2 היה מפעיל גם את החיישנים של הפריט ב-3/2.
        """
        joined = "/".join(path)
        # האות מזוהה לפי רשומה, אחרת בחירה בתפריט של ספק אחד
        # מעדכנת את החיישנים של השני — הנתיב "1/2" קיים בשניהם.
        async_dispatcher_send(
            self.hass, signal_call_received(entry.entry_id), joined
        )
        # האירוע נשאר בשם אחד לשלושת הספקים כדי שאוטומציה קיימת
        # לא תישבר, והספק מגיע בתוכו.
        self.hass.bus.async_fire(
            EVENT_CALL_RECEIVED,
            {
                "provider": driver_id,
                "path": joined,
                "digit": path[-1] if path else "",
                "entity_id": node.entity or "",
                "action": node.action or "",
            },
        )

    async def _run_leaf(self, node) -> list[Say]:
        """הקראת מצב, או ביצוע פעולה והקראת התוצאה.

        מחזיר הודעות בלבד. מי שקורא מחליט לאן ממשיכים.
        """
        if node.is_group:
            return await self._run_group(node)

        state = self.hass.states.get(node.entity or "")
        if state is None:
            return [Say("text", "המכשיר לא נמצא")]

        name = self._friendly_name(node.entity, state)

        if not node.action:
            return [Say("text", f"{name} כרגע"), *_speak_state(state)]

        domain = node.entity.split(".", 1)[0]

        # המדיניות נבדקת גם כאן ולא רק בטופס. תת-רשומה שנשמרה לפני
        # שינוי מדיניות, או עריכה ידנית ב-storage, לא תעקוף אותה.
        if not action_allowed(self.hass, domain, node.action):
            _LOGGER.warning(
                "Blocked an attempt to call a forbidden action: %s.%s", domain, node.action
            )
            return [Say("text", "הפעולה אינה מורשית")]

        if domain_needs_confirmation(domain) and not node.confirmed:
            _LOGGER.warning("Blocked a sensitive action without confirmation: %s", node.entity)
            return [Say("text", "הפעולה דורשת אישור שלא ניתן")]

        new_state = await self._call_and_wait(node)
        if new_state is False:
            return [Say("text", "אירעה שגיאה בביצוע הפעולה")]
        if new_state is None:
            return [Say("text", "הפעולה בוצעה")]
        return [Say("text", f"{name} כרגע"), *_speak_state(new_state)]

    async def _run_group(self, node) -> list[Say]:
        """פעולה על קבוצה — כל האורות במטבח וכדומה.

        הישויות נפתרות עכשיו ולא בהגדרה, ולכן מכשיר שנוסף למרחב
        נכנס מעצמו ומכשיר שהוסר יורד. קבוצה ריקה נאמרת ולא
        מושתקת: "אין אורות במטבח" עדיף על שקט שנשמע כתקלה.
        """
        from . import smart as smart_mod  # noqa: PLC0415

        target = node.target
        entity_ids = smart_mod.match_entities(
            self.hass, target.get("domain", ""), target.get("area", ""),
            target.get("floor", ""), label=target.get("label", ""),
        )
        name = target.get("name") or node.say or "הקבוצה"
        if not entity_ids:
            return [Say("text", f"אין מכשירים ב{name}")]

        if not node.action:
            return [
                Say("text", f"{name} כרגע"),
                *self._speak_many(entity_ids),
            ]

        domain = target.get("domain", "")
        if not action_allowed(self.hass, domain, node.action):
            _LOGGER.warning(
                "Blocked an attempt to call a forbidden action: %s.%s",
                domain, node.action,
            )
            return [Say("text", "הפעולה אינה מורשית")]
        if domain_needs_confirmation(domain) and not node.confirmed:
            _LOGGER.warning("Blocked a sensitive action on a group: %s", domain)
            return [Say("text", "הפעולה דורשת אישור שלא ניתן")]

        try:
            async with asyncio.timeout(SERVICE_CALL_TIMEOUT):
                await self.hass.services.async_call(
                    domain, node.action,
                    {"entity_id": entity_ids, **node.data},
                    blocking=True,
                )
        except TimeoutError:
            _LOGGER.warning("Calling %s on %s did not finish in time", node.action, name)
            return [Say("text", "הפעולה נשלחה אך לא הסתיימה בזמן")]
        except Exception:  # noqa: BLE001 — השיחה ממשיכה גם בכשל
            _LOGGER.exception("Calling %s on %s failed", node.action, name)
            return [Say("text", "אירעה שגיאה בביצוע הפעולה")]

        count = len(entity_ids)
        word = "מכשיר אחד" if count == 1 else f"{count} מכשירים"
        return [Say("text", f"בוצע על {word}")]

    def _speak_many(self, entity_ids: list[str]) -> list[Say]:
        """מצב של כמה ישויות, בשמן או בספירה לפי הגודל.

        קבוצה קטנה מוקראת בשמות — "מזגן סלון על קירור, מזגן חדר
        שינה כבוי" — כי זה מה שהמתקשר באמת רצה לדעת. קבוצה גדולה
        מסוכמת: "שלושה דלוקים ושניים כבויים". ספירה על שני
        מכשירים נשמעת כחידה, ושמות על עשרה כרשימת מכולת.
        """
        if 0 < len(entity_ids) <= NAME_EACH_UP_TO:
            parts: list[Say] = []
            for entity_id in entity_ids:
                state = self.hass.states.get(entity_id)
                if state is None:
                    continue
                # דרך `_friendly_name` ולא ישירות מהמאפיין: מזהה
                # אטום כמו 0xa4c138f59bc7b721 מוקרא אחרת כרצף
                # תווים חסר משמעות.
                parts.append(Say("text", self._friendly_name(entity_id, state)))
                parts.extend(_speak_state(state))
            if parts:
                return parts

        counts: dict[str, int] = {}
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            key = str(state.state)
            counts[key] = counts.get(key, 0) + 1
        if not counts:
            return [Say("text", "לא ידוע")]

        if len(counts) == 1:
            return [Say("text", "כולם"), *_speak_state_word(next(iter(counts)))]

        parts = []
        for index, (value, count) in enumerate(
            sorted(counts.items(), key=lambda item: -item[1])
        ):
            if index:
                parts.append(Say("text", "ו"))
            parts.append(Say("number", str(count)))
            parts.extend(_speak_state_word(value))
        return parts

    async def _call_and_wait(self, node):
        """הפעלת השירות והמתנה לשינוי מצב אמיתי, לא sleep קבוע."""
        future: asyncio.Future = self.hass.loop.create_future()

        @callback
        def _listener(event) -> None:
            if not future.done():
                future.set_result(event.data.get("new_state"))

        unsub = async_track_state_change_event(self.hass, [node.entity], _listener)
        try:
            domain = node.entity.split(".", 1)[0]
            # תקרה על הקריאה עצמה. בלי זה שירות שנתקע חוסם את
            # הבקשה עד שהספק מוותר, והמתקשר שומע שקט ואז שגיאה.
            async with asyncio.timeout(SERVICE_CALL_TIMEOUT):
                await self.hass.services.async_call(
                    domain, node.action,
                    {"entity_id": node.entity, **node.data},
                    blocking=True,
                )
            try:
                return await asyncio.wait_for(future, timeout=STATE_CHANGE_TIMEOUT)
            except TimeoutError:
                # המכשיר לא דיווח בזמן. המצב הידוע האחרון עדיף על שקט.
                return self.hass.states.get(node.entity)
        except TimeoutError:
            _LOGGER.warning("Calling %s did not finish in time", node.entity)
            return self.hass.states.get(node.entity)
        except Exception:  # noqa: BLE001 — השיחה ממשיכה גם בכשל
            _LOGGER.exception("Calling %s failed", node.entity)
            return False
        finally:
            unsub()
            if not future.done():
                future.cancel()


# ----------------------------------------------------------------------


def _reply(drv, action, cfg: dict | None = None):
    """הגשת הפעולה לדרייבר, עם רשת ביטחון לנתיב שאינו ניתן לקידוד.

    קודם ישבו כאן שלושה ענפים, אחד לכל ספק, שידעו שימות מחזירה
    מחרוזת ושהשניים האחרים מחזירים JSON בפורמטים שונים. עכשיו
    הליבה אינה יודעת דבר על הפורמט: `respond` בונה את התשובה
    ורושם אותה לחוצץ האבחון, וספק רביעי לא ידרוש ענף רביעי.
    """
    if action is None:
        action = Terminal([Say("text", "להתראות")])

    try:
        return drv.respond(action, cfg or {})
    except CodecError:
        # לא אמור לקרות: עומק התפריט חסום ב-4 ולכן שם הפרמטר אינו
        # מתקרב למגבלה. נתפס בכל זאת, כי חריגה שאינה נתפסת כאן היא
        # 500 באמצע שיחה — ניתוק בלי הסבר ובלי שורה ביומן.
        _LOGGER.exception("Path exceeds the provider limit, hanging up")
        return drv.respond(Terminal([Say("text", "אירעה שגיאה בתפריט")]), cfg or {})


def _stream_url(request, token: str) -> str:
    """כתובת ערוץ הסטרימינג, כ-wss.

    נגזרת מהבקשה הנוכחית ולא מהגדרה, כדי שלא תוכל להתפצל ממנה.
    """
    base = str(request.url.with_query(None))
    root = base.split("/api/ha_ivr/", 1)[0]
    scheme = "wss" if root.startswith("https") else "ws"
    root = root.split("://", 1)[-1]
    return f"{scheme}://{root}/api/ha_ivr/stream/{token}"


def _speak_state(state) -> list[Say]:
    """מצב ישות כפריטי השמעה. מספרים לעולם לא כטקסט — ראו say_number."""
    raw = str(state.state)
    lowered = raw.lower()
    if lowered in _STATES:
        return [Say("text", _STATES[lowered])]

    # מצבי מיזוג, מאווררים ובוררים מתורגמים במילון המשותף,
    # אחרת הם מוקראים באנגלית.
    translated = translate_option(raw)
    if translated != raw:
        return [Say("text", translated)]

    try:
        number = float(raw)
    except (TypeError, ValueError):
        return [Say("text", raw)]

    unit = str(state.attributes.get("unit_of_measurement", "")).strip()
    parts = say_number(number)
    spoken = translate_unit(unit)
    if spoken:
        parts.append(Say("text", spoken))
    elif unit and unit not in _UNKNOWN_UNITS:
        # לא מוקרא, אבל כן נרשם: המילון גדל לפי מה שבאמת מופיע
        # אצל המשתמש, במקום לנחש מראש רשימת יחידות.
        _UNKNOWN_UNITS.add(unit)
        _LOGGER.info(
            "Unit of measurement with no translation, so it is not spoken: "
            "%r. It can be added to UNIT_NAMES in translations_he.py",
            unit,
        )
    return parts


def _looks_opaque(text: str) -> bool:
    """האם המחרוזת היא מזהה טכני ולא שם.

    מחמיר בכוונה: רק רצף הקסדצימלי ארוך, עם או בלי תחילית 0x.
    שם אמיתי כמו "Sonoff1" או "ESP32" אינו נפסל, כי החלפת שם תקין
    ב"התאורה" גרועה מהקראת שם קצת טכני.
    """
    cleaned = text.strip().lower().removeprefix("0x")
    return len(cleaned) >= 8 and all(ch in "0123456789abcdef" for ch in cleaned)


def _speak_state_word(raw: str) -> list[Say]:
    """מילת המצב בלבד, בלי יחידות — לשימוש בסיכום קבוצה."""
    lowered = raw.lower()
    if lowered in _STATES:
        return [Say("text", _STATES[lowered])]
    translated = translate_option(raw)
    return [Say("text", translated if translated != raw else raw)]


_PROXY_WARNED: set[str] = set()


def _warn_if_proxied(driver_id: str, remote: str | None, filtering: bool) -> None:
    """אזהרה חד־פעמית כשהכתובת הנראית אינה של הספק.

    מאחורי Cloudflare Tunnel או Nginx, request.remote הוא ה-proxy
    ולא הספק — ולכן הכתובת שנרשמת כאן חסרת ערך לסינון, וסינון
    שיוגדר לפיה ייכשל תמיד. הפתרון ב-configuration.yaml:

        http:
          use_x_forwarded_for: true
          trusted_proxies:
            - <כתובת ה-proxy>
    """
    if filtering or driver_id in _PROXY_WARNED:
        return
    try:
        addr = ipaddress.ip_address(remote or "")
    except ValueError:
        return
    if addr.is_private or addr.is_loopback:
        _PROXY_WARNED.add(driver_id)
        _LOGGER.warning(
            "Requests from %s arrive from an internal address (%s) - that is the proxy, not the provider. Collecting ranges from it is pointless until use_x_forwarded_for and trusted_proxies are set in configuration.yaml",
            driver_id, remote,
        )


def reset_warnings() -> None:
    """איפוס האזהרות החד-פעמיות.

    נקרא בפריקת הרשומה. בלעדיו אזהרה שהושתקה נשארת מושתקת עד
    ריסטרט של HA, ולכן תיקון הגדרות אינו מפיק שום סימן שהוא נתפס.
    """
    _PROXY_WARNED.clear()
    _UNKNOWN_UNITS.clear()
    net.forget_bad_networks()

def _digits(phone: str) -> str:
    return "".join(c for c in str(phone) if c.isdigit())


def _repeats(step: int, path: tuple[str, ...]) -> int:
    """כמה פעמים הושמע התפריט בלי שהמתקשר הקיש.

    הצעד עולה בכל סיבוב, והנתיב מתארך רק בהקשה אמיתית — ולכן
    ההפרש ביניהם הוא בדיוק מספר הסיבובים הריקים, והוא מתאפס לבד
    ברגע שמקישים.

    הגרסה הקודמת ספרה פרמטרים שהצטברו. בימות ובטכנוליין זה עבד
    כי הם צוברים, אבל Vonage מחזירה פרמטר אחד בלבד — המונה נתקע
    על אחת, התקרה לא נחצתה, והתפריט חזר בלולאה אינסופית.
    """
    return max(0, step - len(path) - 1)
