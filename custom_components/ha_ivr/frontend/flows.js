// מה שקורה בתוך החלון: הוספה למקש, עריכת מקש, ובנייה מהחדרים.
//
// כל flow הוא מחסנית של צעדים. צעד מחזיר תצוגה: כותרת, גוף, וכפתור
// ראשי. כל טופס הוא ha-form של Home Assistant, עם הבוררים הרשמיים
// (ישות, חדר, קומה, תווית, רשימת סימון ושדות של פעולה). השרת מחליט
// מה מותר; כאן רק אוספים את מה שנבחר.

import { form, h, icon, row } from "./dom.js";

const MAX_KEYS = 9;

const text = (label, extra = {}) => ({ selector: { text: {} }, label, ...extra });
const checklist = (name, label, options, extra = {}) => ({
  name, label, selector: { select: { multiple: true, mode: "list", options } }, ...extra,
});
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

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
    this.stack.push({ data: {}, ...step });
    this.error = "";
    this.ctx.paint();
  }

  back() {
    if (this.stack.length < 2) return;
    this.stack.pop();
    this.error = "";
    this.ctx.paint();
  }

  dirty() {
    return false;
  }

  // שינוי בטופס מעדכן רק את הכפתורים: ציור מחדש של הטופס היה מאבד את המיקוד.
  changed() {
    this.ctx.paintFooter();
  }

  fail(message) {
    this.error = message;
    this.ctx.paint();
  }

  /** פעולה מול השרת, אחת בכל פעם. שגיאה מוצגת בראש החלון. */
  async run(work) {
    if (this.busy) return;
    this.busy = true;
    this.error = "";
    this.ctx.paint();
    try {
      await work();
    } catch (err) {
      this.error = this.ctx.errorText(err);
    } finally {
      this.busy = false;
      if (this.ctx.flow === this) this.ctx.paint();
    }
  }

  /** טופס של הצעד הנוכחי. הערכים נשמרים בצעד, כך שחזרה מוצאת אותם. */
  form(schema) {
    const step = this.step;
    return form(this.ctx.hass, schema, step.data, (value) => {
      step.data = value;
      this.changed?.();
    });
  }

  /** בדיקת כמות: לפחות אחד, ולא יותר מהמקשים. */
  counted(values) {
    if (!values || !values.length) return this.fail(this.t("pick_one")) ?? false;
    if (values.length > MAX_KEYS) return this.fail(this.t("too_many", { n: values.length })) ?? false;
    return true;
  }
}

// ------------------------------------------------------------------
// הוספה למקש ריק
// ------------------------------------------------------------------

export class AddFlow extends Flow {
  constructor(ctx, digit, { replace = false } = {}) {
    super(ctx);
    this.digit = digit;
    this.path = ctx.path(digit);
    this.replace = replace;
    const kind = ctx.level.kind;
    const first = kind === "plan" || kind === "options" ? "parts" : replace ? "device" : "what";
    this.stack = [{ id: first, data: {} }];
  }

  view() {
    const t = this.t;
    const views = {
      what: () => this.what(),
      parts: () => this.parts(),
      device: () => this.device(),
      caps: () => this.caps(),
      options: () => this.options(),
      fixed: () => this.fixedPick(),
      values: () => this.values(),
      place: () => this.place(),
      contents: () => this.contents(),
      functions: () => this.functions(),
      submenu: () => this.named("name_menu", true),
      goto: () => this.target("goto"),
      assistant: () => this.target("assistant"),
    };
    return { title: this.replace ? t("replace") : t("add_title", { digit: this.digit }), ...views[this.step.id]() };
  }

  what() {
    const t = this.t;
    const flags = this.ctx.flags;
    const level = this.ctx.level;
    const types = [
      ["device", "lightbulb-outline", true],
      ["room", "home-group", true],
      ["submenu", "folder-outline", level.can_nest],
      ["assistant", "account-voice", flags.assistant],
      ["goto", "phone-forward", flags.extensions],
      ["alerts", "bell-outline", flags.alerts],
    ];
    return {
      body: h("div", { class: "rows" }, types.filter((type) => type[2]).map(([type, iconName]) =>
        row(iconName, t(`type_${type}`), t(`type_${type}_text`), () => this.pick(type)))),
    };
  }

