"""בוררי הצינור ורגישות ה-VAD, כישויות.

ישויות ולא שדות בטופס, מפני ש-`async_accept_pipeline_from_satellite`
בונה בעצמה את הקריאה לצינור:

    pipeline_id=self._resolve_pipeline(),
    audio_settings=AudioSettings(silence_seconds=self._resolve_vad_sensitivity()),

ושתי הפונקציות קוראות מישויות `select` דרך `pipeline_entity_id`
ו-`vad_sensitivity_entity_id`. ערך שיושב בטופס אינו מגיע לצינור
כלל, ובלי שום שורה ביומן.

`AssistPipelineSelect` ו-`VadSensitivitySelect` מגיעות מ-HA עצמה
ומשחזרות את בחירתן בטעינה מחדש. אין כאן מימוש, רק חיבור למכשיר
של הרשומה.

זוג אחד לרשומה ולא לקו: שתי ישויות הלוויין מצביעות לאותו זוג,
כי הצינור הוא בחירה של מי שהגדיר ולא של הקו שהשיחה נחתה עליו.
"""

from __future__ import annotations

import logging

from homeassistant.components.assist_pipeline import (
    AssistPipelineSelect,
    VadSensitivitySelect,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

_LOGGER = logging.getLogger(__name__)


def _device(entry) -> DeviceInfo:
    return DeviceInfo(identifiers={(entry.domain, entry.entry_id)})


class IvrPipelineSelect(AssistPipelineSelect):
    """בורר הצינור של הרשומה."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry) -> None:
        AssistPipelineSelect.__init__(self, hass, entry.domain, entry.entry_id)
        self._attr_device_info = _device(entry)
        self._entry = entry

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if await self.async_get_last_state() is not None:
            return

        # הגירה מהטופס, פעם אחת. הבורר נולד על ברירת המחדל של
        # HA, ולכן רשומה שכבר בחרה צינור בטופס הייתה עוברת בשקט
        # למועדף ומשתנה שוב בכל פעם שהמועדף משתנה.
        #
        # ההגדרה שומרת מזהה והבורר מחזיק שמות, ולכן נדרש תרגום:
        # `_resolve_pipeline` משווה `pipeline.name` למצב.
        stored = str(self._entry.options.get("stream_pipeline", "") or "")
        if not stored:
            return

        from homeassistant.components.assist_pipeline import (  # noqa: PLC0415
            async_get_pipelines,
        )

        for pipeline in async_get_pipelines(self.hass):
            if pipeline.id == stored and pipeline.name in self.options:
                self._attr_current_option = pipeline.name
                self.async_write_ha_state()
                _LOGGER.info(
                    "Pipeline select migrated from the options: %s", pipeline.name
                )
                return

        _LOGGER.warning(
            "The pipeline in the options (%s) no longer exists. The select stays on the Home Assistant default",
            stored,
        )


class IvrVadSensitivitySelect(VadSensitivitySelect):
    """בורר רגישות ה-VAD של הרשומה.

    הרגישות קובעת כמה שקט נדרש כדי להחליט שהמתקשר סיים —
    תוקפני 0.25 שניות, רגיל 0.7, רגוע 1.25. על קו טלפון עם
    השהיה זה ההבדל בין תחושת שיחה לבין משפט שנקטע באמצע.
    """

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry) -> None:
        VadSensitivitySelect.__init__(self, hass, entry.entry_id)
        self._attr_device_info = _device(entry)
        self._entry = entry

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if await self.async_get_last_state() is not None:
            return

        stored = str(self._entry.options.get("stream_vad", "") or "")
        if stored and stored in self.options:
            self._attr_current_option = stored
            self.async_write_ha_state()
            _LOGGER.info("VAD select migrated from the options: %s", stored)


def selects(hass: HomeAssistant, entry) -> list:
    """שני הבוררים של רשומה אחת."""
    return [IvrPipelineSelect(hass, entry), IvrVadSensitivitySelect(hass, entry)]


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """זוג בוררים לרשומה. שני הקווים מצביעים לאותו זוג."""
    async_add_entities(selects(hass, entry))
