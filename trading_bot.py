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
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
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
SESSION = requests.Session()
SESSION.headers.update(UA)

# (القسم، الاسم، رمز Yahoo، رمز Stooq البديل أو None، عدد الخانات العشرية)
ASSETS = [
    ("fx", "💶 EUR/USD", "EURUSD=X", "eurusd", 4),
    ("fx", "💷 GBP/USD", "GBPUSD=X", "gbpusd", 4),
    ("fx", "💴 USD/JPY", "USDJPY=X", "usdjpy", 3),
    ("fx", "🇨🇭 USD/CHF", "USDCHF=X", "usdchf", 4),
    ("fx", "🇦🇺 AUD/USD", "AUDUSD=X", "audusd", 4),
    ("fx", "🇨🇦 USD/CAD", "USDCAD=X", "usdcad", 4),
    ("fx", "🇳🇿 NZD/USD", "NZDUSD=X", "nzdusd", 4),
    ("com", "🥇 الذهب (عقود آجلة)", "GC=F", "xauusd", 2),
    ("com", "🥈 الفضة (عقود آجلة)", "SI=F", "xagusd", 3),
    ("com", "🛢 نفط WTI", "CL=F", "cl.f", 2),
    ("com", "🛢 نفط برنت", "BZ=F", None, 2),
    ("idx", "🇺🇸 داو جونز", "^DJI", "^dji", 2),
    ("idx", "🇺🇸 S&P 500", "^GSPC", "^spx", 2),
    ("idx", "🇺🇸 ناسداك", "^IXIC", "^ndq", 2),
    ("idx", "🇩🇪 DAX الألماني", "^GDAXI", "^dax", 2),
    ("idx", "🇬🇧 FTSE 100", "^FTSE", "^ukx", 2),
    ("idx", "🇯🇵 نيكاي 225", "^N225", "^nkx", 2),
    ("idx", "💵 مؤشر الدولار DXY", "DX-Y.NYB", None, 2),
]
CRYPTO = [
    ("cry", "🪙 Bitcoin (BTC)", "bitcoin", "BTC-USD", 0),
    ("cry", "🔷 Ethereum (ETH)", "ethereum", "ETH-USD", 0),
]
SECTIONS = [
    ("fx", "💱 العملات الرئيسية"),
    ("com", "🏅 الذهب والمعادن والنفط"),
    ("idx", "📈 المؤشرات"),
    ("cry", "🪙 العملات الرقمية"),
]
STALE_AFTER = 6 * 3600  # أقدم من 6 ساعات = آخر إغلاق وليس سعراً حياً
MIN_SHARE = 0.6         # أقل نسبة أصول لازم تنجلب حتى ننشر


def fnum(x):
    try:
        v = float(x)
        return v if v == v else None  # يستبعد NaN
    except (TypeError, ValueError):
        return None


def yahoo_quote(symbol):
    """سعر أصل من Yahoo Finance. يرجع dict أو يرمي استثناء."""
    last = None
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
        try:
            r = SESSION.get(url, params={"range": "1d", "interval": "1d"}, timeout=20)
            if r.status_code == 429:
                last = RuntimeError("HTTP 429 (طلبات كثيرة)")
                time.sleep(2)
                continue
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            meta = res["meta"]
            price = fnum(meta.get("regularMarketPrice"))
            if price is None:
                raise ValueError("ما في سعر بالرد")
            prev = fnum(meta.get("chartPreviousClose"))
            if prev is None:
                prev = fnum(meta.get("previousClose"))
            return {
                "price": price,
                "prev": prev,
                "time": meta.get("regularMarketTime"),
                "src": "yahoo",
                "approx": False,
            }
        except Exception as e:  # نجرب المضيف التاني
            last = e
    raise RuntimeError(f"Yahoo فشل: {last}")


def stooq_quote(symbol):
    """سعر بديل من Stooq. التغير فيه تقريبي (من افتتاح اليوم)."""
    r = SESSION.get(
        "https://stooq.com/q/l/",
        params={"s": symbol, "f": "sd2t2ohlc", "h": "", "e": "csv"},
        timeout=20,
    )
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    if not rows:
        raise ValueError("رد فاضي")
    row = rows[0]
    close, open_ = fnum(row.get("Close")), fnum(row.get("Open"))
    if close is None:
        raise ValueError("ما في سعر (N/D)")
    return {"price": close, "prev": open_, "time": None, "src": "stooq", "approx": True}


