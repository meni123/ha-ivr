// העורך (בעמודה שליד הלוח, או בגיליון תחתון), דיאלוג אישור ותפריט צף.
//
// הדיאלוג הוא <dialog> אמיתי עם showModal(): הדפדפן שם אותו בשכבה
// העליונה, הופך את שאר העמוד ל-inert ומחזיק בו את המיקוד. אין כאן
// מלכודת מיקוד ידנית. Escape מגיע כאירוע cancel, ואותו אפשר לעצור רק
// אחרי פעולה של המשתמש (close watcher). לכן מי שמחזיק טיוטה צריך גם
// לשמור אותה כשהדיאלוג נסגר בכל זאת.

import { btn, cls, h, icon, iconBtn } from "./dom.js";

const canModal = (el) => typeof el.showModal === "function";

export class Dialog {
  /**
   * העורך מופיע בשני מקומות, באותו עיצוב בדיוק: במסך רחב — בעמודה שליד
   * הלוח (side), ובמסך צר — כגיליון תחתון (<dialog> מודאלי).
   *
   * @param {ShadowRoot} root המקום של הדיאלוג.
   * @param {object} hooks onCancel(ev), onClose(), onBackdrop(), onEscape(), onPlace().
   */
  constructor(root, hooks) {
    this.root = root;
    this.hooks = hooks;
    this.modal = h("dialog", { class: "dlg dlg-box", "aria-labelledby": "dlg-title" });
    this.modal.addEventListener("cancel", (ev) => hooks.onCancel(ev));
    this.modal.addEventListener("close", () => hooks.onClose());
    // לחיצה על הרקע מגיעה לאלמנט הדיאלוג עצמו, מחוץ לתוכן.
    this.modal.addEventListener("click", (ev) => {
      if (ev.target === this.modal) hooks.onBackdrop();
    });
    this.side = h("section", { class: "card dlg-box side-editor", role: "region", "aria-labelledby": "dlg-title" });
    // בעמודה אין close watcher: Escape מטופל כאן, ותמיד אפשר לעצור אותו.
    this.side.addEventListener("keydown", (ev) => {
      if (ev.key !== "Escape" || ev.defaultPrevented) return;
      ev.preventDefault();
      hooks.onEscape();
    });
    this.inline = false;
    this.opener = null;
  }

  /** המיכל הפעיל: העמודה, או הדיאלוג המודאלי. */
  get el() {
    return this.inline ? this.side : this.modal;
  }

  get open() {
    if (this.inline) return this.side.hasAttribute("open");
    return Boolean(this.modal.open || this.modal.hasAttribute("open"));
  }

  /** ציור התוכן. `view` הוא מה שה-flow החזיר. */
  paint(view, t, { refocus = false } = {}) {
    const head = h("div", { class: "dlg-head" },
      view.back
        ? iconBtn("arrow-left", t("back"), { "data-act": "dlg-back", class: "icon-btn back-icon" })
        : null,
      view.badge ? h("span", { class: "dlg-badge", "aria-hidden": "true" }, h("bdi", { dir: "ltr" }, view.badge)) : null,
      h("div", { class: "dlg-title" },
        h("h2", { id: "dlg-title" }, view.badge ? h("span", { class: "sr" }, `${t("key", { digit: view.badge })}: `) : null,
          h("bdi", null, view.title)),
        view.subtitle ? h("p", null, view.subtitle) : null),
      view.menu ? iconBtn("dots-vertical", t("more"), { "data-act": "dlg-menu" }) : null,
      view.back ? null : iconBtn("close", t("close"), { "data-act": "dlg-close" }));
    const body = h("div", { class: cls("dlg-body", view.fill && "fill") }, view.error
      ? h("div", { class: "alert error", role: "alert" }, icon("alert-circle-outline"), h("div", { class: "grow" }, view.error))
      : null, view.body);
    const foot = view.foot && view.foot.flat(Infinity).filter(Boolean).length
      ? h("div", { class: "dlg-foot" }, view.foot) : null;
    const inner = view.form
      ? h("form", { class: "dlg-form", "data-form": "dlg", novalidate: true }, body, foot)
      : [body, foot];
    const box = this.el;
    box.replaceChildren(head, ...[inner].flat().filter(Boolean));
    box.className = this.inline
      ? cls("card dlg-box side-editor", view.fill && "fill")
      : cls("dlg dlg-box", view.small && "small", view.fill && "fill");
    if (refocus) this.focus();
  }

