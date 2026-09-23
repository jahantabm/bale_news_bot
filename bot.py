# -*- coding: utf-8 -*-

"""
JAHANTAB | جهان‌تاب
آخرین تحولات سیستان و بلوچستان

نسخه 6.0

ویژگی‌ها:
- فقط منابع خبری داخلی تعریف‌شده
- تمرکز تخصصی روی سیستان و بلوچستان
- پوشش شهرها و شهرستان‌های استان
- پوشش فرهنگ، هنر، موسیقی و میراث
- پوشش هامون، هیرمند، جازموریان، مکران و دریای عمان
- حذف خبرهای سایر استان‌ها
- حذف خبرهای خارجی نامرتبط
- حذف موضوعات ورزشی/هنری سراسری نامرتبط
- ضدتکرار بر اساس URL
- ضدتکرار بر اساس عنوان نرمال‌شده
- ضدتکرار بر اساس شباهت عنوان
- حداکثر یک خبر در هر 30 دقیقه
- دکمه مشاهده خبر
- دکمه‌های تلگرام، بله و سروش
- تصویر خبر در صورت وجود
"""

import os
import re
import json
import html
import time
import hashlib
import calendar

from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
CHAT_ID = os.getenv("BALE_CHAT_ID")

STATE_FILE = "sent_links.txt"
TITLE_STATE_FILE = "sent_titles.txt"

# هر 30 دقیقه یک خبر
PUBLISH_INTERVAL = 30 * 60

# حداکثر سن خبر
MAX_NEWS_AGE_HOURS = 24

# تعداد خبر در هر چرخه
MAX_NEWS_PER_CYCLE = 1


if not BOT_TOKEN:
    raise RuntimeError("BALE_BOT_TOKEN is not set")

if not CHAT_ID:
    raise RuntimeError("BALE_CHAT_ID is not set")


# ============================================================
# APPROVED INTERNAL IRANIAN NEWS SOURCES
# ============================================================

SOURCES = [

    ("ایرنا", "irna.ir", [
        "https://www.irna.ir/rss",
    ]),

    ("ایسنا", "isna.ir", [
        "https://www.isna.ir/rss",
    ]),

    ("مهر", "mehrnews.com", [
        "https://www.mehrnews.com/rss",
    ]),

    ("فارس", "farsnews.ir", [
        "https://www.farsnews.ir/rss",
    ]),

    ("ایلنا", "ilna.ir", [
        "https://www.ilna.ir/rss",
    ]),

    ("تسنیم", "tasnimnews.com", [
        "https://www.tasnimnews.com/fa/rss/feed/0/8/0/مهمترین-اخبار-تسنیم",
    ]),

    ("تابناک", "tabnak.ir", [
        "https://www.tabnak.ir/fa/rss/allnews",
    ]),

    ("عصر ایران", "asriran.com", [
        "https://www.asriran.com/fa/rss/allnews",
    ]),

    ("فرارو", "fararu.com", [
        "https://fararu.com/fa/rss",
    ]),

    ("جهان نیوز", "jahannews.com", [
        "https://www.jahannews.com/rss",
    ]),

    ("خبرآنلاین", "khabaronline.ir", [
        "https://www.khabaronline.ir/rss",
    ]),

    ("آخرین خبر", "akharinkhabar.ir", [
        "https://akharinkhabar.ir/rss",
    ]),

    ("خبر فوری", "khabarfouri.com", [
        "https://www.khabarfouri.com/rss",
    ]),

    ("روز پلاس", "roozplus.com", [
        "https://roozplus.com/rss",
    ]),

    ("همشهری", "hamshahrionline.ir", [
        "https://www.hamshahrionline.ir/rss",
    ]),

    ("جام جم", "jamejamonline.ir", [
        "https://jamejamonline.ir/rss",
    ]),

    ("باشگاه خبرنگاران جوان", "yjc.ir", [
        "https://www.yjc.ir/fa/rss/allnews",
    ]),

    ("انتخاب", "entekhab.ir", [
        "https://www.entekhab.ir/fa/rss",
    ]),

    ("خبرگزاری صداوسیما", "iribnews.ir", [
        "https://www.iribnews.ir/fa/rss",
    ]),
]


# ============================================================
# BLOCKED DOMAINS
# ============================================================

BLOCKED_DOMAINS = {
    "google.com",
    "news.google.com",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "fb.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "t.co",
    "telegram.me",
    "t.me",
    "aparat.com",
}


# ============================================================
# SIستان و بلوچستان
# ============================================================

PROVINCE_TERMS = [
    "سیستان و بلوچستان",
    "سیستان‌ و بلوچستان",
    "سیستان‌وبلوچستان",
    "سیستان وبلوچستان",
    "استان سیستان و بلوچستان",
    "استان سیستان‌ و بلوچستان",
    "استان سیستان‌وبلوچستان",
]


