// לוח המקשים: עורך התפריט הטלפוני בסרגל הצד.
//
// העמוד מצייר לוח מקשים של טלפון. כל מקש הוא מה שהמתקשר מקבל כשהוא
// מקיש עליו. כל ההחלטות נשארות בשרת (editor.py); כאן מציירים את הרמה
// שחזרה ושולחים את מה שהמשתמש ביקש.
//
// המיקום בתפריט נמצא בכתובת: /ha-ivr/<קו>/<ספרות>. ה-route ש-Home
// Assistant מעביר הוא מקור האמת, וכל ניווט עובר דרך navigate של
// ha-panel-custom, כמו בשאר הממשק. "אחורה" בדפדפן עולה רמה.

import {
  DOMAIN_ICONS, MAIN_ATTR, PICKER_SKIP, auto, btn, cls, esc, h, icon, iconBtn, iconOf, joined, keyType, ltr, quoted,
} from "./dom.js";
import { STRINGS, counted, isRTL, langOf, translator } from "./strings.js";
import { adopt } from "./styles.js";
import { Dialog, Menu, confirmDialog } from "./dialog.js";
import { AddFlow, BuildFlow, KeyFlow } from "./flows.js";

const WS_TYPE = "ha_ivr/editor";
const STORE_KEY = "ha_ivr_entry";
const RECENT_KEY = "ha_ivr_recent";
const HELP_URL = "https://github.com/meni123/ha-ivr#readme";
const SETTINGS_URL = "/config/integrations/integration/ha_ivr";
// סדר המקשים בלוח, משמאל לימין ומלמעלה למטה.
const PAD = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];
// כמה תווים בשנייה מנוע דיבור אומר, בערך. רק להערכה.
const CHARS_PER_SECOND = 14;
const UNDO_MS = 6000;

// השדות שהבורר מחפש בהם והמשקל של כל אחד, כמו ב-entity_picker.ts של HA.
const ENTITY_KEYS = [["primary", 10], ["friendly", 8], ["deviceName", 7], ["area", 6], ["end", 6], ["id", 3]];
const DEVICE_KEYS = [["primary", 10], ["area", 6], ["end", 6]];
const AREA_KEYS = [["primary", 10], ["aliases", 8], ["secondary", 6]];
const LABEL_KEYS = [["primary", 10], ["secondary", 5]];
// מצבים שהאייקון שלהם נצבע כפעיל, כשאין state-badge.
const ACTIVE_STATES = new Set(["on", "open", "opening", "closing", "playing", "heat", "cool", "heat_cool", "auto", "dry", "fan_only", "cleaning", "unlocked", "home", "armed_home", "armed_away"]);

/** אותיות קטנות, בלי ניקוד וסימנים: "שָׁלוֹם" ו"שלום" נמצאים אותו דבר. */
const norm = (value) => String(value ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();

/**
 * עד כמה מילה מתאימה לשדה, בין 0 ל-1. מופע רצוף עדיף, ועוד יותר
 * בתחילת מילה; בלעדיו — התאמה עמומה (האותיות לפי הסדר, קרובות זו לזו),
 * כמו ה-threshold של Fuse. מילה של תו אחד מתאימה רק כמופע רצוף.
 */
const matchScore = (value, term) => {
  if (!value || !term) return 0;
  const at = value.indexOf(term);
  if (at >= 0) {
    let score = 0.7 - Math.min(at, 30) / 100;
    if (at === 0 || /[\s._\-]/.test(value[at - 1])) score += 0.2;
    if (value === term) score += 0.1;
    // שדה קצר שהמילה ממלאת את רובו גובר על משפט ארוך שהיא רק חלק ממנו.
    return score + 0.3 * (term.length / value.length);
  }
  if (term.length < 2) return 0;
  let pos = -1;
  let first = -1;
  for (const ch of term) {
    pos = value.indexOf(ch, pos + 1);
    if (pos < 0) return 0;
    if (first < 0) first = pos;
  }
  const density = term.length / (pos - first + 1);
  return density >= 0.6 ? 0.35 * density : 0;
};

const parentOf = (path) => String(path || "").split("/").filter(Boolean).slice(0, -1).join("/");

const store = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch (_err) {
      return null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (_err) {
      // בלי אחסון מקומי פשוט לא זוכרים.
    }
  },
};

class HaIvrPanel extends HTMLElement {
  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    this._entries = null;
    this._blocked = new Set();
    this._entryId = "";
    this._level = null;
    this._failed = false;
    this._busy = 0;
    this._cursor = "1";
    this._flash = "";
    this._flow = null;
    this._lost = null;
    this._live = new Map();
    this._liveDlg = new Map();
    this._renders = 0;
    this._seq = 0;
    this._drag = "";
    this._lang = "he";
    this.t = translator("he");

    const style = adopt(root);
    this._page = h("div", { class: "page" });
    this._bar = h("div", { class: "busy-bar", hidden: true, "aria-hidden": "true" });
    root.append(...[style, this._page, this._bar].filter(Boolean));

    this._dialog = new Dialog(root, {
      onCancel: (ev) => this._onDialogCancel(ev),
      onClose: () => this._onDialogClose(),
      onBackdrop: () => this._onBackdrop(),
      onEscape: () => this._askClose(),
      onPlace: () => this._render(),
    });
    this._menu = new Menu(root, (...args) => this.t(...args));

