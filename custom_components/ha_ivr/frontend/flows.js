// מה שקורה בתוך הדיאלוג: אשף ההוספה, דיאלוג המקש, ובניית תפריט מחדרים.
//
// כל flow מחזיק את המצב שלו ומחזיר תצוגה (view) שהדיאלוג מצייר. "חזרה"
// היא מחסנית של צעדים: תמיד חוזרים בדיוק לצעד הקודם, עם מה שסומן בו.
// השרת מחליט אם משהו מותר; כאן רק אוספים את מה שהמשתמש בחר.

import { CAP_GROUPS, DOMAIN_ICONS, auto, btn, capGroup, cls, h, icon, iconBtn, ltr } from "./dom.js";
import { counted } from "./strings.js";

const MAX_KEYS = 9;
// הקטעים של הבורר, לפי הסדר של ha-target-picker.
const PICKER_SECTIONS = ["entity", "device", "area", "label"];

// ------------------------------------------------------------------
// אבני בניין של טופס ורשימה
// ------------------------------------------------------------------

/** שדה עם תווית גלויה, עזרה מתחת, ושגיאה שמחליפה את העזרה. */
export const field = (label, input, { help = "", error = "", required = false, t } = {}) => h("label", { class: cls("field", error && "bad") },
  h("span", { class: "lbl" }, label, required && t ? h("span", { class: "req" }, ` · ${t("required")}`) : null),
  input,
  error ? h("p", { class: "err", role: "alert" }, error) : help ? h("p", { class: "t-help" }, help) : null);

/** שורה ברשימה: אייקון, כותרת, שורת משנה, ושברון כשהיא פותחת עוד צעד. */
export const item = (attrs, iconName, title, sub, { chev = false, tag = null } = {}) => btn("item", attrs,
  iconName ? icon(iconName) : null,
  h("span", { class: "txt" }, h("span", null, title), sub ? h("small", null, sub) : null),
  tag,
  chev ? icon("chevron-right", "chev") : null);

/** שורה עם תיבת סימון. */
export const check = (name, value, title, { checked = false, sub = null, group = null } = {}) => h("label", { class: "item" },
  h("input", { type: "checkbox", name, value, checked: Boolean(checked), "data-group": group }),
  h("span", { class: "txt" }, h("span", null, title), sub ? h("small", null, sub) : null));

/** קבוצה בתוך רשימה: כותרת, "סימון הכול / ביטול הכול", ושורות. */
export const section = (title, rows, { iconName = null, bulk = null, t } = {}) => {
  const list = rows.flat(Infinity).filter(Boolean);
  if (!list.length) return null;
  let tools = null;
  if (bulk && t && list.length >= (bulk.least || 3)) {
    const attrs = { "data-act": "check-all", "data-name": bulk.name, "data-group": bulk.group || null };
    tools = h("span", null,
      btn("link", { ...attrs, "data-on": "1" }, t("select_all")),
      btn("link", attrs, t("select_none")));
  }
  return h("section", { class: "section" },
    h("div", { class: "section-head" }, iconName ? icon(iconName) : null, h("h3", { class: "grow" }, title), tools),
    h("div", { class: "list" }, list));
};

const submit = (label, busy, attrs = {}) => h("button", {
  type: "submit", class: cls("btn accent", busy && "busy"), disabled: busy, ...attrs,
}, label);
const cancel = (t) => btn("btn plain", { "data-act": "dlg-close" }, t("cancel"));

/** הערה קצרה ליכולת: כמה אפשרויות, איזה טווח, איך מקישים קוד. */
export const capNote = (t, c) => {
  if (c.needs_fixed || c.kind === "fixed") return t("note_fixed");
  if (c.code) {
    if (c.code.end) return t("note_code_end");
    if (c.code.width) return t("note_code_width", { n: c.code.width });
    return t("note_code");
  }
  if (c.kind === "choice") return t("options_count", { n: (c.options || []).length });
  if (c.kind === "number" && c.min !== null && c.min !== undefined && c.max !== null && c.max !== undefined) {
    return [ltr(c.min), " – ", ltr(c.max)];
  }
  if (c.kind === "status") return t("note_status");
  if (c.kind === "text") return c.max_length ? t("note_text_max", { n: c.max_length }) : t("note_text");
  return "";
};

/** שדה של פעולה עם ערך קבוע. השמות מקבלים קידומת, כדי לא להתנגש בשם המקש. */
export const actionField = (t, spec, value) => {
  const name = `v_${spec.name}`;
  const given = value === undefined || value === null ? "" : String(value);
  if (spec.type === "boolean") {
    return h("label", { class: "item" },
      h("input", { type: "checkbox", name, checked: Boolean(value) }),
      h("span", { class: "txt" }, h("span", null, spec.label)));
  }
  let input;
  let help = "";
  if (spec.type === "select") {
    input = h("select", { name }, h("option", { value: "" }),
      (spec.options || []).map((o) => h("option", { value: o.value, selected: o.value === given }, o.label)));
  } else if (spec.type === "number") {
    const bounded = spec.min !== null && spec.max !== null && spec.max < 1e6;
    if (bounded) help = [ltr(spec.min), " – ", ltr(spec.max), spec.unit ? ` ${spec.unit}` : ""];
    input = h("input", {
      type: "number", name, dir: "ltr", value: given, inputmode: "decimal",
      min: spec.min !== null ? spec.min : null,
      max: spec.max !== null && spec.max < 1e6 ? spec.max : null,
      step: spec.step || "any",
    });
  } else {
    input = h("input", { type: "text", name, value: given });
  }
  return field(spec.label, input, { help, required: spec.required, t });
};

