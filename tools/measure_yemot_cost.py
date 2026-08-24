#!/usr/bin/env python3
"""מדידת עלות: הקראת TTS מול השמעת קובץ, במסלול היוצא של ימות.

השאלה: האם השמעת קובץ שה-Home Assistant מייצר זולה מהקראת טקסט
במנוע ה-TTS של ימות. הסקריפט אינו מנחש — הוא שולח בפועל ומדפיס
את המחיר שימות מחזירה.

**זו שיחה יוצאת אמיתית. היא עולה יחידות ותצלצל אצל הנמען.**
לכן הוא אינו רץ מעצמו: יש להריץ ידנית, עם מספר משלך.

    python3 tools/measure_yemot_cost.py 0501234567
    python3 tools/measure_yemot_cost.py 0501234567 --tts-only
    python3 tools/measure_yemot_cost.py 0501234567 --file-only

הטוקן נקרא מרשומת ההגדרה של ימות ב-Home Assistant, ואינו מודפס.
"""
from __future__ import annotations

import argparse
import json
import os
import math
import pathlib
import struct
import sys
import urllib.parse
import urllib.request

API = "https://www.call2all.co.il/ym/api"
MESSAGE = "זוהי בדיקת עלות של מערכת הבית החכם. אין צורך לעשות דבר."
# הודעה ארוכה, כדי לבדוק אם התוספת של ה-TTS תלויה באורך. קובץ
# מחויב לפי משך/שיחה ולא לפי תווים, ולכן A אמור לזנק ו-B להישאר.
MESSAGE_LONG = (
    "זוהי בדיקת עלות מפורטת של מערכת הבית החכם. "
    "ההודעה הזו ארוכה בכוונה, כדי לבדוק האם מנוע ההקראה גובה "
    "תוספת לפי מספר התווים בטקסט. אם התוספת אכן תלויה באורך, "
    "אזי הקראת טקסט ארוך תעלה יותר מהשמעת קובץ מוקלט באותו אורך, "
    "משום שקובץ מחויב לפי משך השיחה בלבד ולא לפי כמות התווים. "
    "אין צורך לעשות דבר, זו בדיקה בלבד, תודה רבה ולהתראות."
)


# ---------------------------------------------------------------------------
# טוקן — מרשומת ההגדרה, בלי להדפיס אותו

def read_token(config_dir: str) -> str:
    p = pathlib.Path(config_dir) / ".storage" / "core.config_entries"
    data = json.loads(p.read_text())["data"]["entries"]
    for e in data:
        if e.get("domain") == "ha_ivr" and e["data"].get("provider") == "yemot":
            tok = (e.get("options", {}).get("yemot_token")
                   or e["data"].get("yemot_token"))
            if tok:
                return str(tok)
    sys.exit("לא נמצאה רשומת ימות עם טוקן ב-" + str(p))


# ---------------------------------------------------------------------------
# WAV קצר לבדיקה — צליל דיבור מדומה, באורך שמדמה הודעה אמיתית

def make_wav(seconds: float = 4.0, rate: int = 8000) -> bytes:
    n = int(seconds * rate)
    samples = bytearray()
    for i in range(n):
        # שני טונים מתחלפים, כדי שהאורך יהיה מציאותי ולא שקט דחוס
        f = 320 if (i // (rate // 3)) % 2 else 440
        v = int(9000 * math.sin(2 * math.pi * f * i / rate))
        samples += struct.pack("<h", v)
    body = bytes(samples)
    hdr = b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", len(body))
    return hdr + body


# ---------------------------------------------------------------------------
# קריאות API

def call(cmd: str, params: dict, files: dict | None = None) -> dict:
    url = f"{API}/{cmd}"
    if files:
        boundary = "----ymBound12345"
        body = bytearray()
        for k, v in params.items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                     f'name="{k}"\r\n\r\n{v}\r\n').encode()
        for k, (fname, content) in files.items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; "
                     f'name="{k}"; filename="{fname}"\r\n'
                     "Content-Type: audio/wav\r\n\r\n").encode()
            body += content + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            url, data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except ValueError:
        return {"_raw": raw}


def price_of(resp: dict) -> str:
    keys = ("estimatedPrice", "customerUnits", "price", "units", "cost")
    got = {k: resp[k] for k in keys if k in resp}
    return ", ".join(f"{k}={v}" for k, v in got.items()) or "(אין שדה מחיר בתשובה)"


# ---------------------------------------------------------------------------

def run_tts(token: str, phone: str, long: bool = False) -> None:
    print("\n▸ מסלול A — SendTTS (הקראת טקסט, מה שנעשה היום)")
    msg = MESSAGE_LONG if long else MESSAGE
    print(f"   אורך הטקסט: {len(msg)} תווים")
    resp = call("SendTTS", {"token": token, "phones": phone, "ttsMessage": msg})
    print("   תשובה:", json.dumps(resp, ensure_ascii=False)[:300])
    # **`billing` הוא העלות בפועל של SendTTS**, מתוך התשובה עצמה.
    print("   חיוב:  billing =", resp.get("billing", "?"))


