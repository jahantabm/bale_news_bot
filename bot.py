# -*- coding: utf-8 -*-

"""
============================================================
JAHANTAB | جهان‌تاب
آخرین تحولات سیستان و بلوچستان
============================================================

ویژگی‌های این نسخه:

✓ فقط منابع داخلی و رسانه‌های ایرانی مورد تأیید
✓ تمرکز تخصصی روی سیستان و بلوچستان
✓ شهرها و شهرستان‌های استان
✓ فرهنگ، هنر و موسیقی سیستان و بلوچستان
✓ هامون، هیرمند، جازموریان، مکران و دریای عمان
✓ اخبار اقتصادی، اجتماعی، سیاسی، امنیتی، عمرانی و محیط زیست استان
✓ حذف اخبار سایر استان‌ها
✓ حذف اخبار خارجی
✓ حذف اخبار ورزشی سراسری
✓ حذف اخبار عمومی کشور که ارتباط واقعی با استان ندارند
✓ تشخیص خبر تکراری بین خبرگزاری‌های مختلف
✓ حداکثر یک خبر در هر ۳۰ دقیقه
✓ جلوگیری از اجرای هم‌زمان
✓ جلوگیری از ارسال مجدد خبر پس از Restart
✓ دکمه «مشاهده خبر»
✓ لینک تلگرام، بله و سروش داخل Inline Keyboard
✓ ارسال تصویر در صورت وجود og:image
✓ اگر تصویر مشکل داشته باشد، خبر به‌صورت متنی ارسال می‌شود

============================================================
"""

import os
import re
import json
import html
import time
import hashlib
import difflib
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
PUBLISHED_STATE_FILE = "published_state.json"
LOCK_FILE = "jahantab.lock"

# حداقل فاصله بین دو انتشار
PUBLISH_INTERVAL_MINUTES = 30

# حداکثر عمر خبر
MAX_NEWS_AGE_HOURS = 24

# تعداد خبرهایی که از RSS بررسی می‌شود
MAX_CANDIDATES = 1000


if not BOT_TOKEN:
    raise RuntimeError("BALE_BOT_TOKEN is not set")

if not CHAT_ID:
    raise RuntimeError("BALE_CHAT_ID is not set")


# ============================================================
# APPROVED IRANIAN SOURCES
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
    "استان سیستان و بلوچستان",
    "استان سیستان‌ و بلوچستان",
    "استان سیستان‌وبلوچستان",
]


# ============================================================
# CITIES / COUNTIES
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
    "ادیمی",
    "محمدان",
    "بزمان",
    "نوک‌آباد",
    "راسک",
    "پارود",
    "زرآباد",
    "لاشار",
    "آهوران",
    "کورین",
    "نصرت‌آباد",
    "میرجاوه",
    "اسپکه",
]


# ============================================================
# SPECIAL NATURAL / GEOGRAPHICAL SUBJECTS
# ============================================================

SPECIAL_LOCAL_TERMS = [

    # هامون
    "هامون",
    "تالاب هامون",
    "تالاب بین‌المللی هامون",

    # هیرمند
    "هیرمند",
    "رودخانه هیرمند",
    "رود هیرمند",
    "حقابه هیرمند",
    "حقابه ایران",
    "آب هیرمند",

    # جازموریان
    "جازموریان",
    "تالاب جازموریان",

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
    "چابهار",
]


# ============================================================
# CULTURE / ART / MUSIC
# ============================================================