/** הערכים שמולאו בטופס של פעולה: שדה ריק אינו נשלח. */
export const formValues = (fields, data) => {
  const values = {};
  for (const spec of fields) {
    const raw = data.get(`v_${spec.name}`);
    if (spec.type === "boolean") {
      if (raw) values[spec.name] = true;
    } else if (String(raw || "").trim() !== "") {
      values[spec.name] = String(raw).trim();
    }
  }
  return values;
};

const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

// ------------------------------------------------------------------
// הבסיס
// ------------------------------------------------------------------

class Flow {
  constructor(ctx) {
    this.ctx = ctx;
    this.t = ctx.t;
    this.error = "";
    this.busy = false;
    this.stack = [];
  }

  get step() {
    return this.stack[this.stack.length - 1];
  }

  push(step) {
    this.stack.push(step);
    this.error = "";
    this.ctx.repaint({ refocus: true });
  }

  back() {
    if (this.stack.length < 2) return;
    this.stack.pop();
    this.error = "";
    this.ctx.repaint({ refocus: true });
  }

  dirty() {
    return false;
  }

  /** פעולה מול השרת: אחת בכל פעם, ושגיאה מוצגת בראש הדיאלוג. */
  async run(work) {
    if (this.busy) return undefined;
    this.busy = true;
    this.error = "";
    this.ctx.repaint();
    try {
      return await work();
    } catch (err) {
      this.error = this.ctx.errorText(err);
      return undefined;
    } finally {
      this.busy = false;
      if (this.ctx.flow === this) this.ctx.repaint({ refocus: Boolean(this.error) });
    }
  }

  input() {}
}

// ------------------------------------------------------------------
// הוספה
// ------------------------------------------------------------------

export class AddFlow extends Flow {
  constructor(ctx, digit, { replace = false } = {}) {
    super(ctx);
    this.digit = digit;
    this.path = ctx.path(digit);
    this.replace = replace;
    const kind = ctx.level.kind;
    if (kind === "plan" || kind === "options") this.stack = [{ id: "parts" }];
    else if (replace) this.stack = [{ id: "device", query: "", filter: "entity" }];
    else this.stack = [{ id: "what" }];
  }

  // כמה צעדים בענף הזה, לפי מה שכבר ידוע.
  _total() {
    const n = this.stack.length;
    const step = this.step;
    if (step.id === "device") return n + 1;
    if (step.id === "caps") return n + (this._choices(this._checked() || step.idents || []).length ? 1 : 0);
    if (step.id === "place") return n + 2;
    if (step.id === "contents") return n + 1;
    return n;
  }

  _subtitle(name) {
    const step = this.step;
    if (step.id === "what" || step.id === "parts") return "";
    const n = this.stack.length;
    return `${this.t("step_of", { n, of: Math.max(n, this._total()) })} · ${name}`;
  }

  view() {
    const t = this.t;
    const step = this.step;
    const base = {
      title: this.replace ? t("replace") : t("add_title", { digit: this.digit }),
      badge: this.digit,
      back: this.stack.length > 1,
      error: this.error,
    };
    const views = {
      what: () => this._what(),
      parts: () => this._parts(),
      device: () => this._device(),
      caps: () => this._caps(),
      options: () => this._options(),
      values: () => this._values(),
      place: () => this._place(),
      contents: () => this._contents(),
      functions: () => this._functions(),
      submenu: () => this._submenu(),
      goto: () => this._target("goto"),
      assistant: () => this._target("assistant"),
    };
    return { ...base, ...(views[step.id] || views.what)() };
  }

  _what() {
    const t = this.t;
    const flags = this.ctx.flags;
    const level = this.ctx.level;
    const types = [
      ["device", "lightbulb-outline", "type_device", true],
      ["room", "door-open", "type_room", true],
      ["submenu", "folder-outline", "type_submenu", level.can_nest],
      ["assistant", "account-voice", "type_assistant", flags.assistant],
      ["goto", "phone-forward", "type_goto", flags.extensions],
      ["alerts", "bell-outline", "type_alerts", flags.alerts],
    ].filter((row) => row[3]).map(([type, iconName, key]) => item(
      { "data-act": "type", "data-type": type }, iconName, t(key), t(`${key}_text`),
      { chev: !["alerts"].includes(type) && !(type === "assistant" && flags.assistant_target) },
    ));
    const recent = this.ctx.recent().map((row) => this._deviceRow(row));
    return {
      body: [
        recent.length ? section(t("recent"), recent, { iconName: "history" }) : null,
        h("div", { class: "list" }, types),
      ],
    };
  }

  _deviceRow(row) {
    return btn("pick", { "data-act": "pick-device", "data-type": "entity", "data-id": row.id },
      this.ctx.rowIcon(row),
      h("span", { class: "txt" }, h("span", { class: "pick-name" }, auto(row.primary)),
        row.secondary ? h("small", null, auto(row.secondary)) : null),
      row.end ? h("span", { class: "pick-domain" }, auto(row.end)) : null);
  }

  _parts() {
    const t = this.t;
    const level = this.ctx.level;
    const items = (level.addable || []).filter((c) => level.kind !== "plan" || c.kind !== "text" || level.streaming);
    if (!items.length) return { body: h("p", { class: "muted" }, t("caps_none")) };
    if (level.kind === "options") {
      return {
        body: h("div", { class: "list" }, items.map((o) => item(
          { "data-act": "add-part", "data-value": o.value ?? "" }, "radiobox-marked", auto(o.label), "",
        ))),
      };
    }
    const groups = CAP_GROUPS.map((g) => section(t(`group_${g.id}`), items.filter((c) => capGroup(c) === g.id).map((c) => {
      if (g.id === "fixed") {
        return item({ "aria-disabled": "true", disabled: true }, g.icon, auto(c.name || c.label), t("note_fixed"));
      }
      return item({ "data-act": "add-part", "data-ident": c.ident ?? "" }, g.icon, auto(c.name || c.label), capNote(t, c));
    }), { iconName: g.icon }));
    return { body: [h("p", { class: "t-help" }, t("caps_new")), groups] };
  }

