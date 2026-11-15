// בדיקת עשן: מריצים את העמוד מול DOM מזויף ושרת מזויף, ומוודאים שכל
// מצב מצטייר בלי חריגה ושהפקודות שנשלחות נכונות.
import fs from "node:fs";
const src = fs.readFileSync(
  new URL("../custom_components/ha_ivr/frontend/panel.js", import.meta.url), "utf8",
);

// --- DOM קטן: מספיק לעמוד, וסופר כל אלמנט שנוצר ---
const created = [];
const innerHtmlWrites = [];
let focused = null;
class Node0 {
  constructor() { this.parentNode = null; }
  remove() {
    if (!this.parentNode) return;
    const kids = this.parentNode.childNodes;
    kids.splice(kids.indexOf(this), 1);
    this.parentNode = null;
  }
}
class Text0 extends Node0 {
  constructor(t) { super(); this.data = String(t); }
  get textContent() { return this.data; }
  set textContent(v) { this.data = String(v); }
}
const splitTop = (s, sep) => {
  const out = []; let cur = ""; let depth = 0; let quote = "";
  for (const ch of s) {
    if (quote) { cur += ch; if (ch === quote) quote = ""; continue; }
    if (ch === '"' || ch === "'") { quote = ch; cur += ch; continue; }
    if (ch === "[") depth += 1;
    if (ch === "]") depth -= 1;
    if (!depth && (sep === " " ? /\s/.test(ch) : ch === sep)) { if (cur.trim()) out.push(cur.trim()); cur = ""; continue; }
    cur += ch;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
};
const compound = (s) => {
  const tests = [];
  const re = /^(?:([a-zA-Z][\w-]*|\*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:="((?:[^"\\]|\\.)*)"|='((?:[^'\\]|\\.)*)')?\])/;
  while (s) {
    const m = s.match(re);
    if (!m) throw new Error(`בורר לא נתמך: ${s}`);
    if (m[1]) tests.push((e) => m[1] === "*" || e.tagName === m[1].toLowerCase());
    else if (m[2]) tests.push((e) => e.getAttribute("id") === m[2]);
    else if (m[3]) tests.push((e) => e.classList.contains(m[3]));
    else {
      const raw = m[5] ?? m[6];
      const want = raw === undefined ? undefined : raw.replace(/\\(.)/g, "$1");
      tests.push((e) => (want === undefined ? e.hasAttribute(m[4]) : e.getAttribute(m[4]) === want));
    }
    s = s.slice(m[0].length);
  }
  return (e) => tests.every((t) => t(e));
};
const matches = (el, sel) => splitTop(sel, ",").some((group) => {
  const chain = splitTop(group, " ").map(compound);
  if (!chain[chain.length - 1](el)) return false;
  let at = el.parentNode;
  for (let i = chain.length - 2; i >= 0; i -= 1) {
    while (at instanceof El && !chain[i](at)) at = at.parentNode;
    if (!(at instanceof El)) return false;
    at = at.parentNode;
  }
  return true;
});
class El extends Node0 {
  constructor(tag) { super(); this.tagName = tag.toLowerCase(); this.attrs = new Map(); this.childNodes = []; created.push(this.tagName); }
  setAttribute(n, v) { this.attrs.set(n, String(v)); }
  getAttribute(n) { return this.attrs.has(n) ? this.attrs.get(n) : null; }
  hasAttribute(n) { return this.attrs.has(n); }
  removeAttribute(n) { this.attrs.delete(n); }
  get classList() {
    const list = () => (this.getAttribute("class") || "").split(/\s+/).filter(Boolean);
    const set = (l) => this.setAttribute("class", l.join(" "));
    return {
      contains: (c) => list().includes(c),
      add: (...c) => set([...new Set([...list(), ...c])]),
      remove: (...c) => set(list().filter((x) => !c.includes(x))),
      toggle: (c, force) => {
        const on = force === undefined ? !list().includes(c) : Boolean(force);
        set(on ? [...new Set([...list(), c])] : list().filter((x) => x !== c));
        return on;
      },
    };
  }
  get dataset() {
    const out = {};
    for (const [k, v] of this.attrs) if (k.startsWith("data-")) out[k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v;
    return out;
  }
  append(...kids) {
    for (let kid of kids) {
      if (typeof kid !== "object") kid = new Text0(kid);
      kid.remove();
      kid.parentNode = this;
      this.childNodes.push(kid);
    }
  }
  replaceChildren(...kids) {
    for (const c of this.childNodes) c.parentNode = null;
    this.childNodes = [];
    this.append(...kids);
  }
  get textContent() { return this.childNodes.map((c) => c.textContent).join(""); }
  set textContent(v) { this.replaceChildren(new Text0(v)); }
  set innerHTML(v) { innerHtmlWrites.push(v); }
  get checked() { return this._checked ?? this.hasAttribute("checked"); }
  set checked(v) { this._checked = Boolean(v); }
  get value() { return this._value ?? this.getAttribute("value") ?? ""; }
  set value(v) { this._value = String(v); }
  get hidden() { return this.hasAttribute("hidden"); }
  set hidden(v) { if (v) this.setAttribute("hidden", ""); else this.removeAttribute("hidden"); }
  get disabled() { return this.hasAttribute("disabled"); }
  get name() { return this.getAttribute("name"); }
  focus() { focused = this; }
  addEventListener() {}
  matches(sel) { return matches(this, sel); }
  closest(sel) { let e = this; while (e instanceof El) { if (e.matches(sel)) return e; e = e.parentNode; } return null; }
  querySelectorAll(sel) {
    const out = [];
    const walk = (n) => { for (const c of n.childNodes) if (c instanceof El) { if (matches(c, sel)) out.push(c); walk(c); } };
    walk(this);
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  getElementById(id) { return this.querySelector(`#${id}`); }
}
const listeners = {};
class Shadow extends El {
  constructor() { super("#shadow"); }
  addEventListener(n, f) { listeners[n] = f; }
  get activeElement() { let e = focused; while (e) { if (e === this) return focused; e = e.parentNode; } return null; }
}
const VOID = new Set(["input", "br", "path"]);
const escT = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const ser = (n) => {
  if (n instanceof Text0) return escT(n.data);
  if (n.tagName === "style") return "";
  const a = [...n.attrs].map(([k, v]) => (v === "" ? ` ${k}` : ` ${k}="${escT(v).replace(/"/g, "&quot;")}"`)).join("");
  if (VOID.has(n.tagName)) return `<${n.tagName}${a}>`;
  return `<${n.tagName}${a}>${n.childNodes.map(ser).join("")}</${n.tagName}>`;
};

globalThis.document = {
  createElement: (t) => new El(t),
  createElementNS: (_ns, t) => new El(t),
  createTextNode: (t) => new Text0(t),
};
globalThis.HTMLElement = class { attachShadow() { this.shadowRoot = new Shadow(); return this.shadowRoot; } dispatchEvent() {} };
const defs = {};
globalThis.customElements = { get: (n) => defs[n], define: (n, c) => { defs[n] = c; } };
globalThis.localStorage = { getItem: () => "", setItem: () => {} };
globalThis.history = { pushState() {} };
globalThis.window = { dispatchEvent() {} };
globalThis.CustomEvent = class { constructor(t) { this.type = t; } };
globalThis.FormData = class {
  constructor(form) { this.f = form.fields; }
  get(n) { const v = this.f[n]; return Array.isArray(v) ? v[0] : v; }
  getAll(n) { const v = this.f[n]; return v === undefined ? [] : [].concat(v); }
};
await import("data:text/javascript;base64," + Buffer.from(src).toString("base64"));
const Panel = defs["ha-ivr-panel"];

// --- השרת המזויף ---
const EVIL = "<img src=x onerror=alert(1)>";
const EVIL2 = '"><script>alert(1)</script>';
const key = (path, kind, extra = {}) => ({ path, digit: path.slice(-1), enter: false, silent: false, label: "", detail: "", kind, name: kind, ...extra });
const levels = {
  "": { entry_id: "e", path: "", kind: "menu", self: null, streaming: true, crumbs: [{ path: "", name: "ראשי" }],
    keys: { 1: key("1", "device", { enter: true, domain: "climate", detail: "5 פעולות", name: "<מזגן>", entity_id: "climate.ac", state: "ok" }),
      2: key("2", "action", { domain: "button", detail: "פעמון", entity_id: "button.bell", state: "ok" }), 3: key("3", "submenu", { enter: true, silent: true, detail: "ריק" }),
      4: key("4", "goto", { target: "200", detail: "200" }), 5: key("5", "assistant"), 6: key("6", "alerts", { name: EVIL }),
      7: key("7", "group", { enter: true, domain: "light", missing: true }), 8: null, 9: null },
    heard: ["לתפריט מזגן הקש 1", EVIL2], silent: false, intro: "", addable: null, can_add: true, can_nest: true,
    loose: [{ id: "x", title: "אבוד" }, { id: "y", title: EVIL2 }] },
  "1": { entry_id: "e", path: "1", kind: "plan", streaming: false, self: key("1", "device", { enter: true, name: "מזגן", entity_id: "climate.ac" }),
    crumbs: [{ path: "", name: "ראשי" }, { path: "1", name: "מזגן" }],
    keys: { 1: key("1/1", "cap", { cap: "simple", ident: "turn_on", label: "הדלקה" }), 2: key("1/2", "cap", { cap: "choice", enter: true }),
      3: key("1/3", "cap", { cap: "number", detail: "הקשת מספר", gone: true }), 4: key("1/4", "cap", { cap: "status" }), 5: null, 6: null, 7: null, 8: null, 9: null },
    heard: ["להדלקה הקש 1"], silent: false, intro: null,
    addable: [{ ident: "turn_off", kind: "simple", name: "כיבוי", label: "כיבוי", new: true, code: null, needs_fixed: false },
      { ident: "say", kind: "text", name: "הכתבה", label: "הכתבה", new: true, code: null, needs_fixed: false, max_length: 100 },
      { ident: "preset", kind: "fixed", name: "מצב שמור", label: "מצב שמור", new: true, code: null, needs_fixed: true }],
    can_add: true, can_nest: true, loose: [] },
  "1/2": { entry_id: "e", path: "1/2", kind: "options", self: key("1/2", "cap", { cap: "choice", enter: true, label: "מצב" }),
    crumbs: [{ path: "", name: "ראשי" }, { path: "1", name: "מזגן" }, { path: "1/2", name: "מצב" }],
    keys: { 1: key("1/2/1", "option", { value: "low" }), 2: null, 3: null, 4: null, 5: null, 6: null, 7: null, 8: null, 9: null },
    heard: [], silent: false, intro: null, addable: [], can_add: true, can_nest: false, loose: [] },
  "3": { entry_id: "e", path: "3", kind: "menu", self: key("3", "submenu", { enter: true, id: "s3", label: "דלת" }),
    crumbs: [{ path: "", name: "ראשי" }, { path: "3", name: "דלת" }],
    keys: Object.fromEntries("123456789".split("").map((d) => [d, null])),
    heard: [], silent: true, intro: "", addable: null, can_add: true, can_nest: true, loose: [] },
};
const rooms = [{ area_id: "kit", name: "מטבח", kinds: [{ domain: "light", name: "התאורה", count: 1 }, { domain: "switch", name: "המתג", count: 2 }] },
  { area_id: "", name: "כל הבית", kinds: [{ domain: "light", name: "התאורה", count: 4 }] }];
const cap = (ident, kind, name, extra = {}) => ({ ident, kind, name, label: name, action: ident, options: [], min: null, max: null, code: null, needs_fixed: false, max_length: 0, checked: false, ...extra });
const sent = [];
const STATE_WORDS = { cool: "קירור", heat: "חימום", on: "דלוק" };
const hass = {
  states: { "light.a": { state: "on", attributes: { friendly_name: "מנורה" } }, "sensor.t": { state: "21", attributes: {} },
    "lock.d": { state: "locked", attributes: {} }, "switch.h": { state: "off", attributes: { friendly_name: "נסתר" } },
    "tts.x": { state: "ok", attributes: { friendly_name: "קול" } },
    "climate.ac": { state: "cool", attributes: { friendly_name: "מזגן", temperature: 22 } },
    "button.bell": { state: "unknown", attributes: { friendly_name: EVIL } } },
  entities: { "light.a": { area_id: "kit" }, "switch.h": { hidden: true } },
  devices: {}, areas: { kit: { name: "מטבח" } },
  formatEntityState: (s) => STATE_WORDS[s.state] || s.state,
  formatEntityAttributeValue: (s, a) => `${s.attributes[a]}°`,
  formatEntityName: (s) => s.attributes.friendly_name || "",
  callWS: async (m) => {
    sent.push(m);
    if (m.op === "entries") return { entries: [{ entry_id: "e", title: "קו", goto: true, extensions: true, goto_hint: "רמז", assistant: true, assistant_target: m.noTarget ? "" : "ha-assist", alerts: true, streaming: true }, { entry_id: "f", title: "קו ב" }], blocked: ["lock"] };
    if (m.op === "rooms") return { rooms };
    if (m.op === "places") return { floors: [{ id: "f1", name: "קומה א" }], areas: [{ id: "kit", name: "מטבח" }, { id: "liv", name: "סלון" }], labels: [] };
    if (m.op === "place") return { name: "מטבח", target: m.args.target, kinds: rooms[0].kinds, members: [{ entity_id: "light.a", name: "מנורה", domain: "light" }, { entity_id: "switch.q", name: "<קומקום>", domain: "switch" }, { entity_id: "switch.r", name: "תנור", domain: "switch" }] };
    if (m.op === "place_functions") return { kinds: [
      { domain: "light", name: "התאורה", capabilities: [{ ident: "turn_on", label: "הדלקה" }, { ident: "turn_off", label: "כיבוי" }] },
      { domain: "switch", name: "המתג", capabilities: [{ ident: "toggle", label: "החלפת מצב" }] }] };
    if (m.op === "actions") return { entity_id: m.args.entity_id, name: "מנורה", actions: [{ action: "turn_on", label: "הדלקה", fields: [
      { name: "brightness_pct", label: "בהירות", type: "number", required: false, min: 0, max: 100, step: 1, unit: "%" },
      { name: "effect", label: "אפקט", type: "select", required: false, options: [{ value: "rainbow", label: "קשת" }] },
      { name: "flash", label: "הבהוב", type: "boolean", required: false }] }] };
    if (m.op === "group") return { domain: "switch", name: "מתגים", target: { area_id: ["kit"], entity_id: ["switch.direct"] }, exclude: ["switch.r"], places: { floors: [], areas: [{ id: "kit", name: "מטבח" }, { id: "liv", name: "סלון" }], labels: [{ id: "eco", name: "חיסכון" }] } };
    if (m.op === "fixed") return { entity_id: "light.a", name: "מנורה", values: { brightness_pct: 30, effect: "rainbow", flash: true }, action: { action: "turn_on", label: "הדלקה", fields: [
      { name: "brightness_pct", label: "בהירות", type: "number", required: false, min: 0, max: 100, step: 1, unit: "%" },
      { name: "effect", label: "אפקט", type: "select", required: false, options: [{ value: "rainbow", label: "קשת" }] },
      { name: "flash", label: "הבהוב", type: "boolean", required: false }] } };
    if (m.op === "capabilities") return { entity_id: m.args.entity_id, name: "מנורה", fixed: true, state: "ok", streaming: !m.plain && m.entry_id === "e", capabilities: [
      cap("turn_on", "simple", "הדלקה", { checked: true }),
      cap("turn_off", "simple", "כיבוי"),
      cap("toggle", "simple", "החלפת מצב"),
      cap("set_fan_mode", "choice", "מצב מאוורר", { checked: !m.plain, options: [{ value: "low", label: "נמוך" }, { value: "high", label: "<גבוה>" }, { value: "auto", label: "אוטומטי" }] }),
      cap("set_temperature", "number", "טמפרטורה", { min: -5, max: 30 }),
      cap("unlock", "simple", "פתיחה", { code: { end: true, width: 0, min: 4, max: 8 } }),
      cap("say", "text", "הודעה בקול", { max_length: 120 }),
      cap("set_effect", "fixed", "אפקט", { needs_fixed: true, action: "turn_on" })] };
    if (m.op === "level") return levels[m.path];
    if (m.fail) throw { message: "נכשל" };
    return levels[m.view] || levels[""];
  },
};

let fails = 0;
const ok = (name, cond) => { if (!cond) { fails += 1; console.log("FAIL", name); } };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const el = new Panel();
el.narrow = false;
el.hass = hass;
await wait(20);
const root = el.shadowRoot;
const html = () => root.childNodes.map(ser).join("");
const text = () => root.textContent.replace(/\s+/g, " ");
const $ = (sel) => root.querySelector(sel);
const $$ = (sel) => root.querySelectorAll(sel);
const click = async (act, data = {}) => listeners.click({ target: { closest: () => ({ dataset: { act, ...data } }) } });
const press = async (node) => listeners.click({ target: node });
const submit = async (form, fields, data = {}) => listeners.submit({ preventDefault() {}, target: { dataset: { form, ...data }, fields } });
const keydown = (node, k) => { let stopped = false; listeners.keydown({ key: k, target: node, preventDefault() { stopped = true; } }); return stopped; };
const last = () => sent[sent.length - 1];
const box = (name, value) => $(`input[name="${name}"][value="${value}"]`);

ok("נטען", text().includes("המתקשר שומע") && text().includes("לתפריט מזגן הקש 1"));
ok("שם נמלט", html().includes("&lt;מזגן&gt;") && !html().includes("<מזגן>"));
ok("לשוניות", text().includes("קו ב"));
ok("פריט בלי מקש", text().includes("אבוד"));
ok("פירורי לחם", $(".crumbs [aria-current]")?.textContent === "ראשי");
ok("לוח קבוע של 12 מקשים", $$(".pad .key").length === 12);
ok("לכל מקש aria-label", $$(".pad .key").every((k) => k.getAttribute("aria-label")));
ok("כל מקש באותו מבנה", $$(".pad .key").every((k) => k.querySelector(".k-digit") && k.querySelector(".k-name") && k.querySelector(".k-sub")));
ok("כוכבית וסולמית מבודדות", $$(".k-digit bdi").map((b) => b.textContent).join("") === "123456789*0#" && $$(".k-digit bdi").every((b) => b.getAttribute("dir") === "ltr"));
ok("שלוחה מבודדת", $('.key[data-digit="4"] .k-sub bdi')?.textContent === "200");
ok("ערך מעוצב מבודד בכיוון שלו", $$('.key[data-digit="1"] .k-sub bdi[dir="auto"]').map((b) => b.textContent).join("|") === "קירור|5 פעולות");
ok("סגנון לכל מצב", $('.key[data-digit="3"]').classList.contains("k-stack") && $('.key[data-digit="5"]').classList.contains("k-assist") && $('.key[data-digit="8"]').classList.contains("k-empty"));
ok("מצב חי מתוך hass", $('.key[data-digit="1"] .k-sub').textContent === "קירור · 5 פעולות");
ok("קבוצה בלי מכשירים מסומנת", $('.key[data-digit="7"] .tag')?.textContent === "אין מכשירים");
ok("מקש שאינו מוקרא מסומן", $('.key[data-digit="3"] .tag')?.textContent === "לא מוקרא");

// --- XSS: שמות זדוניים נשארים טקסט ---
ok("esc נמלט גם מרכאות", Panel.esc(`"'<>&`) === "&quot;&#39;&lt;&gt;&amp;");
ok("שום img ו-script לא נוצרו", !created.includes("img") && !created.includes("script"));
ok("אין innerHTML בכלל", innerHtmlWrites.length === 0);
ok("השם הזדוני מוצג כטקסט", $('.key[data-digit="6"] .k-name').textContent === EVIL && html().includes("&lt;img src=x onerror=alert(1)&gt;"));
ok("גם שורת שמע ופריט אבוד", text().includes(EVIL2) && !html().includes("<script>"));

// --- set hass אינו מצייר מחדש ---
const renders = el._renders;
el.hass = { ...hass };
ok("hass עם אותם מצבים: כלום", el._renders === renders);
el.hass = { ...hass, states: { ...hass.states, "climate.ac": { ...hass.states["climate.ac"], state: "heat" } } };
ok("מצב שהשתנה מתעדכן במקום, בלי ציור", el._renders === renders && $('.key[data-digit="1"] .k-sub').textContent === "חימום · 5 פעולות" && $('.key[data-digit="1"]').getAttribute("aria-label").includes("חימום"));
const { "climate.ac": _gone, ...without } = hass.states;
el.hass = { ...hass, states: without };
ok("מכשיר שנמחק: תגית, בלי חריגה", el._renders === renders && $('.key[data-digit="1"] .tag-removed')?.textContent === "המכשיר הוסר" && $('.key[data-digit="1"]').classList.contains("k-removed"));
el.hass = { ...hass, states: { ...hass.states, "climate.ac": { state: "unavailable", attributes: {} } } };
ok("מכשיר לא זמין", $('.key[data-digit="1"] .tag-unavailable')?.textContent === "לא זמין");
el.hass = { ...hass, formatEntityState: () => { throw new Error("x"); }, states: { ...hass.states, "climate.ac": { state: "dry", attributes: {} } } };
ok("עיצוב שנכשל נופל לערך הגולמי", $('.key[data-digit="1"] .k-sub').textContent === "dry · 5 פעולות");
el.hass = hass;
el._render();

// --- ניווט במקלדת ---
const k1 = $('.key[data-digit="1"]');
ok("רק מקש אחד בטאב", $$('.pad .key[tabindex="0"]').length === 1 && k1.getAttribute("tabindex") === "0");
keydown(k1, "ArrowRight");
ok("חץ ימינה עובר ל-2", focused?.dataset.digit === "2" && focused.getAttribute("tabindex") === "0" && k1.getAttribute("tabindex") === "-1");
keydown(focused, "ArrowDown");
ok("חץ למטה עובר ל-5", focused?.dataset.digit === "5");
keydown(focused, "End");
ok("End עובר לסולמית", focused?.dataset.digit === "#");
ok("בשוליים החץ אינו יוצא", !keydown($('.key[data-digit="3"]'), "ArrowRight"));
el._cursor = "1";

// --- תצוגה חיה של משפט הפתיחה ---
const intro = $('input[name="intro"]');
intro.value = "שלום לכם";
listeners.input({ target: intro });
ok("משפט הפתיחה נשמע מיד", $('[data-live="intro"]').textContent === "שלום לכם" && !$('[data-live="intro"]').hidden);

await click("empty", { digit: "8" });
ok("הוספה", text().includes("מה יקרה כשמקישים 8?") && html().includes("<b>עוזר קולי</b>") && text().includes("התראות אחרונות"));
ok("המקש שנבחר מודגש", $('.key[data-digit="8"]').classList.contains("sel"));
ok("כותרת עם הספרה", $(".ed-head .badge")?.textContent === "8");
keydown($('input, button'), "Escape");
ok("Escape סוגר את העורך", el._mode.name === "heard");
await click("empty", { digit: "8" });
await click("add-step", { step: "device" });
ok("בורר: רק מה שמפעילים", text().includes("מנורה") && !text().includes("sensor.t") && !text().includes("lock.d") && !text().includes("נסתר"));
ok("מזהה המכשיר מבודד", $('.pick[data-id="light.a"] bdi')?.textContent === "light.a");
const search = $("[data-search]");
search.value = "sensor";
listeners.input({ target: search });
ok("החיפוש מחכה רגע", !$("#devices").textContent.includes("sensor.t"));
await wait(200);
ok("חיפוש מוצא חיישן", $("#devices").textContent.includes("sensor.t") && !el._devices("lock").length);
ok("מה שאין בו טעם לא בחיפוש", !el._devices("tts").length);
ok("בורר: עד 50", (() => {
  const saved = el._hass.states;
  el._hass.states = Object.fromEntries(Array.from({ length: 80 }, (_, i) => [`light.l${i}`, { state: "on", attributes: { friendly_name: `אור ${i}` } }]));
  const list = el._deviceList("");
  el._hass.states = saved;
  return list.filter((n) => n.classList && n.classList.contains("pick")).length === 50 && list.some((n) => n.textContent.includes("ועוד 30"));
})());
await click("add-device", { id: "light.a" });
ok("יכולות, עם סימון הכול וביטול הכול", text().includes("מה המתקשר יוכל לעשות") && text().includes("סימון הכול") && text().includes("ביטול הכול") && html().includes('data-name="cap"'));
const groups = $$(".sub h4").map((n) => n.textContent);
ok("היכולות בקבוצות לפי סוג", JSON.stringify(groups) === JSON.stringify(["בהקשה אחת", "בחירה מרשימה", "הקשת מספר", "עם קוד", "הכתבה בקול", "רק עם ערך קבוע"]));
ok("בחירה עם מספר האפשרויות", box("cap", "set_fan_mode").closest(".check").textContent.includes("3 אפשרויות"));
ok("מספר עם טווח, המינוס במקומו", box("cap", "set_temperature").closest(".check").querySelectorAll("bdi").map((b) => b.textContent).join("|") === "-5|30");
ok("קוד: מקישים ואחריו סולמית", box("cap", "unlock").closest(".check").querySelector("bdi")?.textContent === "#");
ok("ערך קבוע אינו תיבת סימון", !box("cap", "set_effect") && $('[data-act="cap-fixed"]')?.dataset.action === "turn_on");
ok("יש בחירה עם ערכים — הכפתור אומר המשך", $("[data-caps-btn]").textContent === "המשך");
ok("כפתור ההוספה בסרגל התחתון", Boolean($(".ed-foot [data-caps-btn]")));
await press($$('.sub [data-act="check-all"][data-group="simple"]')[1]);
ok("ביטול הכול רק בקבוצה שלו", !box("cap", "turn_on").checked && !box("cap", "turn_off").checked && box("cap", "set_fan_mode").checked);
await click("check-all", { name: "cap", on: "1" });
ok("סימון הכול אינו שובר את המסך", text().includes("מה המתקשר יוכל לעשות") && box("cap", "turn_off").checked);
ok("בלי בחירה עם ערכים — הכפתור מוסיף מיד", el._capsButton(["turn_on"]) === "הוספה למקש 8");
ok("מוצע גם מקש עם ערך קבוע", html().includes('data-act="add-fixed"'));
await press($('[data-act="cap-fixed"]'));
ok("יכולת עם ערך קבוע פותחת את הטופס שלה", last().op === "actions" && el._mode.step === "values" && el._mode.action.action === "turn_on");
await click("add-back");
await click("add-back");
ok("חזרה שומרת את מה שסומן", el._mode.step === "caps" && box("cap", "turn_off").checked);
await click("add-fixed");
ok("פעולות עם ערך", last().op === "actions" && html().includes("<b>הדלקה</b>") && text().includes("בהירות · אפקט · הבהוב"));
await click("add-values", { index: "0" });
ok("שדות הפעולה", html().includes('type="number" name="brightness_pct"') && html().includes('min="0"') && html().includes('max="100"') && html().includes('בהירות (<bdi dir="ltr">0</bdi> עד <bdi dir="ltr">100</bdi> %)') && html().includes('<option value="rainbow">קשת</option>') && html().includes('type="checkbox" name="flash"'));
await submit("fixed", { brightness_pct: "30", effect: "", _name: " אור עמום " });
ok("ערך קבוע נשלח, ורק מה שמולא", last().op === "add" && last().args.what === "action" && last().args.entity_id === "light.a" && last().args.action === "turn_on" && JSON.stringify(last().args.data) === '{"brightness_pct":"30"}' && last().args.name === "אור עמום");
await click("empty", { digit: "8" });
await click("add-step", { step: "device" });
await click("add-device", { id: "light.a" });
await click("add-fixed");
await click("add-back");
ok("חזרה מפעולות עם ערך למכשיר", text().includes("מה המתקשר יוכל לעשות"));
await submit("device", { cap: ["turn_on"], name: " אור " });
ok("מכשיר נשלח", last().op === "add" && last().path === "8" && last().args.what === "device" && last().args.entity_id === "light.a" && last().args.name === "אור" && last().view === "");
await click("empty", { digit: "8" });
await click("add-step", { step: "device" });
await click("add-device", { id: "light.a" });
await submit("device", { cap: ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"], name: "" });
ok("יותר מתשעה מקשים נעצר במקום", text().includes("מה המתקשר יוכל לעשות"));
await submit("device", { cap: ["turn_on", "set_fan_mode"], name: "מאוורר" });
ok("שלב שני: אילו ערכים להציע", text().includes("אילו ערכים להציע") && text().includes("מצב מאוורר") && text().includes("נמוך") && html().includes("&lt;גבוה&gt;") && html().includes('data-name="opt:set_fan_mode"') && !$$(".sub h4").some((n) => n.textContent === "הדלקה"));
const before = sent.length;
await submit("options", {});
ok("בלי אף ערך אין הוספה", sent.length === before && text().includes("אילו ערכים להציע"));
await click("add-back");
ok("חזרה שומרת את מה שסומן ואת השם", box("cap", "set_fan_mode").checked && !box("cap", "turn_off").checked && $('input[name="name"]').value === "מאוורר");
await submit("device", { cap: ["turn_on", "set_fan_mode"], name: "מאוורר" });
await submit("options", { "opt:set_fan_mode": ["high"] });
ok("הערכים שנבחרו נשלחים עם המכשיר", last().args.what === "device" && last().args.idents.length === 2 && JSON.stringify(last().args.options) === '{"set_fan_mode":["high"]}' && last().args.name === "מאוורר");
// בלי סטרימינג אין הכתבה, גם אם השרת שלח אותה
await click("empty", { digit: "8" });
await click("add-step", { step: "device" });
const realCall = hass.callWS;
hass.callWS = (m) => realCall({ ...m, plain: m.op === "capabilities" });
await click("add-device", { id: "light.a" });
hass.callWS = realCall;
ok("בלי סטרימינג אין הכתבה", !box("cap", "say") && !text().includes("הכתבה בקול"));
await click("close");
await click("empty", { digit: "9" });
await click("add-step", { step: "room" });
ok("חדרים", text().includes("איזה חדר?") && text().includes("כל הבית"));
ok("חיפוש: השם שהוקלד עולה לפני מה שרק מכיל אותו", (() => {
  const saved = el._hass.states;
  el._hass.states = { "switch.x": { attributes: { friendly_name: "מנורה חכמה" } }, "light.y": { attributes: { friendly_name: "מנורה" } } };
  const names = el._devices("מנורה").map((r) => r.name);
  el._hass.states = saved;
  return names[0] === "מנורה" && names.length === 2;
})());
ok("מוצע גם לצרף כמה מקומות", text().includes("כמה מקומות יחד"));
await click("add-room", { index: "0" });
ok("חדר: מה לכלול, המשך או הוספה מיד", last().op === "place" && last().args.target.area_id[0] === "kit" && text().includes("מה לכלול") && html().includes('data-go="next"') && text().includes("הוספה מיד, עם הכול"));
await listeners.submit({ preventDefault() {}, submitter: { dataset: { go: "add" } }, target: { dataset: { form: "room" }, fields: { kind: ["light", "switch"] } } });
ok("הוספה מיד מכניסה את הסוגים שסומנו, בלי החרגות", last().args.what === "room" && last().args.target.area_id[0] === "kit" && last().args.domains.length === 2 && last().args.exclude === undefined && last().args.idents === undefined);
await click("empty", { digit: "9" });
await click("add-step", { step: "room" });
await click("add-room", { index: "0" });
await submit("room", { kind: ["light", "switch"] });
ok("שלב המכשירים: לפי סוג, כולם מסומנים", text().includes("אילו מכשירים?") && html().includes("&lt;קומקום&gt;") && box("member:switch", "switch.q").checked && box("member:switch", "switch.r").checked);
ok("רשימה של פריט או שניים בלי כפתורי סימון", !html().includes('data-name="member:switch"') && !text().includes("סימון הכול"));
await submit("members", {});
ok("בלי אף מכשיר אין המשך", text().includes("אילו מכשירים?"));
await submit("members", { "member:light": ["light.a"], "member:switch": ["switch.q"] });
ok("מה שלא סומן נשלח כהחרגה", last().op === "place_functions" && JSON.stringify(last().args.exclude) === '["switch.r"]' && last().args.domains.length === 2);
ok("שלב הפעולות: לפי סוג", text().includes("מה המתקשר יוכל לעשות?") && text().includes("החלפת מצב"));
await click("add-back");
ok("חזרה למכשירים שומרת את מה שהוסר", !box("member:switch", "switch.r").checked && box("member:switch", "switch.q").checked);
await submit("members", { "member:light": ["light.a"], "member:switch": ["switch.q"] });
await submit("functions", { "cap:light": ["turn_on"], name: " מטבח קטן " });
ok("חדר נשלח עם המכשירים והפעולות שנבחרו", last().args.what === "room" && last().args.target.area_id[0] === "kit" && JSON.stringify(last().args.domains) === '["light"]' && JSON.stringify(last().args.idents) === '{"light":["turn_on"]}' && JSON.stringify(last().args.exclude) === '["switch.r"]' && last().args.name === "מטבח קטן");
await click("empty", { digit: "9" });
await click("add-step", { step: "room" });
await click("add-room", { index: "0" });
await submit("room", { kind: ["light", "switch"] });
await submit("members", { "member:light": ["light.a"] });
ok("סוג שלא נשאר בו מכשיר יורד, ואינו החרגה", JSON.stringify(last().args.domains) === '["light"]' && last().args.exclude.length === 0);
await click("empty", { digit: "9" });
await click("add-step", { step: "room" });
await click("add-places");
ok("כמה מקומות: קומות וחדרים", last().op === "places" && text().includes("אילו מקומות יחד?") && text().includes("קומה א") && text().includes("סלון") && !text().includes("תוויות"));
await submit("places", {});
ok("בלי מקום אין המשך", text().includes("אילו מקומות יחד?"));
await submit("places", { floor_id: ["f1"], area_id: ["kit", "liv"] });
ok("המקומות נשלחים יחד", last().op === "place" && last().args.target.floor_id[0] === "f1" && last().args.target.area_id.length === 2 && text().includes("מה לכלול"));
await click("add-back");
ok("חזרה מהסוגים לבחירת המקומות", text().includes("אילו מקומות יחד?"));
await click("empty", { digit: "9" });
await click("add-step", { step: "submenu" });
await submit("submenu", { name: "גינה" });
ok("תפריט נשלח ונכנסים אליו", last().args.what === "submenu" && last().view === "9");
await click("empty", { digit: "9" });
await click("add-assistant");
ok("עוזר מיד", last().args.what === "assistant" && last().path === "9");
await click("empty", { digit: "9" });
await click("add-step", { step: "goto" });
ok("טופס מעבר", text().includes("לאן עוברים") && text().includes("רמז"));
await submit("goto", { target: "200", name: "משרד" });
ok("מעבר נשלח", last().args.what === "goto" && last().args.target === "200");
await click("empty", { digit: "9" });
await click("add-alerts");
ok("התראות נשלח", last().args.what === "alerts");
await click("key", { digit: "2" });
ok("פרטי מקש", text().includes("פעולה אחת במכשיר «פעמון»") && text().includes("העברה למקש אחר"));
ok("מזהה המכשיר מבודד בכותרת", $('.entity bdi[dir="ltr"]')?.textContent === "button.bell");
const rename = $('input[name="name"]');
rename.value = "צלצול";
listeners.input({ target: rename });
await submit("rename", { name: "צלצול" }, { path: "2" });
ok("שינוי שם", last().op === "rename" && last().path === "2" && last().args.name === "צלצול");
await click("key", { digit: "1" });
await click("open", { path: "" });
await click("key", { digit: "4" });
ok("מקש רגיל בלי כפתורי עריכה של ערך", !html().includes('data-act="edit-value"'));
ok("יעד מעבר", html().includes('value="200"'));
await submit("target", { target: "300" }, { path: "4" });
ok("יעד נשלח", last().op === "update" && last().args.target === "300");
await click("key", { digit: "5" });
ok("עוזר עם יעד קבוע: אין מה לערוך", text().includes("מחבר את המתקשר לעוזר הקולי") && !html().includes('data-form="target"'));
el._entries[0].assistant_target = "";
el._render();
ok("עוזר בשלוחה של המשתמש: היעד נערך", text().includes("השלוחה שמחוברת לעוזר הקולי") && html().includes('data-form="target"'));
el._entries[0].assistant_target = "ha-assist";
// --- עריכת מקש קיים: ערך קבוע, והמקום של קבוצה ---
levels[""].keys["2"].fixed = true;
await el._open("");
ok("מקש עם ערך קבוע בסגנון משלו", $('.key[data-digit="2"]').classList.contains("k-fixed"));
await click("key", { digit: "2" });
ok("מקש עם ערך קבוע מציע לשנות אותו", html().includes('data-act="edit-value"'));
await click("edit-value", { path: "2" });
ok("הטופס נפתח עם הערכים השמורים", last().op === "fixed" && last().path === "2" && html().includes('name="brightness_pct" dir="ltr" value="30"') && html().includes('<option value="rainbow" selected>') && html().includes('name="flash" checked') && html().includes(">שמירה<"));
await submit("edit-values", { brightness_pct: "45", effect: "" });
ok("הערך החדש נשלח, ומה שנוקה יורד", last().op === "update" && last().path === "2" && JSON.stringify(last().args.values) === '{"brightness_pct":"45"}');
levels[""].keys["2"].fixed = false;

// --- מכשיר שהוסר: החלפה והסרה ---
levels[""].keys["8"] = key("8", "action", { domain: "light", detail: "מנורה", entity_id: "light.gone", missing: true, state: "missing", name: "ישנה" });
await el._open("");
ok("מקש של מכשיר שהוסר", $('.key[data-digit="8"] .tag-removed')?.textContent === "המכשיר הוסר");
await click("key", { digit: "8" });
ok("החלפה והסרה במקום", text().includes("המכשיר הוסר") && Boolean($('[data-act="replace"]')) && Boolean($('.note [data-act="remove"]')));
await press($('[data-act="replace"]'));
ok("החלפה פותחת את הבורר", text().includes("במה להחליף?") && $('.ed-head [data-act="close"]'));
await click("add-device", { id: "light.a" });
const mark = sent.length;
await submit("device", { cap: ["turn_on"], name: "" });
ok("החלפה: קודם מסירים, ואז מוסיפים באותו מקש", sent[mark].op === "remove" && sent[mark].path === "8" && sent[mark + 1].op === "add" && sent[mark + 1].path === "8");
levels[""].keys["8"] = null;

levels["7"] = { ...levels[""], path: "7", kind: "plan", crumbs: [{ path: "", name: "ראשי" }, { path: "7", name: "מתגים" }], self: key("7", "group", { domain: "switch", name: "מתגים", label: "" }), keys: { 1: null, 2: null, 3: null, 4: null, 5: null, 6: null, 7: null, 8: null, 9: null }, heard: [], addable: [] };
await el._open("7");
ok("קבוצה מציעה לשנות את המקום והמכשירים", html().includes('data-act="edit-place"'));
await click("edit-place", { path: "7" });
ok("המקומות הנוכחיים מסומנים, ומכשירים שנבחרו ישירות מוזכרים", last().op === "group" && text().includes("איפה המתגים?") && box("area_id", "kit").checked && !box("area_id", "liv").checked && text().includes("1 מכשירים שנבחרו ישירות"));
await submit("edit-places", { area_id: ["kit", "liv"] });
ok("המקום החדש נשאל, והבחירה הישירה נשמרת", last().op === "place" && last().args.target.area_id.length === 2 && last().args.target.entity_id[0] === "switch.direct");
ok("מי שכבר בחוץ אינו מסומן", text().includes("אילו מתגים?") && !box("member", "switch.r").checked && box("member", "switch.q").checked);
await click("edit-back");
ok("חזרה למקומות שומרת את מה שנבחר", box("area_id", "liv").checked);
await submit("edit-places", { area_id: ["kit", "liv"] });
await submit("edit-members", {});
ok("בלי אף מכשיר אין שמירה", last().op === "place");
await submit("edit-members", { member: ["switch.r"] });
ok("המקום וההחרגות נשמרים יחד", last().op === "update" && last().path === "7" && last().args.place.target.area_id.length === 2 && JSON.stringify(last().args.place.exclude) === '["switch.q"]');
await el._open("");
await click("key", { digit: "4" });
const n = sent.length;
await click("remove", { path: "4", sure: "remove:4" });
ok("מחיקה שואלת קודם", sent.length === n && text().includes("להסיר?"));
await click("remove", { path: "4", sure: "remove:4" });
ok("ואז מוחקת", last().op === "remove" && last().path === "4" && last().view === "");
await click("key", { digit: "2" });
await click("carry", { path: "2", name: "פעמון" });
ok("מצב העברה", text().includes("מעבירים את «פעמון»") && text().includes("לכאן") && $('.key[data-digit="2"]').classList.contains("carried"));
await click("key", { digit: "3" });
ok("תפריט נפתח תוך כדי העברה", el._level.path === "3" && el._carry);
await click("empty", { digit: "5" });
ok("העברה לתפריט אחר", last().op === "move" && last().path === "2" && last().args.to === "3/5" && !el._carry);
await click("open", { path: "" });
await click("key", { digit: "2" });
await click("carry", { path: "2", name: "פעמון" });
await click("key", { digit: "4" });
ok("החלפה באותה רמה", last().op === "move" && last().args.to === "4");
await click("loose-place", { id: "x", name: "אבוד" });
await click("empty", { digit: "9" });
ok("שיבוץ פריט אבוד", last().op === "move" && last().args.id === "x" && last().args.to === "9" && last().path === undefined);
await click("loose-remove", { id: "x", sure: "l" });
await click("loose-remove", { id: "x", sure: "l" });
ok("מחיקת פריט אבוד", last().op === "remove" && last().args.id === "x");
await click("key", { digit: "1" });
ok("כניסה למכשיר", el._level.path === "1" && text().includes("מקש 1") && !text().includes("לתפריט הראשי"));
ok("יכולת שאינה מתגלה עוד: לא זמין", $('.key[data-digit="3"] .tag-unavailable')?.textContent === "לא זמין");
await click("empty", { digit: "5" });
ok("פעולות להוספה", text().includes("איזו פעולה להוסיף?") && text().includes("כיבוי") && text().includes("יכולת חדשה"));
ok("בלי סטרימינג אין הכתבה ברשימה", !text().includes("הכתבה"));
ok("ערך קבוע מסומן ואינו נלחץ", text().includes("מצב שמור") && !$('[data-act="add-part"][data-ident="preset"]'));
await click("add-part", { ident: "turn_off", value: "" });
ok("יכולת נשלחת", last().args.what === "capability" && last().args.ident === "turn_off" && last().path === "1/5");
await click("key", { digit: "1" });
await click("carry", { path: "1/1", name: "הדלקה" });
ok("פעולה נשארת ברמה שלה", el._carry.only === "1");
await click("up");
ok("יציאה מהרמה מבטלת", el._level.path === "" && !el._carry);
await click("key", { digit: "1" });
await click("key", { digit: "2" });
ok("רמת אפשרויות", el._level.path === "1/2" && text().includes("לתפריט הראשי") && text().includes("שם הפעולה"));
ok("פירורי לחם בכל רמה", $$(".crumbs li").length === 3 && $(".crumbs [aria-current]").textContent === "מצב");
await click("empty", { digit: "5" });
ok("אין מה להוסיף", el._toast === "אין עוד מה להוסיף כאן.");
await click("carry", { path: "1/2", name: "מצב", up: "1" });
ok("העברת הרמה עצמה", el._level.path === "1" && el._carry.path === "1/2" && el._carry.only === "1");
await click("carry-cancel");
await click("remove", { path: "1", sure: "r" });
await click("remove", { path: "1", sure: "r" });
ok("מחיקת הרמה מחזירה למעלה", last().op === "remove" && last().view === "");
await click("open", { path: "3" });
ok("תפריט ריק מזהיר", text().includes("אין כאן עדיין מקשים"));
await submit("intro", { intro: "שלום" });
ok("פתיחה נשלחת", last().op === "update" && last().path === "3" && last().args.intro === "שלום");
await click("open", { path: "" });
await click("build");
ok("בנייה מהחדרים", text().includes("תפריט מהחדרים בבית") && text().includes("יש 2 מקשים פנויים"));
await submit("build", { room: ["0", "1"] });
ok("בנייה נשלחת", last().op === "build" && last().args.area_ids.join("|") === "kit|");
await click("entry", { id: "f" });
ok("מעבר קו", last().op === "level" && last().entry_id === "f");
// גרירה
el._level = levels[""];
el._render();
ok("ידית גרירה במקש מלא בלבד", Boolean($('.key[data-digit="2"] .k-grip')) && !$('.key[data-digit="8"] .k-grip'));
listeners.dragstart({ target: { closest: () => ({ dataset: { digit: "2" } }) }, dataTransfer: { setData() {} } });
let prevented = false;
const target8 = $('.key[data-digit="8"]');
const over = { target: target8, dataTransfer: {}, preventDefault() { prevented = true; } };
listeners.dragover(over);
ok("מקש היעד מודגש", target8.classList.contains("over"));
await listeners.drop(over);
ok("גרירה", prevented && last().op === "move" && last().path === "2" && last().args.to === "8");
// רוחב צר: העורך עולה מלמטה
el.narrow = true;
ok("כפתור תפריט בצר", html().includes('data-act="menu"'));
ok("בצר, שמע בתוך העמוד", Boolean($(".editor")) && !$(".editor.sheet"));
await click("key", { digit: "5" });
ok("בצר העורך הוא גיליון", Boolean($(".editor.sheet[role=\"dialog\"]")) && Boolean($(".scrim")));
await press($(".scrim"));
ok("לחיצה ברקע סוגרת", !$(".editor.sheet"));
ok("עדיין אין img ו-script", !created.includes("img") && !created.includes("script") && innerHtmlWrites.length === 0);
hass.callWS = async () => { throw { message: "נכשל" }; };
await click("open", { path: "3" });
ok("שגיאה מוצגת", el._toast === "נכשל" && el._busy === 0 && $(".toast")?.textContent === "נכשל");
console.log(fails ? `FAIL — ${fails} נכשלו` : "PASS — לוח המקשים מצטייר ושולח את הפקודות הנכונות");
process.exit(fails ? 1 : 0);