CULTURE_TERMS = [

    "فرهنگ سیستان و بلوچستان",
    "فرهنگ سیستان",
    "فرهنگ بلوچستان",
    "هنر سیستان و بلوچستان",
    "هنر سیستان",
    "هنر بلوچستان",

    "موسیقی سیستان و بلوچستان",
    "موسیقی سیستان",
    "موسیقی بلوچستان",
    "موسیقی بلوچی",
    "موسیقی محلی سیستان",
    "موسیقی محلی بلوچستان",

    "هنرمندان سیستان و بلوچستان",
    "هنرمندان بلوچستان",
    "هنرمند سیستانی",
    "هنرمند بلوچ",

    "فرهنگ بلوچ",
    "فرهنگ بلوچی",
    "میراث فرهنگی",
    "میراث فرهنگی سیستان و بلوچستان",
    "صنایع دستی",
    "صنایع دستی سیستان و بلوچستان",
    "سفال کلپورگان",
    "کلپورگان",
    "سوزن‌دوزی بلوچ",
    "سوزن دوزی بلوچ",
    "لباس بلوچی",
    "لباس محلی بلوچستان",
    "رقص محلی بلوچستان",
    "موسیقی مقامی",

    "جشنواره فرهنگی",
    "جشنواره هنری",
    "نمایشگاه هنری",
    "رویداد فرهنگی",
    "آیین‌های سنتی",
    "آیین سنتی",
    "ادبیات بلوچستان",
    "شعر بلوچی",
    "شاعر بلوچ",
]


# ============================================================
# REAL LOCAL CONTEXT
# ============================================================

LOCAL_CONTEXT_TERMS = [

    # مدیریت استان
    "استاندار",
    "استانداری",
    "معاون استاندار",
    "فرماندار",
    "فرمانداری",
    "نماینده ولی فقیه",
    "مجمع نمایندگان",
    "نماینده مردم",

    # انتظامی / امنیتی
    "حادثه",
    "تصادف",
    "آتش‌سوزی",
    "آتش سوزی",
    "زلزله",
    "سیل",
    "طوفان",
    "بارندگی",
    "کشف",
    "قاچاق",
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
    "نیروهای امنیتی",
    "نیروهای نظامی",
    "مرزبانی",
    "مرزبان",

    # توسعه
    "افتتاح",
    "بهره‌برداری",
    "بهره برداری",
    "پروژه",
    "طرح",
    "ساخت",
    "توسعه",
    "اعتبار",
    "سرمایه‌گذاری",
    "سرمایه گذاری",
    "زیرساخت",
    "راه",
    "جاده",
    "بندر",
    "بیمارستان",
    "مدرسه",
    "دانشگاه",
    "فرودگاه",
    "راه‌آهن",
    "راه آهن",

    # آب / کشاورزی
    "آب",
    "آبرسانی",
    "برق",
    "گاز",
    "کشاورزی",
    "دامداری",
    "صیادی",
    "ماهیگیری",
    "شیلات",
    "محیط زیست",
    "خشکسالی",
    "تنش آبی",

    # اقتصاد / تجارت
    "اقتصاد",
    "اشتغال",
    "بازار",
    "تجارت",
    "صادرات",
    "واردات",
    "مرز",
    "مرز رسمی",
    "بازرگانی",
    "منطقه آزاد",

    # مکران
    "کشتیرانی",
    "بندر",
    "پتروشیمی",
    "سواحل",
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

    # کشورها / مناطق پرتکرار
    "سوریه",
    "ترکیه",
    "پاکستان",
    "هند",
    "عراق",
    "افغانستان",
    "لبنان",
    "یمن",
    "عربستان",
    "امارات",
    "قطر",
    "کویت",
    "بحرین",
    "اردن",
    "مصر",
    "لیبی",
    "تونس",
    "الجزایر",
    "مراکش",

    "آمریکا",
    "ایالات متحده",
    "انگلیس",
    "بریتانیا",
    "فرانسه",
    "آلمان",
    "ایتالیا",
    "اسپانیا",
    "روسیه",
    "اوکراین",
    "چین",
    "ژاپن",
    "کره جنوبی",
    "کره شمالی",

    # مناطق پرتکرار
    "غزه",
    "کرانه باختری",
    "رمالله",
    "تل‌آویو",
    "قدس",
    "استانبول",
    "آنکارا",
    "دمشق",
    "حلب",
    "رقه",
    "اسلام‌آباد",
    "کابل",
    "دهلی",
    "لندن",
    "پاریس",
    "برلین",
    "مسکو",
    "کی‌یف",
]


