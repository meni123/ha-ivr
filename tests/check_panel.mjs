// בדיקת עשן: מריצים את העמוד מול DOM מזויף ושרת מזויף, ומוודאים שכל
// מצב מצטייר בלי חריגה ושהפקודות שנשלחות נכונות.
import fs from "node:fs";
const src = fs.readFileSync(
  new URL("../custom_components/ha_ivr/frontend/panel.js", import.meta.url), "utf8",
);
const listeners = {};
class Shadow {
  constructor() { this.html = ""; }
  addEventListener(n, f) { listeners[n] = f; }
  set innerHTML(v) { this.html = v; }
  get innerHTML() { return this.html; }
  querySelector() { return null; }
  getElementById() { return null; }
}
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

const key = (path, kind, extra = {}) => ({ path, digit: path.slice(-1), enter: false, silent: false, label: "", detail: "", kind, name: kind, ...extra });
const levels = {
  "": { entry_id: "e", path: "", kind: "menu", self: null, crumbs: [{ path: "", name: "ראשי" }],
    keys: { 1: key("1", "device", { enter: true, domain: "climate", detail: "5 פעולות", name: "<מזגן>" }),
      2: key("2", "action", { domain: "button", detail: "פעמון" }), 3: key("3", "submenu", { enter: true, silent: true, detail: "ריק" }),
      4: key("4", "goto", { target: "200", detail: "200" }), 5: key("5", "assistant"), 6: key("6", "alerts"),
      7: key("7", "group", { enter: true, domain: "light", missing: true }), 8: null, 9: null },
    heard: ["לתפריט מזגן הקש 1"], silent: false, intro: "", addable: null, can_add: true, can_nest: true,
    loose: [{ id: "x", title: "אבוד" }] },
  "1": { entry_id: "e", path: "1", kind: "plan", self: key("1", "device", { enter: true, name: "מזגן" }),
    crumbs: [{ path: "", name: "ראשי" }, { path: "1", name: "מזגן" }],
    keys: { 1: key("1/1", "cap", { cap: "simple", ident: "turn_on", label: "הדלקה" }), 2: key("1/2", "cap", { cap: "choice", enter: true }),
      3: key("1/3", "cap", { cap: "number", detail: "הקשת מספר" }), 4: key("1/4", "cap", { cap: "status" }), 5: null, 6: null, 7: null, 8: null, 9: null },
    heard: ["להדלקה הקש 1"], silent: false, intro: null, addable: [{ ident: "turn_off", label: "כיבוי" }], can_add: true, can_nest: true, loose: [] },
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
const sent = [];
const hass = {
  states: { "light.a": { attributes: { friendly_name: "מנורה" } }, "sensor.t": { attributes: {} },
    "lock.d": { attributes: {} }, "switch.h": { attributes: { friendly_name: "נסתר" } } },
  entities: { "light.a": { area_id: "kit" }, "switch.h": { hidden: true } },
  devices: {}, areas: { kit: { name: "מטבח" } },
  callWS: async (m) => {
    sent.push(m);
    if (m.op === "entries") return { entries: [{ entry_id: "e", title: "קו", goto: true, extensions: true, goto_hint: "רמז", assistant: true, assistant_target: m.noTarget ? "" : "ha-assist", alerts: true }, { entry_id: "f", title: "קו ב" }], blocked: ["lock"] };
    if (m.op === "rooms") return { rooms };
    if (m.op === "capabilities") return { entity_id: m.args.entity_id, name: "מנורה", capabilities: [{ ident: "turn_on", label: "הדלקה", checked: true }] };
    if (m.op === "level") return levels[m.path];
    if (m.fail) throw { message: "נכשל" };
    return levels[m.view] || levels[""];
  },
};
let fails = 0;
const ok = (name, cond) => { if (!cond) { fails += 1; console.log("FAIL", name); } };
const el = new Panel();
el.narrow = false;
el.hass = hass;
await new Promise((r) => setTimeout(r, 20));
const html = () => el.shadowRoot.html;
const click = async (act, data = {}) => listeners.click({ target: { closest: () => ({ dataset: { act, ...data } }) } });
const submit = async (form, fields, data = {}) => listeners.submit({ preventDefault() {}, target: { dataset: { form, ...data }, fields } });
const last = () => sent[sent.length - 1];

ok("נטען", html().includes("המתקשר שומע") && html().includes("לתפריט מזגן הקש 1"));
ok("שם נמלט", html().includes("&lt;מזגן&gt;") && !html().includes("<מזגן>"));
ok("לשוניות", html().includes("קו ב"));
ok("פריט בלי מקש", html().includes("אבוד"));
await click("empty", { digit: "8" });
ok("הוספה", html().includes("מה יקרה כשמקישים 8?") && html().includes("לדבר עם העוזר הקולי") && html().includes("התראות אחרונות"));
await click("add-step", { step: "device" });
ok("בורר: רק מה שמפעילים", html().includes("מנורה") && !html().includes("sensor.t") && !html().includes("lock.d") && !html().includes("נסתר"));
listeners.input({ target: { matches: () => true, value: "sensor" } });
ok("חיפוש מוצא חיישן", el._devicesHtml("sensor").includes("sensor.t") && !el._devicesHtml("lock").includes("lock.d"));
await click("add-device", { id: "light.a" });
ok("יכולות", html().includes("מה המתקשר יוכל לעשות") && html().includes("הוספה למקש 8"));
await submit("device", { cap: ["turn_on"], name: " אור " });
ok("מכשיר נשלח", last().op === "add" && last().path === "8" && last().args.what === "device" && last().args.entity_id === "light.a" && last().args.name === "אור" && last().view === "");
await click("empty", { digit: "9" });
await click("add-step", { step: "room" });
ok("חדרים", html().includes("איזה חדר?") && html().includes("כל הבית"));
await click("add-room", { index: "0" });
await submit("room", { kind: ["light", "switch"], name: "" });
ok("חדר נשלח", last().args.what === "room" && last().args.area_id === "kit" && last().args.domains.length === 2);
await click("empty", { digit: "9" });
await click("add-step", { step: "submenu" });
await submit("submenu", { name: "גינה" });
ok("תפריט נשלח ונכנסים אליו", last().args.what === "submenu" && last().view === "9");
await click("empty", { digit: "9" });
await click("add-assistant");
ok("עוזר מיד", last().args.what === "assistant" && last().path === "9");
await click("empty", { digit: "9" });
await click("add-step", { step: "goto" });
ok("טופס מעבר", html().includes("לאן עוברים") && html().includes("רמז"));
await submit("goto", { target: "200", name: "משרד" });
ok("מעבר נשלח", last().args.what === "goto" && last().args.target === "200");
await click("empty", { digit: "9" });
await click("add-alerts");
ok("התראות נשלח", last().args.what === "alerts");
await click("key", { digit: "2" });
ok("פרטי מקש", html().includes("פעולה אחת במכשיר «פעמון»") && html().includes("העברה למקש אחר"));
await submit("rename", { name: "צלצול" }, { path: "2" });
ok("שינוי שם", last().op === "rename" && last().path === "2" && last().args.name === "צלצול");
await click("key", { digit: "4" });
ok("יעד מעבר", html().includes('value="200"'));
await submit("target", { target: "300" }, { path: "4" });
ok("יעד נשלח", last().op === "update" && last().args.target === "300");
await click("key", { digit: "4" });
const n = sent.length;
await click("remove", { path: "4", sure: 'remove:data-path="4"' });
ok("מחיקה שואלת קודם", sent.length === n && html().includes("להסיר?"));
await click("remove", { path: "4", sure: 'remove:data-path="4"' });
ok("ואז מוחקת", last().op === "remove" && last().path === "4" && last().view === "");
await click("key", { digit: "2" });
await click("carry", { path: "2", name: "פעמון" });
ok("מצב העברה", html().includes("מעבירים את «פעמון»") && html().includes("לכאן"));
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
ok("כניסה למכשיר", el._level.path === "1" && html().includes("מקש 1") && html().includes("לתפריט הראשי") === false);
await click("empty", { digit: "5" });
ok("פעולות להוספה", html().includes("איזו פעולה להוסיף?") && html().includes("כיבוי"));
await click("add-part", { ident: "turn_off", value: "" });
ok("יכולת נשלחת", last().args.what === "capability" && last().args.ident === "turn_off" && last().path === "1/5");
await click("key", { digit: "1" });
await click("carry", { path: "1/1", name: "הדלקה" });
ok("פעולה נשארת ברמה שלה", el._carry.only === "1");
await click("up");
ok("יציאה מהרמה מבטלת", el._level.path === "" && !el._carry);
await click("key", { digit: "1" });
await click("key", { digit: "2" });
ok("רמת אפשרויות", el._level.path === "1/2" && html().includes("לתפריט הראשי") && html().includes("שם הפעולה"));
await click("empty", { digit: "5" });
ok("אין מה להוסיף", el._toast === "אין עוד מה להוסיף כאן.");
await click("carry", { path: "1/2", name: "מצב", up: "1" });
ok("העברת הרמה עצמה", el._level.path === "1" && el._carry.path === "1/2" && el._carry.only === "1");
await click("carry-cancel");
await click("remove", { path: "1", sure: "r" });
await click("remove", { path: "1", sure: "r" });
ok("מחיקת הרמה מחזירה למעלה", last().op === "remove" && last().view === "");
await click("open", { path: "3" });
ok("תפריט ריק מזהיר", html().includes("אין כאן עדיין מקשים"));
await submit("intro", { intro: "שלום" });
ok("פתיחה נשלחת", last().op === "update" && last().path === "3" && last().args.intro === "שלום");
await click("open", { path: "" });
await click("build");
ok("בנייה מהחדרים", html().includes("תפריט מהחדרים בבית") && html().includes("יש 2 מקשים פנויים"));
await submit("build", { room: ["0", "1"] });
ok("בנייה נשלחת", last().op === "build" && last().args.area_ids.join("|") === "kit|");
await click("entry", { id: "f" });
ok("מעבר קו", last().op === "level" && last().entry_id === "f");
// גרירה
el._level = levels[""];
listeners.dragstart({ target: { closest: () => ({ dataset: { digit: "2" } }) }, dataTransfer: { setData() {} } });
let prevented = false;
const over = { target: { closest: () => ({ dataset: { drop: "8" }, classList: { add() {}, remove() {} } }) }, dataTransfer: {}, preventDefault() { prevented = true; } };
listeners.dragover(over);
await listeners.drop(over);
ok("גרירה", prevented && last().op === "move" && last().path === "2" && last().args.to === "8");
// רוחב צר, וכשל
el.narrow = true;
ok("כפתור תפריט בצר", html().includes('data-act="menu"'));
hass.callWS = async () => { throw { message: "נכשל" }; };
await click("open", { path: "3" });
ok("שגיאה מוצגת", el._toast === "נכשל" && el._busy === 0);
console.log(fails ? `FAIL — ${fails} נכשלו` : "PASS — לוח המקשים מצטייר ושולח את הפקודות הנכונות");
process.exit(fails ? 1 : 0);
