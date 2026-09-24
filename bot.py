# -*- coding: utf-8 -*-
"""
============================================================
JAHANTAB | جهان‌تاب
رصدخانه خبری سیستان و بلوچستان
نسخه نهایی v9.0
============================================================

ARCHITECTURE
------------------------------------------------------------
RSS
 ↓
Geographic Filter
 ↓
Irrelevant-News Filter
 ↓
Duplicate-Link Filter
 ↓
Event Similarity
 ↓
Event Clustering
 ↓
Best Version Selection
 ↓
Local Scoring
 ↓
Freshness Scoring
 ↓
Publish

ویژگی‌های اصلی v9.0:

- فقط منابع داخلی و رسمی/شناخته‌شده ایرانی
- تمرکز سخت‌گیرانه بر سیستان و بلوچستان
- حذف لینک تکراری
- حذف عنوان تکراری
- تشخیص رویدادهای یکسان از چند خبرگزاری
- گروه‌بندی خبرهای مربوط به یک رویداد
- انتخاب بهترین نسخه خبر
- جلوگیری از انتشار مجدد همان رویداد در اجراهای بعدی
- Event Similarity چندمعیاره

وزن تشخیص تکراری بودن رویداد:

    عنوان             25%
    خلاصه             35%
    واژه‌های متمایز   25%
    شباهت کاراکتری    15%

- امتیاز خیلی بالا → تکراری قطعی
- امتیاز متوسط → بررسی تکمیلی
- امتیاز پایین → رویداد جدید

- RSS date
- email.utils fallback
- freshness scoring
- SequenceMatcher
- Jaccard
- distinctive-word similarity
- PID-safe lock
- state persistence
- automatic pruning
- OG image
- sendPhoto fallback
- sendMessage fallback
- لاگ کامل علت رد/ادغام خبر
============================================================
"""

import os
import re
import json
import html
import time
import calendar
import email.utils
import logging
import difflib
import hashlib

from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests
import feedparser

from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
CHAT_ID = os.getenv("BALE_CHAT_ID")

STATE_FILE = "sent_links.txt"
TITLES_FILE = "sent_titles.txt"
PUBLISHED_STATE_FILE = "published_state.json"

# state مربوط به رویدادها
EVENTS_FILE = "published_events.json"

LOCK_FILE = "jahantab.lock"

PUBLISH_INTERVAL_MINUTES = 30

# فقط خبرهای حداکثر 24 ساعت گذشته
MAX_NEWS_AGE_HOURS = 24

MAX_CANDIDATES = 1000

MAX_CAPTION_LEN = 1000
MAX_TEXT_LEN = 3900

MAX_TITLES_KEPT = 500

# ------------------------------------------------------------
# EVENT DUPLICATION
# ------------------------------------------------------------

# امتیاز کلی از 0 تا 100
#
# >= 82
# رویداد تقریباً قطعی تکراری
#
# 68 تا 81
# احتمالاً همان رویداد
#
# < 68
# رویداد جدید
#
EVENT_DUPLICATE_THRESHOLD = 82
EVENT_PROBABLE_THRESHOLD = 68

# اگر یک خبر با رویداد ذخیره‌شده بیش از این فاصله داشته باشد
# دیگر به‌صورت خودکار همان رویداد فرض نمی‌شود.
EVENT_MAX_AGE_HOURS = 72

# ------------------------------------------------------------
# EVENT WEIGHTS
# ------------------------------------------------------------

TITLE_WEIGHT = 0.25
SUMMARY_WEIGHT = 0.35
DISTINCTIVE_WEIGHT = 0.25
CHARACTER_WEIGHT = 0.15

# ------------------------------------------------------------
# FRESHNESS
# ------------------------------------------------------------

FRESHNESS_HOURS = 24

# ------------------------------------------------------------
# LOCAL MINIMUM SCORES
# ------------------------------------------------------------

MIN_CITY_SCORE = 25
MIN_PROVINCE_SCORE = 30
MIN_SPECIAL_SCORE = 28

# ------------------------------------------------------------
# STATE LIMITS
# ------------------------------------------------------------

MAX_EVENTS_KEPT = 600


TELEGRAM_URL = "https://t.me/jahantab_news"
BALE_URL = "https://ble.ir/jahantabnews"
SOROUSH_URL = "https://splus.ir/jahantabnews"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

log = logging.getLogger("jahantab")


if not BOT_TOKEN:
    raise RuntimeError("BALE_BOT_TOKEN is not set")

if not CHAT_ID:
    raise RuntimeError("BALE_CHAT_ID is not set")


# ============================================================
# HTTP SESSION
# ============================================================

def build_session():

    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36 "
            "JahantabBot/9.0"
        ),
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
    })

    retry = Retry(
        total=3,
        backoff_factor=0.8,
        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],
        allowed_methods=[
            "GET",
            "POST",
        ],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=12,
        pool_maxsize=24,
    )

    session.mount(
        "http://",
        adapter,
    )

    session.mount(
        "https://",
        adapter,
    )

    return session


SESSION = build_session()