def run_file(token: str, phone: str, long: bool = False) -> None:
    print("\n▸ מסלול B — UploadFile + RunCampaign (השמעת קובץ מ-HA)")

    seconds = 38.0 if long else 4.0
    print(f"   אורך הקובץ: {seconds:.0f} שניות")
    tmpl = call("CreateTemplate", {"token": token,
                                   "description": "HA cost test"})
    tid = str(tmpl.get("templateId") or "")
    print("   CreateTemplate:", json.dumps(tmpl, ensure_ascii=False)[:200])
    if not tid:
        print("   ✗ לא התקבל templateId — עוצר את מסלול B")
        return

    wav = make_wav(seconds)
    up = call("UploadFile",
              {"token": token, "path": f"ivr2:{tid}.wav", "convertAudio": "1"},
              files={"file": (f"{tid}.wav", wav)})
    print("   UploadFile:   ", json.dumps(up, ensure_ascii=False)[:200])

    resp = call("RunCampaign", {"token": token, "templateId": tid, "phones": phone})
    print("   RunCampaign:  ", json.dumps(resp, ensure_ascii=False)[:300])
    print("   מחיר: ", price_of(resp))
    if cid := resp.get("campaignId"):
        print(f"   campaignId={cid}  — דוח: GetCampaignStatus")


def run_sms(token: str, phone: str) -> None:
    """אימות ערוץ SMS — 0.1 יחידה. הפרמטרים לא מתועדים, מגלים כאן.

    מנסה את שם הפרמטר הסביר (`message`). התשובה מודפסת במלואה כדי
    שנלמד את השם הנכון אם נדחה.
    """
    print("\n▸ ערוץ SMS — SendSms (0.1 יחידה)")
    resp = call("SendSms", {"token": token, "phones": phone,
                            "message": "בדיקת התראה מהבית החכם."})
    print("   תשובה:", json.dumps(resp, ensure_ascii=False)[:400])


def run_tzintuk(token: str, phone: str) -> None:
    """אימות צינתוק — 0.1 יחידה. צלצול-ניתוק, בלי תוכן.

    ביומן ימות מוזכר `runRingHangup`/`rhAdd`; מנסים כאן את הצורה
    הישירה, ומדפיסים הכל כדי ללמוד את הפורמט הנכון.
    """
    print("\n▸ ערוץ צינתוק — RunTzintuk (0.1 יחידה)")
    resp = call("RunTzintuk", {"token": token, "phones": phone})
    print("   תשובה:", json.dumps(resp, ensure_ascii=False)[:400])


def report(token: str, campaign_id: str) -> None:
    """החיוב הסופי של קמפיין, אחרי שהשיחה הסתיימה — לא ההערכה.

    הדוח הוא הסמכות: הערכת ההגשה אינה כוללת בהכרח את תוספת ה-TTS,
    שנגבית לפי אורך הטקסט ולעיתים רק בסיום.
    """
    print(f"\n▸ דוח קמפיין {campaign_id}")
    resp = call("GetCampaignStatus", {"token": token, "campaignId": campaign_id})
    print("   ", json.dumps(resp, ensure_ascii=False)[:600])
    # השדות שמעניינים: היחידות שנגבו בפועל, ומצב השיחה.
    hot = ("price", "units", "customerUnits", "billing", "estimatedPrice",
           "actualPrice", "totalPrice", "duration", "status", "entries")
    got = {k: resp[k] for k in hot if k in resp}
    if got:
        print("   שדות מחיר/מצב:", ", ".join(f"{k}={v}" for k, v in got.items()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("phone", nargs="?", help="מספר לבדיקה, שלך")
    ap.add_argument("--config", default=os.environ.get("HA_CONFIG", "/config"),
                    help="תיקיית ההגדרות של HA (או משתנה הסביבה HA_CONFIG)")
    ap.add_argument("--tts-only", action="store_true")
    ap.add_argument("--file-only", action="store_true")
    ap.add_argument("--report", metavar="CAMPAIGN_ID", action="append",
                    help="לקרוא את החיוב הסופי של קמפיין (אפשר לחזור עליו)")
    ap.add_argument("--long", action="store_true",
                    help="הודעה ארוכה, לבדיקת תוספת TTS תלוית-אורך")
    ap.add_argument("--sms", action="store_true", help="אימות ערוץ SMS (0.1)")
    ap.add_argument("--tzintuk", action="store_true", help="אימות צינתוק (0.1)")
    a = ap.parse_args()

    token = read_token(a.config)
    print(f"טוקן: ***{token[-4:]}")

    if a.report:
        # קריאה בלבד — אינה מחייגת ואינה עולה.
        for cid in a.report:
            report(token, cid)
        return

    if not a.phone:
        sys.exit("חסר מספר. או --report CAMPAIGN_ID לקריאת דוח קיים.")
    print(f"נמען: {a.phone}")
    print("שים לב: כל ערוץ הוא פעולה יוצאת אמיתית שעולה יחידות.")

    # ערוצי ההתראה החדשים — כשמבקשים אותם, מריצים רק אותם.
    if a.sms or a.tzintuk:
        if a.sms:
            run_sms(token, a.phone)
        if a.tzintuk:
            run_tzintuk(token, a.phone)
        return

    if not a.file_only:
        run_tts(token, a.phone, a.long)
    if not a.tts_only:
        run_file(token, a.phone, a.long)

    print("\nהערכת ההגשה אינה החיוב הסופי. אחרי שהשיחות מסתיימות, קרא")
    print("את הדוח של כל קמפיין:  --report <campaignId>")


if __name__ == "__main__":
    main()