  pick(type) {
    if (type === "room") this.push({ id: "place" });
    else if (type === "alerts") this.add("alerts", {});
    else if (type === "assistant" && this.ctx.flags.assistant_target) this.add("assistant", {});
    else this.push({ id: type });
  }

  // יכולות או אפשרויות שעדיין אין להן מקש, בתוך מכשיר או בחירה.
  parts() {
    const level = this.ctx.level;
    const items = (level.addable || []).filter((c) => !c.needs_fixed);
    if (!items.length) return { body: h("p", { class: "muted" }, this.t("caps_none")) };
    return {
      body: h("div", { class: "rows" }, items.map((c) => level.kind === "options"
        ? row("radiobox-marked", c.label, "", () => this.add("option", { value: c.value }), { chevron: false })
        : row("plus", c.label, this.note(c), () => this.add("capability", { ident: c.ident }), { chevron: false }))),
    };
  }

  device() {
    const ctx = this.ctx;
    const hass = ctx.hass;
    const domains = new Set(Object.keys(hass.states).map((id) => id.split(".", 1)[0]));
    for (const domain of ctx.blocked) domains.delete(domain);
    const own = Object.values(hass.entities || {}).filter((e) => e.platform === "ha_ivr").map((e) => e.entity_id);
    return {
      body: this.form([{
        name: "entity_id",
        label: this.t("device"),
        selector: { entity: { filter: [{ domain: [...domains] }], exclude_entities: own } },
      }]),
    };
  }

  /** בחירת ישות טוענת את מה שהיא יודעת לעשות; "כל הבית" מסתיר את בוררי המקום. */
  changed() {
    const step = this.step;
    if (step.id === "place") {
      if (Boolean(step.data.whole) !== Boolean(step.whole)) {
        step.whole = Boolean(step.data.whole);
        this.ctx.paint();
      }
      return;
    }
    if (step.id !== "device" || !step.data.entity_id) {
      this.ctx.paintFooter();
      return;
    }
    this.run(async () => {
      const found = await this.ctx.api("capabilities", { args: { entity_id: step.data.entity_id } });
      const idents = found.capabilities.filter((c) => c.checked && !c.needs_fixed).map((c) => c.ident);
      this.push({ id: "caps", found, data: { idents, name: "" } });
    });
  }

  note(c) {
    if (c.code) return this.t("note_code");
    if (c.kind === "status") return this.t("note_status");
    return "";
  }

  caps() {
    const t = this.t;
    const step = this.step;
    const found = step.found;
    const dialable = found.capabilities.filter((c) => !c.needs_fixed);
    const options = dialable.map((c) => ({ value: c.ident, label: [c.label, this.note(c)].filter(Boolean).join(" · ") }));
    return {
      subtitle: found.name,
      body: [
        this.ctx.entityLine(found.entity_id),
        this.form([
          checklist("idents", t("caps"), options, { helper: t("caps_help") }),
          { name: "name", ...text(t("name_label"), { helper: t("name_help", { name: found.name }) }) },
        ]),
        found.fixed ? h("div", { class: "rows" }, row("tune-variant", t("fixed"), t("fixed_text"), () => this.toFixed())) : null,
      ],
      primary: { label: this.choices().length ? t("next") : t("add"), run: () => this.submitCaps() },
    };
  }

  /** בחירות עם יותר מערך אחד, שצריך לקבוע מה מהן יוצע. */
  choices() {
    const caps = this.stack.find((s) => s.id === "caps");
    const idents = caps.data.idents || [];
    return caps.found.capabilities.filter((c) => idents.includes(c.ident) && (c.options || []).length > 1);
  }

  submitCaps() {
    const step = this.step;
    if (!this.counted(step.data.idents)) return;
    const choices = this.choices();
    if (!choices.length) {
      this.add("device", { entity_id: step.found.entity_id, idents: step.data.idents, name: step.data.name || "" });
      return;
    }
    const data = {};
    for (const c of choices) data[`opt:${c.ident}`] = c.options.slice(0, MAX_KEYS).map((o) => o.value);
    this.push({ id: "options", data });
  }