  focus() {
    const box = this.el;
    const target = box.querySelector("[data-focus]")
      || box.querySelector(".dlg-body input, .dlg-body select, .dlg-body button")
      || box.querySelector(".dlg-head button");
    if (target && typeof target.focus === "function") target.focus({ preventScroll: true });
  }

  /** פתיחה. `inline` נקבע לפני הציור הראשון, ולא משתנה עד הסגירה. */
  show(opener) {
    if (this.open) return;
    this.opener = opener || null;
    if (this.inline) {
      this.side.setAttribute("open", "");
      this.hooks.onPlace();
    } else {
      if (!this.modal.isConnected) this.root.append(this.modal);
      if (canModal(this.modal)) this.modal.showModal();
      else this.modal.setAttribute("open", "");
    }
    this.focus();
    if (this.inline && typeof this.side.scrollIntoView === "function") {
      this.side.scrollIntoView({ block: "nearest" });
    }
  }

  close() {
    if (!this.open) return;
    if (this.inline) {
      this.side.removeAttribute("open");
      this.hooks.onClose();
      return;
    }
    if (typeof this.modal.close === "function") this.modal.close();
    else {
      this.modal.removeAttribute("open");
      this.hooks.onClose();
    }
  }

  /** המיקוד חוזר למה שפתח את העורך, אם הוא עדיין בעמוד. */
  restoreFocus() {
    const opener = this.opener;
    this.opener = null;
    if (opener && opener.isConnected && typeof opener.focus === "function") {
      opener.focus({ preventScroll: true });
      return true;
    }
    return false;
  }

  shake() {
    const box = this.el;
    box.classList.remove("shake");
    // קריאה ל-offsetWidth מאתחלת את האנימציה.
    void box.offsetWidth;
    box.classList.add("shake");
  }
}

/**
 * דיאלוג אישור, כמו showConfirmationDialog: כותרת שהיא שאלה, תיאור,
 * [ביטול] ופועל. המיקוד מתחיל על "ביטול". אין X, והרקע אינו סוגר.
 */
export const confirmDialog = (root, { title, text, ok, cancel, danger = false }) => new Promise((resolve) => {
  const el = h("dialog", { class: "dlg small", role: "alertdialog", "aria-labelledby": "cf-title", "aria-describedby": "cf-text" });
  let answer = false;
  const done = (value) => {
    answer = value;
    if (typeof el.close === "function") el.close();
    else finish();
  };
  const finish = () => {
    el.remove();
    resolve(answer);
  };
  const no = btn("btn plain", { "data-focus": true }, cancel);
  const yes = btn(cls("btn", danger ? "danger" : "accent"), null, ok);
  no.addEventListener("click", () => done(false));
  yes.addEventListener("click", () => done(true));
  el.addEventListener("close", finish);
  el.addEventListener("cancel", () => {
    answer = false;
  });
  el.append(
    h("div", { class: "dlg-head" }, h("div", { class: "dlg-title" }, h("h2", { id: "cf-title" }, h("bdi", null, title)))),
    h("div", { class: "dlg-body" }, text ? h("p", { id: "cf-text", class: "muted" }, text) : null),
    h("div", { class: "dlg-foot" }, no, yes),
  );
  root.append(el);
  if (canModal(el)) el.showModal();
  else el.setAttribute("open", "");
  no.focus();
});

/**
 * תפריט צף (popover). פריט עם `sub` מחליף את התוכן ברשימה שלו, עם
 * שורת חזרה. בחירה בפריט סוגרת את התפריט וקוראת ל-onPick(value).
 */
export class Menu {
  constructor(root, t) {
    this.root = root;
    this.t = t;
    this.el = h("div", { class: "menu", role: "menu", popover: "auto" });
    this.el.addEventListener("click", (ev) => this._click(ev));
    this.el.addEventListener("keydown", (ev) => this._key(ev));
    this.el.addEventListener("toggle", (ev) => {
      if (ev.newState === "closed") this._closed();
    });
    this.items = [];
    this.stack = [];
  }

  get open() {
    try {
      return this.el.matches(":popover-open") || this.el.hasAttribute("open");
    } catch (_err) {
      return this.el.hasAttribute("open");
    }
  }