# ============================================================
# CITIES / COUNTIES / LOCAL AREAS
# ============================================================

CITY_TERMS = [
    "زاهدان",
    "زابل",
    "چابهار",
    "سراوان",
    "ایرانشهر",
    "خاش",
    "نیکشهر",
    "کنارک",
    "راسک",
    "دلگان",
    "میرجاوه",
    "زهک",
    "هیرمند",
    "هامون",
    "فنوج",
    "سرباز",
    "قصرقند",
    "بزمان",
    "بمپور",
    "دشتیاری",
    "مهرستان",
    "سیب و سوران",
    "نیمروز",
    "بنت",
    "پیشین",
    "گشت",
    "تفتان",
    "بزمان",
    "محمدان",
    "نگور",
    "اسپکه",
    "لاشار",
    "آشار",
    "راسک",
    "پلان",
    "زرآباد",
    "باهوکلات",
    "گلمورتی",
    "زابلی",
    "ادیمی",
    "نوک‌آباد",
    "نوک آباد",
    "دشتیاری",
    "کلات",
]


# ============================================================
# SPECIAL LOCAL GEOGRAPHY
# ============================================================

LOCAL_GEOGRAPHY_TERMS = [

    # هامون
    "هامون",
    "تالاب هامون",
    "دریاچه هامون",
    "هامون صابری",
    "هامون هیرمند",

    # هیرمند
    "رودخانه هیرمند",
    "رود هیرمند",
    "هیرمند",
    "حقابه هیرمند",
    "حق‌آبه هیرمند",
    "آب هیرمند",

    # جازموریان
    "جازموریان",
    "تالاب جازموریان",
    "حوضه جازموریان",

    # مکران
    "مکران",
    "سواحل مکران",
    "ساحل مکران",

    # دریای عمان
    "دریای عمان",
    "سواحل دریای عمان",
    "ساحل دریای عمان",

    # چابهار
    "بندر چابهار",
    "منطقه آزاد چابهار",
    "مکران جنوبی",
]


# ============================================================
# LOCAL CULTURE / ART / MUSIC / HERITAGE
# ============================================================

LOCAL_CULTURE_TERMS = [

    # فرهنگ
    "فرهنگ سیستان",
    "فرهنگ بلوچستان",
    "فرهنگ سیستان و بلوچستان",
    "فرهنگ بلوچ",
    "فرهنگ بومی بلوچستان",
    "فرهنگ بومی سیستان",

    # هنر
    "هنر سیستان",
    "هنر بلوچستان",
    "هنرمندان سیستان و بلوچستان",
    "هنرمند سیستان و بلوچستان",
    "هنر بومی بلوچستان",
    "صنایع دستی سیستان و بلوچستان",
    "صنایع‌دستی سیستان و بلوچستان",

    # موسیقی
    "موسیقی سیستان",
    "موسیقی بلوچستان",
    "موسیقی بلوچ",
    "موسیقی سیستان و بلوچستان",
    "هنرمند بلوچ",
    "خواننده بلوچ",
    "خواننده سیستانی",
    "نوازنده بلوچ",
    "موسیقی بومی بلوچستان",
    "موسیقی محلی بلوچستان",
    "موسیقی محلی سیستان",

    # ادبیات
    "شاعر بلوچ",
    "شاعر سیستانی",
    "شاعران بلوچ",
    "ادبیات بلوچستان",
    "ادبیات سیستان",

    # میراث
    "میراث فرهنگی سیستان و بلوچستان",
    "میراث فرهنگی بلوچستان",
    "میراث فرهنگی سیستان",
    "باستان‌شناسی سیستان و بلوچستان",
    "باستان شناسی سیستان و بلوچستان",
    "آثار باستانی سیستان و بلوچستان",
    "محوطه باستانی سیستان و بلوچستان",

    # بناها و آثار شاخص
    "شهر سوخته",
    "کوه خواجه",
    "قلعه رستم",
    "قلعه ناصری",
    "قلعه بمپور",
    "روستای کلپور",
    "کلپورگان",
    "سفال کلپورگان",
    "سفالگری کلپورگان",
    "سوزن‌دوزی بلوچ",
    "سوزن دوزی بلوچ",
    "حصیربافی",
    "بلوچی‌دوزی",
    "بلوچی دوزی",
]


# ============================================================
# LOCAL ECONOMY / SOCIETY / ENVIRONMENT
# ============================================================