  options() {
    const t = this.t;
    return {
      subtitle: t("options_help"),
      body: this.form(this.choices().map((c) => checklist(`opt:${c.ident}`, c.name, c.options))),
      primary: {
        label: t("add"),
        run: () => {
          const caps = this.stack.find((s) => s.id === "caps");
          const options = {};
          for (const c of this.choices()) {
            const values = this.step.data[`opt:${c.ident}`];
            if (!this.counted(values)) return;
            options[c.ident] = values;
          }
          this.add("device", {
            entity_id: caps.found.entity_id, idents: caps.data.idents, options, name: caps.data.name || "",
          });
        },
      },
    };
  }

  toFixed() {
    const caps = this.step;
    this.run(async () => {
      const found = await this.ctx.api("actions", { args: { entity_id: caps.found.entity_id } });
      this.push({ id: "fixed", actions: found.actions, entity: found });
    });
  }

  fixedPick() {
    const step = this.step;
    return {
      subtitle: this.t("fixed_pick"),
      body: h("div", { class: "rows" }, step.actions.map((action) =>
        row("tune-variant", action.label, action.fields.map((f) => f.label).join(" · "),
          () => this.push({ id: "values", action, entity: step.entity })))),
    };
  }

  values() {
    const t = this.t;
    const step = this.step;
    return {
      subtitle: `${step.entity.name} · ${step.action.label}`,
      body: [
        h("p", { class: "help" }, t("values_help")),
        this.form([
          ...step.action.fields,
          { name: "__name", ...text(t("name_label"), { helper: t("name_help", { name: step.entity.name }) }) },
        ]),
      ],
      primary: {
        label: t("add"),
        run: () => {
          const { __name: name = "", ...data } = step.data;
          this.add("action", { entity_id: step.entity.entity_id, action: step.action.action, data, name });
        },
      },
    };
  }

  place() {
    const t = this.t;
    const whole = Boolean(this.step.data.whole);
    return {
      subtitle: t("type_room"),
      body: this.form([
        { name: "whole", label: t("place_whole"), selector: { boolean: {} } },
        ...(whole ? [] : placeSchema(t)),
      ]),
      primary: {
        label: t("next"),
        run: () => {
          const target = whole ? {} : placeTarget(this.step.data);
          if (!whole && !Object.keys(target).length) return this.fail(t("pick_one"));
          return this.run(async () => {
            const room = await this.ctx.api("place", { args: { target } });
            const data = { domains: room.kinds.map((k) => k.domain) };
            for (const k of room.kinds) data[`m:${k.domain}`] = members(room, k.domain).map((m) => m.entity_id);
            this.push({ id: "contents", room, data });
          });
        },
      },
    };
  }

  /** בחירת סוגים ומכשירים. מה שלא סומן נשמר כהחרגה. */
  picked() {
    const step = this.stack.find((s) => s.id === "contents");
    const domains = step.data.domains || [];
    const exclude = [];
    for (const domain of domains) {
      const kept = new Set(step.data[`m:${domain}`] || []);
      for (const m of members(step.room, domain)) if (!kept.has(m.entity_id)) exclude.push(m.entity_id);
    }
    return { room: step.room, domains, exclude };
  }

  checkKinds(domains) {
    if (!domains.length) return this.fail(this.t("pick_one")) ?? false;
    if (domains.length > 1 && !this.ctx.level.can_nest) return this.fail(this.t("depth_one")) ?? false;
    return true;
  }

  contents() {
    const t = this.t;
    const room = this.step.room;
    if (!room.kinds.length) return { subtitle: room.name, body: h("p", { class: "muted" }, t("no_rooms")) };
    const kinds = room.kinds.map((k) => ({ value: k.domain, label: `${k.name} · ${t("count_devices", { n: k.count })}` }));
    const lists = room.kinds.filter((k) => k.count > 1).map((k) => ({
      type: "expandable", flatten: true, title: `${t("members")}: ${k.name}`,
      // הכותרת כבר בלוח המתקפל, ולכן לרשימה עצמה אין תווית.
      schema: [checklist(`m:${k.domain}`, "", members(room, k.domain).map((m) => ({ value: m.entity_id, label: m.name })))],
    }));
    return {
      subtitle: room.name,
      body: [
        h("p", { class: "help" }, t("place_help")),
        this.ctx.level.can_nest ? null : h("p", { class: "alert" }, t("depth_one")),
        this.form([checklist("domains", t("kinds"), kinds), ...lists]),
        h("div", { class: "acts" }, h("button", {
          type: "button", class: "btn", onclick: () => {
            const { domains, exclude } = this.picked();
            if (this.checkKinds(domains)) this.add("room", { target: room.target, domains, exclude, name: "" });
          },
        }, icon("plus"), t("add_all"))),
      ],
      primary: {
        label: t("next"),
        run: () => {
          const { domains, exclude } = this.picked();
          if (!this.checkKinds(domains)) return;
          this.run(async () => {
            const found = await this.ctx.api("place_functions", { args: { target: room.target, exclude, domains } });
            const data = { name: "" };
            for (const k of found.kinds) data[`cap:${k.domain}`] = k.capabilities.map((c) => c.ident);
            this.push({ id: "functions", kinds: found.kinds, data });
          });
        },
      },
    };
  }

