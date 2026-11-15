"""נקודת הקצה. אחת לכל הספקים — הדרייבר רק מפענח ומרנדר."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import logging
import time
from dataclasses import replace

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    DOMAIN_NAMES,
    EVENT_CALL_RECEIVED,
    MENU_MAX_REPEATS,
    SERVICE_CALL_TIMEOUT,
    signal_call_received,
)
from .policy import action_allowed, domain_needs_confirmation
from .translations_he import field_unit

from . import call as call_mod
from . import security
from . import speech

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

# כמה מטלות מוקראות בשיחה, ובכמה תווים. רשימת קניות היא פריטים
# קצרים ועשרה מהם סבירים; תור SMS הוא פסקה לכל פריט, ושישה כאלה
# הם 690 תווים — כדקה של הקראה, ומעבר לתקרת הזמן של כל מנוע
# הקראה מקומי. לכן תקציב תווים ולא רק ספירה: פריט קצר אינו נפגע,
# ופריט ארוך נקטע.
TODO_MAX_SPOKEN = 10
TODO_ITEM_CHARS = 100
TODO_TOTAL_CHARS = 320

# יחידות שכבר נרשמו ביומן כלא מתורגמות. פעם אחת לכל יחידה,
# אחרת כל הקראת חיישן מייצרת שורה.
_UNKNOWN_UNITS = speech._UNKNOWN_UNITS

# הקשה כפולה: ב-VoIP ובסלולר אותו מקש מגיע לפעמים פעמיים בהפרש של
# מאות אלפיות. בלי סינון, `toggle` מתהפך פעמיים ותת-תפריט נפתח ומיד
# נבחר בו פריט. רק מקשי תפריט — באיסוף ספרות (קוד, מספר) 1111 הוא
# ערך לגיטימי.
DOUBLE_PRESS_SEC = 0.6
_LAST_KEY: dict[str, tuple[str, float]] = {}
_LAST_KEY_MAX = 500

# מה שהמתקשר שומע על כל תוצאה של הפעלה. ההבחנה חשובה: הוא אינו
# רואה יומן, ו"אירעה שגיאה" אחד לכל מקרה אינו אומר לו מה לעשות.
OUTCOME_WORDS = {
    call_mod.UNAVAILABLE: "המכשיר אינו זמין כרגע",
    call_mod.MISSING: "המכשיר לא נמצא",
    call_mod.NOT_FOUND: "הפעולה אינה קיימת עוד",
    call_mod.NOT_SUPPORTED: "המכשיר אינו תומך בפעולה",
    call_mod.INVALID: "הערך אינו תקין",
    call_mod.SCHEMA: "הערך אינו תקין",
    call_mod.UNAUTHORIZED: "אין הרשאה לפעולה",
    call_mod.FAILED: "המכשיר לא הגיב",
    call_mod.TIMEOUT: "הפעולה נשלחה אך לא הסתיימה בזמן",
    call_mod.ERROR: "אירעה שגיאה בביצוע הפעולה",
}
# הודעה מתורגמת של HA ארוכה מזה אינה מוקראת — היא נכתבה למסך.
MAX_SPOKEN_MESSAGE = 120


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
        # יש מי ששולח JSON בגוף ולא טופס, ומעביר את ההקשה שם. לכן
        # הגוף נשמר כמו שהוא ולא נמעך לתוך הפרמטרים.
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
        if not getattr(drv, "HAS_ENDPOINT", True):
            # קו שמנהל את השיחה בעצמו אינו מקבל בקשות מבחוץ.
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

        # חתימה אחת לכל הדרייברים. מי שאינו צריך את הגוף
        # מתעלם ממנו.
        ctx = drv.parse(params, body or {})
        cfg["caller"] = ctx.caller
        return await self.async_step(
            drv, entry, ctx, cfg,
            remote=request.remote, method=request.method, filtering=bool(allowed),
        )

    async def async_step(
        self, drv, entry, ctx, cfg: dict, *,
        remote: str | None = None, method: str = "", filtering: bool = False,
    ):
        """הצעד הבא בתפריט, בלי תלות בדרך שבה הבקשה הגיעה.

        בקשת HTTP מספק מגיעה לכאן מ-`_handle`. קו שמנהל את השיחה
        בעצמו קורא לכאן ישירות, דרך `async_menu_step`.
        """
        driver_id = drv.DRIVER_ID
        opts = entry.options

        if ctx.hangup:
            # מגיעה עם אותם פרמטרים כמו הבקשה שלפניה, ולכן נראית
            # ביומן כהקשה חוזרת אם לא מבדילים.
            _LOGGER.debug("%s <- hangup, caller=%s", driver_id, ctx.caller)
            return _reply(drv, None)

        _LOGGER.debug(
            "%s <- [%s] path=%s key=%s step=%s caller=%s from=%s",
            driver_id, method, ctx.path or "(שורש)", ctx.digit,
            ctx.step, ctx.caller, remote,
        )
        _warn_if_proxied(driver_id, remote, filtering)

        # נבנה מחדש בכל בקשה, ולכן משקף תמיד את ההגדרות
        # העדכניות. לכל רשומה עץ משלה.
        root = menu_mod.build_tree(self.hass, entry)
        found = tree_mod.find_collector(root, ctx.path)
        secret = found is not None and found[0].is_secret

        # ספרות של קוד נוסעות בנתיב. ביומן הן מוסתרות.
        shown_path = (
            "/".join([*found[1], *("•" for _ in found[2])]) if secret
            else "/".join(ctx.path)
        )
        history.record(
            "menu.request",
            driver=driver_id,
            path=shown_path or "(שורש)",
            digit="•" if secret and ctx.digit not in (None, KEY_ROOT) else ctx.digit,
            step=ctx.step,
            caller=ctx.caller,
            remote=remote,
        )

        phones = opts.get("allowed_phones") or []
        if phones and _digits(ctx.caller) not in {_digits(p) for p in phones}:
            _LOGGER.warning("Blocked a call from %s", ctx.caller)
            return _reply(
                drv,
                Terminal([Say("text", "המספר שלך אינו מורשה")]),
                cfg,
            )

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
        if found is not None:
            if found[0].is_secret:
                return await self._collect_code(drv, entry, driver_id, root, ctx, cfg, found)
            return await self._collect_digit(drv, entry, driver_id, root, ctx, cfg, found)

        if ctx.digit is not None and _double_press(ctx):
            _LOGGER.debug("%s: dropped a repeated key %s", driver_id, ctx.digit)
            node = tree_mod.resolve(root, ctx.path) or root
            return _reply(
                drv,
                tree_mod.prompt_for(node, ctx.path, ctx.step,
                                    supports_goto=drv.SUPPORTS_GOTO),
                cfg,
            )

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
            return _reply(drv, goto, cfg)

        # צומת איסוף מספר. לא עלה: הפעלה בלי הערך שטרם הוקש הייתה
        # קוראת לשירות בלי פרמטר, נכשלת, ומשמיעה "אירעה שגיאה"
        # לפני שהמתקשר בכלל הספיק להקיש.
        if node.is_collect:
            if node.is_secret and security.blocked(
                self.hass, entry.entry_id, ctx.call_id or ctx.caller, ctx.caller
            ):
                return self._code_blocked(drv, root, path, ctx, cfg)
            return _reply(
                drv, tree_mod.collect_prompt(node, path, ctx.step, ()), cfg
            )

        # הכתבה: המתקשר עובר לשלוחת הסטרימינג, שם הטקסט מוקלט, מוקרא
        # לאישור ומופעל, ואז הוא חוזר לכאן.
        if node.is_dictate:
            from . import dictation  # noqa: PLC0415

            goto = dictation.async_start(self.hass, entry, node, path, ctx)
            if goto is not None:
                self._report_call(entry, driver_id, path, node)
                return _reply(drv, goto, cfg)
            parent_path = path[:-1]
            parent = tree_mod.resolve(root, parent_path) or root
            prompt = tree_mod.prompt_for(
                parent, parent_path, ctx.step, supports_goto=drv.SUPPORTS_GOTO
            )
            return _reply(
                drv,
                replace(prompt, messages=[
                    Say("text", "ההכתבה אינה זמינה כרגע"), *prompt.messages,
                ]),
                cfg,
            )

        # עלה. מבצעים, ואז מחזירים את תפריט ההורה עם התוצאה בראשו.
        #
        # לא לנווט לשום מקום. אצל ספק ששלוחת ה-API שלו יושבת
        # בשורש, ניווט לשורש אחרי פעולה מחזיר אליה עצמה שוב ושוב;
        # אצל ספק אחר הוא מנתק אחרי כל פעולה. תשובה אחת בלי ניווט
        # נמנעת משניהם, וגם חוסכת סיבוב שרת.
        if node.alerts:
            # שלוחת "התראות אחרונות": מקריאה את היומן במקום להריץ
            # פעולה. מסוננת לפי מספר המתקשר — כל אחד שומע את שלו.
            result = self._say_alerts(entry, node, ctx.caller)
        else:
            self._report_call(entry, driver_id, path, node)
            result = await self._run_leaf(node, entry)

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
        result = await self._run_leaf(leaf, entry)

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

    def _code_blocked(self, drv, root, path, ctx, cfg):
        """פעולות הקוד נעולות. חוזרים לתפריט ההורה בלי לאסוף ספרות."""
        parent_path = tuple(path[:-1])
        parent = tree_mod.resolve(root, parent_path) or root
        prompt = tree_mod.prompt_for(
            parent, parent_path, ctx.step, supports_goto=drv.SUPPORTS_GOTO
        )
        return _reply(
            drv,
            replace(prompt, messages=[
                Say("text", "פעולות עם קוד חסומות כרגע. נסו שוב מאוחר יותר"),
                *prompt.messages,
            ]),
            cfg,
        )

    async def _collect_code(self, drv, entry, driver_id, root, ctx, cfg, found):
        """הספרה הבאה של קוד, ובסוף — הפעלה עם הקוד.

        הקוד אינו מוקרא, אינו נרשם ואינו נשמר. הספרות נוסעות בנתיב
        כמו בכל איסוף, ולכן הן מוסתרות ביומן (ראו `async_step`).
        """
        node, base, collected = found
        call_key = ctx.call_id or ctx.caller

        if ctx.digit == KEY_ROOT:
            prompt = tree_mod.prompt_for(
                root, (), ctx.step, supports_goto=drv.SUPPORTS_GOTO
            )
            return _reply(drv, prompt, cfg)

        if security.blocked(self.hass, entry.entry_id, call_key, ctx.caller):
            return self._code_blocked(drv, root, base, ctx, cfg)

        if ctx.digit is None:
            return _reply(drv, tree_mod.collect_prompt(node, base, ctx.step, ()), cfg)

        if ctx.digit not in tree_mod.valid_next_digits(node.collect, collected):
            prompt = tree_mod.collect_prompt(node, base, ctx.step, collected)
            return _reply(
                drv,
                replace(prompt, messages=[Say("text", "בחירה שאינה קיימת"), *prompt.messages]),
                cfg,
            )

        if ctx.digit != tree_mod.KEY_END:
            collected = (*collected, ctx.digit)
        if not tree_mod.code_complete(node.collect, collected, ctx.digit):
            # בין ספרות של קוד: ארבע שניות, לא עשר. מי שהפסיק להקיש
            # באמצע קוד לא יחזור אליו, ולא כדאי להשאיר אותו פתוח.
            prompt = tree_mod.collect_prompt(node, base, ctx.step, collected)
            return _reply(drv, replace(prompt, timeout=4), cfg)

        code = "".join(collected)
        leaf = replace(node, data={**node.data, "code": code}, collect={})
        self._report_call(entry, driver_id, base, replace(leaf, data={}))
        result, outcome = await self._run_leaf_outcome(leaf, entry)
        del code, leaf

        if outcome is not None and outcome.status == call_mod.INVALID:
            security.record_failure(self.hass, entry.entry_id, call_key, ctx.caller)
            result = [Say("text", "הקוד שגוי או שהפעולה נדחתה")]
        elif outcome is not None and outcome.succeeded:
            security.record_success(self.hass, entry.entry_id, call_key)

        parent_path = base[:-1]
        parent = tree_mod.resolve(root, parent_path) or root
        prompt = tree_mod.prompt_for(
            parent, parent_path, ctx.step, supports_goto=drv.SUPPORTS_GOTO
        )
        return _reply(drv, replace(prompt, messages=[*result, *prompt.messages]), cfg)

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

        הנתיב ולא הספרה: עם תתי-תפריטים הספרה אינה ייחודית, ולפיה
        פריט ב-1/2 מפעיל גם את החיישנים של הפריט ב-3/2.
        """
        joined = "/".join(path)
        # האות מזוהה לפי רשומה, אחרת בחירה בתפריט של ספק אחד
        # מעדכנת את החיישנים של השני — הנתיב "1/2" קיים בשניהם.
        async_dispatcher_send(
            self.hass, signal_call_received(entry.entry_id), joined
        )
        # האירוע בשם אחד לכל הספקים, כדי שאוטומציה קיימת לא
        # תישבר, והספק מגיע בתוכו.
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

    async def _run_leaf(self, node, entry=None) -> list[Say]:
        """הקראת מצב, או ביצוע פעולה והקראת התוצאה.

        מחזיר הודעות בלבד. מי שקורא מחליט לאן ממשיכים.
        """
        says, _outcome = await self._run_leaf_outcome(node, entry)
        return says

    async def _run_leaf_outcome(self, node, entry=None):
        """כמו `_run_leaf`, ומחזיר גם את התוצאה — למי שצריך לדעת אם
        הפעולה נדחתה (קוד שגוי) ולא רק מה להקריא."""
        entry_id = getattr(entry, "entry_id", "")
        if node.is_group:
            return await self._run_group(node, entry_id)

        state = self.hass.states.get(node.entity or "")
        if state is None:
            return [Say("text", "המכשיר לא נמצא")], None

        name = self._friendly_name(node.entity, state)

        if not node.action:
            # מצב של רשימת מטלות הוא מספר הפריטים הפתוחים בלבד.
            # התוכן מגיע משירות תגובה.
            if node.entity and node.entity.startswith("todo."):
                return await self._speak_todo([node.entity], name), None
            return [Say("text", f"{name} כרגע"), *_speak_state(state)], None

        entity_domain = node.entity.split(".", 1)[0]
        domain, action = call_mod.split_action(node.action, entity_domain)

        # המדיניות נבדקת גם כאן ולא רק בטופס. תת-רשומה שנשמרה לפני
        # שינוי מדיניות, או עריכה ידנית ב-storage, לא תעקוף אותה.
        if not _permitted(self.hass, entity_domain, domain, action):
            _LOGGER.warning(
                "Blocked an attempt to call a forbidden action: %s.%s", domain, action
            )
            return [Say("text", "הפעולה אינה מורשית")], None

        if _needs_confirmation(entity_domain, domain, action) and not node.confirmed:
            _LOGGER.warning("Blocked a sensitive action without confirmation: %s", node.entity)
            return [Say("text", "הפעולה דורשת אישור שלא ניתן")], None

        outcome = await call_mod.async_call_one(
            self.hass, node.entity, node.action, dict(node.data), entry_id=entry_id
        )
        return self._outcome_says(name, outcome), outcome

    def _outcome_says(self, name: str, outcome) -> list[Say]:
        """מה שהמתקשר שומע על תוצאה של הפעלה על ישות אחת."""
        if outcome.status in (call_mod.OK, call_mod.UNCONFIRMED):
            if outcome.state is None:
                return [Say("text", "הפעולה בוצעה")]
            prefix = [Say("text", "לא אושר")] if outcome.status == call_mod.UNCONFIRMED else []
            return [*prefix, Say("text", f"{name} כרגע"), *_speak_state(outcome.state)]
        if outcome.status == call_mod.TIMEOUT:
            says = [Say("text", OUTCOME_WORDS[call_mod.TIMEOUT])]
            if outcome.state is not None:
                says += [Say("text", f"{name} כרגע"), *_speak_state(outcome.state)]
            return says
        message = (outcome.message or "").strip()
        if message and len(message) <= MAX_SPOKEN_MESSAGE and outcome.status in (
            call_mod.INVALID, call_mod.FAILED, call_mod.NOT_SUPPORTED,
        ):
            return [Say("text", message)]
        return [Say("text", OUTCOME_WORDS.get(outcome.status, OUTCOME_WORDS[call_mod.ERROR]))]

    async def _run_group(self, node, entry_id: str = ""):
        """פעולה על קבוצה — כל האורות במטבח וכדומה.

        הישויות נפתרות עכשיו ולא בהגדרה, ולכן מכשיר שנוסף למרחב
        נכנס מעצמו ומכשיר שהוסר יורד. קבוצה ריקה נאמרת ולא
        מושתקת: "אין אורות במטבח" עדיף על שקט שנשמע כתקלה.
        """
        from . import smart as smart_mod  # noqa: PLC0415

        target = node.target
        entity_ids = smart_mod.match_entities(
            self.hass, target.get("domain", ""), target.get("target") or {}
        )
        name = target.get("name") or node.say or "הקבוצה"
        if not entity_ids:
            return [Say("text", f"אין מכשירים ב{name}")], None

        if not node.action:
            if target.get("domain") == "todo":
                return await self._speak_todo(entity_ids, name), None
            return [
                Say("text", f"{name} כרגע"),
                *self._speak_many(entity_ids),
            ], None

        entity_domain = target.get("domain", "")
        domain, action = call_mod.split_action(node.action, entity_domain)
        if not _permitted(self.hass, entity_domain, domain, action):
            _LOGGER.warning(
                "Blocked an attempt to call a forbidden action: %s.%s", domain, action,
            )
            return [Say("text", "הפעולה אינה מורשית")], None
        if _needs_confirmation(entity_domain, domain, action) and not node.confirmed:
            _LOGGER.warning("Blocked a sensitive action on a group: %s", entity_domain)
            return [Say("text", "הפעולה דורשת אישור שלא ניתן")], None

        outcome = await call_mod.async_call_many(
            self.hass, entity_ids, node.action, dict(node.data), entry_id=entry_id
        )
        return _group_says(outcome), outcome

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

    async def _speak_todo(self, entity_ids: list[str], name: str) -> list[Say]:
        """המטלות הפתוחות עצמן, ולא רק כמה יש.

        המצב של ישות `todo` הוא מספר הפריטים הפתוחים, ולכן הקראת
        מצב רגילה אומרת "שלוש" ולא מה הן. התוכן מגיע מ-
        `todo.get_items`, שהוא שירות תגובה ומחזיר את הפריטים
        במקום לשנות דבר. ברירת המחדל שלו היא הפתוחים בלבד, וזה
        מה שרוצים לשמוע.
        """
        try:
            async with asyncio.timeout(SERVICE_CALL_TIMEOUT):
                response = await self.hass.services.async_call(
                    "todo", "get_items", {"entity_id": entity_ids},
                    blocking=True, return_response=True,
                )
        except Exception:  # noqa: BLE001 — השיחה ממשיכה גם בכשל
            _LOGGER.exception("Reading the to-do list failed")
            return [Say("text", "אירעה שגיאה בקריאת הרשימה")]

        items: list[str] = []
        for entity_id in entity_ids:
            entry = (response or {}).get(entity_id) or {}
            for item in entry.get("items") or []:
                summary = str((item or {}).get("summary") or "").strip()
                if summary:
                    items.append(summary)

        if not items:
            return [Say("text", f"אין מטלות ב{name}")]

        count = len(items)
        says = [Say("text", name)]
        says.append(
            Say("text", "מטלה אחת") if count == 1
            else Say("text", f"{count} מטלות")
        )

        spoken = 0
        said = 0
        for item in items[:TODO_MAX_SPOKEN]:
            # שורות חדשות ורווחים כפולים מגיעים מתוכן SMS ואינם
            # נשמעים; הם רק מאריכים את מה שנשלח להקראה.
            text = " ".join(item.split())[:TODO_ITEM_CHARS]
            if spoken and spoken + len(text) > TODO_TOTAL_CHARS:
                break
            says.append(Say("text", text))
            spoken += len(text)
            said += 1

        if count > said:
            says.append(Say("text", f"ועוד {count - said}"))
        return says

