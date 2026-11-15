// לוח המקשים: עורך התפריט הטלפוני בסרגל הצד.
//
// העמוד מצייר לוח מקשים של טלפון. כל מקש הוא מה שהמתקשר מקבל כשהוא
// מקיש עליו. כל ההחלטות נשארות בשרת (editor.py); כאן רק מציירים את
// הרמה שחזרה ושולחים את מה שהמשתמש ביקש.

const WS_TYPE = "ha_ivr/editor";
const STORE_KEY = "ha_ivr_entry";
const PICKER_LIMIT = 80;

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const KIND_ICONS = {
  submenu: "mdi:folder-outline",
  goto: "mdi:phone-forward",
  assistant: "mdi:account-voice",
  alerts: "mdi:bell-outline",
  option: "mdi:circle-small",
};

const CAP_ICONS = {
  simple: "mdi:gesture-tap",
  status: "mdi:volume-high",
  choice: "mdi:format-list-bulleted",
  number: "mdi:numeric",
};

const DOMAIN_ICONS = {
  light: "mdi:lightbulb",
  switch: "mdi:toggle-switch-outline",
  input_boolean: "mdi:toggle-switch-outline",
  climate: "mdi:air-conditioner",
  cover: "mdi:window-shutter",
  fan: "mdi:fan",
  media_player: "mdi:speaker",
  lock: "mdi:lock-outline",
  scene: "mdi:palette-outline",
  script: "mdi:script-text-outline",
  sensor: "mdi:eye-outline",
  binary_sensor: "mdi:eye-outline",
  vacuum: "mdi:robot-vacuum",
  water_heater: "mdi:water-boiler",
  button: "mdi:gesture-tap-button",
  automation: "mdi:robot-outline",
};

// הסדר שבו סוגי המכשירים מופיעים בבורר: מה שמפעילים קודם.
const DOMAIN_ORDER = [
  "light", "switch", "climate", "cover", "fan", "water_heater", "media_player",
  "vacuum", "scene", "script", "button", "input_boolean", "humidifier", "valve",
];

// סוגים שאין להם מה לחפש בבורר המכשירים.
const PICKER_SKIP = new Set([
  "zone", "tts", "stt", "conversation", "wake_word", "update", "event", "image",
  "notify", "ai_task", "assist_satellite", "device_tracker", "ha_ivr",
]);

const iconOf = (key) => {
  if (key.kind === "cap") return CAP_ICONS[key.cap] || CAP_ICONS.simple;
  if (KIND_ICONS[key.kind]) return KIND_ICONS[key.kind];
  return DOMAIN_ICONS[key.domain] || "mdi:devices";
};