  functions() {
    const t = this.t;
    const step = this.step;
    const { room, exclude } = this.picked();
    if (!step.kinds.some((k) => k.capabilities.length)) {
      return { body: h("p", { class: "muted" }, t("functions_none")) };
    }
    return {
      subtitle: room.name,
      body: this.form([
        ...step.kinds.map((k) => checklist(`cap:${k.domain}`, k.name, k.capabilities.map((c) => ({ value: c.ident, label: c.label })))),
        { name: "name", ...text(t("name_label"), { helper: t("name_help", { name: room.name }) }) },
      ]),
      primary: {
        label: t("add"),
        run: () => {
          const idents = {};
          for (const k of step.kinds) {
            const chosen = step.data[`cap:${k.domain}`] || [];
            if (chosen.length) idents[k.domain] = chosen;
          }
          const domains = Object.keys(idents);
          if (!this.checkKinds(domains)) return;
          this.add("room", { target: room.target, exclude, domains, idents, name: step.data.name || "" });
        },
      },
    };
  }

  named(labelKey, required) {
    const t = this.t;
    return {
      body: this.form([{ name: "name", required, ...text(t(labelKey)) }]),
      primary: {
        label: t("add"),
        run: () => {
          const name = String(this.step.data.name || "").trim();
          if (required && !name) return this.fail(t("err_name_required"));
          return this.add("submenu", { name }, { enter: true });
        },
      },
    };
  }

  target(kind) {
    const t = this.t;
    return {
      subtitle: t(`type_${kind}`),
      body: this.form([
        { name: "target", required: true, ...text(t(`target_${kind}`), { helper: this.ctx.flags.goto_hint || "" }) },
        { name: "name", ...text(t("name_label")) },
      ]),
      primary: {
        label: t("add"),
        run: () => {
          const target = String(this.step.data.target || "").trim();
          if (!target) return this.fail(t("err_target_required"));
          return this.add(kind, { target, name: String(this.step.data.name || "").trim() });
        },
      },
    };
  }

  add(what, args, { enter = false } = {}) {
    return this.run(async () => {
      await this.ctx.mutate("add", {
        path: this.path, args: { what, ...args, ...(this.replace ? { replace: true } : {}) },
      }, { flash: this.digit, enter: enter ? this.path : "" });
      this.ctx.done();
    });
  }
}

const members = (room, domain) => room.members.filter((m) => m.domain === domain);

const placeSchema = (t) => [
  { name: "area_id", label: t("areas"), selector: { area: { multiple: true } } },
  { name: "floor_id", label: t("floors"), selector: { floor: { multiple: true } } },
  { name: "label_id", label: t("labels"), selector: { label: { multiple: true } } },
];

const placeTarget = (data) => {
  const target = {};
  for (const key of ["area_id", "floor_id", "label_id"]) if ((data[key] || []).length) target[key] = data[key];
  return target;
};

// ------------------------------------------------------------------
// מקש קיים
// ------------------------------------------------------------------

export class KeyFlow extends Flow {
  constructor(ctx, key, { self = false } = {}) {
    super(ctx);
    this.key = key;
    this.self = self;
    const flags = ctx.flags;
    // יעד נערך רק כשהמשתמש הוא שקבע אותו.
    this.editTarget = key.kind === "goto" ? Boolean(flags.extensions) : key.kind === "assistant" && !flags.assistant_target;
    this.fields = [];
    this.original = { name: key.label || "", target: key.target || "" };
    this.stack = [{ id: "main", data: { ...this.original } }];
    this.place = null;
  }