  show(anchor, items, onPick) {
    if (!this.el.isConnected) this.root.append(this.el);
    this.anchor = anchor;
    this.onPick = onPick;
    this.stack = [items];
    this._paint();
    if (typeof this.el.showPopover === "function") {
      try {
        if (!this.open) this.el.showPopover();
      } catch (_err) {
        this.el.setAttribute("open", "");
      }
    } else {
      this.el.setAttribute("open", "");
    }
    this._place();
    this.el.querySelector(".mi:not([aria-disabled='true'])")?.focus();
  }

  hide() {
    if (typeof this.el.hidePopover === "function") {
      try {
        this.el.hidePopover();
      } catch (_err) {
        // לא היה פתוח.
      }
    }
    if (this.el.hasAttribute("open")) {
      this.el.removeAttribute("open");
      this._closed();
    }
  }

  _closed() {
    const anchor = this.anchor;
    this.anchor = null;
    if (anchor && anchor.isConnected && typeof anchor.focus === "function") anchor.focus({ preventScroll: true });
  }

  _paint() {
    const items = this.stack[this.stack.length - 1];
    const rows = [];
    if (this.stack.length > 1) {
      rows.push(btn("mi", { role: "menuitem", "data-mi": "back" }, icon("arrow-left", "back-icon"), h("span", { class: "txt" }, this.t("back"))),
        h("div", { class: "sep", role: "separator" }));
    }
    items.forEach((item, index) => {
      if (item.sep) {
        rows.push(h("div", { class: "sep", role: "separator" }));
        return;
      }
      if (item.header) {
        rows.push(h("div", { class: "mh", role: "presentation" }, item.header));
        return;
      }
      rows.push(btn(cls("mi", item.danger && "danger"), {
        role: "menuitem", "data-mi": String(index),
        "aria-disabled": item.disabled ? "true" : null,
        "aria-haspopup": item.sub ? "menu" : null,
      },
      item.icon ? icon(item.icon) : null,
      h("span", { class: "txt" }, h("bdi", null, item.label)),
      item.sub ? icon("chevron-right", "chev") : null));
    });
    this.el.replaceChildren(...rows);
  }

  _place() {
    const anchor = this.anchor;
    if (!anchor || typeof anchor.getBoundingClientRect !== "function") return;
    const box = anchor.getBoundingClientRect();
    const own = this.el.getBoundingClientRect ? this.el.getBoundingClientRect() : { width: 240, height: 200 };
    const vw = typeof innerWidth === "number" ? innerWidth : 1024;
    const vh = typeof innerHeight === "number" ? innerHeight : 768;
    const rtl = getComputedStyle && getComputedStyle(anchor).direction === "rtl";
    let left = rtl ? box.left : box.right - own.width;
    left = Math.max(8, Math.min(left, vw - own.width - 8));
    let top = box.bottom + 4;
    if (top + own.height > vh - 8) top = Math.max(8, box.top - own.height - 4);
    this.el.style.left = `${Math.round(left)}px`;
    this.el.style.top = `${Math.round(top)}px`;
  }

  _click(ev) {
    const el = ev.target.closest ? ev.target.closest("[data-mi]") : null;
    if (!el || el.getAttribute("aria-disabled") === "true") return;
    if (el.dataset.mi === "back") {
      this.stack.pop();
      this._paint();
      this.el.querySelector(".mi")?.focus();
      return;
    }
    const item = this.stack[this.stack.length - 1][Number(el.dataset.mi)];
    if (!item) return;
    if (item.sub) {
      this.stack.push(item.sub);
      this._paint();
      this._place();
      this.el.querySelector(".mi:not([data-mi='back'])")?.focus();
      return;
    }
    const pick = this.onPick;
    this.anchor = this.anchor || null;
    this.hide();
    if (pick) pick(item.value);
  }

  // חצים למעלה ולמטה בין הפריטים, כמו בתפריט של מערכת ההפעלה.
  _key(ev) {
    const items = [...this.el.querySelectorAll(".mi:not([aria-disabled='true'])")];
    const at = items.indexOf(this.root.activeElement);
    let next = -1;
    if (ev.key === "ArrowDown") next = (at + 1) % items.length;
    else if (ev.key === "ArrowUp") next = (at - 1 + items.length) % items.length;
    else if (ev.key === "Home") next = 0;
    else if (ev.key === "End") next = items.length - 1;
    else if (ev.key === "Escape" && !this.el.showPopover) {
      this.hide();
      return;
    }
    if (next < 0 || !items.length) return;
    ev.preventDefault();
    items[next].focus();
  }
}
