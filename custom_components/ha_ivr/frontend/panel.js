// לוח המקשים: עורך התפריט הטלפוני בסרגל הצד.
//
// העמוד מצייר לוח מקשים של טלפון, וכל מקש הוא מה שהמתקשר מקבל כשהוא
// מקיש עליו. ההחלטות נשארות בשרת (editor.py); כאן מציירים את הרמה
// שחזרה ושולחים את מה שהמשתמש ביקש. הטפסים והבוררים הם הרכיבים של
// Home Assistant עצמו (ha-form, ha-selector).
//
// המיקום בתפריט נמצא בכתובת: /ha-ivr/<קו>/<ספרות>. "אחורה" בדפדפן עולה רמה.

import { auto, cls, form, h, icon, iconButton, keyIcon, ltr, put } from "./dom.js";
import { isRTL, langOf, translator } from "./strings.js";
import { CSS } from "./styles.js";
import { AddFlow, BuildFlow, KeyFlow, parentOf } from "./flows.js";

const WS_TYPE = "ha_ivr/editor";
const STORE_KEY = "ha_ivr_entry";
const HELP_URL = "https://github.com/meni123/ha-ivr#readme";
const SETTINGS_URL = "/config/integrations/integration/ha_ivr";
const PAD = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];
// כמה תווים בשנייה מנוע דיבור אומר, בערך. רק להערכה.
const CHARS_PER_SECOND = 14;
const UNDO_MS = 6000;

const remembered = {
  get() {
    try {
      return localStorage.getItem(STORE_KEY);
    } catch (_err) {
      return null;
    }
  },
  set(value) {
    try {
      localStorage.setItem(STORE_KEY, value);
    } catch (_err) {
      // בלי אחסון מקומי פשוט לא זוכרים את הקו האחרון.
    }
  },
};

class HaIvrPanel extends HTMLElement {
  constructor() {
    super();
    const root = this.attachShadow({ mode: "open" });
    this._entries = null;
    this.blocked = new Set();
    this._entryId = "";
    this._level = null;
    this._failed = false;
    this._flash = "";
    this._flow = null;
    this._live = new Map();
    this._dialogLive = new Map();
    this._seq = 0;
    this.t = translator("he");
    this._page = h("div", { class: "page" });
    this._dialog = h("dialog", {
      oncancel: (ev) => {
        ev.preventDefault();
        this.askClose();
      },
      onclose: () => {
        this._flow = null;
      },
    });
    root.append(h("style", null, CSS), this._page, this._dialog);
  }

  // ------------------------------------------------------------------
  // מה ש-Home Assistant מעביר
  // ------------------------------------------------------------------

  // hass מתעדכן בכל שינוי בבית. מתעדכנים רק המכשירים שמוצגים, ורק אם השתנו.
  set hass(hass) {
    const before = this._hass;
    this._hass = hass;
    const lang = langOf(hass);
    const dir = isRTL(hass) ? "rtl" : "ltr";
    if (lang !== this._lang || dir !== this.getAttribute("dir")) {
      this._lang = lang;
      this.t = translator(lang);
      this.setAttribute("dir", dir);
      this.setAttribute("lang", lang);
      if (this._started) this.render();
    }
    if (!this._started) {
      this._started = true;
      this._start();
      return;
    }
    if (before && before.states !== hass.states) {
      for (const scope of [this._live, this._dialogLive]) {
        for (const [eid, paints] of scope) {
          if (before.states[eid] !== hass.states[eid]) paints.forEach((paint) => paint());
        }
      }
    }
  }

  get hass() {
    return this._hass;
  }

  set narrow(narrow) {
    if (Boolean(narrow) === Boolean(this._narrow)) return;
    this._narrow = Boolean(narrow);
    this.render();
  }

  set route(route) {
    this._route = route;
    if (this._entries) this._syncRoute();
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
    return this._level.path ? `${this._level.path}/${digit}` : digit;
  }

  // ------------------------------------------------------------------
  // השרת והכתובת
  // ------------------------------------------------------------------