  // הבורר, כמו ha-target-picker של Home Assistant: שדה חיפוש, שבבי סינון
  // (ישויות, מכשירים, מרחבים | תוויות), כותרת דביקה לכל קטע, ושורות עם
  // אייקון אמיתי, שם, "אזור ◂ מכשיר" ושם הסוג. המיקוד נשאר בשדה, והחצים
  // מזיזים את הסימון. מכשיר פותח את הישויות שלו; מרחב או תווית — את
  // "מה לכלול".
  _device() {
    const ctx = this.ctx;
    const step = this.step;
    const query = step.query || "";
    const chips = step.deviceId ? null : h("div", { class: "chips", role: "group", "aria-label": ctx.ha("ui.components.target-picker.add_target", "filter") },
      PICKER_SECTIONS.map((key, index) => [
        index === 3 ? h("span", { class: "chip-sep", "aria-hidden": "true" }) : null,
        btn(cls("chip", step.filter === key && "on"), {
          "data-act": "pick-filter", "data-filter": key, "aria-pressed": step.filter === key ? "true" : "false",
        }, step.filter === key ? icon("check") : null, ctx.sectionTitle(key)),
      ]));
    return {
      subtitle: this._subtitle(step.deviceName ? auto(step.deviceName) : this.t("type_device")),
      fill: true,
      body: [
        h("div", { class: "search" }, icon("magnify"),
          h("input", {
            type: "search", "data-search": true, "data-focus": true, value: query, autocomplete: "off",
            spellcheck: "false", role: "combobox", "aria-expanded": "true", "aria-controls": "picks",
            "aria-autocomplete": "list", "aria-label": ctx.ha("ui.common.search", "search"), placeholder: ctx.ha("ui.common.search", "search"),
          }),
          iconBtn("close", this.t("clear"), { "data-act": "search-clear", class: "icon-btn clear", hidden: !query })),
        chips,
        h("div", { class: "picker", id: "picks", role: "listbox", "aria-label": this.t("type_device") }, this.deviceList(query)),
      ],
    };
  }

  /** הקטעים והשורות לפי החיפוש והסינון. */
  deviceList(query) {
    const ctx = this.ctx;
    const step = this.step;
    const text = String(query || "").trim();
    const sections = ctx.pickerSections(text, step.filter || "", step.deviceId || "");
    this.items = [];
    this.rows = [];
    for (const section of sections) {
      if (!section.rows.length) continue;
      if (!step.deviceId) this.items.push({ head: section.title });
      for (const row of section.rows) {
        this.items.push({ row, index: this.rows.length });
        this.rows.push(row);
      }
    }
    this.hl = text && this.rows.length ? 0 : -1;
    this.shown = 0;
    if (!this.rows.length) {
      const none = text
        ? ctx.ha("ui.components.entity.entity-picker.no_match", "no_match", { term: `‘${text}’` })
        : ctx.ha("ui.components.entity.entity-picker.no_entities", "no_devices");
      return [h("div", { class: "pick-none", role: "option", "aria-disabled": "true" }, icon("magnify"), h("span", null, none))];
    }
    return this._more();
  }

  // שורות במנות: אלפי ישויות לא נבנות בבת אחת. השורה האחרונה מביאה עוד.
  _more() {
    const out = [];
    const end = Math.min(this.items.length, this.shown + 100);
    for (let i = this.shown; i < end; i += 1) {
      const item = this.items[i];
      out.push(item.head
        ? h("div", { class: "pick-head", role: "presentation" }, item.head)
        : this._pickRow(item.row, item.index));
    }
    this.shown = end;
    if (end < this.items.length) {
      const sentinel = h("div", { class: "pick-more", "aria-hidden": "true" });
      this.ctx.whenVisible(sentinel, () => {
        if (sentinel.isConnected) sentinel.replaceWith(...this._more());
      });
      out.push(sentinel);
    }
    return out;
  }

  _pickRow(row, index) {
    const showId = row.type === "entity" && this.ctx.showEntityId();
    return btn(cls("pick", index === this.hl && "hl"), {
      "data-act": "pick-device", "data-type": row.type, "data-id": row.id, role: "option", id: `pick-${index}`,
      "aria-selected": index === this.hl ? "true" : "false", tabindex: "-1",
    },
    this.ctx.rowIcon(row),
    h("span", { class: "txt" },
      h("span", { class: "pick-name" }, auto(row.primary)),
      row.secondary ? h("small", null, auto(row.secondary)) : null,
      showId ? h("small", { class: "code" }, ltr(row.id)) : null),
    showId || !row.end ? null : h("span", { class: "pick-domain" }, auto(row.end)));
  }

