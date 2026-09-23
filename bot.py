# -*- coding: utf-8 -*-

"""
============================================================
🌐 جهان‌تاب | آخرین تحولات سیستان و بلوچستان
============================================================

ویژگی‌ها:
- منابع داخلی و خبرگزاری‌های ایرانی
- تمرکز تخصصی بر سیستان و بلوچستان
- انتشار حداکثر یک خبر در هر ۳۰ دقیقه
- فیلتر چندمرحله‌ای اخبار محلی
- فرهنگ، هنر و موسیقی استان
- هامون، هیرمند، جازموریان، مکران و دریای عمان
- حذف اخبار مربوط به سایر استان‌ها
- حذف اخبار ورزشی و سرگرمی نامرتبط
- حذف خبرهای تکراری
- حذف گزارش‌های چندرسانه‌ای و بسته‌های خبری تکراری
- تصویر خبر در صورت وجود
- دکمه مشاهده خبر
- لینک تلگرام، بله و سروش داخل باکس
============================================================
"""

import os
import re
import json
import html
import time
from difflib import SequenceMatcher
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

# هر چند دقیقه یک بار بررسی شود
CHECK_INTERVAL_MINUTES = 30

# حداکثر سن خبر
MAX_NEWS_AGE_HOURS = 24

# در هر اجرا فقط یک خبر
MAX_NEWS_PER_RUN = 1


if not BOT_TOKEN:
    raise RuntimeError(
        "BALE_BOT_TOKEN is not set"
    )

if not CHAT_ID:
    raise RuntimeError(
        "BALE_CHAT_ID is not set"
    )


# ============================================================
# APPROVED INTERNAL IRANIAN NEWS SOURCES
# ============================================================

SOURCES = [

    (
        "ایرنا",
        "irna.ir",
        [
            "https://www.irna.ir/rss",
        ],
    ),

    (
        "ایسنا",
        "isna.ir",
        [
            "https://www.isna.ir/rss",
        ],
    ),

    (
        "مهر",
        "mehrnews.com",
        [
            "https://www.mehrnews.com/rss",
        ],
    ),

    (
        "فارس",
        "farsnews.ir",
        [
            "https://www.farsnews.ir/rss",
        ],
    ),

    (
        "ایلنا",
        "ilna.ir",
        [
            "https://www.ilna.ir/rss",
        ],
    ),

    (
        "تسنیم",
        "tasnimnews.com",
        [
            "https://www.tasnimnews.com/fa/rss/feed/0/8/0/مهمترین-اخبار-تسنیم",
        ],
    ),

    (
        "خبرگزاری صداوسیما",
        "iribnews.ir",
        [
            "https://www.iribnews.ir/fa/rss",
        ],
    ),

    (
        "باشگاه خبرنگاران جوان",
        "yjc.ir",
        [
            "https://www.yjc.ir/fa/rss/allnews",
        ],
    ),

    (
        "خبرآنلاین",
        "khabaronline.ir",
        [
            "https://www.khabaronline.ir/rss",
        ],
    ),

    (
        "تابناک",
        "tabnak.ir",
        [
            "https://www.tabnak.ir/fa/rss/allnews",
        ],
    ),

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
# PROVINCE
# ============================================================

PROVINCE_TERMS = [

    "سیستان و بلوچستان",
    "سیستان‌ و بلوچستان",
    "سیستان‌وبلوچستان",
    "استان سیستان و بلوچستان",
    "استان سیستان‌وبلوچستان",

]


# ============================================================
# CITIES
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
    "راسک",
    "پارود",
    "نگور",
    "اسپکه",
    "محمدان",
    "بزمان",
    "بمپور",
    "بخش زرآباد",
    "زرآباد",

]


# ============================================================
# SPECIAL GEOGRAPHICAL / ENVIRONMENTAL TERMS
# ============================================================