LOCAL_SUBJECT_TERMS = [

    # آب
    "آبرسانی",
    "تنش آبی",
    "کمبود آب",
    "بحران آب",
    "آب شرب",
    "آب آشامیدنی",
    "حقابه",
    "حق‌آبه",

    # محیط زیست
    "محیط زیست",
    "محیط‌زیست",
    "خشکسالی",
    "گرد و غبار",
    "ریزگرد",
    "تالاب",
    "حیات وحش",
    "حیات‌وحش",
    "منطقه حفاظت شده",
    "منطقه حفاظت‌شده",

    # کشاورزی
    "کشاورزی",
    "نخلستان",
    "خرما",
    "دامداری",
    "مراتع",

    # دریا و صید
    "صیادی",
    "ماهیگیری",
    "شیلات",
    "صید",
    "لنج",
    "بندر",
    "کشتیرانی",

    # توسعه
    "پروژه",
    "طرح توسعه",
    "زیرساخت",
    "راه",
    "جاده",
    "راه‌آهن",
    "راه آهن",
    "فرودگاه",
    "بیمارستان",
    "مدرسه",
    "دانشگاه",
    "بندر",
    "منطقه آزاد",

    # مدیریت استان
    "استاندار",
    "استانداری",
    "فرماندار",
    "فرمانداری",
    "معاون استاندار",
    "نماینده ولی فقیه",
    "مجمع نمایندگان",
    "نماینده مردم",

    # حوادث و انتظامی
    "حادثه",
    "تصادف",
    "آتش‌سوزی",
    "آتش سوزی",
    "زلزله",
    "سیل",
    "طوفان",
    "بارندگی",
    "قاچاق",
    "کشف",
    "توقیف",
    "دستگیری",
    "بازداشت",
    "فوت",
    "جان باخت",
    "کشته",
    "مصدوم",
    "نجات",
    "امداد",
    "مأمور انتظامی",
    "نیروی انتظامی",
    "فراجا",
    "پلیس",
]


# ============================================================
# OTHER IRANIAN PROVINCES
# ============================================================

OTHER_PROVINCE_TERMS = [
    "آذربایجان شرقی",
    "آذربایجان غربی",
    "اردبیل",
    "اصفهان",
    "البرز",
    "ایلام",
    "بوشهر",
    "تهران",
    "چهارمحال و بختیاری",
    "خراسان جنوبی",
    "خراسان رضوی",
    "خراسان شمالی",
    "خوزستان",
    "زنجان",
    "سمنان",
    "فارس",
    "قزوین",
    "قم",
    "کردستان",
    "کرمان",
    "کرمانشاه",
    "کهگیلویه و بویراحمد",
    "گلستان",
    "گیلان",
    "لرستان",
    "مازندران",
    "مرکزی",
    "هرمزگان",
    "همدان",
    "یزد",
]


# ============================================================
# FOREIGN LOCATION TERMS
# ============================================================

FOREIGN_LOCATION_TERMS = [
    "سوریه",
    "ترکیه",
    "عراق",
    "پاکستان",
    "افغانستان",
    "لبنان",
    "یمن",
    "غزه",
    "اسرائیل",
    "فلسطین",
    "اردن",
    "عربستان",
    "قطر",
    "امارات",
    "آمریکا",
    "ایالات متحده",
    "روسیه",
    "اوکراین",
    "چین",
    "هند",
    "فرانسه",
    "آلمان",
    "انگلیس",
    "بریتانیا",
    "سازمان ملل",
    "نیویورک",
    "واشنگتن",
    "لندن",
    "پاریس",
    "مسکو",
    "آنکارا",
    "دمشق",
    "بغداد",
    "کابل",
    "اسلام‌آباد",
    "اسلام آباد",
    "تل‌آویو",
    "تل آویو",
]


# ============================================================
# GENERIC NATIONAL / UNRELATED TOPICS
# ============================================================

UNRELATED_TERMS = [

    # ورزش سراسری
    "سردار آزمون",
    "مهدی طارمی",
    "تیم ملی فوتبال",
    "تیم ملی",
    "فوتبال",
    "لیگ برتر",
    "استقلال",
    "پرسپولیس",
    "سپاهان",
    "جام جهانی",
    "بازیکن",
    "مربی",
    "ورزشگاه",

    # سرگرمی سراسری
    "سلبریتی",
    "بازیگر",
    "فیلم",
    "سریال",
    "آگاتا کریستی",
    "خانم مارپل",
    "مارپل",

    # موضوعات عمومی غیرمحلی
    "فال",
    "طالع بینی",
    "مد و زیبایی",
    "سبک زندگی",
]


