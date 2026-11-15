"""לוח המקשים בסרגל הצד: הרישום, והפקודה שהוא שולח.

הלוח הוא עמוד אחד שמדבר עם `editor.py` בפקודת WebSocket אחת. כל
ההחלטות — מה מותר, מה תפוס, מה המתקשר ישמע — נשארות בצד השרת; העמוד
רק מצייר את מה שחזר.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from . import editor
from .const import BLOCKED_DOMAINS, CONFIRM_DOMAINS, DOMAIN

_LOGGER = logging.getLogger(__name__)

STATIC_URL = f"/{DOMAIN}_static"
PANEL_URL = "ha-ivr"
PANEL_ELEMENT = "ha-ivr-panel"
PANEL_TITLE = "תפריט טלפוני"
PANEL_TITLE_EN = "Phone menu"
PANEL_ICON = "mdi:dialpad"
WS_TYPE = f"{DOMAIN}/editor"


async def async_register(hass: HomeAssistant, stamp: str) -> None:
    """הוספת הלוח לסרגל הצד. נקרא פעם אחת, מ-`async_setup`."""
    # חותמת הבנייה בנתיב ולא בפרמטר: מודול שהלוח מייבא יחסית יורש את
    # הנתיב, וכך גם הוא נטען מחדש אחרי עדכון ולא מגיע מהמטמון.
    static = f"{STATIC_URL}/{re.sub(r'[^A-Za-z0-9._-]', '-', stamp)}"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(static, str(Path(__file__).parent / "frontend"), False)]
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_ELEMENT,
        # שם הלוח בסרגל נקבע פעם אחת, בשפת המערכת.
        sidebar_title=(
            PANEL_TITLE
            if str(getattr(getattr(hass, "config", None), "language", "he") or "he").startswith("he")
            else PANEL_TITLE_EN
        ),
        sidebar_icon=PANEL_ICON,
        module_url=f"{static}/panel.js",
        require_admin=True,
        config={"build": stamp},
    )
    websocket_api.async_register_command(hass, ws_editor)


def _entry(hass: HomeAssistant, entry_id: str):
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == entry_id:
            return entry
    raise editor.EditorError("no_entry", "הקו הזה אינו קיים עוד")


async def _level(hass: HomeAssistant, entry, path: str) -> dict:
    """הרמה המבוקשת, או הקרובה ביותר מעליה שעדיין קיימת."""
    parts = [p for p in str(path or "").split("/") if p]
    while True:
        try:
            return await editor.async_level(hass, entry, "/".join(parts))
        except editor.EditorError:
            if not parts:
                raise
            parts.pop()


async def async_run(hass: HomeAssistant, msg: dict) -> Any:
    """הרצת פעולה אחת של הלוח. פעולה שמשנה מחזירה את הרמה המעודכנת."""
    op = str(msg.get("op", ""))
    args = dict(msg.get("args") or {})
    path = str(msg.get("path", "") or "")

    if op == "entries":
        return {
            "entries": editor.entries(hass),
            "blocked": sorted(BLOCKED_DOMAINS | CONFIRM_DOMAINS),
        }

    entry = _entry(hass, str(msg.get("entry_id", "")))

    if op == "level":
        return await _level(hass, entry, path)
    if op == "capabilities":
        return await editor.async_capabilities(
            hass, str(args.get("entity_id", "")), entry
        )
    if op == "actions":
        return await editor.async_actions(hass, str(args.get("entity_id", "")))
    if op == "rooms":
        return {"rooms": await editor.async_rooms(hass)}
    if op == "places":
        return editor.async_places(hass)
    if op == "place":
        return await editor.async_place(hass, args)
    if op == "place_functions":
        return await editor.async_place_functions(hass, args)
    if op == "group":
        return editor.group_place(hass, entry, path)
    if op == "fixed":
        return await editor.async_fixed(hass, entry, path)

    undo = ""
    if op == "add":
        what = str(args.pop("what", ""))
        replace = bool(args.pop("replace", False))

        async def _add() -> None:
            # החלפה: ההסרה וההוספה נשמרות יחד, או שלא נשמר דבר.
            if replace:
                editor.remove(hass, entry, path)
            await editor.async_add(hass, entry, path, what, **args)

        await editor.async_atomic(hass, entry, _add)
    elif op == "undo":
        editor.undo(hass, entry, str(args.get("token", "")))
    elif op == "build":
        await editor.async_build(hass, entry, path, list(args.get("area_ids") or []))
    elif op == "rename":
        editor.rename(hass, entry, path, str(args.get("name", "")))
    elif op == "update":

        async def _update() -> None:
            # כל מה שנערך בדיאלוג אחד נשמר יחד. השם אחרון: שם ריק
            # מחזיר את ברירת המחדל, וזו תלויה בשאר השינויים.
            if "values" in args:
                await editor.async_set_values(hass, entry, path, args["values"])
            for key in ("intro", "target", "place"):
                if key in args:
                    editor.update(hass, entry, path, **{key: args[key]})
            if "name" in args:
                editor.rename(hass, entry, path, str(args.get("name") or ""))

        await editor.async_atomic(hass, entry, _update)
    elif op == "remove":
        before = editor._snapshot(entry)
        editor.remove(hass, entry, path, str(args.get("id", "")))
        undo = editor.remember_undo(entry, before)
    elif op == "move":
        to = str(args.get("to", "") or "")
        # "into": לתפריט אחר, על המקש הפנוי הראשון בו.
        if args.get("into"):
            to = editor.free_slot_in(hass, entry, to)
        editor.move(hass, entry, to, path, str(args.get("id", "")))
    else:
        raise editor.EditorError("unknown", "פעולה שאינה מוכרת")

    level = await _level(hass, entry, str(msg.get("view", "") or ""))
    return {**level, "undo": undo} if undo else level


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE,
        vol.Required("op"): str,
        vol.Optional("entry_id"): str,
        vol.Optional("path"): str,
        vol.Optional("view"): str,
        vol.Optional("args"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_editor(hass: HomeAssistant, connection, msg: dict) -> None:
    try:
        result = await async_run(hass, msg)
    except editor.EditorError as err:
        connection.send_error(msg["id"], err.code, err.message)
        return
    connection.send_result(msg["id"], result)