SPECIAL_LOCAL_TERMS = [

    # هامون
    "هامون",
    "دریاچه هامون",
    "تالاب هامون",

    # هیرمند
    "هیرمند",
    "رودخانه هیرمند",
    "رود هیرمند",
    "حق‌آبه هیرمند",
    "حق آبه هیرمند",
    "حقابه هیرمند",

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
# LOCAL NEWS CONTEXT
# ============================================================

LOCAL_CONTEXT_TERMS = [

    # مدیریت استان
    "استاندار",
    "استانداری",
    "معاون استاندار",
    "فرماندار",
    "فرمانداری",
    "مدیرکل",
    "اداره کل",
    "نماینده ولی فقیه",
    "مجمع نمایندگان",
    "نماینده مردم",
    "نماینده سیستان",
    "نماینده بلوچستان",

    # انتظامی و حوادث
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
    "پلیس",
    "فراجا",
    "نیروی انتظامی",
    "مأمور انتظامی",
    "مرزبانی",

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

    # آب و انرژی
    "آب",
    "آبرسانی",
    "تنش آبی",
    "بحران آب",
    "برق",
    "گاز",
    "خشکسالی",
    "حق‌آبه",
    "حق آبه",
    "منابع آب",

    # کشاورزی
    "کشاورزی",
    "دامداری",
    "باغداری",
    "صیادی",
    "ماهیگیری",
    "شیلات",
    "موز",
    "خرما",

    # محیط زیست
    "محیط زیست",
    "محیط‌زیست",
    "تالاب",
    "حیات وحش",
    "گرد و غبار",
    "ریزگرد",
    "خشکسالی",

    # اقتصاد
    "اقتصاد",
    "اشتغال",
    "سرمایه‌گذاری",
    "سرمایه گذاری",
    "بازار",
    "تجارت",
    "مرز",
    "مرزنشین",
    "صادرات",
    "واردات",

    # اجتماعی
    "آموزش",
    "دانش‌آموز",
    "دانشجو",
    "بهداشت",
    "درمان",
    "سلامت",
    "بیمارستان",
    "جمعیت",
    "خانواده",

    # مکران / چابهار
    "مکران",
    "چابهار",
    "دریای عمان",
    "کشتیرانی",
    "بندر",
    "منطقه آزاد",

]


# ============================================================
# CULTURE / ART / MUSIC
# ============================================================

CULTURE_TERMS = [

    # فرهنگ
    "فرهنگ",
    "فرهنگی",
    "فرهنگ و هنر",
    "هنر",

    # موسیقی
    "موسیقی",
    "موسیقی بلوچستان",
    "موسیقی سیستان",
    "موسیقی بلوچی",
    "موسیقی محلی",
    "موسیقی سنتی",
    "هنرمند",
    "خواننده",
    "نوازنده",
    "ساز",
    "دف",
    "دهل",
    "رباب",
    "قیچک",

    # هنر
    "نمایشگاه",
    "جشنواره",
    "شعر",
    "شاعر",
    "داستان",
    "نویسنده",
    "کتاب",
    "فیلم",
    "سینما",
    "تئاتر",
    "نمایش",

    # میراث
    "میراث فرهنگی",
    "گردشگری",
    "صنایع دستی",
    "باستان‌شناسی",
    "آثار تاریخی",
    "بناهای تاریخی",
    "روستای تاریخی",
    "قلعه",
    "موزه",

    # فرهنگ بلوچ / سیستان
    "بلوچ",
    "بلوچستان",
    "سیستان",
    "لباس بلوچی",
    "سوزن‌دوزی",
    "سوزن دوزی",
    "حصیربافی",
    "گلیم",
    "زیورآلات سنتی",

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
# UNRELATED SUBJECTS
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

    # سرگرمی عمومی
    "سلبریتی",
    "آگاتا کریستی",
    "خانم مارپل",
    "مارپل",
    "فال",
    "طالع بینی",
    "مد",
    "زیبایی",
    "سبک زندگی",

]


# ============================================================
# ROUNDUP / GENERIC ARTICLES
# ============================================================

GENERIC_EXCLUDE_TERMS = [

    "آخرین اخبار ایران",
    "آخرین اخبار کشور",
    "مهمترین اخبار امروز",
    "اخبار مهم امروز",
    "اخبار لحظه‌ای ایران",
    "خبرهای مهم کشور",

]


# ============================================================
# NATIONAL EXCEPTIONAL NEWS
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

    "User-Agent":
        "Mozilla/5.0 "
        "(compatible; JahantabNewsBot/5.0)"

})


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):

    if not value:
        return ""

    value = html.unescape(
        str(value)
    )

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


