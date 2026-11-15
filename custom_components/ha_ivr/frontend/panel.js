// לוח המקשים: עורך התפריט הטלפוני בסרגל הצד.
//
// העמוד מצייר לוח מקשים של טלפון. כל מקש הוא מה שהמתקשר מקבל כשהוא
// מקיש עליו. כל ההחלטות נשארות בשרת (editor.py); כאן רק מציירים את
// הרמה שחזרה ושולחים את מה שהמשתמש ביקש.
//
// כל טקסט שמגיע מבחוץ נכנס כצומת טקסט. אין כאן innerHTML בכלל.

const WS_TYPE = "ha_ivr/editor";
const STORE_KEY = "ha_ivr_entry";
const PICKER_LIMIT = 50;
const SEARCH_DELAY = 150;
// סדר המקשים בלוח, משמאל לימין ומלמעלה למטה.
const PAD = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

// ערך בתוך מרכאות של בורר CSS.
const quoted = (value) => String(value ?? "").replace(/["\\]/g, "\\$&");

// נתיבי SVG מ-Material Design Icons (Apache 2.0).
const ICONS = {
  "folder-outline": "M20,18H4V8H20M20,6H12L10,4H4C2.89,4 2,4.89 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V8C22,6.89 21.1,6 20,6Z",
  "phone-forward": "M20,15.5C18.75,15.5 17.55,15.3 16.43,14.93C16.08,14.82 15.69,14.9 15.41,15.18L13.21,17.38C10.38,15.94 8.06,13.62 6.62,10.79L8.82,8.59C9.1,8.31 9.18,7.92 9.07,7.57C8.7,6.45 8.5,5.25 8.5,4A1,1 0 0,0 7.5,3H4A1,1 0 0,0 3,4A17,17 0 0,0 20,21A1,1 0 0,0 21,20V16.5A1,1 0 0,0 20,15.5M18,11L23,6L18,1V4H14V8H18V11Z",
  "account-voice": "M9,5A4,4 0 0,1 13,9A4,4 0 0,1 9,13A4,4 0 0,1 5,9A4,4 0 0,1 9,5M9,15C11.67,15 17,16.34 17,19V21H1V19C1,16.34 6.33,15 9,15M16.76,5.36C18.78,7.56 18.78,10.61 16.76,12.63L15.08,10.94C15.92,9.76 15.92,8.23 15.08,7.05L16.76,5.36M20.07,2C24,6.05 23.97,12.11 20.07,16L18.44,14.37C21.21,11.19 21.21,6.65 18.44,3.63L20.07,2Z",
  "bell-outline": "M10 21H14C14 22.1 13.1 23 12 23S10 22.1 10 21M21 19V20H3V19L5 17V11C5 7.9 7 5.2 10 4.3V4C10 2.9 10.9 2 12 2S14 2.9 14 4V4.3C17 5.2 19 7.9 19 11V17L21 19M17 11C17 8.2 14.8 6 12 6S7 8.2 7 11V18H17V11Z",
  "radiobox-marked": "M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,7A5,5 0 0,0 7,12A5,5 0 0,0 12,17A5,5 0 0,0 17,12A5,5 0 0,0 12,7Z",
  "gesture-tap": "M10,9A1,1 0 0,1 11,8A1,1 0 0,1 12,9V13.47L13.21,13.6L18.15,15.79C18.68,16.03 19,16.56 19,17.14V21.5C18.97,22.32 18.32,22.97 17.5,23H11C10.62,23 10.26,22.85 10,22.57L5.1,18.37L5.84,17.6C6.03,17.39 6.3,17.28 6.58,17.28H6.8L10,19V9M11,5A4,4 0 0,1 15,9C15,10.5 14.2,11.77 13,12.46V11.24C13.61,10.69 14,9.89 14,9A3,3 0 0,0 11,6A3,3 0 0,0 8,9C8,9.89 8.39,10.69 9,11.24V12.46C7.8,11.77 7,10.5 7,9A4,4 0 0,1 11,5Z",
  "volume-high": "M14,3.23V5.29C16.89,6.15 19,8.83 19,12C19,15.17 16.89,17.84 14,18.7V20.77C18,19.86 21,16.28 21,12C21,7.72 18,4.14 14,3.23M16.5,12C16.5,10.23 15.5,8.71 14,7.97V16C15.5,15.29 16.5,13.76 16.5,12M3,9V15H7L12,20V4L7,9H3Z",
  "format-list-bulleted": "M7,5H21V7H7V5M7,13V11H21V13H7M4,4.5A1.5,1.5 0 0,1 5.5,6A1.5,1.5 0 0,1 4,7.5A1.5,1.5 0 0,1 2.5,6A1.5,1.5 0 0,1 4,4.5M4,10.5A1.5,1.5 0 0,1 5.5,12A1.5,1.5 0 0,1 4,13.5A1.5,1.5 0 0,1 2.5,12A1.5,1.5 0 0,1 4,10.5M7,19V17H21V19H7M4,16.5A1.5,1.5 0 0,1 5.5,18A1.5,1.5 0 0,1 4,19.5A1.5,1.5 0 0,1 2.5,18A1.5,1.5 0 0,1 4,16.5Z",
  "numeric": "M4,17V9H2V7H6V17H4M22,15C22,16.11 21.1,17 20,17H16V15H20V13H18V11H20V9H16V7H20A2,2 0 0,1 22,9V10.5A1.5,1.5 0 0,1 20.5,12A1.5,1.5 0 0,1 22,13.5V15M14,15V17H8V13C8,11.89 8.9,11 10,11H12V9H8V7H12A2,2 0 0,1 14,9V11C14,12.11 13.1,13 12,13H10V15H14Z",
  "microphone-message": "M8,7A2,2 0 0,1 10,9V14A2,2 0 0,1 8,16A2,2 0 0,1 6,14V9A2,2 0 0,1 8,7M14,14C14,16.97 11.84,19.44 9,19.92V22H7V19.92C4.16,19.44 2,16.97 2,14H4A4,4 0 0,0 8,18A4,4 0 0,0 12,14H14M21.41,9.41L17.17,13.66L18.18,10H14A2,2 0 0,1 12,8V4A2,2 0 0,1 14,2H20A2,2 0 0,1 22,4V8C22,8.55 21.78,9.05 21.41,9.41Z",
  "tune-variant": "M8 13C6.14 13 4.59 14.28 4.14 16H2V18H4.14C4.59 19.72 6.14 21 8 21S11.41 19.72 11.86 18H22V16H11.86C11.41 14.28 9.86 13 8 13M8 19C6.9 19 6 18.1 6 17C6 15.9 6.9 15 8 15S10 15.9 10 17C10 18.1 9.1 19 8 19M19.86 6C19.41 4.28 17.86 3 16 3S12.59 4.28 12.14 6H2V8H12.14C12.59 9.72 14.14 11 16 11S19.41 9.72 19.86 8H22V6H19.86M16 9C14.9 9 14 8.1 14 7C14 5.9 14.9 5 16 5S18 5.9 18 7C18 8.1 17.1 9 16 9Z",
  "lightbulb": "M12,2A7,7 0 0,0 5,9C5,11.38 6.19,13.47 8,14.74V17A1,1 0 0,0 9,18H15A1,1 0 0,0 16,17V14.74C17.81,13.47 19,11.38 19,9A7,7 0 0,0 12,2M9,21A1,1 0 0,0 10,22H14A1,1 0 0,0 15,21V20H9V21Z",
  "toggle-switch-outline": "M17 6H7C3.69 6 1 8.69 1 12S3.69 18 7 18H17C20.31 18 23 15.31 23 12S20.31 6 17 6M17 16H7C4.79 16 3 14.21 3 12S4.79 8 7 8H17C19.21 8 21 9.79 21 12S19.21 16 17 16M17 9C15.34 9 14 10.34 14 12S15.34 15 17 15 20 13.66 20 12 18.66 9 17 9Z",
  "air-conditioner": "M6.59,0.66C8.93,-1.15 11.47,1.06 12.04,4.5C12.47,4.5 12.89,4.62 13.27,4.84C13.79,4.24 14.25,3.42 14.07,2.5C13.65,0.35 16.06,-1.39 18.35,1.58C20.16,3.92 17.95,6.46 14.5,7.03C14.5,7.46 14.39,7.89 14.16,8.27C14.76,8.78 15.58,9.24 16.5,9.06C18.63,8.64 20.38,11.04 17.41,13.34C15.07,15.15 12.53,12.94 11.96,9.5C11.53,9.5 11.11,9.37 10.74,9.15C10.22,9.75 9.75,10.58 9.93,11.5C10.35,13.64 7.94,15.39 5.65,12.42C3.83,10.07 6.05,7.53 9.5,6.97C9.5,6.54 9.63,6.12 9.85,5.74C9.25,5.23 8.43,4.76 7.5,4.94C5.37,5.36 3.62,2.96 6.59,0.66M5,16H7A2,2 0 0,1 9,18V24H7V22H5V24H3V18A2,2 0 0,1 5,16M5,18V20H7V18H5M12.93,16H15L12.07,24H10L12.93,16M18,16H21V18H18V22H21V24H18A2,2 0 0,1 16,22V18A2,2 0 0,1 18,16Z",
  "window-shutter": "M3 4H21V8H19V20H17V8H7V20H5V8H3V4M8 9H16V11H8V9M8 12H16V14H8V12M8 15H16V17H8V15M8 18H16V20H8V18Z",
  "fan": "M12,11A1,1 0 0,0 11,12A1,1 0 0,0 12,13A1,1 0 0,0 13,12A1,1 0 0,0 12,11M12.5,2C17,2 17.11,5.57 14.75,6.75C13.76,7.24 13.32,8.29 13.13,9.22C13.61,9.42 14.03,9.73 14.35,10.13C18.05,8.13 22.03,8.92 22.03,12.5C22.03,17 18.46,17.1 17.28,14.73C16.78,13.74 15.72,13.3 14.79,13.11C14.59,13.59 14.28,14 13.88,14.34C15.87,18.03 15.08,22 11.5,22C7,22 6.91,18.42 9.27,17.24C10.25,16.75 10.69,15.71 10.89,14.79C10.4,14.59 9.97,14.27 9.65,13.87C5.96,15.85 2,15.07 2,11.5C2,7 5.56,6.89 6.74,9.26C7.24,10.25 8.29,10.68 9.22,10.87C9.41,10.39 9.73,9.97 10.14,9.65C8.15,5.96 8.94,2 12.5,2Z",
  "speaker": "M12,12A3,3 0 0,0 9,15A3,3 0 0,0 12,18A3,3 0 0,0 15,15A3,3 0 0,0 12,12M12,20A5,5 0 0,1 7,15A5,5 0 0,1 12,10A5,5 0 0,1 17,15A5,5 0 0,1 12,20M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8C10.89,8 10,7.1 10,6C10,4.89 10.89,4 12,4M17,2H7C5.89,2 5,2.89 5,4V20A2,2 0 0,0 7,22H17A2,2 0 0,0 19,20V4C19,2.89 18.1,2 17,2Z",
  "lock-outline": "M12,17C10.89,17 10,16.1 10,15C10,13.89 10.89,13 12,13A2,2 0 0,1 14,15A2,2 0 0,1 12,17M18,20V10H6V20H18M18,8A2,2 0 0,1 20,10V20A2,2 0 0,1 18,22H6C4.89,22 4,21.1 4,20V10C4,8.89 4.89,8 6,8H7V6A5,5 0 0,1 12,1A5,5 0 0,1 17,6V8H18M12,3A3,3 0 0,0 9,6V8H15V6A3,3 0 0,0 12,3Z",
  "palette-outline": "M12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2C17.5,2 22,6 22,11A6,6 0 0,1 16,17H14.2C13.9,17 13.7,17.2 13.7,17.5C13.7,17.6 13.8,17.7 13.8,17.8C14.2,18.3 14.4,18.9 14.4,19.5C14.5,20.9 13.4,22 12,22M12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C12.3,20 12.5,19.8 12.5,19.5C12.5,19.3 12.4,19.2 12.4,19.1C12,18.6 11.8,18.1 11.8,17.5C11.8,16.1 12.9,15 14.3,15H16A4,4 0 0,0 20,11C20,7.1 16.4,4 12,4M6.5,10C7.3,10 8,10.7 8,11.5C8,12.3 7.3,13 6.5,13C5.7,13 5,12.3 5,11.5C5,10.7 5.7,10 6.5,10M9.5,6C10.3,6 11,6.7 11,7.5C11,8.3 10.3,9 9.5,9C8.7,9 8,8.3 8,7.5C8,6.7 8.7,6 9.5,6M14.5,6C15.3,6 16,6.7 16,7.5C16,8.3 15.3,9 14.5,9C13.7,9 13,8.3 13,7.5C13,6.7 13.7,6 14.5,6M17.5,10C18.3,10 19,10.7 19,11.5C19,12.3 18.3,13 17.5,13C16.7,13 16,12.3 16,11.5C16,10.7 16.7,10 17.5,10Z",
  "script-text-outline": "M15,20A1,1 0 0,0 16,19V4H8A1,1 0 0,0 7,5V16H5V5A3,3 0 0,1 8,2H19A3,3 0 0,1 22,5V6H20V5A1,1 0 0,0 19,4A1,1 0 0,0 18,5V9L18,19A3,3 0 0,1 15,22H5A3,3 0 0,1 2,19V18H13A2,2 0 0,0 15,20M9,6H14V8H9V6M9,10H14V12H9V10M9,14H14V16H9V14Z",
  "eye-outline": "M12,9A3,3 0 0,1 15,12A3,3 0 0,1 12,15A3,3 0 0,1 9,12A3,3 0 0,1 12,9M12,4.5C17,4.5 21.27,7.61 23,12C21.27,16.39 17,19.5 12,19.5C7,19.5 2.73,16.39 1,12C2.73,7.61 7,4.5 12,4.5M3.18,12C4.83,15.36 8.24,17.5 12,17.5C15.76,17.5 19.17,15.36 20.82,12C19.17,8.64 15.76,6.5 12,6.5C8.24,6.5 4.83,8.64 3.18,12Z",
  "robot-vacuum": "M12,2C14.65,2 17.19,3.06 19.07,4.93L17.65,6.35C16.15,4.85 14.12,4 12,4C9.88,4 7.84,4.84 6.35,6.35L4.93,4.93C6.81,3.06 9.35,2 12,2M3.66,6.5L5.11,7.94C4.39,9.17 4,10.57 4,12A8,8 0 0,0 12,20A8,8 0 0,0 20,12C20,10.57 19.61,9.17 18.88,7.94L20.34,6.5C21.42,8.12 22,10.04 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12C2,10.04 2.58,8.12 3.66,6.5M12,6A6,6 0 0,1 18,12C18,13.59 17.37,15.12 16.24,16.24L14.83,14.83C14.08,15.58 13.06,16 12,16C10.94,16 9.92,15.58 9.17,14.83L7.76,16.24C6.63,15.12 6,13.59 6,12A6,6 0 0,1 12,6M12,8A1,1 0 0,0 11,9A1,1 0 0,0 12,10A1,1 0 0,0 13,9A1,1 0 0,0 12,8Z",
  "water-boiler": "M8 2C6.89 2 6 2.89 6 4V16C6 17.11 6.89 18 8 18H9V20H6V22H9C10.11 22 11 21.11 11 20V18H13V20C13 21.11 13.89 22 15 22H18V20H15V18H16C17.11 18 18 17.11 18 16V4C18 2.89 17.11 2 16 2H8M12 4.97A2 2 0 0 1 14 6.97A2 2 0 0 1 12 8.97A2 2 0 0 1 10 6.97A2 2 0 0 1 12 4.97M10 14.5H14V16H10V14.5Z",
  "gesture-tap-button": "M13 5C15.21 5 17 6.79 17 9C17 10.5 16.2 11.77 15 12.46V11.24C15.61 10.69 16 9.89 16 9C16 7.34 14.66 6 13 6S10 7.34 10 9C10 9.89 10.39 10.69 11 11.24V12.46C9.8 11.77 9 10.5 9 9C9 6.79 10.79 5 13 5M20 20.5C19.97 21.32 19.32 21.97 18.5 22H13C12.62 22 12.26 21.85 12 21.57L8 17.37L8.74 16.6C8.93 16.39 9.2 16.28 9.5 16.28H9.7L12 18V9C12 8.45 12.45 8 13 8S14 8.45 14 9V13.47L15.21 13.6L19.15 15.79C19.68 16.03 20 16.56 20 17.14V20.5M20 2H4C2.9 2 2 2.9 2 4V12C2 13.11 2.9 14 4 14H8V12L4 12L4 4H20L20 12H18V14H20V13.96L20.04 14C21.13 14 22 13.09 22 12V4C22 2.9 21.11 2 20 2Z",
  "robot-outline": "M17.5 15.5C17.5 16.61 16.61 17.5 15.5 17.5S13.5 16.61 13.5 15.5 14.4 13.5 15.5 13.5 17.5 14.4 17.5 15.5M8.5 13.5C7.4 13.5 6.5 14.4 6.5 15.5S7.4 17.5 8.5 17.5 10.5 16.61 10.5 15.5 9.61 13.5 8.5 13.5M23 15V18C23 18.55 22.55 19 22 19H21V20C21 21.11 20.11 22 19 22H5C3.9 22 3 21.11 3 20V19H2C1.45 19 1 18.55 1 18V15C1 14.45 1.45 14 2 14H3C3 10.13 6.13 7 10 7H11V5.73C10.4 5.39 10 4.74 10 4C10 2.9 10.9 2 12 2S14 2.9 14 4C14 4.74 13.6 5.39 13 5.73V7H14C17.87 7 21 10.13 21 14H22C22.55 14 23 14.45 23 15M21 16H19V14C19 11.24 16.76 9 14 9H10C7.24 9 5 11.24 5 14V16H3V17H5V20H19V17H21V16Z",
  "devices": "M3 6H21V4H3C1.9 4 1 4.9 1 6V18C1 19.1 1.9 20 3 20H7V18H3V6M13 12H9V13.78C8.39 14.33 8 15.11 8 16C8 16.89 8.39 17.67 9 18.22V20H13V18.22C13.61 17.67 14 16.88 14 16S13.61 14.33 13 13.78V12M11 17.5C10.17 17.5 9.5 16.83 9.5 16S10.17 14.5 11 14.5 12.5 15.17 12.5 16 11.83 17.5 11 17.5M22 8H16C15.5 8 15 8.5 15 9V19C15 19.5 15.5 20 16 20H22C22.5 20 23 19.5 23 19V9C23 8.5 22.5 8 22 8M21 18H17V10H21V18Z",
  "plus": "M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z",
  "arrow-down-bold-outline": "M22,11L12,21L2,11H8V3H16V11H22M12,18L17,13H14V5H10V13H7L12,18Z",
  "alert-outline": "M12,2L1,21H23M12,6L19.53,19H4.47M11,10V14H13V10M11,16V18H13V16",
  "alert-circle-outline": "M11,15H13V17H11V15M11,7H13V13H11V7M12,2C6.47,2 2,6.5 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20Z",
  "phone-plus-outline": "M20 15.5C18.8 15.5 17.5 15.3 16.4 14.9H16.1C15.8 14.9 15.6 15 15.4 15.2L13.2 17.4C10.4 15.9 8 13.6 6.6 10.8L8.8 8.6C9.1 8.3 9.2 7.9 9 7.6C8.7 6.5 8.5 5.2 8.5 4C8.5 3.5 8 3 7.5 3H4C3.5 3 3 3.5 3 4C3 13.4 10.6 21 20 21C20.5 21 21 20.5 21 20V16.5C21 16 20.5 15.5 20 15.5M5 5H6.5C6.6 5.9 6.8 6.8 7 7.6L5.8 8.8C5.4 7.6 5.1 6.3 5 5M19 19C17.7 18.9 16.4 18.6 15.2 18.2L16.4 17C17.2 17.2 18.1 17.4 19 17.4V19M16 3V6H13V8H16V11H18V8H21V6H18V3Z",
  "menu": "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z",
  "cog-outline": "M12,8A4,4 0 0,1 16,12A4,4 0 0,1 12,16A4,4 0 0,1 8,12A4,4 0 0,1 12,8M12,10A2,2 0 0,0 10,12A2,2 0 0,0 12,14A2,2 0 0,0 14,12A2,2 0 0,0 12,10M10,22C9.75,22 9.54,21.82 9.5,21.58L9.13,18.93C8.5,18.68 7.96,18.34 7.44,17.94L4.95,18.95C4.73,19.03 4.46,18.95 4.34,18.73L2.34,15.27C2.21,15.05 2.27,14.78 2.46,14.63L4.57,12.97L4.5,12L4.57,11L2.46,9.37C2.27,9.22 2.21,8.95 2.34,8.73L4.34,5.27C4.46,5.05 4.73,4.96 4.95,5.05L7.44,6.05C7.96,5.66 8.5,5.32 9.13,5.07L9.5,2.42C9.54,2.18 9.75,2 10,2H14C14.25,2 14.46,2.18 14.5,2.42L14.87,5.07C15.5,5.32 16.04,5.66 16.56,6.05L19.05,5.05C19.27,4.96 19.54,5.05 19.66,5.27L21.66,8.73C21.79,8.95 21.73,9.22 21.54,9.37L19.43,11L19.5,12L19.43,13L21.54,14.63C21.73,14.78 21.79,15.05 21.66,15.27L19.66,18.73C19.54,18.95 19.27,19.04 19.05,18.95L16.56,17.95C16.04,18.34 15.5,18.68 14.87,18.93L14.5,21.58C14.46,21.82 14.25,22 14,22H10M11.25,4L10.88,6.61C9.68,6.86 8.62,7.5 7.85,8.39L5.44,7.35L4.69,8.65L6.8,10.2C6.4,11.37 6.4,12.64 6.8,13.8L4.68,15.36L5.43,16.66L7.86,15.62C8.63,16.5 9.68,17.14 10.87,17.38L11.24,20H12.76L13.13,17.39C14.32,17.14 15.37,16.5 16.14,15.62L18.57,16.66L19.32,15.36L17.2,13.81C17.6,12.64 17.6,11.37 17.2,10.2L19.31,8.65L18.56,7.35L16.15,8.39C15.38,7.5 14.32,6.86 13.12,6.62L12.75,4H11.25Z",
  "cursor-move": "M13,6V11H18V7.75L22.25,12L18,16.25V13H13V18H16.25L12,22.25L7.75,18H11V13H6V16.25L1.75,12L6,7.75V11H11V6H7.75L12,1.75L16.25,6H13Z",
  "drag": "M7,19V17H9V19H7M11,19V17H13V19H11M15,19V17H17V19H15M7,15V13H9V15H7M11,15V13H13V15H11M15,15V13H17V15H15M7,11V9H9V11H7M11,11V9H13V11H11M15,11V9H17V11H15M7,7V5H9V7H7M11,7V5H13V7H11M15,7V5H17V7H15Z",
  "arrow-right": "M4,11V13H16L10.5,18.5L11.92,19.92L19.84,12L11.92,4.08L10.5,5.5L16,11H4Z",
  "home-outline": "M12 5.69L17 10.19V18H15V12H9V18H7V10.19L12 5.69M12 3L2 12H5V20H11V14H13V20H19V12H22",
  "door-open": "M12,3C10.89,3 10,3.89 10,5H3V19H2V21H22V19H21V5C21,3.89 20.11,3 19,3H12M12,5H19V19H12V5M5,11H7V13H5V11Z",
  "home-group": "M17,16H15V22H12V17H8V22H5V16H3L10,10L17,16M6,2L10,6H9V9H7V6H5V9H3V6H2L6,2M18,3L23,8H22V12H19V9H17V12H15.34L14,10.87V8H13L18,3Z",
  "lightbulb-outline": "M12,2A7,7 0 0,1 19,9C19,11.38 17.81,13.47 16,14.74V17A1,1 0 0,1 15,18H9A1,1 0 0,1 8,17V14.74C6.19,13.47 5,11.38 5,9A7,7 0 0,1 12,2M9,21V20H15V21A1,1 0 0,1 14,22H10A1,1 0 0,1 9,21M12,4A5,5 0 0,0 7,9C7,11.05 8.23,12.81 10,13.58V16H14V13.58C15.77,12.81 17,11.05 17,9A5,5 0 0,0 12,4Z",
  "dialpad": "M12,19A2,2 0 0,0 10,21A2,2 0 0,0 12,23A2,2 0 0,0 14,21A2,2 0 0,0 12,19M6,1A2,2 0 0,0 4,3A2,2 0 0,0 6,5A2,2 0 0,0 8,3A2,2 0 0,0 6,1M6,7A2,2 0 0,0 4,9A2,2 0 0,0 6,11A2,2 0 0,0 8,9A2,2 0 0,0 6,7M6,13A2,2 0 0,0 4,15A2,2 0 0,0 6,17A2,2 0 0,0 8,15A2,2 0 0,0 6,13M18,5A2,2 0 0,0 20,3A2,2 0 0,0 18,1A2,2 0 0,0 16,3A2,2 0 0,0 18,5M12,13A2,2 0 0,0 10,15A2,2 0 0,0 12,17A2,2 0 0,0 14,15A2,2 0 0,0 12,13M18,13A2,2 0 0,0 16,15A2,2 0 0,0 18,17A2,2 0 0,0 20,15A2,2 0 0,0 18,13M18,7A2,2 0 0,0 16,9A2,2 0 0,0 18,11A2,2 0 0,0 20,9A2,2 0 0,0 18,7M12,7A2,2 0 0,0 10,9A2,2 0 0,0 12,11A2,2 0 0,0 14,9A2,2 0 0,0 12,7M12,1A2,2 0 0,0 10,3A2,2 0 0,0 12,5A2,2 0 0,0 14,3A2,2 0 0,0 12,1Z",
  "swap-horizontal": "M21,9L17,5V8H10V10H17V13M7,11L3,15L7,19V16H14V14H7V11Z",
  "delete-outline": "M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19M8,9H16V19H8V9M15.5,4L14.5,3H9.5L8.5,4H5V6H19V4H15.5Z",
  "close": "M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z",
  "keyboard-return": "M19,7V11H5.83L9.41,7.41L8,6L2,12L8,18L9.41,16.58L5.83,13H21V7H19Z",
};

const KIND_ICONS = {
  submenu: "folder-outline",
  goto: "phone-forward",
  assistant: "account-voice",
  alerts: "bell-outline",
  option: "radiobox-marked",
};

const CAP_ICONS = {
  simple: "gesture-tap",
  status: "volume-high",
  choice: "format-list-bulleted",
  number: "numeric",
  text: "microphone-message",
  fixed: "tune-variant",
};

const DOMAIN_ICONS = {
  light: "lightbulb",
  switch: "toggle-switch-outline",
  input_boolean: "toggle-switch-outline",
  climate: "air-conditioner",
  cover: "window-shutter",
  fan: "fan",
  media_player: "speaker",
  lock: "lock-outline",
  scene: "palette-outline",
  script: "script-text-outline",
  sensor: "eye-outline",
  binary_sensor: "eye-outline",
  vacuum: "robot-vacuum",
  water_heater: "water-boiler",
  button: "gesture-tap-button",
  automation: "robot-outline",
};

// התכונה שמוצגת ליד המצב בכותרת של מכשיר.
const MAIN_ATTR = {
  climate: "temperature",
  water_heater: "temperature",
  light: "brightness",
  cover: "current_position",
  fan: "percentage",
  media_player: "volume_level",
};

// יחידות ש-Home Assistant מדווח עליהן באנגלית.
const UNITS = {
  seconds: "שניות", second: "שניות", s: "שניות",
  minutes: "דקות", minute: "דקות", min: "דקות", hours: "שעות",
};

// הסדר שבו סוגי המכשירים מופיעים בבורר: מה שמפעילים קודם.
const DOMAIN_ORDER = [
  "light", "switch", "climate", "cover", "fan", "water_heater", "media_player",
  "vacuum", "scene", "script", "button", "input_boolean", "humidifier", "valve",
];

// סוגים שאין להם מה לחפש בבורר המכשירים.
const PICKER_SKIP = new Set(["stt", "wake_word", "conversation", "tts", "assist_satellite"]);

// קבוצות היכולות בעורך, לפי הסדר.
const CAP_GROUPS = [
  { id: "simple", title: "בהקשה אחת", icon: "gesture-tap" },
  { id: "status", title: "הקראת מצב", icon: "volume-high" },
  { id: "choice", title: "בחירה מרשימה", icon: "format-list-bulleted" },
  { id: "number", title: "הקשת מספר", icon: "numeric" },
  { id: "code", title: "עם קוד", icon: "dialpad" },
  { id: "text", title: "הכתבה בקול", icon: "microphone-message" },
  { id: "fixed", title: "רק עם ערך קבוע", icon: "tune-variant" },
];

const capGroup = (c) => {
  if (c.needs_fixed || c.kind === "fixed") return "fixed";
  if (c.code) return "code";
  return CAP_GROUPS.some((g) => g.id === c.kind) ? c.kind : "simple";
};

const iconOf = (key) => {
  if (key.kind === "cap") return CAP_ICONS[key.cap] || CAP_ICONS.simple;
  if (key.kind === "action" && key.fixed) return "tune-variant";
  if (KIND_ICONS[key.kind]) return KIND_ICONS[key.kind];
  return DOMAIN_ICONS[key.domain] || "devices";
};

// הסגנון של המקש: לכל מצב סגנון אחד.
const keyType = (key) => {
  if (key.kind === "submenu" || key.kind === "group") return "stack";
  if (key.kind === "assistant") return "assist";
  if ((key.kind === "action" && key.fixed) || (key.kind === "cap" && key.cap === "fixed")) return "fixed";
  if (key.kind === "cap" && key.cap === "text") return "dictate";
  return "plain";
};

const cls = (...names) => names.filter(Boolean).join(" ");

// בונה אלמנט. מאפיין null/false אינו נכתב, וילדים שהם מחרוזות נכנסים כטקסט.
const h = (tag, attrs, ...kids) => {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [name, value] of Object.entries(attrs)) {
      if (value === null || value === undefined || value === false) continue;
      el.setAttribute(name, value === true ? "" : String(value));
    }
  }
  return put(el, kids);
};