# ----------------------------------------------------------------------


def _reply(drv, action, cfg: dict | None = None):
    """הגשת הפעולה לדרייבר, עם רשת ביטחון לנתיב שאינו ניתן לקידוד.

    הליבה אינה יודעת דבר על הפורמט: `respond` של הדרייבר בונה את
    התשובה ורושם אותה לחוצץ האבחון, וספק נוסף אינו דורש ענף כאן.
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


async def async_menu_step(hass: HomeAssistant, entry, ctx):
    """הצעד הבא בתפריט, לקו שמנהל את השיחה בעצמו.

    אותו מנוע בדיוק שעונה לספקים ב-HTTP: אותן הרשאות, אותו עץ ואותה
    הפעלה. ההבדל היחיד הוא שהפעולה חוזרת כמו שהיא ולא כתשובת HTTP.
    """
    drv = registry.for_entry(entry)
    cfg = {
        "options": dict(entry.options),
        "entry_id": entry.entry_id,
        "caller": ctx.caller,
    }
    return await IvrView(hass).async_step(drv, entry, ctx, cfg)


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
    """מצב ישות כפריטי השמעה. ראו `speech.speak_state`."""
    return speech.speak_state(state)


def _looks_opaque(text: str) -> bool:
    """האם המחרוזת היא מזהה טכני ולא שם.

    מחמיר בכוונה: רק רצף הקסדצימלי ארוך, עם או בלי תחילית 0x.
    שם אמיתי כמו "Sonoff1" או "ESP32" אינו נפסל, כי החלפת שם תקין
    ב"התאורה" גרועה מהקראת שם קצת טכני.
    """
    cleaned = text.strip().lower().removeprefix("0x")
    return len(cleaned) >= 8 and all(ch in "0123456789abcdef" for ch in cleaned)


def _speak_state_word(raw: str, domain: str = "") -> list[Say]:
    """מילת המצב בלבד, בלי יחידות — לשימוש בסיכום קבוצה."""
    return speech.speak_word(raw, domain)


def _double_press(ctx) -> bool:
    """האם זו אותה הקשה שהגיעה פעמיים, תוך פחות מ-`DOUBLE_PRESS_SEC`."""
    key = ctx.call_id or ctx.caller
    if not key:
        return False
    now = time.monotonic()
    last = _LAST_KEY.get(key)
    _LAST_KEY[key] = (ctx.digit, now)
    if len(_LAST_KEY) > _LAST_KEY_MAX:
        for stale in [k for k, (_, t) in _LAST_KEY.items() if now - t > 60]:
            _LAST_KEY.pop(stale, None)
    return last is not None and last[0] == ctx.digit and now - last[1] < DOUBLE_PRESS_SEC


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

    ספירת פרמטרים שהצטברו אינה מחליפה את זה: היא עובדת רק אצל
    ספק שצובר אותם, ואצל ספק שמחזיר פרמטר אחד המונה נתקע על אחת.
    """
    return max(0, step - len(path) - 1)