  // הסימון זז בלי לצייר מחדש: רק המחלקה, aria-selected ו-activedescendant.
  _highlight(index) {
    const list = this.ctx.dialogOne("#picks");
    const input = this.ctx.dialogOne("[data-search]");
    if (!list || !this.rows || !this.rows.length) return;
    const next = Math.max(0, Math.min(this.rows.length - 1, index));
    let row = list.querySelector(`#pick-${next}`);
    while (!row) {
      const more = list.querySelector(".pick-more");
      if (!more) break;
      more.replaceWith(...this._more());
      row = list.querySelector(`#pick-${next}`);
    }
    for (const old of list.querySelectorAll(".pick.hl")) {
      old.classList.remove("hl");
      old.setAttribute("aria-selected", "false");
    }
    this.hl = next;
    if (!row) return;
    row.classList.add("hl");
    row.setAttribute("aria-selected", "true");
    if (input) input.setAttribute("aria-activedescendant", `pick-${next}`);
    if (typeof row.scrollIntoView === "function") row.scrollIntoView({ block: "nearest" });
  }

  keydown(ev) {
    if (this.step.id !== "device" || !ev.target.matches || !ev.target.matches("[data-search]")) return;
    const page = 8;
    const moves = {
      ArrowDown: () => this.hl + 1, ArrowUp: () => this.hl - 1,
      PageDown: () => this.hl + page, PageUp: () => this.hl - page,
      Home: () => 0, End: () => (this.rows || []).length - 1,
    };
    if (moves[ev.key]) {
      if (!(this.rows || []).length) return;
      ev.preventDefault();
      this._highlight(this.hl < 0 && ev.key === "ArrowUp" ? 0 : moves[ev.key]());
      return;
    }
    if (ev.key === "Enter") {
      ev.preventDefault();
      const rows = this.rows || [];
      const row = rows[this.hl >= 0 ? this.hl : rows.length === 1 ? 0 : -1];
      if (row) this.act("pick-device", { id: row.id, type: row.type });
    }
  }

  _caps() {
    const t = this.t;
    const step = this.step;
    const found = step.found;
    const caps = found.capabilities.filter((c) => c.kind !== "text" || found.streaming);
    const start = step.idents || caps.filter((c) => c.checked && !c.needs_fixed).map((c) => c.ident);
    const groups = CAP_GROUPS.map((g) => {
      const items = caps.filter((c) => capGroup(c) === g.id);
      if (g.id === "fixed") {
        return section(t(`group_${g.id}`), items.map((c) => item(
          { "data-act": "cap-fixed", "data-action": c.action || "" }, null, auto(c.name || c.label), t("set_value"), { chev: true },
        )), { iconName: g.icon });
      }
      return section(t(`group_${g.id}`), items.map((c) => check("cap", c.ident, auto(c.name || c.label), {
        checked: start.includes(c.ident), sub: capNote(t, c), group: g.id,
      })), { iconName: g.icon, bulk: { name: "cap", group: g.id, least: 2 }, t });
    });
    return {
      subtitle: this._subtitle(t("caps")),
      form: true,
      body: [
        this.ctx.entityLine(found.entity_id),
        groups,
        field(t("name_label"), h("input", { type: "text", name: "name", value: step.name || "", placeholder: found.name }),
          { help: t("name_help", { name: found.name }) }),
      ],
      foot: [cancel(t), submit(this._capsLabel(start), this.busy, { "data-primary": true })],
    };
  }

  _checked() {
    const boxes = this.ctx.dialogAll('input[name="cap"]');
    return boxes.length ? boxes.filter((box) => box.checked).map((box) => box.value) : null;
  }

  _choices(idents) {
    const found = this.stack.find((s) => s.id === "caps")?.found;
    if (!found) return [];
    return found.capabilities.filter((c) => idents.includes(c.ident) && (c.options || []).length > 1);
  }

  _capsLabel(idents) {
    return this._choices(idents).length ? this.t("next") : this.t("add");
  }

  _options() {
    const t = this.t;
    const step = this.step;
    const sections = this._choices(step.idents).map((c) => section(auto(c.name), c.options.map((o, index) => check(
      `opt:${c.ident}`, o.value, auto(o.label), { checked: step.kept ? (step.kept[c.ident] || []).includes(o.value) : index < MAX_KEYS },
    )), { iconName: "format-list-bulleted", bulk: { name: `opt:${c.ident}` }, t }));
    return {
      subtitle: this._subtitle(t("options_title")),
      form: true,
      body: [h("p", { class: "t-help" }, t("options_help")), sections],
      foot: [cancel(t), submit(t("add"), this.busy)],
    };
  }

  _values() {
    const t = this.t;
    const step = this.step;
    return {
      subtitle: this._subtitle(auto(step.action.label)),
      form: true,
      body: [
        h("p", { class: "t-help" }, t("values_help")),
        step.action.fields.map((f) => actionField(t, f)),
        field(t("name_label"), h("input", { type: "text", name: "name", placeholder: step.fixed.name }),
          { help: t("name_help", { name: step.fixed.name }) }),
      ],
      foot: [cancel(t), submit(t("add"), this.busy)],
    };
  }

  _place() {
    const t = this.t;
    const found = this.step.places;
    const part = (title, name, items) => section(title, items.map((i) => check(name, i.id, auto(i.name))),
      { bulk: { name }, t });
    const empty = !found.floors.length && !found.areas.length && !found.labels.length;
    return {
      subtitle: this._subtitle(t("type_room")),
      form: true,
      body: [
        h("div", { class: "list" }, check("whole", "1", t("place_whole"), { sub: t("type_room_text") })),
        empty ? h("p", { class: "muted" }, t("no_rooms")) : null,
        part(t("areas"), "area_id", found.areas),
        part(t("floors"), "floor_id", found.floors),
        part(t("labels"), "label_id", found.labels),
      ],
      foot: [cancel(t), submit(t("next"), this.busy)],
    };
  }