# ============================================================
# SOURCES
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
            (
                "https://www.tasnimnews.com/fa/rss/feed/"
                "0/8/0/مهمترین-اخبار-تسنیم"
            ),
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
        "تابناک",
        "tabnak.ir",
        [
            "https://www.tabnak.ir/fa/rss/allnews",
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
        "همشهری",
        "hamshahrionline.ir",
        [
            "https://www.hamshahrionline.ir/rss",
        ],
    ),

    (
        "جام جم",
        "jamejamonline.ir",
        [
            "https://jamejamonline.ir/rss",
        ],
    ),

    (
        "انتخاب",
        "entekhab.ir",
        [
            "https://www.entekhab.ir/fa/rss",
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
# LOCAL TERMS
# ============================================================

PROVINCE_TERMS = [
    "سیستان و بلوچستان",
    "استان سیستان و بلوچستان",
]


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
    "پیشین",
    "تفتان",
    "ادیمی",
    "محمدان",
    "نوک آباد",
    "پارود",
    "زرآباد",
    "لاشار",
    "آهوران",
    "کورین",
    "نصرت آباد",
    "اسپکه",
]


SPECIAL_LOCAL_TERMS = [
    "تالاب هامون",
    "تالاب بین المللی هامون",
    "رودخانه هیرمند",
    "رود هیرمند",
    "حقابه هیرمند",
    "حقابه ایران",
    "آب هیرمند",
    "جازموریان",
    "تالاب جازموریان",
    "مکران",
    "سواحل مکران",
    "ساحل مکران",
    "دریای عمان",
    "سواحل دریای عمان",
    "ساحل دریای عمان",
    "بندر چابهار",
    "منطقه آزاد چابهار",
]


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
    "میراث فرهنگی سیستان و بلوچستان",
    "سفال کلپورگان",
    "کلپورگان",
    "سوزن دوزی بلوچ",
    "لباس بلوچی",
    "لباس محلی بلوچستان",
    "رقص محلی بلوچستان",
    "موسیقی مقامی",
    "جشنواره فرهنگی",
    "جشنواره هنری",
    "نمایشگاه هنری",
    "رویداد فرهنگی",
    "آیین های سنتی",
    "آیین سنتی",
    "ادبیات بلوچستان",
    "شعر بلوچی",
    "شاعر بلوچ",
]


LOCAL_CONTEXT_TERMS = [
    "استاندار",
    "استانداری",
    "معاون استاندار",
    "فرماندار",
    "فرمانداری",
    "نماینده ولی فقیه",
    "مجمع نمایندگان",
    "نماینده مردم",

    "حادثه",
    "تصادف",
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

    "افتتاح",
    "بهره برداری",
    "پروژه",
    "طرح",
    "ساخت",
    "توسعه",
    "اعتبار",
    "سرمایه گذاری",

    "راه",
    "جاده",
    "بندر",
    "بیمارستان",
    "مدرسه",
    "دانشگاه",
    "فرودگاه",
    "راه آهن",

    "آب رسانی",
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
    "کشتیرانی",
    "پتروشیمی",
    "سواحل",
]


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


FOREIGN_LOCATION_TERMS = [
    "سوریه",
    "ترکیه",
    "هند",
    "عراق",
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
    "غزه",
    "کرانه باختری",
    "رام الله",
    "تل آویو",
    "قدس",
    "استانبول",
    "آنکارا",
    "دمشق",
    "حلب",
    "رقه",
    "لندن",
    "پاریس",
    "برلین",
    "مسکو",
    "کی یف",
]


GENERAL_EXCLUDE_TERMS = [
    "آگاتا کریستی",
    "خانم مارپل",
    "فال حافظ",
    "فال روزانه",
    "سردار آزمون",
    "تیم ملی فوتبال",
    "تیم ملی",
    "فوتبال",
    "لیگ برتر",
    "استقلال",
    "پرسپولیس",
    "سلبریتی",
    "فال",
    "مد و زیبایی",
]