# ============================================================
# NATIONAL / GENERAL SUBJECTS TO REJECT
# ============================================================

GENERAL_EXCLUDE_TERMS = [

    # ورزش سراسری
    "سردار آزمون",
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
    "ورزش",

    # سرگرمی عمومی
    "سلبریتی",
    "آگاتا کریستی",
    "خانم مارپل",
    "مارپل",

    # موضوعات عمومی
    "فال",
    "مد",
    "زیبایی",
    "سبک زندگی",

    # خبرهای کاملاً خارجی
    "وزارت دفاع سوریه",
    "رئیس جمهور ترکیه",
    "رئیس‌جمهور ترکیه",
    "نخست وزیر ترکیه",
    "نخست‌وزیر ترکیه",
    "ارتش سوریه",
]


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


def normalize_persian_text(text):

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
        "‌": "",
        "\u200c": "",
        "\u200e": "",
        "\u200f": "",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(
        r"[ًٌٍَُِّْـ]",
        "",
        text,
    )

    return text.strip()


def normalize_title(text):

    text = normalize_persian_text(text)

    # حذف کلمات کم‌اهمیت برای تشخیص تکراری
    remove_words = [
        "خبر",
        "گزارش",
        "اعلام",
        "آخرین",
        "واکنش",
        "جزئیات",
        "مهم",
        "جدید",
        "در",
        "از",
        "به",
        "یک",
        "این",
        "آن",
    ]

    for word in remove_words:
        text = re.sub(
            rf"\b{re.escape(word)}\b",
            " ",
            text,
        )

    text = re.sub(
        r"[^\w\u0600-\u06FF\s]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip().lower()


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
    )

    return url.rstrip("?&")


def get_domain(url):

    try:

        domain = urlparse(url).hostname or ""

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
# FILE LOCK
# ============================================================