  api(op, message = {}) {
    return this._hass.callWS({ type: WS_TYPE, op, entry_id: this._entryId, ...message });
  }

  errorText(err) {
    return (err && err.message) || this.t("err_failed");
  }

  async _start() {
    this._failed = false;
    this.render();
    try {
      const found = await this.api("entries");
      this._entries = found.entries || [];
      this.blocked = new Set(found.blocked || []);
    } catch (_err) {
      this._failed = true;
      this.render();
      return;
    }
    if (this._entries.length) await this._syncRoute();
    else this.render();
  }

  _routeParts() {
    return String((this._route && this._route.path) || "").split("/").filter(Boolean);
  }

  _navigate(entryId, path, { replace = false } = {}) {
    const prefix = (this._route && this._route.prefix) || "/ha-ivr";
    const url = `${prefix}/${entryId}${path ? `/${path}` : ""}`;
    if (location.pathname === url) return;
    history[replace ? "replaceState" : "pushState"](null, "", url);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace } }));
  }

  /** מה שבכתובת קובע מה מוצג. */
  async _syncRoute() {
    const parts = this._routeParts();
    let entryId = parts[0] || "";
    const path = parts.slice(1).join("/");
    if (!this._entries.some((e) => e.entry_id === entryId)) {
      const saved = remembered.get();
      entryId = (this._entries.find((e) => e.entry_id === saved) || this._entries[0]).entry_id;
      this._navigate(entryId, "", { replace: true });
      await this._load(entryId, "");
      return;
    }
    if (entryId === this._entryId && this._level && this._level.path === path) return;
    if (this._flow) this.done();
    await this._load(entryId, path);
  }

  async _load(entryId, path) {
    const seq = ++this._seq;
    this._entryId = entryId;
    remembered.set(entryId);
    try {
      const level = await this.api("level", { path });
      if (seq !== this._seq) return;
      this._level = level;
      // רמה שנעלמה: השרת מחזיר את הקרובה מעליה, והכתובת מתוקנת במקום.
      if (level.path !== path) this._navigate(entryId, level.path, { replace: true });
      this.render();
    } catch (err) {
      if (seq !== this._seq) return;
      this.toast(this.errorText(err));
      if (path) await this.go("");
    }
  }

  async go(path) {
    this._navigate(this._entryId, path);
    await this._load(this._entryId, path);
  }

  /** שינוי בשרת. השרת מחזיר את הרמה שמוצגת אחריו; `enter` נכנס לרמה שנוצרה. */
  async mutate(op, message, { view, flash = "", enter = "" } = {}) {
    const want = enter || (view === undefined ? this._level.path : view);
    const level = await this.api(op, { ...message, view: want });
    this._level = level;
    this._flash = flash;
    if (level.path !== this._routeParts().slice(1).join("/")) this._navigate(this._entryId, level.path, { replace: !enter });
    this.render();
    return level;
  }

  toast(message, action = null) {
    const detail = { message, duration: action ? UNDO_MS : 4000, dismissable: true };
    if (action) detail.action = action;
    this.dispatchEvent(new CustomEvent("hass-notification", { bubbles: true, composed: true, detail }));
  }

  // ------------------------------------------------------------------
  // מצב המכשירים
  // ------------------------------------------------------------------

  stateText(eid) {
    const obj = this._hass.states[eid];
    if (!obj) return "";
    try {
      return this._hass.formatEntityState(obj);
    } catch (_err) {
      return obj.state;
    }
  }

  // מכשיר שמוצג נרשם כאן, כדי שעדכון של hass יצבע רק אותו. ללוח ולחלון יש
  // רשימה נפרדת, ששתיהן מתאפסות כשהן מצוירות מחדש.
  _watch(eid, paint, scope = this._live) {
    if (!scope.has(eid)) scope.set(eid, []);
    scope.get(eid).push(paint);
  }

  /** אזהרה על מקש: מכשיר שהוסר, לא זמין, קבוצה ריקה או מקש שאינו מוקרא. */
  alertFor(key) {
    const t = this.t;
    if (key.entity_id) {
      const obj = this._hass.states[key.entity_id];
      if (!obj) return { kind: "removed", text: t("key_removed") };
      if (obj.state === "unavailable") return { kind: "unavailable", text: t("key_unavailable") };
    }
    if (key.kind === "cap" && key.gone) return { kind: "unavailable", text: t("key_unavailable") };
    if (key.kind === "group" && key.missing) return { kind: "unavailable", text: t("key_no_devices") };
    if (key.silent) return { kind: "quiet", text: t("key_quiet") };
    return null;
  }

  keySub(key) {
    const t = this.t;
    const n = Number(key.count || 0);
    const alert = this.alertFor(key);
    if (alert) return alert.text;
    switch (key.kind) {
      case "device": return [this.stateText(key.entity_id), t("count_actions", { n })].filter(Boolean).join(" · ");
      case "action": return key.does || "";
      case "goto": return ltr(key.target || "");
      case "submenu": return n ? t("count_keys", { n }) : t("key_empty");
      case "group": return t("count_devices", { n });
      case "cap":
        if (key.cap === "choice") return t("count_options", { n });
        if (key.cap === "number" && key.min != null && key.max != null) return ltr(`${key.min}–${key.max}`);
        return "";
      default: return "";
    }
  }

  entityLine(eid) {
    const state = h("span");
    const paint = () => state.replaceChildren(this._hass.states[eid] ? this.stateText(eid) : this.t("key_removed"));
    paint();
    this._watch(eid, paint, this._dialogLive);
    return h("div", { class: "entity" }, ltr(eid), state);
  }

  heardList(lines) {
    return h("ul", { class: "heard" }, lines.map((line) => h("li", null, auto(line))));
  }

  // ------------------------------------------------------------------
  // הציור
  // ------------------------------------------------------------------

  render() {
    this._live = new Map();
    this._page.className = cls("page", this._narrow && "narrow");
    this._page.replaceChildren(this._toolbar(), h("main", { class: "content" }, this._main()));
    this._flash = "";
    if (this._flow) this.paint();
  }

  _toolbar() {
    const t = this.t;
    const entries = this._entries || [];
    const level = this._level;
    const canBuild = level && !level.path && level.kind === "menu" && level.can_add && Object.values(level.keys).some((k) => !k);
    return h("header", { class: "toolbar" },
      this._narrow ? iconButton("menu", t("menu"), () => this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }))) : null,
      h("h1", null, t("title")),
      entries.length > 1 ? h("select", {
        "aria-label": t("line"),
        onchange: (ev) => {
          this._navigate(ev.target.value, "");
          this._load(ev.target.value, "");
        },
      }, entries.map((e) => h("option", { value: e.entry_id, selected: e.entry_id === this._entryId }, e.title))) : null,
      canBuild ? iconButton("home-group", t("build"), () => this.build()) : null,
      iconButton("cog-outline", t("line_settings"), () => {
        history.pushState(null, "", SETTINGS_URL);
        window.dispatchEvent(new CustomEvent("location-changed"));
      }),
      iconButton("help-circle-outline", t("help"), () => window.open(HELP_URL, "_blank", "noopener")));
  }

  _main() {
    const t = this.t;
    if (this._failed) {
      return h("div", { class: "empty" }, icon("alert-circle-outline"), h("h2", null, t("failed_title")),
        h("p", null, t("failed_text")), h("button", { type: "button", class: "btn primary", onclick: () => this._start() }, t("retry")));
    }
    if (this._entries && !this._entries.length) {
      return h("div", { class: "empty" }, icon("phone-plus-outline"), h("h2", null, t("empty_title")),
        h("p", null, t("empty_text")), h("a", { class: "btn primary", href: SETTINGS_URL }, t("empty_go")));
    }
    if (!this._level) return null;
    return [this._phone(), h("div", { class: "side" }, this._heardCard(), this._introCard(), this._looseCard())];
  }

  _phone() {
    const t = this.t;
    const level = this._level;
    const crumbs = level.crumbs || [];
    const depth = level.path ? level.path.split("/").length : 0;
    const where = h("div", { class: "where" },
      h("ol", { class: "crumbs", "aria-label": t("pad") }, crumbs.map((c, i) => h("li", null, i === crumbs.length - 1
        ? h("span", { "aria-current": "page" }, auto(i ? c.name : t("root")))
        : h("button", { type: "button", onclick: () => this.go(c.path) }, auto(i ? c.name : t("root")))))),
      level.self ? iconButton("pencil-outline", t("edit_here", { name: level.self.name }),
        () => this.openFlow(new KeyFlow(this, level.self, { self: true }))) : null);
    const pad = h("div", { class: "pad", role: "group", "aria-label": t("pad"), onkeydown: (ev) => this._arrows(ev) }, [
      ..."123456789".split("").map((digit) => this._slot(digit)),
      this._nav("*", depth > 0, t("key_home"), "home-outline", () => this.go("")),
      this._nav("0", depth > 0, t("key_back"), "keyboard-return", () => this.go(parentOf(level.path))),
      this._nav("#", false, t("key_reserved"), "", null),
    ]);
    return h("section", { class: "card" }, where, pad);
  }

  _nav(digit, on, name, iconName, onclick) {
    return h("div", { class: "slot" }, h("button", {
      type: "button", class: "key k-nav", "data-digit": digit, onclick: on ? onclick : null,
      "aria-disabled": on ? null : "true", "aria-label": `${this.t("key", { digit })}: ${name}`,
    }, h("span", { class: "k-digit" }, digit), on && iconName ? icon(iconName, "k-icon") : h("span"),
    h("span", { class: "k-name" }, on ? name : ""), h("span", { class: "k-sub" })));
  }

  _canAdd() {
    const level = this._level;
    if (level.kind === "menu") return level.can_add;
    return (level.addable || []).some((c) => !c.needs_fixed);
  }

  _slot(digit) {
    const t = this.t;
    const key = this._level.keys[digit];
    const head = h("span", { class: "k-digit" }, digit);
    if (!key) {
      const open = this._canAdd();
      return h("div", { class: "slot" }, h("button", {
        type: "button", class: "key k-empty", "data-digit": digit,
        onclick: open ? () => this.openFlow(new AddFlow(this, digit)) : null,
        "aria-disabled": open ? null : "true", "aria-label": `${t("key", { digit })}: ${t("key_empty")}`,
      }, head, icon("plus", "k-icon"), h("span", { class: "k-name" }, open ? t("key_add") : ""), h("span", { class: "k-sub" }, t("key_empty"))));
    }
    const sub = h("span", { class: "k-sub" });
    const el = h("button", {
      type: "button", "data-digit": digit, title: key.name,
      class: cls("key", ["submenu", "group"].includes(key.kind) && "k-stack", this._flash === digit && "k-flash"),
      onclick: () => (key.enter ? this.go(key.path) : this.openFlow(new KeyFlow(this, key))),
    }, head, keyIcon(this._hass, key), h("span", { class: "k-name" }, auto(key.name)), sub);
    const paint = () => {
      sub.replaceChildren();
      put(sub, [this.keySub(key)]);
      el.classList.toggle("k-removed", this.alertFor(key)?.kind === "removed");
      el.setAttribute("aria-label", [`${t("key", { digit })}: ${key.name}`, sub.textContent].filter(Boolean).join(". "));
    };
    paint();
    if (key.entity_id) this._watch(key.entity_id, paint);
    // מקש שנכנסים בו נערך בכפתור משלו.
    const edit = key.enter ? iconButton("pencil-outline", t("key_edit", { digit }),
      () => this.openFlow(new KeyFlow(this, key)), { class: "icon-btn k-edit" }) : null;
    return h("div", { class: "slot" }, el, edit);
  }

  // חצים בין המקשים, כמו בטלפון.
  _arrows(ev) {
    const at = PAD.indexOf(ev.target.dataset?.digit);
    const moves = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 3, ArrowUp: -3 };
    if (at < 0 || !(ev.key in moves)) return;
    const next = PAD[at + moves[ev.key]];
    if (!next || (Math.abs(moves[ev.key]) === 1 && Math.floor(at / 3) !== Math.floor((at + moves[ev.key]) / 3))) return;
    ev.preventDefault();
    this.shadowRoot.querySelector(`.pad [data-digit="${next}"]`)?.focus();
  }

  _heardCard() {
    const t = this.t;
    const level = this._level;
    const lines = level.heard || [];
    const filled = Object.values(level.keys).some(Boolean);
    const seconds = Math.max(1, Math.round(lines.join(" ").length / CHARS_PER_SECOND));
    return h("section", { class: "card" },
      h("h2", null, icon("volume-high"), t("heard"), lines.length ? h("small", null, t("heard_seconds", { n: seconds })) : null),
      lines.length ? this.heardList(lines) : h("p", { class: "muted" }, !level.path && !filled ? t("heard_empty_root") : t("heard_empty")));
  }

  _introCard() {
    const t = this.t;
    const level = this._level;
    if (level.intro === null || level.intro === undefined) return null;
    const data = { intro: level.intro };
    const save = h("button", { type: "button", class: "btn primary", disabled: true, onclick: () => this._guard(() =>
      this.mutate("update", { path: level.path, args: { intro: String(data.intro || "").trim() } })) }, t("save"));
    return h("section", { class: "card" },
      h("h2", null, icon("account-voice"), t("intro")),
      form(this._hass, [{ name: "intro", label: t("intro"), helper: t("intro_help"), selector: { text: {} } }], data, (value) => {
        data.intro = value.intro;
        save.disabled = String(value.intro || "").trim() === String(level.intro || "").trim();
      }),
      h("div", { class: "acts" }, save));
  }

  _looseCard() {
    const t = this.t;
    const level = this._level;
    const loose = level.loose || [];
    if (!loose.length) return null;
    const free = level.kind === "menu" && Object.values(level.keys).some((k) => !k);
    return h("section", { class: "card" },
      h("h2", null, icon("alert-outline"), t("loose")),
      h("p", { class: "help" }, t("loose_help")),
      h("div", { class: "rows" }, loose.map((item) => h("div", { class: "row" },
        h("span", { class: "txt" }, auto(item.title)),
        free ? iconButton("dialpad", t("key_add"), () => this._guard(() =>
          this.mutate("move", { args: { to: level.path, into: true, id: item.id } }))) : null,
        iconButton("delete-outline", t("remove"), () => this._guard(async () => {
          const result = await this.mutate("remove", { args: { id: item.id } });
          this._undoToast(result.undo);
        }))))));
  }

  // ------------------------------------------------------------------
  // החלון
  // ------------------------------------------------------------------

  async openFlow(flow) {
    if (this._flow && this._flow !== flow && this._flow.dirty() && !(await this._discard())) return;
    this._flow = flow;
    this.paint();
    if (!this._dialog.open) this._dialog.showModal();
    if (typeof flow.load === "function") await flow.load();
  }

  /** ציור החלון מהצעד הנוכחי של ה-flow. */
  paint() {
    const flow = this._flow;
    if (!flow) return;
    const t = this.t;
    this._dialogLive = new Map();
    const view = flow.view();
    this._dialog.classList.toggle("narrow", Boolean(this._narrow));
    this._footer = h("footer");
    const box = h("div", { class: "dlg" },
      h("header", null,
        flow.stack.length > 1 ? iconButton(this.getAttribute("dir") === "rtl" ? "arrow-right" : "arrow-left", t("back"), () => flow.back()) : null,
        h("div", { class: "titles" }, h("h2", null, auto(view.title)), view.subtitle ? h("p", null, auto(view.subtitle)) : null),
        iconButton("close", t("close"), () => this.askClose())),
      h("div", { class: "body" }, flow.error ? h("p", { class: "alert error", role: "alert" }, flow.error) : null, view.body),
      this._footer);
    this._fillFooter(view);
    this._dialog.replaceChildren(box);
  }

  /** רק הכפתורים, אחרי שינוי בטופס: ציור מחדש של הטופס היה מאבד את המיקוד. */
  paintFooter() {
    if (this._flow && this._footer) this._fillFooter(this._flow.view());
  }

  _fillFooter(view) {
    const t = this.t;
    const flow = this._flow;
    this._footer.replaceChildren();
    put(this._footer, [
      h("button", { type: "button", class: "btn", onclick: () => this.askClose() }, t("cancel")),
      view.primary ? h("button", {
        type: "button", class: "btn primary", disabled: flow.busy || view.primary.disabled,
        onclick: () => view.primary.run(),
      }, view.primary.label) : null,
    ]);
  }

  done() {
    this._flow = null;
    if (this._dialog.open) this._dialog.close();
  }

  async askClose() {
    if (this._flow && this._flow.dirty() && !(await this._discard())) return;
    this.done();
  }

  _discard() {
    const t = this.t;
    return this.confirm(t("discard_title"), t("discard_text"), t("discard_go"));
  }

  /** אישור בחלון קטן משלו, מעל החלון הפתוח. */
  confirm(title, text, ok) {
    return new Promise((resolve) => {
      const box = h("dialog", { onclose: () => {
        box.remove();
        resolve(box.returnValue === "ok");
      } }, h("div", { class: "dlg" },
        h("header", null, h("div", { class: "titles" }, h("h2", null, title))),
        h("div", { class: "body" }, h("p", { class: "muted" }, text)),
        h("footer", null,
          h("button", { type: "button", class: "btn", onclick: () => box.close("") }, this.t("cancel")),
          h("button", { type: "button", class: "btn primary", onclick: () => box.close("ok") }, ok))));
      this.shadowRoot.append(box);
      box.showModal();
    });
  }

  /** פעולה מחוץ לטופס: שגיאה בחלון אם הוא פתוח, אחרת בהודעה. */
  async _guard(work) {
    try {
      return await work();
    } catch (err) {
      if (this._flow) this._flow.fail(this.errorText(err));
      else this.toast(this.errorText(err));
      return null;
    }
  }

  _undoToast(token, message = this.t("removed")) {
    if (!token) {
      this.toast(message);
      return;
    }
    this.toast(message, {
      text: this.t("undo"),
      action: () => this._guard(async () => {
        await this.mutate("undo", { args: { token } });
        this.toast(this.t("restored"));
      }),
    });
  }

  // ------------------------------------------------------------------
  // פעולות על מקש, מתוך החלון
  // ------------------------------------------------------------------

  openLevel(key) {
    this.done();
    this.go(key.path);
  }

  canReplace(key) {
    return Boolean(key.entity_id) && ["device", "action"].includes(key.kind) && parentOf(key.path) === this._level.path;
  }

  replace(key) {
    this.done();
    this.openFlow(new AddFlow(this, key.digit, { replace: true }));
  }

  async remove(key) {
    const t = this.t;
    const inside = key.kind === "submenu" ? Number(key.count || 0) : 0;
    if (inside && !(await this.confirm(t("confirm_remove", { name: key.name }), t("confirm_remove_text", { n: inside }), t("remove")))) return;
    await this._guard(async () => {
      const level = await this.mutate("remove", { path: key.path }, {
        view: key.path === this._level.path ? parentOf(key.path) : this._level.path,
      });
      this.done();
      this._undoToast(level.undo);
    });
  }

  async build() {
    await this._guard(async () => {
      const found = await this.api("rooms");
      await this.openFlow(new BuildFlow(this, found.rooms || []));
    });
  }
}

export { HaIvrPanel };

if (!customElements.get("ha-ivr-panel")) customElements.define("ha-ivr-panel", HaIvrPanel);