const put = (el, kids) => {
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false || kid === "") continue;
    el.append(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
  }
  return el;
};

// מזהים, מספרי טלפון, * ו-# — תמיד משמאל לימין, מבודדים מהטקסט שסביבם.
const ltr = (text) => h("bdi", { dir: "ltr" }, String(text ?? ""));
// ערך מעוצב (מצב, טמפרטורה) מבודד בכיוון שלו, כדי ש-"23°" לא יתהפך.
const own = (text) => h("bdi", { dir: "auto" }, String(text ?? ""));
// כמה ערכים מבודדים, מופרדים בנקודה.
const joined = (parts) => parts.filter(Boolean).flatMap((p, i) => (i ? [" · ", own(p)] : [own(p)]));

const SVG_NS = "http://www.w3.org/2000/svg";
const icon = (name, extra = "") => {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("class", cls("icon", extra));
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICONS[name] || ICONS.devices);
  svg.append(path);
  return svg;
};

// כפתור. ברירת המחדל type=button, כדי שלא ישלח טופס בטעות.
const btn = (className, attrs, ...kids) => h("button", { type: "button", class: className, ...attrs }, ...kids);

const STYLE = `
:host {
  --s1: 4px; --s2: 8px; --s3: 12px; --s4: 16px; --s5: 24px; --s6: 32px;
  --r: var(--ha-card-border-radius, 12px);
  --r-in: calc(var(--r) * 0.66);
  --tap: 44px;
  --fg: var(--primary-text-color);
  --sub: color-mix(in srgb, var(--secondary-text-color) 78%, var(--primary-text-color));
  --bg: var(--primary-background-color);
  --card: var(--card-background-color, var(--primary-background-color));
  --raise: color-mix(in srgb, var(--primary-text-color) 4%, var(--card));
  --raise2: color-mix(in srgb, var(--primary-text-color) 9%, var(--card));
  --line: var(--divider-color);
  --line-strong: color-mix(in srgb, var(--primary-text-color) 28%, var(--card));
  --ink: color-mix(in srgb, var(--primary-color) 50%, var(--primary-text-color));
  --tint: color-mix(in srgb, var(--primary-color) 14%, var(--card));
  --err-ink: color-mix(in srgb, var(--error-color, var(--primary-color)) 50%, var(--primary-text-color));
  --err-tint: color-mix(in srgb, var(--error-color, var(--primary-color)) 14%, var(--card));
  --warn-ink: color-mix(in srgb, var(--warning-color, var(--primary-color)) 50%, var(--primary-text-color));
  --warn-tint: color-mix(in srgb, var(--warning-color, var(--primary-color)) 16%, var(--card));
  --ok-ink: color-mix(in srgb, var(--success-color, var(--primary-color)) 50%, var(--primary-text-color));
  --ok-tint: color-mix(in srgb, var(--success-color, var(--primary-color)) 14%, var(--card));
  --info-ink: color-mix(in srgb, var(--info-color, var(--primary-color)) 50%, var(--primary-text-color));
  --info-tint: color-mix(in srgb, var(--info-color, var(--primary-color)) 12%, var(--card));
  --assist-ink: color-mix(in srgb, var(--accent-color, var(--primary-color)) 50%, var(--primary-text-color));
  --assist-tint: color-mix(in srgb, var(--accent-color, var(--primary-color)) 13%, var(--card));
  display: block;
  height: 100vh;
  height: 100dvh;
  color: var(--fg);
  background: var(--bg);
  font-family: var(--ha-font-family-body, Roboto, "Noto Sans Hebrew", sans-serif);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
bdi { unicode-bidi: isolate; }
bdi[dir="ltr"] { direction: ltr; }
.icon { width: 24px; height: 24px; fill: currentColor; flex: none; }
.t-title { font-size: 20px; font-weight: 500; line-height: 1.3; margin: 0; }
.t-label { font-size: 14px; font-weight: 500; line-height: 1.4; margin: 0; }
.t-sub { font-size: 12px; font-weight: 400; line-height: 1.4; color: var(--sub); margin: 0; }
p { margin: 0; }
button, input, select { font: inherit; color: inherit; }
:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }

.page { display: flex; flex-direction: column; height: 100%; }
header.top {
  display: flex; align-items: center; gap: var(--s2);
  min-height: var(--header-height, 56px); padding: 0 var(--s3);
  background: var(--app-header-background-color, var(--primary-color));
  color: var(--app-header-text-color, var(--text-primary-color));
  border-bottom: 1px solid var(--line);
}
header.top h1 { font-weight: 400; margin: 0 var(--s1); white-space: nowrap; }
header.top :focus-visible { outline-color: currentColor; }
.grow { flex: 1; min-width: 0; }
.iconbtn {
  display: inline-flex; align-items: center; justify-content: center; flex: none;
  width: var(--tap); height: var(--tap); border: 0; border-radius: 50%;
  background: none; color: inherit; cursor: pointer;
}
.iconbtn:hover { background: color-mix(in srgb, currentColor 12%, transparent); }
.tabs { display: flex; gap: var(--s1); overflow-x: auto; }
.tab {
  min-height: var(--tap); border: 0; background: none; cursor: pointer;
  padding: 0 var(--s4); border-radius: calc(var(--tap) / 2); white-space: nowrap;
}
.tab.on { background: color-mix(in srgb, currentColor 18%, transparent); font-weight: 500; }
.bar { height: 3px; flex: none; }
.busy .bar {
  background: linear-gradient(90deg, transparent, var(--primary-color), transparent);
  background-size: 50% 100%; background-repeat: no-repeat;
  animation: slide 1s linear infinite;
}
@keyframes slide { from { background-position: 150% 0; } to { background-position: -50% 0; } }

main.layout {
  flex: 1; min-height: 0; overflow: auto; padding: var(--s4);
  display: grid; gap: var(--s4); align-items: start;
  grid-template-columns: minmax(320px, 420px) 1fr;
}
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: var(--r);
}
.phone { position: sticky; top: 0; padding: var(--s4); display: grid; gap: var(--s3); }

/* פירורי לחם */
.crumbs { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s1); margin: 0; padding: 0; list-style: none; }
.crumbs li { display: inline-flex; align-items: center; gap: var(--s1); }
.crumbs li + li::before { content: "‹"; color: var(--sub); }
.crumb {
  display: inline-flex; align-items: center; min-height: var(--tap); padding: 0 var(--s2); border: 0; border-radius: var(--r-in);
  background: none; color: var(--ink); cursor: pointer;
}
.crumb:hover { background: var(--tint); }
.crumb[aria-current] { color: var(--fg); font-weight: 500; cursor: default; background: none; }

/* הלוח */
.pad { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--s2); direction: ltr; }
.key {
  position: relative; direction: rtl; aspect-ratio: 1 / 1; min-width: 0; min-height: var(--tap);
  padding: var(--s5) var(--s2) var(--s2);
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--s1);
  border-radius: var(--r); border: 1px solid var(--line); background: var(--raise);
  text-align: center; cursor: pointer; overflow: hidden;
  transition: transform 0.08s, border-color 0.15s, background-color 0.15s;
}
.key:hover { border-color: var(--line-strong); }
.key:active { transform: scale(0.97); }
.k-digit {
  position: absolute; top: var(--s2); left: var(--s3);
  font-size: 20px; font-weight: 500; line-height: 1; color: var(--sub);
  font-variant-numeric: tabular-nums;
}
.k-grip {
  position: absolute; top: var(--s1); right: var(--s1); display: inline-flex;
  color: var(--sub); opacity: 0; cursor: grab; transition: opacity 0.15s;
}
.k-grip .icon { width: 20px; height: 20px; }
.key:hover .k-grip, .key:focus-visible .k-grip { opacity: 1; }
.k-icon { color: var(--ink); }
.k-name {
  font-size: 14px; font-weight: 500; line-height: 1.25; max-width: 100%; overflow-wrap: anywhere;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.k-sub {
  font-size: 12px; line-height: 1.4; color: var(--sub); max-width: 100%; min-height: 17px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.k-empty { background: none; border: 1.5px dashed var(--line-strong); color: var(--sub); }
.k-empty .k-icon { color: var(--sub); }
.k-empty .k-name { font-weight: 400; }
.k-empty:hover { border-color: var(--ink); color: var(--ink); }
.k-empty:hover .k-icon { color: var(--ink); }
.k-off, .k-off:hover { cursor: default; border-color: var(--line); color: var(--sub); }
.k-off .k-icon, .k-off .k-name { opacity: 0.45; }
.k-off:active { transform: none; }
.k-stack { box-shadow: 0 3px 0 -1px var(--raise2), 0 4px 0 -1px var(--line-strong); }
.k-assist { background: var(--assist-tint); border-color: color-mix(in srgb, var(--assist-ink) 35%, var(--card)); }
.k-assist .k-icon { color: var(--assist-ink); }
.k-fixed { border: 1.5px solid var(--ink); background: color-mix(in srgb, var(--primary-color) 6%, var(--card)); }
.k-dictate { background: var(--info-tint); border-color: color-mix(in srgb, var(--info-ink) 35%, var(--card)); }
.k-dictate .k-icon { color: var(--info-ink); }
.k-removed { border: 1.5px dashed var(--err-ink); }
.k-removed .k-icon { color: var(--err-ink); }
.k-unavailable .k-icon { color: var(--warn-ink); }
.k-nav { background: none; border-color: transparent; }
.k-nav .k-digit { position: static; font-size: 20px; }
.k-nav.k-off .k-digit { opacity: 0.6; }
.key.sel { border-color: var(--ink); box-shadow: inset 0 0 0 1.5px var(--ink); }
.key.carried { border: 1.5px dashed var(--ink); opacity: 0.6; }
.key.over { background: var(--tint); border: 2px dashed var(--ink); }
.key.flash { animation: flash 1.2s ease-out; }
@keyframes flash { from { box-shadow: 0 0 0 6px var(--tint); } to { box-shadow: 0 0 0 0 transparent; } }

/* תגיות אזהרה */
.tag {
  display: inline-flex; align-items: center; gap: var(--s1); max-width: 100%;
  min-height: 20px; padding: 0 var(--s2); border-radius: 10px;
  font-size: 12px; font-weight: 500; line-height: 1.2; white-space: nowrap;
  background: var(--raise2); color: var(--sub);
}
.tag::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: none; }
.tag-removed { background: var(--err-tint); color: var(--err-ink); }
.tag-unavailable { background: var(--warn-tint); color: var(--warn-ink); }
.tag-new { background: var(--ok-tint); color: var(--ok-ink); }
.tag-fixed { background: var(--tint); color: var(--ink); }

.banner {
  display: flex; align-items: center; gap: var(--s2); padding: var(--s1) var(--s1) var(--s1) var(--s3);
  padding-inline: var(--s3) var(--s1);
  border-radius: var(--r-in); background: var(--tint); color: var(--fg);
}
.banner .icon { color: var(--ink); }
.loose { border-top: 1px solid var(--line); padding-top: var(--s3); display: grid; gap: var(--s1); }
.row { display: flex; align-items: center; gap: var(--s2); min-height: var(--tap); }
.row .grow { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* העורך */
.editor {
  position: sticky; top: 0; display: flex; flex-direction: column; overflow: auto;
  max-height: calc(100dvh - var(--header-height, 56px) - 3px - var(--s4) * 2);
}
.ed-head {
  position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: var(--s2);
  min-height: 60px; padding: var(--s2) var(--s4); padding-inline-start: var(--s2);
  background: var(--card); border-bottom: 1px solid var(--line);
}
.ed-head h2 { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.ed-head .lead { display: inline-flex; color: var(--ink); padding-inline-start: var(--s2); }
.badge {
  display: inline-flex; align-items: center; justify-content: center; flex: none;
  min-width: 36px; height: 36px; padding: 0 var(--s2); border-radius: var(--r-in);
  background: var(--ink); color: var(--card); font-size: 20px; font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.ed-form { display: flex; flex-direction: column; flex: 1; margin: 0; }
.ed-body { flex: 1; display: flex; flex-direction: column; gap: var(--s4); padding: var(--s4); }
.ed-foot {
  position: sticky; bottom: 0; z-index: 2; display: flex; flex-wrap: wrap; align-items: center; gap: var(--s2);
  padding: var(--s3) var(--s4); background: var(--card); border-top: 1px solid var(--line);
}
.section { display: grid; gap: var(--s2); }
.muted { color: var(--sub); }
.note {
  display: flex; gap: var(--s2); align-items: flex-start; padding: var(--s3);
  border-radius: var(--r-in); background: var(--warn-tint);
}
.note .icon { color: var(--warn-ink); }
.note.err { background: var(--err-tint); }
.note.err .icon { color: var(--err-ink); }
.note .grow { display: grid; gap: var(--s2); }
.note .btns { display: flex; flex-wrap: wrap; gap: var(--s2); }

.entity { display: flex; align-items: center; gap: var(--s2); flex-wrap: wrap; color: var(--sub); font-size: 12px; }
.entity .live { color: var(--fg); font-weight: 500; font-size: 14px; }

/* המתקשר שומע */
.heard-box { display: grid; gap: var(--s2); }
.heard-title { display: flex; align-items: center; gap: var(--s2); color: var(--sub); }
.heard-title .icon { width: 20px; height: 20px; }
.heard {
  margin: 0; padding: var(--s3) var(--s4); list-style: none; display: grid; gap: var(--s1);
  border-radius: var(--r); border-start-start-radius: var(--s1); background: var(--raise);
  border: 1px solid var(--line); font-size: 14px; line-height: 1.6;
}
.heard li.live { color: var(--ink); }

/* בחירה */
.choices { display: grid; gap: var(--s2); }
.choice {
  display: flex; align-items: center; gap: var(--s3); width: 100%; min-height: 56px; text-align: start;
  padding: var(--s2) var(--s3); border-radius: var(--r-in); border: 1px solid var(--line);
  background: none; cursor: pointer;
}
.choice:hover { border-color: var(--ink); background: var(--raise); }
.choice[aria-disabled] { cursor: default; }
.choice[aria-disabled]:hover { border-color: var(--line); background: none; }
.choice .icon { color: var(--ink); }
.choice b { display: block; font-weight: 500; }
.choice small { display: block; color: var(--sub); font-size: 12px; }
.choice .tag { flex: none; }

/* קבוצות של תיבות סימון */
.sub { border: 1px solid var(--line); border-radius: var(--r-in); overflow: hidden; }
.sub-head {
  display: flex; align-items: center; gap: var(--s2); min-height: var(--tap);
  padding-inline: var(--s3) var(--s1); background: var(--raise); border-bottom: 1px solid var(--line);
}
.sub-head .icon { width: 20px; height: 20px; color: var(--ink); }
.sub-rows { display: grid; padding: var(--s1); }
.bulk { display: inline-flex; flex: none; }
.link {
  min-height: var(--tap); padding: 0 var(--s2); border: 0; border-radius: var(--r-in);
  background: none; color: var(--ink); font-size: 12px; cursor: pointer;
}
.link:hover { background: var(--tint); }
.check {
  display: flex; align-items: center; gap: var(--s3); min-height: var(--tap);
  padding: var(--s1) var(--s2); border-radius: var(--r-in); cursor: pointer;
}
.check:hover { background: var(--raise); }
.check input { width: 20px; height: 20px; margin: 0; accent-color: var(--ink); flex: none; }
.check .grow { display: grid; }
.check small { color: var(--sub); font-size: 12px; }
.check .tag { flex: none; }
.fixrow {
  display: flex; align-items: center; gap: var(--s3); width: 100%; min-height: var(--tap);
  padding: var(--s1) var(--s2); border: 0; border-radius: var(--r-in); background: none;
  text-align: start; cursor: pointer;
}
.fixrow:hover { background: var(--raise); }
.fixrow .grow { display: grid; }
.fixrow small { color: var(--sub); font-size: 12px; }
.fixrow .go { color: var(--ink); font-weight: 500; font-size: 12px; white-space: nowrap; }

/* שדות */
label.field { display: grid; gap: var(--s1); font-size: 12px; color: var(--sub); }
input[type="text"], input[type="number"], input[type="search"], select {
  display: block; width: 100%; min-height: var(--tap); padding: 0 var(--s3); font-size: 14px;
  color: var(--fg); background: var(--card);
  border: 1px solid var(--line-strong); border-radius: var(--r-in); outline: none;
}
input:focus-visible, select:focus-visible { border-color: var(--ink); outline: 2px solid var(--ink); outline-offset: 0; }
.inline { display: flex; gap: var(--s2); align-items: flex-end; margin: 0; }
.inline label.field { flex: 1; }

/* כפתורים */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: var(--s2);
  min-height: var(--tap); padding: 0 var(--s4); border: 0; border-radius: var(--r-in);
  font-weight: 500; cursor: pointer; white-space: nowrap; background: none; color: var(--ink);
}
.btn .icon { width: 20px; height: 20px; }
.btn:hover { background: var(--tint); }
.btn.primary { background: var(--ink); color: var(--card); }
.btn.primary:hover { background: color-mix(in srgb, var(--ink) 88%, var(--primary-text-color)); }
.btn.tonal { background: var(--tint); }
.btn.danger { color: var(--err-ink); }
.btn.danger:hover { background: var(--err-tint); }
.btn.danger.sure { background: var(--err-ink); color: var(--card); }

.list { display: grid; gap: var(--s3); }
.picks { display: grid; }
.picks h4 { margin: var(--s2) 0 0; padding: var(--s1) var(--s2); font-size: 12px; font-weight: 500; color: var(--sub); }
.pick {
  display: flex; align-items: center; gap: var(--s3); width: 100%; min-height: var(--tap); text-align: start;
  padding: var(--s1) var(--s2); border: 0; border-radius: var(--r-in); background: none; cursor: pointer;
}
.pick:hover { background: var(--raise); }
.pick .icon { color: var(--sub); width: 20px; height: 20px; }
.pick .grow { display: grid; }
.pick small { color: var(--sub); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.empty-state { grid-column: 1 / -1; display: grid; justify-items: center; gap: var(--s4); padding: var(--s6) var(--s4); text-align: center; }
.empty-state .icon { width: 56px; height: 56px; color: var(--sub); }
.toast {
  position: fixed; bottom: calc(var(--s5) + env(safe-area-inset-bottom)); left: 50%; transform: translateX(-50%);
  max-width: calc(100% - var(--s6)); padding: var(--s3) var(--s4); border-radius: var(--r-in); z-index: 10;
  background: var(--fg); color: var(--card);
}

/* מסך צר: עמודה אחת, והעורך עולה מלמטה */
.page.narrow main.layout { grid-template-columns: minmax(0, 1fr); padding: var(--s3); gap: var(--s3); }
.page.narrow .phone, .page.narrow .editor { position: static; max-height: none; }
.page.narrow .phone { padding: var(--s3); }
/* במסך צר המקש קצת גבוה יותר, כדי ששם בשתי שורות ותגית ייכנסו */
.page.narrow .key { aspect-ratio: 5 / 6; padding-top: var(--s5); }
.page.narrow .editor.sheet {
  position: fixed; inset-inline: 0; top: auto; bottom: 0; z-index: 6; max-height: 88dvh;
  border-radius: var(--r) var(--r) 0 0; border-bottom: 0;
  padding-bottom: env(safe-area-inset-bottom);
  animation: rise 0.2s ease-out;
}
.sheet .ed-head::before {
  content: ""; position: absolute; top: var(--s1); left: 50%; width: 36px; height: 4px;
  margin-left: -18px; border-radius: 2px; background: var(--line-strong);
}
.scrim { position: fixed; inset: 0; z-index: 5; background: var(--mdc-dialog-scrim-color, rgba(0, 0, 0, 0.32)); }
@keyframes rise { from { transform: translateY(24px); opacity: 0; } to { transform: none; opacity: 1; } }
@media (hover: none) { .k-grip { display: none; } }
@media (prefers-reduced-motion: reduce) {
  *, *::before { animation: none !important; transition: none !important; }
}
`;

class HaIvrPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entries = null;
    this._blocked = new Set();
    this._entryId = "";
    this._level = null;
    this._mode = { name: "heard" };
    this._carry = null;
    this._busy = 0;
    this._toast = "";
    this._flash = "";
    this._sure = "";
    this._failed = "";
    this._cursor = "1";
    this._live = new Map();
    this._renders = 0;
    const root = this.shadowRoot;
    root.addEventListener("click", (ev) => this._onClick(ev));
    root.addEventListener("submit", (ev) => this._onSubmit(ev));
    root.addEventListener("input", (ev) => this._onInput(ev));
    root.addEventListener("keydown", (ev) => this._onKeyDown(ev));
    root.addEventListener("dragstart", (ev) => this._onDragStart(ev));
    root.addEventListener("dragover", (ev) => this._onDragOver(ev));
    root.addEventListener("dragleave", (ev) => this._dropTarget(ev)?.classList.remove("over"));
    root.addEventListener("drop", (ev) => this._onDrop(ev));
    root.addEventListener("dragend", () => {
      this._drag = "";
    });
  }

  // Home Assistant מעדכן את hass בכל שינוי בבית. העמוד אינו מצויר מחדש
  // בגללו: מתעדכנים רק המכשירים שמוצגים, ורק אם המצב שלהם השתנה.
  set hass(hass) {
    const before = this._hass;
    this._hass = hass;
    if (!this._started) {
      this._started = true;
      this._start();
      return;
    }
    if (before && hass && before.states !== hass.states) this._refresh(before.states || {});
  }

  get hass() {
    return this._hass;
  }

  set narrow(narrow) {
    if (narrow !== this._narrow) {
      this._narrow = narrow;
      this._render();
    }
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    this._render();
  }

  // ------------------------------------------------------------------
  // השרת
  // ------------------------------------------------------------------

  async _call(op, message = {}) {
    this._busy += 1;
    this._setBusy();
    try {
      return await this._hass.callWS({
        type: WS_TYPE, op, entry_id: this._entryId, ...message,
      });
    } catch (err) {
      this._say((err && err.message) || "הפעולה נכשלה");
      return null;
    } finally {
      this._busy -= 1;
      this._setBusy();
    }
  }

  _setBusy() {
    this.shadowRoot.querySelector(".page")?.classList.toggle("busy", this._busy > 0);
  }

  async _start() {
    const found = await this._call("entries");
    if (!found) {
      this._failed = "הלוח לא נטען. רעננו את העמוד.";
      this._render();
      return;
    }
    this._entries = found.entries;
    this._blocked = new Set(found.blocked);
    let wanted = "";
    try {
      wanted = localStorage.getItem(STORE_KEY) || "";
    } catch (_err) {
      wanted = "";
    }
    const entry = this._entries.find((e) => e.entry_id === wanted) || this._entries[0];
    if (!entry) {
      this._render();
      return;
    }
    await this._pickEntry(entry.entry_id);
  }

  async _pickEntry(entryId) {
    this._entryId = entryId;
    try {
      localStorage.setItem(STORE_KEY, entryId);
    } catch (_err) {
      // בלי אחסון מקומי פשוט לא זוכרים את הבחירה.
    }
    this._carry = null;
    await this._open("");
  }

  get _flags() {
    return (this._entries || []).find((e) => e.entry_id === this._entryId) || {};
  }

  async _open(path) {
    const level = await this._call("level", { path });
    if (!level) return;
    if (this._carry && this._carry.only !== undefined && this._carry.only !== level.path) {
      this._carry = null;
    }
    this._level = level;
    this._mode = { name: "heard" };
    this._sure = "";
    this._render();
  }

  // פעולה שמשנה. השרת מחזיר את הרמה המעודכנת, ומציירים אותה.
  async _change(op, message, { view, flash = "" } = {}) {
    const level = await this._call(op, {
      ...message, view: view === undefined ? this._level.path : view,
    });
    if (!level) return false;
    this._level = level;
    this._mode = { name: "heard" };
    this._carry = null;
    this._sure = "";
    this._flash = flash;
    this._render();
    return true;
  }

  _say(text) {
    this._toast = text;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this._toast = "";
      this._renderToast();
    }, 4500);
    this._renderToast();
  }

  _renderToast() {
    const box = this.shadowRoot.querySelector(".toast-box");
    if (box) box.replaceChildren(...(this._toast ? [h("div", { class: "toast" }, this._toast)] : []));
  }

  _path(digit) {
    return this._level.path ? `${this._level.path}/${digit}` : digit;
  }

  _go(url) {
    history.pushState(null, "", url);
    window.dispatchEvent(new CustomEvent("location-changed", { bubbles: true, composed: true }));
  }

  // ------------------------------------------------------------------
  // מצב המכשירים מתוך hass
  // ------------------------------------------------------------------

  _stateObj(eid) {
    const states = this._hass && this._hass.states;
    return eid && states ? states[eid] : undefined;
  }

  _stateText(eid) {
    const obj = this._stateObj(eid);
    if (!obj) return "";
    try {
      const text = typeof this._hass.formatEntityState === "function"
        ? this._hass.formatEntityState(obj) : obj.state;
      return typeof text === "string" && text ? text : String(obj.state ?? eid);
    } catch (_err) {
      return String(obj.state ?? eid);
    }
  }

  _attrText(eid, attr) {
    const obj = this._stateObj(eid);
    if (!obj || !obj.attributes || obj.attributes[attr] === undefined || obj.attributes[attr] === null) return "";
    try {
      const text = typeof this._hass.formatEntityAttributeValue === "function"
        ? this._hass.formatEntityAttributeValue(obj, attr) : obj.attributes[attr];
      return text === undefined || text === null ? "" : String(text);
    } catch (_err) {
      return String(obj.attributes[attr]);
    }
  }

  _entityName(eid) {
    const obj = this._stateObj(eid);
    if (!obj) return eid;
    const plain = (obj.attributes && obj.attributes.friendly_name) || eid;
    try {
      if (typeof this._hass.formatEntityName !== "function") return String(plain);
      const name = this._hass.formatEntityName(obj, [{ type: "device" }, { type: "entity" }]);
      return typeof name === "string" && name.trim() ? name : String(plain);
    } catch (_err) {
      return String(plain);
    }
  }

  // מכשיר שמוצג נרשם כאן, כדי שעדכון של hass יצבע רק אותו.
  _watch(eid, paint) {
    if (!eid) return;
    if (!this._live.has(eid)) this._live.set(eid, []);
    this._live.get(eid).push(paint);
  }

  _refresh(before) {
    const now = this._hass.states || {};
    for (const [eid, paints] of this._live) {
      if (before[eid] === now[eid]) continue;
      for (const paint of paints) paint();
    }
  }

  // ------------------------------------------------------------------
  // הציור
  // ------------------------------------------------------------------

  _render() {
    const root = this.shadowRoot;
    this._renders += 1;
    this._live = new Map();
    const active = root.activeElement;
    const keyFocused = Boolean(active && active.classList && active.classList.contains("key"));
    const page = h("div", { class: cls("page", this._busy > 0 && "busy", this._narrow && "narrow"), dir: "rtl" },
      this._header(),
      h("div", { class: "bar", "aria-hidden": "true" }),
      h("main", { class: "layout" }, this._main()),
      h("div", { class: "toast-box", role: "status", "aria-live": "polite" }));
    root.replaceChildren(h("style", null, STYLE), page);
    this._renderToast();
    this._flash = "";
    const focus = root.querySelector("[data-focus]");
    if (focus) {
      focus.focus({ preventScroll: true });
    } else if (keyFocused) {
      root.querySelector(`.key[data-digit="${quoted(this._cursor)}"]`)?.focus();
    } else if (this._narrow && this._mode.name !== "heard") {
      root.querySelector(".sheet .ed-head button")?.focus();
    }
  }

  _header() {
    const entries = this._entries || [];
    return h("header", { class: "top" },
      this._narrow ? btn("iconbtn", { "data-act": "menu", "aria-label": "תפריט", title: "תפריט" }, icon("menu")) : null,
      h("h1", { class: "t-title" }, "תפריט טלפוני"),
      entries.length > 1
        ? h("nav", { class: "tabs", "aria-label": "קווי טלפון" }, entries.map((e) => {
          const on = e.entry_id === this._entryId;
          return btn(cls("tab", on && "on"), {
            "data-act": "entry", "data-id": e.entry_id, "aria-current": on ? "page" : null,
          }, e.title);
        }))
        : null,
      h("span", { class: "grow" }),
      btn("iconbtn", {
        "data-act": "settings", "aria-label": "הגדרות הקו ואנשי קשר", title: "הגדרות הקו ואנשי קשר",
      }, icon("cog-outline")));
  }

  _main() {
    if (this._failed) {
      return h("div", { class: "empty-state" }, icon("alert-circle-outline"), h("p", null, this._failed));
    }
    if (this._entries && !this._entries.length) {
      return h("div", { class: "empty-state" }, icon("phone-plus-outline"),
        h("p", null, "עדיין לא הוגדר קו טלפון."),
        btn("btn primary", { "data-act": "settings" }, "הוספת קו"));
    }
    if (!this._level) return null;
    return [this._phone(), this._editor()];
  }

  _phone() {
    return h("section", { class: "card phone", "aria-label": "לוח המקשים" },
      this._crumbs(), this._carryBanner(), this._pad(), this._loose());
  }

  _crumbs() {
    const crumbs = this._level.crumbs || [];
    const last = crumbs.length - 1;
    return h("nav", { "aria-label": "מיקום בתפריט" },
      h("ol", { class: "crumbs" }, crumbs.map((c, i) => h("li", null, i === last
        ? h("span", { class: "crumb", "aria-current": "page" }, c.name)
        : btn("crumb", { "data-act": "open", "data-path": c.path }, c.name)))));
  }

  _carryBanner() {
    if (!this._carry) return null;
    return h("div", { class: "banner", role: "status" }, icon("cursor-move"),
      h("span", { class: "grow" }, `מעבירים את «${this._carry.name}». בחרו מקש.`),
      btn("btn", { "data-act": "carry-cancel" }, "ביטול"));
  }

  _pad() {
    const level = this._level;
    const depth = level.path ? level.path.split("/").length : 0;
    if (!PAD.includes(this._cursor)) this._cursor = "1";
    const keys = "123456789".split("").map((d) => this._key(d));
    keys.push(
      this._navKey("*", depth > 1, { act: "open", path: "", name: "לתפריט הראשי", icon: "home-outline" }),
      this._navKey("0", depth > 0, { act: "up", name: "חזרה", icon: "keyboard-return" }),
      this._navKey("#", false, {}),
    );
    return h("div", { class: "pad", role: "group", "aria-label": "מקשי הטלפון. החצים עוברים בין המקשים." }, keys);
  }

  _tabindex(digit) {
    return digit === this._cursor ? "0" : "-1";
  }

  _digit(digit) {
    return h("span", { class: "k-digit", "aria-hidden": "true" }, ltr(digit));
  }

  _navKey(digit, on, { act, path, name, icon: iconName }) {
    return btn(cls("key k-nav", !on && "k-off"), {
      "data-digit": digit, "data-act": on ? act : null, "data-path": on ? path : null,
      "aria-disabled": on ? null : "true", tabindex: this._tabindex(digit),
      "aria-label": on ? `מקש ${digit}: ${name}` : `מקש ${digit}`,
    },
    this._digit(digit),
    on && iconName ? icon(iconName, "k-icon") : null,
    h("span", { class: "k-name" }, on ? name : ""),
    h("span", { class: "k-sub" }));
  }

  _canAdd() {
    const level = this._level;
    if (level.kind === "menu") return level.can_add;
    return Boolean(this._addable().length);
  }

  _key(digit) {
    const key = this._level.keys[digit];
    const mode = this._mode;
    const chosen = (mode.name === "add" || mode.name === "info") && mode.digit === digit;
    const base = { "data-digit": digit, "data-drop": digit, tabindex: this._tabindex(digit) };
    if (!key) {
      const open = Boolean(this._carry) || this._canAdd();
      const name = this._carry ? "לכאן" : "הוספה";
      return btn(cls("key k-empty", chosen && "sel", !open && "k-off"), {
        ...base, "data-act": "empty",
        "aria-label": open ? `מקש ${digit}: ריק. ${name}` : `מקש ${digit}: ריק`,
      },
      this._digit(digit),
      icon(this._carry ? "arrow-down-bold-outline" : "plus", "k-icon"),
      h("span", { class: "k-name" }, name),
      h("span", { class: "k-sub" }));
    }
    const el = btn(cls(
      "key", `k-${keyType(key)}`,
      chosen && "sel",
      this._carry && this._carry.path === key.path && "carried",
      this._flash === digit && "flash",
    ), { ...base, "data-act": "key", draggable: "true", title: key.name },
    this._digit(digit),
    h("span", { class: "k-grip", "aria-hidden": "true" }, icon("drag")),
    icon(iconOf(key), "k-icon"),
    h("span", { class: "k-name" }, key.name),
    h("span", { class: "k-sub" }));
    const paint = () => this._paintKey(el, key);
    paint();
    if (key.entity_id) this._watch(key.entity_id, paint);
    return el;
  }

  // מה שמשתנה במקש עם מצב המכשיר: שורת המשנה, התגית והתווית לקורא המסך.
  _paintKey(el, key) {
    const alert = this._alert(key);
    const sub = this._keySub(key);
    const line = el.querySelector(".k-sub");
    line.replaceChildren(...(alert ? [this._tag(alert.kind, alert.text)] : [sub].flat()));
    el.classList.toggle("k-removed", Boolean(alert && alert.kind === "removed"));
    el.classList.toggle("k-unavailable", Boolean(alert && alert.kind === "unavailable"));
    const parts = [`מקש ${key.digit || ""}: ${key.name}`, line.textContent];
    el.setAttribute("aria-label", parts.filter(Boolean).join(". "));
  }

  // אזהרה על מקש: מכשיר שהוסר, לא זמין, קבוצה ריקה או מקש שאינו מוקרא.
  _alert(key) {
    if (key.entity_id) {
      const hasStates = Boolean(this._hass && this._hass.states);
      const obj = this._stateObj(key.entity_id);
      if (hasStates ? !obj : key.missing || key.state === "missing") {
        return { kind: "removed", text: "המכשיר הוסר" };
      }
      if (hasStates ? obj.state === "unavailable" : key.state === "unavailable") {
        return { kind: "unavailable", text: "לא זמין" };
      }
    }
    if (key.kind === "cap" && key.gone) return { kind: "unavailable", text: "לא זמין" };
    if (key.kind === "group" && key.missing) return { kind: "unavailable", text: "אין מכשירים" };
    if (key.silent) return { kind: "quiet", text: "לא מוקרא" };
    return null;
  }

  _keySub(key) {
    if (key.kind === "device" && key.entity_id) {
      return joined([this._stateText(key.entity_id), key.detail]);
    }
    if (key.kind === "action") return key.does || key.detail || "";
    if (key.kind === "goto" && key.target) return ltr(key.target);
    return key.detail || "";
  }

  _tag(kind, text) {
    return h("span", { class: `tag tag-${kind}` }, text);
  }

  _loose() {
    const loose = this._level.loose || [];
    if (!loose.length) return null;
    return h("div", { class: "loose" },
      h("h3", { class: "t-label" }, "פריטים בלי מקש. המתקשר אינו מגיע אליהם"),
      loose.map((item) => h("div", { class: "row" },
        h("span", { class: "grow" }, item.title),
        btn("btn", { "data-act": "loose-place", "data-id": item.id, "data-name": item.title }, "שיבוץ במקש"),
        this._removeButton("loose-remove", { "data-id": item.id }, "מחיקה", "למחוק?"))));
  }

  // ------------------------------------------------------------------
  // העורך: מה שומעים, הוספה, פרטי מקש
  // ------------------------------------------------------------------

  _editor() {
    const view = this._view();
    const sheet = Boolean(this._narrow) && this._mode.name !== "heard";
    const head = h("div", { class: "ed-head" },
      view.back ? btn("iconbtn", { "data-act": view.back, "aria-label": "חזרה", title: "חזרה" }, icon("arrow-right")) : null,
      view.lead ? h("span", { class: "lead" }, icon(view.lead)) : null,
      view.digit ? h("span", { class: "badge", "aria-hidden": "true" }, ltr(view.digit)) : null,
      h("h2", { class: "t-title", id: "ed-title" }, view.digit ? h("span", { class: "sr" }, `מקש ${view.digit}: `) : null, view.title),
      sheet && view.back !== "close" ? btn("iconbtn", { "data-act": "close", "aria-label": "סגירה", title: "סגירה" }, icon("close")) : null);
    const body = h("div", { class: "ed-body" }, view.body);
    const foot = view.foot && view.foot.flat(Infinity).filter(Boolean).length
      ? h("div", { class: "ed-foot" }, view.foot) : null;
    const content = view.form
      ? h("form", { class: "ed-form", "data-form": view.form, ...(view.formAttrs || {}) }, body, foot)
      : [body, foot];
    const aside = h("aside", {
      class: cls("card editor", sheet && "sheet"), "aria-labelledby": "ed-title",
      role: sheet ? "dialog" : null, "aria-modal": sheet ? "true" : null,
    }, head, content);
    return sheet ? [h("div", { class: "scrim", "data-act": "close", "aria-hidden": "true" }), aside] : aside;
  }

  _view() {
    const mode = this._mode;
    if (mode.name === "add") return this._addView();
    if (mode.name === "info") return this._infoView();
    if (mode.name === "build") return this._buildView();
    if (mode.name === "edit") return this._editView();
    return this._heardView();
  }

  _removeButton(act, attrs, label, sure) {
    const key = `${act}:${Object.values(attrs).join("|")}`;
    const on = this._sure === key;
    return btn(cls("btn danger", on && "sure"), { "data-act": act, ...attrs, "data-sure": key },
      icon("delete-outline"), on ? sure : label);
  }

  _note(text, { err = false, buttons = null } = {}) {
    return h("div", { class: cls("note", err && "err"), role: err ? "alert" : null },
      icon("alert-outline"),
      h("div", { class: "grow" }, h("span", null, text), buttons ? h("div", { class: "btns" }, buttons) : null));
  }

  // הבועה של "המתקשר שומע". שורות שמשתנות בזמן הקלדה מסומנות data-live.
  _heardBox(lines, { intro = null, name = null } = {}) {
    const items = [];
    let introDone = false;
    lines.forEach((line, index) => {
      const li = h("li", null, line);
      if (intro !== null && index === 0 && intro && line === intro) {
        li.setAttribute("data-live", "intro");
        introDone = true;
      } else if (name && line.includes(name)) {
        li.setAttribute("data-live", "name");
        li._line = line;
        li._name = name;
      }
      items.push(li);
    });
    if (intro !== null && !introDone) {
      items.unshift(h("li", { class: "live", "data-live": "intro", hidden: !intro }, intro || ""));
    }
    return h("div", { class: "heard-box" },
      h("div", { class: "heard-title" }, icon("volume-high"), h("span", { class: "t-label" }, "המתקשר שומע")),
      h("ul", { class: "heard", "aria-live": "polite" }, items));
  }

  _heardView() {
    const level = this._level;
    const self = level.self;
    const root = !level.path;
    const filled = Object.values(level.keys).some(Boolean);
    const body = [];
    if (level.heard.length) {
      body.push(this._heardBox(level.heard, { intro: level.intro }));
    } else if (root && !filled) {
      body.push(h("p", null, "התפריט עדיין ריק. לחצו על מקש בלוח כדי לקבוע מה יקרה כשמתקשר מקיש עליו."),
        h("div", null, btn("btn primary", { "data-act": "build" }, icon("home-group"), "לבנות תפריט מהחדרים בבית")));
    } else if (!filled) {
      body.push(this._note("אין כאן עדיין מקשים, ולכן המתקשר אינו שומע על התפריט הזה. לחצו על מקש כדי להוסיף."));
    } else {
      body.push(this._note("המתקשר אינו מגיע לכאן כרגע."));
    }

    if (level.intro !== null && level.intro !== undefined) {
      body.push(h("form", { class: "inline", "data-form": "intro" },
        h("label", { class: "field" }, "משפט פתיחה (לא חובה)",
          h("input", { type: "text", name: "intro", value: level.intro, placeholder: root ? "שלום, הגעתם לבית" : null })),
        h("button", { type: "submit", class: "btn tonal" }, "שמירה")));
    }

    let foot = null;
    if (self) {
      const menu = self.kind === "submenu";
      const label = self.kind === "cap" ? "שם הפעולה" : menu ? "שם התפריט" : "שם בטלפון";
      body.push(h("div", { class: "section" },
        h("h3", { class: "t-label" }, `מקש ${self.digit}`),
        self.entity_id ? this._entityLine(self.entity_id) : null,
        h("form", { class: "inline", "data-form": "rename", "data-path": level.path },
          h("label", { class: "field" }, label,
            h("input", { type: "text", name: "name", value: self.label, placeholder: self.name })),
          h("button", { type: "submit", class: "btn tonal" }, "שמירה")),
        self.missing
          ? this._note(self.kind === "group" ? "אין כרגע מכשירים בקבוצה הזו." : "המכשיר הזה אינו קיים עוד.")
          : null));
      foot = [
        self.kind === "group" ? btn("btn", { "data-act": "edit-place", "data-path": level.path }, "שינוי המקום והמכשירים") : null,
        btn("btn", { "data-act": "carry", "data-path": level.path, "data-name": self.name, "data-up": "1" },
          icon("cursor-move"), "העברה למקש אחר"),
        h("span", { class: "grow" }),
        this._removeButton("remove", { "data-path": level.path }, "הסרה", menu ? "למחוק עם כל מה שבתוכו?" : "להסיר?"),
      ];
    }

    if (root && filled && level.can_add) {
      body.push(h("div", null, btn("btn", { "data-act": "build" }, icon("home-group"), "הוספת חדרים שלמים למקשים הפנויים")));
    }
    body.push(h("p", { class: "t-sub" }, "לחיצה על מקש מלא פותחת אותו. לחיצה על מקש ריק מוסיפה. אפשר גם לגרור מקש למקום אחר."));
    const crumbs = level.crumbs || [];
    const here = crumbs.length ? crumbs[crumbs.length - 1].name : "ראשי";
    return { title: here, digit: self ? self.digit : null, lead: self ? null : "home-outline", body, foot };
  }

  // שורת המכשיר: המזהה, והמצב החי שלו.
  _entityLine(eid) {
    const live = h("span", { class: "live" });
    const line = h("div", { class: "entity" }, live, ltr(eid));
    const domain = eid.split(".", 1)[0];
    const paint = () => {
      const obj = this._stateObj(eid);
      const extra = MAIN_ATTR[domain] ? this._attrText(eid, MAIN_ATTR[domain]) : "";
      live.replaceChildren(...(obj
        ? joined([this._stateText(eid), extra])
        : [this._tag("removed", "המכשיר הוסר")]));
    };
    paint();
    this._watch(eid, paint);
    return line;
  }

  _describe(key) {
    if (key.kind === "action") {
      return `פעולה אחת במכשיר «${key.detail}»${key.does ? `: ${key.does}` : ""}.`;
    }
    if (key.kind === "goto") return ["מעביר את השיחה לשלוחה ", ltr(key.target), "."];
    if (key.kind === "assistant") return "מחבר את המתקשר לעוזר הקולי של הבית.";
    if (key.kind === "alerts") return "מקריא את ההתראות האחרונות שנשלחו לטלפון.";
    if (key.kind === "option") return "אחת האפשרויות שהמתקשר בוחר מהן.";
    if (key.cap === "status") return "מקריא את המצב הנוכחי.";
    if (key.cap === "text") return "המתקשר אומר משפט, והוא נשלח כטקסט.";
    if (key.cap === "number") return `${key.detail}.`;
    return "פעולה בהקשה אחת.";
  }

  _infoView() {
    const key = this._level.keys[this._mode.digit];
    if (!key) return this._heardView();
    const flags = this._flags;
    const body = [h("p", { class: "muted" }, this._describe(key))];
    if (key.entity_id) body.push(this._entityLine(key.entity_id));

    const alert = this._alert(key);
    if (alert && alert.kind === "removed") {
      body.push(this._note("המכשיר הזה הוסר מ-Home Assistant. המקש לא יעשה דבר עד שתחליפו אותו או תסירו אותו.", {
        err: true,
        buttons: [
          btn("btn tonal", { "data-act": "replace", "data-digit": key.digit, "data-path": key.path },
            icon("swap-horizontal"), "החלפה במכשיר אחר"),
          this._removeButton("remove", { "data-path": key.path }, "הסרת המקש", "להסיר?"),
        ],
      }));
    } else if (alert && alert.kind === "unavailable") {
      body.push(this._note(key.kind === "cap"
        ? "המכשיר כבר אינו מדווח על היכולת הזו. המקש נשאר במקומו."
        : "המכשיר אינו זמין כרגע."));
    } else if (key.silent) {
      body.push(this._note("המקש הזה אינו מוקרא למתקשר כרגע."));
    }

    if (key.kind !== "option") {
      body.push(h("form", { class: "inline", "data-form": "rename", "data-path": key.path },
        h("label", { class: "field" }, key.kind === "cap" ? "שם הפעולה" : "שם בטלפון",
          h("input", { type: "text", name: "name", value: key.label, placeholder: key.name, "data-focus": true })),
        h("button", { type: "submit", class: "btn tonal" }, "שמירה")));
    }
    // יעד נערך רק היכן שהמשתמש הוא שקבע אותו: שלוחה שהוא בחר, או
    // שלוחת העוזר אצל ספק שאין לו יעד קבוע לעוזר.
    const editable = key.kind === "goto"
      ? flags.extensions
      : key.kind === "assistant" && !flags.assistant_target;
    if (editable) {
      body.push(h("form", { class: "inline", "data-form": "target", "data-path": key.path },
        h("label", { class: "field" }, key.kind === "assistant" ? "השלוחה שמחוברת לעוזר הקולי" : "לאן עוברים",
          h("input", { type: "text", name: "target", dir: "ltr", inputmode: "tel", value: key.target })),
        h("button", { type: "submit", class: "btn tonal" }, "שמירה")));
      if (flags.goto_hint) body.push(h("p", { class: "t-sub" }, flags.goto_hint));
    }
    const said = (this._level.heard || []).filter((line) => key.name && line.includes(key.name));
    if (said.length) body.push(this._heardBox(said, { name: key.name }));

    const foot = [
      key.fixed ? btn("btn", { "data-act": "edit-value", "data-path": key.path }, icon("tune-variant"), "שינוי הערך") : null,
      btn("btn", { "data-act": "carry", "data-path": key.path, "data-name": key.name }, icon("cursor-move"), "העברה למקש אחר"),
      h("span", { class: "grow" }),
      alert && alert.kind === "removed" ? null : this._removeButton("remove", { "data-path": key.path }, "הסרה", "להסיר?"),
    ];
    return { title: key.name, digit: key.digit, back: "close", body, foot };
  }

  _choice(act, iconName, title, text, attrs = {}, tag = null) {
    return btn("choice", { "data-act": act, ...attrs },
      icon(iconName),
      h("span", { class: "grow" }, h("b", null, title), text ? h("small", null, text) : null),
      tag);
  }

  // מה שאפשר להוסיף ברמה הזו. הכתבה רק בקו עם סטרימינג.
  _addable() {
    const level = this._level;
    return (level.addable || []).filter((item) => level.kind !== "plan" || item.kind !== "text" || level.streaming);
  }

  // הערה קצרה ליכולת: כמה אפשרויות, איזה טווח, איך מקישים קוד.
  _capNote(c) {
    if (c.needs_fixed || c.kind === "fixed") return "קובעים ערך אחד מראש";
    if (c.code) {
      if (c.code.end) return ["מקישים קוד ואחריו ", ltr("#")];
      if (c.code.width) return `קוד של ${c.code.width} ספרות`;
      return "מקישים קוד";
    }
    if (c.kind === "choice") return `${(c.options || []).length} אפשרויות`;
    if (c.kind === "number" && c.min !== null && c.min !== undefined && c.max !== null && c.max !== undefined) {
      return ["טווח ", ltr(c.min), " עד ", ltr(c.max)];
    }
    if (c.kind === "status") return "מקריא את המצב הנוכחי";
    if (c.kind === "text") return c.max_length ? `המתקשר אומר, עד ${c.max_length} תווים` : "המתקשר אומר, והטקסט נשלח";
    return "";
  }

  _addView() {
    const mode = this._mode;
    const level = this._level;
    const flags = this._flags;
    const digit = mode.digit;
    const first = mode.step === "what" || (mode.replace && mode.step === "device");
    const view = (title, body, extra = {}) => ({ title, digit, back: first ? "close" : "add-back", body, ...extra });
    const submit = (label) => h("button", { type: "submit", class: "btn primary" }, label);

    if (level.kind !== "menu") {
      const items = this._addable();
      if (level.kind === "plan") {
        const groups = CAP_GROUPS.map((g) => {
          const rows = items.filter((c) => capGroup(c) === g.id).map((c) => (g.id === "fixed"
            ? h("div", { class: "choice", "aria-disabled": "true" }, icon(g.icon),
              h("span", { class: "grow" }, h("b", null, c.name || c.label),
                h("small", null, "אפשר להוסיף רק כמקש עם ערך קבוע, בתפריט שמעל")),
              c.new ? this._tag("new", "יכולת חדשה") : null)
            : this._choice("add-part", g.icon, c.name || c.label, this._capNote(c),
              { "data-ident": c.ident ?? "" }, c.new ? this._tag("new", "יכולת חדשה") : null)));
          return rows.length ? h("section", { class: "section" }, h("h3", { class: "t-sub" }, g.title), h("div", { class: "choices" }, rows)) : null;
        });
        return view("איזו פעולה להוסיף?", [
          h("p", { class: "t-sub" }, "יכולות שהמכשיר מדווח עליהן ועדיין אין להן מקש. שום דבר לא נוסף מעצמו."),
          groups,
        ]);
      }
      return view("איזו אפשרות להחזיר?", h("div", { class: "choices" }, items.map((item) => this._choice(
        "add-part", "radiobox-marked", item.label, "", { "data-ident": item.ident ?? "", "data-value": item.value ?? "" },
      ))));
    }

    if (mode.step === "device") {
      return view(mode.replace ? "במה להחליף?" : "איזה מכשיר?", [
        h("label", { class: "field" }, "חיפוש לפי שם, חדר או מזהה",
          h("input", { type: "search", "data-search": true, "data-focus": true, value: mode.query || "", autocomplete: "off" })),
        h("div", { class: "picks", id: "devices" }, this._deviceList(mode.query || "")),
      ]);
    }

    if (mode.step === "caps") return this._capsView(view, submit);

    if (mode.step === "options") {
      const sections = this._choices(mode.idents).map((c) => this._group(
        c.name, c.options.length > 9 ? "עד 9, מקש לכל ערך" : `${c.options.length} אפשרויות`, "format-list-bulleted",
        this._bulk(`opt:${c.ident}`, c.options.length),
        c.options.map((o, index) => this._check(`opt:${c.ident}`, o.value, o.label, { checked: index < 9 })),
      ));
      return view(mode.found.name, [
        h("p", { class: "muted" }, "אילו ערכים להציע למתקשר. מסירים סימון ממה שאין בו צורך."),
        h("div", { class: "list" }, sections),
      ], { form: "options", foot: [submit(`הוספה למקש ${digit}`)] });
    }

    if (mode.step === "fixed") {
      const actions = mode.fixed.actions.map((a, index) => this._choice(
        "add-values", "tune-variant", a.label, a.fields.map((f) => f.label).join(" · "), { "data-index": index },
      ));
      return view(mode.fixed.name, [
        h("p", { class: "muted" }, "המקש יעשה דבר אחד, עם הערך שתקבעו עכשיו."),
        h("div", { class: "choices" }, actions),
      ]);
    }

    if (mode.step === "values") {
      const action = mode.action;
      return view(action.label, [
        h("p", { class: "muted" }, "ממלאים רק את מה שהמקש צריך לקבוע. שדה ריק נשאר כמו שהוא במכשיר."),
        action.fields.map((f) => this._field(f)),
        h("label", { class: "field" }, "שם בטלפון (לא חובה)",
          h("input", { type: "text", name: "_name", placeholder: `למשל: ${mode.fixed.name} ל-24` })),
      ], { form: "fixed", foot: [submit(`הוספה למקש ${digit}`)] });
    }

    if (mode.step === "places") {
      const found = mode.places;
      const part = (title, name, items) => (items.length
        ? this._group(title, "", null, this._bulk(name, items.length), items.map((i) => this._check(name, i.id, i.name)))
        : null);
      return view("אילו מקומות יחד?", h("div", { class: "list" },
        part("קומות", "floor_id", found.floors),
        part("חדרים", "area_id", found.areas),
        part("תוויות", "label_id", found.labels)),
      { form: "places", foot: [submit("המשך")] });
    }

    if (mode.step === "room") {
      const rooms = (mode.rooms || []).map((room, index) => this._choice(
        "add-room", room.area_id ? "door-open" : "home-outline", room.name,
        room.kinds.map((k) => k.name).join(" · "), { "data-index": index },
      ));
      return view("איזה חדר?", [
        rooms.length ? h("div", { class: "choices" }, rooms) : h("p", { class: "muted" }, "לא נמצאו חדרים עם מכשירים שאפשר להפעיל."),
        h("div", { class: "choices" }, this._choice("add-places", "home-group", "כמה מקומות יחד", "כמה חדרים, קומה שלמה או תווית")),
      ]);
    }

    if (mode.step === "kinds") {
      const room = mode.room;
      if (!room.kinds.length) return view(room.name, h("p", { class: "muted" }, "אין כאן מכשירים שאפשר להפעיל בטלפון."));
      const kinds = room.kinds.map((k) => this._check("kind", k.domain, k.name, {
        checked: !mode.domains || mode.domains.includes(k.domain), sub: `${Number(k.count)} מכשירים`,
      }));
      return view(room.name, [
        this._group("מה לכלול", "", null, this._bulk("kind", room.kinds.length), kinds),
        level.can_nest ? null : h("p", { class: "t-sub" }, "בעומק הזה אפשר לבחור סוג אחד בלבד."),
        h("p", { class: "t-sub" }, "בהמשך בוחרים אילו מכשירים ואילו פעולות. «הוספה מיד» מכניסה את כולם, ואפשר להסיר אחר כך מתוך המקש."),
      ], {
        form: "room",
        foot: [
          h("button", { type: "submit", class: "btn primary", "data-go": "next" }, "המשך"),
          h("button", { type: "submit", class: "btn", "data-go": "add" }, "הוספה מיד, עם הכול"),
        ],
      });
    }

    if (mode.step === "members") {
      const room = mode.room;
      const out = mode.exclude || [];
      const of = (domain) => room.members.filter((m) => m.domain === domain);
      const sections = room.kinds.filter((k) => mode.domains.includes(k.domain)).map((k) => this._group(
        k.name, "", DOMAIN_ICONS[k.domain] || "devices", this._bulk(`member:${k.domain}`, of(k.domain).length),
        of(k.domain).map((m) => this._check(`member:${k.domain}`, m.entity_id, m.name, {
          checked: !out.includes(m.entity_id), sub: ltr(m.entity_id),
        })),
      ));
      return view("אילו מכשירים?", [
        h("p", { class: "muted" }, "מסירים סימון ממכשיר שלא רוצים לכלול. מכשיר חדש שיתווסף למקום הזה יצטרף מעצמו."),
        h("div", { class: "list" }, sections),
      ], { form: "members", foot: [submit("המשך")] });
    }

    if (mode.step === "functions") {
      const sections = mode.functions.map((k) => this._group(
        k.name, "", DOMAIN_ICONS[k.domain] || "devices", this._bulk(`cap:${k.domain}`, k.capabilities.length),
        k.capabilities.map((c) => this._check(`cap:${k.domain}`, c.ident, c.label, { checked: true })),
      ));
      return view("מה המתקשר יוכל לעשות?", [
        sections.length ? h("div", { class: "list" }, sections) : h("p", { class: "muted" }, "אין פעולה שכל המכשירים שנבחרו יודעים לעשות."),
        h("label", { class: "field" }, "שם בטלפון (לא חובה)",
          h("input", { type: "text", name: "name", placeholder: mode.room.name })),
      ], { form: "functions", foot: [submit(`הוספה למקש ${digit}`)] });
    }

    if (mode.step === "submenu") {
      return view("תפריט חדש", h("label", { class: "field" }, "איך לקרוא לו",
        h("input", { type: "text", name: "name", placeholder: "למשל: קומה עליונה", "data-focus": true })),
      { form: "submenu", foot: [submit("הוספה")] });
    }

    if (mode.step === "goto" || mode.step === "assistant") {
      const assistant = mode.step === "assistant";
      return view(assistant ? "עוזר קולי" : "מעבר לשלוחה אחרת", [
        h("label", { class: "field" }, assistant ? "השלוחה שמחוברת לעוזר הקולי" : "לאן עוברים",
          h("input", { type: "text", name: "target", dir: "ltr", inputmode: "tel", "data-focus": true })),
        flags.goto_hint ? h("p", { class: "t-sub" }, flags.goto_hint) : null,
        h("label", { class: "field" }, `שם בטלפון${assistant ? " (לא חובה)" : ""}`,
          h("input", { type: "text", name: "name", placeholder: assistant ? "עוזר קולי" : "למשל: המשרד" })),
      ], { form: mode.step, foot: [submit("הוספה")] });
    }

    const choices = [
      this._choice("add-step", "lightbulb-outline", "מכשיר", "אור, מזגן, תריס, סצנה. כל דבר שיש בבית", { "data-step": "device" }),
      this._choice("add-step", "door-open", "חדר שלם", "כל האורות, התריסים והמזגנים של חדר, או של כל הבית", { "data-step": "room" }),
    ];
    if (level.can_nest) {
      choices.push(this._choice("add-step", "folder-outline", "תפריט נוסף", "מקש שפותח עוד מקשים", { "data-step": "submenu" }));
    }
    if (flags.assistant) {
      choices.push(this._choice("add-assistant", "account-voice", "עוזר קולי", "המתקשר מבקש בקול מה שהוא רוצה"));
    }
    if (flags.extensions) {
      choices.push(this._choice("add-step", "phone-forward", "מעבר לשלוחה אחרת", "העברת השיחה לשלוחה אחרת בקו", { "data-step": "goto" }));
    }
    if (flags.alerts) {
      choices.push(this._choice("add-alerts", "bell-outline", "התראות אחרונות", "הקראת ההתראות האחרונות שהבית שלח"));
    }
    return view(`מה יקרה כשמקישים ${digit}?`, h("div", { class: "choices" }, choices));
  }

  // בחירת היכולות של מכשיר, בקבוצות לפי סוג.
  _capsView(view, submit) {
    const mode = this._mode;
    const found = mode.found;
    const caps = found.capabilities.filter((c) => c.kind !== "text" || found.streaming);
    // כשחוזרים מהשלב הבא, הסימונים נשארים כפי שהיו.
    const start = mode.idents || caps.filter((c) => c.checked && !c.needs_fixed).map((c) => c.ident);
    const groups = CAP_GROUPS.map((g) => {
      const items = caps.filter((c) => capGroup(c) === g.id);
      if (!items.length) return null;
      if (g.id === "fixed") {
        return this._group(g.title, "", g.icon, null, items.map((c) => btn("fixrow", {
          "data-act": "cap-fixed", "data-action": c.action || "",
        }, h("span", { class: "grow" }, h("span", null, c.name || c.label), h("small", null, this._capNote(c))),
        h("span", { class: "go" }, "קביעת ערך"))));
      }
      return this._group(g.title, items.length > 1 ? `${items.length}` : "", g.icon, this._bulk("cap", items.length, g.id, 2),
        items.map((c) => this._check("cap", c.ident, c.name || c.label, {
          checked: start.includes(c.ident), sub: this._capNote(c), group: g.id,
        })));
    });
    return view(found.name, [
      found.entity_id ? this._entityLine(found.entity_id) : null,
      h("div", { class: "section" }, h("h3", { class: "t-label" }, "מה המתקשר יוכל לעשות"), h("div", { class: "list" }, groups)),
      h("label", { class: "field" }, "שם בטלפון (לא חובה)",
        h("input", { type: "text", name: "name", value: mode.label || "", placeholder: found.name })),
    ], {
      form: "device",
      foot: [
        h("button", { type: "submit", class: "btn primary", "data-caps-btn": true }, this._capsButton(start)),
        found.fixed ? btn("btn", { "data-act": "add-fixed" }, icon("tune-variant"), "מקש עם ערך קבוע, למשל 24 מעלות") : null,
      ],
    });
  }

  // תת-כרטיס של קבוצה: כותרת, סימון הכול / ביטול הכול, ושורות.
  _group(title, meta, iconName, bulk, rows) {
    return h("section", { class: "sub" },
      h("div", { class: "sub-head" },
        iconName ? icon(iconName) : null,
        h("h4", { class: "t-label" }, title),
        meta ? h("span", { class: "t-sub" }, meta) : null,
        h("span", { class: "grow" }),
        bulk),
      h("div", { class: "sub-rows" }, rows));
  }

  _check(name, value, label, { checked = false, sub = null, group = null } = {}) {
    return h("label", { class: "check" },
      h("input", { type: "checkbox", name, value, checked: Boolean(checked), "data-group": group }),
      h("span", { class: "grow" }, h("span", null, label), sub && (!Array.isArray(sub) || sub.length) ? h("small", null, sub) : null));
  }

  // "סימון הכול / ביטול הכול" לקבוצת תיבות סימון אחת.
  _bulk(name, count, group = null, least = 3) {
    if (count < least) return null;
    const attrs = { "data-act": "check-all", "data-name": name, "data-group": group };
    return h("span", { class: "bulk" },
      btn("link", { ...attrs, "data-on": "1" }, "סימון הכול"),
      btn("link", attrs, "ביטול הכול"));
  }

  // היכולות מתוך מה שסומן שיש בהן כמה ערכים לבחור מתוכם.
  _choices(idents) {
    return this._mode.found.capabilities.filter(
      (c) => idents.includes(c.ident) && (c.options || []).length > 1,
    );
  }

  _capsButton(idents) {
    return this._choices(idents).length ? "המשך" : `הוספה למקש ${this._mode.digit}`;
  }

  _checkedCaps() {
    const boxes = [...this.shadowRoot.querySelectorAll('input[name="cap"]')];
    return boxes.length ? boxes.filter((box) => box.checked).map((box) => box.value) : null;
  }

  // הכפתור אומר מה יקרה: עוד שלב של בחירת ערכים, או הוספה.
  _syncCapsButton() {
    const button = this.shadowRoot.querySelector("[data-caps-btn]");
    if (!button) return;
    button.textContent = this._capsButton(this._checkedCaps() || []);
  }

  _field(field, value) {
    // רוב השדות רשות, ולכן מסומן רק מה שחובה.
    const star = field.required ? " (חובה)" : "";
    const given = value === undefined || value === null ? "" : String(value);
    if (field.type === "boolean") {
      return h("label", { class: "check" },
        h("input", { type: "checkbox", name: field.name, checked: Boolean(value) }),
        h("span", { class: "grow" }, field.label));
    }
    if (field.type === "select") {
      return h("label", { class: "field" }, field.label + star,
        h("select", { name: field.name }, h("option", { value: "" }),
          field.options.map((o) => h("option", { value: o.value, selected: o.value === given }, o.label))));
    }
    if (field.type === "number") {
      // כל מספר מבודד בכיוון משלו, כדי שסימן המינוס והסדר לא יתהפכו.
      const unit = UNITS[field.unit] || field.unit || "";
      const bounded = field.min !== null && field.max !== null && field.max < 1e6;
      return h("label", { class: "field" }, field.label,
        bounded ? [" (", ltr(field.min), " עד ", ltr(field.max), unit ? ` ${unit}` : "", ")"] : null,
        star,
        h("input", {
          type: "number", name: field.name, dir: "ltr", value: given,
          min: field.min !== null ? field.min : null,
          max: field.max !== null && field.max < 1e6 ? field.max : null,
          step: field.step || "any",
        }));
    }
    return h("label", { class: "field" }, field.label + star,
      h("input", { type: "text", name: field.name, value: given }));
  }

  // הערכים שמולאו בטופס של פעולה: שדה ריק אינו נשלח.
  _formValues(fields, data) {
    const values = {};
    for (const field of fields) {
      const raw = data.get(field.name);
      if (field.type === "boolean") {
        if (raw) values[field.name] = true;
      } else if (String(raw || "").trim() !== "") {
        values[field.name] = String(raw).trim();
      }
    }
    return values;
  }

  // עריכה של מקש קיים: המקום והמכשירים של קבוצה, או ערך קבוע.
  _editView() {
    const mode = this._mode;
    const submit = (label) => h("button", { type: "submit", class: "btn primary" }, label);
    const digit = mode.path ? mode.path.split("/").pop() : null;
    if (mode.step === "values") {
      const found = mode.fixed;
      return {
        title: found.action.label, digit, back: "close", form: "edit-values",
        body: [
          h("p", { class: "muted" }, `${found.name}. שדה ריק נשאר כמו שהוא במכשיר.`),
          found.action.fields.map((f) => this._field(f, found.values[f.name])),
        ],
        foot: [submit("שמירה")],
      };
    }
    const group = mode.group;
    if (mode.step === "members") {
      const out = mode.exclude;
      return {
        title: `אילו ${group.name}?`, digit, back: "edit-back", form: "edit-members",
        body: [
          h("p", { class: "muted" }, "מסירים סימון ממכשיר שלא רוצים לכלול. מכשיר חדש שיתווסף למקום הזה יצטרף מעצמו."),
          this._group(group.name, "", DOMAIN_ICONS[group.domain] || "devices", this._bulk("member", mode.members.length),
            mode.members.map((m) => this._check("member", m.entity_id, m.name, {
              checked: !out.includes(m.entity_id), sub: ltr(m.entity_id),
            }))),
        ],
        foot: [submit("שמירה")],
      };
    }
    const chosen = mode.target || group.target;
    const part = (title, name, items) => (items.length
      ? this._group(title, "", null, this._bulk(name, items.length),
        items.map((i) => this._check(name, i.id, i.name, { checked: (chosen[name] || []).includes(i.id) })))
      : null);
    const direct = (group.target.device_id || []).length + (group.target.entity_id || []).length;
    return {
      title: `איפה ה${group.name}?`, digit, back: "close", form: "edit-places",
      body: [
        h("p", { class: "muted" }, `בלי סימון: כל הבית.${direct ? ` ${direct} מכשירים שנבחרו ישירות נשארים בקבוצה.` : ""}`),
        h("div", { class: "list" },
          part("קומות", "floor_id", group.places.floors),
          part("חדרים", "area_id", group.places.areas),
          part("תוויות", "label_id", group.places.labels)),
      ],
      foot: [submit("המשך")],
    };
  }

  _buildView() {
    const free = Object.values(this._level.keys).filter((k) => !k).length;
    const rooms = this._mode.rooms || [];
    return {
      title: "תפריט מהחדרים בבית", lead: "home-group", back: "close", form: "build",
      body: [
        h("p", { class: "muted" }, `כל חדר שתסמנו יקבל מקש, ובתוכו מה שאפשר להפעיל בו. יש ${free} מקשים פנויים.`),
        rooms.length
          ? this._group("חדרים", "", "door-open", this._bulk("room", rooms.length), rooms.map((room, index) => this._check(
            "room", index, room.name, { checked: Boolean(room.area_id) && index < free, sub: room.kinds.map((k) => k.name).join(" · ") },
          )))
          : h("p", { class: "muted" }, "לא נמצאו חדרים עם מכשירים שאפשר להפעיל."),
      ],
      foot: [h("button", { type: "submit", class: "btn primary" }, "בנייה")],
    };
  }

  _devices(query) {
    const hass = this._hass;
    const text = query.trim().toLowerCase();
    const rows = [];
    for (const [id, state] of Object.entries(hass.states || {})) {
      if (!state) continue;
      const domain = id.split(".", 1)[0];
      if (this._blocked.has(domain) || PICKER_SKIP.has(domain)) continue;
      const known = hass.entities ? hass.entities[id] : null;
      if (known && (known.hidden || known.entity_category || known.platform === "ha_ivr")) continue;
      const rank = DOMAIN_ORDER.indexOf(domain);
      // בלי חיפוש מוצג רק מה שמפעילים. חיישנים ושאר הדברים — בחיפוש.
      if (!text && rank < 0) continue;
      const device = known && known.device_id && hass.devices ? hass.devices[known.device_id] : null;
      const areaId = (known && known.area_id) || (device && device.area_id) || "";
      const area = (areaId && hass.areas && hass.areas[areaId] && hass.areas[areaId].name) || "";
      const name = this._entityName(id);
      if (text && !`${name} ${id} ${area}`.toLowerCase().includes(text)) continue;
      const lower = name.toLowerCase();
      const near = !text ? 0 : lower === text ? 0 : lower.startsWith(text) ? 1 : 2;
      rows.push({ id, name, domain, area, near, rank: rank < 0 ? 99 : rank });
    }
    rows.sort((a, b) =>
      (a.area ? 0 : 1) - (b.area ? 0 : 1)
      || a.area.localeCompare(b.area, "he")
      || a.near - b.near
      || a.rank - b.rank
      || a.name.localeCompare(b.name, "he"));
    return rows;
  }

  _deviceList(query) {
    const rows = this._devices(query);
    if (!rows.length) {
      return [h("p", { class: "muted" }, query.trim() ? "לא נמצא מכשיר בשם הזה." : "לא נמצאו מכשירים.")];
    }
    let area = null;
    const out = [];
    for (const row of rows.slice(0, PICKER_LIMIT)) {
      if (row.area !== area) {
        area = row.area;
        out.push(h("h4", null, area || "בלי חדר"));
      }
      out.push(btn("pick", { "data-act": "add-device", "data-id": row.id },
        icon(DOMAIN_ICONS[row.domain] || "devices"),
        h("span", { class: "grow" }, h("span", null, row.name), h("small", null, ltr(row.id)))));
    }
    if (rows.length > PICKER_LIMIT) {
      out.push(h("p", { class: "t-sub" }, `ועוד ${rows.length - PICKER_LIMIT}. הקלידו שם כדי לצמצם.`));
    } else if (!query.trim()) {
      out.push(h("p", { class: "t-sub" }, "מחפשים חיישן או משהו אחר? הקלידו את שמו."));
    }
    return out;
  }

  // ------------------------------------------------------------------
  // מה שהמשתמש עושה
  // ------------------------------------------------------------------

  _setMode(mode) {
    this._mode = mode;
    this._sure = "";
    this._render();
  }

  _parent(path) {
    return path.split("/").slice(0, -1).join("/");
  }

  async _add(what, args = {}, { enter = false } = {}) {
    const digit = this._mode.digit;
    const path = this._path(digit);
    // החלפה של מכשיר שהוסר: קודם מוציאים את הישן מהמקש.
    if (this._mode.replace) {
      const level = await this._call("remove", { path: this._mode.replace, view: this._level.path });
      if (!level) return;
      this._level = level;
    }
    await this._change(
      "add", { path, args: { what, ...args } },
      { flash: digit, view: enter ? path : undefined },
    );
  }

  async _onClick(ev) {
    const el = ev.target.closest("[data-act]");
    if (!el || el.disabled || this._busy > 0) return;
    const data = el.dataset;
    const level = this._level;
    const mode = this._mode;
    if (data.digit && PAD.includes(data.digit)) this._cursor = data.digit;

    // מחיקה בשתי לחיצות: הראשונה שואלת, השנייה מוחקת.
    if (data.sure && this._sure !== data.sure) {
      this._sure = data.sure;
      this._render();
      return;
    }

    switch (data.act) {
      case "menu":
        this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
        return;
      case "settings":
        this._go("/config/integrations/integration/ha_ivr");
        return;
      case "entry":
        if (data.id !== this._entryId) await this._pickEntry(data.id);
        return;
      case "open":
        if (data.path !== level.path || mode.name !== "heard") await this._open(data.path);
        return;
      case "up":
        await this._open(this._parent(level.path));
        return;
      case "key":
        await this._onKey(data.digit);
        return;
      case "empty":
        await this._onEmpty(data.digit);
        return;
      case "close":
        this._setMode({ name: "heard" });
        return;
      case "replace":
        this._setMode({ name: "add", digit: data.digit, step: "device", replace: data.path });
        return;
      case "edit-place": {
        const group = await this._call("group", { path: data.path });
        if (group) this._setMode({ name: "edit", step: "places", path: data.path, group });
        return;
      }
      case "edit-value": {
        const fixed = await this._call("fixed", { path: data.path });
        if (fixed) this._setMode({ name: "edit", step: "values", path: data.path, fixed });
        return;
      }
      case "edit-back":
        this._setMode({ ...mode, step: "places" });
        return;
      case "carry-cancel":
        this._carry = null;
        this._render();
        return;
      case "carry": {
        const key = data.up ? level.self : level.keys[mode.digit];
        const home = this._parent(data.path);
        this._carry = { path: data.path, name: data.name };
        // פעולה של מכשיר ואפשרות של בחירה זזות רק בתוך הרמה שלהן.
        if (key && (key.kind === "cap" || key.kind === "option")) this._carry.only = home;
        if (data.up) await this._open(home);
        else this._setMode({ name: "heard" });
        return;
      }
      case "remove":
        await this._change("remove", { path: data.path }, {
          view: data.path === level.path ? this._parent(level.path) : level.path,
        });
        return;
      case "loose-place":
        this._carry = { id: data.id, name: data.name };
        this._setMode({ name: "heard" });
        return;
      case "loose-remove":
        await this._change("remove", { args: { id: data.id } });
        return;
      case "build": {
        const found = await this._call("rooms");
        if (found) this._setMode({ name: "build", rooms: found.rooms });
        return;
      }
      case "add-back": {
        const before = {
          caps: "device", options: "caps", fixed: "caps", values: "fixed",
          places: "room", kinds: mode.places ? "places" : "room",
          members: "kinds", functions: "members",
        }[mode.step] || "what";
        this._setMode({ ...mode, step: before, places: before === "room" ? null : mode.places });
        return;
      }
      case "add-step": {
        if (data.step === "room") {
          const found = await this._call("rooms");
          if (found) this._setMode({ ...mode, step: "room", rooms: found.rooms });
          return;
        }
        this._setMode({ ...mode, step: data.step });
        return;
      }
      case "add-assistant":
        if (this._flags.assistant_target) await this._add("assistant");
        else this._setMode({ ...mode, step: "assistant" });
        return;
      case "add-alerts":
        await this._add("alerts");
        return;
      case "add-device": {
        const found = await this._call("capabilities", { args: { entity_id: data.id } });
        if (found) this._setMode({ ...mode, step: "caps", found, idents: null, label: "" });
        return;
      }
      case "add-room": {
        const picked = mode.rooms[Number(data.index)];
        const room = await this._call("place", {
          args: { target: picked.area_id ? { area_id: [picked.area_id] } : {} },
        });
        if (room) this._setMode({ ...mode, step: "kinds", room, places: null, domains: null, exclude: null });
        return;
      }
      case "check-all": {
        const scope = data.group ? `[data-group="${quoted(data.group)}"]` : "";
        const boxes = this.shadowRoot.querySelectorAll(`input[type="checkbox"][name="${quoted(data.name)}"]${scope}`);
        for (const box of boxes) box.checked = Boolean(data.on);
        this._syncCapsButton();
        return;
      }
      case "add-places": {
        const places = await this._call("places");
        if (places) this._setMode({ ...mode, step: "places", places });
        return;
      }
      case "add-fixed":
      case "cap-fixed": {
        // יכולת שאי אפשר להקיש פותחת ישר את הטופס של הערך הקבוע שלה.
        const idents = this._checkedCaps() || mode.idents;
        const fixed = await this._call("actions", { args: { entity_id: mode.found.entity_id } });
        if (!fixed) return;
        const action = data.act === "cap-fixed" ? fixed.actions.find((a) => a.action === data.action) : null;
        this._setMode({ ...mode, idents, step: action ? "values" : "fixed", fixed, action: action || null });
        return;
      }
      case "add-values":
        this._setMode({ ...mode, step: "values", action: mode.fixed.actions[Number(data.index)] });
        return;
      case "add-part":
        if (level.kind === "plan") await this._add("capability", { ident: data.ident });
        else await this._add("option", { value: data.value });
        return;
      default:
    }
  }

  async _onKey(digit) {
    const key = this._level.keys[digit];
    const carry = this._carry;
    if (!carry) {
      if (key.enter) await this._open(key.path);
      else this._setMode({ name: "info", digit });
      return;
    }
    if (carry.path === key.path) {
      this._carry = null;
      this._render();
      return;
    }
    // תפריט פותחים, כדי שאפשר יהיה להניח בתוכו.
    if (key.kind === "submenu" && carry.only === undefined) {
      await this._open(key.path);
      return;
    }
    if (carry.path && this._parent(carry.path) === this._level.path) {
      await this._change("move", { path: carry.path, args: { to: key.path } }, { flash: digit });
      return;
    }
    this._say("המקש הזה תפוס. בחרו מקש ריק.");
  }

  async _onEmpty(digit) {
    const carry = this._carry;
    const to = this._path(digit);
    if (carry) {
      const message = carry.id
        ? { args: { to, id: carry.id } }
        : { path: carry.path, args: { to } };
      await this._change("move", message, { flash: digit });
      return;
    }
    if (!this._canAdd()) {
      this._say("אין עוד מה להוסיף כאן.");
      return;
    }
    this._setMode({ name: "add", digit, step: "what" });
  }

  async _onSubmit(ev) {
    ev.preventDefault();
    if (this._busy > 0) return;
    const form = ev.target;
    const data = new FormData(form);
    const text = (name) => String(data.get(name) || "").trim();
    const level = this._level;
    const mode = this._mode;

    switch (form.dataset.form) {
      case "intro":
        await this._change("update", { path: level.path, args: { intro: text("intro") } });
        return;
      case "rename":
        await this._change("rename", { path: form.dataset.path, args: { name: text("name") } });
        return;
      case "target":
        await this._change("update", { path: form.dataset.path, args: { target: text("target") } });
        return;
      case "device": {
        const idents = data.getAll("cap");
        if (!idents.length) {
          this._say("סמנו לפחות פעולה אחת.");
          return;
        }
        if (idents.length > 9) {
          this._say(`יש תשעה מקשים, וסומנו ${idents.length} פעולות. הסירו ${idents.length - 9}.`);
          return;
        }
        if (this._choices(idents).length) {
          this._setMode({ ...mode, step: "options", idents, label: text("name") });
          return;
        }
        await this._add("device", { entity_id: mode.found.entity_id, idents, name: text("name") });
        return;
      }
      case "options": {
        const options = {};
        for (const c of this._choices(mode.idents)) {
          const values = data.getAll(`opt:${c.ident}`);
          if (!values.length) {
            this._say(`סמנו לפחות ערך אחד ב«${c.name}».`);
            return;
          }
          if (values.length > 9) {
            this._say(`ב«${c.name}» אפשר עד 9 ערכים, וסומנו ${values.length}.`);
            return;
          }
          options[c.ident] = values;
        }
        await this._add("device", {
          entity_id: mode.found.entity_id, idents: mode.idents, options, name: mode.label,
        });
        return;
      }
      case "room": {
        const domains = data.getAll("kind");
        if (!domains.length) {
          this._say("סמנו לפחות סוג אחד.");
          return;
        }
        if (domains.length > 1 && !level.can_nest) {
          this._say("בעומק הזה אפשר לבחור סוג אחד בלבד.");
          return;
        }
        if (ev.submitter && ev.submitter.dataset.go === "add") {
          await this._add("room", { target: mode.room.target, domains, name: "" });
          return;
        }
        this._setMode({ ...mode, step: "members", domains });
        return;
      }
      case "members": {
        const exclude = [];
        const kept = [];
        for (const domain of mode.domains) {
          const all = mode.room.members.filter((m) => m.domain === domain);
          const checked = new Set(data.getAll(`member:${domain}`));
          // סוג שלא נשאר בו אף מכשיר פשוט אינו נכנס.
          if (!all.some((m) => checked.has(m.entity_id))) continue;
          kept.push(domain);
          for (const m of all) if (!checked.has(m.entity_id)) exclude.push(m.entity_id);
        }
        if (!kept.length) {
          this._say("סמנו לפחות מכשיר אחד.");
          return;
        }
        const found = await this._call("place_functions", {
          args: { target: mode.room.target, exclude, domains: kept },
        });
        if (found) this._setMode({ ...mode, step: "functions", exclude, functions: found.kinds });
        return;
      }
      case "functions": {
        const idents = {};
        for (const kind of mode.functions) {
          const picked = data.getAll(`cap:${kind.domain}`);
          if (picked.length) idents[kind.domain] = picked;
        }
        const domains = Object.keys(idents);
        if (!domains.length) {
          this._say("סמנו לפחות פעולה אחת.");
          return;
        }
        if (domains.length > 1 && !level.can_nest) {
          this._say("בעומק הזה אפשר לבחור סוג אחד בלבד.");
          return;
        }
        await this._add("room", {
          target: mode.room.target, exclude: mode.exclude, domains, idents, name: text("name"),
        });
        return;
      }
      case "places": {
        const target = {};
        for (const key of ["floor_id", "area_id", "label_id"]) {
          const ids = data.getAll(key);
          if (ids.length) target[key] = ids;
        }
        if (!Object.keys(target).length) {
          this._say("סמנו לפחות מקום אחד.");
          return;
        }
        const room = await this._call("place", { args: { target } });
        if (room) this._setMode({ ...mode, step: "kinds", room, domains: null, exclude: null });
        return;
      }
      case "fixed":
        await this._add("action", {
          entity_id: mode.fixed.entity_id, action: mode.action.action,
          data: this._formValues(mode.action.fields, data), name: text("_name"),
        });
        return;
      case "edit-values":
        await this._change("update", {
          path: mode.path,
          args: { values: this._formValues(mode.fixed.action.fields, data) },
        });
        return;
      case "edit-places": {
        // מכשירים שנבחרו ישירות אינם בטופס, ולכן נשארים כמות שהם.
        const target = {};
        for (const key of ["device_id", "entity_id"]) {
          if ((mode.group.target[key] || []).length) target[key] = mode.group.target[key];
        }
        for (const key of ["floor_id", "area_id", "label_id"]) {
          const ids = data.getAll(key);
          if (ids.length) target[key] = ids;
        }
        const room = await this._call("place", { args: { target } });
        if (!room) return;
        const members = room.members.filter((m) => m.domain === mode.group.domain);
        if (!members.length) {
          this._say(`אין שם ${mode.group.name}.`);
          return;
        }
        // בפעם הראשונה — מי שכבר בחוץ. אחרי שינוי המקום הבחירה נשמרת.
        this._setMode({
          ...mode, step: "members", target, members,
          exclude: mode.exclude || mode.group.exclude,
        });
        return;
      }
      case "edit-members": {
        const kept = new Set(data.getAll("member"));
        if (!kept.size) {
          this._say("סמנו לפחות מכשיר אחד.");
          return;
        }
        const exclude = mode.members.map((m) => m.entity_id).filter((id) => !kept.has(id));
        await this._change("update", {
          path: mode.path, args: { place: { target: mode.target, exclude } },
        });
        return;
      }
      case "submenu":
        await this._add("submenu", { name: text("name") }, { enter: true });
        return;
      case "goto":
      case "assistant":
        await this._add(form.dataset.form, { target: text("target"), name: text("name") });
        return;
      case "build": {
        const areaIds = data.getAll("room").map((i) => mode.rooms[Number(i)].area_id);
        if (!areaIds.length) {
          this._say("סמנו לפחות חדר אחד.");
          return;
        }
        await this._change("build", { path: level.path, args: { area_ids: areaIds } });
        return;
      }
      default:
    }
  }

  _onInput(ev) {
    const target = ev.target;
    if (target.name === "cap") {
      this._syncCapsButton();
      return;
    }
    // תצוגה חיה של מה שהמתקשר ישמע, בזמן ההקלדה.
    if (target.name === "intro") {
      for (const li of this.shadowRoot.querySelectorAll('[data-live="intro"]')) {
        li.textContent = target.value;
        li.hidden = !target.value;
      }
      return;
    }
    if (target.name === "name") {
      for (const li of this.shadowRoot.querySelectorAll('[data-live="name"]')) {
        if (li._line) li.textContent = li._line.split(li._name).join(target.value.trim() || li._name);
      }
      return;
    }
    if (!target.matches || !target.matches("[data-search]")) return;
    this._mode.query = target.value;
    clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      const list = this.shadowRoot.getElementById("devices");
      if (list) list.replaceChildren(...this._deviceList(this._mode.query || ""));
    }, SEARCH_DELAY);
  }

  // חצים בתוך הלוח, ו-Escape שסוגר את העורך.
  _onKeyDown(ev) {
    if (ev.key === "Escape") {
      if (this._mode.name !== "heard") {
        ev.preventDefault();
        this._setMode({ name: "heard" });
      } else if (this._carry) {
        this._carry = null;
        this._render();
      }
      return;
    }
    const el = ev.target && ev.target.closest ? ev.target.closest(".key") : null;
    if (!el) return;
    const at = PAD.indexOf(el.dataset.digit);
    if (at < 0) return;
    const col = at % 3;
    let next = -1;
    if (ev.key === "ArrowRight" && col < 2) next = at + 1;
    else if (ev.key === "ArrowLeft" && col > 0) next = at - 1;
    else if (ev.key === "ArrowDown" && at + 3 < PAD.length) next = at + 3;
    else if (ev.key === "ArrowUp" && at - 3 >= 0) next = at - 3;
    else if (ev.key === "Home") next = 0;
    else if (ev.key === "End") next = PAD.length - 1;
    if (next < 0) return;
    ev.preventDefault();
    this._cursor = PAD[next];
    for (const key of this.shadowRoot.querySelectorAll(".pad .key")) {
      key.setAttribute("tabindex", key.dataset.digit === this._cursor ? "0" : "-1");
    }
    this.shadowRoot.querySelector(`.pad .key[data-digit="${quoted(this._cursor)}"]`)?.focus();
  }

  // ------------------------------------------------------------------
  // גרירה
  // ------------------------------------------------------------------

  _dropTarget(ev) {
    return ev.target.closest ? ev.target.closest("[data-drop]") : null;
  }

  _onDragStart(ev) {
    const el = ev.target.closest ? ev.target.closest(".key[draggable]") : null;
    const key = el ? this._level.keys[el.dataset.digit] : null;
    if (!key) return;
    this._drag = key.path;
    ev.dataTransfer.effectAllowed = "move";
    ev.dataTransfer.setData("text/plain", key.path);
  }

  _onDragOver(ev) {
    const el = this._dropTarget(ev);
    if (!this._drag || !el || this._path(el.dataset.drop) === this._drag) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = "move";
    el.classList.add("over");
  }

  async _onDrop(ev) {
    const el = this._dropTarget(ev);
    const from = this._drag;
    this._drag = "";
    if (!from || !el) return;
    ev.preventDefault();
    el.classList.remove("over");
    const to = this._path(el.dataset.drop);
    if (to !== from && this._busy === 0) {
      await this._change("move", { path: from, args: { to } }, { flash: el.dataset.drop });
    }
  }
}

HaIvrPanel.esc = esc;

if (!customElements.get("ha-ivr-panel")) {
  customElements.define("ha-ivr-panel", HaIvrPanel);
}