def acquire_lock():

    try:

        fd = os.open(
            LOCK_FILE,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY,
        )

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                {
                    "pid": os.getpid(),
                    "time": time.time(),
                },
                file,
            )

        return True

    except FileExistsError:

        try:

            with open(
                LOCK_FILE,
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(file)

            lock_time = float(
                data.get("time", 0)
            )

            # اگر lock بیشتر از 10 دقیقه مانده
            # احتمالاً اجرای قبلی مرده است.
            if (
                time.time() - lock_time
                > 600
            ):

                os.remove(
                    LOCK_FILE
                )

                return acquire_lock()

        except Exception:
            pass

        return False


def release_lock():

    try:

        if os.path.exists(
            LOCK_FILE
        ):
            os.remove(
                LOCK_FILE
            )

    except Exception:
        pass


# ============================================================
# SENT LINKS
# ============================================================

def load_sent_links():

    if not os.path.exists(
        STATE_FILE
    ):
        return set()

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            return {
                line.strip()
                for line in file
                if line.strip()
            }

    except Exception:
        return set()


def save_sent_link(link):

    with open(
        STATE_FILE,
        "a",
        encoding="utf-8",
    ) as file:

        file.write(
            link + "\n"
        )


# ============================================================
# PUBLISH STATE
# ============================================================

def load_publish_state():

    if not os.path.exists(
        PUBLISHED_STATE_FILE
    ):
        return {
            "last_publish": 0,
        }

    try:

        with open(
            PUBLISHED_STATE_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        return data

    except Exception:

        return {
            "last_publish": 0,
        }


def save_publish_state():

    with open(
        PUBLISHED_STATE_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            {
                "last_publish": time.time(),
            },
            file,
            ensure_ascii=False,
            indent=2,
        )


def can_publish():

    state = load_publish_state()

    last_publish = float(
        state.get(
            "last_publish",
            0,
        )
    )

    elapsed = (
        time.time()
        - last_publish
    )

    required = (
        PUBLISH_INTERVAL_MINUTES
        * 60
    )

    if elapsed < required:

        remaining = int(
            required - elapsed
        )

        print(
            "30-minute cooldown active. "
            f"Remaining: {remaining} seconds"
        )

        return False

    return True


# ============================================================
# DATE
# ============================================================

def parse_date(entry):

    try:

        import calendar

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

    # مهم:
    # اگر تاریخ واقعی وجود نداشت، خبر را
    # به عنوان خبر جدید در نظر نمی‌گیریم.
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

    if len(text) > 500:

        text = (
            text[:497]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return text


# ============================================================
# LOCATION CHECKS
# ============================================================

def has_any(text, terms):

    text = normalize_persian_text(
        text
    )

    return any(
        normalize_persian_text(term)
        in text
        for term in terms
    )


def other_province_in_title(title):

    title = normalize_persian_text(
        title
    )

    for province in OTHER_PROVINCE_TERMS:

        if (
            normalize_persian_text(
                province
            )
            in title
        ):
            return True

    return False


def foreign_location_in_title(title):

    title = normalize_persian_text(
        title
    )

    for term in FOREIGN_LOCATION_TERMS:

        if (
            normalize_persian_text(term)
            in title
        ):
            return True

    return False


# ============================================================
# LOCAL SCORE
# ============================================================

def local_score(
    title,
    summary,
):

    title = normalize_persian_text(
        title
    )

    summary = normalize_persian_text(
        summary
    )

    full_text = (
        title
        + " "
        + summary
    )

    score = 0

    # --------------------------------------------------------
    # OTHER PROVINCE
    # --------------------------------------------------------

    if other_province_in_title(
        title
    ):
        score -= 100

    # --------------------------------------------------------
    # FOREIGN
    # --------------------------------------------------------

    if foreign_location_in_title(
        title
    ):
        score -= 100

    # --------------------------------------------------------
    # PROVINCE
    # --------------------------------------------------------

    for term in PROVINCE_TERMS:

        term = normalize_persian_text(
            term
        )

        if term in title:
            score += 40

        elif term in summary:
            score += 15

    # --------------------------------------------------------
    # CITIES
    # --------------------------------------------------------

    for term in CITY_TERMS:

        term = normalize_persian_text(
            term
        )

        if term in title:
            score += 15

        elif term in summary:
            score += 5

    # --------------------------------------------------------
    # SPECIAL NATURAL SUBJECTS
    # --------------------------------------------------------

    for term in SPECIAL_LOCAL_TERMS:

        term = normalize_persian_text(
            term
        )

        if term in title:
            score += 30

        elif term in summary:
            score += 12

    # --------------------------------------------------------
    # CULTURE / ART / MUSIC
    # --------------------------------------------------------

    for term in CULTURE_TERMS:

        term = normalize_persian_text(
            term
        )

        if term in title:
            score += 30

        elif term in summary:
            score += 12

    # --------------------------------------------------------
    # LOCAL CONTEXT
    # --------------------------------------------------------

    context_count = 0

    for term in LOCAL_CONTEXT_TERMS:

        if normalize_persian_text(term) in full_text:
            context_count += 1

    score += min(
        context_count * 5,
        30,
    )

    return score


# ============================================================
# LOCAL NEWS FILTER
# ============================================================

def is_real_local_news(
    title,
    summary,
):

    title = normalize_persian_text(
        title
    )

    summary = normalize_persian_text(
        summary
    )

    full_text = (
        title
        + " "
        + summary
    )

    # --------------------------------------------------------
    # HARD REJECT: OTHER PROVINCE IN TITLE
    # --------------------------------------------------------

    if other_province_in_title(
        title
    ):
        return False

    # --------------------------------------------------------
    # HARD REJECT: FOREIGN LOCATION IN TITLE
    # --------------------------------------------------------

    if foreign_location_in_title(
        title
    ):
        return False

    # --------------------------------------------------------
    # HARD REJECT: GENERAL EXCLUDE
    # --------------------------------------------------------

    for term in GENERAL_EXCLUDE_TERMS:

        if normalize_persian_text(term) in full_text:
            return False

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    has_province = has_any(
        full_text,
        PROVINCE_TERMS,
    )

    has_city = has_any(
        full_text,
        CITY_TERMS,
    )

    has_special = has_any(
        full_text,
        SPECIAL_LOCAL_TERMS,
    )

    has_culture = has_any(
        full_text,
        CULTURE_TERMS,
    )

    # هیچ نشانه‌ای از استان نیست
    if not (
        has_province
        or has_city
        or has_special
        or has_culture
    ):
        return False

    # --------------------------------------------------------
    # STRONG LOCAL EVIDENCE
    # --------------------------------------------------------

    score = local_score(
        title,
        summary,
    )

    # استان در عنوان
    if has_any(
        title,
        PROVINCE_TERMS,
    ):

        return score >= 30

    # موضوعات ویژه در عنوان
    if has_any(
        title,
        SPECIAL_LOCAL_TERMS,
    ):

        return score >= 25

    # فرهنگ / هنر / موسیقی در عنوان
    if has_any(
        title,
        CULTURE_TERMS,
    ):

        return score >= 25

    # شهر در عنوان
    if has_any(
        title,
        CITY_TERMS,
    ):

        # شهر به تنهایی کافی نیست
        context_count = sum(
            1
            for term in LOCAL_CONTEXT_TERMS
            if normalize_persian_text(term)
            in full_text
        )

        if context_count >= 1:
            return score >= 20

        # اگر موضوع ویژه هم وجود دارد
        if has_special or has_culture:
            return score >= 20

        return False

    # اگر فقط در متن اشاره شده
    return score >= 25


# ============================================================
# DUPLICATE DETECTION
# ============================================================

def title_similarity(
    title1,
    title2,
):

    a = normalize_title(
        title1
    )

    b = normalize_title(
        title2
    )

    if not a or not b:
        return 0

    return difflib.SequenceMatcher(
        None,
        a,
        b,
    ).ratio()


def make_event_key(
    title,
):

    normalized = normalize_title(
        title
    )

    return hashlib.sha1(
        normalized.encode(
            "utf-8"
        )
    ).hexdigest()


def is_duplicate_of_selected(
    item,
    selected,
):

    for old in selected:

        similarity = title_similarity(
            item["title"],
            old["title"],
        )

        # عناوین تقریباً یکسان
        if similarity >= 0.72:
            return True

    return False


# ============================================================
# RSS
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; JahantabNewsBot/6.0)"
    )
})


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

            # خبر بدون تاریخ معتبر رد می‌شود
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

            # خبر آینده
            if age < timedelta(0):
                continue

            # خبر قدیمی
            if age > max_age:
                continue

            collected.append(
                item
            )

    # حذف URL تکراری
    unique = {}

    for item in collected:

        link = item["link"]

        if link not in unique:
            unique[link] = item

    return list(
        unique.values()
    )