# ============================================================
# TEXT NORMALIZATION
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

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def normalize_persian_text(text):

    text = clean_text(text)

    text = text.replace(
        "\u200c",
        " ",
    )

    text = text.replace(
        "\u200e",
        "",
    )

    text = text.replace(
        "\u200f",
        "",
    )

    replacements = {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    text = re.sub(
        r"[ًٌٍَُِّْـ]",
        "",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def normalize_title(text):

    text = normalize_persian_text(
        text
    ).lower()

    remove_words = [
        "خبر",
        "گزارش",
        "اعلام",
        "آخرین",
        "واکنش",
        "جزئیات",
        "مهم",
        "جدید",
    ]

    for word in remove_words:

        text = re.sub(
            rf"(?<!\w){re.escape(word)}(?!\w)",
            " ",
            text,
        )

    text = re.sub(
        r"[^\w\u0600-\u06FF\s]",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def tokenize(text):

    text = normalize_persian_text(
        text
    ).lower()

    text = re.sub(
        r"[^\w\u0600-\u06FF\s]",
        " ",
        text,
    )

    return [
        x
        for x in text.split()
        if len(x) >= 2
    ]


def term_in(text, term):

    if not term:
        return False

    return re.search(
        rf"(?<!\w){re.escape(term)}(?!\w)",
        text,
    ) is not None


def has_any(text, terms):

    normalized_text = (
        normalize_persian_text(text)
    )

    for term in terms:

        normalized_term = (
            normalize_persian_text(term)
        )

        if term_in(
            normalized_text,
            normalized_term,
        ):
            return True

    return False


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

    url = re.sub(
        r"[?&]+$",
        "",
        url,
    )

    return url


def get_domain(url):

    try:

        domain = (
            urlparse(url).hostname
            or ""
        ).lower()

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

    return any(
        domain.endswith(
            "." + blocked
        )
        for blocked in BLOCKED_DOMAINS
    )


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

def write_lock():

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
    ) as f:

        json.dump(
            {
                "pid": os.getpid(),
                "time": time.time(),
            },
            f,
        )


def acquire_lock():

    try:

        write_lock()

        return True

    except FileExistsError:
        pass

    try:

        with open(
            LOCK_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        lock_time = float(
            data.get(
                "time",
                0,
            )
        )

        lock_pid = int(
            data.get(
                "pid",
                0,
            )
        )

    except Exception:

        return False

    if (
        time.time()
        - lock_time
        <= 600
    ):

        return False

    alive = False

    try:

        os.kill(
            lock_pid,
            0,
        )

        alive = True

    except (
        OSError,
        ProcessLookupError,
    ):

        alive = False

    if alive:
        return False

    log.warning(
        f"Removing stale lock "
        f"(pid={lock_pid})"
    )

    try:

        os.remove(
            LOCK_FILE
        )

    except FileNotFoundError:
        pass

    try:

        write_lock()

        return True

    except FileExistsError:

        return False


def release_lock():

    try:

        if not os.path.exists(
            LOCK_FILE
        ):
            return

        with open(
            LOCK_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        if int(
            data.get(
                "pid",
                0,
            )
        ) != os.getpid():

            return

        os.remove(
            LOCK_FILE
        )

    except Exception:
        pass


# ============================================================
# STATE
# ============================================================

def prune_file(
    path,
    keep,
):

    try:

        if not os.path.exists(
            path
        ):
            return

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:

            lines = [
                line
                for line in f
                if line.strip()
            ]

        if len(lines) <= keep:
            return

        with open(
            path,
            "w",
            encoding="utf-8",
        ) as f:

            f.writelines(
                lines[-keep:]
            )

    except Exception as exc:

        log.warning(
            f"Prune failed for "
            f"{path}: {exc}"
        )


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
        ) as f:

            return {
                normalize_url(
                    line.strip()
                )
                for line in f
                if line.strip()
            }

    except Exception:

        return set()


def save_sent_link(link):

    link = normalize_url(
        link
    )

    if not link:
        return

    with open(
        STATE_FILE,
        "a",
        encoding="utf-8",
    ) as f:

        f.write(
            link + "\n"
        )


def load_sent_titles():

    if not os.path.exists(
        TITLES_FILE
    ):
        return []

    try:

        with open(
            TITLES_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            return [
                line.strip()
                for line in f
                if line.strip()
            ][-MAX_TITLES_KEPT:]

    except Exception:

        return []


def save_sent_title(title):

    normalized = normalize_title(
        title
    )

    if not normalized:
        return

    with open(
        TITLES_FILE,
        "a",
        encoding="utf-8",
    ) as f:

        f.write(
            normalized + "\n"
        )

    prune_file(
        TITLES_FILE,
        MAX_TITLES_KEPT,
    )


# ============================================================
# PUBLISHED STATE
# ============================================================

def load_publish_state():

    default = {
        "last_publish": 0
    }

    if not os.path.exists(
        PUBLISHED_STATE_FILE
    ):
        return default

    try:

        with open(
            PUBLISHED_STATE_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            state = json.load(f)

        if not isinstance(
            state,
            dict,
        ):
            return default

        return state

    except Exception:

        return default


def save_publish_state(
    extra=None
):

    state = load_publish_state()

    state["last_publish"] = (
        time.time()
    )

    if extra:
        state.update(
            extra
        )

    with open(
        PUBLISHED_STATE_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )


def can_publish():

    state = load_publish_state()

    try:

        last_publish = float(
            state.get(
                "last_publish",
                0,
            )
        )

    except Exception:

        last_publish = 0

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

        log.info(
            f"Cooldown active: "
            f"{remaining}s remaining"
        )

        return False

    return True


# ============================================================
# EVENT STATE
# ============================================================

def load_events():

    if not os.path.exists(
        EVENTS_FILE
    ):
        return []

    try:

        with open(
            EVENTS_FILE,
            "r",
            encoding="utf-8",
        ) as f:

            events = json.load(f)

        if not isinstance(
            events,
            list,
        ):
            return []

        return events

    except Exception as exc:

        log.warning(
            f"Could not load events: "
            f"{exc}"
        )

        return []


def save_events(events):

    events = sorted(
        events,
        key=lambda x: x.get(
            "published_at",
            0,
        ),
        reverse=True,
    )

    events = events[
        :MAX_EVENTS_KEPT
    ]

    with open(
        EVENTS_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            events,
            f,
            ensure_ascii=False,
            indent=2,
        )


def make_event_id(item):

    base = (
        normalize_title(
            item.get(
                "title",
                "",
            )
        )
        + "|"
        + normalize_persian_text(
            item.get(
                "summary",
                "",
            )
        )[:500]
    )

    return hashlib.sha1(
        base.encode(
            "utf-8"
        )
    ).hexdigest()


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

            ts = calendar.timegm(
                entry.published_parsed
            )

            return datetime.fromtimestamp(
                ts,
                timezone.utc,
            )

        if getattr(
            entry,
            "updated_parsed",
            None,
        ):

            ts = calendar.timegm(
                entry.updated_parsed
            )

            return datetime.fromtimestamp(
                ts,
                timezone.utc,
            )

    except Exception:
        pass

    raw = (
        getattr(
            entry,
            "published",
            None,
        )
        or getattr(
            entry,
            "updated",
            None,
        )
    )

    if raw:

        try:

            dt = (
                email.utils
                .parsedate_to_datetime(
                    raw
                )
            )

            if dt.tzinfo is None:

                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        except Exception:
            pass

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
            .rsplit(
                " ",
                1,
            )[0]
            + "..."
        )

    return text


# ============================================================
# LOCATION CHECKS
# ============================================================

def other_province_in_title(
    title
):

    t = normalize_persian_text(
        title
    )

    if has_any(
        t,
        PROVINCE_TERMS,
    ):
        return False

    if has_any(
        t,
        CITY_TERMS,
    ):
        return False

    return has_any(
        t,
        OTHER_PROVINCE_TERMS,
    )


def foreign_location_in_title(
    title
):

    t = normalize_persian_text(
        title
    )

    if has_any(
        t,
        PROVINCE_TERMS,
    ):
        return False

    if has_any(
        t,
        SPECIAL_LOCAL_TERMS,
    ):
        return False

    if has_any(
        t,
        CITY_TERMS,
    ):
        return False

    return has_any(
        t,
        FOREIGN_LOCATION_TERMS,
    )


# ============================================================
# TERM SCORING
# ============================================================

def score_terms(
    full_text,
    title,
    terms,
    title_score,
    body_score,
):

    score = 0

    for term in terms:

        normalized_term = (
            normalize_persian_text(
                term
            )
        )

        if term_in(
            title,
            normalized_term,
        ):

            score += title_score

        elif term_in(
            full_text,
            normalized_term,
        ):

            score += body_score

    return score


# ============================================================
# LOCAL SCORE
# ============================================================

def local_score(
    title,
    summary,
):

    normalized_title = (
        normalize_persian_text(
            title
        )
    )

    normalized_summary = (
        normalize_persian_text(
            summary
        )
    )

    full = (
        normalized_title
        + " "
        + normalized_summary
    ).strip()

    score = 0

    if other_province_in_title(
        title
    ):

        score -= 120

    if foreign_location_in_title(
        title
    ):

        score -= 120

    score += score_terms(
        full,
        normalized_title,
        PROVINCE_TERMS,
        45,
        12,
    )

    score += score_terms(
        full,
        normalized_title,
        CITY_TERMS,
        20,
        4,
    )

    score += score_terms(
        full,
        normalized_title,
        SPECIAL_LOCAL_TERMS,
        32,
        10,
    )

    score += score_terms(
        full,
        normalized_title,
        CULTURE_TERMS,
        32,
        10,
    )

    context_count = sum(
        1
        for term in LOCAL_CONTEXT_TERMS
        if term_in(
            full,
            normalize_persian_text(
                term
            ),
        )
    )

    score += min(
        context_count * 5,
        30,
    )

    return score


# ============================================================
# TITLE LOCALITY
# ============================================================

def title_locality_type(
    title
):

    t = normalize_persian_text(
        title
    )

    if has_any(
        t,
        PROVINCE_TERMS,
    ):
        return "province"

    if has_any(
        t,
        SPECIAL_LOCAL_TERMS,
    ):
        return "special"

    if has_any(
        t,
        CULTURE_TERMS,
    ):
        return "culture"

    if has_any(
        t,
        CITY_TERMS,
    ):
        return "city"

    return "none"


# ============================================================
# STRICT LOCAL FILTER
# ============================================================

def is_real_local_news(
    title,
    summary,
    score=None,
):

    normalized_title = (
        normalize_persian_text(
            title
        )
    )

    normalized_summary = (
        normalize_persian_text(
            summary
        )
    )

    full = (
        normalized_title
        + " "
        + normalized_summary
    ).strip()

    if other_province_in_title(
        title
    ):

        return (
            False,
            "other province in title",
        )

    if foreign_location_in_title(
        title
    ):

        return (
            False,
            "foreign location in title",
        )

    for term in GENERAL_EXCLUDE_TERMS:

        normalized_term = (
            normalize_persian_text(
                term
            )
        )

        if term_in(
            full,
            normalized_term,
        ):

            return (
                False,
                f"general exclude: {term}",
            )

    has_province = has_any(
        full,
        PROVINCE_TERMS,
    )

    has_city = has_any(
        full,
        CITY_TERMS,
    )

    has_special = has_any(
        full,
        SPECIAL_LOCAL_TERMS,
    )

    has_culture = has_any(
        full,
        CULTURE_TERMS,
    )

    if not (
        has_province
        or has_city
        or has_special
        or has_culture
    ):

        return (
            False,
            "no local signal",
        )

    if score is None:

        score = local_score(
            title,
            summary,
        )

    title_type = title_locality_type(
        title
    )

    if title_type == "province":

        if score < MIN_PROVINCE_SCORE:

            return (
                False,
                f"province score too low: {score}",
            )

        return (
            True,
            "province title",
        )

    if title_type == "special":

        if score < MIN_SPECIAL_SCORE:

            return (
                False,
                f"special score too low: {score}",
            )

        return (
            True,
            "special local title",
        )

    if title_type == "culture":

        if score < 25:

            return (
                False,
                f"culture score too low: {score}",
            )

        return (
            True,
            "culture title",
        )

    if title_type == "city":

        context_count = sum(
            1
            for term in LOCAL_CONTEXT_TERMS
            if term_in(
                full,
                normalize_persian_text(
                    term
                ),
            )
        )

        if context_count == 0:

            if not (
                has_province
                or has_special
                or has_culture
            ):

                return (
                    False,
                    "city without local context",
                )

        if score < MIN_CITY_SCORE:

            return (
                False,
                f"city score too low: {score}",
            )

        return (
            True,
            "city title",
        )

    if not (
        has_province
        or has_special
        or has_culture
    ):

        return (
            False,
            "weak body local context",
        )

    if score < 30:

        return (
            False,
            f"body local score too low: {score}",
        )

    return (
        True,
        "body local signal",
    )


# ============================================================
# TEXT SIMILARITY
# ============================================================

def sequence_similarity(
    a,
    b,
):

    a = normalize_title(a)
    b = normalize_title(b)

    if not a or not b:
        return 0.0

    return difflib.SequenceMatcher(
        None,
        a,
        b,
    ).ratio()


def jaccard_similarity(
    a,
    b,
):

    sa = set(
        tokenize(a)
    )

    sb = set(
        tokenize(b)
    )

    if not sa or not sb:
        return 0.0

    return (
        len(sa & sb)
        / max(
            len(sa | sb),
            1,
        )
    )


# ============================================================
# DISTINCTIVE WORDS
# ============================================================

STOP_WORDS = {
    "از",
    "به",
    "در",
    "با",
    "برای",
    "و",
    "یا",
    "که",
    "این",
    "آن",
    "یک",
    "شد",
    "شده",
    "شود",
    "کرد",
    "کرده",
    "است",
    "هست",
    "بود",
    "بودند",
    "نیز",
    "اما",
    "هم",
    "بر",
    "تا",
    "را",
    "وی",
    "او",
    "آنها",
    "ما",
    "من",
    "ایران",
    "کشور",
    "استان",
    "خبر",
    "گزارش",
    "اعلام",
    "آخرین",
    "مهم",
    "جدید",
    "امروز",
    "دیروز",
}


def distinctive_words(text):

    words = tokenize(
        text
    )

    result = []

    for word in words:

        if word in STOP_WORDS:
            continue

        if len(word) < 3:
            continue

        result.append(
            word
        )

    return set(
        result
    )


def distinctive_similarity(
    a,
    b,
):

    sa = distinctive_words(a)
    sb = distinctive_words(b)

    if not sa or not sb:
        return 0.0

    return (
        len(sa & sb)
        / max(
            len(sa | sb),
            1,
        )
    )


# ============================================================
# EVENT SIMILARITY
# ============================================================

def event_similarity(
    item_a,
    item_b,
):

    title_a = item_a.get(
        "title",
        "",
    )

    title_b = item_b.get(
        "title",
        "",
    )

    summary_a = item_a.get(
        "summary",
        "",
    )

    summary_b = item_b.get(
        "summary",
        "",
    )

    # --------------------------------------------------------
    # عنوان
    # --------------------------------------------------------

    title_score = max(
        sequence_similarity(
            title_a,
            title_b,
        ),
        jaccard_similarity(
            title_a,
            title_b,
        ),
    )

    # --------------------------------------------------------
    # خلاصه
    # --------------------------------------------------------

    summary_score = max(
        jaccard_similarity(
            summary_a,
            summary_b,
        ),
        sequence_similarity(
            summary_a,
            summary_b,
        ),
    )

    # --------------------------------------------------------
    # واژه‌های متمایز
    # --------------------------------------------------------

    distinctive_score = (
        distinctive_similarity(
            title_a
            + " "
            + summary_a,
            title_b
            + " "
            + summary_b,
        )
    )

    # --------------------------------------------------------
    # شباهت کاراکتری
    # --------------------------------------------------------

    character_score = (
        sequence_similarity(
            title_a
            + " "
            + summary_a,
            title_b
            + " "
            + summary_b,
        )
    )

    # --------------------------------------------------------
    # امتیاز نهایی
    # --------------------------------------------------------

    final_score = (
        title_score
        * TITLE_WEIGHT
        + summary_score
        * SUMMARY_WEIGHT
        + distinctive_score
        * DISTINCTIVE_WEIGHT
        + character_score
        * CHARACTER_WEIGHT
    )

    return round(
        final_score * 100,
        2,
    ), {
        "title": round(
            title_score * 100,
            2,
        ),
        "summary": round(
            summary_score * 100,
            2,
        ),
        "distinctive": round(
            distinctive_score * 100,
            2,
        ),
        "character": round(
            character_score * 100,
            2,
        ),
    }


# ============================================================
# EVENT MATCH
# ============================================================

def event_matches(
    item,
    event,
):

    try:

        published_at = float(
            event.get(
                "published_at",
                0,
            )
        )

        item_timestamp = (
            item["published"]
            .timestamp()
        )

        distance_hours = abs(
            item_timestamp
            - published_at
        ) / 3600

        if (
            distance_hours
            > EVENT_MAX_AGE_HOURS
        ):

            return (
                False,
                0,
                {},
                "event too old",
            )

    except Exception:

        distance_hours = 0

    reference = {
        "title": event.get(
            "title",
            "",
        ),
        "summary": event.get(
            "summary",
            "",
        ),
    }

    score, details = (
        event_similarity(
            item,
            reference,
        )
    )

    # --------------------------------------------------------
    # امتیاز خیلی بالا
    # --------------------------------------------------------

    if score >= EVENT_DUPLICATE_THRESHOLD:

        return (
            True,
            score,
            details,
            "duplicate event",
        )

    # --------------------------------------------------------
    # امتیاز متوسط
    # --------------------------------------------------------

    if score >= EVENT_PROBABLE_THRESHOLD:

        # اگر شهر/استان/کلیدواژه اصلی
        # نیز مشترک باشد، تکراری محسوب می‌شود.

        item_tokens = (
            distinctive_words(
                item["title"]
                + " "
                + item["summary"]
            )
        )

        event_tokens = (
            distinctive_words(
                event.get(
                    "title",
                    "",
                )
                + " "
                + event.get(
                    "summary",
                    "",
                )
            )
        )

        overlap = (
            len(
                item_tokens
                & event_tokens
            )
            / max(
                len(
                    item_tokens
                    | event_tokens
                ),
                1,
            )
        )

        if overlap >= 0.35:

            return (
                True,
                score,
                details,
                "probable duplicate event",
            )

    return (
        False,
        score,
        details,
        "new event",
    )


# ============================================================
# EVENT CLUSTERING
# ============================================================

def cluster_candidates(
    candidates,
    existing_events,
):

    clusters = []

    # --------------------------------------------------------
    # ابتدا خبرهای جدید را بر اساس شباهت
    # به گروه‌های داخلی تقسیم می‌کنیم.
    # --------------------------------------------------------

    for item in candidates:

        assigned = False

        best_cluster = None
        best_score = 0

        for cluster in clusters:

            reference = cluster[0]

            score, _ = (
                event_similarity(
                    item,
                    reference,
                )
            )

            if score > best_score:

                best_score = score
                best_cluster = cluster

        if (
            best_cluster is not None
            and best_score
            >= EVENT_PROBABLE_THRESHOLD
        ):

            best_cluster.append(
                item
            )

            assigned = True

            log.info(
                "EVENT CLUSTER MERGE: "
                f"{item['title']} "
                f"score={best_score}"
            )

        if not assigned:

            clusters.append(
                [item]
            )

    # --------------------------------------------------------
    # هر گروه یک event candidate است.
    # --------------------------------------------------------

    return clusters


# ============================================================
# BEST VERSION OF EVENT
# ============================================================

def candidate_quality(item):

    local = item.get(
        "local_score",
        0,
    )

    fresh = item.get(
        "freshness",
        0,
    )

    summary_length = len(
        item.get(
            "summary",
            "",
        )
    )

    # وجود خلاصه کامل‌تر امتیاز می‌دهد
    summary_quality = min(
        summary_length / 250,
        1.0,
    ) * 15

    # نسخه نهایی
    return (
        local
        + fresh
        + summary_quality
    )


def select_best_version(
    cluster
):

    ranked = sorted(
        cluster,
        key=lambda item: (
            candidate_quality(item),
            item.get(
                "local_score",
                0,
            ),
            item.get(
                "freshness",
                0,
            ),
            item["published"],
        ),
        reverse=True,
    )

    selected = ranked[0]

    if len(cluster) > 1:

        log.info(
            "EVENT GROUP "
            f"contains {len(cluster)} "
            "sources:"
        )

        for candidate in ranked:

            log.info(
                "  SOURCE VERSION: "
                f"[{candidate['source']}] "
                f"{candidate['title']} "
                f"quality="
                f"{candidate_quality(candidate):.2f}"
            )

    return selected


# ============================================================
# FRESHNESS
# ============================================================

def freshness_score(
    published
):

    now = datetime.now(
        timezone.utc
    )

    try:

        age_hours = (
            now - published
        ).total_seconds() / 3600

    except Exception:

        return 0

    if age_hours < 0:
        age_hours = 0

    if age_hours >= FRESHNESS_HOURS:
        return 0

    return max(
        0,
        int(
            20
            * (
                1
                - (
                    age_hours
                    / FRESHNESS_HOURS
                )
            )
        ),
    )


# ============================================================
# RSS COLLECTION
# ============================================================

def collect_news():

    now = datetime.now(
        timezone.utc
    )

    max_age = timedelta(
        hours=MAX_NEWS_AGE_HOURS
    )

    items = []

    for (
        source_name,
        source_domain,
        feeds,
    ) in SOURCES:

        for feed_url in feeds:

            try:

                response = SESSION.get(
                    feed_url,
                    timeout=18,
                )

                response.raise_for_status()

                feed = feedparser.parse(
                    response.content
                )

            except Exception as exc:

                log.warning(
                    f"RSS error "
                    f"{source_name}: {exc}"
                )

                continue

            for entry in feed.entries:

                title = clean_text(
                    getattr(
                        entry,
                        "title",
                        "",
                    )
                )

                link = (
                    getattr(
                        entry,
                        "link",
                        "",
                    )
                    .strip()
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

                if not published:
                    continue

                age = now - published

                if (
                    age < timedelta(0)
                    or age > max_age
                ):
                    continue

                summary = make_summary(
                    entry
                )

                if len(summary) > 480:

                    summary = (
                        summary[:477]
                        + "..."
                    )

                items.append({
                    "title": title,
                    "summary": summary,
                    "link": normalize_url(
                        link
                    ),
                    "published": published,
                    "source": source_name,
                    "source_domain": source_domain,
                })

    # --------------------------------------------------------
    # حذف لینک‌های تکراری
    # --------------------------------------------------------

    unique = {}

    for item in items:

        unique[
            item["link"]
        ] = item

    news = sorted(
        unique.values(),
        key=lambda x: x["published"],
        reverse=True,
    )

    return news[
        :MAX_CANDIDATES
    ]


# ============================================================
# PREPARE CANDIDATES
# ============================================================

def prepare_candidates(
    news,
    sent_links,
    sent_titles,
):

    candidates = []

    for item in news:

        normalized_link = normalize_url(
            item["link"]
        )

        # ----------------------------------------------------
        # LINK DUPLICATE
        # ----------------------------------------------------

        if normalized_link in sent_links:

            log.info(
                "SKIP LINK DUPLICATE: "
                f"{item['title']}"
            )

            continue

        # ----------------------------------------------------
        # TITLE DUPLICATE
        # ----------------------------------------------------

        duplicate_title = False

        for old_title in sent_titles:

            score = max(
                sequence_similarity(
                    item["title"],
                    old_title,
                ),
                jaccard_similarity(
                    item["title"],
                    old_title,
                ),
            )

            if score >= 0.75:

                duplicate_title = True

                log.info(
                    "SKIP TITLE DUPLICATE: "
                    f"{item['title']} "
                    f"score={score:.2f}"
                )

                break

        if duplicate_title:
            continue

        # ----------------------------------------------------
        # LOCAL FILTER
        # ----------------------------------------------------

        local = local_score(
            item["title"],
            item["summary"],
        )

        valid, reason = (
            is_real_local_news(
                item["title"],
                item["summary"],
                local,
            )
        )

        if not valid:

            log.info(
                "SKIP LOCAL FILTER "
                f"[{reason}]: "
                f"{item['title']}"
            )

            continue

        # ----------------------------------------------------
        # FRESHNESS
        # ----------------------------------------------------

        fresh = freshness_score(
            item["published"]
        )

        item["local_score"] = local
        item["freshness"] = fresh
        item["filter_reason"] = reason

        candidates.append(
            item
        )

    return candidates


# ============================================================
# REMOVE EVENTS ALREADY PUBLISHED
# ============================================================

def remove_published_events(
    candidates,
    events,
):

    remaining = []

    for item in candidates:

        matched_event = None
        matched_score = 0
        matched_details = {}
        matched_reason = ""

        for event in events:

            (
                matched,
                score,
                details,
                reason,
            ) = event_matches(
                item,
                event,
            )

            if (
                matched
                and score > matched_score
            ):

                matched_event = event
                matched_score = score
                matched_details = details
                matched_reason = reason

        if matched_event is not None:

            log.info(
                "SKIP ALREADY PUBLISHED EVENT: "
                f"{item['title']}"
            )

            log.info(
                "  matched event: "
                f"{matched_event.get('title', '')}"
            )

            log.info(
                "  event score: "
                f"{matched_score}"
            )

            log.info(
                "  details: "
                f"{matched_details}"
            )

            log.info(
                "  reason: "
                f"{matched_reason}"
            )

            continue

        remaining.append(
            item
        )

    return remaining


# ============================================================
# SELECT BEST EVENT
# ============================================================

def select_best_event(
    candidates
):

    if not candidates:
        return None

    clusters = cluster_candidates(
        candidates,
        [],
    )

    event_versions = []

    for cluster in clusters:

        selected = (
            select_best_version(
                cluster
            )
        )

        selected = dict(
            selected
        )

        selected[
            "event_size"
        ] = len(cluster)

        selected[
            "event_sources"
        ] = list({
            x["source"]
            for x in cluster
        })

        event_versions.append(
            selected
        )

    # --------------------------------------------------------
    # انتخاب بهترین رویداد برای انتشار
    # --------------------------------------------------------

    event_versions.sort(
        key=lambda item: (
            item.get(
                "local_score",
                0,
            ),
            item.get(
                "freshness",
                0,
            ),
            candidate_quality(
                item
            ),
            item["published"],
        ),
        reverse=True,
    )

    return event_versions[0]


# ============================================================
# SAVE EVENT
# ============================================================

def register_published_event(
    item
):

    events = load_events()

    event = {
        "event_id": make_event_id(
            item
        ),
        "title": item[
            "title"
        ],
        "summary": item[
            "summary"
        ],
        "link": item[
            "link"
        ],
        "source": item[
            "source"
        ],
        "sources": item.get(
            "event_sources",
            [
                item["source"]
            ],
        ),
        "published_at": item[
            "published"
        ].timestamp(),
        "registered_at": time.time(),
        "local_score": item.get(
            "local_score",
            0,
        ),
    }

    events.insert(
        0,
        event,
    )

    save_events(
        events
    )


# ============================================================
# OG IMAGE
# ============================================================

def get_og_image(
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

        for prop in [
            "og:image",
            "twitter:image",
        ]:

            tag = (
                soup.find(
                    "meta",
                    property=prop,
                )
                or soup.find(
                    "meta",
                    attrs={
                        "name": prop
                    },
                )
            )

            if (
                tag
                and tag.get(
                    "content"
                )
            ):

                image = (
                    tag[
                        "content"
                    ].strip()
                )

                if image.startswith(
                    "//"
                ):

                    image = (
                        "https:"
                        + image
                    )

                return image

    except Exception as exc:

        log.warning(
            f"OG image error: "
            f"{exc}"
        )

    return None


# ============================================================
# SAFE CUT
# ============================================================

def safe_cut(
    text,
    max_length,
):

    if not text:
        return ""

    if len(text) <= max_length:
        return text

    if max_length <= 3:
        return text[
            :max_length
        ]

    shortened = (
        text[
            : max_length - 3
        ]
        .rsplit(
            " ",
            1,
        )[0]
    )

    return shortened + "..."


# ============================================================
# MESSAGE
# ============================================================

def build_message(
    item
):

    text = (
        "🚨 استان سیستان و بلوچستان\n\n"
        f"📰 {item['title']}\n\n"
    )

    if item.get(
        "summary"
    ):

        text += (
            item["summary"]
            + "\n\n"
        )

    text += (
        f"🗞 منبع: {item['source']}\n\n"
        "📱 جهان‌تاب"
    )

    return text


def build_keyboard(
    url
):

    return json.dumps(
        {
            "inline_keyboard": [
                [
                    {
                        "text": "🔗 مشاهده خبر",
                        "url": url,
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
# BALE API
# ============================================================

def bale_api(
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

    response.raise_for_status()

    result = response.json()

    if not result.get(
        "ok"
    ):

        raise RuntimeError(
            result
        )

    return result


# ============================================================
# PUBLISH ITEM
# ============================================================

def publish_item(
    item
):

    try:

        text = build_message(
            item
        )

        keyboard = build_keyboard(
            item["link"]
        )

        # ----------------------------------------------------
        # OG IMAGE
        # ----------------------------------------------------

        image_url = get_og_image(
            item["link"]
        )

        if image_url:

            try:

                image_response = (
                    SESSION.get(
                        image_url,
                        timeout=12,
                    )
                )

                image_response.raise_for_status()

                content_type = (
                    image_response
                    .headers
                    .get(
                        "Content-Type",
                        "",
                    )
                    .lower()
                )

                image_size = len(
                    image_response.content
                )

                if (
                    content_type.startswith(
                        "image/"
                    )
                    and image_size
                    < 5_000_000
                ):

                    bale_api(
                        "sendPhoto",
                        data={
                            "chat_id": CHAT_ID,
                            "caption": safe_cut(
                                text,
                                MAX_CAPTION_LEN,
                            ),
                            "reply_markup": keyboard,
                        },
                        files={
                            "photo": (
                                "news.jpg",
                                image_response.content,
                            )
                        },
                    )

                    log.info(
                        "Published with image"
                    )

                    return True

            except Exception as exc:

                log.warning(
                    "Photo publish failed: "
                    f"{exc}"
                )

        # ----------------------------------------------------
        # TEXT FALLBACK
        # ----------------------------------------------------

        bale_api(
            "sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": safe_cut(
                    text,
                    MAX_TEXT_LEN,
                ),
                "reply_markup": keyboard,
            },
        )

        log.info(
            "Published as text"
        )

        return True

    except Exception as exc:

        log.error(
            f"Publish failed: "
            f"{exc}"
        )

        return False


# ============================================================
# MAIN
# ============================================================

def main():

    log.info(
        "=" * 70
    )

    log.info(
        "JAHANTAB | جهان‌تاب v9.0 START"
    )

    log.info(
        "Event-based duplicate detection ENABLED"
    )

    log.info(
        "=" * 70
    )

    if not acquire_lock():

        log.warning(
            "Another process is running"
        )

        return

    try:

        # ----------------------------------------------------
        # COOLDOWN
        # ----------------------------------------------------

        if not can_publish():

            log.info(
                "30-minute cooldown active"
            )

            return

        # ----------------------------------------------------
        # LOAD STATE
        # ----------------------------------------------------

        sent_links = (
            load_sent_links()
        )

        sent_titles = (
            load_sent_titles()
        )

        published_events = (
            load_events()
        )

        log.info(
            f"Known links: "
            f"{len(sent_links)}"
        )

        log.info(
            f"Known titles: "
            f"{len(sent_titles)}"
        )

        log.info(
            f"Known events: "
            f"{len(published_events)}"
        )

        # ----------------------------------------------------
        # COLLECT
        # ----------------------------------------------------

        news = collect_news()

        log.info(
            f"Collected RSS items: "
            f"{len(news)}"
        )

        if not news:

            log.info(
                "No RSS news collected"
            )

            return

        # ----------------------------------------------------
        # LOCAL FILTER
        # ----------------------------------------------------

        candidates = prepare_candidates(
            news,
            sent_links,
            sent_titles,
        )

        log.info(
            f"Local candidates: "
            f"{len(candidates)}"
        )

        if not candidates:

            log.info(
                "No suitable local candidates"
            )

            return

        # ----------------------------------------------------
        # EVENT DEDUP AGAINST PREVIOUSLY
        # PUBLISHED EVENTS
        # ----------------------------------------------------

        candidates = (
            remove_published_events(
                candidates,
                published_events,
            )
        )

        log.info(
            "Candidates after published-event "
            f"dedup: {len(candidates)}"
        )

        if not candidates:

            log.info(
                "All candidates belong to "
                "already published events"
            )

            return

        # ----------------------------------------------------
        # GROUP SAME EVENT
        # ----------------------------------------------------

        selected = select_best_event(
            candidates
        )

        if not selected:

            log.info(
                "No event selected"
            )

            return

        # ----------------------------------------------------
        # LOG EVENT
        # ----------------------------------------------------

        log.info(
            "=" * 70
        )

        log.info(
            "SELECTED EVENT"
        )

        log.info(
            f"Title: {selected['title']}"
        )

        log.info(
            f"Source: {selected['source']}"
        )

        log.info(
            f"Local score: "
            f"{selected['local_score']}"
        )

        log.info(
            f"Freshness: "
            f"{selected['freshness']}"
        )

        log.info(
            f"Event versions: "
            f"{selected.get('event_size', 1)}"
        )

        log.info(
            f"Event sources: "
            f"{selected.get('event_sources', [])}"
        )

        log.info(
            "=" * 70
        )

        # ----------------------------------------------------
        # PUBLISH
        # ----------------------------------------------------

        published = publish_item(
            selected
        )

        if not published:

            log.error(
                "News was NOT published."
            )

            log.error(
                "State files will NOT be updated."
            )

            return

        # ----------------------------------------------------
        # SAVE LINK
        # ----------------------------------------------------

        save_sent_link(
            selected["link"]
        )

        # ----------------------------------------------------
        # SAVE TITLE
        # ----------------------------------------------------

        save_sent_title(
            selected["title"]
        )

        # ----------------------------------------------------
        # REGISTER EVENT
        # ----------------------------------------------------

        register_published_event(
            selected
        )

        # ----------------------------------------------------
        # SAVE PUBLISH STATE
        # ----------------------------------------------------

        save_publish_state(
            {
                "last_title": selected[
                    "title"
                ],
                "last_link": selected[
                    "link"
                ],
                "last_source": selected[
                    "source"
                ],
                "last_score": selected[
                    "local_score"
                ],
                "last_event_size": selected.get(
                    "event_size",
                    1,
                ),
                "last_event_sources": selected.get(
                    "event_sources",
                    [
                        selected[
                            "source"
                        ]
                    ],
                ),
            }
        )

        log.info(
            "=" * 70
        )

        log.info(
            "SUCCESS"
        )

        log.info(
            "News published."
        )

        log.info(
            "Link + title + event state saved."
        )

        log.info(
            "=" * 70
        )

    except Exception as exc:

        log.exception(
            f"MAIN ERROR: {exc}"
        )

    finally:

        release_lock()

        log.info(
            "JAHANTAB | END"
        )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()