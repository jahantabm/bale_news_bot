# -*- coding: utf-8 -*-

"""
============================================================
🌐 JAHANTAB | جهان‌تاب
آخرین تحولات سیستان و بلوچستان

نسخه نهایی

ویژگی‌ها:
- فقط منابع خبری داخلی و مورد تأیید
- تمرکز تخصصی روی سیستان و بلوچستان
- فیلتر دقیق محلی
- جلوگیری از ورود اخبار سایر استان‌ها
- پوشش:
    * اخبار سیاسی و مدیریتی استان
    * حوادث و انتظامی
    * اقتصاد و توسعه
    * آب و محیط زیست
    * هامون
    * هیرمند
    * جازموریان
    * مکران
    * دریای عمان
    * چابهار
    * فرهنگ و هنر
    * موسیقی
    * میراث فرهنگی
    * گردشگری
    * ادبیات و رسانه
    * اقوام و آیین‌های محلی
- حذف اخبار ورزشی سراسری
- حذف اخبار هنری غیرمرتبط
- حذف اخبار سایر استان‌ها
- حذف خبرهای تکراری
- جلوگیری از اجرای همزمان دو نسخه بات
- ارسال حداکثر یک خبر در هر ۳۰ دقیقه
- لینک خبر + شبکه‌های اجتماعی داخل Inline Keyboard
- دریافت تصویر خبر در صورت وجود
- نگهداری لینک‌های ارسال‌شده
============================================================
"""

import os
import re
import json
import html
import time
import hashlib
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
LOCK_FILE = "jahantab_bot.lock"

# هر ۳۰ دقیقه
RUN_INTERVAL_SECONDS = 30 * 60

# حداکثر سن خبر
MAX_NEWS_AGE_HOURS = 24

# حداکثر تعداد خبر در هر اجرا
MAX_NEWS_PER_RUN = 1


if not BOT_TOKEN:
    raise RuntimeError("BALE_BOT_TOKEN is not set")

if not CHAT_ID:
    raise RuntimeError("BALE_CHAT_ID is not set")


# ============================================================
# ONLY APPROVED INTERNAL IRANIAN NEWS SOURCES
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
    "سیب‌ و سوران",
    "نیمروز",
    "بنت",
    "پیشین",
    "گشت",
    "تفتان",
    "دُرّی",
    "بمپور",
    "محمدان",
    "راسک",
    "پارود",
    "بخش سرباز",
    "لاشار",
    "آشار",
    "نوک‌آباد",
    "میرجاوه",
    "ریمدان",
    "پسابندر",
    "نگور",
    "زرآباد",
    "بزمان",
]


# ============================================================
# NATURAL / GEOGRAPHICAL AREAS
# ============================================================

GEOGRAPHICAL_TERMS = [

    # هامون
    "هامون",
    "تالاب هامون",
    "دریاچه هامون",

    # هیرمند
    "هیرمند",
    "رودخانه هیرمند",
    "رود هیرمند",

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
    "خلیج چابهار",
    "بندر چابهار",
]


# ============================================================
# CULTURE / ART / MUSIC / HERITAGE
# ============================================================

CULTURE_TERMS = [

    "فرهنگ سیستان و بلوچستان",
    "فرهنگ سیستان",
    "فرهنگ بلوچستان",
    "فرهنگ بلوچ",
    "فرهنگ زابلی",
    "هنر سیستان و بلوچستان",
    "هنرمندان سیستان و بلوچستان",
    "هنرمند سیستان و بلوچستان",

    # موسیقی
    "موسیقی سیستان و بلوچستان",
    "موسیقی بلوچستان",
    "موسیقی سیستان",
    "موسیقی بلوچ",
    "موسیقی محلی سیستان",
    "موسیقی محلی بلوچستان",
    "هنرمند موسیقی بلوچ",
    "خواننده بلوچ",
    "خواننده سیستانی",
    "نوازنده بلوچ",
    "موسیقی محلی",

    # سازها
    "قیچک",
    "رباب",
    "دونلی",
    "دهلک",
    "سرود بلوچی",
    "آواز بلوچی",

    # میراث فرهنگی
    "میراث فرهنگی سیستان",
    "میراث فرهنگی بلوچستان",
    "میراث فرهنگی سیستان و بلوچستان",
    "صنایع دستی سیستان",
    "صنایع دستی بلوچستان",
    "صنایع دستی سیستان و بلوچستان",

    # آیین‌ها
    "آیین بلوچ",
    "آیین‌های بلوچ",
    "آیین سیستانی",
    "آیین‌های سیستان",
    "جشنواره فرهنگی",
    "جشنواره هنری",
    "جشنواره موسیقی",

    # گردشگری
    "گردشگری سیستان و بلوچستان",
    "گردشگری بلوچستان",
    "گردشگری سیستان",
    "جاذبه گردشگری",
    "میراث تاریخی",
    "محوطه تاریخی",
    "باستان‌شناسی",
    "باستان شناسی",
    "شهر سوخته",
    "کوه خواجه",
    "قلعه رستم",
    "قلعه ناصری",
    "چاه‌نیمه",
]


