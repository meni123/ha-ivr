// עזרי DOM קטנים. בלי innerHTML: כל טקסט נכנס כצומת טקסט.

/**
 * יצירת אלמנט. מפתח שמתחיל ב-on הוא מאזין, `props` נכנס כמאפיינים
 * (hass, schema, data של רכיבי HA), וערך ריק או false מדולג.
 */
export const h = (tag, attrs, ...kids) => {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "props") Object.assign(el, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  put(el, kids);
  return el;
};

/** הוספת ילדים: מערכים נפרסים, ריקים מדולגים, מחרוזות הופכות לטקסט. */
export const put = (el, kids) => {
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false || kid === "") continue;
    el.append(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
  }
  return el;
};

export const cls = (...names) => names.filter(Boolean).join(" ");

// טקסט שהכיוון שלו נקבע לפי תוכנו (שם באנגלית בתוך עברית), ומזהה טכני משמאל לימין.
export const auto = (text) => h("bdi", null, String(text ?? ""));
export const ltr = (text) => h("bdi", { dir: "ltr" }, String(text ?? ""));

export const icon = (name, className = "") => h("ha-icon", { icon: `mdi:${name}`, class: className || null });

export const button = (label, onclick, { kind = "", iconName = "", disabled = false, attrs = {} } = {}) =>
  h("button", { type: "button", class: cls("btn", kind), onclick, disabled, ...attrs },
    iconName ? icon(iconName) : null, label);

export const iconButton = (name, label, onclick, attrs = {}) =>
  h("button", { type: "button", class: "icon-btn", "aria-label": label, title: label, onclick, ...attrs }, icon(name));

/** שורה ברשימת בחירה: אייקון, כותרת ושורת משנה. */
export const row = (iconName, title, sub, onclick, { chevron = true } = {}) =>
  h("button", { type: "button", class: "row", onclick },
    iconName ? icon(iconName) : null,
    h("span", { class: "txt" }, h("span", null, title), sub ? h("small", null, sub) : null),
    chevron ? icon("chevron-left", "chev") : null);

/** ‏ha-form של Home Assistant: כל סוג שדה מצויר כמו במסך האוטומציות. */
export const form = (hass, schema, data, onchange) => h("ha-form", {
  props: {
    hass,
    schema,
    data,
    computeLabel: (s) => s.label ?? s.name,
    computeHelper: (s) => s.helper ?? "",
  },
  // ‏ha-form מחושב מ-data, ולכן הערך החדש חוזר אליו. בלי זה שינוי שני דורס את הראשון.
  "onvalue-changed": (ev) => {
    ev.currentTarget.data = ev.detail.value;
    onchange(ev.detail.value);
  },
});

const KIND_ICONS = {
  submenu: "folder-outline",
  goto: "phone-forward",
  assistant: "account-voice",
  alerts: "bell-outline",
  option: "radiobox-marked",
  group: "home-group",
};

const CAP_ICONS = {
  simple: "gesture-tap",
  status: "volume-high",
  choice: "format-list-bulleted",
  number: "numeric",
  fixed: "tune-variant",
};

/** האייקון של מקש. מקש של ישות מקבל את אייקון המצב האמיתי שלה. */
export const keyIcon = (hass, key) => {
  const stateObj = key.entity_id && hass.states ? hass.states[key.entity_id] : null;
  if (stateObj && (key.kind === "device" || key.kind === "action")) {
    return h("ha-state-icon", { class: "k-icon", props: { hass, stateObj } });
  }
  if (key.kind === "cap") return icon(CAP_ICONS[key.cap] || CAP_ICONS.simple, "k-icon");
  return icon(KIND_ICONS[key.kind] || "devices", "k-icon");
};
