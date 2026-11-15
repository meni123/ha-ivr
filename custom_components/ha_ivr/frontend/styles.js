// העיצוב של הלוח: הטוקנים של Home Assistant 2026.11, ולכל אחד ערך גיבוי
// לגרסה שאין בה אותו. כל הצבעים מהערכה של HA, כך שמצב כהה ועיצוב
// אישי עובדים מעצמם. רק מאפיינים לוגיים (inline/block), כדי שהכיוון
// יתהפך עם השפה.

export const CSS = `
:host {
  display: block;
  min-height: 100%;
  --sp1: var(--ha-space-1, 4px);
  --sp2: var(--ha-space-2, 8px);
  --sp3: var(--ha-space-3, 12px);
  --sp4: var(--ha-space-4, 16px);
  --sp5: var(--ha-space-5, 20px);
  --sp6: var(--ha-space-6, 24px);
  --sp8: var(--ha-space-8, 32px);
  --tap: 44px;
  --r-sm: var(--ha-border-radius-sm, 4px);
  --r-md: var(--ha-border-radius-md, 8px);
  --r-lg: var(--ha-card-border-radius, var(--ha-border-radius-lg, 12px));
  --r-xl: var(--ha-border-radius-xl, 16px);
  --r-pill: var(--ha-border-radius-pill, 9999px);
  --fs-xs: var(--ha-font-size-xs, 10px);
  --fs-s: var(--ha-font-size-s, 12px);
  --fs-m: var(--ha-font-size-m, 14px);
  --fs-l: var(--ha-font-size-l, 16px);
  --fs-xl: var(--ha-font-size-xl, 20px);
  --fs-2xl: var(--ha-font-size-2xl, 24px);
  --fw-normal: var(--ha-font-weight-normal, 400);
  --fw-medium: var(--ha-font-weight-medium, 500);
  --fw-bold: var(--ha-font-weight-bold, 600);
  --lh: var(--ha-line-height-normal, 1.5);
  --lh-tight: var(--ha-line-height-condensed, 1.2);
  --fg: var(--ha-color-text-primary, var(--primary-text-color, #141414));
  --fg2: var(--ha-color-text-secondary, var(--secondary-text-color, #5e5e5e));
  --fg3: var(--ha-color-text-disabled, var(--disabled-text-color, #9e9e9e));
  --line: var(--ha-card-border-color, var(--divider-color, rgba(0, 0, 0, .12)));
  --card: var(--ha-card-background, var(--card-background-color, #fff));
  --surface: var(--ha-color-surface-low, var(--secondary-background-color, #f4f4f4));
  --field: var(--ha-color-form-background, var(--surface));
  --brand: var(--primary-color, #009ac7);
  --on-brand: var(--ha-color-on-primary-loud, var(--text-primary-color, #fff));
  --brand-quiet: var(--ha-color-fill-primary-quiet-resting, color-mix(in srgb, var(--brand) 10%, transparent));
  --brand-quiet-hover: var(--ha-color-fill-primary-quiet-hover, color-mix(in srgb, var(--brand) 16%, transparent));
  --neutral-quiet: var(--ha-color-fill-neutral-quiet-resting, color-mix(in srgb, var(--fg) 5%, transparent));
  --neutral-hover: var(--ha-color-fill-neutral-quiet-hover, color-mix(in srgb, var(--fg) 9%, transparent));
  --danger: var(--ha-color-on-danger-quiet, var(--error-color, #db4437));
  --danger-loud: var(--ha-color-fill-danger-loud-resting, var(--error-color, #db4437));
  --danger-quiet: var(--ha-color-fill-danger-quiet-resting, color-mix(in srgb, var(--error-color, #db4437) 10%, transparent));
  --warn: var(--ha-color-on-warning-quiet, var(--warning-color, #ffa600));
  --warn-quiet: var(--ha-color-fill-warning-quiet-resting, color-mix(in srgb, var(--warning-color, #ffa600) 14%, transparent));
  --ok-quiet: var(--ha-color-fill-success-quiet-resting, color-mix(in srgb, var(--success-color, #43a047) 12%, transparent));
  --ok: var(--ha-color-on-success-quiet, var(--success-color, #43a047));
  --assist: var(--accent-color, #ff9800);
  --focus: var(--ha-color-focus, var(--brand));
  --shadow-m: var(--ha-box-shadow-m, 0 4px 12px rgba(0, 0, 0, .14));
  --shadow-l: var(--ha-box-shadow-l, 0 8px 28px rgba(0, 0, 0, .2));
  --fast: var(--ha-animation-duration-fast, 150ms);
  --normal: var(--ha-animation-duration-normal, 250ms);
  color: var(--fg);
  font-family: var(--ha-font-family-body, Roboto, "Noto Sans Hebrew", system-ui, sans-serif);
  font-size: var(--fs-m);
  line-height: var(--lh);
  -webkit-font-smoothing: antialiased;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
button, input, select, textarea { font: inherit; color: inherit; }
button { cursor: pointer; }
button:disabled, [aria-disabled="true"] { cursor: default; }
:focus { outline: none; }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.icon { width: 24px; height: 24px; flex: none; fill: currentColor; }
.grow { flex: 1 1 auto; min-width: 0; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.muted { color: var(--fg2); }
.t-help { color: var(--fg2); font-size: var(--fs-s); margin: 0; }

/* --- סרגל עליון, כמו hass-subpage --- */
.toolbar {
  position: sticky; inset-block-start: 0; z-index: 4;
  display: flex; align-items: center; gap: var(--sp1);
  min-block-size: var(--header-height, 56px);
  padding: var(--sp2) var(--sp3);
  background: var(--ha-panel-toolbar-background, var(--app-header-background-color, var(--brand)));
  color: var(--app-header-text-color, var(--on-brand));
  border-block-end: var(--app-header-border-bottom, none);
}
.toolbar .title {
  margin: 0; margin-inline-start: var(--sp6);
  font-size: var(--fs-xl); font-weight: var(--fw-normal); line-height: var(--lh-tight);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.narrow .toolbar .title { margin-inline-start: var(--sp2); }
.toolbar .icon-btn { color: inherit; }
.line-pick {
  margin-inline-start: var(--sp3); max-inline-size: 260px;
  block-size: 36px; padding-inline: var(--sp3) var(--sp8);
  border: 1px solid color-mix(in srgb, currentColor 30%, transparent); border-radius: var(--r-pill);
  background: color-mix(in srgb, currentColor 8%, transparent); color: inherit;
}
.line-pick option { color: var(--fg); background: var(--card); }

/* --- כפתורים --- */
.icon-btn {
  display: inline-grid; place-items: center; flex: none;
  inline-size: var(--tap); block-size: var(--tap); padding: 0;
  border: 0; border-radius: var(--r-pill); background: transparent; color: var(--fg2);
  transition: background var(--fast);
}
.icon-btn:hover { background: var(--neutral-hover); }
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: var(--sp2);
  min-block-size: 40px; padding: 0 var(--sp4);
  border: 0; border-radius: var(--r-pill);
  font-weight: var(--fw-medium); white-space: nowrap;
  transition: background var(--fast), color var(--fast);
}
.btn .icon { width: 20px; height: 20px; }
.btn.accent { background: var(--brand); color: var(--on-brand); }
.btn.accent:hover { background: color-mix(in srgb, var(--brand) 88%, #000); }
.btn.plain { background: transparent; color: var(--brand); }
.btn.plain:hover { background: var(--brand-quiet); }
.btn.quiet { background: var(--brand-quiet); color: var(--brand); }
.btn.quiet:hover { background: var(--brand-quiet-hover); }
.btn.danger { background: var(--danger-loud); color: #fff; }
.btn:disabled { background: var(--neutral-quiet); color: var(--fg3); }
.btn.plain:disabled { background: transparent; }
.btn.busy { pointer-events: none; }
.btn.busy::before {
  content: ""; inline-size: 16px; block-size: 16px; border-radius: 50%;
  border: 2px solid currentColor; border-inline-end-color: transparent;
  animation: spin 0.8s linear infinite;
}
.link { border: 0; background: none; padding: var(--sp1) var(--sp2); color: var(--brand); font-size: var(--fs-s); border-radius: var(--r-sm); }
.link:hover { text-decoration: underline; }

/* --- פריסה --- */
.page { container: page / inline-size; }
.content {
  max-inline-size: var(--ha-content-width-wide, 1280px);
  margin-inline: auto;
  padding: var(--sp6) var(--ha-content-gutter, var(--sp4)) var(--sp8);
  display: grid; gap: var(--sp4); align-items: start;
  grid-template-columns: minmax(320px, 440px) minmax(0, 1fr);
}
.side { display: grid; gap: var(--sp4); min-inline-size: 0; }
@container page (max-width: 719px) {
  .content { grid-template-columns: minmax(0, 1fr); padding-block-start: var(--sp4); }
  .phone { inline-size: 100%; max-inline-size: 440px; justify-self: center; }
  .side { inline-size: 100%; max-inline-size: 440px; justify-self: center; }
}
.card {
  background: var(--card); border-radius: var(--r-lg);
  border: var(--ha-card-border-width, 1px) solid var(--line);
  box-shadow: var(--ha-card-box-shadow, none);
}
.card-head { display: flex; align-items: center; gap: var(--sp2); padding: var(--sp4) var(--sp4) 0; }
.card-head .icon { color: var(--fg2); width: 20px; height: 20px; }
.card-head h2 { margin: 0; font-size: var(--fs-l); font-weight: var(--fw-medium); }
.card-body { padding: var(--sp3) var(--sp4) var(--sp4); display: grid; gap: var(--sp3); }
.card-foot { display: flex; justify-content: flex-end; gap: var(--sp2); padding: 0 var(--sp4) var(--sp4); }

/* --- פירורי לחם --- */
.phone { padding: var(--sp3); display: grid; gap: var(--sp3); }
.where { display: flex; align-items: center; gap: var(--sp1); min-block-size: var(--tap); padding-inline-start: var(--sp1); }
.crumbs { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; list-style: none; margin: 0; padding: 0; min-inline-size: 0; flex: 1; }
.crumbs li { display: flex; align-items: center; min-inline-size: 0; }
.crumbs li + li::before { content: "›"; color: var(--fg3); padding-inline: var(--sp1); }
.crumb {
  border: 0; background: none; padding: var(--sp1) var(--sp2); border-radius: var(--r-sm);
  color: var(--brand); font-size: var(--fs-m); max-inline-size: 16ch;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
a.crumb { text-decoration: none; }
.crumb:hover { background: var(--brand-quiet); }
.crumb[aria-current] { color: var(--fg); font-weight: var(--fw-medium); background: none; }

/* --- לוח המקשים --- */
.pad { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--sp2); direction: ltr; }
.slot { position: relative; min-inline-size: 0; }
.key {
  position: relative; inline-size: 100%; aspect-ratio: 1 / 1; min-block-size: var(--tap);
  display: grid; grid-template-rows: auto 1fr auto auto; justify-items: center; align-items: center;
  gap: 2px; padding: var(--sp2) var(--sp1) var(--sp2);
  border: 1px solid var(--line); border-radius: var(--r-xl);
  background: var(--card); color: var(--fg); text-align: center;
  transition: background var(--fast), border-color var(--fast), transform var(--fast);
}
.key:hover:not([aria-disabled="true"]) { background: var(--neutral-hover); }
.key:active:not([aria-disabled="true"]) { transform: scale(0.98); }
.k-digit {
  justify-self: start; padding-inline: var(--sp1);
  font-size: var(--fs-l); font-weight: var(--fw-bold); line-height: 1; color: var(--fg2);
  font-variant-numeric: tabular-nums;
}
.k-icon { width: 28px; height: 28px; color: var(--brand); }
.k-name, .k-sub {
  display: block; max-inline-size: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding-inline: var(--sp1);
}
.k-name { font-size: var(--fs-m); font-weight: var(--fw-medium); line-height: var(--lh-tight); }
.k-sub { font-size: var(--fs-s); color: var(--fg2); min-block-size: 1.2em; line-height: var(--lh-tight); }
.k-stack { background: var(--brand-quiet); border-color: transparent; }
.k-stack:hover:not([aria-disabled="true"]) { background: var(--brand-quiet-hover); }
.k-assist .k-icon { color: var(--assist); }
.k-fixed .k-icon, .k-dictate .k-icon { color: var(--fg2); }
.k-empty { border-style: dashed; background: transparent; color: var(--fg2); }
.k-empty .k-icon { color: var(--fg3); }
.k-empty .k-name { font-weight: var(--fw-normal); }
.k-nav { background: var(--surface); border-color: transparent; }
.k-nav .k-icon { color: var(--fg2); }
.key[aria-disabled="true"] { opacity: 0.5; }
.k-nav[aria-disabled="true"] { opacity: 0.45; }
.k-removed { border-color: var(--danger); }
.k-removed .k-icon { color: var(--danger); }
.k-unavailable .k-icon { color: var(--fg3); }
.key.sel { border: 2px solid var(--brand); background: var(--brand-quiet); }
.key.over { border: 2px solid var(--brand); background: var(--brand-quiet-hover); }
.key.dragging { opacity: 0.4; }
.key.flash { animation: flash 1.2s ease-out; }
.key.skeleton { border-style: solid; background: var(--surface); animation: pulse 1.4s ease-in-out infinite; }
.k-more {
  position: absolute; inset-block-start: 2px; inset-inline-end: 2px;
  inline-size: 36px; block-size: 36px;
  opacity: 0; transition: opacity var(--fast);
}
.k-more .icon { width: 20px; height: 20px; }
.slot:hover .k-more, .slot:focus-within .k-more, .k-more:focus-visible { opacity: 1; }
@media (hover: none) { .k-more { opacity: 1; } }
.k-grip { position: absolute; inset-block-start: 8px; inset-inline-start: 50%; transform: translateX(-50%); color: var(--fg3); opacity: 0; }
.k-grip .icon { width: 16px; height: 16px; }
@media (pointer: fine) { .slot:hover .k-grip { opacity: 1; } }
@container page (max-width: 399px) {
  .key { aspect-ratio: 5 / 6; padding-inline: 2px; }
  .k-icon { width: 24px; height: 24px; }
  .k-name { font-size: var(--fs-s); }
  .k-sub { font-size: var(--fs-xs); }
}

/* --- תגיות --- */
.tag {
  display: inline-flex; align-items: center; gap: 2px; max-inline-size: 100%;
  padding: 0 var(--sp2); border-radius: var(--r-pill);
  font-size: var(--fs-xs); font-weight: var(--fw-medium); line-height: 18px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.tag .icon { width: 12px; height: 12px; }
.tag-removed { background: var(--danger-quiet); color: var(--danger); }
.tag-unavailable, .tag-quiet { background: var(--neutral-quiet); color: var(--fg2); }

/* --- כרטיסי הצד --- */
.heard { list-style: none; margin: 0; padding: var(--sp3) var(--sp4); display: grid; gap: var(--sp1);
  background: var(--surface); border-radius: var(--r-md); }
.heard li { display: flex; gap: var(--sp2); }
.heard li::before { content: "“"; color: var(--fg3); }
.heard-meta { color: var(--fg2); font-size: var(--fs-s); margin-inline-start: auto; }
.rows { display: grid; }
.row { display: flex; align-items: center; gap: var(--sp2); min-block-size: 48px; border-block-start: 1px solid var(--line); }
.row:first-child { border-block-start: 0; }

/* --- שדות --- */
.field { display: grid; gap: var(--sp1); }
.field > span.lbl { font-size: var(--fs-s); font-weight: var(--fw-medium); color: var(--fg2); }
.field .req { color: var(--fg3); font-weight: var(--fw-normal); }
.field input, .field select, .search input {
  inline-size: 100%; min-block-size: 48px; padding: var(--sp2) var(--sp3);
  border: 1px solid var(--line); border-block-end: 1px solid var(--fg2); border-radius: var(--r-md) var(--r-md) var(--r-sm) var(--r-sm);
  background: var(--field); transition: border-color var(--fast);
}
.field input:hover, .field select:hover { border-block-end-color: var(--fg); }
.field input:focus-visible, .field select:focus-visible, .search input:focus-visible {
  outline: none; border-block-end: 2px solid var(--brand);
}
.field.bad input, .field.bad select { border-block-end: 2px solid var(--danger); }
.field .err { color: var(--danger); font-size: var(--fs-s); margin: 0; }
.search { position: relative; }
.search .icon { position: absolute; inset-block-start: 12px; inset-inline-start: 12px; color: var(--fg2); }
.search input { padding-inline-start: 44px; }

/* --- בורר, כמו ha-target-picker --- */
.dlg-box .search input {
  min-block-size: 52px; border: 1px solid var(--ha-color-border-neutral-quiet, var(--line));
  border-radius: var(--r-lg); background: var(--card); padding-inline-end: 44px;
}
.dlg-box .search input:hover { border-color: var(--fg2); }
.dlg-box .search input:focus-visible { outline: none; border: 2px solid var(--brand); padding-inline-start: 43px; }
.search .icon { inset-block-start: 14px; }
.chips { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp2); }
.chip {
  display: inline-flex; align-items: center; gap: var(--sp2); block-size: 32px; padding: 0 var(--sp4);
  border: 1px solid var(--ha-color-border-neutral-quiet, var(--line)); border-radius: var(--r-md);
  background: transparent; color: var(--fg); font-size: var(--fs-m); font-weight: var(--fw-medium);
}
.chip .icon { width: 18px; height: 18px; margin-inline-start: -4px; }
.chip:hover { background: var(--neutral-hover); }
.chip.on { background: var(--brand-quiet); border-color: transparent; color: var(--brand); }
.chip-sep { inline-size: 1px; block-size: 32px; background: var(--line); }
/* השדה והשבבים נשארים במקום, ורק הרשימה גוללת — כמו בבורר של HA. */
.dlg-body.fill { overflow: hidden; display: flex; flex-direction: column; gap: var(--sp3); padding-block-end: 0; }
.dlg-body.fill > .picker { flex: 1 1 auto; min-block-size: 0; overflow: auto; overscroll-behavior: contain; align-content: start; }
.side-editor.fill { block-size: calc(100dvh - var(--header-height, 56px) - var(--sp8)); }
dialog.dlg.fill { block-size: min(90dvh, 900px); }
.pick-head {
  position: sticky; inset-block-start: 0; z-index: 1;
  padding: var(--sp2) var(--sp4); background: var(--ha-color-fill-neutral-quiet-resting, var(--surface));
  color: var(--fg2); font-size: var(--fs-m); font-weight: var(--fw-medium);
}
.pick-head + .pick { border-block-start: 0; }
.pick-ha-icon { inline-size: 32px; block-size: 32px; flex: none; display: inline-flex; align-items: center; justify-content: center; color: var(--state-icon-color, var(--fg2)); --mdc-icon-size: 24px; }
.search input::-webkit-search-cancel-button { display: none; }
.search .clear { position: absolute; inset-block-start: 2px; inset-inline-end: 2px; }
.picker { display: grid; margin-inline: calc(var(--sp4) * -1); }
.pick {
  display: flex; align-items: center; gap: var(--sp4); inline-size: 100%;
  min-block-size: var(--ha-combo-box-item-two-line-min-height, 64px);
  padding: var(--sp3) var(--sp4); border: 0; border-block-start: 1px solid var(--line);
  background: transparent; color: var(--fg); text-align: start;
}
.picker > .pick:first-child, .section .list > .pick:first-child { border-block-start: 0; }
.pick:hover, .pick.hl { background: var(--neutral-hover); }
.pick .txt { display: grid; flex: 1 1 auto; min-inline-size: 0; line-height: 1.6; }
.pick .txt > * { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pick-name { font-size: var(--fs-m); }
.pick small { font-size: var(--fs-s); color: var(--fg2); }
.pick small.code { font-family: var(--ha-font-family-code, monospace); font-size: var(--fs-xs); }
.pick-domain {
  align-self: flex-end; max-inline-size: 30%; flex: none;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: var(--fs-s); color: var(--fg2);
}
.pick-icon {
  display: inline-grid; place-items: center; inline-size: 32px; block-size: 32px; flex: none;
  color: var(--state-icon-color, var(--fg2));
}
.pick-icon.on { color: var(--state-active-color, var(--brand)); }
.pick-badge { inline-size: 32px; block-size: 32px; flex: none; }
.pick-none { display: flex; align-items: center; gap: var(--sp4); padding: var(--sp3) var(--sp4); color: var(--fg2); }
.pick-more { block-size: 1px; }

/* --- רשימות בדיאלוג --- */
.list { display: grid; }
.item {
  display: flex; align-items: center; gap: var(--sp3); inline-size: 100%;
  min-block-size: 56px; padding: var(--sp2) var(--sp3);
  border: 0; border-radius: var(--r-md); background: transparent; color: var(--fg); text-align: start;
}
button.item:hover, label.item:hover { background: var(--neutral-hover); }
.item > .icon:first-child { color: var(--fg2); }
.item .txt { display: grid; flex: 1 1 auto; min-inline-size: 0; }
.item .txt > :first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item small { color: var(--fg2); font-size: var(--fs-s); }
.item .chev { color: var(--fg3); }
:host([dir="rtl"]) .chev, [dir="rtl"] .chev { transform: scaleX(-1); }
/* הדיאלוג המודאלי יושב מחוץ ל-.page, ולכן גם לפי ה-dir של הרכיב עצמו. */
:host([dir="rtl"]) .back-icon, [dir="rtl"] .back-icon { transform: scaleX(-1); }
.item[aria-disabled="true"] { opacity: 0.55; }
/* תיבת סימון כמו ha-checkbox (Web Awesome): 20px, מסגרת 2px, פינה קטנה,
   מילוי ראשי עם סימן לבן כשמסומן, והכהיה במעבר עכבר. */
input[type="checkbox"] {
  appearance: none; -webkit-appearance: none; position: relative; flex: none; margin: 0;
  inline-size: var(--ha-checkbox-size, 20px); block-size: var(--ha-checkbox-size, 20px);
  border: var(--ha-checkbox-border-width, var(--ha-border-width-md, 2px)) solid
    var(--ha-checkbox-border-color, var(--ha-color-border-neutral-normal, var(--fg2)));
  border-radius: var(--ha-checkbox-border-radius, var(--r-sm));
  background: var(--ha-checkbox-background-color, var(--ha-color-form-background, transparent));
  cursor: pointer; transition: background-color var(--fast), border-color var(--fast);
}
input[type="checkbox"]::after {
  content: ""; position: absolute; inset: 0; transform: scale(var(--ha-checkbox-checked-icon-scale, 0.9));
  background: var(--ha-checkbox-checked-icon-color, var(--ha-color-on-primary-loud, #fff));
  -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/%3E%3C/svg%3E") center / contain no-repeat;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/%3E%3C/svg%3E") center / contain no-repeat;
  opacity: 0;
}
input[type="checkbox"]:checked {
  background: var(--ha-checkbox-checked-background-color, var(--ha-color-fill-primary-loud-resting, var(--brand)));
  border-color: var(--ha-checkbox-checked-background-color, var(--ha-color-fill-primary-loud-resting, var(--brand)));
}
input[type="checkbox"]:checked::after { opacity: 1; }
label:hover > input[type="checkbox"]:not(:disabled), input[type="checkbox"]:not(:disabled):hover {
  border-color: var(--ha-checkbox-border-color-hover, var(--ha-color-border-neutral-loud, var(--fg)));
  background-color: var(--ha-checkbox-background-color-hover, var(--ha-color-form-background-hover, transparent));
}
label:hover > input[type="checkbox"]:checked:not(:disabled), input[type="checkbox"]:checked:not(:disabled):hover {
  background-color: var(--ha-checkbox-checked-background-color-hover, var(--ha-color-fill-primary-loud-hover, var(--brand)));
  border-color: var(--ha-checkbox-checked-background-color-hover, var(--ha-color-fill-primary-loud-hover, var(--brand)));
}
input[type="checkbox"]:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
input[type="checkbox"]:disabled { opacity: 0.5; cursor: default; }
.item input[type="radio"] { inline-size: 20px; block-size: 20px; accent-color: var(--brand); flex: none; margin: 0; }
.section { display: grid; gap: var(--sp1); }
.section-head { display: flex; align-items: center; gap: var(--sp2); min-block-size: 36px; padding-inline: var(--sp3); }
.section-head h3 { margin: 0; font-size: var(--fs-s); font-weight: var(--fw-medium); color: var(--fg2); text-transform: none; }
.section-head .icon { width: 18px; height: 18px; color: var(--fg2); }
details.fold { border: 1px solid var(--line); border-radius: var(--r-md); }
details.fold > summary { list-style: none; display: flex; align-items: center; gap: var(--sp3); min-block-size: 56px; padding: var(--sp2) var(--sp3); cursor: pointer; }
details.fold > summary::-webkit-details-marker { display: none; }
details.fold > summary .chev { transition: transform var(--fast); }
details.fold[open] > summary .chev { transform: rotate(90deg); }
details.fold > .list { padding: 0 var(--sp2) var(--sp2); border-block-start: 1px solid var(--line); }
.entity { display: flex; align-items: center; gap: var(--sp2); flex-wrap: wrap; color: var(--fg2); font-size: var(--fs-s); }
.entity .live { color: var(--fg); font-size: var(--fs-m); }

/* --- קטעים בעורך: מסגרת, כותרת אפורה ומפרידים, כמו רשימה בכרטיס של HA --- */
.dlg-body .section {
  gap: 0; overflow: clip; flex: none;
  border: 1px solid var(--ha-color-border-neutral-quiet, var(--line)); border-radius: var(--r-lg);
  background: var(--card);
}
.dlg-body .section > .section-head {
  min-block-size: 44px; padding-inline: var(--sp4) var(--sp2);
  background: var(--ha-color-fill-neutral-quiet-resting, var(--surface));
  border-block-end: 1px solid var(--ha-color-border-neutral-quiet, var(--line));
}
.dlg-body .section > .section-head h3 { color: var(--fg); font-size: var(--fs-m); font-weight: var(--fw-medium); }
.dlg-body .section > .section-head .icon { color: var(--fg2); }
.dlg-body .section > .list > * + *, .dlg-body .section > .item + details,
.dlg-body .section > .field + .field { border-block-start: 1px solid var(--ha-color-border-neutral-quiet, var(--line)); }
.dlg-body .section .item { border-radius: 0; min-block-size: 48px; padding-inline: var(--sp4); }
.dlg-body .section .item:has(small) { min-block-size: 64px; }
.dlg-body .section > .field { padding: var(--sp3) var(--sp4); }
.dlg-body .section > .heard { border-radius: 0; }
.dlg-body .section > details.fold { border: 0; border-radius: 0; }
.dlg-body .section > details.fold > summary { padding-inline: var(--sp4); min-block-size: 48px; }
.dlg-body .section > details.fold > .list { padding: 0; }
.dlg-body .section > details.fold > .list > .item { padding-inline-start: calc(var(--sp4) + var(--sp6)); }

/* --- התראה בתוך התוכן, כמו ha-alert --- */
.alert {
  display: flex; gap: var(--sp3); align-items: flex-start; padding: var(--sp3);
  border-radius: var(--r-md); background: var(--warn-quiet);
}
.alert .icon { color: var(--warn); }
.alert.error { background: var(--danger-quiet); }
.alert.error .icon { color: var(--danger); }
.alert.info { background: var(--brand-quiet); }
.alert.info .icon { color: var(--brand); }
.alert .acts { display: flex; flex-wrap: wrap; gap: var(--sp2); margin-block-start: var(--sp2); }

/* --- מצב ריק --- */
.empty { display: grid; justify-items: center; gap: var(--sp3); padding: var(--sp8) var(--sp4); text-align: center; grid-column: 1 / -1; }
.empty .icon { width: 64px; height: 64px; color: var(--fg3); }
.empty h2 { margin: 0; font-size: var(--fs-xl); font-weight: var(--fw-medium); }
.empty p { margin: 0; color: var(--fg2); max-inline-size: 42ch; }

/* --- דיאלוג --- */
dialog.dlg {
  inline-size: min(580px, calc(100vw - 32px)); max-block-size: min(90dvh, 900px);
  padding: 0; border: 0; border-radius: var(--ha-dialog-border-radius, var(--r-xl, 24px));
  background: var(--ha-dialog-surface-background, var(--card)); color: var(--fg);
  box-shadow: var(--shadow-l); overflow: hidden;
}
dialog.dlg[open] { display: flex; flex-direction: column; animation: pop var(--normal) ease-out; }
dialog.dlg.small { inline-size: min(380px, calc(100vw - 32px)); }
dialog.dlg::backdrop { background: var(--ha-color-overlay-modal, var(--mdc-dialog-scrim-color, rgb(0 0 0 / 0.32))); }
.dlg-head { display: flex; align-items: center; gap: var(--sp1); padding: var(--sp3) var(--sp3) var(--sp2) var(--sp4); min-block-size: 64px; }
.dlg-title { flex: 1 1 auto; min-inline-size: 0; }
.dlg-title h2 { margin: 0; font-size: var(--fs-xl); font-weight: var(--fw-normal); line-height: var(--lh-tight); overflow: hidden; text-overflow: ellipsis; }
.dlg-title p { margin: 2px 0 0; color: var(--fg2); font-size: var(--fs-s); }
.dlg-badge {
  display: inline-grid; place-items: center; inline-size: 36px; block-size: 36px; flex: none;
  border-radius: var(--r-md); background: var(--brand-quiet); color: var(--brand);
  font-weight: var(--fw-bold); font-size: var(--fs-l); margin-inline-end: var(--sp2);
}
.dlg-body { flex: 1 1 auto; overflow: auto; padding: var(--sp2) var(--sp4) var(--sp4); display: grid; gap: var(--sp4); align-content: start; overscroll-behavior: contain; }
.dlg-foot {
  display: flex; justify-content: flex-end; flex-wrap: wrap; gap: var(--sp2);
  padding: var(--sp3) var(--sp4) var(--sp4); border-block-start: 1px solid var(--line);
}
.dlg-form { display: contents; }
.dlg.shake { animation: shake 0.3s; }
@media (max-width: 870px), (max-height: 500px) {
  dialog.dlg:not(.small) {
    inline-size: 100vw; max-inline-size: 100vw; margin: auto 0 0; max-block-size: 90dvh;
    border-end-start-radius: 0; border-end-end-radius: 0;
    padding-block-end: env(safe-area-inset-bottom, 0px);
  }
  dialog.dlg:not(.small)[open] { animation: rise var(--normal) ease-out; }
  dialog.dlg:not(.small)::before {
    content: ""; display: block; flex: none; inline-size: 32px; block-size: 4px; margin: var(--sp2) auto 0;
    border-radius: var(--r-pill); background: var(--line);
  }
  .dlg-head { min-block-size: 56px; padding-block-start: var(--sp1); }
}

/* --- העורך בעמודה שליד הלוח: אותו מבנה כמו הגיליון --- */
.side-editor {
  position: sticky; inset-block-start: calc(var(--header-height, 56px) + var(--sp4));
  display: flex; flex-direction: column; overflow: hidden;
  max-block-size: calc(100dvh - var(--header-height, 56px) - var(--sp8));
  animation: pop var(--normal) ease-out;
}
.side-editor > .dlg-form { display: contents; }
.side-editor.shake { animation: shake 0.3s; }

/* --- תפריט צף --- */
.menu {
  position: fixed; margin: 0; inset: auto; min-inline-size: 220px; max-inline-size: min(320px, calc(100vw - 16px));
  max-block-size: min(60vh, 480px); overflow: auto;
  padding: var(--sp1); border: 1px solid var(--line); border-radius: var(--r-md);
  background: var(--card); color: var(--fg); box-shadow: var(--shadow-m);
}
.menu:not(:popover-open):not([open]) { display: none; }
.menu .mi {
  display: flex; align-items: center; gap: var(--sp3); inline-size: 100%;
  min-block-size: 40px; padding: 0 var(--sp3); border: 0; border-radius: var(--r-sm);
  background: transparent; color: var(--fg); text-align: start; white-space: nowrap;
}
.menu .mi .icon { width: 20px; height: 20px; color: var(--fg2); }
.menu .mi:hover:not([aria-disabled="true"]) { background: var(--neutral-hover); }
.menu .mi.danger, .menu .mi.danger .icon { color: var(--danger); }
.menu .mi[aria-disabled="true"] { color: var(--fg3); }
.menu .mi .txt { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.menu .sep { block-size: 1px; background: var(--line); margin: var(--sp1) 0; }
.menu .mh { padding: var(--sp2) var(--sp3) var(--sp1); color: var(--fg2); font-size: var(--fs-s); }

.busy-bar { position: fixed; inset-block-start: 0; inset-inline: 0; block-size: 3px; z-index: 10; overflow: hidden; pointer-events: none; }
.busy-bar::before { content: ""; position: absolute; inset-block: 0; inline-size: 40%; background: var(--brand); animation: slide 1s ease-in-out infinite; }

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 50% { opacity: 0.55; } }
@keyframes flash { from { box-shadow: 0 0 0 3px var(--brand); } to { box-shadow: 0 0 0 0 transparent; } }
@keyframes pop { from { opacity: 0; transform: scale(0.96); } }
@keyframes rise { from { transform: translateY(40%); opacity: 0.4; } }
@keyframes shake { 25% { transform: translateX(-6px); } 75% { transform: translateX(6px); } }
@keyframes slide { from { inset-inline-start: -40%; } to { inset-inline-start: 100%; } }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after, ::backdrop { animation: none !important; transition: none !important; }
}
`;

let shared = null;

/** גיליון סגנון אחד לכל המופעים. בדפדפן בלי CSSStyleSheet בונים <style>. */
export const adopt = (root) => {
  if (typeof CSSStyleSheet === "function" && "adoptedStyleSheets" in root) {
    try {
      if (!shared) {
        shared = new CSSStyleSheet();
        shared.replaceSync(CSS);
      }
      root.adoptedStyleSheets = [shared];
      return null;
    } catch (_err) {
      // גיבוי למטה.
    }
  }
  const style = document.createElement("style");
  style.textContent = CSS;
  return style;
};
