#!/usr/bin/env bash
# פריסה לקונטיינר, עם כל האימותים שהיו פעם כללים במסמך.
#
# מה שהסקריפט הזה אוכף במקום שמישהו יזכור:
#   * השער עובר לפני שמעתיקים
#   * העותק הפרוס זהה לפיתוח, בלי שאריות מגרסה קודמת
#   * החתימה שרצה בקונטיינר היא החתימה שיצאה מהפיתוח
#
# החתימה נגזרת מתוכן הקבצים, ולכן היא נבדקת פעמיים: על העץ הפרוס
# לפני ההפעלה מחדש, ומול היומן אחריה. הראשונה תופסת שאריות, השנייה
# תופסת קונטיינר שטען קוד אחר.
#
#   ./deploy.sh          פריסה מלאה
#   ./deploy.sh --check  שער בלבד, בלי לגעת בקונטיינר

set -euo pipefail
cd "$(dirname "$0")"

# הסביבה, עם ברירות מחדל של התקנת Home Assistant בקונטיינר.
# מי שהתקנה שלו אחרת מגדיר אותן לפני ההרצה:
#
#   HA_CONFIG=/srv/hass ./deploy.sh
#
# הגדרות מקומיות, אם יש. הקובץ אינו בגיט — כך הריפו נשאר גנרי
# ומי שההתקנה שלו אינה סטנדרטית אינו מקליד נתיב בכל הרצה.
[ -f .deploy.local ] && . ./.deploy.local

HA_CONFIG="${HA_CONFIG:-/config}"
CC="${HA_CUSTOM_COMPONENTS:-$HA_CONFIG/custom_components}"
LOG="${HA_LOG:-$HA_CONFIG/home-assistant.log}"
CONTAINER="${HA_CONTAINER:-homeassistant}"
PACKAGES=(ha_ivr)
WAIT=90

die() { printf '\n✗ %s\n' "$*" >&2; exit 1; }
step() { printf '\n▸ %s\n' "$*"; }

stamp_of() {  # חתימת עץ, מחושבת מהקבצים עצמם — אותו קוד שרץ בטעינה
  python3 -c "
import sys; sys.path.insert(0, '$1')
import ha_ivr; print(ha_ivr.build_stamp())"
}

# ---------------------------------------------------------------- שער
step "שער"
for gate in run_live check_names check_flow check_gate; do
  python3 "tests/$gate.py" | tail -1 || die "tests/$gate.py נכשל. לא נפרס דבר"
done

DEV=$(stamp_of custom_components)
printf '\n  חתימת הפיתוח: %s\n' "$DEV"

if ! git diff --quiet HEAD 2>/dev/null || [ -n "$(git status --porcelain)" ]; then
  printf '  ⚠ העץ אינו נקי. החתימה שתופיע ביומן לא תצביע על שום קומיט\n'
else
  printf '  קומיט: %s\n' "$(git rev-parse --short HEAD)"
fi

[ "${1:-}" = "--check" ] && { printf '\n✓ השער עבר. לא נפרס דבר\n'; exit 0; }

# -------------------------------------------------------------- העתקה
step "העתקה"
# rm לפני cp: cp אינו מוחק, וקובץ שהוסר מהפיתוח ממשיך לחיות בפרוס
# ומשנה את החתימה. זה בדיוק מה שהחתימה נועדה לתפוס.
for pkg in "${PACKAGES[@]}"; do
  rm -rf "${CC:?}/$pkg"
  cp -r "custom_components/$pkg" "$CC/$pkg"
done
find "$CC" -path "*ha_ivr*" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

for pkg in "${PACKAGES[@]}"; do
  diff -rq "custom_components/$pkg" "$CC/$pkg" --exclude=__pycache__ \
    || die "$pkg אינו זהה אחרי ההעתקה"
done
printf '  העותק זהה\n'

OUT=$(stamp_of "$CC")
[ "$OUT" = "$DEV" ] || die "חתימת העץ הפרוס $OUT ≠ פיתוח $DEV"
printf '  חתימת העץ הפרוס תואמת\n'

# ------------------------------------------------------------- הפעלה
step "הפעלה מחדש"
LINES=$(wc -l < "$LOG")
docker restart "$CONTAINER" >/dev/null

printf '  ממתין לחתימה ביומן'
for _ in $(seq "$WAIT"); do
  # **היומן מתקצר בעלייה.** Home Assistant פותחת אותו מחדש, ולכן
  # ספירת השורות שנלקחה לפני ההפעלה גדולה מהקובץ כולו — ו-tail
  # מאותה שורה מדלג על כל היומן החדש. הפריסה הצליחה, החתימה ישבה
  # בשורה 28, והסקריפט חיפש משורה 3000 והלאה והכריז על כישלון.
  NOW=$(wc -l < "$LOG" 2>/dev/null || echo 0)
  FROM=$(( NOW < LINES ? 1 : LINES + 1 ))
  if LINE=$(tail -n "+$FROM" "$LOG" 2>/dev/null | grep -m1 "ha_ivr .* is running"); then
    printf '\n'
    case "$LINE" in
      *"$DEV"*) printf '\n✓ %s רץ בקונטיינר\n' "$DEV"; exit 0 ;;
      *) die "היומן מצהיר על חתימה אחרת:
  $LINE" ;;
    esac
  fi
  printf '.'
  sleep 1
done
# **החתימה מופיעה רק כשיש רשומה.** `async_setup` נקראת בידי HA
# כשנטענת רשומה ראשונה, ולכן התקנה טרייה בלי הגדרה לא תכתוב אותה
# לעולם. זה מצב תקין, ולא כשל שיש לעצור עליו.
if ! grep -q '"domain": "ha_ivr"' "$HA_CONFIG/.storage/core.config_entries" 2>/dev/null; then
  printf '\n\n⚠ הקוד נפרס, אך אין עדיין רשומת ha_ivr\n'
  printf '  החתימה תופיע ביומן אחרי הוספת האינטגרציה בממשק.\n'
  exit 0
fi
die "החתימה לא הופיעה ביומן תוך $WAIT שניות. יש לבדוק את $LOG"