  /** ערך קבוע של פעולה נטען לפני הציור הראשון. */
  async load() {
    if (this.key.kind !== "action" || !this.key.fixed) return;
    await this.run(async () => {
      const fixed = await this.ctx.api("fixed", { path: this.key.path });
      this.fields = fixed.action.fields;
      this.fixedLabel = fixed.action.label;
      Object.assign(this.original, fixed.values || {});
      Object.assign(this.stack[0].data, fixed.values || {});
    });
  }

  draft() {
    return this.stack[0].data;
  }

  dirty() {
    return !same(this.draft(), this.original) || Boolean(this.place);
  }

  view() {
    const views = { main: () => this.main(), move: () => this.move(), places: () => this.places(), members: () => this.members() };
    return { title: this.key.name, ...views[this.step.id]() };
  }

  main() {
    const t = this.t;
    const ctx = this.ctx;
    const key = this.key;
    const alert = ctx.alertFor(key);
    const notes = {
      removed: t("alert_removed"),
      unavailable: key.kind === "cap" ? t("alert_gone") : t("alert_unavailable"),
      quiet: t("alert_quiet"),
    };
    const schema = [];
    if (key.kind !== "option") {
      const label = key.kind === "submenu" ? t("name_menu") : key.kind === "cap" ? t("name_action") : t("name_label");
      schema.push({ name: "name", ...text(label, { helper: t("name_help", { name: key.name }) }) });
    }
    if (this.editTarget) {
      schema.push({ name: "target", required: true, ...text(t(`target_${key.kind}`), { helper: ctx.flags.goto_hint || "" }) });
    }
    schema.push(...this.fields);
    const actions = [];
    if (key.enter && !this.self) actions.push(row("folder-open-outline", t("open_level"), "", () => ctx.openLevel(key)));
    if (key.kind === "group") actions.push(row("home-group", t("edit_place"), "", () => this.editPlace()));
    if (!this.self && this.destinations().length) actions.push(row("cursor-move", t("move"), "", () => this.push({ id: "move" })));
    if (ctx.canReplace(key)) actions.push(row("swap-horizontal", t("replace"), "", () => ctx.replace(key)));
    actions.push(row("delete-outline", t("remove"), "", () => ctx.remove(key), { chevron: false }));
    const heard = (ctx.level.heard || []).filter((line) => this.self || (key.name && line.includes(key.name)));
    return {
      subtitle: t(`kind_${key.kind}`),
      body: [
        alert ? h("p", { class: alert.kind === "removed" ? "alert error" : "alert" }, notes[alert.kind] || alert.text) : null,
        key.entity_id ? ctx.entityLine(key.entity_id) : null,
        this.fixedLabel ? h("h3", { class: "sub" }, this.fixedLabel) : null,
        schema.length ? this.form(schema) : null,
        heard.length ? ctx.heardList(heard) : null,
        h("div", { class: "rows" }, actions),
      ],
      primary: { label: t("save"), run: () => this.save(), disabled: !this.dirty() },
    };
  }

  /** לאן אפשר להעביר: מקש אחר באותה רמה, או תפריט אחר. */
  destinations() {
    const t = this.t;
    const ctx = this.ctx;
    const key = this.key;
    const level = ctx.level;
    const home = parentOf(key.path);
    if (home !== level.path) return [];
    const out = [];
    for (const digit of "123456789") {
      if (digit === key.digit) continue;
      const there = level.keys[digit];
      out.push({
        label: there ? t("swap_with", { digit, name: there.name }) : t("move_key", { digit }),
        args: { to: ctx.path(digit) }, flash: digit,
      });
    }
    if (!["cap", "option"].includes(key.kind)) {
      const inside = (p) => p === key.path || p.startsWith(`${key.path}/`);
      for (const menu of level.targets || []) {
        if (menu.path === home || inside(menu.path)) continue;
        out.push({ label: t("into_menu", { name: menu.path ? `${menu.path} · ${menu.name}` : t("root") }), args: { to: menu.path, into: true } });
      }
    }
    return out;
  }

