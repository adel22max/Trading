#!/usr/bin/env python3
"""
بوت قناة التداول: ينشر 4 أنواع من المنشورات.

الاستخدام:
    python trading_bot.py quiz       -> سؤال تداول (Quiz) من trading_questions.json
    python trading_bot.py term       -> مصطلح اليوم من terms.json
    python trading_bot.py calendar   -> أهم أحداث اليوم الاقتصادية
    python trading_bot.py market     -> لمحة أسعار السوق
    أضف --dry-run لطباعة المنشور بدون إرساله.

متغيرات البيئة:
    TRADING_BOT_TOKEN   توكن بوت قناة التداول (بوت مستقل عن بوت الإنكليزي)
    TRADING_CHANNEL_ID  @Heikin_Trading0 أو رقم القناة -100...
"""

import csv
import html
import io
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "trading_state.json"

TOKEN = os.environ.get("TRADING_BOT_TOKEN", "").strip()
CHANNEL = os.environ.get("TRADING_CHANNEL_ID", "").strip()
TZ = ZoneInfo("Asia/Damascus")
DRY = "--dry-run" in sys.argv
UA = {"User-Agent": "Mozilla/5.0 (compatible; ChannelBot/1.0)"}

FOOTER = "⚠️ للمعلومة والتعليم فقط، وليس نصيحة مالية. التداول ينطوي على مخاطر."
DAYS_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def esc(s):
    return html.escape(str(s), quote=False)


# ---------------- تليجرام ----------------
def tg(method, payload):
    if DRY:
        print(f"--- {method} ---")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    resp = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/{method}", json=payload, timeout=30
    )
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(f"رد غير متوقع من تليجرام (HTTP {resp.status_code})")
    if not data.get("ok"):
        raise RuntimeError(f"تليجرام رجّع خطأ: {data.get('description')}")