  _contents() {
    const t = this.t;
    const step = this.step;
    const room = step.room;
    if (!room.kinds.length) {
      return { subtitle: this._subtitle(auto(room.name)), body: h("p", { class: "muted" }, t("err_empty_room")) };
    }
    const out = new Set(step.exclude || []);
    const kinds = room.kinds.map((k) => {
      const members = room.members.filter((m) => m.domain === k.domain);
      return h("div", { class: "section" },
        check("kind", k.domain, auto(k.name), {
          checked: !step.domains || step.domains.includes(k.domain),
          sub: counted(t, k.count, "devices_one", "devices_count"),
        }),
        members.length > 1
          ? h("details", { class: "fold" },
            h("summary", null, icon(DOMAIN_ICONS[k.domain] || "devices"), h("span", { class: "grow" }, t("members")), icon("chevron-right", "chev")),
            h("div", { class: "list" }, members.map((m) => check(`member:${k.domain}`, m.entity_id, auto(m.name), {
              checked: !out.has(m.entity_id), sub: ltr(m.entity_id),
            }))))
          : null);
    });
    return {
      subtitle: this._subtitle(auto(room.name)),
      form: true,
      body: [
        h("p", { class: "t-help" }, t("contents_help")),
        this.ctx.level.can_nest ? null : h("div", { class: "alert info" }, icon("alert-circle-outline"), h("div", null, t("depth_one"))),
        kinds,
        h("div", null, btn("btn quiet", { "data-act": "add-all" }, icon("plus"), t("add_all"))),
      ],
      foot: [cancel(t), submit(t("next"), this.busy)],
    };
  }

  _functions() {
    const t = this.t;
    const step = this.step;
    const room = this.stack.find((s) => s.id === "contents").room;
    const sections = step.kinds.map((k) => section(auto(k.name), k.capabilities.map((c) => check(
      `cap:${k.domain}`, c.ident, auto(c.name || c.label), { checked: true, sub: capNote(t, c) },
    )), { iconName: DOMAIN_ICONS[k.domain] || "devices", bulk: { name: `cap:${k.domain}` }, t }));
    return {
      subtitle: this._subtitle(t("caps")),
      form: true,
      body: [
        sections.some(Boolean) ? sections : h("p", { class: "muted" }, t("functions_none")),
        field(t("name_label"), h("input", { type: "text", name: "name", placeholder: room.name }),
          { help: t("name_help", { name: room.name }) }),
      ],
      foot: [cancel(t), submit(t("add"), this.busy)],
    };
  }

  _submenu() {
    const t = this.t;
    return {
      subtitle: this._subtitle(t("type_submenu")),
      form: true,
      body: field(t("name_menu"), h("input", {
        type: "text", name: "name", placeholder: t("submenu_name_hint"), "data-focus": true, required: true,
      }), { required: true, t }),
      foot: [cancel(t), submit(t("add"), this.busy)],
    };
  }

  _target(kind) {
    const t = this.t;
    const flags = this.ctx.flags;
    const assistant = kind === "assistant";
    return {
      subtitle: this._subtitle(t(assistant ? "type_assistant" : "type_goto")),
      form: true,
      body: [
        field(t(assistant ? "target_assistant" : "target_goto"), h("input", {
          type: "text", name: "target", dir: "ltr", inputmode: "tel", "data-focus": true, required: true,
        }), { help: flags.goto_hint || "", required: true, t }),
        field(t("name_label"), h("input", { type: "text", name: "name", placeholder: t(assistant ? "type_assistant" : "type_goto") })),
      ],
      foot: [cancel(t), submit(t("add"), this.busy)],
    };
  }

  // ------------------------------------------------------------------

  async act(act, data) {
    const t = this.t;
    const step = this.step;
    const ctx = this.ctx;
    switch (act) {
      case "type": {
        const type = data.type;
        if (type === "device") {
          await this.run(async () => {
            await ctx.pickerData();
            this.push({ id: "device", query: "", filter: "" });
          });
        }
        else if (type === "room") {
          await this.run(async () => {
            const places = await ctx.api("places");
            this.push({ id: "place", places });
          });
        } else if (type === "submenu") this.push({ id: "submenu" });
        else if (type === "goto") this.push({ id: "goto" });
        else if (type === "assistant") {
          if (ctx.flags.assistant_target) await this.add("assistant", {});
          else this.push({ id: "assistant" });
        } else if (type === "alerts") await this.add("alerts", {});
        return;
      }
      case "pick-device": {
        const kind = data.type || "entity";
        if (kind === "device") {
          this.push({ id: "device", query: "", filter: "", deviceId: data.id, deviceName: ctx.deviceName(data.id) });
          return;
        }
        if (kind === "area" || kind === "floor" || kind === "label") {
          const target = { [`${kind}_id`]: [data.id] };
          await this.run(async () => {
            const room = await ctx.api("place", { args: { target } });
            this.push({ id: "contents", room, domains: null, exclude: null });
          });
          return;
        }
        await this.run(async () => {
          const found = await ctx.api("capabilities", { args: { entity_id: data.id } });
          this.push({ id: "caps", found, idents: null, name: "" });
        });
        return;
      }
      case "pick-filter":
        step.filter = step.filter === data.filter ? "" : data.filter;
        this.ctx.repaint({ refocus: true });
        return;
      case "cap-fixed": {
        // מה שסומן עד עכשיו נשמר, כדי שחזרה תמצא אותו כמו שהיה.
        step.idents = this._checked() || step.idents;
        step.name = ctx.dialogValue("name") ?? step.name;
        await this.run(async () => {
          step.fixed = step.fixed || await ctx.api("actions", { args: { entity_id: step.found.entity_id } });
          const action = step.fixed.actions.find((a) => a.action === data.action);
          if (!action) throw new Error(t("err_unsupported"));
          this.push({ id: "values", fixed: step.fixed, action, entity_id: step.found.entity_id });
        });
        return;
      }
      case "search-clear": {
        step.query = "";
        const input = ctx.dialogOne("[data-search]");
        if (input) {
          input.value = "";
          input.focus();
        }
        const clear = ctx.dialogOne(".search .clear");
        if (clear) clear.hidden = true;
        this._refill();
        return;
      }
      case "add-part":
        if (ctx.level.kind === "plan") await this.add("capability", { ident: data.ident });
        else await this.add("option", { value: data.value });
        return;
      case "add-all": {
        const form = ctx.dialogForm();
        const { domains, exclude } = this._picked(form);
        if (!this._checkKinds(domains)) return;
        await this.add("room", { target: step.room.target, domains, exclude, name: "" });
        return;
      }
      default:
    }
  }