# ============================================================
# SELECT ONE NEWS
# ============================================================

def select_best_local_news(
    news,
    sent_links,
):

    candidates = []

    # ابتدا جدیدترین‌ها
    news = sorted(
        news,
        key=lambda x: x["published"],
        reverse=True,
    )

    for item in news:

        link = item["link"]

        if link in sent_links:
            continue

        if not is_real_local_news(
            item["title"],
            item["summary"],
        ):
            continue

        item = dict(item)

        item["score"] = local_score(
            item["title"],
            item["summary"],
        )

        candidates.append(
            item
        )

    if not candidates:
        return None

    # امتیاز + تازگی
    candidates.sort(
        key=lambda x: (
            x["score"],
            x["published"],
        ),
        reverse=True,
    )

    # --------------------------------------------------------
    # حذف خبرهای تکراری بین خبرگزاری‌ها
    # --------------------------------------------------------

    selected = []

    for item in candidates:

        if is_duplicate_of_selected(
            item,
            selected,
        ):
            print(
                "Duplicate event rejected: "
                f"{item['title']}"
            )
            continue

        selected.append(
            item
        )

    if not selected:
        return None

    return selected[0]


# ============================================================
# IMAGE
# ============================================================

def get_image_from_article(
    url
):

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
            "Image lookup failed: "
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

    text = (
        "🚨 استان سیستان و بلوچستان\n\n"
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
            "text": build_message(
                item
            ),
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

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
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

        reply_markup = (
            build_reply_markup(
                item["link"]
            )
        )

        caption = build_message(
            item
        )

        # محدودیت کپشن
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
            "Photo send failed: "
            f"{exc}"
        )

        return send_text(
            item
        )