def send_text(text):
    tg(
        "sendMessage",
        {
            "chat_id": CHANNEL,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


# ---------------- حفظ ما انتشر ----------------
def load_json(name):
    return json.loads((BASE_DIR / name).read_text(encoding="utf-8"))


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def pick_unused(kind, count):
    state = load_state()
    used = set(state.get(kind, []))
    remaining = [i for i in range(count) if i not in used]
    if not remaining:  # خلصت كلها، نبدأ من جديد
        used = set()
        remaining = list(range(count))
    return random.choice(remaining), used, state


def mark_used(kind, idx, used, state):
    if DRY:
        return
    used.add(idx)
    state[kind] = sorted(used)
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


# ---------------- 1) سؤال التداول ----------------
def post_quiz():
    questions = load_json("trading_questions.json")
    idx, used, state = pick_unused("quiz", len(questions))
    q = questions[idx]

    options = q["options"][:]
    correct_text = options[0]  # أول خيار هو الصحيح، منخلط الترتيب
    random.shuffle(options)

    payload = {
        "chat_id": CHANNEL,
        "question": q["q"],
        "options": options,
        "type": "quiz",
        "correct_option_id": options.index(correct_text),
        "is_anonymous": True,
    }
    if q.get("explanation"):
        payload["explanation"] = q["explanation"]
    tg("sendPoll", payload)
    mark_used("quiz", idx, used, state)
    print("تم نشر السؤال:", q["q"])


# ---------------- 2) مصطلح اليوم ----------------
def build_term_message(t):
    lines = [
        "📚 <b>مصطلح اليوم</b>",
        "",
        f"<b>{esc(t['term'])}</b> — {esc(t['ar'])}",
        "",
        esc(t["explain"]),
    ]
    if t.get("example"):
        lines += ["", f"💡 <i>{esc(t['example'])}</i>"]
    lines += ["", "⚠️ محتوى تعليمي وليس نصيحة مالية."]
    return "\n".join(lines)


def post_term():
    terms = load_json("terms.json")
    idx, used, state = pick_unused("term", len(terms))
    send_text(build_term_message(terms[idx]))
    mark_used("term", idx, used, state)
    print("تم نشر المصطلح:", terms[idx]["term"])


# ---------------- 3) تقويم الأخبار ----------------
CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵", "CAD": "🇨🇦",
    "AUD": "🇦🇺", "NZD": "🇳🇿", "CHF": "🇨🇭", "CNY": "🇨🇳",
}
# الترتيب مهم: أول تطابق هو اللي بيُستعمل
CAL_AR = [
    ("fomc meeting minutes", "محضر اجتماع الفيدرالي"),
    ("non-farm employment change", "الوظائف غير الزراعية"),
    ("unemployment rate", "معدل البطالة"),
    ("jobless claims", "طلبات إعانة البطالة"),
    ("core cpi", "التضخم الأساسي (CPI)"),
    ("cpi", "مؤشر أسعار المستهلك (التضخم)"),
    ("ppi", "مؤشر أسعار المنتجين"),
    ("federal funds rate", "قرار الفائدة الأمريكية"),
    ("official bank rate", "قرار الفائدة"),
    ("main refinancing rate", "قرار الفائدة"),
    ("cash rate", "قرار الفائدة"),
    ("policy rate", "قرار الفائدة"),
    ("interest rate", "قرار الفائدة"),
    ("rate statement", "بيان الفائدة"),
    ("press conference", "مؤتمر صحفي"),
    ("gdp", "الناتج المحلي الإجمالي"),
    ("retail sales", "مبيعات التجزئة"),
    ("pmi", "مؤشر مديري المشتريات"),
    ("crude oil inventories", "مخزونات النفط الخام"),
    ("consumer sentiment", "ثقة المستهلك"),
    ("consumer confidence", "ثقة المستهلك"),
    ("trade balance", "الميزان التجاري"),
    ("speaks", "تصريحات"),
]


def ar_title(title):
    low = title.lower()
    for key, ar in CAL_AR:
        if key in low:
            return ar
    return None


def build_calendar_message(events, now):
    todays = []
    for ev in events:
        try:
            if ev.get("impact") != "High":
                continue
            dt = datetime.fromisoformat(ev["date"]).astimezone(TZ)
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        if dt.date() == now.date():
            todays.append((dt, ev))
    if not todays:
        return None
    todays.sort(key=lambda x: x[0])

    lines = [
        "📅 <b>أهم الأحداث الاقتصادية اليوم</b>",
        f"🗓 {DAYS_AR[now.weekday()]} {now:%d-%m-%Y} — بتوقيت دمشق",
        "",
    ]
    for dt, ev in todays[:12]:
        cur = ev.get("country", "")
        flag = FLAGS.get(cur, "🌐")
        title = ev.get("title", "")
        ar = ar_title(title)
        name = f"{esc(ar)} <i>({esc(title)})</i>" if ar else esc(title)
        lines.append(f"🕐 <b>{dt:%H:%M}</b> {flag} <b>{esc(cur)}</b> — {name}")
        extra = []
        if ev.get("forecast"):
            extra.append(f"المتوقع: {esc(ev['forecast'])}")
        if ev.get("previous"):
            extra.append(f"السابق: {esc(ev['previous'])}")
        if extra:
            lines.append("↳ " + "  |  ".join(extra))
        lines.append("")
    lines.append("<i>المصدر: تقويم Forex Factory. الأوقات والتوقعات قد تتغير.</i>")
    lines.append("")
    lines.append(FOOTER)
    return "\n".join(lines)


def fetch_calendar():
    r = requests.get(CAL_URL, headers=UA, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("مصدر التقويم رفض الطلب مؤقتاً (429)، جرّب بعد قليل")
    r.raise_for_status()
    return r.json()


def post_calendar():
    now = datetime.now(TZ)
    msg = build_calendar_message(fetch_calendar(), now)
    if msg is None:
        print("ما في أحداث عالية التأثير اليوم، ما رح ننشر شي.")
        return
    send_text(msg)
    print("تم نشر تقويم الأخبار.")


# ---------------- 4) لمحة السوق ----------------
# (الرمز بالمصدر، الاسم، عدد الخانات العشرية)
STOOQ = [
    ("XAUUSD", "🥇 الذهب XAU/USD", 2),
    ("EURUSD", "💶 EUR/USD", 4),
    ("GBPUSD", "💷 GBP/USD", 4),
    ("USDJPY", "💴 USD/JPY", 3),
    ("^SPX", "📈 S&P 500", 2),
    ("^NDX", "📈 Nasdaq 100", 2),
]
CRYPTO = [("bitcoin", "🪙 Bitcoin (BTC)"), ("ethereum", "🔷 Ethereum (ETH)")]


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_stooq(text):
    rows = {}
    for row in csv.DictReader(io.StringIO(text)):
        sym = (row.get("Symbol") or "").upper()
        if sym:
            rows[sym] = row
    return rows


def fetch_stooq():
    syms = "+".join(s.lower() for s, _, _ in STOOQ)
    url = f"https://stooq.com/q/l/?s={syms}&f=sd2t2ohlc&h&e=csv"
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return parse_stooq(r.text)


def fetch_crypto():
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": ",".join(c for c, _ in CRYPTO),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        },
        headers=UA,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def change_text(pct):
    if pct is None:
        return ""
    arrow = "▲" if pct >= 0 else "▼"
    return f"  ({arrow} {pct:+.2f}%)"


def build_market_message(stooq_rows, crypto, now):
    market_lines = []
    stale = False
    for sym, label, dec in STOOQ:
        row = stooq_rows.get(sym)
        if not row:
            continue
        close = fnum(row.get("Close"))
        if close is None:
            continue
        open_ = fnum(row.get("Open"))
        pct = (close - open_) / open_ * 100 if open_ else None
        if row.get("Date") and row["Date"] != now.strftime("%Y-%m-%d"):
            stale = True
        market_lines.append(f"{label}: <b>{close:,.{dec}f}</b>{change_text(pct)}")

    crypto_lines = []
    for cid, label in CRYPTO:
        d = crypto.get(cid) or {}
        price = fnum(d.get("usd"))
        if price is None:
            continue
        crypto_lines.append(
            f"{label}: <b>${price:,.0f}</b>{change_text(fnum(d.get('usd_24h_change')))}"
        )

    if not market_lines and not crypto_lines:
        return None

    lines = ["📊 <b>لمحة السوق</b>", f"🕐 {now:%H:%M} بتوقيت دمشق", ""]
    if market_lines:
        lines += ["<b>المعادن والعملات والمؤشرات</b>"] + market_lines + [""]
    if crypto_lines:
        lines += ["<b>العملات الرقمية</b>"] + crypto_lines + [""]
    note = "التغير للأصول التقليدية منذ افتتاح اليوم، وللكريبتو خلال 24 ساعة. الأسعار تقريبية وقد تختلف عن منصتك."
    if stale:
        note += " بعض الأسعار هي آخر إغلاق."
    lines += [f"<i>{note}</i>", "", FOOTER]
    return "\n".join(lines)


def post_market():
    now = datetime.now(TZ)
    rows, crypto = {}, {}
    try:
        rows = fetch_stooq()
    except Exception as e:
        print("تعذر جلب أسعار المعادن والعملات:", e)
    try:
        crypto = fetch_crypto()
    except Exception as e:
        print("تعذر جلب أسعار الكريبتو:", e)
    msg = build_market_message(rows, crypto, now)
    if msg is None:
        raise RuntimeError("ما قدرت أجيب أي سعر من المصادر")
    send_text(msg)
    print("تم نشر لمحة السوق.")


MODES = {
    "quiz": post_quiz,
    "term": post_term,
    "calendar": post_calendar,
    "market": post_market,
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1 or args[0] not in MODES:
        sys.exit("الاستخدام: python trading_bot.py [quiz|term|calendar|market] [--dry-run]")
    if not DRY and (not TOKEN or not CHANNEL):
        sys.exit("لازم تحدد TRADING_BOT_TOKEN و TRADING_CHANNEL_ID")
    MODES[args[0]]()


if __name__ == "__main__":
    main()