def _permitted(hass, entity_domain: str, domain: str, action: str) -> bool:
    """האם מותר להפעיל. פעולה מדומיין אחר — רק שלוש הפעולות של קבוצה."""
    from .capabilities import GROUP_ACTION_DOMAIN, GROUP_ACTIONS  # noqa: PLC0415

    if domain == entity_domain:
        return action_allowed(hass, domain, action)
    return (
        entity_domain == "group"
        and domain == GROUP_ACTION_DOMAIN
        and action in GROUP_ACTIONS
        and hass.services.has_service(domain, action)
    )


def _needs_confirmation(entity_domain: str, domain: str, action: str) -> bool:
    """הדלקה וכיבוי של קבוצה עוברים דרך `homeassistant`, שדורש אישור.
    אלה פעולות רגילות של קבוצה, ולכן אינן דורשות."""
    from .capabilities import GROUP_ACTION_DOMAIN, GROUP_ACTIONS  # noqa: PLC0415

    if entity_domain == "group" and domain == GROUP_ACTION_DOMAIN and action in GROUP_ACTIONS:
        return False
    return domain_needs_confirmation(domain)


def _count(n: int, one: str, many: str) -> str:
    return one if n == 1 else f"{n} {many}"


def _group_says(outcome) -> list[Say]:
    """סיכום של פעולה על קבוצה: כמה ביצעו, כמה לא זמינים, כמה נכשלו."""
    if outcome.done and outcome.done == outcome.total:
        return [Say("text", f"בוצע על {_count(outcome.done, 'מכשיר אחד', 'מכשירים')}")]
    if outcome.done:
        parts = [f"בוצע ב-{outcome.done} מתוך {outcome.total}"]
        if outcome.unavailable:
            parts.append(_count(outcome.unavailable, "אחד לא זמין", "לא זמינים"))
        if outcome.failed:
            parts.append(_count(outcome.failed, "אחד נכשל", "נכשלו"))
        return [Say("text", ", ".join(parts))]
    if outcome.unavailable and outcome.unavailable == outcome.total:
        return [Say("text", "המכשירים אינם זמינים כרגע")]
    return [Say("text", OUTCOME_WORDS.get(outcome.status, OUTCOME_WORDS[call_mod.ERROR]))]
