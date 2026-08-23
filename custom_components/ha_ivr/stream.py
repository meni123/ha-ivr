"""ערוץ הסטרימינג — הקו, לא המנוע.

הספק מתחבר לכאן ב-wss, כלומר TLS על פורט 443 — אותו נתיב שכבר
משמש את התפריט, בלי לפתוח פורט נוסף ובלי לחשוף SIP.

המודול מחזיק את מה שתלוי בספק: האימות, פענוח המסגרות, זיהוי
הספק לפי מסגרת הפתיחה, ההקשות ופקודות הבקרה. הצינור, האודיו
והתורות יושבים ב-`satellite.py`.

`_Session` היא צד הקו של השיחה, והיא מדברת עם הישות בארבע
פעולות בלבד: `send_audio`, `leave`, `close`, `hung_up`. הישות
מדברת איתה דרך `on_chunk`. כל השאר פנימי לצד שלו.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
from typing import Any

from aiohttp import WSMsgType, web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from . import announce as announce_store
from . import history
from . import net
from . import registry
from .audio import PROVIDER_RATE, error_tone
from .config_shared import num
from .const import DOMAIN, SATELLITES
from .const import (
    CONF_STREAM_RETURN_PATH,
    DEFAULT_EXIT_KEYS,
    DEFAULT_MAX_CALL_MINUTES,
    DEFAULT_STREAM_RETURN_PATH,
)

_LOGGER = logging.getLogger(__name__)

# כמה מסגרות ראשונות לרשום ביומן בפירוט.
INSPECT_FRAMES = 12


class StreamView(HomeAssistantView):
    """נקודת הקצה שהספקים מתחברים אליה בכל שיחה."""

    url = "/api/ha_ivr/stream/{token}"
    name = "api:ha_ivr:stream"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def _entries_of(self, drv):
        """הרשומות של הספק הזה, מתוך הדומיין המשותף."""
        return [
            e for e in self.hass.config_entries.async_entries(DOMAIN)
            if str(e.data.get("provider", "")) == drv.DRIVER_ID
        ]

    def _entry_for(self, token: str):
        """הרשומה שהטוקן שייך לה, מבין הספקים בעלי ערוץ סטרימינג.

        הכתובת אחת לכל הספקים, ולכל רשומה טוקן משלה — ולכן
        הטוקן הוא מה שמזהה את הרשומה. השוואה בזמן קבוע, כמו
        בנקודת הקצה של התפריט.
        """
        for driver_id in registry.registered():
            drv = registry.get(driver_id)
            if not getattr(drv, "SUPPORTS_STREAM", False):
                continue
            for entry in self._entries_of(drv):
                expected = str(entry.data.get("token", ""))
                if expected and hmac.compare_digest(str(token), expected):
                    return entry
        return None

    async def get(self, request: web.Request, token: str) -> web.StreamResponse:
        if not registry.registered():
            return web.Response(status=503, text="Not configured")

        entry = self._entry_for(token)
        if entry is None:
            _LOGGER.warning("Stream: bad token from %s", request.remote)
            return web.Response(status=401, text="Unauthorized")

        expected = str(entry.data.get("token", ""))

        # ה-Bearer חובה, בלי תנאי.
        #
        # הטוקן שבנתיב אינו יכול להיות ריק — `_entry_for` כבר
        # סינן אותו — ולכן אין מצב שבו אין מה לאכוף. בדיקה
        # מותנית בקיום הכותרת אינה שכבה בכלל: מי שמחזיק את
        # הטוקן ומשמיט את הכותרת מגיע לאותו מקום.
        #
        # ספק שאינו יכול לשלוח את הכותרת אינו נתמך בערוץ.
        auth = request.headers.get("Authorization", "").strip()
        supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else auth
        if not hmac.compare_digest(supplied, expected):
            _LOGGER.warning(
                "Stream: Bearer %s from %s",
                "missing" if not auth else "invalid", request.remote,
            )
            return web.Response(status=401, text="Unauthorized")

        # רישום מלא של הכתובת והכותרות. מזהה הערוץ שטכנוליין
        # מייצרים בטופס נשלח אלינו במקום שאינו מתועד — פרמטר
        # בכתובת, כותרת, או מסגרת ראשונה. בלי לרשום את שלושתם
        # אי אפשר לדעת מאיפה לקרוא אותו.
        _LOGGER.debug(
            "Stream: query=%s",
            dict(request.query) or "(empty)",
        )
        _LOGGER.debug(
            "Stream: headers=%s",
            {
                k: ("***" if k.lower() == "authorization" else v)
                for k, v in request.headers.items()
            },
        )

        allowed = _stream_ips(entry.options)
        if allowed and not net.ip_allowed(request.remote, allowed):
            _LOGGER.warning(
                "Stream: blocked address %s. Behind a proxy you need use_x_forwarded_for and trusted_proxies, otherwise the address you see is the proxy",
            request.remote,
            )
            return web.Response(status=403, text="Forbidden")

        minutes = int(num(
            entry.options.get("stream_max_minutes"), DEFAULT_MAX_CALL_MINUTES
        ))

        # אין כאן תקרת שיחות מקבילות: מספר הקווים הוא מספר
        # ישויות הלוויין של הרשומה, ושיחה שמעליו נדחית ב-`run`
        # בצליל. תקרה שנייה בשכבת ה-HTTP הייתה מתגלה למתקשר
        # כסוקט שנסגר בשקט.
        ws = web.WebSocketResponse(heartbeat=25)
        await ws.prepare(request)
        session = _Session(self.hass, ws, entry)
        if minutes:
            # תקרת אורך. שיחה שנשארת פתוחה מחזיקה קו, ולכן חייבת
            # סוף גם בלי שאף אחד מדבר.
            try:
                async with asyncio.timeout(minutes * 60):
                    await session.run()
            except TimeoutError:
                _LOGGER.info("Stream: the call exceeded %s minutes", minutes)
                with contextlib.suppress(Exception):
                    await ws.close()
        else:
            await session.run()
        return ws


class _Session:
    """שיחה אחת מצד הקו: מסגרות פנימה, אודיו ופקודות החוצה."""

    def __init__(self, hass: HomeAssistant, ws, entry) -> None:
        self.hass = hass
        self.ws = ws
        self.entry = entry
        self._seen = 0
        self._rate = PROVIDER_RATE
        self._call_id = ""
        self._caller = ""
        self._provider = ""
        self._driver = None
        self._started = False
        self._satellite = None
        self.exiting = False

        options = entry.options
        self._channel_token = str(options.get("stream_channel_token", "") or "")
        self._return_path = str(
            options.get(CONF_STREAM_RETURN_PATH, DEFAULT_STREAM_RETURN_PATH) or ""
        ).strip()
        self._exit_keys = {
            c
            for c in str(options.get("stream_exit_keys", DEFAULT_EXIT_KEYS) or "")
            if not c.isspace() and c != ","
        }

    # ------------------------------------------------------------------
    # מחזור החיים

    def _lines(self) -> list:
        """ישויות הלוויין של הרשומה, לפי סדר."""
        return list((self.hass.data.get(SATELLITES) or {}).get(self.entry.entry_id) or [])

    async def run(self) -> None:
        lines = self._lines()
        if not lines:
            # אין מנוע חלופי. פלטפורמה שלא נטענה היא כשל שקט —
            # `dependencies` בלי `assist_satellite` אינו מייצר שום
            # שגיאה ביומן — ולכן הכשל הזה מדבר, ובקול.
            _LOGGER.error(
                "Stream: no satellite entity for entry %s. The assist_satellite platform did not load",
            self.entry.entry_id,
            )
            await self._say_busy()
            return

        for line in lines:
            # הקצב עדיין ברירת המחדל כאן — מסגרת הפתיחה טרם
            # הגיעה. `_on_start` יעדכן אותו לפני התור הראשון.
            if line.attach(self, self._rate):
                self._satellite = line
                break
        else:
            # כל הקווים תפוסים. קבלה נוספת על קו תפוס מבטלת את
            # השיחה שרצה בו, ולכן השיחה נדחית — בצליל, ולא
            # בסוקט שנסגר בשקט.
            _LOGGER.warning("Stream: all %s lines are busy, rejecting the call", len(lines))
            await self._say_busy()
            return

        _LOGGER.info("Stream: line %s", self._satellite.entity_id)
        try:
            async for msg in self.ws:
                await self._on_message(msg)
        finally:
            if self._satellite is not None:
                self._satellite.detach(self)
                self._satellite = None
            _LOGGER.debug("Stream: connection closed after %s frames", self._seen)
            history.record(
                "stream.end",
                provider=self._provider or "(unidentified)",
                frames=self._seen,
                call_id=self._call_id,
                exiting=self.exiting,
            )

    # ------------------------------------------------------------------
    # מסגרות נכנסות

    async def _on_message(self, msg) -> None:
        self._seen += 1

        # הרישום המפורט מוגבל לתחילת החיבור. מסגרת אודיו מגיעה
        # עשרות פעמים בשנייה, ורישום של כולן ימלא את היומן.
        if self._seen <= INSPECT_FRAMES:
            preview = (
                msg.data[:80] if isinstance(msg.data, str) else msg.data[:24].hex()
            )
            _LOGGER.debug(
                "Stream: frame %s type=%s len=%s <- %s",
                self._seen,
                msg.type.name,
                len(msg.data) if msg.data else 0,
                preview,
            )

        if msg.type is WSMsgType.BINARY:
            if self._satellite is not None:
                self._satellite.on_chunk(msg.data)
            return

        if msg.type is WSMsgType.TEXT:
            await self._on_text(msg.data)
            return

        if msg.type is WSMsgType.ERROR:
            _LOGGER.warning("Stream: connection error: %s", self.ws.exception())

    async def _on_text(self, raw: str) -> None:
        """מסגרת טקסט: בקרה, או אודיו עטוף ב-JSON."""
        try:
            payload: Any = json.loads(raw)
        except ValueError:
            _LOGGER.debug("Stream: text frame that is not JSON: %s", raw[:120])
            return

        if not isinstance(payload, dict):
            return

        # אודיו עטוף — מקרה שכיח בספקים שמעדיפים ערוץ אחד.
        for key in ("audio", "media", "payload", "chunk"):
            if isinstance(payload.get(key), str):
                import base64  # noqa: PLC0415

                if self._satellite is not None:
                    with contextlib.suppress(Exception):
                        self._satellite.on_chunk(base64.b64decode(payload[key]))
                return

        if not self._started:
            # כל דרייבר עם ערוץ סטרימינג נשאל אם המסגרת שלו,
            # והראשון שעונה הוא הספק של השיחה. אין כאן שם ספק.
            for driver in registry.with_stream():
                # הרשומה ידועה מהטוקן, ולכן רק הדרייבר שלה
                # רלוונטי. בלי הסינון, שני ספקים יכולים לענות על
                # אותה מסגרת והראשון לפי סדר המיון מנצח — כולל
                # על רשומה שאינה שלו, ואז פקודות הבקרה נשלחות
                # בפרוטוקול הלא נכון ונבלעות בשקט.
                if driver.DRIVER_ID != str(self.entry.data.get("provider", "")):
                    continue
                meta = driver.detect(payload)
                if meta is not None:
                    self._on_start(driver, meta, payload)
                    return

        # מסגרת בקרה שאינה הקשה. `:dtmf` חייב להמשיך לחילוץ
        # שלמטה — בליעה גורפת של אירועי `websocket:` משאירה את
        # המקש מת, בלי קטיעת השמעה ובלי יציאה לתפריט.
        event = str(payload.get("event", ""))
        if event.startswith("websocket:") and not event.endswith(":dtmf"):
            _LOGGER.debug("Stream: channel event: %s", event)
            return

        if str(payload.get("type", "")) in ("stop", "hangup", "end"):
            _LOGGER.debug("Stream: the PBX signalled the end of the call")
            await self.hung_up()
            return

        digit = _find_digit(payload)
        if digit is not None:
            _LOGGER.debug("Stream: key press on channel: %s", digit)
            # הקשה באמצע הקראה = המתקשר רוצה לקטוע.
            await self._clear_playback()
            if digit in self._exit_keys and self._satellite is not None:
                _LOGGER.info("Stream: leaving to the menu on key %s", digit)
                await self._satellite.request_leave()
            return

        # מסגרת שאינה מוכרת. נרשמת במלואה, כי הפרוטוקול שלהם אינו
        # מתועד וכל מסגרת חדשה היא מידע.
        _LOGGER.info("Stream: control message from the PBX: %s", payload)

    def _on_start(self, driver, meta: dict, payload: dict) -> None:
        """מסגרת הפתיחה: מי הספק, מי המתקשר, ובאיזה קצב."""
        self._driver = driver
        self._provider = driver.DRIVER_ID
        self._started = True
        self._call_id = str(meta.get("call_id") or "")
        self._caller = str(meta.get("caller") or "")
        if meta.get("rate"):
            self._rate = int(meta["rate"])
            if self._satellite is not None:
                self._satellite.set_rate(self._rate)

        history.record(
            "stream.start",
            provider=self._provider,
            call_id=self._call_id,
            caller=self._caller,
            rate=self._rate,
        )

        got_token = str(meta.get("token") or "")
        if self._channel_token and got_token != self._channel_token:
            # שכבת אימות שנייה: גם מי שהשיג את הכתובת אינו יודע
            # את מזהה הערוץ, שנוצר אצל הספק ואינו נוסע בבקשה.
            _LOGGER.warning(
                "Stream: channel id does not match (%s), disconnecting", got_token or "ריק"
            )
            self.hass.async_create_task(self.ws.close())
            return

        _LOGGER.info(
            "Stream: %s, call from %s, id %s, %s Hz",
            self._provider,
            self._caller or "לא ידוע",
            self._call_id[:12] or "לא ידוע",
            self._rate,
        )

        pending = announce_store.claim(
            self.hass, self.entry.entry_id, self._caller
        )
        if pending is not None:
            _LOGGER.info(
                "Stream: this call is the pending alert - %s",
                (pending.message or "")[:60],
            )
            history.record(
                "stream.announce",
                provider=self._provider,
                call_id=self._call_id,
                caller=self._caller,
                message=(pending.message or "")[:200],
            )
            self.hass.async_create_task(self._deliver(pending))
            return

        self._open_input()

    def _open_input(self) -> None:
        """פתיחת הקלט לתור הראשון, בצליל "דבר עכשיו"."""
        if self._satellite is not None:
            self.hass.async_create_task(self._satellite.begin())

    async def _deliver(self, pending) -> None:
        """השמעת ההתראה, ואז ניתוק."""
        satellite = self._satellite
        if satellite is None:
            pending.error = "אין קו פנוי להשמעת ההתראה"
            pending.delivered.set()
            return

        self.exiting = True
        await satellite.play_announcement(pending)
        await self._finish(
            self._driver.hangup_command() if self._driver else None
        )

    async def _finish(self, command: dict | None) -> None:
        """שליחת פקודה סופית, או סגירת הסוקט אם אין לספק כזו.

        פקודה סופית מסיימת את הסשן אצל הספק והוא סוגר את הסוקט
        אחרי שניקז את האודיו — סגירה מצידנו קוטעת את המשפט האחרון.
        """
        if command is not None and not self.ws.closed:
            history.record(
                "stream.control", provider=self._provider, command=command
            )
            with contextlib.suppress(Exception):
                await self.ws.send_str(json.dumps(command))
            return

        with contextlib.suppress(Exception):
            await self.ws.close()

    # ------------------------------------------------------------------
    # מה שהישות קוראת לו

    async def send_audio(self, pcm: bytes) -> None:
        """שליחת PCM גולמי לקו. ההמתנה לניגון היא של הישות."""
        if self.ws.closed:
            return
        with contextlib.suppress(Exception):
            await self.ws.send_bytes(pcm)

    async def hung_up(self) -> None:
        """המתקשר ניתק — בהודעה מפורשת או בהיעדר אודיו."""
        await self._close_socket("המתקשר ניתק")

    async def close(self, reason: str) -> None:
        """סיום השיחה מצידנו, כשאין עוד מי שיענה למתקשר.

        עצירת הצינור אינה סוגרת את השיחה: הלולאה ב-`run` ממשיכה
        לקרוא מהסוקט, השער כבר לא ייפתח בידי איש, וההשתקה נשארת —
        כלומר המתקשר יושב בשקט מוחלט עד תקרת הדקות, ומחזיק כל אותו
        זמן קו. שני נוטשים היו סוגרים את העוזר.

        הסגירה מצידנו היא המסלול השמרני: היא כבר נצפתה בשיחה חיה
        (סשן שנסגר בלי פקודה סופית, והמתקשר חזר לתפריט דרך
        `endGoTo`). פקודת העברה מפורשת שייכת ל-`leave`, שם היא
        נובעת מבקשה של המתקשר ולא מכשל.
        """
        history.record(
            "stream.close",
            provider=self._provider or "(unidentified)",
            reason=reason,
            call_id=self._call_id,
        )
        await self._close_socket(reason)

    async def _close_socket(self, reason: str) -> None:
        _LOGGER.info("Stream: %s, closing the channel", reason)
        self.exiting = True
        with contextlib.suppress(Exception):
            await self.ws.close()

    async def leave(self) -> None:
        """יציאה מהעוזר וחזרה לתפריט.

        הדרייבר קובע מה נשלח: פקודת העברה מפורשת אם יש לספק כזו,
        אחרת סגירת הסוקט. היעד מפורש עדיף על הסתמכות על הגדרת
        שלוחה, והמרכזייה יודעת שזו העברה ולא נפילה.
        """
        self.exiting = True
        command = (
            self._driver.leave_command(self._return_path)
            if self._driver
            else None
        )
        if command is not None:
            _LOGGER.debug(
                "Stream: transferring to path %s and ending the session", self._return_path
            )
        await self._finish(command)

    # ------------------------------------------------------------------

    async def _clear_playback(self) -> None:
        """ריקון חוצץ ההשמעה אצל הספק.

        הספק מחזיק אודיו בחוצץ ומנגן אותו ברצף, ולכן בלי הפקודה
        הזו הקשה באמצע תשובה ארוכה לא מורגשת עד שהתשובה נגמרת.
        """
        command = self._driver.clear_command() if self._driver else None
        if command is None or self.ws.closed:
            return

        history.record("stream.control", provider=self._provider, command=command)
        with contextlib.suppress(Exception):
            await self.ws.send_str(json.dumps(command))

    async def _say_busy(self) -> None:
        """הודעה למתקשר שאין קו פנוי, ואז סגירה.

        סוקט שנסגר בלי מילה משאיר את המתקשר בלי לדעת אם טעה או
        שמשהו נפל. הצליל נשלח מכאן ולא דרך הישות, כי אין ישות
        פנויה — זה כל העניין.

        הקצב הוא עדיין ברירת המחדל — מסגרת הפתיחה טרם עובדה —
        ולכן בקו של 16k הצליל יישמע נמוך. עדיף צליל עמום מדחייה
        אילמת, והמצב עצמו נדיר: שני קווים ושלישית שיחות בו-זמנית.
        """
        history.record(
            "stream.reject",
            provider=self._provider or "(before start)",
            call_id=self._call_id,
        )
        pcm = error_tone(self._rate)
        with contextlib.suppress(Exception):
            await self.ws.send_bytes(pcm)
            await asyncio.sleep(len(pcm) / 2 / self._rate + 0.25)
        await self._close_socket("אין קו פנוי")


def _stream_ips(options) -> list[str]:
    """טווחי ה-IP המותרים לערוץ הסטרימינג.

    ברירת המחדל היא הטווחים שהוגדרו לספק בהגדרות התפריט — אותם
    שרתים מתחברים בשני הערוצים, ואין סיבה לתחזק שתי רשימות.
    הטווחים נלקחים מהרשומה שהטוקן שייך לה, כלומר מהספק הנכון.
    """
    explicit = options.get("stream_allowed_ips")
    if explicit:
        return list(explicit)
    return list(options.get("allowed_ips") or [])

def _find_digit(payload: dict) -> str | None:
    """חילוץ הקשה ממסגרת בקרה.

    ערוץ הבקרה של טכנוליין אינו מתועד, ולכן נבדקים שמות השדות
    המקובלים. מסגרת שאינה מזוהה נרשמת במלואה.
    """
    # Vonage: {"event":"websocket:dtmf","digit":"5","duration":260}
    if str(payload.get("event", "")).lower().endswith(":dtmf"):
        value = payload.get("digit")
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()[:1]

    if str(payload.get("type", "")).lower() in ("dtmf", "key", "keypress", "digit"):
        for field in ("digit", "key", "value", "data", "dtmf"):
            value = payload.get(field)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()[:1]
    for field in ("dtmf", "digit", "keypress"):
        value = payload.get(field)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()[:1]
    return None