# ============================================================
# LOCAL CONTEXT
# ============================================================

LOCAL_CONTEXT_TERMS = [

    # مدیریت استان
    "استاندار",
    "استانداری",
    "معاون استاندار",
    "فرماندار",
    "فرمانداری",
    "مدیرکل",
    "نماینده ولی فقیه",
    "مجمع نمایندگان",
    "نماینده مردم",
    "نماینده مجلس",

    # امنیت / انتظامی
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
    "امنیتی",
    "نظامی",
    "مرزبانی",
    "مرز",
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

    # اقتصاد
    "اقتصاد",
    "بازرگانی",
    "تجارت",
    "اشتغال",
    "کارآفرینی",
    "صنعت",
    "معدن",
    "بازار",
    "سرمایه‌گذار",

    # آب و کشاورزی
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
    "تالاب",
    "رودخانه",

    # مکران
    "بندر چابهار",
    "منطقه آزاد چابهار",
    "سواحل مکران",
    "ساحل مکران",
    "دریای عمان",
    "کشتیرانی",
]


# ============================================================
# LOCAL CULTURAL CONTEXT
# ============================================================

LOCAL_CULTURAL_CONTEXT = [

    "فرهنگ",
    "هنر",
    "موسیقی",
    "هنرمند",
    "خواننده",
    "نوازنده",
    "جشنواره",
    "نمایشگاه",
    "میراث فرهنگی",
    "صنایع دستی",
    "گردشگری",
    "باستان‌شناسی",
    "باستان شناسی",
    "آیین",
    "سنت",
    "ادبیات",
    "شاعر",
    "شعر",
    "کتاب",
    "موزه",
    "اثر تاریخی",
    "محوطه تاریخی",
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
# NATIONWIDE TOPICS THAT MUST NOT ENTER LOCAL SECTION
# ============================================================

LOCAL_EXCLUDE_TERMS = [

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

    # هنر سراسری
    "آگاتا کریستی",
    "خانم مارپل",
    "مارپل",

    # موضوعات عمومی
    "فال",
    "مد",
    "زیبایی",
    "سبک زندگی",
]


# ============================================================
# NATIONAL EXCEPTION
# ============================================================

MAJOR_NATIONAL_TERMS = [

    "حمله آمریکا به ایران",
    "حمله ایالات متحده به ایران",
    "حمله اسرائیل به ایران",
    "حمله رژیم صهیونیستی به ایران",
    "جنگ ایران و آمریکا",
    "جنگ ایران و اسرائیل",
    "درگیری مستقیم ایران و آمریکا",
    "درگیری مستقیم ایران و اسرائیل",
    "آغاز جنگ",
    "آغاز حمله نظامی",
    "حمله گسترده به ایران",
    "حمله موشکی گسترده به ایران",
    "حمله هوایی گسترده به ایران",
    "حمله پهپادی گسترده به ایران",
    "عملیات نظامی گسترده علیه ایران",
    "بسته شدن تنگه هرمز",
    "تعطیلی سراسری کشور",
    "زلزله بسیار بزرگ",
    "سیل گسترده در کشور",
    "بحران ملی",
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
# TEXT HELPERS
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
        "‌": " ",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def title_key(title):

    text = normalize_persian_text(
        title
    )

    # حذف علائم
    text = re.sub(
        r"[^\w\u0600-\u06FF]+",
        "",
        text,
    )

    return text.lower()


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
# LOCK
# ============================================================

def acquire_lock():

    try:

        if os.path.exists(
            LOCK_FILE
        ):

            try:

                with open(
                    LOCK_FILE,
                    "r",
                    encoding="utf-8",
                ) as file:

                    old_pid = (
                        file.read()
                        .strip()
                    )

                print(
                    "Another Jahantab "
                    "instance is already "
                    f"running. PID: {old_pid}"
                )

            except Exception:

                print(
                    "Another Jahantab "
                    "instance appears "
                    "to be running."
                )

            return False

        with open(
            LOCK_FILE,
            "w",
            encoding="utf-8",
        ) as file:

            file.write(
                str(os.getpid())
            )

        return True

    except Exception as exc:

        print(
            f"Lock creation failed: {exc}"
        )

        return False


def release_lock():

    try:

        if os.path.exists(
            LOCK_FILE
        ):

            os.remove(
                LOCK_FILE
            )

    except Exception as exc:

        print(
            f"Lock release failed: {exc}"
        )


# ============================================================
# SENT STATE
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

    try:

        with open(
            STATE_FILE,
            "a",
            encoding="utf-8",
        ) as file:

            file.write(
                link + "\n"
            )

    except Exception as exc:

        print(
            f"Could not save link: {exc}"
        )


def load_sent_titles():

    if not os.path.exists(
        TITLE_STATE_FILE
    ):
        return set()

    try:

        with open(
            TITLE_STATE_FILE,
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


def save_sent_title(title):

    key = title_key(title)

    if not key:
        return

    try:

        with open(
            TITLE_STATE_FILE,
            "a",
            encoding="utf-8",
        ) as file:

            file.write(
                key + "\n"
            )

    except Exception as exc:

        print(
            f"Could not save title: {exc}"
        )


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

            timestamp = (
                calendar.timegm(
                    entry.published_parsed
                )
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

            timestamp = (
                calendar.timegm(
                    entry.updated_parsed
                )
            )

            return datetime.fromtimestamp(
                timestamp,
                timezone.utc,
            )

    except Exception:
        pass

    return datetime.now(
        timezone.utc
    )


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

    if (
        not text
        and getattr(
            entry,
            "description",
            None,
        )
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


def has_other_province_in_title(
    title,
):

    title = normalize_persian_text(
        title
    )

    for province in OTHER_PROVINCE_TERMS:

        if province in title:
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
    # OTHER PROVINCE IN TITLE
    # --------------------------------------------------------

    if has_other_province_in_title(
        title
    ):

        score -= 150

    # --------------------------------------------------------
    # PROVINCE
    # --------------------------------------------------------

    for term in PROVINCE_TERMS:

        if term in title:
            score += 35

        elif term in summary:
            score += 12

    # --------------------------------------------------------
    # CITY
    # --------------------------------------------------------

    city_in_title = False

    for term in CITY_TERMS:

        if term in title:

            score += 10

            city_in_title = True

        elif term in summary:

            score += 4

    # --------------------------------------------------------
    # GEOGRAPHICAL AREAS
    # --------------------------------------------------------

    for term in GEOGRAPHICAL_TERMS:

        if term in title:

            score += 25

        elif term in summary:

            score += 10

    # --------------------------------------------------------
    # CULTURE / ART
    # --------------------------------------------------------

    culture_count = count_terms(
        full_text,
        CULTURE_TERMS,
    )

    if culture_count:

        score += min(
            culture_count * 10,
            30,
        )

    # --------------------------------------------------------
    # LOCAL CONTEXT
    # --------------------------------------------------------

    context_count = count_terms(
        full_text,
        LOCAL_CONTEXT_TERMS,
    )

    score += min(
        context_count * 5,
        30,
    )

    # --------------------------------------------------------
    # CULTURAL CONTEXT
    # --------------------------------------------------------

    cultural_context_count = count_terms(
        full_text,
        LOCAL_CULTURAL_CONTEXT,
    )

    score += min(
        cultural_context_count * 6,
        24,
    )

    # --------------------------------------------------------
    # NATIONAL SPORTS / UNRELATED
    # --------------------------------------------------------

    for term in LOCAL_EXCLUDE_TERMS:

        if term in full_text:
            score -= 70

    # --------------------------------------------------------
    # CITY WITHOUT LOCAL CONTEXT
    # --------------------------------------------------------

    if (
        city_in_title
        and context_count == 0
        and cultural_context_count == 0
    ):

        score -= 30

    return score


# ============================================================
# REAL LOCAL NEWS
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
    # OTHER PROVINCE IN TITLE
    # --------------------------------------------------------

    if has_other_province_in_title(
        title
    ):

        return False

    # --------------------------------------------------------
    # UNRELATED TOPICS
    # --------------------------------------------------------

    for term in LOCAL_EXCLUDE_TERMS:

        if term in full_text:

            return False

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    has_province = contains_any(
        full_text,
        PROVINCE_TERMS,
    )

    has_city = contains_any(
        full_text,
        CITY_TERMS,
    )

    has_geography = contains_any(
        full_text,
        GEOGRAPHICAL_TERMS,
    )

    has_culture = contains_any(
        full_text,
        CULTURE_TERMS,
    )

    # --------------------------------------------------------
    # NO LOCAL EVIDENCE
    # --------------------------------------------------------

    if not (
        has_province
        or has_city
        or has_geography
        or has_culture
    ):

        return False

    # --------------------------------------------------------
    # CULTURAL NEWS
    # --------------------------------------------------------

    if has_culture:

        # فرهنگ/هنر فقط وقتی پذیرفته شود
        # که نشانه‌ای از استان/شهر/منطقه داشته باشد.

        if (
            has_province
            or has_city
            or has_geography
        ):

            return (
                local_score(
                    title,
                    summary,
                )
                >= 15
            )

    # --------------------------------------------------------
    # GEOGRAPHICAL NEWS
    # --------------------------------------------------------

    if has_geography:

        return (
            local_score(
                title,
                summary,
            )
            >= 15
        )

    # --------------------------------------------------------
    # PROVINCE IN TITLE
    # --------------------------------------------------------

    if contains_any(
        title,
        PROVINCE_TERMS,
    ):

        return (
            local_score(
                title,
                summary,
            )
            >= 25
        )

    # --------------------------------------------------------
    # CITY ALONE IS NOT ENOUGH
    # --------------------------------------------------------

    context_count = count_terms(
        full_text,
        LOCAL_CONTEXT_TERMS,
    )

    cultural_context_count = count_terms(
        full_text,
        LOCAL_CULTURAL_CONTEXT,
    )

    if has_city:

        if (
            context_count < 1
            and cultural_context_count < 1
        ):

            return False

    # --------------------------------------------------------
    # FINAL SCORE
    # --------------------------------------------------------

    return (
        local_score(
            title,
            summary,
        )
        >= 15
    )


# ============================================================
# NATIONAL NEWS
# ============================================================

def national_score(
    title,
    summary,
):

    text = (
        normalize_persian_text(title)
        + " "
        + normalize_persian_text(summary)
    )

    score = 0

    for term in MAJOR_NATIONAL_TERMS:

        if term in text:
            score += 10

    return score


def is_exceptional_national_news(
    title,
    summary,
):

    return (
        national_score(
            title,
            summary,
        )
        >= 10
    )


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

            title = normalize_persian_text(
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

            if age < timedelta(0):
                continue

            if age > max_age:
                continue

            collected.append(item)

    # --------------------------------------------------------
    # URL DEDUPLICATION
    # --------------------------------------------------------

    unique_by_url = {}

    for item in collected:

        link = item["link"]

        if link not in unique_by_url:

            unique_by_url[
                link
            ] = item

    return list(
        unique_by_url.values()
    )


# ============================================================
# REMOVE SIMILAR NEWS
# ============================================================

def are_titles_similar(
    title_a,
    title_b,
):

    a = normalize_persian_text(
        title_a
    )

    b = normalize_persian_text(
        title_b
    )

    if a == b:
        return True

    # کلمات مهم
    words_a = {
        w
        for w in re.findall(
            r"[\u0600-\u06FF]+",
            a,
        )
        if len(w) >= 3
    }

    words_b = {
        w
        for w in re.findall(
            r"[\u0600-\u06FF]+",
            b,
        )
        if len(w) >= 3
    }

    if not words_a or not words_b:
        return False

    intersection = (
        words_a & words_b
    )

    smaller = min(
        len(words_a),
        len(words_b),
    )

    if smaller == 0:
        return False

    similarity = (
        len(intersection)
        / smaller
    )

    return similarity >= 0.70


# ============================================================
# SELECT LOCAL NEWS
# ============================================================

def select_local_news(
    news,
    sent_links,
    sent_titles,
):

    candidates = []

    for item in news:

        if item["link"] in sent_links:
            continue

        key = title_key(
            item["title"]
        )

        if key in sent_titles:
            continue

        if not is_real_local_news(
            item["title"],
            item["summary"],
        ):

            continue

        score = local_score(
            item["title"],
            item["summary"],
        )

        item = dict(item)

        item["score"] = score

        candidates.append(item)

    candidates.sort(
        key=lambda x: (
            x["score"],
            x["published"],
        ),
        reverse=True,
    )

    selected = []

    for item in candidates:

        duplicate = False

        for existing in selected:

            if are_titles_similar(
                item["title"],
                existing["title"],
            ):

                duplicate = True
                break

        if duplicate:
            continue

        selected.append(item)

        if (
            len(selected)
            >= MAX_NEWS_PER_RUN
        ):

            break

    return selected


# ============================================================
# SELECT NATIONAL
# ============================================================

def select_national_news(
    news,
    sent_links,
    sent_titles,
):

    candidates = []

    for item in news:

        if item["link"] in sent_links:
            continue

        key = title_key(
            item["title"]
        )

        if key in sent_titles:
            continue

        if is_real_local_news(
            item["title"],
            item["summary"],
        ):

            continue

        if not is_exceptional_national_news(
            item["title"],
            item["summary"],
        ):

            continue

        item = dict(item)

        item["score"] = national_score(
            item["title"],
            item["summary"],
        )

        candidates.append(item)

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
# SOCIAL LINKS
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

        reply_markup = build_reply_markup(
            item["link"]
        )

        caption = build_message(
            item
        )

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
# PROCESS ONE RUN
# ============================================================

def process_once():

    print(
        "==================================="
    )

    print(
        "🌐 JAHANTAB"
    )

    print(
        "آخرین تحولات سیستان و بلوچستان"
    )

    print(
        "==================================="
    )

    sent_links = load_sent_links()

    sent_titles = load_sent_titles()

    print(
        "Previously sent links: "
        f"{len(sent_links)}"
    )

    print(
        "Previously sent titles: "
        f"{len(sent_titles)}"
    )

    all_news = collect_all_news()

    print(
        "Approved-source news: "
        f"{len(all_news)}"
    )

    # --------------------------------------------------------
    # LOCAL
    # --------------------------------------------------------

    local_news = select_local_news(
        all_news,
        sent_links,
        sent_titles,
    )

    print(
        "Selected local news: "
        f"{len(local_news)}"
    )

    # --------------------------------------------------------
    # PUBLISH LOCAL
    # --------------------------------------------------------

    for item in local_news:

        item["category"] = (
            "استان سیستان و بلوچستان"
        )

        print(
            "Publishing local: "
            f"[{item['source']}] "
            f"{item['title']}"
        )

        try:

            # ثبت در حافظه قبل از ارسال
            # برای جلوگیری از انتخاب مجدد
            sent_links.add(
                item["link"]
            )

            sent_titles.add(
                title_key(
                    item["title"]
                )
            )

            publish_item(item)

            save_sent_link(
                item["link"]
            )

            save_sent_title(
                item["title"]
            )

            print(
                "✅ Published successfully."
            )

            # در هر اجرا فقط یک خبر
            return True

        except Exception as exc:

            # اگر ارسال شکست خورد،
            # اجازه می‌دهیم اجرای بعدی دوباره امتحان کند.

            sent_links.discard(
                item["link"]
            )

            sent_titles.discard(
                title_key(
                    item["title"]
                )
            )

            print(
                f"❌ Publish failed: "
                f"{exc}"
            )

    # --------------------------------------------------------
    # EXCEPTIONAL NATIONAL
    # --------------------------------------------------------

    national = select_national_news(
        all_news,
        sent_links,
        sent_titles,
    )

    if national:

        national["category"] = (
            "ایران"
        )

        print(
            "Publishing exceptional "
            "national: "
            f"[{national['source']}] "
            f"{national['title']}"
        )

        try:

            sent_links.add(
                national["link"]
            )

            sent_titles.add(
                title_key(
                    national["title"]
                )
            )

            publish_item(
                national
            )

            save_sent_link(
                national["link"]
            )

            save_sent_title(
                national["title"]
            )

            print(
                "✅ National news published."
            )

            return True

        except Exception as exc:

            print(
                f"❌ National publish failed: "
                f"{exc}"
            )

    print(
        "No suitable new news found."
    )

    return False


# ============================================================
# MAIN LOOP
# EVERY 30 MINUTES
# ============================================================

def main():

    if not acquire_lock():

        print(
            "Jahantab is already running."
        )

        return

    try:

        print(
            "==================================="
        )

        print(
            "🌐 JAHANTAB BOT STARTED"
        )

        print(
            "⏱ Interval: 30 minutes"
        )

        print(
            "📍 Sistan & Baluchestan"
        )

        print(
            "==================================="
        )

        while True:

            try:

                process_once()

            except Exception as exc:

                print(
                    "❌ Main cycle error:"
                )

                print(exc)

            print(
                "-----------------------------------"
            )

            print(
                "⏳ Waiting 30 minutes..."
            )

            print(
                "-----------------------------------"
            )

            time.sleep(
                RUN_INTERVAL_SECONDS
            )

    finally:

        release_lock()

        print(
            "Jahantab lock released."
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()