  _picked(data) {
    const step = this.step;
    const domains = data.getAll("kind");
    const exclude = [];
    const kept = [];
    for (const domain of domains) {
      const all = step.room.members.filter((m) => m.domain === domain);
      const boxes = data.getAll(`member:${domain}`);
      // סוג עם חבר אחד אין לו רשימה, והוא נכלל כולו.
      if (all.length < 2) {
        kept.push(domain);
        continue;
      }
      const on = new Set(boxes);
      if (!all.some((m) => on.has(m.entity_id))) continue;
      kept.push(domain);
      for (const m of all) if (!on.has(m.entity_id)) exclude.push(m.entity_id);
    }
    return { domains: kept, exclude };
  }

  _checkKinds(domains) {
    if (!domains.length) {
      this._fail(this.t("pick_one_kind"));
      return false;
    }
    if (domains.length > 1 && !this.ctx.level.can_nest) {
      this._fail(this.t("depth_one"));
      return false;
    }
    return true;
  }

  _fail(text) {
    this.error = text;
    this.ctx.repaint({ refocus: true });
  }

  async submit(data) {
    const t = this.t;
    const step = this.step;
    const ctx = this.ctx;
    const text = (name) => String(data.get(name) || "").trim();
    switch (step.id) {
      case "caps": {
        const idents = data.getAll("cap");
        step.idents = idents;
        step.name = text("name");
        if (!idents.length) return this._fail(t("pick_one_cap"));
        if (idents.length > MAX_KEYS) return this._fail(t("too_many_caps", { n: idents.length }));
        if (this._choices(idents).length) {
          this.push({ id: "options", idents });
          return undefined;
        }
        return this.add("device", { entity_id: step.found.entity_id, idents, name: step.name });
      }
      case "options": {
        const caps = this.stack.find((s) => s.id === "caps");
        const options = {};
        for (const c of this._choices(step.idents)) {
          const values = data.getAll(`opt:${c.ident}`);
          if (!values.length) return this._fail(t("pick_one_value", { name: c.name }));
          if (values.length > MAX_KEYS) return this._fail(t("too_many_values", { name: c.name }));
          options[c.ident] = values;
        }
        step.kept = options;
        return this.add("device", {
          entity_id: caps.found.entity_id, idents: step.idents, options, name: caps.name,
        });
      }
      case "values":
        return this.add("action", {
          entity_id: step.entity_id, action: step.action.action,
          data: formValues(step.action.fields, data), name: text("name"),
        });
      case "place": {
        const target = {};
        if (!data.get("whole")) {
          for (const key of ["floor_id", "area_id", "label_id"]) {
            const ids = data.getAll(key);
            if (ids.length) target[key] = ids;
          }
          if (!Object.keys(target).length) return this._fail(t("pick_one_room"));
        }
        return this.run(async () => {
          const room = await ctx.api("place", { args: { target } });
          this.push({ id: "contents", room, domains: null, exclude: null });
        });
      }
      case "contents": {
        const { domains, exclude } = this._picked(data);
        step.domains = data.getAll("kind");
        step.exclude = exclude;
        if (!this._checkKinds(domains)) return undefined;
        return this.run(async () => {
          const found = await ctx.api("place_functions", { args: { target: step.room.target, exclude, domains } });
          this.push({ id: "functions", domains, exclude, kinds: found.kinds });
        });
      }
      case "functions": {
        const room = this.stack.find((s) => s.id === "contents").room;
        const idents = {};
        for (const kind of step.kinds) {
          const picked = data.getAll(`cap:${kind.domain}`);
          if (picked.length) idents[kind.domain] = picked;
        }
        const domains = Object.keys(idents);
        if (!domains.length) return this._fail(t("pick_one_cap"));
        if (!this._checkKinds(domains)) return undefined;
        return this.add("room", { target: room.target, exclude: step.exclude, domains, idents, name: text("name") });
      }
      case "submenu":
        if (!text("name")) return this._fail(t("err_name_required"));
        return this.add("submenu", { name: text("name") }, { enter: true });
      case "goto":
      case "assistant":
        if (!text("target")) return this._fail(t("err_target_required"));
        return this.add(step.id, { target: text("target"), name: text("name") });
      default:
        return undefined;
    }
  }

