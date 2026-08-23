"""לוויין Assist — המנוע של העוזר הקולי.

הישות יורשת מ-`AssistSatelliteEntity`, מקבלת אודיו גולמי
ב-`on_chunk`, ומזינה אותו ל-`async_accept_pipeline_from_satellite`.
המבנה עוקב אחר `homeassistant/components/voip/assist_satellite.py`,
עם WebSocket במקום RTP כתחבורה.

חלוקת האחריות מול `stream.py`: מה שתלוי בפרוטוקול של הספק — סוקט,
אימות, פענוח מסגרות, הקשות ופקודות בקרה — יושב בתחבורה. מה שתלוי
בצינור — תור האודיו, לולאת התורות, ההשתקה, הצלילים וההקראה — יושב
כאן.

`async_accept_pipeline_from_satellite` פותרת את הצינור ואת רגישות
ה-VAD ממרשם הישויות ולא מההגדרות, ולכן שניהם ישויות `select`
ב-`select.py`.

לכל רשומה שתי ישויות לוויין, ו-`attach` תופסת את הפנויה. הישות
מחזיקה משימת צינור אחת בלבד, ו-`_cancel_running_pipeline()` רצה
בתחילת כל קבלה — שתי שיחות על אותה ישות פירושן שהשנייה הורגת את
הראשונה. לכן קו = ישות. השיוך הוא השדה `_session`, והשחרור הוא
ה-`finally` של `run()` בצד הסוקט.

ANNOUNCE נחשף על הקו הראשון בלבד: הוא פעולה של חשבון ולא של קו,
ואינו נוגע בסוקט.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from array import array

from homeassistant.components import tts
from homeassistant.components.assist_satellite import (
    AssistSatelliteConfiguration,
    AssistSatelliteEntity,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from . import announce as announce_store
from . import registry
from .audio import (
    DEFAULT_ECHO_TAIL,
    PIPELINE_RATE,
    PROVIDER_RATE,
    error_tone,
    listen_tone,
    resample,
    strip_wav,
    thinking_tone,
    wav_format,
)
from .const import DEFAULT_EXIT_PHRASES
from .outbound import OutboundError

_LOGGER = logging.getLogger(__name__)

# דומיין התרגום של הודעות השגיאה.
ERROR_DOMAIN = "ha_ivr"


def _error(key: str, **placeholders) -> HomeAssistantError:
    """שגיאה מתורגמת, לפי מפתח מ-`strings.json`."""
    return HomeAssistantError(
        translation_domain=ERROR_DOMAIN,
        translation_key=key,
        translation_placeholders={k: str(v) for k, v in placeholders.items()},
    )

# כמה סבבי שתיקה רצופים לפני שמפסיקים להאזין. בלי תקרה, שיחה
# נטושה מחזיקה את הצינור עד שהמרכזייה תסגור.
MAX_SILENT_RUNS = 5

# כמה שניות בלי מסגרת אודיו נחשבות לניתוק. הזרם עובר TCP ולעיתים
# דרך proxy, ולכן ערך נמוך מדי יפרש ג׳יטר כניתוק.
HANGUP_SILENCE = 2.0

# כל כמה מסגרות למדוד את עוצמת הקלט.
LEVEL_EVERY = 5


class IvrSatellite(AssistSatelliteEntity):
    """קו אחד. השיחה הפעילה נקשרת אליו, והצינור רץ דרכו."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:phone-classic"

    def __init__(self, entry, index: int = 0) -> None:
        self._entry = entry
        self._index = index
        self._session = None

        # מזהה הקו הראשון אינו נושא אינדקס. שינוי שלו יוצר ישות
        # חדשה ומשאיר את הקיימת יתומה במרשם, כלא זמינה.
        self._attr_unique_id = (
            f"{entry.entry_id}_satellite"
            if index == 0
            else f"{entry.entry_id}_satellite_{index + 1}"
        )
        self._attr_name = "עוזר קולי" if index == 0 else f"עוזר קולי {index + 1}"

        # מצב השיחה. הישות חיה לאורך כל חיי הרשומה, ולכן כל אלה
        # מאופסים גם ב-`attach`.
        self._audio: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._rate = PROVIDER_RATE
        self._run_task: asyncio.Task | None = None
        self._hangup_task: asyncio.Task | None = None
        self._last_chunk: float | None = None
        self._silent_runs = 0
        self._heard_this_run = False
        self._tts_pending = False
        self._failed_this_run = False
        self._leaving = False
        # מדידת עוצמת הקלט, לאבחון בלבד.
        self._level_sum = 0.0
        self._level_peak = 0
        self._level_count = 0
        # מושתק עד שהצליל הראשון נשלח: אודיו שמגיע בזמן הקראה
        # הוא הד, וה-VAD מזהה אותו כדיבור.
        self._muted = True
        self._out = asyncio.Lock()

    # ------------------------------------------------------------------
    # הגדרות. נקראות בזמן שימוש ולא ב-__init__, כדי שאפשר יהיה
    # לשנות אותן בטופס בלי טעינה מחדש.

    @property
    def _options(self) -> dict:
        return dict(self._entry.options)

    @property
    def device_info(self):
        from homeassistant.helpers.device_registry import DeviceInfo  # noqa: PLC0415

        return DeviceInfo(identifiers={(self._entry.domain, self._entry.entry_id)})

    @property
    def tts_options(self) -> dict | None:
        """פורמט ההקראה שמבקשים מהצינור.

        חייב להיות `property` ולא `_attr_`: ערך שמתעדכן בקשירה
        משאיר חלון שבו הישות נשאלת לפני שהשיחה נקשרה — וזה בדיוק
        המצב ב-ANNOUNCE. תשובה שגויה שם מחזירה mp3, `strip_wav`
        אינו מוצא PCM, והמתקשר שומע צליל תקלה.

        הקצב נלקח מהספק ולא נקבע ל-16k: בקו של 8k כל תשובה הייתה
        עוברת `resample` על לולאת האירועים.
        """
        return {
            tts.ATTR_PREFERRED_FORMAT: "wav",
            tts.ATTR_PREFERRED_SAMPLE_RATE: (
                self._rate if self._session is not None else PIPELINE_RATE
            ),
            tts.ATTR_PREFERRED_SAMPLE_CHANNELS: 1,
            tts.ATTR_PREFERRED_SAMPLE_BYTES: 2,
        }

    def _select_entity_id(self, suffix: str) -> str | None:
        """ישות בורר של הרשומה, לפי המזהה הייחודי שלה.

        זוג בוררים לרשומה ולא לקו: שני הקווים מחזירים את אותו
        מזהה, כי בחירת הצינור אינה תלויה בקו שהמתקשר נחת עליו.
        """
        from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

        return er.async_get(self.hass).async_get_entity_id(
            "select", self._entry.domain, f"{self._entry.entry_id}-{suffix}"
        )

    @property
    def pipeline_entity_id(self) -> str | None:
        return self._select_entity_id("pipeline")

    @property
    def vad_sensitivity_entity_id(self) -> str | None:
        return self._select_entity_id("vad_sensitivity")

    # ------------------------------------------------------------------
    # מה ש-AssistSatelliteEntity מחייבת

    @callback
    def async_get_configuration(self) -> AssistSatelliteConfiguration:
        """אין מילות הפעלה ואין רמקולים להגדיר — הטלפון הוא המכשיר."""
        return AssistSatelliteConfiguration(
            available_wake_words=[], active_wake_words=[], max_active_wake_words=0
        )

    async def async_set_configuration(self, config) -> None:
        """אין מה להגדיר. המתקשר מחייג, וזו כל ההפעלה."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # קשירת השיחה

    @property
    def busy(self) -> bool:
        return self._session is not None

    def attach(self, session, rate: int | None = None) -> bool:
        """תפיסת הקו. False אם הוא כבר תפוס.

        אין `await` בין הבדיקה להשמה, ולולאת האירועים היא חוט אחד,
        ולכן שתי שיחות בו-זמניות אינן יכולות לתפוס את אותו קו —
        מנעול אינו נדרש.

        הקצב מגיע מהשיחה, כי הוא נקרא ממסגרת הפתיחה של הספק.
        """
        if self._session is not None:
            return False

        self._session = session
        self._audio = asyncio.Queue()
        self._silent_runs = 0
        self._muted = True
        self._leaving = False
        self._run_task = None
        self._last_chunk = time.monotonic()

        # מזהה שיחה חדש לכל מתקשר. הישות חיה מעבר לשיחה אחת,
        # ובלי האיפוס המתקשר הבא יורש את הקשר השיחה של הקודם.
        self._conversation_id = None
        if rate:
            self._rate = rate

        self._hangup_task = self._entry.async_create_background_task(
            self.hass, self._check_hangup(), f"{self.entity_id}_hangup"
        )
        return True

    def set_rate(self, rate: int) -> None:
        """עדכון הקצב אחרי שמסגרת הפתיחה של הספק הגיעה."""
        self._rate = rate

    def detach(self, session) -> None:
        """שחרור הקו, רק אם זו אותה שיחה.

        בלי בדיקת הזהות, שיחה שנדחתה ומנקה אחריה משחררת את הקו
        מתחת לשיחה שכן רצה בו.

        המצב מוחזר ל"ממתין" גם כאן ולא רק בסוף השמעה, כי שיחה
        שנקטעה באמצע תשובה אינה מגיעה ל-`tts_response_finished`.
        """
        if self._session is not session:
            return

        self._session = None
        self._muted = True
        self._audio.put_nowait(None)

        for task in (self._run_task, self._hangup_task):
            if task is not None:
                task.cancel()
        self._run_task = None
        self._hangup_task = None

        with contextlib.suppress(Exception):
            self.tts_response_finished()

    # ------------------------------------------------------------------
    # אודיו נכנס

    def on_chunk(self, audio: bytes) -> None:
        """מסגרת אודיו מהקו.

        השעון מתעדכן לפני בדיקת ההשתקה: מסגרת שהגיעה בזמן הקראה
        היא הד ואינה נכנסת לתור, אבל היא מוכיחה שהקו חי.
        """
        self._last_chunk = time.monotonic()
        if self._muted or self._session is None:
            return

        if self._run_task is None:
            self._run_task = self._entry.async_create_background_task(
                self.hass, self._run_turn(), f"{self.entity_id}_turn"
            )
        self._note_level(audio)
        self._audio.put_nowait(audio)

    def _note_level(self, audio: bytes) -> None:
        """מדידת עוצמת המסגרת, לאבחון בלבד.

        משמשת לאבחון VAD שמפספס תחילת דיבור: רמה סבירה עם מעט
        מסגרות מצביעה על השתקה שבלעה את הדיבור, ורמה אפסית לאורך
        התור מצביעה על עוצמת הקלט. אינה משנה התנהגות.
        """
        self._level_count += 1
        if self._level_count % LEVEL_EVERY:
            return
        samples = array("h")
        samples.frombytes(audio[: len(audio) - (len(audio) % 2)])
        if not samples:
            return
        peak = max(abs(s) for s in samples)
        self._level_sum += sum(s * s for s in samples) / len(samples)
        self._level_peak = max(self._level_peak, peak)

    def _report_level(self) -> None:
        """סיכום הרמה לתור שהסתיים, ואיפוס לתור הבא."""
        measured = self._level_count // LEVEL_EVERY
        if measured:
            rms = int((self._level_sum / measured) ** 0.5)
            _LOGGER.debug(
                "Stream: input level for the turn - RMS %s, peak %s, %s frames (%.0f%% of full scale)",
            rms, self._level_peak, self._level_count,
                100 * self._level_peak / 32767,
            )
        self._level_sum = 0.0
        self._level_peak = 0
        self._level_count = 0

    async def _stt_stream(self):
        """האודיו מהקו, מומר לקצב שהצינור מצפה לו."""
        while True:
            chunk = await self._audio.get()
            if chunk is None:
                return
            yield resample(chunk, self._rate, PIPELINE_RATE)

    async def _check_hangup(self) -> None:
        """ניתוק לפי היעדר אודיו.

        המרכזייה אינה תמיד סוגרת את הסוקט כשהמתקשר מנתק, וה-
        `heartbeat` של aiohttp מגלה זאת רק אחרי 25 שניות. עצירת
        זרם המסגרות היא הסימן המהיר.

        רץ רק במצב האזנה. אין ודאות שהספקים ממשיכים לשלוח מסגרות
        בזמן הקראה, ושעון שירוץ אז עלול לנתק באמצע תשובה ארוכה.
        המחיר: ניתוק בזמן הקראה מתגלה רק בסופה.
        """
        try:
            while True:
                await asyncio.sleep(HANGUP_SILENCE / 2)
                if self._muted or self._last_chunk is None:
                    continue
                if (time.monotonic() - self._last_chunk) <= HANGUP_SILENCE:
                    continue
                _LOGGER.info(
                    "Stream: no audio for %s seconds, assuming the caller hung up",
                    HANGUP_SILENCE,
                )
                session = self._session
                if session is not None:
                    await session.hung_up()
                return
        except asyncio.CancelledError:
            # אין לבלוע ביטול.
            if (task := asyncio.current_task()) and task.cancelling():
                raise
            _LOGGER.debug("Stream: hangup watchdog cancelled")

    # ------------------------------------------------------------------
    # תור אחד

    async def _run_turn(self) -> None:
        """תור דיבור אחד: הצינור רץ, ואז נסגר החשבון.

        התור מתחיל ממסגרת אודיו ולא מלולאה שמסתובבת. בזמן הקראה
        ההשתקה דוחה את המסגרות, ולכן אף תור אינו נפתח אז ואין
        צורך באירוע המתנה.
        """
        try:
            self._begin_turn()
            try:
                await self.async_accept_pipeline_from_satellite(self._stt_stream())
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                # אין להמשיך מכאן: בלי הישות המתקשר נשאר על קו
                # פתוח ואילם.
                _LOGGER.exception("Stream: running the pipeline failed")
                session = self._session
                if session is not None:
                    await session.close("הצינור נכשל")
                return
            await self._end_turn()
        finally:
            # מתאפס אחרי `_end_turn` שפותח את השער. מסגרת שנוחתת
            # בחלון שביניהם נכנסת לתור בלי לפתוח תור שני, וזה
            # הכיוון הבטוח: תור שני מבטל את הראשון.
            self._run_task = None

    def _begin_turn(self) -> None:
        """איפוס דגלי התור."""
        self._report_level()
        self._heard_this_run = False
        self._tts_pending = False
        self._failed_this_run = False

    async def _end_turn(self) -> None:
        """סגירת תור."""
        session = self._session
        if session is None or session.exiting:
            # השיחה בדרך החוצה. פתיחת השער כאן תתחיל תור נוסף
            # אחרי שפקודת ההעברה כבר נשלחה.
            return

        self._report_level()

        # תור שנגמר בלי שזוהה טקסט הוא תור שקט — בין אם דרך
        # שגיאת stt ובין אם דרך run-end שקט.
        if not self._heard_this_run:
            self._silent_runs += 1

        # בלי הקראה בדרך, איש אינו פותח את הקלט בהמשך — למשל
        # כשעיבוד הכוונה נכשל אחרי שהדיבור זוהה.
        if not self._tts_pending:
            # שתיקה פשוטה נפתחת בלי צליל, אחרת שיחה שקטה
            # מצפצפת בלופ. כשל אמיתי כן מקבל חיווי.
            if self._failed_this_run:
                await self._resume(failed=True)
            else:
                self._drain()
                self._muted = False

        if self._silent_runs >= MAX_SILENT_RUNS:
            # שתיקה ממושכת אינה ניתוק: הקו חי ומסגרות ממשיכות
            # להגיע, ולכן `_check_hangup` אינו מטפל בזה.
            await session.close("שתיקה ממושכת")

    # ------------------------------------------------------------------
    # אירועי הצינור

    def on_pipeline_event(self, event) -> None:
        """טיפול באירוע מהצינור."""
        from homeassistant.components.assist_pipeline import (  # noqa: PLC0415
            PipelineEventType,
        )

        _LOGGER.debug("Stream: event %s %s", event.type, event.data)

        if self._session is None:
            # קורה בסגירה, כשהצינור פולט אירוע אחרון אחרי הניתוק.
            return

        if self._leaving:
            # הביטול ב-`request_leave` תופס רק בנקודת ה-await
            # הבאה, ולכן אירועים שכבר בדרך מגיעים לכאן. `TTS_END`
            # היה שולח לקו הקראה שאיש לא ישמע.
            _LOGGER.debug("Stream: event %s while leaving, dropped", event.type)
            return

        if event.type is PipelineEventType.ERROR:
            code = (event.data or {}).get("code", "")
            if code == "stt-no-text-recognized":
                # שתיקה בקו. מצב רגיל בהמתנה לדיבור, ולא שגיאה.
                self._silent_runs += 1
                return
            _LOGGER.warning("Stream: the pipeline returned an error: %s", event.data)
            self._failed_this_run = True
            if code == "intent-failed":
                # תור שנכשל משאיר את היסטוריית השיחה במצב שבור,
                # וכל תור אחריו נכשל באותה שגיאה. אין ממשק מוצהר
                # לאיפוס, ולכן השדה של מחלקת הבסיס מאופס ישירות.
                _LOGGER.warning("Stream: resetting the conversation after a failure")
                self._conversation_id = None
        elif event.type is PipelineEventType.STT_VAD_END:
            self._muted = True
            # הצליל כאן ולא ב-STT_END: בין השניים יש עוד המרה,
            # ובלעדיו המתקשר שומע שנייה של שקט.
            self.hass.async_create_task(self._send_tone(thinking_tone))
        elif event.type is PipelineEventType.STT_END:
            self._silent_runs = 0
            self._heard_this_run = True
            text = ((event.data or {}).get("stt_output") or {}).get("text", "")
            if self._is_exit(str(text)):
                # בלי להעביר למודל: הוא אינו מזהה בקשת יציאה,
                # ותשובה שתיזרק עולה קריאה בתשלום ושניות המתנה.
                _LOGGER.info("Stream: leaving to the menu: %s", text)
                # הדגל נקבע כאן ולא ב-`request_leave`: בין השניים
                # יש קפיצת לולאה שבה הצינור ממשיך לרוץ.
                self._leaving = True
                self.hass.async_create_task(self.request_leave())
        elif event.type is PipelineEventType.TTS_END and event.data:
            self._tts_pending = True
            self.hass.async_create_task(self._speak(event.data))

    async def begin(self) -> None:
        """פתיחת הקלט לתור הראשון, אחרי מסגרת הפתיחה של הספק.

        התור עצמו נפתח במסגרת האודיו הראשונה שנכנסת אחרי פתיחת
        השער, ולא כאן.
        """
        await self._resume()

    async def request_leave(self) -> None:
        """יציאה לתפריט — מהקשה בערוץ או מביטוי בדיבור.

        הצליל לפני הפקודה ולא אחריה: פקודה סופית בטכנוליין מנקזת
        עד 6 שניות אודיו לפני הביצוע, ולכן הוא יישמע.
        """
        session = self._session
        if session is None or session.exiting:
            return

        self._leaving = True
        # עצירת הצינור לפני הצליל: מבטלת את הקריאה למודל ואת
        # ההקראה שאחריה.
        with contextlib.suppress(Exception):
            await self._cancel_running_pipeline()

        await self._send_tone(thinking_tone)
        await session.leave()

    # ------------------------------------------------------------------
    # אודיו יוצא

    async def _speak(self, tts_data: dict) -> None:
        """שליחת ההקראה חזרה לקו.

        כל מסלול יציאה כאן חייב לקרוא ל-`_resume`: השער נסגר לפני
        הדיבור, ובלי פתיחה השיחה נשארת אילמת. `tests/check_gate.py`
        אוכף את זה.
        """
        token = ((tts_data or {}).get("tts_output") or {}).get("token")
        if not token:
            await self._resume()
            return

        pcm, rate = await self._fetch_tts(str(token))
        if not pcm:
            await self._resume(failed=True)
            return

        await self._send_audio(resample(pcm, rate, self._rate))
        # מחזיר את הישות ל"ממתין". `RUN_END` עושה זאת רק כשלא
        # הייתה הקראה בתור; תור עם הקראה נשאר ב-RESPONDING.
        self.tts_response_finished()
        await self._resume()

    async def _fetch_tts(self, token: str) -> tuple[bytes, int]:
        """ה-PCM של ההקראה, לפי הטוקן שהצינור החזיר.

        דרך `tts.async_get_stream` ולא בבקשת HTTP של HA אל עצמה:
        `parse_media_source_id` אינו מזהה את צורת ה-`-stream-`
        שהצינור מייצר. הטוקן הוא גם הדבר היחיד ש-ANNOUNCE נותן.
        """
        stream = tts.async_get_stream(self.hass, token)
        if stream is None:
            _LOGGER.error("Stream: the speech stream is not available (%s)", token[:12])
            return b"", self._rate

        if stream.extension != "wav":
            # סטטוס תקין אך פורמט שגוי. בלי הבדיקה `strip_wav`
            # מחזיר ריק, וזה נראה כמו שתיקה מכוונת.
            _LOGGER.error(
                "Stream: the speech came back as %s instead of wav. "
                "`tts_options` did not reach the TTS engine",
                stream.extension,
            )
            return b"", self._rate

        try:
            wav = b"".join([chunk async for chunk in stream.async_stream_result()])
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Stream: could not read the speech audio")
            return b"", self._rate

        pcm, rate = strip_wav(wav)
        if not pcm:
            _LOGGER.warning("Stream: the speech came back with no usable PCM")
            return pcm, rate

        self._report_tts_format(wav, pcm, rate)
        return pcm, rate

    def _report_tts_format(self, wav: bytes, pcm: bytes, rate: int) -> None:
        """מה שמנוע ההקראה החזיר בפועל, מול מה שהתבקש.

        `ATTR_PREFERRED_*` הן העדפות ולא דרישות, ומנוע רשאי
        להתעלם מהן. מה שנתפס כאן הוא אודיו שעובר את בדיקת הסיומת
        ובכל זאת אינו בפורמט המבוקש.

        מספר הערוצים הוא הקריטי: `strip_wav` מחזיר את גוף ה-PCM
        כמו שהוא ו-`resample` מתייחס אליו כמונו, ולכן אודיו
        סטריאו יתנגן במהירות כפולה בלי שום שגיאה.
        """
        got_rate, channels, bits = wav_format(wav)
        want = self.tts_options or {}
        seconds = len(pcm) / 2 / max(rate, 1)

        _LOGGER.debug(
            "Stream: the speech came back as wav - %s Hz, %s channels, %s bits, %s bytes (%.1f seconds)",
            got_rate, channels, bits, len(pcm), seconds,
        )

        if channels and channels != 1:
            _LOGGER.error(
                "Stream: the speech came back with %s channels instead of mono. The audio will play at the wrong speed - change the TTS engine or the pipeline",
            channels,
            )
        if bits and bits != 16:
            _LOGGER.error(
                "Stream: the speech came back at %s bits per sample instead of 16", bits
            )
        asked = want.get(tts.ATTR_PREFERRED_SAMPLE_RATE)
        if asked and got_rate and got_rate != asked:
            # לא שגיאה — `resample` מטפל בזה — אבל כל תשובה
            # משלמת המרה.
            _LOGGER.info(
                "Stream: asked for %s Hz and got %s. The TTS engine ignores "
                "the preference, so every answer is resampled",
                asked, got_rate,
            )

    async def _send_tone(self, builder) -> None:
        """שליחת צליל חיווי לקו, ובהמתנה עד שיתנגן."""
        if not bool(self._options.get("stream_tones", True)):
            return
        await self._send_audio(builder(self._rate))

    async def _send_audio(self, pcm: bytes) -> None:
        """שליחת אודיו והמתנה למשך הניגון שלו.

        הספק מקבל את כל הבלוק בבת אחת ומנגן אותו לאורך זמן, וההד
        חוזר תוך כדי. בלי ההמתנה, התור הבא צורך את ההד כאילו היה
        דיבור של המתקשר.

        משך ההמתנה מוערך לפי אורך ה-PCM: אין ספק שמדווח על סיום
        ניגון.
        """
        session = self._session
        if not pcm or session is None:
            return

        async with self._out:
            await session.send_audio(pcm)
            tail = float(self._options.get("stream_echo_tail", DEFAULT_ECHO_TAIL))
            await asyncio.sleep(len(pcm) / 2 / self._rate + tail)
            # ניקוי בתוך החלון החסום, כדי שההד לא ימתין בתור.
            self._drain()

    async def _resume(self, failed: bool = False) -> None:
        """סוף התור: צליל, ורק אז פתיחת הקלט."""
        session = self._session
        if session is None or session.exiting:
            return

        await self._send_tone(error_tone if failed else listen_tone)
        self._drain()
        self._tts_pending = False
        self._muted = False

    def _drain(self) -> None:
        """זריקת אודיו שהצטבר בתור בזמן ההקראה."""
        dropped = 0
        while not self._audio.empty():
            try:
                if self._audio.get_nowait() is None:
                    self._audio.put_nowait(None)
                    break
                dropped += 1
            except asyncio.QueueEmpty:
                break
        if dropped:
            _LOGGER.debug("Stream: dropped %s echo frames", dropped)

    # ------------------------------------------------------------------

    def _is_exit(self, text: str) -> bool:
        """האם המתקשר ביקש לחזור לתפריט.

        ההשוואה על טקסט מנורמל, כי זיהוי דיבור מוסיף פיסוק.

        הביטוי חייב להסתיים בגבול מילה: הכלה חופשית מזהה "ביי"
        בתוך "ביישוב" ו"בייבי". גבול בתחילת הביטוי אינו נדרש
        בכוונה — בעברית אותיות השימוש נדבקות למילה, ו"לתפריט
        ראשי" חייב להיתפס למרות הל׳ שלפניו.
        """

        def norm(value: str) -> str:
            clean = "".join(c for c in value if c.isalnum() or c.isspace())
            return " ".join(clean.split())

        raw = str(self._options.get("stream_exit", DEFAULT_EXIT_PHRASES) or "")
        clean = norm(text)
        for phrase in [p.strip() for p in raw.split(",") if p.strip()]:
            target = norm(phrase)
            if not target:
                continue
            start = 0
            while (found := clean.find(target, start)) != -1:
                end = found + len(target)
                if end == len(clean) or clean[end] == " ":
                    return True
                start = found + 1
        return False

    # ------------------------------------------------------------------
    # התראה קולית

    async def async_announce_message(
        self, message: str, phones: list[str]
    ) -> None:
        """התראה עם נמענים מפורשים.

        נקודת הכניסה היחידה להתראה: ישות `notify` מגיעה לכאן עם
        נמען אחד, ו-`send_call` עם רשימה.
        """
        announcement = await self._resolve_announcement_media_id(message, None)
        if announcement.tts_token is None:
            raise _error("speech_no_token")
        await self._announce(announcement.tts_token, message, phones=phones)

    async def _announce(
        self, token: str, message: str, *, phones: list[str]
    ) -> None:
        """המסלול המשותף: הקראה, שיגור, והמתנה להשמעה.

        הספק אינו משמיע דבר. הוא מחייג ומחבר את הנמען לשלוחת
        הסטרימינג, והאודיו נשלח מכאן.
        """
        driver = self._driver()
        announce = getattr(driver, "async_announce", None)
        if announce is None:
            raise _error(
                "provider_no_alerts",
                provider=str(getattr(driver, "DRIVER_ID", "?")),
            )

        phones = list(phones)
        if not phones:
            raise _error("no_valid_numbers")

        pcm, rate = await self._fetch_tts(token)
        if not pcm:
            raise _error("speech_not_wav")

        _LOGGER.info(
            "Alert: %s seconds of audio at %s Hz, %s recipients, via %s",
            round(len(pcm) / 2 / rate, 1), rate, len(phones), driver.DRIVER_ID,
        )

        # השמירה לפני השיגור: החיוג עשוי להיענות תוך שניות,
        # ושמירה אחריו פותחת חלון שבו השיחה חוזרת ואין מה להשמיע.
        pending = announce_store.store(
            self.hass, self._entry.entry_id, pcm, rate, message, phones,
        )
        campaign = ""
        try:
            # ההמרה כאן ולא אצל הקוראים: שני המסלולים עוברים
            # דרך כאן, ותפיסה באחד בלבד משאירה את השני עם שגיאה
            # גולמית על המסך.
            try:
                campaign = await announce(self.hass, self._entry, phones=phones) or ""
            except OutboundError as err:
                raise HomeAssistantError(
                    translation_domain=ERROR_DOMAIN,
                    translation_key=err.key or "outbound_failed",
                    translation_placeholders=err.placeholders
                    or {"error": str(err)},
                ) from err
            # ההמתנה היא מה שמאפשר לשירות לדווח אם ההודעה
            # הושמעה בפועל או שאיש לא ענה.
            try:
                async with asyncio.timeout(announce_store.DEFAULT_TTL):
                    await pending.delivered.wait()
            except TimeoutError:
                # הסיבה נלקחת מדוח הספק. אם אינו זמין נשארת
                # ההודעה הגנרית, בלי כשל נוסף על גבי כשל.
                why = ""
                outcome = getattr(driver, "async_call_outcome", None)
                if campaign and outcome is not None:
                    with contextlib.suppress(Exception):
                        why = await outcome(self.hass, self._entry, campaign)
                if pending.played:
                    raise _error(
                        "alert_partly_delivered",
                        summary=pending.summary, detail=why,
                    ) from None
                raise _error("alert_not_delivered", detail=why) from None
            if pending.error:
                raise _error("alert_failed", detail=pending.error)
        finally:
            announce_store.drop(self.hass, self._entry.entry_id, pending)

    async def play_announcement(self, pending) -> None:
        """השמעת התראה בשיחה שחזרה, במקום להריץ את הצינור.

        אין האזנה: ההשתקה נשארת דלוקה לכל אורך ההשמעה, ולכן
        `on_chunk` אינו פותח תור ו-`_check_hangup` אינו רץ.
        """
        self._muted = True
        try:
            await self._send_audio(
                resample(pending.pcm, pending.rate, self._rate)
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Alert: playback failed")
            pending.error = str(err) or type(err).__name__
        finally:
            pending.mark_played()

    def _driver(self):
        """הדרייבר של הרשומה הזו, מהמרשם.

        הליבה אינה מייבאת חבילת ספק — יש בדיקה שמוודאת את זה.
        """
        driver = registry.for_entry(self._entry)
        if driver is None:
            raise _error(
                "no_driver", provider=str(self._entry.data.get("provider", ""))
            )
        return driver