const STYLE = `
:host {
  display: block;
  height: 100vh;
  height: 100dvh;
  color: var(--primary-text-color);
  background: var(--primary-background-color);
  font-family: var(--ha-font-family-body, Roboto, "Noto Sans Hebrew", sans-serif);
  -webkit-font-smoothing: antialiased;
}
* { box-sizing: border-box; }
.page { display: flex; flex-direction: column; height: 100%; direction: rtl; }
header {
  display: flex; align-items: center; gap: 8px;
  min-height: var(--header-height, 56px); padding: 0 12px;
  background: var(--app-header-background-color, var(--primary-color));
  color: var(--app-header-text-color, #fff);
  border-bottom: 1px solid var(--divider-color);
}
header h1 { font-size: 20px; font-weight: 400; margin: 0 4px; white-space: nowrap; }
header .grow { flex: 1; }
.iconbtn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; border: 0; border-radius: 50%;
  background: none; color: inherit; cursor: pointer;
}
.iconbtn:hover { background: rgba(127, 127, 127, 0.18); }
.tabs { display: flex; gap: 4px; overflow-x: auto; }
.tab {
  border: 0; background: none; color: inherit; font: inherit; cursor: pointer;
  padding: 8px 14px; border-radius: 18px; white-space: nowrap; opacity: 0.75;
}
.tab.on { background: rgba(127, 127, 127, 0.25); opacity: 1; font-weight: 500; }
.bar { height: 3px; background: transparent; }
.busy .bar {
  background: linear-gradient(90deg, transparent, var(--primary-color), transparent);
  background-size: 50% 100%; background-repeat: no-repeat;
  animation: slide 1s linear infinite;
}
@keyframes slide { from { background-position: 150% 0; } to { background-position: -50% 0; } }
main {
  flex: 1; overflow: auto; padding: 16px;
  display: grid; gap: 16px; align-items: start; justify-content: center;
  grid-template-columns: minmax(300px, 420px) minmax(300px, 440px);
}
.card {
  background: var(--card-background-color);
  border-radius: var(--ha-card-border-radius, 12px);
  border: 1px solid var(--divider-color);
  padding: 16px;
}
.crumbs { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; margin-bottom: 12px; min-height: 32px; }
.crumb {
  border: 0; background: none; font: inherit; color: var(--primary-color);
  cursor: pointer; padding: 4px 6px; border-radius: 6px;
}
.crumb:hover { background: var(--secondary-background-color); }
.crumb.here { color: var(--primary-text-color); font-weight: 500; cursor: default; }
.crumb.here:hover { background: none; }
.sep { color: var(--secondary-text-color); }
.pad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; direction: ltr; }
.key {
  position: relative; direction: rtl; min-height: 104px; padding: 10px 8px 8px;
  border-radius: 16px; border: 1.5px solid var(--divider-color);
  background: var(--secondary-background-color); color: inherit; font: inherit;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; cursor: pointer; text-align: center; overflow: hidden;
  transition: transform 0.08s, border-color 0.15s, box-shadow 0.15s;
}
.key:hover:not(:disabled) { border-color: var(--primary-color); }
.key:active:not(:disabled) { transform: scale(0.97); }
.key .digit {
  position: absolute; top: 6px; left: 10px; direction: ltr;
  font-size: 20px; font-weight: 500; color: var(--secondary-text-color);
}
.key ha-icon { --mdc-icon-size: 24px; color: var(--primary-color); }
.key .name {
  font-size: 14px; font-weight: 500; line-height: 1.2; max-width: 100%;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.key .detail { font-size: 12px; color: var(--secondary-text-color); max-width: 100%;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.key .more { position: absolute; top: 6px; right: 6px; --mdc-icon-size: 18px; color: var(--secondary-text-color); }
.key.empty { background: none; border-style: dashed; color: var(--secondary-text-color); }
.key.empty ha-icon { color: var(--secondary-text-color); --mdc-icon-size: 22px; }
.key.empty .name { font-weight: 400; font-size: 13px; }
.key:disabled { cursor: default; opacity: 0.45; }
.key.off { cursor: default; opacity: 0.45; }
.key.off:hover { border-color: var(--divider-color); }
.key.silent { opacity: 0.6; }
.key.missing { border-color: var(--warning-color, #ffa600); }
.key.missing ha-icon { color: var(--warning-color, #ffa600); }
.key.sel { border-color: var(--primary-color); box-shadow: 0 0 0 2px var(--primary-color) inset; }
.key.carried { border-style: dashed; border-color: var(--primary-color); opacity: 0.55; }
.key.over { border-color: var(--primary-color); background: var(--card-background-color); }
.key.flash { animation: flash 1.2s ease-out; }
@keyframes flash { from { box-shadow: 0 0 0 6px var(--primary-color); } to { box-shadow: 0 0 0 0 transparent; } }
.key.nav { min-height: 56px; }
.key.nav .digit { position: static; font-size: 22px; }
.key.nav .detail { font-size: 11px; }
.banner {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding: 8px 12px;
  border-radius: 10px; background: var(--primary-color); color: var(--text-primary-color, #fff);
  font-size: 14px;
}
.banner .grow { flex: 1; }
.banner button { border: 0; background: rgba(255, 255, 255, 0.22); color: inherit; font: inherit;
  padding: 4px 10px; border-radius: 8px; cursor: pointer; }
.loose { margin-top: 14px; border-top: 1px solid var(--divider-color); padding-top: 10px; }
.loose h3 { font-size: 13px; font-weight: 500; color: var(--secondary-text-color); margin: 0 0 6px; }
.row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.row .grow { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
h2 { font-size: 18px; font-weight: 500; margin: 0 0 12px; display: flex; align-items: center; gap: 8px; }
h2 .badge {
  display: inline-flex; align-items: center; justify-content: center; direction: ltr;
  min-width: 30px; height: 30px; padding: 0 6px; border-radius: 9px;
  background: var(--primary-color); color: var(--text-primary-color, #fff); font-size: 17px;
}
h3 { font-size: 14px; font-weight: 500; margin: 16px 0 6px; color: var(--secondary-text-color); }
p { margin: 0 0 10px; line-height: 1.5; }
.muted { color: var(--secondary-text-color); font-size: 13px; }
.warn {
  display: flex; gap: 8px; align-items: flex-start; padding: 10px 12px; margin-bottom: 12px;
  border-radius: 10px; font-size: 14px; line-height: 1.4;
  background: color-mix(in srgb, var(--warning-color, #ffa600) 16%, transparent);
}
.warn ha-icon { color: var(--warning-color, #ffa600); flex: none; }
.heard {
  margin: 0 0 12px; padding: 12px 14px; list-style: none; border-radius: 14px;
  border-start-start-radius: 4px; background: var(--secondary-background-color);
  font-size: 15px; line-height: 1.7;
}
.choices { display: flex; flex-direction: column; gap: 8px; }
.choice {
  display: flex; align-items: center; gap: 12px; width: 100%; text-align: start;
  padding: 10px 12px; border-radius: 12px; border: 1px solid var(--divider-color);
  background: none; color: inherit; font: inherit; cursor: pointer;
}
.choice:hover { border-color: var(--primary-color); background: var(--secondary-background-color); }
.choice ha-icon { color: var(--primary-color); flex: none; }
.choice b { display: block; font-weight: 500; }
.choice small { display: block; color: var(--secondary-text-color); font-size: 12.5px; margin-top: 1px; }
.choice .grow { flex: 1; min-width: 0; }
label.field { display: block; margin-bottom: 12px; font-size: 13px; color: var(--secondary-text-color); }
input[type="text"] {
  display: block; width: 100%; margin-top: 4px; padding: 10px 12px; font: inherit; font-size: 15px;
  color: var(--primary-text-color); background: var(--secondary-background-color);
  border: 1px solid var(--divider-color); border-radius: 10px; outline: none;
}
input[type="text"]:focus { border-color: var(--primary-color); }
.inline { display: flex; gap: 8px; align-items: flex-end; margin-bottom: 12px; }
.inline label.field { flex: 1; margin-bottom: 0; }
.check { display: flex; align-items: center; gap: 10px; padding: 7px 4px; cursor: pointer; border-radius: 8px; }
.check:hover { background: var(--secondary-background-color); }
.check input { width: 18px; height: 18px; accent-color: var(--primary-color); flex: none; }
.check small { color: var(--secondary-text-color); margin-inline-start: 4px; }
.btn {
  border: 0; border-radius: 10px; padding: 10px 16px; font: inherit; font-weight: 500;
  cursor: pointer; background: var(--primary-color); color: var(--text-primary-color, #fff);
  white-space: nowrap;
}
.btn.flat { background: none; color: var(--primary-color); padding: 8px 10px; }
.btn.flat:hover { background: var(--secondary-background-color); }
.btn.danger { background: none; color: var(--error-color, #db4437); padding: 8px 10px; }
.btn.danger.sure { background: var(--error-color, #db4437); color: #fff; }
.btn.small { padding: 5px 10px; font-size: 13px; }
.actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; align-items: center; }
.actions .grow { flex: 1; }
.list { max-height: 46vh; overflow: auto; margin: 0 -6px; padding: 0 6px; }
.list h4 { margin: 10px 0 2px; font-size: 12.5px; font-weight: 500; color: var(--secondary-text-color);
  position: sticky; top: 0; background: var(--card-background-color); padding: 3px 0; }
.pick {
  display: flex; align-items: center; gap: 10px; width: 100%; text-align: start;
  padding: 8px 6px; border: 0; border-radius: 8px; background: none; color: inherit;
  font: inherit; cursor: pointer;
}
.pick:hover { background: var(--secondary-background-color); }
.pick ha-icon { color: var(--secondary-text-color); --mdc-icon-size: 20px; flex: none; }
.back { margin: -6px -6px 6px; }
.empty-state { text-align: center; padding: 48px 16px; grid-column: 1 / -1; }
.empty-state ha-icon { --mdc-icon-size: 56px; color: var(--secondary-text-color); }
.toast {
  position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
  max-width: calc(100% - 32px); padding: 12px 18px; border-radius: 10px; z-index: 10;
  background: var(--primary-text-color); color: var(--primary-background-color);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3); font-size: 14px;
}
@media (max-width: 760px) {
  main { grid-template-columns: minmax(0, 480px); padding: 10px; gap: 10px; }
  .key { min-height: 92px; }
}
`;

class HaIvrPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entries = null;
    this._blocked = new Set();
    this._entryId = "";
    this._level = null;
    this._mode = { name: "heard" };
    this._carry = null;
    this._busy = 0;
    this._toast = "";
    this._flash = "";
    this._sure = "";
    this._failed = "";
    const root = this.shadowRoot;
    root.addEventListener("click", (ev) => this._onClick(ev));
    root.addEventListener("submit", (ev) => this._onSubmit(ev));
    root.addEventListener("input", (ev) => this._onInput(ev));
    root.addEventListener("dragstart", (ev) => this._onDragStart(ev));
    root.addEventListener("dragover", (ev) => this._onDragOver(ev));
    root.addEventListener("dragleave", (ev) => this._dropTarget(ev)?.classList.remove("over"));
    root.addEventListener("drop", (ev) => this._onDrop(ev));
    root.addEventListener("dragend", () => {
      this._drag = "";
    });
  }

  // Home Assistant מעדכן את hass בכל שינוי מצב בבית. העמוד אינו מצויר
  // מחדש בגללו: הוא נשען על מה שהשרת החזיר, ורק בורר המכשירים קורא ממנו.
  set hass(hass) {
    this._hass = hass;
    if (!this._started) {
      this._started = true;
      this._start();
    }
  }

  set narrow(narrow) {
    if (narrow !== this._narrow) {
      this._narrow = narrow;
      this._render();
    }
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    this._render();
  }

  // ------------------------------------------------------------------
  // השרת
  // ------------------------------------------------------------------

  async _call(op, message = {}) {
    this._busy += 1;
    this._setBusy();
    try {
      return await this._hass.callWS({
        type: WS_TYPE, op, entry_id: this._entryId, ...message,
      });
    } catch (err) {
      this._say((err && err.message) || "הפעולה נכשלה");
      return null;
    } finally {
      this._busy -= 1;
      this._setBusy();
    }
  }

  _setBusy() {
    this.shadowRoot.querySelector(".page")?.classList.toggle("busy", this._busy > 0);
  }

  async _start() {
    const found = await this._call("entries");
    if (!found) {
      this._failed = "הלוח לא הצליח להיטען. רעננו את העמוד.";
      this._render();
      return;
    }
    this._entries = found.entries;
    this._blocked = new Set(found.blocked);
    let wanted = "";
    try {
      wanted = localStorage.getItem(STORE_KEY) || "";
    } catch (_err) {
      wanted = "";
    }
    const entry = this._entries.find((e) => e.entry_id === wanted) || this._entries[0];
    if (!entry) {
      this._render();
      return;
    }
    await this._pickEntry(entry.entry_id);
  }

  async _pickEntry(entryId) {
    this._entryId = entryId;
    try {
      localStorage.setItem(STORE_KEY, entryId);
    } catch (_err) {
      // בלי אחסון מקומי פשוט לא זוכרים את הבחירה.
    }
    this._carry = null;
    await this._open("");
  }

  get _flags() {
    return (this._entries || []).find((e) => e.entry_id === this._entryId) || {};
  }

  async _open(path) {
    const level = await this._call("level", { path });
    if (!level) return;
    if (this._carry && this._carry.only !== undefined && this._carry.only !== level.path) {
      this._carry = null;
    }
    this._level = level;
    this._mode = { name: "heard" };
    this._sure = "";
    this._render();
  }

  // פעולה שמשנה. השרת מחזיר את הרמה המעודכנת, ומציירים אותה.
  async _change(op, message, { view, flash = "" } = {}) {
    const level = await this._call(op, {
      ...message, view: view === undefined ? this._level.path : view,
    });
    if (!level) return false;
    this._level = level;
    this._mode = { name: "heard" };
    this._carry = null;
    this._sure = "";
    this._flash = flash;
    this._render();
    return true;
  }

  _say(text) {
    this._toast = text;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this._toast = "";
      this._renderToast();
    }, 4500);
    this._renderToast();
  }

  _renderToast() {
    const box = this.shadowRoot.querySelector(".toast-box");
    if (box) box.innerHTML = this._toast ? `<div class="toast">${esc(this._toast)}</div>` : "";
  }

  _path(digit) {
    return this._level.path ? `${this._level.path}/${digit}` : digit;
  }

  _go(url) {
    history.pushState(null, "", url);
    window.dispatchEvent(new CustomEvent("location-changed", { bubbles: true, composed: true }));
  }

  // ------------------------------------------------------------------
  // הציור
  // ------------------------------------------------------------------

  _render() {
    const root = this.shadowRoot;
    root.innerHTML = `
      <style>${STYLE}</style>
      <div class="page ${this._busy > 0 ? "busy" : ""}">
        ${this._headerHtml()}
        <div class="bar"></div>
        <main>${this._mainHtml()}</main>
        <div class="toast-box"></div>
      </div>`;
    this._renderToast();
    this._flash = "";
    root.querySelector("[data-focus]")?.focus();
  }

  _headerHtml() {
    const entries = this._entries || [];
    const tabs = entries.length > 1
      ? `<div class="tabs">${entries.map((e) => `
          <button class="tab ${e.entry_id === this._entryId ? "on" : ""}"
            data-act="entry" data-id="${esc(e.entry_id)}">${esc(e.title)}</button>`).join("")}</div>`
      : "";
    return `
      <header>
        ${this._narrow ? `<button class="iconbtn" data-act="menu" title="תפריט">
          <ha-icon icon="mdi:menu"></ha-icon></button>` : ""}
        <h1>תפריט טלפוני</h1>
        ${tabs}
        <span class="grow"></span>
        <button class="iconbtn" data-act="settings" title="הגדרות הקו ואנשי קשר">
          <ha-icon icon="mdi:cog-outline"></ha-icon></button>
      </header>`;
  }

  _mainHtml() {
    if (this._failed) {
      return `<div class="empty-state"><ha-icon icon="mdi:alert-circle-outline"></ha-icon>
        <p>${esc(this._failed)}</p></div>`;
    }
    if (this._entries && !this._entries.length) {
      return `<div class="empty-state"><ha-icon icon="mdi:phone-plus-outline"></ha-icon>
        <p>עדיין לא הוגדר קו טלפון.</p>
        <button class="btn" data-act="settings">להוספת קו</button></div>`;
    }
    if (!this._level) return "";
    return `
      <section class="card phone">${this._phoneHtml()}</section>
      <aside class="card side">${this._sideHtml()}</aside>`;
  }

  _phoneHtml() {
    const level = this._level;
    const depth = level.path ? level.path.split("/").length : 0;
    const last = level.crumbs.length - 1;
    const crumbs = level.crumbs.map((c, i) => `
      ${i ? '<span class="sep">‹</span>' : ""}
      <button class="crumb ${i === last ? "here" : ""}" data-act="open"
        data-path="${esc(c.path)}">${esc(c.name)}</button>`).join("");
    const carry = this._carry
      ? `<div class="banner"><ha-icon icon="mdi:cursor-move"></ha-icon>
          <span class="grow">מעבירים את «${esc(this._carry.name)}». בחרו מקש.</span>
          <button data-act="carry-cancel">ביטול</button></div>`
      : "";
    const loose = level.loose.length
      ? `<div class="loose"><h3>פריטים בלי מקש — המתקשר אינו מגיע אליהם</h3>
          ${level.loose.map((item) => `
            <div class="row"><span class="grow">${esc(item.title)}</span>
              <button class="btn flat small" data-act="loose-place" data-id="${esc(item.id)}"
                data-name="${esc(item.title)}">שיבוץ במקש</button>
              <button class="btn danger small" data-act="loose-remove"
                data-id="${esc(item.id)}">מחיקה</button></div>`).join("")}</div>`
      : "";
    return `
      <div class="crumbs">${crumbs}</div>
      ${carry}
      <div class="pad">
        ${"123456789".split("").map((d) => this._keyHtml(d)).join("")}
        <button class="key nav" data-act="open" data-path="" ${depth > 1 ? "" : "disabled"}>
          <span class="digit">✱</span><span class="detail">${depth > 1 ? "לתפריט הראשי" : ""}</span></button>
        <button class="key nav" data-act="up" ${depth ? "" : "disabled"}>
          <span class="digit">0</span><span class="detail">${depth ? "חזרה" : ""}</span></button>
        <button class="key nav" disabled><span class="digit">#</span><span class="detail"></span></button>
      </div>
      ${loose}`;
  }

  _canAdd() {
    const level = this._level;
    if (level.kind === "menu") return level.can_add;
    return Boolean(level.addable && level.addable.length);
  }

  _keyHtml(digit) {
    const key = this._level.keys[digit];
    const mode = this._mode;
    const chosen = (mode.name === "add" || mode.name === "info") && mode.digit === digit;
    if (!key) {
      const open = Boolean(this._carry) || this._canAdd();
      return `
        <button class="key empty ${chosen ? "sel" : ""} ${open ? "" : "off"}" data-act="empty"
          data-digit="${digit}" data-drop="${digit}">
          <span class="digit">${digit}</span>
          <ha-icon icon="${this._carry ? "mdi:arrow-down-bold-outline" : "mdi:plus"}"></ha-icon>
          <span class="name">${this._carry ? "לכאן" : "הוספה"}</span>
        </button>`;
    }
    const classes = [
      "key",
      chosen ? "sel" : "",
      key.silent ? "silent" : "",
      key.missing ? "missing" : "",
      this._carry && this._carry.path === key.path ? "carried" : "",
      this._flash === digit ? "flash" : "",
    ].join(" ");
    return `
      <button class="${classes}" data-act="key" data-digit="${digit}" data-drop="${digit}"
        draggable="true" title="${esc(key.name)}">
        <span class="digit">${digit}</span>
        ${key.enter ? '<ha-icon class="more" icon="mdi:chevron-left"></ha-icon>' : ""}
        <ha-icon icon="${key.missing ? "mdi:alert-outline" : iconOf(key)}"></ha-icon>
        <span class="name">${esc(key.name)}</span>
        <span class="detail">${esc(key.detail)}</span>
      </button>`;
  }

  // ------------------------------------------------------------------
  // הצד: מה שומעים, הוספה, פרטי מקש
  // ------------------------------------------------------------------

  _sideHtml() {
    const mode = this._mode;
    if (mode.name === "add") return this._addHtml();
    if (mode.name === "info") return this._infoHtml();
    if (mode.name === "build") return this._buildHtml();
    return this._heardHtml();
  }

  _removeButton(act, attrs, label, sure) {
    const key = `${act}:${attrs}`;
    const on = this._sure === key;
    return `<button class="btn danger ${on ? "sure" : ""}" data-act="${act}" ${attrs}
      data-sure="${esc(key)}">${on ? esc(sure) : esc(label)}</button>`;
  }

  _heardHtml() {
    const level = this._level;
    const self = level.self;
    const root = !level.path;
    const filled = Object.values(level.keys).some(Boolean);
    let top = "";
    if (level.heard.length) {
      top = `<ul class="heard">${level.heard.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`;
    } else if (root && !filled) {
      top = `<p>התפריט עדיין ריק. לחצו על מקש בלוח כדי לקבוע מה יקרה כשמתקשר מקיש עליו.</p>
        <p><button class="btn" data-act="build">לבנות תפריט מהחדרים בבית</button></p>`;
    } else if (!filled) {
      top = `<div class="warn"><ha-icon icon="mdi:alert-outline"></ha-icon>
        <span>אין כאן עדיין מקשים, ולכן המתקשר אינו שומע על התפריט הזה. לחצו על מקש כדי להוסיף.</span></div>`;
    } else {
      top = `<div class="warn"><ha-icon icon="mdi:alert-outline"></ha-icon>
        <span>המתקשר אינו מגיע לכאן כרגע.</span></div>`;
    }

    const intro = level.intro === null ? "" : `
      <form class="inline" data-form="intro">
        <label class="field">משפט פתיחה (לא חובה)
          <input type="text" name="intro" value="${esc(level.intro)}"
            placeholder="${root ? "שלום, הגעתם לבית" : ""}"></label>
        <button class="btn flat">שמירה</button>
      </form>`;

    let own = "";
    if (self) {
      const menu = self.kind === "submenu";
      const label = self.kind === "cap" ? "שם הפעולה" : menu ? "שם התפריט" : "שם בטלפון";
      own = `
        <h3>מקש ${esc(self.digit)}</h3>
        <form class="inline" data-form="rename" data-path="${esc(level.path)}">
          <label class="field">${label}
            <input type="text" name="name" value="${esc(self.label)}"
              placeholder="${esc(self.name)}"></label>
          <button class="btn flat">שמירה</button>
        </form>
        ${self.missing ? `<div class="warn"><ha-icon icon="mdi:alert-outline"></ha-icon>
          <span>${self.kind === "group" ? "אין כרגע מכשירים בקבוצה הזו." : "המכשיר הזה אינו קיים עוד."}</span></div>` : ""}
        <div class="actions">
          <button class="btn flat" data-act="carry" data-path="${esc(level.path)}"
            data-name="${esc(self.name)}" data-up="1">
            העברה למקש אחר</button>
          <span class="grow"></span>
          ${this._removeButton("remove", `data-path="${esc(level.path)}"`, "הסרה",
            menu ? "למחוק עם כל מה שבתוכו?" : "להסיר?")}
        </div>`;
    }

    const build = root && filled && level.can_add
      ? `<div class="actions"><button class="btn flat" data-act="build">
          הוספת חדרים שלמים למקשים הפנויים</button></div>`
      : "";

    return `
      <h2>המתקשר שומע</h2>
      ${top}
      ${intro}
      ${own}
      ${build}
      <p class="muted" style="margin-top:14px">לחיצה על מקש מלא פותחת אותו. לחיצה על מקש ריק מוסיפה. אפשר גם לגרור מקש למקום אחר.</p>`;
  }

  _backButton(act, label = "חזרה") {
    return `<div class="back"><button class="btn flat small" data-act="${act}">
      <ha-icon icon="mdi:arrow-right" style="--mdc-icon-size:16px"></ha-icon> ${label}</button></div>`;
  }

  _describe(key) {
    if (key.kind === "action") return `פעולה אחת במכשיר «${key.detail}».`;
    if (key.kind === "goto") return `מעביר את השיחה לשלוחה ${key.target}.`;
    if (key.kind === "assistant") return "מחבר את המתקשר לעוזר הקולי של הבית.";
    if (key.kind === "alerts") return "מקריא את ההתראות האחרונות שנשלחו לטלפון.";
    if (key.kind === "option") return "אחת האפשרויות שהמתקשר בוחר מהן.";
    if (key.cap === "status") return "מקריא את המצב הנוכחי.";
    if (key.cap === "number") return `${key.detail}.`;
    return "פעולה בהקשה אחת.";
  }

  _infoHtml() {
    const key = this._level.keys[this._mode.digit];
    if (!key) return this._heardHtml();
    const flags = this._flags;
    const rename = key.kind === "option" ? "" : `
      <form class="inline" data-form="rename" data-path="${esc(key.path)}">
        <label class="field">${key.kind === "cap" ? "שם הפעולה" : "שם בטלפון"}
          <input type="text" name="name" value="${esc(key.label)}"
            placeholder="${esc(key.name)}" data-focus></label>
        <button class="btn flat">שמירה</button>
      </form>`;
    // יעד נערך רק היכן שהמשתמש הוא שקבע אותו: שלוחה שהוא בחר, או
    // שלוחת העוזר אצל ספק שאין לו יעד קבוע לעוזר.
    const editable = key.kind === "goto"
      ? flags.extensions
      : key.kind === "assistant" && !flags.assistant_target;
    const target = editable ? `
      <form class="inline" data-form="target" data-path="${esc(key.path)}">
        <label class="field">${key.kind === "assistant" ? "השלוחה שמחוברת לעוזר הקולי" : "לאן עוברים"}
          <input type="text" name="target" dir="ltr" value="${esc(key.target)}"></label>
        <button class="btn flat">שמירה</button>
      </form>
      ${flags.goto_hint ? `<p class="muted">${esc(flags.goto_hint)}</p>` : ""}` : "";
    const warn = key.missing
      ? `<div class="warn"><ha-icon icon="mdi:alert-outline"></ha-icon>
          <span>המכשיר הזה אינו קיים עוד ב-Home Assistant.</span></div>`
      : key.silent
        ? `<div class="warn"><ha-icon icon="mdi:alert-outline"></ha-icon>
            <span>המקש הזה אינו מוקרא למתקשר כרגע.</span></div>`
        : "";
    return `
      ${this._backButton("close")}
      <h2><span class="badge">${esc(key.digit)}</span>${esc(key.name)}</h2>
      <p class="muted">${esc(this._describe(key))}</p>
      ${warn}
      ${rename}
      ${target}
      <div class="actions">
        <button class="btn flat" data-act="carry" data-path="${esc(key.path)}"
          data-name="${esc(key.name)}">העברה למקש אחר</button>
        <span class="grow"></span>
        ${this._removeButton("remove", `data-path="${esc(key.path)}"`, "הסרה", "להסיר?")}
      </div>`;
  }

  _choice(act, icon, title, text, attrs = "") {
    return `
      <button class="choice" data-act="${act}" ${attrs}>
        <ha-icon icon="${icon}"></ha-icon>
        <span class="grow"><b>${esc(title)}</b>${text ? `<small>${esc(text)}</small>` : ""}</span>
      </button>`;
  }

  _addHtml() {
    const mode = this._mode;
    const level = this._level;
    const flags = this._flags;
    const badge = `<span class="badge">${esc(mode.digit)}</span>`;
    const back = this._backButton(mode.step === "what" ? "close" : "add-back");

    if (level.kind !== "menu") {
      const items = (level.addable || []).map((item) => this._choice(
        "add-part", level.kind === "plan" ? "mdi:plus-circle-outline" : "mdi:circle-small",
        item.label, "",
        `data-ident="${esc(item.ident ?? "")}" data-value="${esc(item.value ?? "")}"`,
      )).join("");
      return `${back}
        <h2>${badge}${level.kind === "plan" ? "איזו פעולה להוסיף?" : "איזו אפשרות להחזיר?"}</h2>
        <div class="choices">${items}</div>`;
    }

    if (mode.step === "device") {
      return `${back}
        <h2>${badge}איזה מכשיר?</h2>
        <input type="text" data-search data-focus placeholder="חיפוש לפי שם או חדר" value="${esc(mode.query || "")}">
        <div class="list" id="devices">${this._devicesHtml(mode.query || "")}</div>`;
    }

    if (mode.step === "caps") {
      const caps = mode.found.capabilities.map((c) => `
        <label class="check"><input type="checkbox" name="cap" value="${esc(c.ident)}"
          ${c.checked ? "checked" : ""}><span>${esc(c.label)}</span></label>`).join("");
      return `${back}
        <h2>${badge}${esc(mode.found.name)}</h2>
        <form data-form="device">
          <h3>מה המתקשר יוכל לעשות</h3>
          ${caps}
          <label class="field" style="margin-top:12px">שם בטלפון (לא חובה)
            <input type="text" name="name" placeholder="${esc(mode.found.name)}"></label>
          <div class="actions"><button class="btn">הוספה למקש ${esc(mode.digit)}</button></div>
        </form>`;
    }

    if (mode.step === "room") {
      const rooms = (mode.rooms || []).map((room, index) => this._choice(
        "add-room", room.area_id ? "mdi:door-open" : "mdi:home-outline", room.name,
        room.kinds.map((k) => k.name).join(" · "), `data-index="${index}"`,
      )).join("");
      return `${back}
        <h2>${badge}איזה חדר?</h2>
        <div class="choices list">${rooms || '<p class="muted">לא נמצאו חדרים עם מכשירים שאפשר להפעיל.</p>'}</div>`;
    }

    if (mode.step === "kinds") {
      const room = mode.room;
      const kinds = room.kinds.map((k) => `
        <label class="check"><input type="checkbox" name="kind" value="${esc(k.domain)}" checked>
          <span>${esc(k.name)}<small>(${Number(k.count)})</small></span></label>`).join("");
      return `${back}
        <h2>${badge}${esc(room.name)}</h2>
        <form data-form="room">
          <h3>מה לכלול</h3>
          ${kinds}
          ${level.can_nest ? "" : '<p class="muted">בעומק הזה אפשר לבחור סוג אחד בלבד.</p>'}
          <label class="field" style="margin-top:12px">שם בטלפון (לא חובה)
            <input type="text" name="name" placeholder="${esc(room.name)}"></label>
          <div class="actions"><button class="btn">הוספה למקש ${esc(mode.digit)}</button></div>
        </form>`;
    }

    if (mode.step === "submenu") {
      return `${back}
        <h2>${badge}תפריט חדש</h2>
        <form data-form="submenu">
          <label class="field">איך לקרוא לו
            <input type="text" name="name" placeholder="למשל: קומה עליונה" data-focus></label>
          <div class="actions"><button class="btn">הוספה</button></div>
        </form>`;
    }

    if (mode.step === "goto" || mode.step === "assistant") {
      const assistant = mode.step === "assistant";
      return `${back}
        <h2>${badge}${assistant ? "עוזר קולי" : "מעבר לשלוחה אחרת"}</h2>
        <form data-form="${mode.step}">
          <label class="field">${assistant ? "השלוחה שמחוברת לעוזר הקולי" : "לאן עוברים"}
            <input type="text" name="target" dir="ltr" data-focus></label>
          ${flags.goto_hint ? `<p class="muted">${esc(flags.goto_hint)}</p>` : ""}
          <label class="field">שם בטלפון${assistant ? " (לא חובה)" : ""}
            <input type="text" name="name" placeholder="${assistant ? "עוזר קולי" : "למשל: המשרד"}"></label>
          <div class="actions"><button class="btn">הוספה</button></div>
        </form>`;
    }

    const choices = [
      this._choice("add-step", "mdi:lightbulb-outline", "מכשיר",
        "אור, מזגן, תריס, סצנה — כל דבר שיש בבית", 'data-step="device"'),
      this._choice("add-step", "mdi:door-open", "חדר שלם",
        "כל האורות, התריסים והמזגנים של חדר, או של כל הבית", 'data-step="room"'),
    ];
    if (level.can_nest) {
      choices.push(this._choice("add-step", "mdi:folder-outline", "תפריט נוסף",
        "מקש שפותח עוד מקשים", 'data-step="submenu"'));
    }
    if (flags.assistant) {
      choices.push(this._choice("add-assistant", "mdi:account-voice", "עוזר קולי",
        "המתקשר מבקש בקול מה שהוא רוצה"));
    }
    if (flags.extensions) {
      choices.push(this._choice("add-step", "mdi:phone-forward", "מעבר לשלוחה אחרת",
        "העברת השיחה לשלוחה אחרת בקו", 'data-step="goto"'));
    }
    if (flags.alerts) {
      choices.push(this._choice("add-alerts", "mdi:bell-outline", "התראות אחרונות",
        "הקראת ההתראות האחרונות שהבית שלח"));
    }
    return `${back}
      <h2>${badge}מה יקרה כשמקישים ${esc(mode.digit)}?</h2>
      <div class="choices">${choices.join("")}</div>`;
  }

  _buildHtml() {
    const free = Object.values(this._level.keys).filter((k) => !k).length;
    const rooms = (this._mode.rooms || []).map((room, index) => `
      <label class="check"><input type="checkbox" name="room" value="${index}"
        ${room.area_id && index < free ? "checked" : ""}>
        <span>${esc(room.name)}<small>${esc(room.kinds.map((k) => k.name).join(" · "))}</small></span>
      </label>`).join("");
    return `${this._backButton("close")}
      <h2>תפריט מהחדרים בבית</h2>
      <p class="muted">כל חדר שתסמנו יקבל מקש, ובתוכו מה שאפשר להפעיל בו. יש ${free} מקשים פנויים.</p>
      <form data-form="build">
        <div class="list">${rooms || '<p class="muted">לא נמצאו חדרים עם מכשירים שאפשר להפעיל.</p>'}</div>
        <div class="actions"><button class="btn">בנייה</button></div>
      </form>`;
  }

  _devices(query) {
    const hass = this._hass;
    const text = query.trim().toLowerCase();
    const rows = [];
    for (const [id, state] of Object.entries(hass.states)) {
      const domain = id.split(".", 1)[0];
      if (this._blocked.has(domain) || PICKER_SKIP.has(domain)) continue;
      const known = hass.entities ? hass.entities[id] : null;
      if (known && (known.hidden || known.entity_category || known.platform === "ha_ivr")) continue;
      const rank = DOMAIN_ORDER.indexOf(domain);
      // בלי חיפוש מוצג רק מה שמפעילים. חיישנים ושאר הדברים — בחיפוש.
      if (!text && rank < 0) continue;
      const device = known && known.device_id && hass.devices ? hass.devices[known.device_id] : null;
      const areaId = (known && known.area_id) || (device && device.area_id) || "";
      const area = (areaId && hass.areas && hass.areas[areaId] && hass.areas[areaId].name) || "";
      const name = state.attributes.friendly_name || id;
      if (text && !`${name} ${id} ${area}`.toLowerCase().includes(text)) continue;
      rows.push({ id, name, domain, area, rank: rank < 0 ? 99 : rank });
    }
    rows.sort((a, b) =>
      (a.area ? 0 : 1) - (b.area ? 0 : 1)
      || a.area.localeCompare(b.area, "he")
      || a.rank - b.rank
      || a.name.localeCompare(b.name, "he"));
    return rows;
  }

  _devicesHtml(query) {
    const rows = this._devices(query);
    if (!rows.length) {
      return `<p class="muted" style="margin-top:12px">${query.trim()
        ? "לא נמצא מכשיר בשם הזה." : "לא נמצאו מכשירים."}</p>`;
    }
    let area = null;
    const out = [];
    for (const row of rows.slice(0, PICKER_LIMIT)) {
      if (row.area !== area) {
        area = row.area;
        out.push(`<h4>${esc(area || "בלי חדר")}</h4>`);
      }
      out.push(`
        <button class="pick" data-act="add-device" data-id="${esc(row.id)}" title="${esc(row.id)}">
          <ha-icon icon="${DOMAIN_ICONS[row.domain] || "mdi:devices"}"></ha-icon>
          <span>${esc(row.name)}</span></button>`);
    }
    const more = rows.length > PICKER_LIMIT
      ? `<p class="muted">ועוד ${rows.length - PICKER_LIMIT}. הקלידו שם כדי לצמצם.</p>`
      : query.trim() ? "" : '<p class="muted">מחפשים חיישן או משהו אחר? הקלידו את שמו.</p>';
    return out.join("") + more;
  }

  // ------------------------------------------------------------------
  // מה שהמשתמש עושה
  // ------------------------------------------------------------------

  _setMode(mode) {
    this._mode = mode;
    this._sure = "";
    this._render();
    if (this._narrow && mode.name !== "heard") {
      this.shadowRoot.querySelector(".side")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  _parent(path) {
    return path.split("/").slice(0, -1).join("/");
  }

  async _add(what, args = {}, { enter = false } = {}) {
    const digit = this._mode.digit;
    const path = this._path(digit);
    await this._change(
      "add", { path, args: { what, ...args } },
      { flash: digit, view: enter ? path : undefined },
    );
  }

  async _onClick(ev) {
    const el = ev.target.closest("[data-act]");
    if (!el || el.disabled || this._busy > 0) return;
    const data = el.dataset;
    const level = this._level;
    const mode = this._mode;

    // מחיקה בשתי לחיצות: הראשונה שואלת, השנייה מוחקת.
    if (data.sure && this._sure !== data.sure) {
      this._sure = data.sure;
      this._render();
      return;
    }

    switch (data.act) {
      case "menu":
        this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
        return;
      case "settings":
        this._go("/config/integrations/integration/ha_ivr");
        return;
      case "entry":
        if (data.id !== this._entryId) await this._pickEntry(data.id);
        return;
      case "open":
        if (data.path !== level.path || mode.name !== "heard") await this._open(data.path);
        return;
      case "up":
        await this._open(this._parent(level.path));
        return;
      case "key":
        await this._onKey(data.digit);
        return;
      case "empty":
        await this._onEmpty(data.digit);
        return;
      case "close":
        this._setMode({ name: "heard" });
        return;
      case "carry-cancel":
        this._carry = null;
        this._render();
        return;
      case "carry": {
        const key = data.up ? level.self : level.keys[mode.digit];
        const home = this._parent(data.path);
        this._carry = { path: data.path, name: data.name };
        // פעולה של מכשיר ואפשרות של בחירה זזות רק בתוך הרמה שלהן.
        if (key && (key.kind === "cap" || key.kind === "option")) this._carry.only = home;
        if (data.up) await this._open(home);
        else this._setMode({ name: "heard" });
        return;
      }
      case "remove":
        await this._change("remove", { path: data.path }, {
          view: data.path === level.path ? this._parent(level.path) : level.path,
        });
        return;
      case "loose-place":
        this._carry = { id: data.id, name: data.name };
        this._setMode({ name: "heard" });
        return;
      case "loose-remove":
        await this._change("remove", { args: { id: data.id } });
        return;
      case "build": {
        const found = await this._call("rooms");
        if (found) this._setMode({ name: "build", rooms: found.rooms });
        return;
      }
      case "add-back": {
        const before = { caps: "device", kinds: "room" }[mode.step] || "what";
        this._setMode({ ...mode, step: before });
        return;
      }
      case "add-step": {
        if (data.step === "room") {
          const found = await this._call("rooms");
          if (found) this._setMode({ ...mode, step: "room", rooms: found.rooms });
          return;
        }
        this._setMode({ ...mode, step: data.step });
        return;
      }
      case "add-assistant":
        if (this._flags.assistant_target) await this._add("assistant");
        else this._setMode({ ...mode, step: "assistant" });
        return;
      case "add-alerts":
        await this._add("alerts");
        return;
      case "add-device": {
        const found = await this._call("capabilities", { args: { entity_id: data.id } });
        if (found) this._setMode({ ...mode, step: "caps", found });
        return;
      }
      case "add-room":
        this._setMode({ ...mode, step: "kinds", room: mode.rooms[Number(data.index)] });
        return;
      case "add-part":
        if (level.kind === "plan") await this._add("capability", { ident: data.ident });
        else await this._add("option", { value: data.value });
        return;
      default:
    }
  }

  async _onKey(digit) {
    const key = this._level.keys[digit];
    const carry = this._carry;
    if (!carry) {
      if (key.enter) await this._open(key.path);
      else this._setMode({ name: "info", digit });
      return;
    }
    if (carry.path === key.path) {
      this._carry = null;
      this._render();
      return;
    }
    // תפריט פותחים, כדי שאפשר יהיה להניח בתוכו.
    if (key.kind === "submenu" && carry.only === undefined) {
      await this._open(key.path);
      return;
    }
    if (carry.path && this._parent(carry.path) === this._level.path) {
      await this._change("move", { path: carry.path, args: { to: key.path } }, { flash: digit });
      return;
    }
    this._say("המקש הזה תפוס. בחרו מקש ריק.");
  }

  async _onEmpty(digit) {
    const carry = this._carry;
    const to = this._path(digit);
    if (carry) {
      const message = carry.id
        ? { args: { to, id: carry.id } }
        : { path: carry.path, args: { to } };
      await this._change("move", message, { flash: digit });
      return;
    }
    if (!this._canAdd()) {
      this._say("אין עוד מה להוסיף כאן.");
      return;
    }
    this._setMode({ name: "add", digit, step: "what" });
  }

  async _onSubmit(ev) {
    ev.preventDefault();
    if (this._busy > 0) return;
    const form = ev.target;
    const data = new FormData(form);
    const text = (name) => String(data.get(name) || "").trim();
    const level = this._level;
    const mode = this._mode;

    switch (form.dataset.form) {
      case "intro":
        await this._change("update", { path: level.path, args: { intro: text("intro") } });
        return;
      case "rename":
        await this._change("rename", { path: form.dataset.path, args: { name: text("name") } });
        return;
      case "target":
        await this._change("update", { path: form.dataset.path, args: { target: text("target") } });
        return;
      case "device": {
        const idents = data.getAll("cap");
        if (!idents.length) {
          this._say("סמנו לפחות פעולה אחת.");
          return;
        }
        await this._add("device", { entity_id: mode.found.entity_id, idents, name: text("name") });
        return;
      }
      case "room": {
        const domains = data.getAll("kind");
        if (!domains.length) {
          this._say("סמנו לפחות סוג אחד.");
          return;
        }
        if (domains.length > 1 && !level.can_nest) {
          this._say("בעומק הזה אפשר לבחור סוג אחד בלבד.");
          return;
        }
        await this._add("room", { area_id: mode.room.area_id, domains, name: text("name") });
        return;
      }
      case "submenu":
        await this._add("submenu", { name: text("name") }, { enter: true });
        return;
      case "goto":
      case "assistant":
        await this._add(form.dataset.form, { target: text("target"), name: text("name") });
        return;
      case "build": {
        const areaIds = data.getAll("room").map((i) => mode.rooms[Number(i)].area_id);
        if (!areaIds.length) {
          this._say("סמנו לפחות חדר אחד.");
          return;
        }
        await this._change("build", { path: level.path, args: { area_ids: areaIds } });
        return;
      }
      default:
    }
  }

  _onInput(ev) {
    if (!ev.target.matches || !ev.target.matches("[data-search]")) return;
    this._mode.query = ev.target.value;
    const list = this.shadowRoot.getElementById("devices");
    if (list) list.innerHTML = this._devicesHtml(this._mode.query);
  }

  // ------------------------------------------------------------------
  // גרירה
  // ------------------------------------------------------------------

  _dropTarget(ev) {
    return ev.target.closest ? ev.target.closest("[data-drop]") : null;
  }

  _onDragStart(ev) {
    const el = ev.target.closest ? ev.target.closest(".key[draggable]") : null;
    const key = el ? this._level.keys[el.dataset.digit] : null;
    if (!key) return;
    this._drag = key.path;
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", key.path);
  }

  _onDragOver(ev) {
    const el = this._dropTarget(ev);
    if (!this._drag || !el || this._path(el.dataset.drop) === this._drag) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    el.classList.add("over");
  }

  async _onDrop(ev) {
    const el = this._dropTarget(ev);
    const from = this._drag;
    this._drag = "";
    if (!from || !el) return;
    ev.preventDefault();
    el.classList.remove("over");
    const to = this._path(el.dataset.drop);
    if (to !== from && this._busy === 0) {
      await this._change("move", { path: from, args: { to } }, { flash: el.dataset.drop });
    }
  }
}

if (!customElements.get("ha-ivr-panel")) {
  customElements.define("ha-ivr-panel", HaIvrPanel);
}