  input(ev) {
    const target = ev.target;
    if (target.name === "cap") {
      const button = this.ctx.dialogOne("[data-primary]");
      if (button) button.textContent = this._capsLabel(this._checked() || []);
      return;
    }
    if (target.matches && target.matches("[data-search]")) {
      this.step.query = target.value;
      const clear = this.ctx.dialogOne(".search .clear");
      if (clear) clear.hidden = !target.value;
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this._refill(), 150);
    }
  }

  _refill() {
    const list = this.ctx.dialogOne("#picks");
    if (!list) return;
    list.replaceChildren(...this.deviceList(this.step.query || ""));
    const input = this.ctx.dialogOne("[data-search]");
    if (input) {
      if (this.hl >= 0) input.setAttribute("aria-activedescendant", `pick-${this.hl}`);
      else input.removeAttribute("aria-activedescendant");
    }
  }

  async add(what, args, { enter = false } = {}) {
    const ctx = this.ctx;
    return this.run(async () => {
      await ctx.mutate("add", {
        path: this.path, args: { what, ...args, ...(this.replace ? { replace: true } : {}) },
      }, { flash: this.digit, enter: enter ? this.path : "" });
      if (args.entity_id) ctx.remember(args.entity_id);
      ctx.done();
    });
  }
}

// ------------------------------------------------------------------
// מקש קיים
// ------------------------------------------------------------------

export class KeyFlow extends Flow {
  constructor(ctx, key, { self = false } = {}) {
    super(ctx);
    this.key = key;
    this.self = self;
    this.stack = [{ id: "main" }];
    const flags = ctx.flags;
    // יעד נערך רק היכן שהמשתמש הוא שקבע אותו.
    this.editTarget = key.kind === "goto" ? Boolean(flags.extensions) : key.kind === "assistant" && !flags.assistant_target;
    this.original = { name: key.label || "", target: key.target || "", values: null, place: null };
    this.draft = { ...this.original };
    this.fixed = null;
    this.group = null;
  }

  /** מה שצריך מהשרת לפני הציור הראשון: ערך קבוע של פעולה. */
  async load() {
    if (this.key.kind === "action" && this.key.fixed) {
      await this.run(async () => {
        this.fixed = await this.ctx.api("fixed", { path: this.key.path });
        this.original.values = { ...(this.fixed.values || {}) };
        this.draft.values = { ...this.original.values };
      });
    }
  }

  dirty() {
    return !same(this.draft, this.original);
  }

  view() {
    const t = this.t;
    const key = this.key;
    const step = this.step;
    const base = { badge: key.digit, title: key.name, back: this.stack.length > 1, error: this.error, menu: step.id === "main" };
    if (step.id === "places") return { ...base, ...this._places() };
    if (step.id === "members") return { ...base, ...this._members() };
    return { ...base, ...this._main() };
  }

  _main() {
    const t = this.t;
    const ctx = this.ctx;
    const key = this.key;
    const body = [];
    const alert = ctx.alertFor(key);
    if (alert && alert.kind === "removed") {
      body.push(h("div", { class: "alert error", role: "alert" }, icon("alert-circle-outline"),
        h("div", { class: "grow" }, t("alert_removed"),
          ctx.canReplace(key) ? h("div", { class: "acts" }, btn("btn quiet", { "data-act": "replace" }, icon("swap-horizontal"), t("replace"))) : null)));
    } else if (alert && alert.kind === "unavailable") {
      body.push(h("div", { class: "alert" }, icon("alert-outline"), h("div", null,
        key.kind === "cap" ? t("alert_gone") : key.kind === "group" ? t("alert_group_empty") : t("alert_unavailable"))));
    } else if (key.silent) {
      body.push(h("div", { class: "alert info" }, icon("alert-circle-outline"), h("div", null, t("alert_quiet"))));
    }
    if (key.entity_id) body.push(ctx.entityLine(key.entity_id));
    if (key.enter && !this.self) {
      body.push(h("div", { class: "list" }, item({ "data-act": "open-level" }, "folder-outline", t("open_level"), ctx.keySubText(key), { chev: true })));
    }
    if (key.kind !== "option") {
      const required = key.kind === "submenu" || key.kind === "cap";
      const label = key.kind === "submenu" ? t("name_menu") : key.kind === "cap" ? t("name_action") : t("name_label");
      body.push(field(label, h("input", {
        type: "text", name: "name", value: this.draft.name, placeholder: key.name, "data-focus": true,
      }), { help: required ? "" : t("name_help", { name: key.name }), required, t }));
    }
    if (this.editTarget) {
      body.push(field(t(key.kind === "assistant" ? "target_assistant" : "target_goto"), h("input", {
        type: "text", name: "target", dir: "ltr", inputmode: "tel", value: this.draft.target,
      }), { help: ctx.flags.goto_hint || "", required: true, t }));
    }
    if (this.fixed) {
      body.push(h("div", { class: "section" },
        h("div", { class: "section-head" }, icon("tune-variant"), h("h3", null, auto(this.fixed.action.label))),
        this.fixed.action.fields.map((f) => actionField(t, f, (this.draft.values || {})[f.name]))));
    }
    if (key.kind === "group") {
      body.push(h("div", { class: "list" }, item({ "data-act": "edit-place" }, "home-group", t("edit_place"), t("edit_place_text"), { chev: true })));
    }
    const said = this.self ? ctx.level.heard || [] : (ctx.level.heard || []).filter((line) => key.name && line.includes(key.name));
    if (said.length) body.push(ctx.heardList(said, t("heard")));
    return {
      subtitle: t(`kind_${key.kind}`),
      form: true,
      body,
      foot: [cancel(t), submit(t("save"), this.busy, { "data-save": true, disabled: this.busy || !this.dirty() })],
    };
  }

  _places() {
    const t = this.t;
    const group = this.group;
    const chosen = (this.draft.place && this.draft.place.target) || group.target;
    const part = (title, name, items) => section(title, items.map((i) => check(name, i.id, auto(i.name), {
      checked: (chosen[name] || []).includes(i.id),
    })), { bulk: { name }, t });
    const direct = (group.target.device_id || []).length + (group.target.entity_id || []).length;
    return {
      subtitle: t("edit_place"),
      form: true,
      body: [
        h("p", { class: "t-help" }, t("place_whole"), direct ? ` · ${counted(t, direct, "devices_one", "devices_count")}` : ""),
        part(t("areas"), "area_id", group.places.areas),
        part(t("floors"), "floor_id", group.places.floors),
        part(t("labels"), "label_id", group.places.labels),
      ],
      foot: [submit(t("next"), this.busy)],
    };
  }

