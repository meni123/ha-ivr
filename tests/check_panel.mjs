// בדיקת עשן ללוח: המודולים רצים מול DOM מזויף ושרת מזויף, ונבדק שכל
// זרימה מצטיירת בלי חריגה ושהפקודות שנשלחות לשרת נכונות. ha-form של
// Home Assistant אינו כאן; הבדיקה שולחת את value-changed שהוא היה שולח.
//
// node tests/check_panel.mjs

// --- DOM קטן ---
const created = [];
let innerHtmlWrites = 0;
let focused = null;

class Text0 {
  constructor(t) { this.data = String(t); this.parentNode = null; }
  get textContent() { return this.data; }
}

const compound = (s) => {
  const tests = [];
  const re = /^(?:([a-zA-Z][\w-]*)|\.([\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]|:not\((.+?)\))/;
  while (s) {
    const m = s.match(re);
    if (!m) throw new Error(`בורר לא נתמך: ${s}`);
    if (m[1]) tests.push((e) => e.tagName === m[1].toLowerCase());
    else if (m[2]) tests.push((e) => e.classList.contains(m[2]));
    else if (m[5]) { const inner = compound(m[5]); tests.push((e) => !inner(e)); }
    else tests.push((e) => (m[4] === undefined ? e.hasAttribute(m[3]) : e.getAttribute(m[3]) === m[4]));
    s = s.slice(m[0].length);
  }
  return (e) => tests.every((t) => t(e));
};
const matches = (el, sel) => sel.split(",").some((group) => {
  const chain = group.trim().split(/\s+/).map(compound);
  if (!chain.at(-1)(el)) return false;
  let at = el.parentNode;
  for (let i = chain.length - 2; i >= 0; i -= 1) {
    while (at instanceof El && !chain[i](at)) at = at.parentNode;
    if (!(at instanceof El)) return false;
    at = at.parentNode;
  }
  return true;
});

class El {
  constructor(tag) {
    this.tagName = tag.toLowerCase();
    this.attrs = new Map();
    this.childNodes = [];
    this.parentNode = null;
    this.listeners = {};
    created.push(this.tagName);
  }
  setAttribute(n, v) { this.attrs.set(n, String(v)); }
  getAttribute(n) { return this.attrs.has(n) ? this.attrs.get(n) : null; }
  hasAttribute(n) { return this.attrs.has(n); }
  removeAttribute(n) { this.attrs.delete(n); }
  get className() { return this.getAttribute("class") || ""; }
  set className(v) { this.setAttribute("class", v); }
  get classList() {
    const list = () => this.className.split(/\s+/).filter(Boolean);
    return {
      contains: (c) => list().includes(c),
      toggle: (c, on) => {
        const next = on ?? !list().includes(c);
        this.className = (next ? [...new Set([...list(), c])] : list().filter((x) => x !== c)).join(" ");
      },
    };
  }
  get dataset() {
    const out = {};
    for (const [k, v] of this.attrs) if (k.startsWith("data-")) out[k.slice(5)] = v;
    return out;
  }
  append(...kids) {
    for (let kid of kids) {
      if (typeof kid !== "object") kid = new Text0(kid);
      if (kid.parentNode) kid.parentNode.childNodes.splice(kid.parentNode.childNodes.indexOf(kid), 1);
      kid.parentNode = this;
      this.childNodes.push(kid);
    }
  }
  replaceChildren(...kids) {
    for (const c of this.childNodes) c.parentNode = null;
    this.childNodes = [];
    this.append(...kids);
  }
  remove() {
    if (this.parentNode) this.parentNode.childNodes.splice(this.parentNode.childNodes.indexOf(this), 1);
    this.parentNode = null;
  }
  get textContent() { return this.childNodes.map((c) => c.textContent).join(""); }
  set innerHTML(_v) { innerHtmlWrites += 1; }
  get disabled() { return this.hasAttribute("disabled") || Boolean(this._disabled); }
  set disabled(v) { this._disabled = Boolean(v); }
  get open() { return this.hasAttribute("open"); }
  focus() { focused = this; }
  addEventListener(type, f) { (this.listeners[type] ||= []).push(f); }
  dispatch(type, extra = {}) {
    const ev = { type, target: this, currentTarget: this, preventDefault() {}, ...extra };
    for (const f of this.listeners[type] || []) f(ev);
  }
  click() { this.dispatch("click"); }
  querySelectorAll(sel) {
    const out = [];
    const walk = (n) => { for (const c of n.childNodes) if (c instanceof El) { if (matches(c, sel)) out.push(c); walk(c); } };
    walk(this);
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  showModal() { this.setAttribute("open", ""); }
  close(value = "") { this.returnValue = value; this.removeAttribute("open"); this.dispatch("close"); }
}

const events = [];
globalThis.document = { createElement: (t) => new El(t), createTextNode: (t) => new Text0(t) };
globalThis.HTMLElement = class {
  attachShadow() { this.shadowRoot = new El("#shadow"); return this.shadowRoot; }
  dispatchEvent(ev) { events.push(ev); }
  setAttribute(n, v) { (this._attrs ||= {})[n] = v; }
  getAttribute(n) { return (this._attrs || {})[n] ?? null; }
};
const defs = {};
globalThis.customElements = { get: (n) => defs[n], define: (n, c) => { defs[n] = c; } };
globalThis.localStorage = { getItem: () => null, setItem() {} };
globalThis.location = { pathname: "/ha-ivr" };
globalThis.history = {
  pushState(_s, _t, url) { location.pathname = url; },
  replaceState(_s, _t, url) { location.pathname = url; },
};
globalThis.window = { dispatchEvent(ev) { events.push(ev); }, open() {} };
globalThis.CustomEvent = class { constructor(t, o = {}) { this.type = t; this.detail = o.detail; } };

const { HaIvrPanel: Panel } = await import(new URL("../custom_components/ha_ivr/frontend/panel.js", import.meta.url));
const { STRINGS } = await import(new URL("../custom_components/ha_ivr/frontend/strings.js", import.meta.url));

// --- השרת המזויף ---
const EVIL = "<img src=x onerror=alert(1)>";
const key = (path, kind, extra = {}) => ({ path, digit: path.slice(-1), enter: false, silent: false, label: "", kind, name: kind, count: 0, ...extra });
const empty9 = () => Object.fromEntries("123456789".split("").map((d) => [d, null]));
const levels = {
  "": {
    path: "", kind: "menu", self: null, targets: [{ path: "", name: "" }, { path: "3", name: "דלת" }],
    crumbs: [{ path: "", name: "ראשי" }],
    keys: {
      ...empty9(),
      1: key("1", "device", { enter: true, count: 5, name: "מזגן", entity_id: "climate.ac" }),
      2: key("2", "action", { fixed: true, does: "הרצה עכשיו", entity_id: "automation.a", name: EVIL }),
      3: key("3", "submenu", { enter: true, count: 2, name: "דלת" }),
      4: key("4", "goto", { target: "200", name: "משרד" }),
      7: key("7", "group", { enter: true, missing: true, name: "אורות" }),
    },
    heard: ["שלום", "לתפריט מזגן הקש 1", EVIL], intro: "שלום", addable: null, can_add: true, can_nest: true,
    loose: [{ id: "x", title: "אבוד" }],
  },
  "1": {
    path: "1", kind: "plan", self: key("1", "device", { enter: true, name: "מזגן", entity_id: "climate.ac" }),
    targets: [], crumbs: [{ path: "", name: "ראשי" }, { path: "1", name: "מזגן" }],
    keys: { ...empty9(), 1: key("1/1", "cap", { cap: "simple", name: "הדלקה" }), 2: key("1/2", "cap", { cap: "choice", enter: true, count: 3 }) },
    heard: ["להדלקה הקש 1"], intro: null, can_add: true, can_nest: true, loose: [],
    addable: [{ ident: "turn_off", kind: "simple", label: "כיבוי" }, { ident: "preset", kind: "fixed", label: "מצב", needs_fixed: true }],
  },
};
const sent = [];
const cap = (ident, kind, label, extra = {}) => ({ ident, kind, label, name: label, action: ident, options: [], code: null, needs_fixed: false, checked: true, ...extra });
const hass = {
  language: "he",
  states: {
    "climate.ac": { entity_id: "climate.ac", state: "cool", attributes: { friendly_name: "מזגן" } },
    "automation.a": { entity_id: "automation.a", state: "on", attributes: {} },
    "light.a": { entity_id: "light.a", state: "on", attributes: {} },
    "lock.d": { entity_id: "lock.d", state: "locked", attributes: {} },
  },
  entities: { "sensor.line": { entity_id: "sensor.line", platform: "ha_ivr" } },
  formatEntityState: (s) => ({ cool: "קירור", on: "מופעלת" })[s.state] || s.state,
  callWS: async (m) => {
    sent.push(m);
    if (m.op === "entries") return { entries: [{ entry_id: "e", title: "קו", extensions: true, goto_hint: "רמז", alerts: true }], blocked: ["lock"] };
    if (m.op === "capabilities") return { entity_id: m.args.entity_id, name: "אוטומציה", fixed: true, capabilities: [
      cap("trigger", "simple", "הרצה עכשיו"), cap("turn_off", "simple", "השבתת האוטומציה"),
      cap("set_mode", "choice", "מצב", { options: [{ value: "a", label: "א" }, { value: "b", label: "ב" }] }),
      cap("set_text", "fixed", "טקסט", { needs_fixed: true, checked: false })] };
    if (m.op === "actions") return { entity_id: m.args.entity_id, name: "אוטומציה", actions: [{ action: "trigger", label: "הרצה עכשיו", fields: [
      { name: "skip_condition", label: "דילוג על תנאים", required: false, selector: { boolean: {} } }] }] };
    if (m.op === "place") return { name: "כל הבית", target: m.args.target, kinds: [{ domain: "light", name: "אורות", count: 2 }],
      members: [{ entity_id: "light.a", name: "א", domain: "light" }, { entity_id: "light.b", name: "ב", domain: "light" }] };
    if (m.op === "place_functions") return { kinds: [{ domain: "light", name: "אורות", capabilities: [{ ident: "turn_on", label: "הדלקה" }] }] };
    if (m.op === "fixed") return { values: { skip_condition: false }, action: { label: "הרצה עכשיו", fields: [
      { name: "skip_condition", label: "דילוג על תנאים", required: false, selector: { boolean: {} } }] } };
    if (m.op === "rooms") return { rooms: [{ area_id: "kit", name: "מטבח", kinds: [{ name: "אורות" }] }] };
    if (m.op === "level") return levels[m.path] || levels[""];
    const out = levels[m.view] || levels[""];
    return m.op === "remove" ? { ...out, undo: "tok1" } : out;
  },
};

let fails = 0;
let passes = 0;
const ok = (name, cond) => { if (cond) passes += 1; else { fails += 1; console.log("FAIL", name); } };
const wait = (ms = 0) => new Promise((r) => setTimeout(r, ms));
const last = (op) => [...sent].reverse().find((m) => m.op === op);

const el = new Panel();
el.route = { prefix: "/ha-ivr", path: "" };
el.hass = hass;
await wait(10);
const root = el.shadowRoot;
const $ = (sel) => root.querySelector(sel);
const $$ = (sel) => root.querySelectorAll(sel);
const dialog = () => $("dialog");
const form = () => dialog().querySelector("ha-form");
const change = async (value) => { form().dispatch("value-changed", { detail: { value } }); await wait(); };
const primary = () => dialog().querySelectorAll("footer button").at(-1);
const rowWith = (text) => dialog().querySelectorAll(".row").find((r) => r.textContent.includes(text));
const press = async (node) => { if (!node) throw new Error("אין כפתור"); node.click(); await wait(5); };

// --- הלוח ---
ok("כניסה בלי קו בכתובת משלימה אותו", location.pathname === "/ha-ivr/e");
ok("12 מקשים", $$(".pad .key").length === 12);
ok("הספרות בסדר טלפון", $$(".pad .k-digit").map((d) => d.textContent).join("") === "123456789*0#");
ok("מכשיר: מצב חי ומספר פעולות", $('.key[data-digit="1"]').querySelector(".k-sub").textContent === "קירור · 5 פעולות");
ok("קבוצה ריקה מסומנת", $('.key[data-digit="7"]').querySelector(".k-sub").textContent === "אין מכשירים");
ok("אייקון המצב של HA במקש של ישות", $('.key[data-digit="1"]').querySelector("ha-state-icon") !== null);
ok("שם זדוני הוא טקסט בלבד", !created.includes("img") && !created.includes("script") && innerHtmlWrites === 0);
ok("המתקשר שומע", $$(".heard li").length === 3);
ok("פתיח ב-ha-form", $$(".card ha-form").length === 1);
ok("* ו-0 מושבתים בשורש", $('.key[data-digit="*"]').getAttribute("aria-disabled") === "true");

// --- הוספה: מכשיר ---
await press($('.key[data-digit="5"]'));
ok("מקש ריק פותח הוספה", dialog().open && dialog().querySelector("h2").textContent === "הוספה למקש 5");
ok("סוגי ההוספה לפי הקו (בלי עוזר)", dialog().querySelectorAll(".row").length === 5);
await press(rowWith("מכשיר"));
const picker = form().schema[0].selector.entity;
ok("בורר הישות של HA, בלי דומיין חסום ובלי הישויות של הקו",
  !picker.filter[0].domain.includes("lock") && picker.filter[0].domain.includes("light") && picker.exclude_entities.includes("sensor.line"));
await change({ entity_id: "automation.a" });
await wait(5);
ok("בחירת ישות טוענת את היכולות", last("capabilities").args.entity_id === "automation.a");
ok("רשימת סימון של HA, בלי מה שדורש ערך קבוע",
  form().schema[0].selector.select.multiple && form().schema[0].selector.select.options.map((o) => o.value).join() === "trigger,turn_off,set_mode");
await change({ idents: ["trigger"], name: "" });
ok("בלי בחירה עם ערכים — הכפתור הוא הוספה", primary().textContent === "הוספה");
await press(primary());
ok("הוספת מכשיר", last("add").args.what === "device" && last("add").args.idents.join() === "trigger" && last("add").path === "5");
ok("והחלון נסגר", !dialog().open);

// --- הוספה: בחירה עם ערכים ---
await press($('.key[data-digit="6"]'));
await press(rowWith("מכשיר"));
await change({ entity_id: "automation.a" });
await wait(5);
await change({ idents: ["trigger", "set_mode"], name: "" });
ok("בחירה עם ערכים — המשך", primary().textContent === "המשך");
await press(primary());
await change({ "opt:set_mode": ["b"] });
await press(primary());
ok("הערכים שנבחרו נשלחים", JSON.stringify(last("add").args.options) === JSON.stringify({ set_mode: ["b"] }));

// --- הוספה: ערך קבוע ---
await press($('.key[data-digit="8"]'));
await press(rowWith("מכשיר"));
await change({ entity_id: "automation.a" });
await wait(5);
await press(rowWith("ערך קבוע"));
ok("פעולות עם ערך", last("actions").args.entity_id === "automation.a");
await press(rowWith("הרצה עכשיו"));
ok("השדות של הפעולה הם הבוררים של HA", form().schema[0].selector.boolean !== undefined);
await change({ skip_condition: false, __name: "" });
await press(primary());
ok("ערך קבוע נשלח, והשם הריק אינו בנתונים",
  last("add").args.what === "action" && last("add").args.action === "trigger"
  && JSON.stringify(last("add").args.data) === JSON.stringify({ skip_condition: false }));

// --- הוספה: חדר ---
await press($('.key[data-digit="9"]'));
await press(rowWith("חדר"));
ok("בוררי חדר, קומה ותווית של HA", form().schema.map((s) => s.name).join() === "whole,area_id,floor_id,label_id");
await change({ whole: true });
ok("כל הבית מסתיר את הבוררים", form().schema.length === 1);
await press(primary());
ok("המקום נטען", JSON.stringify(last("place").args.target) === "{}");
await change({ domains: ["light"], "m:light": ["light.a"] });
await press(primary());
ok("מה שלא סומן הוא החרגה", JSON.stringify(last("place_functions").args.exclude) === JSON.stringify(["light.b"]));
await press(primary());
ok("חדר נוסף", last("add").args.what === "room" && last("add").args.idents.light.join() === "turn_on");

// --- הוספה: תפריט והעברה ---
await press($('.key[data-digit="9"]'));
await press(rowWith("תפריט נוסף"));
await press(primary());
ok("תפריט בלי שם נדחה", dialog().querySelector(".alert").textContent === "חסר שם");
await change({ name: "קומה" });
await press(primary());
ok("תפריט נוסף ונכנסים אליו", last("add").args.what === "submenu" && last("add").view === "9");
await press($('.key[data-digit="9"]'));
await press(rowWith("העברת שיחה"));
await change({ target: "5/2", name: "" });
await press(primary());
ok("העברה", last("add").args.what === "goto" && last("add").args.target === "5/2");

// --- מקש קיים ---
await press($('.key[data-digit="2"]'));
await wait(5);
ok("ערך קבוע נטען לעריכה", form().schema.map((s) => s.name).join() === "name,skip_condition" && form().data.skip_condition === false);
ok("שמירה כבויה בלי שינוי", primary().disabled);
await change({ ...form().data, skip_condition: true });
ok("ונדלקת אחרי שינוי", !primary().disabled);
await press(primary());
ok("עדכון שולח רק את מה שהשתנה", JSON.stringify(last("update").args) === JSON.stringify({ values: { skip_condition: true } }));
await press($('.key[data-digit="4"]'));
await press(rowWith("העברה"));
await press(rowWith("מקש 5"));
ok("העברה למקש", last("move").path === "4" && last("move").args.to === "5");
await press($('.key[data-digit="4"]'));
await press(rowWith("הסרה"));
const toast = events.filter((e) => e.type === "hass-notification").at(-1).detail;
ok("הסרה עם ביטול", last("remove").path === "4" && toast.action.text === "ביטול פעולה");
await toast.action.action();
await wait(5);
ok("והביטול נשלח עם האסימון", last("undo").args.token === "tok1");

// --- רמת מכשיר ---
await press($('.key[data-digit="1"]'));
await wait(5);
ok("מקש שנכנסים בו פותח את הרמה שלו", last("level").path === "1" && location.pathname === "/ha-ivr/e/1");
await press($('.key[data-digit="5"]'));
ok("ברמת מכשיר: רק יכולות שאפשר להקיש", dialog().querySelectorAll(".row").length === 1);
await press(rowWith("כיבוי"));
ok("הוספת יכולת", last("add").args.what === "capability" && last("add").path === "1/5");

// --- אנגלית ושפות ---
const en = new Panel();
en.hass = { ...hass, language: "en", translationMetadata: { translations: { en: { isRTL: false } } } };
await wait(10);
ok("ממשק באנגלית, משמאל לימין", en.shadowRoot.querySelector(".toolbar h1").textContent === "Phone menu" && en.getAttribute("dir") === "ltr");
const keysHe = Object.keys(STRINGS.he).sort().join();
ok("אותם מפתחות בשתי השפות", keysHe === Object.keys(STRINGS.en).sort().join());
const holes = (s) => (s.match(/\{\w+\}/g) || []).sort().join();
ok("ואותם משתנים", Object.keys(STRINGS.he).every((k) => holes(STRINGS.he[k]) === holes(STRINGS.en[k])));

// --- כשל ---
const broken = new Panel();
broken.hass = { ...hass, callWS: async () => { throw new Error("x"); } };
await wait(10);
ok("כשל טעינה: מסך עם ניסיון חוזר", broken.shadowRoot.querySelector(".empty h2").textContent === "הלוח לא נטען");

ok("ואחרי הכול — אין img, script או innerHTML", !created.includes("img") && !created.includes("script") && innerHtmlWrites === 0);
console.log(fails ? `FAIL — ${passes} עברו, ${fails} נכשלו` : `PASS — ${passes} עברו`);
process.exit(fails ? 1 : 0);
