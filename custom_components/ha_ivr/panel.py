"""לוח המקשים בסרגל הצד: הרישום, והפקודה שהוא שולח.

הלוח הוא עמוד אחד שמדבר עם `editor.py` בפקודת WebSocket אחת. כל
ההחלטות — מה מותר, מה תפוס, מה המתקשר ישמע — נשארות בצד השרת; העמוד
רק מצייר את מה שחזר.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
PANEL_ICON = "mdi:dialpad"
WS_TYPE = f"{DOMAIN}/editor"


async def async_register(hass: HomeAssistant, stamp: str) -> None:
    """הוספת הלוח לסרגל הצד. נקרא פעם אחת, מ-`async_setup`."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                STATIC_URL, str(Path(__file__).parent / "frontend"), False
            )
        ]
    )
    # חותמת הבנייה בכתובת: דפדפן שמחזיק גרסה קודמת של העמוד טוען
    # את החדשה מיד אחרי עדכון, בלי ניקוי מטמון.
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=f"{STATIC_URL}/panel.js?v={quote(stamp)}",
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
        return await editor.async_capabilities(hass, str(args.get("entity_id", "")))
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

    if op == "add":
        what = str(args.pop("what", ""))
        await editor.async_add(hass, entry, path, what, **args)
    elif op == "build":
        await editor.async_build(hass, entry, path, list(args.get("area_ids") or []))
    elif op == "rename":
        editor.rename(hass, entry, path, str(args.get("name", "")))
    elif op == "update":
        if "values" in args:
            await editor.async_set_values(hass, entry, path, args["values"])
        else:
            editor.update(
                hass, entry, path,
                **{k: args[k] for k in ("intro", "target", "place") if k in args},
            )
    elif op == "remove":
        editor.remove(hass, entry, path, str(args.get("id", "")))
    elif op == "move":
        editor.move(hass, entry, args.get("to", ""), path, str(args.get("id", "")))
    else:
        raise editor.EditorError("unknown", "פעולה שאינה מוכרת")

    return await _level(hass, entry, str(msg.get("view", "") or ""))


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