  _members() {
    const t = this.t;
    const step = this.step;
    const out = new Set(step.exclude || []);
    return {
      subtitle: t("members"),
      form: true,
      body: [
        h("p", { class: "t-help" }, t("contents_help")),
        section(auto(this.group.name), step.members.map((m) => check("member", m.entity_id, auto(m.name), {
          checked: !out.has(m.entity_id), sub: ltr(m.entity_id),
        })), { iconName: DOMAIN_ICONS[this.group.domain] || "devices", bulk: { name: "member" }, t }),
      ],
      foot: [submit(t("next"), this.busy)],
    };
  }

  async act(act) {
    const ctx = this.ctx;
    if (act === "open-level") {
      ctx.done();
      ctx.go(this.key.path);
      return;
    }
    if (act === "replace") {
      ctx.replace(this.key);
      return;
    }
    if (act === "edit-place") {
      await this.run(async () => {
        this.group = this.group || await ctx.api("group", { path: this.key.path });
        this.push({ id: "places" });
      });
    }
  }

  async submit(data) {
    const t = this.t;
    const ctx = this.ctx;
    const step = this.step;
    if (step.id === "places") {
      const group = this.group;
      const target = {};
      // מכשירים שנבחרו ישירות אינם בטופס, ולכן נשארים כמו שהם.
      for (const key of ["device_id", "entity_id"]) {
        if ((group.target[key] || []).length) target[key] = group.target[key];
      }
      for (const key of ["floor_id", "area_id", "label_id"]) {
        const ids = data.getAll(key);
        if (ids.length) target[key] = ids;
      }
      return this.run(async () => {
        const room = await ctx.api("place", { args: { target } });
        const members = room.members.filter((m) => m.domain === group.domain);
        if (!members.length) throw Object.assign(new Error(t("err_empty_room")), { code: "empty_room" });
        this.push({ id: "members", target, members, exclude: (this.draft.place && this.draft.place.exclude) || group.exclude || [] });
      });
    }
    if (step.id === "members") {
      const kept = new Set(data.getAll("member"));
      if (!kept.size) return this._fail(t("pick_one_device"));
      const exclude = step.members.map((m) => m.entity_id).filter((id) => !kept.has(id));
      this.draft.place = { target: step.target, exclude };
      this.stack = [{ id: "main" }];
      ctx.repaint({ refocus: true });
      return undefined;
    }
    this._read(data);
    if (!this.dirty()) {
      ctx.done();
      return undefined;
    }
    const args = {};
    if (this.draft.name !== this.original.name) args.name = this.draft.name;
    if (this.draft.target !== this.original.target) args.target = this.draft.target;
    if (!same(this.draft.values, this.original.values)) args.values = this.draft.values;
    if (!same(this.draft.place, this.original.place)) args.place = this.draft.place;
    return this.run(async () => {
      await ctx.mutate("update", { path: this.key.path, args }, { flash: this.self ? "" : this.key.digit });
      ctx.done();
    });
  }

  _fail(text) {
    this.error = text;
    this.ctx.repaint({ refocus: true });
  }

  // הטיוטה מתעדכנת מהטופס, כדי ש"שמירה" תדע אם יש שינוי.
  _read(data) {
    if (this.step.id !== "main") return;
    if (data.has("name")) this.draft.name = String(data.get("name") || "").trim();
    if (data.has("target")) this.draft.target = String(data.get("target") || "").trim();
    if (this.fixed) this.draft.values = formValues(this.fixed.action.fields, data);
  }

  input() {
    const form = this.ctx.dialogForm();
    if (!form) return;
    this._read(form);
    const save = this.ctx.dialogOne("[data-save]");
    if (save) save.disabled = this.busy || !this.dirty();
  }
}

// ------------------------------------------------------------------
// תפריט מהחדרים
// ------------------------------------------------------------------

export class BuildFlow extends Flow {
  constructor(ctx, rooms) {
    super(ctx);
    this.rooms = rooms;
    this.stack = [{ id: "rooms" }];
  }

  view() {
    const t = this.t;
    const free = Object.values(this.ctx.level.keys).filter((k) => !k).length;
    const rooms = this.rooms;
    return {
      title: t("build"),
      error: this.error,
      form: true,
      body: [
        h("p", { class: "t-help" }, t("build_help", { n: free })),
        rooms.length
          ? section(t("areas"), rooms.map((room, index) => check("room", index, auto(room.name), {
            checked: Boolean(room.area_id) && index < free, sub: auto(room.kinds.map((k) => k.name).join(" · ")),
          })), { iconName: "door-open", bulk: { name: "room" }, t })
          : h("p", { class: "muted" }, t("no_rooms")),
      ],
      foot: [cancel(t), submit(t("build_go"), this.busy)],
    };
  }

  async submit(data) {
    const areaIds = data.getAll("room").map((i) => this.rooms[Number(i)].area_id);
    if (!areaIds.length) {
      this.error = this.t("pick_one_room");
      this.ctx.repaint({ refocus: true });
      return undefined;
    }
    return this.run(async () => {
      await this.ctx.mutate("build", { path: this.ctx.level.path, args: { area_ids: areaIds } });
      this.ctx.done();
    });
  }

  act() {}
}