  move() {
    return {
      subtitle: this.t("move"),
      body: h("div", { class: "rows" }, this.destinations().map((d) => row(d.args.into ? "folder-outline" : "dialpad", d.label, "", () =>
        this.run(async () => {
          await this.ctx.mutate("move", { path: this.key.path, args: d.args }, { flash: d.flash || "" });
          this.ctx.done();
        }), { chevron: false }))),
    };
  }

  editPlace() {
    this.run(async () => {
      const group = await this.ctx.api("group", { path: this.key.path });
      this.group = group;
      const chosen = (this.place && this.place.target) || group.target;
      this.push({ id: "places", data: { area_id: chosen.area_id || [], floor_id: chosen.floor_id || [], label_id: chosen.label_id || [] } });
    });
  }

  places() {
    const t = this.t;
    return {
      subtitle: t("edit_place"),
      body: [h("p", { class: "help" }, t("place_help")), this.form(placeSchema(t))],
      primary: {
        label: t("next"),
        run: () => {
          const group = this.group;
          const target = placeTarget(this.step.data);
          // מכשירים שנבחרו ישירות אינם בטופס, ולכן נשארים כמו שהם.
          for (const k of ["device_id", "entity_id"]) if ((group.target[k] || []).length) target[k] = group.target[k];
          return this.run(async () => {
            const room = await this.ctx.api("place", { args: { target } });
            const list = members(room, group.domain);
            if (!list.length) throw new Error(t("no_rooms"));
            const out = new Set((this.place && this.place.exclude) || group.exclude || []);
            this.push({ id: "members", target, list, data: { kept: list.map((m) => m.entity_id).filter((id) => !out.has(id)) } });
          });
        },
      },
    };
  }

  members() {
    const t = this.t;
    const step = this.step;
    return {
      subtitle: t("members"),
      body: this.form([checklist("kept", this.group.name, step.list.map((m) => ({ value: m.entity_id, label: m.name })))]),
      primary: {
        label: t("next"),
        run: () => {
          const kept = new Set(step.data.kept || []);
          if (!kept.size) return this.fail(t("pick_one"));
          this.place = { target: step.target, exclude: step.list.map((m) => m.entity_id).filter((id) => !kept.has(id)) };
          this.stack = [this.stack[0]];
          return this.ctx.paint();
        },
      },
    };
  }

  save() {
    const draft = this.draft();
    const args = {};
    if ((draft.name || "") !== this.original.name) args.name = String(draft.name || "").trim();
    if (this.editTarget && (draft.target || "") !== this.original.target) args.target = String(draft.target || "").trim();
    if (this.fields.length) {
      const values = {};
      for (const f of this.fields) if (draft[f.name] !== undefined && draft[f.name] !== "") values[f.name] = draft[f.name];
      args.values = values;
    }
    if (this.place) args.place = this.place;
    return this.run(async () => {
      await this.ctx.mutate("update", { path: this.key.path, args }, { flash: this.self ? "" : this.key.digit });
      this.ctx.done();
    });
  }
}

export const parentOf = (path) => String(path || "").split("/").filter(Boolean).slice(0, -1).join("/");

// ------------------------------------------------------------------
// בנייה מהחדרים
// ------------------------------------------------------------------

export class BuildFlow extends Flow {
  constructor(ctx, rooms) {
    super(ctx);
    this.rooms = rooms;
    const free = Object.values(ctx.level.keys).filter((k) => !k).length;
    this.free = free;
    const areas = rooms.filter((r) => r.area_id).slice(0, free).map((r) => r.area_id);
    this.stack = [{ id: "rooms", data: { rooms: areas } }];
  }

  view() {
    const t = this.t;
    const options = this.rooms.map((r) => ({
      value: r.area_id, label: `${r.name} · ${r.kinds.map((k) => k.name).join(", ")}`,
    }));
    return {
      title: t("build"),
      body: [
        h("p", { class: "help" }, t("build_help", { n: this.free })),
        options.length ? this.form([checklist("rooms", t("rooms"), options)]) : h("p", { class: "muted" }, t("no_rooms")),
      ],
      primary: {
        label: t("build_go"),
        run: () => {
          const ids = this.step.data.rooms || [];
          if (!this.counted(ids)) return;
          this.run(async () => {
            await this.ctx.mutate("build", { path: this.ctx.level.path, args: { area_ids: ids } });
            this.ctx.done();
          });
        },
      },
    };
  }
}
