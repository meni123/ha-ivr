// העיצוב של הלוח. רק משתני הערכה של Home Assistant, כך שמצב כהה ועיצוב
// אישי עובדים מעצמם, ורק מאפיינים לוגיים, כדי שהכיוון יתהפך עם השפה.

export const CSS = `
:host {
  display: block; min-height: 100%;
  --fg: var(--primary-text-color); --fg2: var(--secondary-text-color); --fg3: var(--disabled-text-color);
  --line: var(--divider-color); --card: var(--card-background-color); --surface: var(--secondary-background-color);
  --brand: var(--primary-color); --brand-quiet: color-mix(in srgb, var(--primary-color) 12%, transparent);
  --hover: color-mix(in srgb, var(--primary-text-color) 7%, transparent);
  --danger: var(--error-color); --radius: var(--ha-card-border-radius, 12px);
  color: var(--fg); font-family: var(--ha-font-family-body, Roboto, sans-serif); font-size: 14px; line-height: 1.5;
}
* { box-sizing: border-box; }
button, input, select { font: inherit; color: inherit; }
button { cursor: pointer; }
:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
ha-icon, ha-state-icon { --mdc-icon-size: 22px; flex: none; }
:host([dir="ltr"]) .chev { transform: scaleX(-1); }
.muted, .help { color: var(--fg2); margin: 0; }
.help { font-size: 12px; }
.alert { margin: 0; padding: 12px 16px; border-radius: 8px; background: color-mix(in srgb, var(--warning-color) 14%, transparent); }
.alert.error { background: color-mix(in srgb, var(--error-color) 12%, transparent); }

.toolbar {
  position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 4px;
  min-height: var(--header-height, 56px); padding: 0 12px;
  background: var(--app-header-background-color); color: var(--app-header-text-color, var(--text-primary-color));
}
.toolbar h1 { margin: 0 16px; font-size: 20px; font-weight: 400; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.toolbar select { max-width: 220px; height: 36px; border-radius: 18px; padding-inline: 12px; color: var(--fg); background: var(--card); border: 0; }
.icon-btn { display: inline-grid; place-items: center; width: 44px; height: 44px; padding: 0; border: 0; border-radius: 50%; background: none; color: inherit; }
.icon-btn:hover { background: var(--hover); }
.btn { display: inline-flex; align-items: center; gap: 8px; min-height: 40px; padding: 0 16px; border: 0; border-radius: 20px; background: none; color: var(--brand); font-weight: 500; }
.btn:hover { background: var(--brand-quiet); }
.btn.primary { background: var(--brand); color: var(--text-primary-color); }
.btn:disabled { background: none; color: var(--fg3); cursor: default; }

.content {
  max-width: 1200px; margin: 0 auto; padding: 24px 16px 32px;
  display: grid; gap: 16px; align-items: start; grid-template-columns: minmax(300px, 440px) minmax(0, 1fr);
}
.page { container-type: inline-size; }
@container (max-width: 719px) {
  .content { grid-template-columns: minmax(0, 1fr); padding-top: 16px; }
  .content > * { width: 100%; max-width: 440px; justify-self: center; }
}
.side { display: grid; gap: 16px; min-width: 0; }
.card { background: var(--card); border-radius: var(--radius); border: 1px solid var(--line); padding: 16px; display: grid; gap: 12px; }
.card h2 { margin: 0; font-size: 16px; font-weight: 500; display: flex; align-items: center; gap: 8px; }
.card h2 small { margin-inline-start: auto; color: var(--fg2); font-weight: 400; font-size: 12px; }
.empty { text-align: center; padding: 48px 16px; display: grid; gap: 8px; justify-items: center; }

.where { display: flex; align-items: center; min-height: 44px; }
.crumbs { display: flex; flex-wrap: wrap; flex: 1; list-style: none; margin: 0; padding: 0; }
.crumbs li + li::before { content: "›"; color: var(--fg3); padding-inline: 4px; }
.crumbs button { border: 0; background: none; padding: 4px 8px; border-radius: 4px; color: var(--brand); }
.crumbs [aria-current] { color: var(--fg); font-weight: 500; padding: 4px 8px; }

.pad { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; direction: ltr; }
.slot { position: relative; min-width: 0; }
.key {
  width: 100%; aspect-ratio: 1; display: grid; grid-template-rows: auto 1fr auto auto; justify-items: center; align-items: center;
  gap: 2px; padding: 8px 4px; border: 1px solid var(--line); border-radius: 16px; background: var(--card); text-align: center;
}
.key:hover:not([aria-disabled="true"]) { background: var(--hover); }
.k-digit { justify-self: start; padding-inline: 4px; font-size: 16px; font-weight: 600; color: var(--fg2); }
.k-icon { --mdc-icon-size: 28px; color: var(--brand); }
.k-name, .k-sub { max-width: 100%; padding-inline: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.k-name { font-weight: 500; line-height: 1.2; }
.k-sub { font-size: 12px; color: var(--fg2); min-height: 1.2em; line-height: 1.2; }
.k-stack { background: var(--brand-quiet); border-color: transparent; }
.k-empty { border-style: dashed; background: none; color: var(--fg2); }
.k-empty .k-icon { color: var(--fg3); }
.k-nav { background: var(--surface); border-color: transparent; }
.k-nav .k-icon { color: var(--fg2); }
.key[aria-disabled="true"] { opacity: .45; cursor: default; }
.k-removed { border-color: var(--danger); }
.k-removed .k-sub { color: var(--danger); }
.k-flash { animation: flash 1.2s ease-out; }
.k-edit { position: absolute; top: 2px; inset-inline-end: 2px; width: 36px; height: 36px; color: var(--fg2); }
@keyframes flash { from { background: var(--brand-quiet); } }

.heard { list-style: none; margin: 0; padding: 12px 16px; display: grid; gap: 4px; background: var(--surface); border-radius: 8px; }
.heard li::before { content: "“"; color: var(--fg3); margin-inline-end: 6px; }
.rows { display: grid; }
.row {
  display: flex; align-items: center; gap: 12px; min-height: 52px; padding: 6px 4px; width: 100%;
  border: 0; border-top: 1px solid var(--line); background: none; text-align: start;
}
.rows > .row:first-child { border-top: 0; }
.row:hover { background: var(--hover); }
.row ha-icon:first-child { color: var(--fg2); }
.row .txt { flex: 1; display: grid; }
.row small { color: var(--fg2); }
.chev { color: var(--fg3); }
.acts { display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.entity { display: flex; justify-content: space-between; gap: 8px; color: var(--fg2); font-size: 12px; }

dialog {
  width: min(560px, calc(100vw - 32px)); max-height: calc(100vh - 64px); padding: 0;
  border: 0; border-radius: 28px; background: var(--card); color: var(--fg);
  box-shadow: 0 8px 28px rgba(0, 0, 0, .3);
}
dialog::backdrop { background: rgba(0, 0, 0, .4); }
.narrow dialog, dialog.narrow { width: 100vw; max-width: 100vw; margin: auto 0 0; border-radius: 28px 28px 0 0; }
.dlg { display: flex; flex-direction: column; max-height: inherit; }
.dlg header { display: flex; align-items: center; gap: 4px; padding: 12px 12px 0; }
.dlg header .titles { flex: 1; min-width: 0; padding-inline: 12px; }
.dlg header h2 { margin: 0; font-size: 22px; font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dlg header p { margin: 0; color: var(--fg2); }
.dlg .body { padding: 16px 24px; overflow: auto; display: grid; gap: 16px; }
.dlg .sub { margin: 0; font-size: 14px; font-weight: 500; }
.dlg footer { display: flex; justify-content: flex-end; gap: 8px; padding: 8px 24px 20px; }
`;