    root.addEventListener("click", (ev) => this._onClick(ev));
    root.addEventListener("submit", (ev) => this._onSubmit(ev));
    root.addEventListener("input", (ev) => this._onInput(ev));
    root.addEventListener("change", (ev) => this._onChange(ev));
    root.addEventListener("keydown", (ev) => this._onKeyDown(ev));
    root.addEventListener("dragstart", (ev) => this._onDragStart(ev));
    root.addEventListener("dragover", (ev) => this._onDragOver(ev));
    root.addEventListener("dragleave", (ev) => this._dropTarget(ev)?.classList.remove("over"));
    root.addEventListener("drop", (ev) => this._onDrop(ev));
    root.addEventListener("dragend", () => this._endDrag());
  }

  // ------------------------------------------------------------------
  // מה ש-Home Assistant מעביר
  // ------------------------------------------------------------------

  // hass מתעדכן בכל שינוי בבית. העמוד אינו מצויר מחדש בגללו: מתעדכנים
  // רק המכשירים שמוצגים כרגע, ורק אם אובייקט המצב שלהם השתנה.
  set hass(hass) {
    const before = this._hass;
    this._hass = hass;
    const lang = langOf(hass);
    const dir = isRTL(hass) ? "rtl" : "ltr";
    if (lang !== this._lang || dir !== this._dir) {
      this._lang = lang;
      this._dir = dir;
      this.t = translator(lang);
      this.setAttribute("dir", dir);
      this.setAttribute("lang", lang);
      if (this._started) this._render();
    }
    if (!this._started) {
      this._started = true;
      this._start();
      return;
    }
    if (before && hass && before.states !== hass.states) this._refresh(before.states || {});
  }

  get hass() {
    return this._hass;
  }

  set narrow(narrow) {
    if (Boolean(narrow) !== Boolean(this._narrow)) {
      this._narrow = Boolean(narrow);
      this._render();
    }
  }

  get narrow() {
    return Boolean(this._narrow);
  }

  set route(route) {
    this._route = route;
    if (this._entries) this._syncRoute();
  }

  get route() {
    return this._route;
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

  /** קריאה לשרת. שגיאה נזרקת הלאה, עם הקוד שלה. */
  async api(op, message = {}) {
    this._busy += 1;
    this._setBusy();
    try {
      return await this._hass.callWS({ type: WS_TYPE, op, entry_id: this._entryId, ...message });
    } finally {
      this._busy -= 1;
      this._setBusy();
    }
  }

  errorText(err) {
    const code = err && err.code;
    if (code && STRINGS.he[`err_${code}`]) return this.t(`err_${code}`);
    return (err && err.message) || this.t("err_failed");
  }

  _setBusy() {
    this._bar.hidden = this._busy <= 0;
  }

  async _start() {
    this._failed = false;
    this._render();
    let found;
    try {
      found = await this.api("entries");
    } catch (_err) {
      this._failed = true;
      this._render();
      return;
    }
    this._entries = found.entries || [];
    this._blocked = new Set(found.blocked || []);
    if (!this._entries.length) {
      this._render();
      return;
    }
    await this._syncRoute();
  }

  get flags() {
    return (this._entries || []).find((e) => e.entry_id === this._entryId) || {};
  }

  get level() {
    return this._level;
  }

  get flow() {
    return this._flow;
  }

  path(digit) {
    return this._level && this._level.path ? `${this._level.path}/${digit}` : digit;
  }

  // ------------------------------------------------------------------
  // כתובת וניווט
  // ------------------------------------------------------------------

  _prefix() {
    return (this._route && this._route.prefix) || "/ha-ivr";
  }

  _url(entryId, path) {
    return `${this._prefix()}/${entryId}${path ? `/${path}` : ""}`;
  }

  /** ניווט כמו בשאר הממשק: navigate של ha-panel-custom, ובלעדיו ידני. */
  _navigate(entryId, path, { replace = false } = {}) {
    const url = this._url(entryId, path);
    if (typeof location !== "undefined" && location.pathname === url) return;
    const host = this.parentElement;
    if (host && typeof host.navigate === "function") {
      host.navigate(url, { replace });
      return;
    }
    if (replace) history.replaceState(history.state, "", url);
    else history.pushState(null, "", url);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace } }));
  }

  /** מה שבכתובת קובע מה מוצג. כאן רק טוענים ומציירים, לא מנווטים קדימה. */
  async _syncRoute() {
    const parts = String((this._route && this._route.path) || "").split("/").filter(Boolean);
    let entryId = parts[0] || "";
    const path = parts.slice(1).join("/");
    if (!this._entries.some((e) => e.entry_id === entryId)) {
      const saved = store.get(STORE_KEY);
      entryId = (this._entries.find((e) => e.entry_id === saved) || this._entries[0]).entry_id;
      // כניסה מהסרגל, בלי קו בכתובת: משלימים במקום, בלי רשומה בהיסטוריה.
      this._navigate(entryId, "", { replace: true });
      await this._load(entryId, "");
      return;
    }
    if (entryId === this._entryId && this._level && this._level.path === path) return;
    // "אחורה" בדפדפן כשדיאלוג פתוח: הדיאלוג שייך לרמה שעזבנו.
    if (this._flow) this._closeDialog();
    await this._load(entryId, path);
  }

  async _load(entryId, path) {
    const seq = ++this._seq;
    this._entryId = entryId;
    store.set(STORE_KEY, entryId);
    let level;
    try {
      level = await this.api("level", { path });
    } catch (err) {
      if (seq !== this._seq) return;
      this._toast(this.errorText(err));
      if (path) {
        this._navigate(entryId, "", { replace: true });
        await this._load(entryId, "");
      }
      return;
    }
    if (seq !== this._seq) return;
    this._level = level;
    // רמה שנעלמה: השרת החזיר את הקרובה מעליה, והכתובת מתוקנת במקום.
    if (level.path !== path) this._navigate(entryId, level.path, { replace: true });
    this._render();
  }

  /** מעבר לרמה בקו הנוכחי. */
  async go(path) {
    this._navigate(this._entryId, path);
    await this._load(this._entryId, path);
  }

  /**
   * שינוי בשרת. השרת מחזיר את הרמה שמוצגת אחריו, והיא מצוירת. `enter`
   * נכנס לרמה שנוצרה (תת-תפריט חדש).
   */
  async mutate(op, message, { view, flash = "", enter = "" } = {}) {
    if (op !== "undo") this._dismissUndo();
    const want = enter || (view === undefined ? this._level.path : view);
    const level = await this.api(op, { ...message, view: want });
    this._level = level;
    this._flash = flash;
    if (level.path !== this._routePath()) {
      this._navigate(this._entryId, level.path, { replace: !enter });
    }
    this._render();
    return level;
  }

  _routePath() {
    return String((this._route && this._route.path) || "").split("/").filter(Boolean).slice(1).join("/");
  }

  // ------------------------------------------------------------------
  // הודעות
  // ------------------------------------------------------------------

  /** הודעה של Home Assistant (hass-notification), עם פעולה אם יש. */
  _toast(message, action = null) {
    const detail = { message, duration: action ? UNDO_MS : 4000, dismissable: true };
    if (action) detail.action = { text: action.text, action: action.run };
    this.dispatchEvent(new CustomEvent("hass-notification", { bubbles: true, composed: true, detail }));
  }

  _undoToast(message, token) {
    if (!token) {
      this._toast(message);
      return;
    }
    this._undoOpen = true;
    this._toast(message, { text: this.t("undo"), run: () => this._undo(token) });
  }

  // כתיבה אחרת סוגרת את הביטול: הוא כבר לא היה מצליח.
  _dismissUndo() {
    if (!this._undoOpen) return;
    this._undoOpen = false;
    this.dispatchEvent(new CustomEvent("hass-notification", {
      bubbles: true, composed: true, detail: { message: "", duration: 0 },
    }));
  }

  async _undo(token) {
    this._undoOpen = false;
    try {
      await this.mutate("undo", { args: { token } });
      this._toast(this.t("restored"));
    } catch (err) {
      this._toast(this.errorText(err));
    }
  }

  // ------------------------------------------------------------------
  // מצב המכשירים מתוך hass
  // ------------------------------------------------------------------

  stateObj(eid) {
    const states = this._hass && this._hass.states;
    return eid && states ? states[eid] : undefined;
  }

  stateText(eid) {
    const obj = this.stateObj(eid);
    if (!obj) return "";
    try {
      const text = typeof this._hass.formatEntityState === "function" ? this._hass.formatEntityState(obj) : obj.state;
      return typeof text === "string" && text ? text : String(obj.state ?? eid);
    } catch (_err) {
      return String(obj.state ?? eid);
    }
  }

  attrText(eid, attr) {
    const obj = this.stateObj(eid);
    if (!obj || !obj.attributes || obj.attributes[attr] === undefined || obj.attributes[attr] === null) return "";
    try {
      const text = typeof this._hass.formatEntityAttributeValue === "function"
        ? this._hass.formatEntityAttributeValue(obj, attr) : obj.attributes[attr];
      return text === undefined || text === null ? "" : String(text);
    } catch (_err) {
      return String(obj.attributes[attr]);
    }
  }

  entityName(eid) {
    const obj = this.stateObj(eid);
    if (!obj) return eid;
    const plain = (obj.attributes && obj.attributes.friendly_name) || eid;
    try {
      if (typeof this._hass.formatEntityName !== "function") return String(plain);
      const name = this._hass.formatEntityName(obj, [{ type: "device" }, { type: "entity" }]);
      return typeof name === "string" && name.trim() ? name : String(plain);
    } catch (_err) {
      return String(plain);
    }
  }

  _area(eid) {
    const hass = this._hass;
    const known = hass.entities ? hass.entities[eid] : null;
    const device = known && known.device_id && hass.devices ? hass.devices[known.device_id] : null;
    const areaId = (known && known.area_id) || (device && device.area_id) || "";
    return (areaId && hass.areas && hass.areas[areaId] && hass.areas[areaId].name) || "";
  }

  _pickable(id) {
    const hass = this._hass;
    const domain = id.split(".", 1)[0];
    if (this._blocked.has(domain) || PICKER_SKIP.has(domain)) return false;
    const known = hass.entities ? hass.entities[id] : null;
    return !(known && (known.hidden || known.entity_category || known.platform === "ha_ivr"));
  }

  /**
   * החלקים של שורה בבורר, כמו computeEntityPickerDisplay של HA: שם
   * הישות, ומתחתיו "אזור ▸ מכשיר" (ב-RTL החץ הפוך). המכשיר מופיע רק
   * כשלישות יש שם משלה; אחרת הוא כבר הכותרת.
   */
  _entityParts(id) {
    const hass = this._hass;
    const obj = this.stateObj(id);
    const known = hass.entities ? hass.entities[id] : null;
    const device = known && known.device_id && hass.devices ? hass.devices[known.device_id] : null;
    const deviceName = device ? String(device.name_by_user || device.name || "") : "";
    const friendly = String((obj && obj.attributes && obj.attributes.friendly_name) || "");
    let entityName = "";
    try {
      if (typeof hass.formatEntityName === "function" && obj) entityName = String(hass.formatEntityName(obj, [{ type: "entity" }]) || "");
    } catch (_err) {
      entityName = "";
    }
    if (!entityName) {
      entityName = deviceName && friendly.startsWith(deviceName) ? friendly.slice(deviceName.length).trim() : friendly;
    }
    if (entityName === deviceName) entityName = "";
    const domain = id.split(".", 1)[0];
    const area = this._area(id);
    const sep = this._dir === "rtl" ? " ◂ " : " ▸ ";
    return {
      type: "entity", id, domain, area, deviceName, entityName, friendly,
      primary: entityName || deviceName || friendly || id,
      secondary: [area, entityName ? deviceName : ""].filter(Boolean).join(sep),
      end: this._domainName(domain),
    };
  }

  _domainName(domain) {
    const hass = this._hass;
    let name = "";
    try {
      if (typeof hass.localize === "function") name = hass.localize(`component.${domain}.title`) || "";
    } catch (_err) {
      name = "";
    }
    return name || domain.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
  }

  /** טקסט רשמי של Home Assistant, ובלעדיו — שלנו. */
  ha(key, fallback, vars = {}) {
    const hass = this._hass;
    let text = "";
    try {
      if (hass && typeof hass.localize === "function") text = hass.localize(key, vars) || "";
    } catch (_err) {
      text = "";
    }
    if (text) return text;
    const q = vars.term !== undefined ? { q: vars.term } : vars;
    return this.t(fallback, q);
  }

  sectionTitle(key) {
    const official = { entity: "entities", device: "devices", area: "areas", label: "labels" }[key];
    return this.ha(`ui.components.target-picker.type.${official}`, `sec_${key}`);
  }

  /**
   * מה שהבורר צריך מעבר ל-hass: תוויות, קומות, ושם האינטגרציה של כל
   * מכשיר. נטען פעם אחת; כשל באחד מהם פשוט משאיר את הקטע שלו ריק.
   */
  async pickerData() {
    if (this._pickerData) return this._pickerData;
    const hass = this._hass;
    const ws = async (type) => {
      try {
        return await hass.callWS({ type });
      } catch (_err) {
        return [];
      }
    };
    if (typeof hass.loadBackendTranslation === "function") {
      try {
        await hass.loadBackendTranslation("title");
      } catch (_err) {
        // בלי שמות האינטגרציות מוצג המזהה שלהן.
      }
    }
    const [labels, floors, entries] = await Promise.all([
      ws("config/label_registry/list"), ws("config/floor_registry/list"), ws("config_entries/get"),
    ]);
    const domains = {};
    for (const entry of Array.isArray(entries) ? entries : []) domains[entry.entry_id] = entry.domain;
    this._pickerData = {
      labels: Array.isArray(labels) ? labels : [],
      floors: Array.isArray(floors) ? floors : [],
      domains,
    };
    return this._pickerData;
  }

  deviceName(id) {
    const device = this._hass.devices && this._hass.devices[id];
    return device ? String(device.name_by_user || device.name || id) : id;
  }

  /**
   * הקטעים של הבורר: ישויות, מכשירים, מרחבים (קומות וחדרים) ותוויות.
   * החיפוש כמו בבורר של HA: כמה שדות במשקלים שונים, כל מילה חייבת
   * להימצא, והציון הוא הסכום. התאמה מדויקת של מזהה עולה לראש.
   */
  pickerSections(query, filter = "", deviceId = "") {
    const hass = this._hass;
    const lang = this._lang;
    const data = this._pickerData || { labels: [], floors: [], domains: {} };
    const sep = this._dir === "rtl" ? " ◂ " : " ▸ ";
    const want = (key) => !filter || filter === key;
    const pickable = Object.keys(hass.states || {}).filter((id) => hass.states[id] && this._pickable(id));
    const sections = [];

    if (want("entity") || deviceId) {
      const ids = deviceId ? pickable.filter((id) => hass.entities && hass.entities[id] && hass.entities[id].device_id === deviceId) : pickable;
      sections.push({ key: "entity", rows: ids.map((id) => ({ ...this._entityParts(id), keys: ENTITY_KEYS })) });
    }
    if (!deviceId && want("device")) {
      const owned = new Set(pickable.map((id) => hass.entities && hass.entities[id] && hass.entities[id].device_id).filter(Boolean));
      const rows = [];
      for (const device of Object.values(hass.devices || {})) {
        if (!owned.has(device.id) || device.disabled_by) continue;
        const area = device.area_id && hass.areas && hass.areas[device.area_id] ? hass.areas[device.area_id].name : "";
        const domain = data.domains[device.primary_config_entry] || "";
        rows.push({
          type: "device", id: device.id, domain, primary: this.deviceName(device.id), secondary: area,
          end: domain ? this._domainName(domain) : "", area, keys: DEVICE_KEYS,
        });
      }
      sections.push({ key: "device", rows });
    }
    if (!deviceId && want("area")) {
      const floorName = {};
      for (const floor of data.floors) floorName[floor.floor_id] = floor.name;
      const rows = data.floors.map((floor) => ({
        type: "floor", id: floor.floor_id, primary: floor.name, secondary: "", icon: floor.icon || "mdi:home-floor-0",
        aliases: (floor.aliases || []).join(" "), keys: AREA_KEYS,
      }));
      for (const area of Object.values(hass.areas || {})) {
        rows.push({
          type: "area", id: area.area_id, primary: area.name, secondary: floorName[area.floor_id] || "",
          icon: area.icon || "mdi:texture-box", aliases: (area.aliases || []).join(" "), keys: AREA_KEYS,
        });
      }
      sections.push({ key: "area", rows });
    }
    if (!deviceId && want("label")) {
      sections.push({
        key: "label",
        rows: data.labels.map((label) => ({
          type: "label", id: label.label_id, primary: label.name, secondary: label.description || "",
          icon: label.icon || "mdi:label-outline", color: label.color || "", keys: LABEL_KEYS,
        })),
      });
    }

    const text = norm(query);
    const terms = text.split(/\s+/).filter(Boolean);
    for (const section of sections) {
      section.title = this.sectionTitle(section.key);
      if (!terms.length) {
        const label = (r) => `${r.primary}_${r.secondary}`;
        section.rows.sort((a, b) => label(a).localeCompare(label(b), lang, { sensitivity: "accent" }));
        continue;
      }
      const scored = [];
      for (const row of section.rows) {
        const fields = row.keys.map(([key, weight]) => [norm(row[key]), weight]);
        let total = 0;
        for (const term of terms) {
          let best = 0;
          for (const [value, weight] of fields) best = Math.max(best, matchScore(value, term) * weight);
          if (!best) {
            total = 0;
            break;
          }
          total += best;
        }
        if (total) scored.push({ row, total });
      }
      scored.sort((a, b) => b.total - a.total || a.row.primary.localeCompare(b.row.primary, lang));
      const exact = scored.findIndex((x) => x.row.id === text);
      if (exact > 0) scored.unshift(...scored.splice(exact, 1));
      section.rows = scored.map((x) => x.row);
    }
    return sections;
  }

  /** האייקון של שורה, באלמנטים של HA כשהם קיימים. */
  rowIcon(row) {
    const make = (tag) => (typeof customElements !== "undefined" && customElements.get(tag) ? document.createElement(tag) : null);
    if (row.type === "entity") return this.stateIcon(row.id);
    if (row.type === "device") {
      const el = row.domain ? make("ha-domain-icon") : null;
      if (el) {
        el.className = "pick-ha-icon";
        el.hass = this._hass;
        el.domain = row.domain;
        el.brandFallback = true;
        return el;
      }
      return h("span", { class: "pick-icon", "aria-hidden": "true" }, icon("devices"));
    }
    const el = make("ha-icon");
    if (el) {
      el.className = "pick-ha-icon";
      el.icon = row.icon;
      if (row.color) el.style.color = /^#|^rgb/.test(row.color) ? row.color : `var(--${row.color}-color)`;
      return el;
    }
    const fallback = { floor: "home-group", area: "door-open", label: "tune-variant" }[row.type] || "devices";
    return h("span", { class: "pick-icon", "aria-hidden": "true" }, icon(fallback));
  }

  /** האם להציג את מזהה הישות, לפי ההגדרה בפרופיל של המשתמש. */
  showEntityId() {
    return Boolean(this._hass && this._hass.userData && this._hass.userData.showEntityIdPicker);
  }

  /** אייקון המצב: state-badge של HA כשהוא קיים, ואחרת אייקון סוג בצבע המצב. */
  stateIcon(id) {
    const obj = this.stateObj(id);
    const domain = id.split(".", 1)[0];
    if (obj && typeof customElements !== "undefined" && customElements.get("state-badge")) {
      const badge = document.createElement("state-badge");
      badge.className = "pick-badge";
      badge.hass = this._hass;
      badge.stateObj = obj;
      return badge;
    }
    const active = obj && ACTIVE_STATES.has(String(obj.state));
    return h("span", { class: cls("pick-icon", active && "on"), "aria-hidden": "true" }, icon(DOMAIN_ICONS[domain] || "devices"));
  }

  /** קריאה כשהאלמנט נכנס לתצוגה (גלילה בבורר). בלי IntersectionObserver — מיד. */
  whenVisible(el, run) {
    if (typeof IntersectionObserver !== "function") {
      setTimeout(run, 0);
      return;
    }
    const watch = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        watch.disconnect();
        run();
      }
    }, { rootMargin: "200px" });
    watch.observe(el);
  }

  recent() {
    let ids = [];
    try {
      ids = JSON.parse(store.get(RECENT_KEY) || "[]");
    } catch (_err) {
      ids = [];
    }
    return (Array.isArray(ids) ? ids : [])
      .filter((id) => typeof id === "string" && this.stateObj(id) && this._pickable(id))
      .slice(0, 5)
      .map((id) => this._entityParts(id));
  }

  remember(eid) {
    let ids = [];
    try {
      ids = JSON.parse(store.get(RECENT_KEY) || "[]");
    } catch (_err) {
      ids = [];
    }
    ids = [eid, ...(Array.isArray(ids) ? ids : []).filter((id) => id !== eid)].slice(0, 5);
    store.set(RECENT_KEY, JSON.stringify(ids));
  }

  // מכשיר שמוצג נרשם כאן, כדי שעדכון של hass יצבע רק אותו.
  _watch(eid, paint, scope = this._live) {
    if (!eid) return;
    if (!scope.has(eid)) scope.set(eid, []);
    scope.get(eid).push(paint);
  }

  _refresh(before) {
    const now = this._hass.states || {};
    for (const scope of [this._live, this._liveDlg]) {
      for (const [eid, paints] of scope) {
        if (before[eid] === now[eid]) continue;
        for (const paint of paints) paint();
      }
    }
  }

  // ------------------------------------------------------------------
  // מה שמקש מציג
  // ------------------------------------------------------------------

  /** אזהרה על מקש: מכשיר שהוסר, לא זמין, קבוצה ריקה או מקש שאינו מוקרא. */
  alertFor(key) {
    const t = this.t;
    if (key.entity_id) {
      const hasStates = Boolean(this._hass && this._hass.states);
      const obj = this.stateObj(key.entity_id);
      if (hasStates ? !obj : key.missing || key.state === "missing") return { kind: "removed", text: t("key_removed") };
      if (hasStates ? obj.state === "unavailable" : key.state === "unavailable") return { kind: "unavailable", text: t("key_unavailable") };
    }
    if (key.kind === "cap" && key.gone) return { kind: "unavailable", text: t("key_unavailable") };
    if (key.kind === "group" && key.missing) return { kind: "unavailable", text: t("key_no_devices") };
    if (key.silent) return { kind: "quiet", text: t("key_quiet") };
    return null;
  }

  /** שורת המשנה של מקש, מנתונים מובנים ולא מטקסט של השרת. */
  keySubText(key) {
    const t = this.t;
    const n = Number(key.count || 0);
    switch (key.kind) {
      case "device":
        return joined([this.stateText(key.entity_id), counted(t, n, "actions_one", "actions_count")]);
      case "action":
        return key.does || "";
      case "goto":
        return key.target ? ltr(key.target) : "";
      case "submenu":
        return n ? counted(t, n, "keys_one", "keys_count") : t("empty_count");
      case "group":
        return counted(t, n, "devices_one", "devices_count");
      case "cap":
        if (key.cap === "choice") return t("options_count", { n });
        if (key.cap === "number" && key.min !== null && key.min !== undefined && key.max !== null && key.max !== undefined) {
          return [ltr(key.min), " – ", ltr(key.max)];
        }
        return "";
      default:
        return "";
    }
  }

  _tag(kind, text) {
    const iconName = kind === "removed" ? "alert-circle-outline" : "alert-outline";
    return h("span", { class: `tag tag-${kind}` }, icon(iconName), auto(text));
  }

  // ------------------------------------------------------------------
  // הציור
  // ------------------------------------------------------------------

  _render() {
    const root = this.shadowRoot;
    this._renders += 1;
    this._live = new Map();
    const active = root.activeElement;
    const keyFocused = Boolean(active && active.classList && active.classList.contains("key"));
    this._page.className = cls("page", this._narrow && "narrow");
    this._page.setAttribute("dir", this._dir || "rtl");
    this._page.replaceChildren(this._toolbar(), h("main", { class: "content" }, this._main()));
    this._flash = "";
    if (keyFocused) root.querySelector(`.key[data-digit="${quoted(this._cursor)}"]`)?.focus({ preventScroll: true });
  }

  _toolbar() {
    const t = this.t;
    const entries = this._entries || [];
    return h("header", { class: "toolbar" },
      this._narrow ? iconBtn("menu", t("menu"), { "data-act": "sidebar" }) : null,
      h("h1", { class: "title" }, t("title")),
      entries.length > 1
        ? h("select", { class: "line-pick", "data-act": "line", "aria-label": t("line") },
          entries.map((e) => h("option", { value: e.entry_id, selected: e.entry_id === this._entryId }, e.title)))
        : null,
      h("span", { class: "grow" }),
      iconBtn("dots-vertical", t("more"), { "data-act": "page-menu" }));
  }

  _main() {
    const t = this.t;
    if (this._failed) {
      return h("div", { class: "empty" }, icon("alert-circle-outline"),
        h("h2", null, t("failed_title")), h("p", null, t("failed_text")),
        btn("btn accent", { "data-act": "retry" }, t("retry")));
    }
    if (this._entries && !this._entries.length) {
      return h("div", { class: "empty" }, icon("phone-plus-outline"),
        h("h2", null, t("empty_title")), h("p", null, t("empty_text")),
        btn("btn accent", { "data-act": "settings" }, t("empty_go")));
    }
    if (!this._level) return [this._skeleton()];
    const editing = this._flow && this._dialog.inline && this._dialog.open;
    return [this._phone(), h("div", { class: "side" },
      editing ? this._dialog.side : [this._heardCard(), this._introCard(), this._looseCard()])];
  }

  _skeleton() {
    return h("section", { class: "card phone", "aria-busy": "true", "aria-label": this.t("pad") },
      h("div", { class: "where" }),
      h("div", { class: "pad" }, PAD.map(() => h("div", { class: "slot" }, h("div", { class: "key skeleton" })))));
  }

  _phone() {
    return h("section", { class: "card phone", "aria-label": this.t("pad") }, this._where(), this._pad());
  }

  _where() {
    const t = this.t;
    const level = this._level;
    const crumbs = level.crumbs || [];
    const last = crumbs.length - 1;
    const name = (c, i) => (i === 0 ? t("root") : c.name);
    return h("div", { class: "where" },
      h("nav", { "aria-label": t("where"), class: "grow" },
        h("ol", { class: "crumbs" }, crumbs.map((c, i) => h("li", null, i === last
          ? h("span", { class: "crumb", "aria-current": "page" }, auto(name(c, i)))
          : btn("crumb", { "data-act": "crumb", "data-path": c.path }, auto(name(c, i))))))),
      level.self ? iconBtn("pencil-outline", t("edit_here", { name: level.self.name }), { "data-act": "edit-self" }) : null);
  }

  _pad() {
    const t = this.t;
    const level = this._level;
    const depth = level.path ? level.path.split("/").length : 0;
    if (!PAD.includes(this._cursor)) this._cursor = "1";
    const slots = "123456789".split("").map((d) => this._slot(d));
    slots.push(
      this._navSlot("*", depth > 0, "nav-home", t("key_home"), "home-outline"),
      this._navSlot("0", depth > 0, "nav-up", t("key_back"), "keyboard-return"),
      this._navSlot("#", false, "", t("key_reserved"), ""),
    );
    return h("div", { class: "pad", role: "group", "aria-label": t("pad_hint") }, slots);
  }

  _tabindex(digit) {
    return digit === this._cursor ? "0" : "-1";
  }

  _digit(digit) {
    return h("span", { class: "k-digit", "aria-hidden": "true" }, ltr(digit));
  }

  _navSlot(digit, on, act, name, iconName) {
    const t = this.t;
    return h("div", { class: "slot" }, btn(cls("key k-nav"), {
      "data-digit": digit, "data-act": on ? act : null, "aria-disabled": on ? null : "true",
      tabindex: this._tabindex(digit), title: on ? null : name,
      "aria-label": on ? `${t("key", { digit })}: ${name}` : `${t("key", { digit })}: ${name}`,
    },
    this._digit(digit),
    on && iconName ? icon(iconName, "k-icon") : h("span"),
    h("span", { class: "k-name" }, on ? auto(name) : ""),
    h("span", { class: "k-sub" })));
  }

  /** המקש שהעורך שבעמודה עוסק בו, כדי לסמן אותו בלוח. */
  _editing() {
    const flow = this._flow;
    if (!flow || !this._dialog.inline) return "";
    if (flow.digit) return flow.digit;
    const key = flow.key;
    return key && !flow.self && parentOf(key.path) === this._level.path ? key.digit : "";
  }

  _canAdd() {
    const level = this._level;
    if (level.kind === "menu") return level.can_add;
    return (level.addable || []).some((c) => level.kind !== "plan" || c.kind !== "text" || level.streaming);
  }

  _slot(digit) {
    const t = this.t;
    const key = this._level.keys[digit];
    const sel = this._editing() === digit;
    const base = { "data-digit": digit, "data-drop": digit, tabindex: this._tabindex(digit), "aria-current": sel ? "true" : null };
    if (!key) {
      const open = this._canAdd();
      return h("div", { class: "slot" }, btn(cls("key k-empty", sel && "sel"), {
        ...base, "data-act": "empty", "aria-disabled": open ? null : "true",
        "aria-label": `${t("key", { digit })}: ${t("key_empty")}${open ? `. ${t("key_add")}` : ""}`,
      },
      this._digit(digit),
      icon("plus", "k-icon"),
      h("span", { class: "k-name" }, open ? t("key_add") : ""),
      h("span", { class: "k-sub" }, t("key_empty"))));
    }
    const fine = typeof matchMedia === "function" && matchMedia("(pointer: fine)").matches;
    const el = btn(cls("key", `k-${keyType(key)}`, sel && "sel", this._flash === digit && "flash"), {
      ...base, "data-act": "key", draggable: fine ? "true" : null, title: key.name,
    },
    this._digit(digit),
    fine ? h("span", { class: "k-grip", "aria-hidden": "true" }, icon("drag")) : null,
    icon(iconOf(key), "k-icon"),
    h("span", { class: "k-name" }, auto(key.name)),
    h("span", { class: "k-sub" }));
    const paint = () => this._paintKey(el, key);
    paint();
    if (key.entity_id) this._watch(key.entity_id, paint);
    const more = iconBtn("dots-vertical", t("key_edit", { digit }), {
      class: "icon-btn k-more", "data-act": "key-edit", "data-digit": digit, tabindex: this._tabindex(digit),
    });
    return h("div", { class: "slot" }, el, more);
  }

  // מה שמשתנה במקש עם מצב המכשיר: שורת המשנה, התגית והתווית לקורא המסך.
  _paintKey(el, key) {
    const t = this.t;
    const alert = this.alertFor(key);
    const line = el.querySelector(".k-sub");
    if (alert) line.replaceChildren(this._tag(alert.kind, alert.text));
    else {
      const sub = this.keySubText(key);
      line.replaceChildren(...[sub].flat().filter((s) => s !== "" && s !== null && s !== undefined).map((s) => (typeof s === "object" ? s : auto(s))));
    }
    el.classList.toggle("k-removed", Boolean(alert && alert.kind === "removed"));
    el.classList.toggle("k-unavailable", Boolean(alert && alert.kind === "unavailable"));
    const parts = [`${t("key", { digit: key.digit || "" })}: ${key.name}`, line.textContent];
    el.setAttribute("aria-label", parts.filter(Boolean).join(". "));
  }

  heardList(lines, title = "") {
    const intro = this._level ? this._level.intro : null;
    return h("div", { class: "section" },
      title ? h("div", { class: "section-head" }, icon("volume-high"), h("h3", null, title)) : null,
      h("ul", { class: "heard", "aria-live": "polite" }, lines.map((line, index) => h("li", {
        "data-live": intro && index === 0 && line === intro ? "intro" : null,
      }, auto(line)))));
  }

  _heardCard() {
    const t = this.t;
    const level = this._level;
    const root = !level.path;
    const filled = Object.values(level.keys).some(Boolean);
    const lines = level.heard || [];
    let body;
    if (lines.length) {
      body = this.heardList(lines);
    } else if (root && !filled) {
      body = [h("p", { class: "muted" }, t("heard_empty_root")),
        level.can_add ? h("div", null, btn("btn quiet", { "data-act": "build" }, icon("home-group"), t("build"))) : null];
    } else {
      body = h("div", { class: "alert info" }, icon("alert-circle-outline"), h("div", null, filled ? t("heard_unreached") : t("heard_empty")));
    }
    const chars = lines.join(" ").length;
    const seconds = Math.max(1, Math.round(chars / CHARS_PER_SECOND));
    return h("section", { class: "card", "aria-labelledby": "heard-title" },
      h("div", { class: "card-head" }, icon("volume-high"), h("h2", { id: "heard-title" }, t("heard")),
        lines.length ? h("span", { class: "heard-meta" }, t("heard_seconds", { n: seconds })) : null),
      h("div", { class: "card-body" }, body));
  }

  _introCard() {
    const t = this.t;
    const level = this._level;
    if (level.intro === null || level.intro === undefined) return null;
    return h("section", { class: "card", "aria-labelledby": "intro-title" },
      h("form", { "data-form": "intro" },
        h("div", { class: "card-head" }, icon("account-voice"), h("h2", { id: "intro-title" }, t("intro"))),
        h("div", { class: "card-body" }, h("label", { class: "field" },
          h("span", { class: "lbl" }, t("intro_label")),
          h("input", { type: "text", name: "intro", value: level.intro }),
          h("p", { class: "t-help" }, t("intro_help")))),
        h("div", { class: "card-foot" }, h("button", {
          type: "submit", class: "btn accent", "data-intro-save": true, disabled: true,
        }, t("save")))));
  }

  _looseCard() {
    const t = this.t;
    const loose = this._level.loose || [];
    if (!loose.length) return null;
    return h("section", { class: "card", "aria-labelledby": "loose-title" },
      h("div", { class: "card-head" }, icon("alert-outline"), h("h2", { id: "loose-title" }, t("loose"))),
      h("div", { class: "card-body" }, h("p", { class: "t-help" }, t("loose_help")),
        h("div", { class: "rows" }, loose.map((item) => h("div", { class: "row" },
          h("span", { class: "grow" }, auto(item.title)),
          iconBtn("dots-vertical", t("more"), { "data-act": "loose-menu", "data-id": item.id, "data-name": item.title }))))));
  }

  /** שורת מכשיר בדיאלוג: המזהה והמצב החי שלו. */
  entityLine(eid) {
    const live = h("span", { class: "live" });
    const line = h("div", { class: "entity" }, live, ltr(eid));
    const domain = eid.split(".", 1)[0];
    const paint = () => {
      const obj = this.stateObj(eid);
      const extra = MAIN_ATTR[domain] ? this.attrText(eid, MAIN_ATTR[domain]) : "";
      live.replaceChildren(...(obj ? joined([this.stateText(eid), extra]) : [this._tag("removed", this.t("key_removed"))]));
    };
    paint();
    this._watch(eid, paint, this._liveDlg);
    return line;
  }

  // ------------------------------------------------------------------
  // הדיאלוג
  // ------------------------------------------------------------------

  /**
   * פתיחת העורך. במסך רחב הוא בעמודה שליד הלוח, ובמסך צר — גיליון
   * תחתון. עורך שכבר פתוח בעמודה מתחלף, אחרי שאלה אם יש בו שינוי.
   */
  async _openFlow(flow, opener) {
    this._menu.hide();
    const current = this._flow;
    if (current && current !== flow && current.dirty()) {
      const t = this.t;
      const yes = await confirmDialog(this.shadowRoot, {
        title: t("discard_title"), text: t("discard_text"), ok: t("discard_go"), cancel: t("discard_keep"), danger: true,
      });
      if (!yes || this._flow !== current) return;
    }
    const wasOpen = this._dialog.open;
    if (!wasOpen) this._dialog.inline = this._wide();
    this._flow = flow;
    this._lost = null;
    this.repaint({ refocus: wasOpen });
    if (wasOpen) {
      if (this._dialog.inline) this._render();
      this._dialog.opener = opener || this._dialog.opener;
    } else {
      this._dialog.show(opener || this.shadowRoot.activeElement);
    }
    if (typeof flow.load === "function") await flow.load();
  }

  /** יש מקום לעמודה ליד הלוח: לא מסך צר, והעמוד עצמו רחב מספיק. */
  _wide() {
    if (this._narrow) return false;
    if (typeof matchMedia === "function" && matchMedia("(max-width: 870px), (max-height: 500px)").matches) return false;
    const width = this._page.clientWidth;
    return typeof width !== "number" || width === 0 || width >= 720;
  }

  repaint({ refocus = false } = {}) {
    const flow = this._flow;
    if (!flow) return;
    this._liveDlg = new Map();
    this._dialog.paint(flow.view(), this.t, { refocus });
  }

  /** סיום מוצלח: הדיאלוג נסגר בלי לשאול. */
  done() {
    this._flow = null;
    this._lost = null;
    this._dialog.close();
  }

  _closeDialog() {
    this._flow = null;
    this._dialog.close();
  }

  async _askClose() {
    const flow = this._flow;
    if (!flow) return;
    if (!flow.dirty()) {
      this.done();
      return;
    }
    const t = this.t;
    const yes = await confirmDialog(this.shadowRoot, {
      title: t("discard_title"), text: t("discard_text"), ok: t("discard_go"), cancel: t("discard_keep"), danger: true,
    });
    if (yes && this._flow === flow) this.done();
  }

  // Escape. אחרי פעולת משתמש אפשר לעצור אותו; אחרת הדיאלוג נסגר בכל
  // מקרה, והטיוטה נשמרת כדי שאפשר יהיה לשחזר אותה.
  _onDialogCancel(ev) {
    const flow = this._flow;
    if (!flow || !flow.dirty()) return;
    if (ev.cancelable) {
      ev.preventDefault();
      this._askClose();
      return;
    }
    this._lost = flow;
  }

  _onDialogClose() {
    const lost = this._lost;
    const inline = this._dialog.inline;
    this._flow = null;
    this._lost = null;
    this._liveDlg = new Map();
    if (inline) {
      // העמודה חוזרת לכרטיסים שלה, והמיקוד חוזר למקש.
      this._dialog.inline = false;
      this._render();
      if (!this._dialog.restoreFocus()) {
        this.shadowRoot.querySelector(`.key[data-digit="${quoted(this._cursor)}"]`)?.focus({ preventScroll: true });
      }
    } else {
      this._dialog.restoreFocus();
    }
    if (lost) {
      this._toast(this.t("unsaved"), { text: this.t("restore"), run: () => this._openFlow(lost) });
    }
  }

  _onBackdrop() {
    if (this._flow && this._flow.dirty()) this._dialog.shake();
    else this.done();
  }

  dialogAll(selector) {
    return [...this._dialog.el.querySelectorAll(selector)];
  }

  dialogOne(selector) {
    return this._dialog.el.querySelector(selector);
  }

  dialogForm() {
    const form = this._dialog.el.querySelector("form");
    return form ? new FormData(form) : null;
  }

  dialogValue(name) {
    const el = this._dialog.el.querySelector(`[name="${quoted(name)}"]`);
    return el ? String(el.value || "").trim() : undefined;
  }

  canReplace(key) {
    return Boolean(key.entity_id) && ["device", "action"].includes(key.kind) && parentOf(key.path) === this._level.path;
  }

  replace(key) {
    this.done();
    this._openFlow(new AddFlow(this, key.digit, { replace: true }));
  }

  // ------------------------------------------------------------------
  // תפריטים צפים
  // ------------------------------------------------------------------

  _keyMenu(key) {
    const t = this.t;
    const level = this._level;
    const home = parentOf(key.path);
    const items = [];
    const moves = [];
    if (home === level.path) {
      for (const digit of "123456789") {
        if (digit === key.digit) continue;
        const there = level.keys[digit];
        moves.push(there
          ? { label: t("swap_with", { name: `${digit} · ${there.name}` }), icon: "swap-horizontal", value: { move: this.path(digit) } }
          : { label: t("move_key", { digit }), icon: "plus", value: { move: this.path(digit) } });
      }
    }
    if (!["cap", "option"].includes(key.kind)) {
      const inside = (p) => p === key.path || p.startsWith(`${key.path}/`);
      const menus = (level.targets || []).filter((m) => m.path !== home && !inside(m.path)).map((m) => ({
        label: m.path ? `${m.path} · ${m.name}` : t("root"), icon: m.path ? "folder-outline" : "home-outline", value: { into: m.path },
      }));
      if (menus.length) {
        if (moves.length) moves.push({ sep: true });
        moves.push({ label: t("other_menu"), icon: "folder-outline", sub: menus });
      }
    }
    if (moves.length) items.push({ label: t("move_to"), icon: "cursor-move", sub: moves });
    if (this.canReplace(key)) items.push({ label: t("replace"), icon: "swap-horizontal", value: { replace: true } });
    if (items.length) items.push({ sep: true });
    items.push({ label: t("remove"), icon: "delete-outline", danger: true, value: { remove: true } });
    return items;
  }

  async _pickKey(key, value) {
    if (!value) return;
    if (value.replace) {
      this.replace(key);
      return;
    }
    if (value.remove) {
      await this._remove(key);
      return;
    }
    const args = value.move ? { to: value.move } : { to: value.into, into: true };
    await this._guard(async () => {
      const level = await this.mutate("move", { path: key.path, args }, {
        view: key.path === this._level.path ? parentOf(key.path) : this._level.path,
        flash: value.move ? value.move.split("/").pop() : "",
      });
      this.done();
      return level;
    });
  }

  async _remove(key) {
    const t = this.t;
    const inside = key.kind === "submenu" ? Number(key.count || 0) : 0;
    if (inside) {
      const yes = await confirmDialog(this.shadowRoot, {
        title: t("confirm_remove", { name: key.name }),
        text: inside === 1 ? t("confirm_remove_one") : t("confirm_remove_text", { n: inside }),
        ok: t("remove_item"), cancel: t("cancel"), danger: true,
      });
      if (!yes) return;
    }
    await this._guard(async () => {
      const level = await this.mutate("remove", { path: key.path }, {
        view: key.path === this._level.path ? parentOf(key.path) : this._level.path,
      });
      this.done();
      this._undoToast(t("removed"), level.undo);
    });
  }

  /** פעולה מחוץ לטופס: שגיאה בדיאלוג אם הוא פתוח, אחרת בהודעה. */
  async _guard(work) {
    try {
      return await work();
    } catch (err) {
      if (this._flow) {
        this._flow.error = this.errorText(err);
        this.repaint({ refocus: true });
      } else {
        this._toast(this.errorText(err));
      }
      return null;
    }
  }

  _pageMenu(anchor) {
    const t = this.t;
    const level = this._level;
    const items = [{ label: t("line_settings"), icon: "cog-outline", value: "settings" }];
    if (level && !level.path && level.kind === "menu" && level.can_add && Object.values(level.keys).some((k) => !k)) {
      items.push({ label: t("build"), icon: "home-group", value: "build" });
    }
    items.push({ sep: true }, { label: t("help"), icon: "help-circle-outline", value: "help" });
    this._menu.show(anchor, items, (value) => {
      if (value === "settings") this._goSettings();
      else if (value === "build") this._build(anchor);
      else if (value === "help") window.open(HELP_URL, "_blank", "noopener");
    });
  }

  _looseMenu(anchor, id, name) {
    const t = this.t;
    const level = this._level;
    const items = [];
    if (level.kind === "menu") {
      const free = "123456789".split("").filter((d) => !level.keys[d]).map((d) => ({
        label: t("move_key", { digit: d }), icon: "plus", value: { to: this.path(d) },
      }));
      if (free.length) items.push({ label: t("place_on_key"), icon: "cursor-move", sub: free });
    }
    items.push({ label: t("remove_item"), icon: "delete-outline", danger: true, value: { remove: true } });
    this._menu.show(anchor, items, async (value) => {
      if (value.remove) {
        await this._guard(async () => {
          const result = await this.mutate("remove", { args: { id } });
          this._undoToast(t("removed_item"), result.undo);
        });
      } else if (value.to) {
        await this._guard(() => this.mutate("move", { args: { to: value.to, id } }, { flash: value.to.split("/").pop() }));
      }
      void name;
    });
  }

  _goSettings() {
    const host = this.parentElement;
    if (host && typeof host.navigate === "function") host.navigate(SETTINGS_URL);
    else {
      history.pushState(null, "", SETTINGS_URL);
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    }
  }

  async _build(opener) {
    await this._guard(async () => {
      const found = await this.api("rooms");
      await this._openFlow(new BuildFlow(this, found.rooms || []), opener);
    });
  }

  // ------------------------------------------------------------------
  // מה שהמשתמש עושה
  // ------------------------------------------------------------------

  async _onClick(ev) {
    const el = ev.target.closest ? ev.target.closest("[data-act]") : null;
    if (!el || el.disabled || el.getAttribute("aria-disabled") === "true") return;
    const data = el.dataset;
    const level = this._level;
    if (data.digit && PAD.includes(data.digit)) this._cursor = data.digit;
    const flow = this._flow;
    const inDialog = Boolean(flow && el.closest && el.closest(".dlg-box"));

    if (inDialog) {
      switch (data.act) {
        case "dlg-close":
          await this._askClose();
          return;
        case "dlg-back":
          flow.back();
          return;
        case "dlg-menu":
          if (flow.key) this._menu.show(el, this._keyMenu(flow.key), (value) => this._pickKey(flow.key, value));
          return;
        case "check-all": {
          const scope = data.group ? `[data-group="${quoted(data.group)}"]` : "";
          for (const box of this.dialogAll(`input[type="checkbox"][name="${quoted(data.name)}"]${scope}`)) box.checked = Boolean(data.on);
          flow.input({ target: { name: data.name } });
          return;
        }
        default:
          await flow.act(data.act, data, el);
          return;
      }
    }

    switch (data.act) {
      case "sidebar":
        this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
        return;
      case "page-menu":
        this._pageMenu(el);
        return;
      case "settings":
        this._goSettings();
        return;
      case "retry":
        await this._start();
        return;
      case "build":
        await this._build(el);
        return;
      case "crumb":
        await this.go(data.path);
        return;
      case "nav-home":
        await this.go("");
        return;
      case "nav-up":
        await this.go(parentOf(level.path));
        return;
      case "edit-self":
        if (level.self) await this._openFlow(new KeyFlow(this, level.self, { self: true }), el);
        return;
      case "key": {
        const key = level.keys[data.digit];
        if (!key) return;
        if (key.enter) await this.go(key.path);
        else await this._openFlow(new KeyFlow(this, key), el);
        return;
      }
      case "key-edit": {
        const key = level.keys[data.digit];
        if (key) await this._openFlow(new KeyFlow(this, key), el);
        return;
      }
      case "empty":
        if (this._canAdd()) await this._openFlow(new AddFlow(this, data.digit), el);
        return;
      case "loose-menu":
        this._looseMenu(el, data.id, data.name);
        return;
      default:
    }
  }

  async _onSubmit(ev) {
    ev.preventDefault();
    const form = ev.target;
    const data = new FormData(form);
    if (form.dataset.form === "dlg") {
      if (this._flow) await this._flow.submit(data, ev.submitter);
      return;
    }
    if (form.dataset.form === "intro") {
      await this._guard(() => this.mutate("update", {
        path: this._level.path, args: { intro: String(data.get("intro") || "").trim() },
      }));
    }
  }

  _onInput(ev) {
    const target = ev.target;
    if (this._flow && target.closest && target.closest(".dlg-box")) {
      this._flow.input(ev);
      return;
    }
    // תצוגה חיה של הפתיח בזמן ההקלדה, וכפתור שמירה רק כשיש שינוי.
    if (target.name === "intro") {
      const value = String(target.value || "");
      for (const li of this.shadowRoot.querySelectorAll('[data-live="intro"]')) li.replaceChildren(auto(value));
      const save = this.shadowRoot.querySelector("[data-intro-save]");
      if (save) save.disabled = value.trim() === String(this._level.intro || "").trim();
    }
  }

  _onChange(ev) {
    const target = ev.target;
    if (this._flow && target.closest && target.closest(".dlg-box")) {
      this._flow.input(ev);
      return;
    }
    if (target.dataset && target.dataset.act === "line" && target.value !== this._entryId) {
      this._navigate(target.value, "");
      this._load(target.value, "");
    }
  }

  // חצים בתוך הלוח. מקש ההקשר (או Shift+F10) פותח את עריכת המקש.
  _onKeyDown(ev) {
    const el = ev.target && ev.target.closest ? ev.target.closest(".key") : null;
    if (this._flow && ev.target.closest && ev.target.closest(".dlg-box")) {
      if (typeof this._flow.keydown === "function") this._flow.keydown(ev);
      return;
    }
    if (!el) return;
    const digit = el.dataset.digit;
    if ((ev.key === "ContextMenu" || (ev.key === "F10" && ev.shiftKey)) && this._level.keys[digit]) {
      ev.preventDefault();
      this._openFlow(new KeyFlow(this, this._level.keys[digit]), el);
      return;
    }
    const at = PAD.indexOf(digit);
    if (at < 0) return;
    const col = at % 3;
    let next = -1;
    if (ev.key === "ArrowRight" && col < 2) next = at + 1;
    else if (ev.key === "ArrowLeft" && col > 0) next = at - 1;
    else if (ev.key === "ArrowDown" && at + 3 < PAD.length) next = at + 3;
    else if (ev.key === "ArrowUp" && at - 3 >= 0) next = at - 3;
    else if (ev.key === "Home") next = 0;
    else if (ev.key === "End") next = PAD.length - 1;
    if (next < 0) return;
    ev.preventDefault();
    this._cursor = PAD[next];
    for (const node of this.shadowRoot.querySelectorAll(".pad .key, .pad .k-more")) {
      node.setAttribute("tabindex", node.dataset.digit === this._cursor ? "0" : "-1");
    }
    this.shadowRoot.querySelector(`.pad .key[data-digit="${quoted(this._cursor)}"]`)?.focus();
  }

  // ------------------------------------------------------------------
  // גרירה (רק עם עכבר; במגע — "העברה ל…" בדיאלוג המקש)
  // ------------------------------------------------------------------

  _dropTarget(ev) {
    return ev.target.closest ? ev.target.closest("[data-drop]") : null;
  }

  _onDragStart(ev) {
    const el = ev.target.closest ? ev.target.closest(".key[draggable]") : null;
    const key = el ? this._level.keys[el.dataset.digit] : null;
    if (!key) return;
    this._drag = key.path;
    el.classList.add("dragging");
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", key.path);
  }

  _onDragOver(ev) {
    const el = this._dropTarget(ev);
    if (!this._drag || !el || this.path(el.dataset.drop) === this._drag) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    el.classList.add("over");
  }

  _endDrag() {
    this._drag = "";
    for (const node of this.shadowRoot.querySelectorAll(".key.dragging, .key.over")) node.classList.remove("dragging", "over");
  }

  async _onDrop(ev) {
    const el = this._dropTarget(ev);
    const from = this._drag;
    this._endDrag();
    if (!from || !el) return;
    ev.preventDefault();
    const to = this.path(el.dataset.drop);
    if (to !== from) await this._guard(() => this.mutate("move", { path: from, args: { to } }, { flash: el.dataset.drop }));
  }
}

HaIvrPanel.esc = esc;

if (!customElements.get("ha-ivr-panel")) {
  customElements.define("ha-ivr-panel", HaIvrPanel);
}
