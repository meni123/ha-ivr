// בדיקת עשן ללוח: מריצים את המודולים מול DOM מזויף ושרת מזויף, ומוודאים
// שכל זרימה מצטיירת בלי חריגה ושהפקודות שנשלחות נכונות.
import fs from "node:fs";

// --- DOM קטן: מספיק ללוח, וסופר כל אלמנט שנוצר ---
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
    if (ch === "[" || ch === "(") depth += 1;
    if (ch === "]" || ch === ")") depth -= 1;
    if (!depth && (sep === " " ? /\s/.test(ch) : ch === sep)) { if (cur.trim()) out.push(cur.trim()); cur = ""; continue; }
    cur += ch;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
};
const compound = (s) => {
  const tests = [];
  const re = /^(?:([a-zA-Z][\w-]*|\*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:="((?:[^"\\]|\\.)*)"|='((?:[^'\\]|\\.)*)')?\]|:not\((.+?)\))/;
  while (s) {
    const m = s.match(re);
    if (!m) throw new Error(`בורר לא נתמך: ${s}`);
    if (m[1]) tests.push((e) => m[1] === "*" || e.tagName === m[1].toLowerCase());
    else if (m[2]) tests.push((e) => e.getAttribute("id") === m[2]);
    else if (m[3]) tests.push((e) => e.classList.contains(m[3]));
    else if (m[7]) { const inner = compound(m[7]); tests.push((e) => !inner(e)); }
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
  const chain = splitTop(group, " ").filter((p) => p !== ">").map(compound);
  if (!chain[chain.length - 1](el)) return false;
  let at = el.parentNode;
  for (let i = chain.length - 2; i >= 0; i -= 1) {
    while (at instanceof El && !chain[i](at)) at = at.parentNode;
    if (!(at instanceof El)) return false;
    at = at.parentNode;
  }
  return true;
});
const fire = (node, type, ev = {}) => {
  for (const f of (node._ls && node._ls[type]) || []) f({ target: node, cancelable: true, preventDefault() { this.defaultPrevented = true; }, ...ev });
};
class El extends Node0 {
  constructor(tag) { super(); this.tagName = tag.toLowerCase(); this.attrs = new Map(); this.childNodes = []; this.style = {}; created.push(this.tagName); }
  setAttribute(n, v) { this.attrs.set(n, String(v)); }
  getAttribute(n) { return this.attrs.has(n) ? this.attrs.get(n) : null; }
  hasAttribute(n) { return this.attrs.has(n); }
  removeAttribute(n) { this.attrs.delete(n); }
  get className() { return this.getAttribute("class") || ""; }
  set className(v) { this.setAttribute("class", v); }
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
  get isConnected() { let e = this; while (e) { if (e instanceof Shadow) return true; e = e.parentNode; } return false; }
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
  get value() {
    if (this._value !== undefined) return this._value;
    if (this.tagName === "select") {
      const opts = this.querySelectorAll("option");
      const pick = opts.find((o) => o.hasAttribute("selected")) || opts[0];
      return pick ? pick.getAttribute("value") || "" : "";
    }
    return this.getAttribute("value") ?? "";
  }
  set value(v) { this._value = String(v); }
  get hidden() { return this.hasAttribute("hidden"); }
  set hidden(v) { if (v) this.setAttribute("hidden", ""); else this.removeAttribute("hidden"); }
  get disabled() { return this._disabled ?? this.hasAttribute("disabled"); }
  set disabled(v) { this._disabled = Boolean(v); }
  get open() { return this.hasAttribute("open"); }
  get name() { return this.getAttribute("name"); }
  get offsetWidth() { return 0; }
  focus() { focused = this; }
  addEventListener(n, f) { (this._ls ||= {})[n] = [...((this._ls || {})[n] || []), f]; }
  getBoundingClientRect() { return { left: 0, right: 40, top: 0, bottom: 40, width: 40, height: 40 }; }
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
  // <dialog>: showModal פותח, close סוגר ומודיע.
  showModal() { if (this.tagName !== "dialog") throw new Error("not a dialog"); this.setAttribute("open", ""); }
  close() { this.removeAttribute("open"); fire(this, "close"); }
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

const events = [];
const nav = [];
globalThis.document = {
  createElement: (t) => new El(t),
  createElementNS: (_ns, t) => new El(t),
  createTextNode: (t) => new Text0(t),
};
globalThis.HTMLElement = class {
  attachShadow() { this.shadowRoot = new Shadow(); return this.shadowRoot; }
  dispatchEvent(ev) { events.push(ev); }
  setAttribute(n, v) { (this._attrs ||= {})[n] = v; }
  getAttribute(n) { return (this._attrs || {})[n] ?? null; }
};
const defs = {};
globalThis.customElements = { get: (n) => defs[n], define: (n, c) => { defs[n] = c; } };
const storage = {};
globalThis.localStorage = { getItem: (k) => storage[k] ?? null, setItem: (k, v) => { storage[k] = String(v); } };
globalThis.location = { pathname: "/ha-ivr" };
globalThis.history = {
  state: null,
  pushState(_s, _t, url) { nav.push(["push", url]); location.pathname = url; },
  replaceState(_s, _t, url) { nav.push(["replace", url]); location.pathname = url; },
};
globalThis.window = { dispatchEvent(ev) { events.push(ev); }, open() {} };
globalThis.CustomEvent = class { constructor(t, o = {}) { this.type = t; this.detail = o.detail; } };
globalThis.matchMedia = (q) => ({ matches: q.includes("pointer: fine") });
globalThis.getComputedStyle = () => ({ direction: "rtl" });
globalThis.FormData = class {
  constructor(form) {
    this.f = {};
    if (form.fields) { this.f = form.fields; return; }
    for (const input of form.querySelectorAll("input, select")) {
      const name = input.getAttribute("name");
      if (!name) continue;
      const type = input.getAttribute("type");
      if (type === "checkbox") { if (input.checked) (this.f[name] ||= []).push(input.getAttribute("value") ?? "on"); continue; }
      (this.f[name] ||= []).push(input.value);
    }
  }
  has(n) { return n in this.f; }
  get(n) { const v = this.f[n]; return Array.isArray(v) ? v[0] : v ?? null; }
  getAll(n) { const v = this.f[n]; return v === undefined ? [] : [].concat(v); }
};
await import(new URL("../custom_components/ha_ivr/frontend/panel.js", import.meta.url));
const Panel = defs["ha-ivr-panel"];
const { STRINGS } = await import(new URL("../custom_components/ha_ivr/frontend/strings.js", import.meta.url));

// --- השרת המזויף ---
const EVIL = "<img src=x onerror=alert(1)>";
const EVIL2 = '"><script>alert(1)</script>';
const key = (path, kind, extra = {}) => ({ path, digit: path.slice(-1), enter: false, silent: false, label: "", detail: "", kind, name: kind, count: 0, ...extra });
const empty9 = () => Object.fromEntries("123456789".split("").map((d) => [d, null]));
const targets = [{ path: "", name: "" }, { path: "3", name: "דלת" }, { path: "7", name: "אורות" }];
const levels = {
  "": { entry_id: "e", path: "", kind: "menu", self: null, streaming: true, revision: "r1", targets, crumbs: [{ path: "", name: "ראשי" }],
    keys: { 1: key("1", "device", { enter: true, domain: "climate", count: 5, name: "<מזגן>", entity_id: "climate.ac", state: "ok" }),
      2: key("2", "action", { domain: "button", does: "לחיצה", fixed: true, entity_id: "button.bell", state: "ok" }),
      3: key("3", "submenu", { enter: true, silent: true, count: 2, name: "דלת" }),
      4: key("4", "goto", { target: "200", label: "", name: "משרד" }), 5: key("5", "assistant"), 6: key("6", "alerts", { name: EVIL }),
      7: key("7", "group", { enter: true, domain: "light", missing: true, name: "אורות" }), 8: null, 9: null },
    heard: ["שלום", "לתפריט מזגן הקש 1", EVIL2], silent: false, intro: "שלום", addable: null, can_add: true, can_nest: true,
    loose: [{ id: "x", title: "אבוד" }, { id: "y", title: EVIL2 }] },
  "1": { entry_id: "e", path: "1", kind: "plan", streaming: false, revision: "r1", targets, self: key("1", "device", { enter: true, name: "מזגן", entity_id: "climate.ac", count: 4 }),
    crumbs: [{ path: "", name: "ראשי" }, { path: "1", name: "מזגן" }],
    keys: { ...empty9(), 1: key("1/1", "cap", { cap: "simple", ident: "turn_on", label: "הדלקה", name: "הדלקה" }), 2: key("1/2", "cap", { cap: "choice", enter: true, count: 3 }),
      3: key("1/3", "cap", { cap: "number", min: 16, max: 30, gone: true }), 4: key("1/4", "cap", { cap: "status" }) },
    heard: ["להדלקה הקש 1"], silent: false, intro: null,
    addable: [{ ident: "turn_off", kind: "simple", name: "כיבוי", label: "כיבוי", new: true, code: null, needs_fixed: false },
      { ident: "say", kind: "text", name: "הכתבה", label: "הכתבה", new: true, code: null, needs_fixed: false, max_length: 100 },
      { ident: "preset", kind: "fixed", name: "מצב שמור", label: "מצב שמור", new: true, code: null, needs_fixed: true }],
    can_add: true, can_nest: true, loose: [] },
  "3": { entry_id: "e", path: "3", kind: "menu", revision: "r1", targets, self: key("3", "submenu", { enter: true, id: "s3", label: "דלת", name: "דלת", count: 0 }),
    crumbs: [{ path: "", name: "ראשי" }, { path: "3", name: "דלת" }],
    keys: empty9(), heard: [], silent: true, intro: "", addable: null, can_add: true, can_nest: true, loose: [] },
};
levels["8"] = { ...levels["3"], path: "8", self: key("8", "submenu", { enter: true, name: "קומה" }), crumbs: [{ path: "", name: "ראשי" }, { path: "8", name: "קומה" }] };
const cap = (ident, kind, name, extra = {}) => ({ ident, kind, name, label: name, action: ident, options: [], min: null, max: null, code: null, needs_fixed: false, max_length: 0, checked: false, ...extra });
const sent = [];
let failNext = null;
const STATE_WORDS = { cool: "קירור", heat: "חימום", on: "דלוק" };
const hass = {
  language: "he",
  states: { "light.a": { state: "on", attributes: { friendly_name: "מנורה" } }, "sensor.t": { state: "21", attributes: {} },
    "lock.d": { state: "locked", attributes: {} }, "switch.h": { state: "off", attributes: { friendly_name: "נסתר" } },
    "tts.x": { state: "ok", attributes: { friendly_name: "קול" } },
    "climate.ac": { state: "cool", attributes: { friendly_name: "מזגן", temperature: 22 } },
    "button.bell": { state: "unknown", attributes: { friendly_name: EVIL } } },
  entities: { "light.a": { area_id: "kit", device_id: "d1" }, "switch.h": { hidden: true }, "climate.ac": { device_id: "d2" } },
  devices: { d1: { id: "d1", name: "מנורת תקרה", area_id: "kit", primary_config_entry: "c1" }, d2: { id: "d2", name: "מזגן סלון" } },
  areas: { kit: { area_id: "kit", name: "מטבח", aliases: ["בישול"] } },
  formatEntityState: (s) => STATE_WORDS[s.state] || s.state,
  formatEntityAttributeValue: (s, a) => `${s.attributes[a]}°`,
  formatEntityName: (s) => s.attributes.friendly_name || "",
  callWS: async (m) => {
    sent.push(m);
    if (failNext && failNext === m.op) { failNext = null; throw { code: "taken", message: "מקש תפוס" }; }
    if (m.op === "entries") return { entries: [{ entry_id: "e", title: "קו", goto: true, extensions: true, goto_hint: "רמז", assistant: true, assistant_target: "ha-assist", alerts: true, streaming: true }, { entry_id: "f", title: "קו ב" }], blocked: ["lock"] };
    if (m.op === "rooms") return { rooms: [{ area_id: "kit", name: "מטבח", kinds: [{ domain: "light", name: "התאורה", count: 1 }] }] };
    if (m.op === "places") return { floors: [{ id: "f1", name: "קומה א" }], areas: [{ id: "kit", name: "מטבח" }, { id: "liv", name: "סלון" }], labels: [] };
    if (m.op === "place") return { name: "מטבח", target: m.args.target, kinds: [{ domain: "light", name: "התאורה", count: 1 }, { domain: "switch", name: "המתג", count: 2 }],
      members: [{ entity_id: "light.a", name: "מנורה", domain: "light" }, { entity_id: "switch.q", name: "<קומקום>", domain: "switch" }, { entity_id: "switch.r", name: "תנור", domain: "switch" }] };
    if (m.op === "place_functions") return { kinds: [
      { domain: "light", name: "התאורה", capabilities: [{ ident: "turn_on", label: "הדלקה" }, { ident: "turn_off", label: "כיבוי" }] },
      { domain: "switch", name: "המתג", capabilities: [{ ident: "toggle", label: "החלפת מצב" }] }] };
    if (m.op === "actions") return { entity_id: m.args.entity_id, name: "מנורה", actions: [{ action: "turn_on", label: "הדלקה", fields: [
      { name: "brightness_pct", label: "בהירות", type: "number", required: false, min: 0, max: 100, step: 1, unit: "%" },
      { name: "flash", label: "הבהוב", type: "boolean", required: false }] }] };
    if (m.op === "group") return { domain: "switch", name: "מתגים", target: { area_id: ["kit"], entity_id: ["switch.direct"] }, exclude: ["switch.r"], places: { floors: [], areas: [{ id: "kit", name: "מטבח" }, { id: "liv", name: "סלון" }], labels: [] } };
    if (m.op === "fixed") return { entity_id: "button.bell", name: "פעמון", values: { brightness_pct: 30 }, action: { action: "turn_on", label: "הדלקה", fields: [
      { name: "brightness_pct", label: "בהירות", type: "number", required: false, min: 0, max: 100, step: 1, unit: "%" }] } };
    if (m.op === "capabilities") return { entity_id: m.args.entity_id, name: "מנורה", fixed: true, state: "ok", streaming: true, capabilities: [
      cap("turn_on", "simple", "הדלקה", { checked: true }),
      cap("turn_off", "simple", "כיבוי"),
      cap("set_fan_mode", "choice", "מצב מאוורר", { checked: true, options: [{ value: "low", label: "נמוך" }, { value: "high", label: "<גבוה>" }] }),
      cap("set_temperature", "number", "טמפרטורה", { min: -5, max: 30 }),
      cap("unlock", "simple", "פתיחה", { code: { end: true, width: 0, min: 4, max: 8 } }),
      cap("set_effect", "fixed", "אפקט", { needs_fixed: true, action: "turn_on" })] };
    if (m.op === "level") return levels[m.path] || levels[""];
    const out = levels[m.view] || levels[""];
    return m.op === "remove" ? { ...out, undo: "tok1" } : out;
  },
};

let fails = 0;
let passes = 0;
const ok = (name, cond) => { if (!cond) { fails += 1; console.log("FAIL", name); } else passes += 1; };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const el = new Panel();
el.narrow = false;
el.hass = hass;
await wait(10);
const root = el.shadowRoot;
const html = () => root.childNodes.map(ser).join("");
const $ = (sel) => root.querySelector(sel);
const $$ = (sel) => root.querySelectorAll(sel);
const last = (op) => [...sent].reverse().find((m) => m.op === op);
const press = async (node) => { await listeners.click({ target: node }); await wait(0); };
const act = async (sel) => { const n = $(sel); if (!n) throw new Error(`אין ${sel}`); await press(n); };
const dlg = () => $(".dlg-box:not(.small)");
const dlgOpen = () => Boolean(dlg() && dlg().open);
const confirmBox = () => $("dialog.small");
const submitDlg = async (submitter = null) => { await listeners.submit({ preventDefault() {}, target: dlg().querySelector("form"), submitter }); await wait(0); };
const type = async (sel, value) => { const n = dlg().querySelector(sel); n.value = value; await listeners.input({ target: n }); };
const toasts = () => events.filter((e) => e.type === "hass-notification").map((e) => e.detail);

// --- כניסה ראשונה ---
ok("כניסה בלי קו בכתובת משלימה במקום, בלי רשומה בהיסטוריה",
  nav.length === 1 && nav[0][0] === "replace" && nav[0][1] === "/ha-ivr/e");
ok("לוח של 12 מקשים", $$(".pad .key").length === 12);
ok("הספרות משמאל לימין ובסדר טלפון",
  $$(".pad .key .k-digit bdi").map((b) => b.textContent).join("") === "123456789*0#"
  && $$(".pad .k-digit bdi").every((b) => b.getAttribute("dir") === "ltr"));
ok("שם מקש ב-<bdi> בלי dir, שמזהה כיוון לבד",
  $$(".pad .k-name > bdi").length >= 7 && $$(".pad .k-name > bdi").every((b) => !b.hasAttribute("dir")));
ok("כל שורה של המתקשר שומע ב-<bdi> בלי dir",
  $$(".heard li").length === 3 && $$(".heard li").every((li) => li.childNodes[0].tagName === "bdi" && !li.childNodes[0].hasAttribute("dir")));
ok("שם זדוני לא יוצר אלמנט", !created.includes("img") && !created.includes("script"));
ok("אין innerHTML בכלל", innerHtmlWrites.length === 0);
ok("esc נשאר לבדיקות", Panel.esc(EVIL2) === "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;");
ok("סרגל עליון עם שם ובורר קו", $(".toolbar .title").textContent === "תפריט טלפוני" && $$(".line-pick option").length === 2);
ok("אין כפתור תפריט כשלא צר", !$('[data-act="sidebar"]'));
ok("מכשיר: מצב חי ומספר פעולות", $('.key[data-digit="1"] .k-sub').textContent === "קירור · 5 פעולות");
ok("תת-תפריט, עוזר וקבוצה בסגנון משלהם",
  $('.key[data-digit="3"]').classList.contains("k-stack") && $('.key[data-digit="5"]').classList.contains("k-assist")
  && $('.key[data-digit="7"]').classList.contains("k-stack"));
ok("מקש שאינו מוקרא מקבל תגית", $('.key[data-digit="3"] .tag-quiet') !== null);
ok("קבוצה ריקה מסומנת", $('.key[data-digit="7"] .tag-unavailable') !== null);
ok("מקש ריק", $('.key[data-digit="8"]').classList.contains("k-empty"));
ok("* ו-0 מושבתים בשורש, # תמיד",
  ["*", "0", "#"].every((d) => $(`.key[data-digit="${d}"]`).getAttribute("aria-disabled") === "true"));
ok("לכל מקש מלא כפתור עריכה", $$(".k-more").length === 7);
ok("גרירה רק עם עכבר", $$('.key[draggable="true"]').length === 7);
ok("פתיח התפריט בכרטיס משלו, ושמירה כבויה עד שינוי",
  $('[data-form="intro"] input[name="intro"]').value === "שלום" && $("[data-intro-save]").disabled);
ok("לא משובצים", $$(".rows .row").length === 2);
ok("הערכת משך", $(".heard-meta").textContent.includes("שניות"));

// --- עדכון של hass: במקום, בלי ציור מחדש ---
const renders = el._renders;
el.hass = { ...hass, states: { ...hass.states, "climate.ac": { state: "heat", attributes: { friendly_name: "מזגן" } } } };
ok("עדכון hass אינו מצייר מחדש", el._renders === renders);
ok("אבל מעדכן את המקש", $('.key[data-digit="1"] .k-sub').textContent.startsWith("חימום"));
el.hass = { ...el.hass, states: { ...el.hass.states, "climate.ac": undefined } };
ok("מכשיר שנמחק: תגית ותווית לקורא מסך",
  $('.key[data-digit="1"] .tag-removed') !== null && $('.key[data-digit="1"]').getAttribute("aria-label").includes("המכשיר הוסר"));
el.hass = hass;

// --- מקלדת ---
focused = $('.key[data-digit="1"]');
listeners.keydown({ key: "ArrowRight", target: focused, preventDefault() {} });
ok("חץ ימינה עובר למקש 2", el._cursor === "2" && $('.key[data-digit="2"]').getAttribute("tabindex") === "0");
listeners.keydown({ key: "End", target: $('.key[data-digit="2"]'), preventDefault() {} });
ok("End עובר ל-#", el._cursor === "#");
ok("כפתור העריכה של המקש הנוכחי בלבד בסדר הטאב",
  $$(".k-more").filter((b) => b.getAttribute("tabindex") === "0").length === 0);
listeners.keydown({ key: "ArrowUp", target: $('.key[data-digit="#"]'), preventDefault() {} });
ok("חץ למעלה מ-# ל-9", el._cursor === "9");

// --- ניווט ---
nav.length = 0;
await act('.key[data-digit="1"]');
ok("מקש שנכנס לרמה: ניווט קדימה לכתובת שלו", nav.at(-1)?.join() === "push,/ha-ivr/e/1" && el._level.path === "1");
ok("פירורי לחם: הראשי מתורגם, האחרון אינו כפתור",
  $$(".crumbs li").length === 2 && $(".crumbs [aria-current]").textContent === "מזגן" && $('[data-act="crumb"]').textContent === "ראשי");
ok("עריכה של הרמה עצמה ליד הפירורים", $('[data-act="edit-self"]') !== null);
ok("* ו-0 פעילים בתוך רמה", !$('.key[data-digit="0"]').hasAttribute("aria-disabled"));
ok("יכולת עם טווח", $('.key[data-digit="3"] .tag-unavailable') !== null);
el.route = { prefix: "/ha-ivr", path: "/e" };
await wait(0);
ok("route מבחוץ (אחורה בדפדפן) רק טוען, בלי ניווט נוסף", el._level.path === "" && nav.length === 1);
nav.length = 0;
el.route = { prefix: "/ha-ivr", path: "/e/9/9" };
await wait(0);
ok("נתיב שאינו קיים: מתוקן במקום", nav.at(-1)?.join() === "replace,/ha-ivr/e" && el._level.path === "");
el.route = { prefix: "/ha-ivr", path: "/e" };
await wait(0);

// --- הוספה: מכשיר ---
await act('.key[data-digit="8"]');
ok("מקש ריק פותח דיאלוג הוספה", dlgOpen() && dlg().textContent.includes("הוספה למקש 8"));
ok("כל הסוגים שהקו תומך בהם", dlg().querySelectorAll('[data-act="type"]').length === 6);
ok("בצעד הראשון: X ולא חזרה", dlg().querySelector('[data-act="dlg-close"]') && !dlg().querySelector('[data-act="dlg-back"]'));
await press(dlg().querySelector('[data-type="device"]'));
ok("בחירת מכשיר: חיפוש וחזרה", dlg().querySelector("[data-search]") && dlg().querySelector('[data-act="dlg-back"]'));
ok("שלב 2 מתוך 3", dlg().textContent.includes("שלב 2 מתוך 3"));
ok("חסום ומוסתר אינם ברשימה", !dlg().textContent.includes("lock.d") && !dlg().textContent.includes("נסתר"));
await type("[data-search]", "קול");
ok("החיפוש מחכה", dlg().textContent.includes("מנורה"));
await wait(200);
ok("ומסנן אחרי ההשהיה, בנוסח של HA", dlg().querySelector(".pick-none")?.textContent === "לא נמצאו ישויות עבור ‘קול’");
ok("כפתור ניקוי מופיע כשיש טקסט", !dlg().querySelector(".search .clear").hidden);
await press(dlg().querySelector('[data-act="search-clear"]'));
ok("ניקוי מחזיר את כל הרשימה", dlg().querySelector("[data-search]").value === "" && dlg().querySelector(".search .clear").hidden
  && dlg().querySelectorAll(".pick").length >= 4);
const row = dlg().querySelector('.pick[data-id="light.a"]');
ok("שורה כמו בבורר של HA: אייקון, שם, אזור, ושם האינטגרציה",
  row.querySelector(".pick-icon.on") && row.querySelector(".pick-name").textContent === "מנורה"
  && row.querySelector("small").textContent === "מטבח ◂ מנורת תקרה" && row.querySelector(".pick-domain").textContent === "Light");
ok("בלי חיפוש: לפי שם, ובלי כותרות של חדרים", !dlg().querySelector("#picks h4"));
ok("קטעים עם כותרות, כמו בבורר של HA", dlg().querySelectorAll(".pick-head").map((x) => x.textContent).join("|") === "ישויות|מכשירים|מרחבים");
ok("שבבי סינון: ישויות, מכשירים, מרחבים | תוויות",
  dlg().querySelectorAll(".chip").map((c) => c.textContent).join("|") === "ישויות|מכשירים|מרחבים|תוויות" && dlg().querySelector(".chip-sep"));
await press(dlg().querySelector('[data-filter="area"]'));
ok("שבב מסנן לקטע אחד", dlg().querySelectorAll(".pick-head").length === 1 && dlg().querySelector('.pick[data-type="area"]')
  && dlg().querySelector('[data-filter="area"]').getAttribute("aria-pressed") === "true");
await type("[data-search]", "בישול");
await wait(200);
ok("מרחב נמצא גם לפי כינוי", dlg().querySelector(".pick")?.dataset.id === "kit");
await press(dlg().querySelector('.pick[data-type="area"]'));
ok("מרחב: ישר ל'מה לכלול'", last("place").args.target.area_id.join() === "kit" && dlg().querySelector('input[name="kind"]'));
await act('.dlg-box [data-act="dlg-back"]');
await press(dlg().querySelector('[data-filter="area"]'));
await type("[data-search]", "תקרה");
await wait(200);
ok("מכשיר: שם, אזור", dlg().querySelector('.pick[data-type="device"] small')?.textContent === "מטבח");
await press(dlg().querySelector('.pick[data-type="device"]'));
ok("מכשיר פותח את הישויות שלו בלבד", dlg().querySelectorAll(".pick").length === 1
  && dlg().querySelector(".pick").dataset.id === "light.a" && !dlg().querySelector(".chips") && dlg().textContent.includes("מנורת תקרה"));
await act('.dlg-box [data-act="dlg-back"]');
await type("[data-search]", "מנו מטב");
await wait(200);
ok("כמה מילים: כל אחת חייבת להימצא, בכל שדה",
  dlg().querySelectorAll('.pick[data-type="entity"]').length === 1 && dlg().querySelector(".pick").dataset.id === "light.a");
ok("בחיפוש התוצאה הראשונה מסומנת", dlg().querySelector(".pick.hl")?.dataset.id === "light.a"
  && dlg().querySelector("[data-search]").getAttribute("aria-activedescendant") === "pick-0");
await type("[data-search]", "climate.ac");
await wait(200);
ok("מזהה מדויק עולה לראש", dlg().querySelector(".pick").dataset.id === "climate.ac");
await type("[data-search]", "מזן");
await wait(200);
ok("התאמה עמומה", dlg().querySelector(".pick")?.dataset.id === "climate.ac");
await type("[data-search]", "");
await wait(200);
const search = dlg().querySelector("[data-search]");
listeners.keydown({ key: "ArrowDown", target: search, preventDefault() {} });
listeners.keydown({ key: "ArrowDown", target: search, preventDefault() {} });
ok("חצים מזיזים את הסימון, והמיקוד נשאר בשדה", dlg().querySelector(".pick.hl")?.getAttribute("id") === "pick-1");
listeners.keydown({ key: "Home", target: search, preventDefault() {} });
ok("Home לראש", dlg().querySelector(".pick.hl")?.getAttribute("id") === "pick-0");
await type("[data-search]", "מנורה");
await wait(200);
listeners.keydown({ key: "Enter", target: dlg().querySelector("[data-search]"), preventDefault() {} });
await wait(0);
ok("Enter בוחר את המסומן", last("capabilities").args.entity_id === "light.a");
ok("יכולות בקבוצות", dlg().querySelectorAll(".section-head h3").map((h3) => h3.textContent).join("|").startsWith("בהקשה אחת|בחירה מרשימה|הקשת מספר|עם קוד|עם ערך קבוע"));
ok("הכפתור אומר שיש עוד שלב", dlg().querySelector("[data-primary]").textContent === "המשך");
dlg().querySelector('input[value="set_fan_mode"]').checked = false;
await listeners.input({ target: dlg().querySelector('input[value="set_fan_mode"]') });
ok("ומתעדכן לפי הסימון", dlg().querySelector("[data-primary]").textContent === "הוספה");
dlg().querySelector('input[value="set_fan_mode"]').checked = true;
dlg().querySelector('input[name="name"]').value = "מנורה במטבח";
await submitDlg();
ok("בחירה עם ערכים: עוד שלב", dlg().querySelectorAll('input[name="opt:set_fan_mode"]').length === 2);
await act('.dlg-box [data-act="dlg-back"]');
ok("חזרה מגיעה לצעד הקודם בדיוק, עם מה שסומן",
  dlg().querySelector('input[value="set_fan_mode"]').checked && dlg().querySelector('input[name="name"]').value === "מנורה במטבח");
await submitDlg();
dlg().querySelector('input[name="opt:set_fan_mode"][value="high"]').checked = false;
await submitDlg();
let m = last("add");
ok("הוספת מכשיר עם יכולות וערכים",
  m.path === "8" && m.args.what === "device" && m.args.entity_id === "light.a"
  && m.args.idents.join() === "turn_on,set_fan_mode" && m.args.options.set_fan_mode.join() === "low"
  && m.args.name === "מנורה במטבח" && m.view === "" && !m.args.replace);
ok("והדיאלוג נסגר", !dlgOpen());
ok("ונזכר בשימוש האחרון", JSON.parse(storage.ha_ivr_recent)[0] === "light.a");

// --- הוספה: ערך קבוע ---
await act('.key[data-digit="8"]');
ok("בשימוש לאחרונה בראש הרשימה", dlg().textContent.includes("בשימוש לאחרונה"));
await press(dlg().querySelector('[data-act="pick-device"][data-id="light.a"]'));
await press(dlg().querySelector('[data-act="cap-fixed"]'));
ok("ערך קבוע: הטופס של הפעולה", dlg().querySelector('input[name="v_brightness_pct"]')?.getAttribute("min") === "0");
dlg().querySelector('input[name="v_brightness_pct"]').value = "40";
dlg().querySelector('input[name="v_flash"]').checked = true;
await submitDlg();
m = last("add");
ok("הוספת פעולה עם ערך", m.args.what === "action" && m.args.action === "turn_on"
  && m.args.data.brightness_pct === "40" && m.args.data.flash === true);

// --- הוספה: חדר בשלושה צעדים ---
await act('.key[data-digit="8"]');
await press(dlg().querySelector('[data-type="room"]'));
ok("מקום: חדרים וקומות", dlg().querySelectorAll('input[name="area_id"]').length === 2 && dlg().textContent.includes("כל הבית"));
await submitDlg();
ok("בלי בחירה — שגיאה בראש הדיאלוג", dlg().querySelector(".alert.error")?.textContent.includes("לפחות חדר"));
dlg().querySelector('input[name="whole"]').checked = true;
await submitDlg();
ok("כל הבית: יעד ריק", last("place").args.target && Object.keys(last("place").args.target).length === 0);
ok("מה לכלול: סוגים, וחברים בסעיף מתקפל", dlg().querySelectorAll('input[name="kind"]').length === 2 && dlg().querySelector("details.fold"));
dlg().querySelector('input[name="member:switch"][value="switch.r"]').checked = false;
await submitDlg();
ok("פונקציות לפי מה שנשאר", last("place_functions").args.exclude.join() === "switch.r" && last("place_functions").args.domains.join() === "light,switch");
await submitDlg();
m = last("add");
ok("הוספת חדר", m.args.what === "room" && m.args.idents.light.join() === "turn_on,turn_off" && m.args.exclude.join() === "switch.r");

await act('.key[data-digit="8"]');
await press(dlg().querySelector('[data-type="room"]'));
dlg().querySelector('input[name="area_id"][value="kit"]').checked = true;
await submitDlg();
await press(dlg().querySelector('[data-act="add-all"]'));
m = last("add");
ok("הוספה עם הכול מדלגת על הצעד האחרון", m.args.what === "room" && m.args.target.area_id.join() === "kit" && !m.args.idents);

// --- הוספה: תפריט, עוזר ---
await act('.key[data-digit="8"]');
await press(dlg().querySelector('[data-type="submenu"]'));
await submitDlg();
ok("תפריט בלי שם נעצר בטופס", dlgOpen() && dlg().querySelector(".alert.error"));
dlg().querySelector('input[name="name"]').value = "קומה";
nav.length = 0;
await submitDlg();
m = last("add");
ok("תפריט חדש: נכנסים אליו", m.args.what === "submenu" && m.view === "8" && nav.at(-1)?.[0] === "push");
el.route = { prefix: "/ha-ivr", path: "/e" };
await wait(0);
await act('.key[data-digit="8"]');
await press(dlg().querySelector('[data-type="assistant"]'));
ok("עוזר עם יעד קבוע נוסף מיד", last("add").args.what === "assistant" && !dlgOpen());

// --- שגיאה מהשרת: בדיאלוג, לא בהודעה ---
await act('.key[data-digit="8"]');
failNext = "add";
await press(dlg().querySelector('[data-type="alerts"]'));
ok("שגיאה מתורגמת לפי הקוד, בראש הדיאלוג", dlgOpen() && dlg().querySelector(".alert.error").textContent === "המקש תפוס");
await act('.dlg-box [data-act="dlg-close"]');
ok("סגירה בלי שינוי לא שואלת", !dlgOpen() && !confirmBox());

// --- דיאלוג מקש: עריכה ושמירה אחת ---
await act('.k-more[data-digit="4"]');
ok("דיאלוג המקש: ספרה, שם וסוג", dlgOpen() && dlg().querySelector(".dlg-badge").textContent === "4" && dlg().textContent.includes("העברת שיחה"));
ok("שמירה כבויה עד שיש שינוי", dlg().querySelector("[data-save]").disabled);
await type('input[name="target"]', "300");
ok("שינוי מפעיל את השמירה", !dlg().querySelector("[data-save]").disabled);
await type('input[name="name"]', "מזכירות");
await submitDlg();
m = last("update");
ok("כל מה שהשתנה נשלח בעדכון אחד", m.path === "4" && m.args.target === "300" && m.args.name === "מזכירות" && !("values" in m.args));
ok("והדיאלוג נסגר", !dlgOpen());

await act('.key[data-digit="2"]');
await wait(0);
ok("פעולה עם ערך קבוע: הערך בדיאלוג", dlg().querySelector('input[name="v_brightness_pct"]')?.value === "30");
await type('input[name="v_brightness_pct"]', "55");
await submitDlg();
ok("עדכון ערך", last("update").args.values.brightness_pct === "55" && !("name" in last("update").args));

// --- העורך בעמודה שליד הלוח ---
await act('.k-more[data-digit="6"]');
ok("במסך רחב העורך בעמודה, לא בחלון קופץ", dlg().tagName === "section" && dlg().classList.contains("side-editor")
  && !$("dialog.dlg-box")?.open);
ok("והמקש שבעריכה מסומן בלוח", $('.key[data-digit="6"]').classList.contains("sel")
  && $('.key[data-digit="6"]').getAttribute("aria-current") === "true");
ok("כרטיסי הצד מתחלפים בעורך", !$("#heard-title"));
await act('.k-more[data-digit="4"]');
ok("מקש אחר מחליף את העורך בלי לסגור", dlgOpen() && dlg().querySelector(".dlg-badge").textContent === "4"
  && $('.key[data-digit="4"]').classList.contains("sel") && !$('.key[data-digit="6"]').classList.contains("sel"));
await type('input[name="name"]', "שונה");
let side = dlg();
for (const f of side._ls.keydown) f({ key: "Escape", target: side, preventDefault() { this.defaultPrevented = true; } });
await wait(0);
ok("Escape בעמודה עם שינוי שואל", confirmBox()?.open);
for (const f of confirmBox().querySelector(".btn.danger")._ls.click) f({});
await wait(0);
ok("וסגירה מחזירה את הכרטיסים", !dlgOpen() && $("#heard-title") && !$(".key.sel"));

// --- Escape עם שינוי, בגיליון תחתון (מסך צר) ---
el.narrow = true;
await act('.k-more[data-digit="6"]');
ok("במסך צר העורך הוא <dialog>", dlg().tagName === "dialog");
await type('input[name="name"]', "התראות");
let ev = { cancelable: true, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
for (const f of dlg()._ls.cancel) f(ev);
await wait(0);
ok("Escape עם שינוי נעצר ושואל", ev.defaultPrevented && confirmBox()?.open);
for (const f of confirmBox().querySelector(".btn.plain")._ls.click) f({});
await wait(0);
ok("המשך עריכה משאיר את הדיאלוג", dlgOpen() && !confirmBox());
ev = { cancelable: false, preventDefault() { throw new Error("לא אמור"); } };
for (const f of dlg()._ls.cancel) f(ev);
dlg().close();
await wait(0);
const lost = toasts().at(-1);
ok("Escape שאי אפשר לעצור: הודעה עם שחזור", !dlgOpen() && lost.message === "השינויים לא נשמרו" && lost.action.text === "שחזור");
lost.action.action();
await wait(0);
ok("שחזור פותח את הטיוטה כמו שהייתה", dlgOpen() && dlg().querySelector('input[name="name"]').value === "התראות");
listeners.click({ target: $('.dlg-box [data-act="dlg-close"]') });
await wait(0);
ok("סגירה עם שינוי שואלת", confirmBox()?.open);
for (const f of confirmBox().querySelector(".btn.danger")._ls.click) f({});
await wait(0);
ok("ביטול השינויים סוגר", !dlgOpen());
let backdrop = 0;
await act('.k-more[data-digit="6"]');
await type('input[name="name"]', "שונה");
dlg().classList.remove("shake");
for (const f of dlg()._ls.click) f({ target: dlg() });
ok("לחיצה על הרקע עם שינוי אינה סוגרת", dlgOpen() && dlg().classList.contains("shake"));
backdrop += 1;
dlg().close();
await wait(0);
el.narrow = false;

// --- תפריט המקש: העברה, החלפה, הסרה וביטול ---
const menu = () => $(".menu");
const pick = async (label) => {
  const item = menu().querySelectorAll(".mi").find((b) => b.textContent.includes(label));
  if (!item) throw new Error(`אין בתפריט: ${label} — ${menu().textContent}`);
  for (const f of menu()._ls.click) f({ target: item });
  await wait(0);
};
await act('.k-more[data-digit="4"]');
await act('.dlg-box [data-act="dlg-menu"]');
ok("תפריט המקש נפתח", menu()?.hasAttribute("open"));
ok("הסרה אחרונה ובצבע אזהרה", menu().querySelectorAll(".mi").at(-1).classList.contains("danger"));
await pick("העברה ל");
ok("מקש ריק והחלפה עם תפוס", menu().textContent.includes("מקש 8") && menu().textContent.includes("החלפה עם 1"));
await pick("מקש 9");
m = last("move");
ok("העברה למקש ריק", m.path === "4" && m.args.to === "9" && !m.args.into && !dlgOpen());

await act('.k-more[data-digit="4"]');
await act('.dlg-box [data-act="dlg-menu"]');
await pick("העברה ל");
await pick("תפריט אחר");
ok("תפריט אחר: בלי הרמה הנוכחית", !menu().textContent.includes("ראשי") && menu().textContent.includes("3 · דלת"));
await pick("3 · דלת");
m = last("move");
ok("העברה לתפריט אחר", m.args.to === "3" && m.args.into === true);

await act('.k-more[data-digit="2"]');
await wait(0);
await act('.dlg-box [data-act="dlg-menu"]');
await pick("החלפת המכשיר");
ok("החלפה: נפתח בבחירת מכשיר", dlgOpen() && dlg().querySelector("[data-search]") && dlg().textContent.includes("החלפת המכשיר"));
await press(dlg().querySelector('[data-act="pick-device"][data-id="light.a"]'));
dlg().querySelector('input[value="set_fan_mode"]').checked = false;
await submitDlg();
m = last("add");
ok("ההחלפה היא פעולה אחת בשרת", m.path === "2" && m.args.replace === true && !sent.slice(-3).some((s) => s.op === "remove"));

events.length = 0;
await act('.k-more[data-digit="3"]');
await act('.dlg-box [data-act="dlg-menu"]');
await pick("הסרה מהמקש");
ok("הסרת תפריט עם מקשים שואלת קודם", confirmBox()?.open && confirmBox().textContent.includes("יוסרו גם 2"));
ok("המיקוד מתחיל על ביטול", focused === confirmBox().querySelector(".btn.plain"));
for (const f of confirmBox().querySelector(".btn.danger")._ls.click) f({});
await wait(0);
m = last("remove");
ok("הסרה", m.path === "3" && !dlgOpen());
const undoToast = toasts().at(-1);
ok("הודעה עם ביטול", undoToast.message === "המקש הוסר" && undoToast.action.text === "ביטול" && undoToast.duration === 6000);
undoToast.action.action();
await wait(0);
ok("ביטול שולח את האסימון", last("undo").args.token === "tok1" && toasts().at(-1).message === "המקש חזר");

await act('.k-more[data-digit="5"]');
await act('.dlg-box [data-act="dlg-menu"]');
await pick("הסרה מהמקש");
ok("מקש בודד מוסר בלי לשאול", !confirmBox() && last("remove").path === "5");
await act('.k-more[data-digit="6"]');
await type('input[name="name"]', "משהו");
await submitDlg();
ok("כתיבה אחרת סוגרת את הודעת הביטול", toasts().some((t) => t.duration === 0));

// --- גרירה ---
listeners.dragstart({ target: $('.key[data-digit="4"]'), dataTransfer: { setData() {} } });
listeners.dragover({ target: $('.key[data-digit="9"]'), preventDefault() {}, dataTransfer: {} });
ok("יעד הגרירה מודגש", $('.key[data-digit="9"]').classList.contains("over"));
await listeners.drop({ target: $('.key[data-digit="9"]'), preventDefault() {} });
ok("שחרור מעביר", last("move").path === "4" && last("move").args.to === "9");

// --- פתיח ---
const intro = $('input[name="intro"]');
intro.value = "ברוכים הבאים";
listeners.input({ target: intro });
ok("הפתיח מתעדכן חי, והשמירה נדלקת", $('[data-live="intro"]').textContent === "ברוכים הבאים" && !$("[data-intro-save]").disabled);
await listeners.submit({ preventDefault() {}, target: $('[data-form="intro"]') });
ok("שמירת פתיח", last("update").args.intro === "ברוכים הבאים" && last("update").path === "");

// --- לא משובצים ---
await act('[data-act="loose-menu"][data-id="x"]');
await pick("שיבוץ במקש");
await pick("מקש 8");
ok("שיבוץ פריט", last("move").args.id === "x" && last("move").args.to === "8");

// --- תפריט העמוד ובנייה מחדרים ---
await act('[data-act="page-menu"]');
await pick("בניית תפריט");
ok("בנייה: חדר מסומן", dlgOpen() && dlg().querySelector('input[name="room"]').checked);
await submitDlg();
ok("בנייה נשלחת", last("build").args.area_ids.join() === "kit" && !dlgOpen());

// --- רמת מכשיר ---
await act('.key[data-digit="1"]');
await act('.key[data-digit="5"]');
ok("ברמת מכשיר: רק יכולות שעוד לא שובצו",
  dlg().querySelectorAll('[data-act="add-part"]').length === 1 && !dlg().textContent.includes("יכולת חדשה") && !dlg().querySelector(".tag"));
ok("הכתבה לא מוצעת בקו בלי סטרימינג", !dlg().textContent.includes("הכתבה"));
await press(dlg().querySelector('[data-act="add-part"]'));
ok("הוספת יכולת", last("add").args.what === "capability" && last("add").args.ident === "turn_off" && last("add").path === "1/5");
await act('[data-act="edit-self"]');
ok("עריכת הרמה עצמה: בלי 'פתיחה'", dlgOpen() && !dlg().querySelector('[data-act="open-level"]'));
await act('.dlg-box [data-act="dlg-close"]');
await wait(0);
el.route = { prefix: "/ha-ivr", path: "/e" };
await wait(0);

// --- מסך צר ---
el.narrow = true;
ok("מסך צר: כפתור התפריט של HA", $('[data-act="sidebar"]') !== null);
await act('[data-act="sidebar"]');
ok("ומבקש את הסרגל", events.at(-1).type === "hass-toggle-menu");
el.narrow = false;

// --- אנגלית ---
const en = new Panel();
en.hass = { ...hass, language: "en", translationMetadata: { translations: { en: { isRTL: false } } } };
await wait(10);
const enText = en.shadowRoot.querySelector(".toolbar .title").textContent + en.shadowRoot.querySelector(".heard-meta").textContent + en.shadowRoot.querySelector(".pad").textContent.replace(/[֐-׿<>]+/g, "");
ok("ממשק באנגלית", en.shadowRoot.querySelector(".toolbar .title").textContent === "Phone menu");
ok("כיוון לפי השפה", en.getAttribute("dir") === "ltr" && en.shadowRoot.querySelector(".page").getAttribute("dir") === "ltr");
ok("אין עברית בטקסטים של הלוח באנגלית", !/[֐-׿]/.test(enText));
const keysHe = Object.keys(STRINGS.he).sort();
const keysEn = Object.keys(STRINGS.en).sort();
ok("אותם מפתחות בשתי השפות", keysHe.join() === keysEn.join());
const holes = (s) => (s.match(/\{\w+\}/g) || []).sort().join();
ok("ואותם placeholders", keysHe.every((k) => holes(STRINGS.he[k]) === holes(STRINGS.en[k])));
ok("כל שגיאה של השרת מתורגמת",
  ["no_entry", "invalid_path", "not_found", "taken", "full", "too_deep", "name_required", "undo_stale", "undo_expired"].every((c) => STRINGS.en[`err_${c}`]));

// --- שגיאת טעינה ---
const broken = new Panel();
broken.hass = { ...hass, callWS: async () => { throw { message: "x" }; } };
await wait(10);
ok("כשל טעינה: מצב ריק עם ניסיון חוזר", broken.shadowRoot.querySelector(".empty h2")?.textContent === "הלוח לא נטען"
  && broken.shadowRoot.querySelector('[data-act="retry"]'));
const none = new Panel();
none.hass = { ...hass, callWS: async () => ({ entries: [], blocked: [] }) };
await wait(10);
ok("בלי קו: מצב ריק עם הוספת קו", none.shadowRoot.querySelector(".empty h2")?.textContent === "עוד לא הוגדר קו");

ok("ואחרי הכול — עדיין אין img או script", !created.includes("img") && !created.includes("script") && innerHtmlWrites.length === 0);
void html;
void fs;
console.log(fails ? `FAIL — ${passes} עברו, ${fails} נכשלו` : `PASS — ${passes} עברו`);
process.exit(fails ? 1 : 0);