# ============================================================
# SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; JahantabNewsBot/6.0)"
    )
})


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def clean_text(value):

    if not value:
        return ""

    value = html.unescape(str(value))

    soup = BeautifulSoup(
        value,
        "html.parser",
    )

    value = soup.get_text(
        " ",
        strip=True,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_persian(text):

    text = clean_text(text)

    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "‌": " ",
        "\u200c": " ",
        "\u200f": " ",
        "\u200e": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # حذف علائم نگارشی برای مقایسه
    text = re.sub(
        r"[^\w\sآ-ی]",
        " ",
        text,
        flags=re.UNICODE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip().lower()


def title_fingerprint(title):

    normalized = normalize_persian(title)

    words = normalized.split()

    # حذف کلمات بسیار عمومی
    stop_words = {
        "در",
        "به",
        "از",
        "با",
        "برای",
        "یک",
        "این",
        "آن",
        "شد",
        "شدند",
        "کرد",
        "کرده",
        "اعلام",
        "خبر",
        "گفت",
        "گفتند",
    }

    words = [
        word
        for word in words
        if word not in stop_words
    ]

    words = sorted(set(words))

    return " ".join(words)


def title_hash(title):

    fingerprint = title_fingerprint(title)

    return hashlib.sha256(
        fingerprint.encode("utf-8")
    ).hexdigest()


# ============================================================
# URL
# ============================================================

def normalize_url(url):

    if not url:
        return ""

    url = str(url).strip()

    url = re.sub(
        r"[?&](utm_[^&]+|fbclid|gclid)=[^&]*",
        "",
        url,
        flags=re.IGNORECASE,
    )

    return url.rstrip("?&")


def get_domain(url):

    try:

        domain = (
            urlparse(url).hostname
            or ""
        )

        domain = domain.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return domain

    except Exception:
        return ""


def is_blocked_url(url):

    domain = get_domain(url)

    if not domain:
        return True

    if domain in BLOCKED_DOMAINS:
        return True

    for blocked in BLOCKED_DOMAINS:

        if domain.endswith(
            "." + blocked
        ):
            return True

    return False


def is_allowed_source_url(
    url,
    source_domain,
):

    domain = get_domain(url)

    if not domain:
        return False

    if is_blocked_url(url):
        return False

    return (
        domain == source_domain
        or domain.endswith(
            "." + source_domain
        )
    )


# ============================================================
# STATE
# ============================================================

def load_state_file(path):

    if not os.path.exists(path):
        return set()

    try:

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:

            return {
                line.strip()
                for line in file
                if line.strip()
            }

    except Exception as exc:

        print(
            f"State read error: {exc}"
        )

        return set()


def load_sent_links():

    return load_state_file(
        STATE_FILE
    )


def load_sent_titles():

    return load_state_file(
        TITLE_STATE_FILE
    )


def save_state(path, value):

    try:

        with open(
            path,
            "a",
            encoding="utf-8",
        ) as file:

            file.write(
                value + "\n"
            )

    except Exception as exc:

        print(
            f"State save error: {exc}"
        )


def save_sent_link(link):

    save_state(
        STATE_FILE,
        link,
    )


def save_sent_title(title):

    save_state(
        TITLE_STATE_FILE,
        title_hash(title),
    )


# ============================================================
# DATE
# ============================================================

def parse_date(entry):

    try:

        if getattr(
            entry,
            "published_parsed",
            None,
        ):

            timestamp = calendar.timegm(
                entry.published_parsed
            )

            return datetime.fromtimestamp(
                timestamp,
                timezone.utc,
            )

        if getattr(
            entry,
            "updated_parsed",
            None,
        ):

            timestamp = calendar.timegm(
                entry.updated_parsed
            )

            return datetime.fromtimestamp(
                timestamp,
                timezone.utc,
            )

    except Exception:
        pass

    # اگر تاریخ قابل تشخیص نباشد،
    # خبر جدید فرض نمی‌شود.
    return None


# ============================================================
# SUMMARY
# ============================================================

def make_summary(entry):

    text = ""

    if getattr(
        entry,
        "summary",
        None,
    ):

        text = clean_text(
            entry.summary
        )

    if not text and getattr(
        entry,
        "description",
        None,
    ):

        text = clean_text(
            entry.description
        )

    if not text:
        return ""

    text = re.sub(
        r"\s*\.\.\.\s*$",
        "",
        text,
    )

    if len(text) > 600:

        text = (
            text[:597]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return text


# ============================================================
# TERM HELPERS
# ============================================================

def contains_any(
    text,
    terms,
):

    return any(
        term in text
        for term in terms
    )


def count_terms(
    text,
    terms,
):

    return sum(
        1
        for term in terms
        if term in text
    )


# ============================================================
# OTHER PROVINCE DETECTION
# ============================================================

def other_province_in_title(title):

    title = normalize_persian(title)

    for province in OTHER_PROVINCE_TERMS:

        if normalize_persian(province) in title:
            return True

    return False


def other_province_in_text(text):

    text = normalize_persian(text)

    for province in OTHER_PROVINCE_TERMS:

        if normalize_persian(province) in text:
            return True

    return False


# ============================================================
# FOREIGN DETECTION
# ============================================================

def foreign_location_in_title(title):

    title = normalize_persian(title)

    for term in FOREIGN_LOCATION_TERMS:

        if normalize_persian(term) in title:
            return True

    return False


# ============================================================
# LOCAL EVIDENCE
# ============================================================

def get_local_evidence(
    title,
    summary,
):

    title_n = normalize_persian(title)
    summary_n = normalize_persian(summary)

    full = (
        title_n
        + " "
        + summary_n
    )

    province_hits = [
        term
        for term in PROVINCE_TERMS
        if normalize_persian(term) in full
    ]

    city_hits = [
        term
        for term in CITY_TERMS
        if normalize_persian(term) in full
    ]

    geography_hits = [
        term
        for term in LOCAL_GEOGRAPHY_TERMS
        if normalize_persian(term) in full
    ]

    culture_hits = [
        term
        for term in LOCAL_CULTURE_TERMS
        if normalize_persian(term) in full
    ]

    subject_hits = [
        term
        for term in LOCAL_SUBJECT_TERMS
        if normalize_persian(term) in full
    ]

    return {
        "province": province_hits,
        "city": city_hits,
        "geography": geography_hits,
        "culture": culture_hits,
        "subject": subject_hits,
    }


# ============================================================
# STRICT LOCAL FILTER
# ============================================================

def local_score(
    title,
    summary,
):

    title_n = normalize_persian(title)
    summary_n = normalize_persian(summary)

    full = (
        title_n
        + " "
        + summary_n
    )

    evidence = get_local_evidence(
        title,
        summary,
    )

    score = 0

    # --------------------------------------------------------
    # DIRECT PROVINCE
    # --------------------------------------------------------

    if evidence["province"]:
        score += 50

        if any(
            normalize_persian(term)
            in title_n
            for term in PROVINCE_TERMS
        ):
            score += 30

    # --------------------------------------------------------
    # CITY
    # --------------------------------------------------------

    city_title_hits = [
        term
        for term in CITY_TERMS
        if normalize_persian(term)
        in title_n
    ]

    if city_title_hits:
        score += 25

    elif evidence["city"]:
        score += 12

    # --------------------------------------------------------
    # SPECIAL GEOGRAPHY
    # --------------------------------------------------------

    if evidence["geography"]:

        score += 35

        if any(
            normalize_persian(term)
            in title_n
            for term in LOCAL_GEOGRAPHY_TERMS
        ):
            score += 15

    # --------------------------------------------------------
    # CULTURE / ART / MUSIC
    # --------------------------------------------------------

    if evidence["culture"]:

        score += 35

        # اگر همزمان مکان محلی هم وجود داشته باشد
        if (
            evidence["province"]
            or evidence["city"]
            or evidence["geography"]
        ):
            score += 20

    # --------------------------------------------------------
    # LOCAL SUBJECT
    # --------------------------------------------------------

    if evidence["subject"]:

        score += min(
            len(evidence["subject"]) * 5,
            25,
        )

    # --------------------------------------------------------
    # OTHER PROVINCE
    # --------------------------------------------------------

    if other_province_in_title(title):
        score -= 100

    # --------------------------------------------------------
    # FOREIGN TITLE
    # --------------------------------------------------------

    if foreign_location_in_title(title):

        # فقط در صورتی اجازه بده که خود عنوان
        # ارتباط روشن با سیستان و بلوچستان داشته باشد.
        if not (
            contains_any(
                title_n,
                [
                    "سیستان",
                    "بلوچستان",
                    "چابهار",
                    "مکران",
                    "هیرمند",
                    "هامون",
                    "جازموریان",
                ],
            )
        ):
            score -= 100

    # --------------------------------------------------------
    # GENERIC UNRELATED TOPICS
    # --------------------------------------------------------

    for term in UNRELATED_TERMS:

        if normalize_persian(term) in full:
            score -= 80

    return score


def is_real_local_news(
    title,
    summary,
):

    title_n = normalize_persian(title)
    summary_n = normalize_persian(summary)

    full = (
        title_n
        + " "
        + summary_n
    )

    evidence = get_local_evidence(
        title,
        summary,
    )

    # ========================================================
    # HARD REJECT: OTHER PROVINCE IN TITLE
    # ========================================================

    if other_province_in_title(title):
        return False

    # ========================================================
    # HARD REJECT: GENERIC NATIONAL SPORTS ETC.
    # ========================================================

    for term in UNRELATED_TERMS:

        if normalize_persian(term) in full:
            return False

    # ========================================================
    # HARD REJECT: FOREIGN ARTICLE
    # ========================================================

    if foreign_location_in_title(title):

        # فقط اگر ارتباط مستقیم و واضح با استان باشد
        local_anchor = (
            evidence["province"]
            or evidence["geography"]
            or any(
                normalize_persian(x)
                in title_n
                for x in [
                    "بلوچستان",
                    "سیستان",
                    "چابهار",
                    "مکران",
                    "هیرمند",
                    "هامون",
                    "جازموریان",
                ]
            )
        )

        if not local_anchor:
            return False

    # ========================================================
    # MUST HAVE STRONG LOCAL ANCHOR
    # ========================================================

    has_province = bool(
        evidence["province"]
    )

    has_city = bool(
        evidence["city"]
    )

    has_geography = bool(
        evidence["geography"]
    )

    has_culture = bool(
        evidence["culture"]
    )

    # ========================================================
    # CULTURE / MUSIC / ART
    # ========================================================

    if has_culture:

        # فرهنگ و هنر باید همراه با نشانه محلی باشد.
        if (
            has_province
            or has_city
            or has_geography
        ):
            return True

        return False

    # ========================================================
    # HAMUN / HIRMAND / JAZMURIAN / MAKRAN / OMAN
    # ========================================================

    if has_geography:

        # این موارد ذاتاً محلی هستند،
        # اما خبر باید درباره خود موضوع باشد.
        return True

    # ========================================================
    # PROVINCE EXPLICIT
    # ========================================================

    if has_province:

        score = local_score(
            title,
            summary,
        )

        return score >= 50

    # ========================================================
    # CITY ONLY
    # ========================================================

    if has_city:

        # نام شهر به تنهایی کافی نیست.
        subject_count = count_terms(
            full,
            LOCAL_SUBJECT_TERMS,
        )

        culture_count = count_terms(
            full,
            LOCAL_CULTURE_TERMS,
        )

        if (
            subject_count >= 1
            or culture_count >= 1
        ):
            return (
                local_score(
                    title,
                    summary,
                )
                >= 30
            )

        return False

    return False


# ============================================================
# ARTICLE DUPLICATION
# ============================================================

def token_set(text):

    normalized = normalize_persian(text)

    return set(
        word
        for word in normalized.split()
        if len(word) > 2
    )


def title_similarity(
    title_a,
    title_b,
):

    a = token_set(title_a)
    b = token_set(title_b)

    if not a or not b:
        return 0.0

    intersection = len(
        a.intersection(b)
    )

    union = len(
        a.union(b)
    )

    if union == 0:
        return 0.0

    return intersection / union


def is_duplicate_title(
    title,
    sent_titles,
):

    current = token_set(title)

    if not current:
        return False

    for stored_hash in sent_titles:

        # hash به تنهایی امکان similarity ندارد.
        # similarity با عنوان‌های همین اجرای فعلی
        # پایین‌تر انجام می‌شود.
        if title_hash(title) == stored_hash:
            return True

    return False


# ============================================================
# RSS
# ============================================================

def fetch_feed(url):

    try:

        response = SESSION.get(
            url,
            timeout=20,
        )

        response.raise_for_status()

        return feedparser.parse(
            response.content
        )

    except Exception as exc:

        print(
            f"RSS feed error: {exc}"
        )

        return None


def collect_source(
    source_name,
    source_domain,
    feed_urls,
):

    items = []

    for feed_url in feed_urls:

        print(
            f"{source_name} RSS: "
            f"{feed_url}"
        )

        feed = fetch_feed(
            feed_url
        )

        if not feed:
            continue

        print(
            f"{source_name}: "
            f"{len(feed.entries)} entries"
        )

        for entry in feed.entries:

            title = clean_text(
                getattr(
                    entry,
                    "title",
                    "",
                )
            )

            link = normalize_url(
                getattr(
                    entry,
                    "link",
                    "",
                )
            )

            if not title or not link:
                continue

            if not is_allowed_source_url(
                link,
                source_domain,
            ):
                continue

            published = parse_date(
                entry
            )

            # خبر بدون تاریخ قابل اعتماد
            # وارد صف انتشار نمی‌شود.
            if published is None:
                continue

            summary = make_summary(
                entry
            )

            items.append({
                "title": title,
                "summary": summary,
                "link": link,
                "published": published,
                "source": source_name,
                "source_domain": source_domain,
            })

    return items


def collect_all_news():

    now = datetime.now(
        timezone.utc
    )

    max_age = timedelta(
        hours=MAX_NEWS_AGE_HOURS
    )

    collected = []

    for (
        source_name,
        source_domain,
        feeds,
    ) in SOURCES:

        source_news = collect_source(
            source_name,
            source_domain,
            feeds,
        )

        for item in source_news:

            age = (
                now
                - item["published"]
            )

            if age < timedelta(0):
                continue

            if age > max_age:
                continue

            collected.append(item)

    # --------------------------------------------------------
    # URL DEDUP
    # --------------------------------------------------------

    unique = {}

    for item in collected:

        link = item["link"]

        if link not in unique:
            unique[link] = item

    return list(
        unique.values()
    )


# ============================================================
# SELECT ONE LOCAL NEWS
# ============================================================

def select_local_news(
    news,
    sent_links,
    sent_titles,
):

    candidates = []

    # عنوان‌هایی که در همین اجرای فعلی دیده‌ایم
    current_titles = []

    for item in news:

        link = item["link"]
        title = item["title"]

        # ----------------------------------------------------
        # URL DUPLICATE
        # ----------------------------------------------------

        if link in sent_links:
            continue

        # ----------------------------------------------------
        # HASH DUPLICATE
        # ----------------------------------------------------

        if is_duplicate_title(
            title,
            sent_titles,
        ):
            continue

        # ----------------------------------------------------
        # LOCAL FILTER
        # ----------------------------------------------------

        if not is_real_local_news(
            title,
            item["summary"],
        ):
            continue

        # ----------------------------------------------------
        # SIMILARITY WITH ALREADY SENT TITLES
        # We only have hashes persisted, so exact hash
        # is checked here. Similarity is also applied
        # between candidates from different sources.
        # ----------------------------------------------------

        duplicate_candidate = False

        for previous_title in current_titles:

            similarity = title_similarity(
                title,
                previous_title,
            )

            if similarity >= 0.72:

                duplicate_candidate = True
                break

        if duplicate_candidate:
            continue

        current_titles.append(
            title
        )

        score = local_score(
            title,
            item["summary"],
        )

        candidate = dict(item)

        candidate["score"] = score

        candidates.append(
            candidate
        )

    # --------------------------------------------------------
    # NEWEST + STRONGEST
    # --------------------------------------------------------

    candidates.sort(
        key=lambda x: (
            x["score"],
            x["published"],
        ),
        reverse=True,
    )

    if candidates:
        return candidates[0]

    return None


# ============================================================
# IMAGE
# ============================================================

def get_image_from_article(url):

    try:

        response = SESSION.get(
            url,
            timeout=10,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        image = soup.find(
            "meta",
            property="og:image",
        )

        if (
            image
            and image.get("content")
        ):

            return image[
                "content"
            ].strip()

        image = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            },
        )

        if (
            image
            and image.get("content")
        ):

            return image[
                "content"
            ].strip()

    except Exception as exc:

        print(
            f"Image lookup failed: "
            f"{exc}"
        )

    return None


# ============================================================
# BALE API
# ============================================================

def bale_request(
    method,
    data=None,
    files=None,
):

    url = (
        "https://tapi.bale.ai/"
        f"bot{BOT_TOKEN}/{method}"
    )

    response = SESSION.post(
        url,
        data=data,
        files=files,
        timeout=30,
    )

    try:

        result = response.json()

    except Exception:

        result = {
            "ok": False,
            "description": response.text,
        }

    if (
        not response.ok
        or not result.get(
            "ok",
            False,
        )
    ):

        raise RuntimeError(
            f"Bale API error: "
            f"{result}"
        )

    return result


# ============================================================
# CHANNEL LINKS
# ============================================================

TELEGRAM_URL = (
    "https://t.me/jahantab_news"
)

BALE_URL = (
    "https://ble.ir/jahantabnews"
)

SOROUSH_URL = (
    "https://splus.ir/jahantabnews"
)


# ============================================================
# MESSAGE
# ============================================================

def build_message(item):

    category = item.get(
        "category",
        "استان سیستان و بلوچستان",
    )

    text = (
        f"🚨 {category}\n\n"
        f"📰 {item['title']}\n\n"
    )

    if item["summary"]:

        text += (
            item["summary"]
            + "\n\n"
        )

    text += (
        f"🗞 منبع: "
        f"{item['source']}"
    )

    text += (
        "\n\n"
        "📱 جهان‌تاب"
    )

    return text


# ============================================================
# INLINE KEYBOARD
# ============================================================

def build_reply_markup(
    article_url,
):

    return json.dumps(
        {
            "inline_keyboard": [

                [
                    {
                        "text": "🔗 مشاهده خبر",
                        "url": article_url,
                    }
                ],

                [
                    {
                        "text": "📨 تلگرام",
                        "url": TELEGRAM_URL,
                    },

                    {
                        "text": "🟦 بله",
                        "url": BALE_URL,
                    },

                    {
                        "text": "🟠 سروش",
                        "url": SOROUSH_URL,
                    },
                ],
            ]
        },
        ensure_ascii=False,
    )


# ============================================================
# SEND TEXT
# ============================================================

def send_text(item):

    reply_markup = build_reply_markup(
        item["link"]
    )

    return bale_request(
        "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": build_message(item),
            "reply_markup": reply_markup,
        },
    )


# ============================================================
# SEND PHOTO
# ============================================================

def send_photo(
    item,
    image_url,
):

    try:

        response = SESSION.get(
            image_url,
            timeout=15,
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            "",
        )

        if not content_type.startswith(
            "image/"
        ):

            raise RuntimeError(
                "URL did not return image"
            )

        extension = ".jpg"

        if "png" in content_type:
            extension = ".png"

        elif "webp" in content_type:
            extension = ".webp"

        files = {
            "photo": (
                f"news{extension}",
                response.content,
                content_type,
            )
        }

        reply_markup = build_reply_markup(
            item["link"]
        )

        caption = build_message(
            item
        )

        # محدودیت کپشن بله
        caption = caption[:1000]

        return bale_request(
            "sendPhoto",
            data={
                "chat_id": CHAT_ID,
                "caption": caption,
                "reply_markup": reply_markup,
            },
            files=files,
        )

    except Exception as exc:

        print(
            f"Photo send failed: "
            f"{exc}"
        )

        return send_text(item)


# ============================================================
# PUBLISH
# ============================================================

def publish_item(item):

    image_url = get_image_from_article(
        item["link"]
    )

    if image_url:

        return send_photo(
            item,
            image_url,
        )

    return send_text(item)


# ============================================================
# PUBLISH ONE NEWS
# ============================================================

def publish_one_news():

    print()
    print(
        "-----------------------------------"
    )

    print(
        "Scanning approved Iranian sources..."
    )

    sent_links = load_sent_links()
    sent_titles = load_sent_titles()

    all_news = collect_all_news()

    print(
        f"Collected fresh news: "
        f"{len(all_news)}"
    )

    # --------------------------------------------------------
    # SELECT ONLY ONE
    # --------------------------------------------------------

    selected = select_local_news(
        all_news,
        sent_links,
        sent_titles,
    )

    if not selected:

        print(
            "No suitable new local news found."
        )

        print(
            "Nothing published this cycle."
        )

        print(
            "-----------------------------------"
        )

        return False

    selected["category"] = (
        "استان سیستان و بلوچستان"
    )

    print(
        "SELECTED:"
    )

    print(
        f"[{selected['source']}] "
        f"{selected['title']}"
    )

    print(
        f"Score: "
        f"{selected['score']}"
    )

    # --------------------------------------------------------
    # PUBLISH
    # --------------------------------------------------------

    try:

        publish_item(
            selected
        )

        # ----------------------------------------------------
        # VERY IMPORTANT:
        # Only after successful Bale publication,
        # save URL + title fingerprint.
        # ----------------------------------------------------

        save_sent_link(
            selected["link"]
        )

        save_sent_title(
            selected["title"]
        )

        print(
            "Published successfully."
        )

        print(
            "Saved to anti-duplicate state."
        )

        print(
            "-----------------------------------"
        )

        return True

    except Exception as exc:

        print(
            f"Publish failed: {exc}"
        )

        print(
            "IMPORTANT: "
            "News was NOT saved as sent."
        )

        print(
            "-----------------------------------"
        )

        return False


# ============================================================
# MAIN LOOP
# ============================================================

def main():

    print()
    print(
        "=========================================="
    )

    print(
        "        JAHANTAB NEWS BOT v6.0"
    )

    print(
        "        جهان‌تاب"
    )

    print(
        "آخرین تحولات سیستان و بلوچستان"
    )

    print(
        "=========================================="
    )

    print(
        "Mode: ONE NEWS EVERY 30 MINUTES"
    )

    print(
        "Local focus: Sistan & Baluchestan"
    )

    print(
        "Sources: Approved Iranian news sources"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # FIRST RUN
    # --------------------------------------------------------

    publish_one_news()

    # --------------------------------------------------------
    # CONTINUOUS 30-MINUTE LOOP
    # --------------------------------------------------------

    while True:

        next_time = (
            datetime.now()
            + timedelta(
                seconds=PUBLISH_INTERVAL
            )
        )

        print()
        print(
            "Next scan at: "
            + next_time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        print(
            "Waiting 30 minutes..."
        )

        try:

            time.sleep(
                PUBLISH_INTERVAL
            )

        except KeyboardInterrupt:

            print()
            print(
                "Bot stopped by user."
            )

            break

        # ----------------------------------------------------
        # NEXT CYCLE
        # ----------------------------------------------------

        try:

            publish_one_news()

        except Exception as exc:

            print(
                "Cycle error:"
            )

            print(exc)

            print(
                "Bot will continue."
            )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()