def coingecko_quotes(ids):
    r = SESSION.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": ",".join(ids),
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def collect_quotes():
    """يجلب كل الأصول. يرجع (quotes, failures). كل فشل بينطبع بالسجل."""
    quotes, failures = {}, []

    for sec, label, ysym, ssym, dec in ASSETS:
        q, errs = None, []
        for name, fn, sym in (("yahoo", yahoo_quote, ysym), ("stooq", stooq_quote, ssym)):
            if not sym:
                continue
            try:
                q = fn(sym)
                break
            except Exception as e:
                errs.append(f"{name}:{sym}: {e}")
            time.sleep(0.3)
        if q:
            quotes[label] = q
            print(f"OK   [{q['src']}] {label} = {q['price']}")
        else:
            failures.append(label)
            print(f"FAIL {label} -> " + " | ".join(errs))
        time.sleep(0.3)

    try:
        cg = coingecko_quotes([c[2] for c in CRYPTO])
    except Exception as e:
        cg = {}
        print(f"FAIL CoinGecko -> {e}")
    for sec, label, cid, ysym, dec in CRYPTO:
        d = cg.get(cid) or {}
        price = fnum(d.get("usd"))
        q = None
        if price is not None:
            q = {
                "price": price,
                "pct": fnum(d.get("usd_24h_change")),
                "time": d.get("last_updated_at"),
                "src": "coingecko",
                "approx": False,
            }
        else:
            try:
                q = yahoo_quote(ysym)
            except Exception as e:
                print(f"FAIL {label} -> {e}")
        if q:
            quotes[label] = q
            print(f"OK   [{q['src']}] {label} = {q['price']}")
        else:
            failures.append(label)
        time.sleep(0.3)
    return quotes, failures


def pct_of(q):
    if q.get("pct") is not None:
        return q["pct"]
    if q.get("prev"):
        return (q["price"] - q["prev"]) / q["prev"] * 100
    return None


def change_text(pct):
    if pct is None:
        return ""
    arrow = "▲" if pct >= 0 else "▼"
    return f"  ({arrow} {pct:+.2f}%)"


def build_market_message(quotes, now, now_ts=None):
    """quotes: {label: dict}. يرجع نص المنشور أو None إذا ما في بيانات."""
    now_ts = now_ts or now.timestamp()
    decs = {label: dec for _, label, _, _, dec in ASSETS}
    decs.update({label: dec for _, label, _, _, dec in CRYPTO})
    by_section = {}
    for sec, label, *_ in ASSETS + CRYPTO:
        if label in quotes:
            by_section.setdefault(sec, []).append(label)
    if not by_section:
        return None

    lines = ["📊 <b>لمحة السوق</b>", f"🕐 {now:%H:%M} بتوقيت دمشق", ""]
    approx = False
    for sec, title in SECTIONS:
        labels = by_section.get(sec)
        if not labels:
            continue
        stale = sum(
            1 for l in labels
            if quotes[l].get("time") and now_ts - quotes[l]["time"] > STALE_AFTER
        )
        if stale * 2 >= len(labels):
            title += " — آخر إغلاق"
        lines.append(f"<b>{esc(title)}</b>")
        for l in labels:
            q = quotes[l]
            approx = approx or q.get("approx", False)
            lines.append(f"{esc(l)}: <b>{q['price']:,.{decs[l]}f}</b>{change_text(pct_of(q))}")
        lines.append("")

    note = (
        "التغير مقارنة بإغلاق اليوم السابق، وللكريبتو خلال 24 ساعة. "
        "الأسعار تقريبية وقد تختلف عن منصتك."
    )
    if approx:
        note += " بعض التغيرات تقريبية من مصدر بديل."
    lines += [f"<i>{note}</i>", "", FOOTER]
    return "\n".join(lines)


def post_market():
    now = datetime.now(TZ)
    quotes, failures = collect_quotes()
    total = len(ASSETS) + len(CRYPTO)
    traditional = sum(1 for _, l, *_ in ASSETS if l in quotes)
    if traditional == 0 or len(quotes) < total * MIN_SHARE:
        raise RuntimeError(
            f"ما جبت إلا {len(quotes)} من {total} أصل، فما رح أنشر منشور ناقص. "
            f"الفاشلة: {', '.join(failures)}"
        )
    send_text(build_market_message(quotes, now))
    if failures:
        print("تنبيه: نُشر المنشور بدون:", ", ".join(failures))
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