# ============================================================
# PUBLISH
# ============================================================

def publish_item(item):

    image_url = (
        get_image_from_article(
            item["link"]
        )
    )

    if image_url:

        return send_photo(
            item,
            image_url,
        )

    return send_text(
        item
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=========================================="
    )

    print(
        "JAHANTAB | جهان‌تاب"
    )

    print(
        "آخرین تحولات سیستان و بلوچستان"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # LOCK
    # --------------------------------------------------------

    if not acquire_lock():

        print(
            "Another Jahantab process is already running."
        )

        return

    try:

        # ----------------------------------------------------
        # 30 MINUTE COOLDOWN
        # ----------------------------------------------------

        if not can_publish():

            print(
                "No publication this run."
            )

            return

        # ----------------------------------------------------
        # SENT LINKS
        # ----------------------------------------------------

        sent_links = (
            load_sent_links()
        )

        print(
            "Previously sent links: "
            f"{len(sent_links)}"
        )

        # ----------------------------------------------------
        # COLLECT
        # ----------------------------------------------------

        all_news = (
            collect_all_news()
        )

        print(
            "Fresh approved-source news: "
            f"{len(all_news)}"
        )

        # ----------------------------------------------------
        # SELECT ONE
        # ----------------------------------------------------

        selected = (
            select_best_local_news(
                all_news,
                sent_links,
            )
        )

        if not selected:

            print(
                "No valid Sistan & "
                "Baluchestan news found."
            )

            return

        selected["category"] = (
            "استان سیستان و بلوچستان"
        )

        print(
            "------------------------------------------"
        )

        print(
            "SELECTED:"
        )

        print(
            f"[{selected['source']}] "
            f"{selected['title']}"
        )

        print(
            f"Score: {selected['score']}"
        )

        print(
            f"URL: {selected['link']}"
        )

        print(
            "------------------------------------------"
        )

        # ----------------------------------------------------
        # FINAL SAFETY CHECK
        # ----------------------------------------------------

        if not is_real_local_news(
            selected["title"],
            selected["summary"],
        ):

            print(
                "FINAL SAFETY CHECK FAILED."
            )

            return

        # ----------------------------------------------------
        # PUBLISH
        # ----------------------------------------------------

        print(
            "Publishing..."
        )

        publish_item(
            selected
        )

        # ----------------------------------------------------
        # SAVE STATE ONLY AFTER SUCCESS
        # ----------------------------------------------------

        save_sent_link(
            selected["link"]
        )

        save_publish_state()

        print(
            "Published successfully."
        )

        print(
            "Next publication allowed "
            "after 30 minutes."
        )

    finally:

        release_lock()

        print(
            "=========================================="
        )

        print(
            "Jahantab finished."
        )

        print(
            "=========================================="
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()