def normalize_text(text):

    text = clean_text(text)

    replacements = {

        "ي": "ی",
        "ى": "ی",
        "ك": "ک",

        "ۀ": "ه",
        "ة": "ه",

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


def normalize_title(text):

    text = normalize_text(
        text
    ).lower()

    text = re.sub(
        r"[^\w\s\u0600-\u06FF]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


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
# SENT LINKS
# ============================================================

def load_sent_links():

    if not os.path.exists(
        STATE_FILE
    ):
        return set()

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

def contains_any(
    text,
    terms,
):

    text = normalize_text(
        text
    )

    return any(
        normalize_text(term)
        in text
        for term in terms
    )


def has_other_province_in_title(
    title,
):

    title = normalize_text(
        title
    )

    for province in OTHER_PROVINCE_TERMS:

        if normalize_text(
            province
        ) in title:

            return True

    return False


def count_terms(
    text,
    terms,
):

    text = normalize_text(
        text
    )

    count = 0

    for term in terms:

        if normalize_text(
            term
        ) in text:

            count += 1

    return count


# ============================================================
# LOCAL SCORE
# ============================================================

def local_score(
    title,
    summary,
):

    title = normalize_text(
        title
    )

    summary = normalize_text(
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
        score -= 100

    # --------------------------------------------------------
    # PROVINCE
    # --------------------------------------------------------

    for term in PROVINCE_TERMS:

        term = normalize_text(
            term
        )

        if term in title:
            score += 35

        elif term in summary:
            score += 12

    # --------------------------------------------------------
    # CITIES
    # --------------------------------------------------------

    city_in_title = False

    for term in CITY_TERMS:

        term = normalize_text(
            term
        )

        if term in title:

            score += 10
            city_in_title = True

        elif term in summary:

            score += 3

    # --------------------------------------------------------
    # SPECIAL GEOGRAPHY
    # --------------------------------------------------------

    for term in SPECIAL_LOCAL_TERMS:

        term = normalize_text(
            term
        )

        if term in title:
            score += 25

        elif term in summary:
            score += 10

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
    # CULTURE / ART / MUSIC
    # --------------------------------------------------------

    culture_count = count_terms(
        full_text,
        CULTURE_TERMS,
    )

    if culture_count:

        score += min(
            culture_count * 7,
            25,
        )

    # --------------------------------------------------------
    # UNRELATED
    # --------------------------------------------------------

    if contains_any(
        full_text,
        LOCAL_EXCLUDE_TERMS,
    ):

        score -= 70

    # --------------------------------------------------------
    # CITY WITHOUT CONTEXT
    # --------------------------------------------------------

    if (
        city_in_title
        and context_count == 0
        and culture_count == 0
    ):

        score -= 25

    return score


# ============================================================
# REAL LOCAL NEWS
# ============================================================

def is_real_local_news(
    title,
    summary,
):

    title = normalize_text(
        title
    )

    summary = normalize_text(
        summary
    )

    full_text = (
        title
        + " "
        + summary
    )

    # --------------------------------------------------------
    # OTHER PROVINCE IN TITLE = REJECT
    # --------------------------------------------------------

    if has_other_province_in_title(
        title
    ):
        return False

    # --------------------------------------------------------
    # UNRELATED SUBJECT
    # --------------------------------------------------------

    if contains_any(
        full_text,
        LOCAL_EXCLUDE_TERMS,
    ):
        return False

    # --------------------------------------------------------
    # GENERIC NATIONAL ROUNDUPS
    # --------------------------------------------------------

    if contains_any(
        title,
        GENERIC_EXCLUDE_TERMS,
    ):
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

    has_special = contains_any(
        full_text,
        SPECIAL_LOCAL_TERMS,
    )

    # --------------------------------------------------------
    # CULTURE
    # --------------------------------------------------------

    has_culture = contains_any(
        full_text,
        CULTURE_TERMS,
    )

    if not (
        has_province
        or has_city
        or has_special
    ):
        return False

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    score = local_score(
        title,
        summary,
    )

    # --------------------------------------------------------
    # PROVINCE IN TITLE
    # --------------------------------------------------------

    if contains_any(
        title,
        PROVINCE_TERMS,
    ):

        return score >= 20

    # --------------------------------------------------------
    # SPECIAL LOCAL SUBJECT IN TITLE
    # --------------------------------------------------------

    if contains_any(
        title,
        SPECIAL_LOCAL_TERMS,
    ):

        return score >= 20

    # --------------------------------------------------------
    # CULTURE / ART / MUSIC
    #
    # If the title itself identifies
    # a Sistan-Baluchestan cultural subject,
    # allow it with strong local evidence.
    # --------------------------------------------------------

    if has_culture:

        culture_count = count_terms(
            full_text,
            CULTURE_TERMS,
        )

        local_location_count = (
            count_terms(
                full_text,
                CITY_TERMS,
            )
            + count_terms(
                full_text,
                PROVINCE_TERMS,
            )
            + count_terms(
                full_text,
                SPECIAL_LOCAL_TERMS,
            )
        )

        if (
            culture_count >= 1
            and local_location_count >= 1
            and score >= 15
        ):
            return True

    # --------------------------------------------------------
    # CITY ALONE IS NOT ENOUGH
    # --------------------------------------------------------

    context_count = count_terms(
        full_text,
        LOCAL_CONTEXT_TERMS,
    )

    if (
        has_city
        and context_count < 1
        and not has_culture
        and not has_special
    ):
        return False

    return score >= 15


# ============================================================
# NATIONAL NEWS
# ============================================================

def national_score(
    title,
    summary,
):

    text = (
        normalize_text(title)
        + " "
        + normalize_text(summary)
    )

    score = 0

    for term in MAJOR_NATIONAL_TERMS:

        if normalize_text(
            term
        ) in text:

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

            collected.append(
                item
            )

    # --------------------------------------------------------
    # URL DEDUPLICATION
    # --------------------------------------------------------

    unique = {}

    for item in collected:

        if item["link"] not in unique:

            unique[
                item["link"]
            ] = item

    return list(
        unique.values()
    )


# ============================================================
# SIMILAR NEWS DETECTION
# ============================================================

def title_similarity(
    title_a,
    title_b,
):

    a = normalize_title(
        title_a
    )

    b = normalize_title(
        title_b
    )

    if not a or not b:
        return 0

    ratio = SequenceMatcher(
        None,
        a,
        b,
    ).ratio()

    words_a = set(
        a.split()
    )

    words_b = set(
        b.split()
    )

    if not words_a or not words_b:
        return ratio

    common = (
        len(
            words_a
            & words_b
        )
        /
        max(
            len(words_a),
            len(words_b),
        )
    )

    return max(
        ratio,
        common,
    )


def is_duplicate_news(
    item,
    selected_items,
):

    for selected in selected_items:

        similarity = title_similarity(
            item["title"],
            selected["title"],
        )

        # تقریباً یک خبر
        if similarity >= 0.72:
            return True

    return False


# ============================================================
# SELECT ONE LOCAL NEWS
# ============================================================

def select_local_news(
    news,
    sent_links,
):

    candidates = []

    for item in news:

        if item["link"] in sent_links:
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

        candidates.append(
            item
        )

    candidates.sort(
        key=lambda x: (
            x["score"],
            x["published"],
        ),
        reverse=True,
    )

    selected = []

    for item in candidates:

        if is_duplicate_news(
            item,
            selected,
        ):
            continue

        selected.append(
            item
        )

        if len(selected) >= MAX_NEWS_PER_RUN:
            break

    return selected


# ============================================================
# SELECT EXCEPTIONAL NATIONAL NEWS
# ============================================================

def select_national_news(
    news,
    sent_links,
):

    candidates = []

    for item in news:

        if item["link"] in sent_links:
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

        candidates.append(
            item
        )

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

def get_image_from_article(
    url,
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
                "name":
                    "twitter:image"
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
            "description":
                response.text,

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
                        "text":
                            "🔗 مشاهده خبر",
                        "url":
                            article_url,
                    }

                ],

                [

                    {
                        "text":
                            "📨 تلگرام",
                        "url":
                            TELEGRAM_URL,
                    },

                    {
                        "text":
                            "🟦 بله",
                        "url":
                            BALE_URL,
                    },

                    {
                        "text":
                            "🟠 سروش",
                        "url":
                            SOROUSH_URL,
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

    reply_markup = (
        build_reply_markup(
            item["link"]
        )
    )

    return bale_request(

        "sendMessage",

        data={

            "chat_id":
                CHAT_ID,

            "text":
                build_message(
                    item
                ),

            "reply_markup":
                reply_markup,

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

        caption = caption[:1000]

        return bale_request(

            "sendPhoto",

            data={

                "chat_id":
                    CHAT_ID,

                "caption":
                    caption,

                "reply_markup":
                    reply_markup,

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
# ONE CYCLE
# ============================================================

def run_cycle():

    print()
    print(
        "=========================================="
    )

    print(
        "🌐 جهان‌تاب | آخرین تحولات "
        "سیستان و بلوچستان"
    )

    print(
        "=========================================="
    )

    print(
        "شروع بررسی خبرها..."
    )

    sent_links = (
        load_sent_links()
    )

    print(
        "Previously sent links: "
        f"{len(sent_links)}"
    )

    all_news = (
        collect_all_news()
    )

    print(
        "Approved-source news: "
        f"{len(all_news)}"
    )

    # ========================================================
    # LOCAL NEWS
    # ========================================================

    local_news = (
        select_local_news(
            all_news,
            sent_links,
        )
    )

    if local_news:

        item = local_news[0]

        item["category"] = (
            "استان سیستان و بلوچستان"
        )

        print(
            "Selected local news:"
        )

        print(
            f"[{item['source']}] "
            f"{item['title']}"
        )

        print(
            f"Score: {item['score']}"
        )

        try:

            publish_item(
                item
            )

            save_sent_link(
                item["link"]
            )

            print(
                "✅ خبر با موفقیت منتشر شد."
            )

            return True

        except Exception as exc:

            print(
                "❌ Publish failed: "
                f"{exc}"
            )

            return False

    # ========================================================
    # EXCEPTIONAL NATIONAL NEWS
    # فقط در صورت نبود خبر محلی
    # ========================================================

    national = (
        select_national_news(
            all_news,
            sent_links,
        )
    )

    if national:

        national["category"] = (
            "ایران"
        )

        print(
            "Exceptional national news:"
        )

        print(
            f"[{national['source']}] "
            f"{national['title']}"
        )

        try:

            publish_item(
                national
            )

            save_sent_link(
                national["link"]
            )

            print(
                "✅ خبر ملی استثنایی منتشر شد."
            )

            return True

        except Exception as exc:

            print(
                "❌ National publish failed: "
                f"{exc}"
            )

            return False

    print(
        "ℹ️ خبر مناسب برای انتشار پیدا نشد."
    )

    return False


# ============================================================
# CONTINUOUS 30-MINUTE LOOP
# ============================================================

def main():

    print(
        "=========================================="
    )

    print(
        "🌐 JAHANTAB NEWS BOT"
    )

    print(
        "آخرین تحولات سیستان و بلوچستان"
    )

    print(
        f"⏱ بررسی هر "
        f"{CHECK_INTERVAL_MINUTES} دقیقه"
    )

    print(
        "=========================================="
    )

    while True:

        cycle_start = time.time()

        try:

            run_cycle()

        except Exception as exc:

            print(
                "❌ خطای کلی:"
            )

            print(
                exc
            )

        elapsed = (
            time.time()
            - cycle_start
        )

        sleep_seconds = max(
            60,
            (
                CHECK_INTERVAL_MINUTES
                * 60
            )
            - elapsed,
        )

        print()
        print(
            "------------------------------------------"
        )

        print(
            f"⏳ بررسی بعدی حدود "
            f"{CHECK_INTERVAL_MINUTES} دقیقه دیگر."
        )

        print(
            "------------------------------------------"
        )

        time.sleep(
            sleep_seconds
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()