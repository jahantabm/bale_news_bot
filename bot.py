# -*- coding: utf-8 -*-
"""
============================================================
JAHANTAB | جهان‌تاب
رصدخانه خبری سیستان و بلوچستان
نسخه نهایی v8.0
============================================================

ویژگی‌ها:
- RSS چند منبع خبری
- فیلتر سخت‌گیرانه سیستان و بلوچستان
- تشخیص استان‌های دیگر در عنوان
- تشخیص موقعیت خارجی در عنوان
- جلوگیری از خبرهای ملی/عمومی با اشاره گذرا به استان
- Word Boundary
- ZWNJ → space
- حذف خبرهای تکراری cross-run
- SequenceMatcher + Jaccard
- PID-safe lock
- Prune خودکار state
- تاریخ RSS + fallback email.utils
- امتیازدهی بر اساس ارتباط + تازگی
- لاگ علت رد خبر
- ارسال عکس در صورت وجود
- fallback به sendMessage
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
LOCK_FILE = "jahantab.lock"

PUBLISH_INTERVAL_MINUTES = 30

# فقط خبرهای حداکثر 24 ساعت گذشته
MAX_NEWS_AGE_HOURS = 24

# حداکثر تعداد خبرهای بررسی‌شده
MAX_CANDIDATES = 1000

# محدودیت متن
MAX_CAPTION_LEN = 1000
MAX_TEXT_LEN = 3900

# تعداد عنوان‌های ذخیره‌شده
MAX_TITLES_KEPT = 400

# شباهت عنوان
TITLE_DUP_THRESHOLD = 0.65

# برای خبرهای صرفاً شهری، حداقل امتیاز
MIN_CITY_SCORE = 25

# برای خبرهای استانی
MIN_PROVINCE_SCORE = 30

# برای خبرهای خاص مثل هامون، مکران و...
MIN_SPECIAL_SCORE = 28

# حداکثر فاصله زمانی که در امتیاز تازگی اثر کامل دارد
FRESHNESS_HOURS = 24


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
            "JahantabBot/8.0"
        ),
        "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.5",
    })

    retry = Retry(
        total=3,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=12,
        pool_maxsize=24,
    )

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


SESSION = build_session()


# ============================================================
# SOURCES
# ============================================================

SOURCES = [
    (
        "ایرنا",
        "irna.ir",
        ["https://www.irna.ir/rss"],
    ),
    (
        "ایسنا",
        "isna.ir",
        ["https://www.isna.ir/rss"],
    ),
    (
        "مهر",
        "mehrnews.com",
        ["https://www.mehrnews.com/rss"],
    ),
    (
        "فارس",
        "farsnews.ir",
        ["https://www.farsnews.ir/rss"],
    ),
    (
        "ایلنا",
        "ilna.ir",
        ["https://www.ilna.ir/rss"],
    ),
    (
        "تسنیم",
        "tasnimnews.com",
        [
            "https://www.tasnimnews.com/fa/rss/feed/0/8/0/"
            "مهمترین-اخبار-تسنیم"
        ],
    ),
    (
        "تابناک",
        "tabnak.ir",
        ["https://www.tabnak.ir/fa/rss/allnews"],
    ),
    (
        "عصر ایران",
        "asriran.com",
        ["https://www.asriran.com/fa/rss/allnews"],
    ),
    (
        "فرارو",
        "fararu.com",
        ["https://fararu.com/fa/rss"],
    ),
    (
        "جهان نیوز",
        "jahannews.com",
        ["https://www.jahannews.com/rss"],
    ),
    (
        "خبرآنلاین",
        "khabaronline.ir",
        ["https://www.khabaronline.ir/rss"],
    ),
    (
        "همشهری",
        "hamshahrionline.ir",
        ["https://www.hamshahrionline.ir/rss"],
    ),
    (
        "جام جم",
        "jamejamonline.ir",
        ["https://jamejamonline.ir/rss"],
    ),
    (
        "باشگاه خبرنگاران جوان",
        "yjc.ir",
        ["https://www.yjc.ir/fa/rss/allnews"],
    ),
    (
        "انتخاب",
        "entekhab.ir",
        ["https://www.entekhab.ir/fa/rss"],
    ),
    (
        "خبرگزاری صداوسیما",
        "iribnews.ir",
        ["https://www.iribnews.ir/fa/rss"],
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


# ============================================================
# SPECIAL LOCAL TERMS
# ============================================================

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


# ============================================================
# CULTURE
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


# ============================================================
# LOCAL CONTEXT
# ============================================================

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
    "زیرساخت",

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


# ============================================================
# OTHER PROVINCES
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
# FOREIGN
# ============================================================

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


# ============================================================
# GENERAL EXCLUDES
# ============================================================

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

    value = html.unescape(str(value))

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
    """
    ZWNJ به space تبدیل می‌شود.
    """

    text = clean_text(text)

    text = text.replace("\u200c", " ")
    text = text.replace("\u200e", "")
    text = text.replace("\u200f", "")

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
    text = normalize_persian_text(text).lower()

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


def term_in(text, term):
    if not term:
        return False

    return re.search(
        rf"(?<!\w){re.escape(term)}(?!\w)",
        text,
    ) is not None


def has_any(text, terms):
    normalized_text = normalize_persian_text(text)

    for term in terms:
        normalized_term = normalize_persian_text(term)

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
        domain.endswith("." + blocked)
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
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
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
            data.get("time", 0)
        )

        lock_pid = int(
            data.get("pid", 0)
        )

    except Exception:
        return False

    # اگر قفل تازه است، دست نزن
    if time.time() - lock_time <= 600:
        return False

    # قفل قدیمی است؛ PID را بررسی کن
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
        os.remove(LOCK_FILE)

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
            data.get("pid", 0)
        ) != os.getpid():

            return

        os.remove(LOCK_FILE)

    except Exception:
        pass


# ============================================================
# STATE
# ============================================================

def prune_file(path, keep):
    try:
        if not os.path.exists(path):
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
                normalize_url(line.strip())
                for line in f
                if line.strip()
            }

    except Exception:
        return set()


def save_sent_link(link):
    link = normalize_url(link)

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
# PUBLISH STATE
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


def save_publish_state(extra=None):
    state = load_publish_state()

    state["last_publish"] = time.time()

    if extra:
        state.update(extra)

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

    elapsed = time.time() - last_publish

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
            .rsplit(" ", 1)[0]
            + "..."
        )

    return text


# ============================================================
# LOCATION CHECKS
# ============================================================

def other_province_in_title(title):
    t = normalize_persian_text(
        title
    )

    # اگر خود استان ما در عنوان هست،
    # استان دیگر را به‌تنهایی منفی نکن
    if has_any(
        t,
        PROVINCE_TERMS,
    ):
        return False

    # اگر شهر محلی در عنوان هست،
    # اجازه عبور بده
    if has_any(
        t,
        CITY_TERMS,
    ):
        return False

    return has_any(
        t,
        OTHER_PROVINCE_TERMS,
    )


def foreign_location_in_title(title):
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

    # استان دیگر در عنوان
    if other_province_in_title(
        title
    ):
        score -= 120

    # کشور/شهر خارجی در عنوان
    if foreign_location_in_title(
        title
    ):
        score -= 120

    # استان
    score += score_terms(
        full,
        normalized_title,
        PROVINCE_TERMS,
        45,
        12,
    )

    # شهر
    score += score_terms(
        full,
        normalized_title,
        CITY_TERMS,
        20,
        4,
    )

    # نشانه‌های خاص منطقه
    score += score_terms(
        full,
        normalized_title,
        SPECIAL_LOCAL_TERMS,
        32,
        10,
    )

    # فرهنگ
    score += score_terms(
        full,
        normalized_title,
        CULTURE_TERMS,
        32,
        10,
    )

    # زمینه محلی
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

def title_locality_type(title):
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
# STRICT LOCAL NEWS FILTER
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

    # --------------------------------------------------------
    # استان دیگر در عنوان
    # --------------------------------------------------------

    if other_province_in_title(
        title
    ):
        return False, "other province in title"

    # --------------------------------------------------------
    # موقعیت خارجی در عنوان
    # --------------------------------------------------------

    if foreign_location_in_title(
        title
    ):
        return False, "foreign location in title"

    # --------------------------------------------------------
    # محتوای عمومی/نامرتبط
    # --------------------------------------------------------

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
            return False, (
                f"general exclude: {term}"
            )

    # --------------------------------------------------------
    # نشانه‌های محلی
    # --------------------------------------------------------

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
        return False, "no local signal"

    # --------------------------------------------------------
    # امتیاز
    # --------------------------------------------------------

    if score is None:
        score = local_score(
            title,
            summary,
        )

    title_type = title_locality_type(
        title
    )

    # --------------------------------------------------------
    # عنوان با نام استان
    # --------------------------------------------------------

    if title_type == "province":

        if score < MIN_PROVINCE_SCORE:
            return False, (
                f"province score too low: {score}"
            )

        return True, "province title"

    # --------------------------------------------------------
    # عنوان با نشانه خاص
    # --------------------------------------------------------

    if title_type == "special":

        if score < MIN_SPECIAL_SCORE:
            return False, (
                f"special score too low: {score}"
            )

        return True, "special local title"

    # --------------------------------------------------------
    # عنوان فرهنگی
    # --------------------------------------------------------

    if title_type == "culture":

        if score < 25:
            return False, (
                f"culture score too low: {score}"
            )

        return True, "culture title"

    # --------------------------------------------------------
    # عنوان شهری
    # --------------------------------------------------------

    if title_type == "city":

        # شهر در عنوان + حداقل یک زمینه محلی
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

        # اگر فقط نام شهر آمده ولی
        # هیچ زمینه محلی وجود ندارد
        if context_count == 0:

            # فقط وقتی اجازه بده که
            # استان/موضوع خاص هم در متن باشد
            if not (
                has_province
                or has_special
                or has_culture
            ):
                return False, (
                    "city mentioned without local context"
                )

        if score < MIN_CITY_SCORE:
            return False, (
                f"city score too low: {score}"
            )

        return True, "city title"

    # --------------------------------------------------------
    # نشانه محلی فقط در خلاصه
    # --------------------------------------------------------

    # این بخش سخت‌گیرانه است.
    # صرفاً اشاره در summary کافی نیست.
    if not (
        has_province
        or has_special
        or has_culture
    ):
        return False, (
            "local signal only in weak body context"
        )

    if score < 30:
        return False, (
            f"body local score too low: {score}"
        )

    return True, "body local signal"


# ============================================================
# TITLE SIMILARITY
# ============================================================

def title_similarity(
    a,
    b,
):
    na = normalize_title(a)
    nb = normalize_title(b)

    if not na or not nb:
        return 0.0

    sequence_ratio = (
        difflib.SequenceMatcher(
            None,
            na,
            nb,
        ).ratio()
    )

    sa = set(
        na.split()
    )

    sb = set(
        nb.split()
    )

    jaccard = (
        len(sa & sb)
        / max(
            len(sa | sb),
            1,
        )
    )

    return max(
        sequence_ratio,
        jaccard,
    )


def is_duplicate(
    title,
    recent_titles,
):
    for old_title in recent_titles:

        similarity = title_similarity(
            title,
            old_title,
        )

        if similarity >= TITLE_DUP_THRESHOLD:
            return True

    return False


# ============================================================
# FRESHNESS
# ============================================================

def freshness_score(
    published,
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

    # حداکثر 20 امتیاز
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
# SELECT BEST
# ============================================================

def select_best(
    news,
    sent_links,
    sent_titles,
):
    candidates = []

    for item in news:

        # ----------------------------------------------------
        # لینک قبلاً منتشر شده
        # ----------------------------------------------------

        normalized_link = normalize_url(
            item["link"]
        )

        if normalized_link in sent_links:
            log.info(
                f"SKIP duplicate link: "
                f"{item['title']}"
            )
            continue

        # ----------------------------------------------------
        # عنوان تکراری
        # ----------------------------------------------------

        if is_duplicate(
            item["title"],
            sent_titles,
        ):

            log.info(
                f"SKIP duplicate title: "
                f"{item['title']}"
            )

            continue

        # ----------------------------------------------------
        # local score
        # ----------------------------------------------------

        local = local_score(
            item["title"],
            item["summary"],
        )

        is_local, reason = (
            is_real_local_news(
                item["title"],
                item["summary"],
                local,
            )
        )

        if not is_local:

            log.info(
                f"SKIP local filter "
                f"[{reason}]: "
                f"{item['title']}"
            )

            continue

        # ----------------------------------------------------
        # freshness
        # ----------------------------------------------------

        fresh = freshness_score(
            item["published"]
        )

        # ----------------------------------------------------
        # امتیاز نهایی
        # ----------------------------------------------------

        final_score = (
            local
            + fresh
        )

        candidate = dict(
            item
        )

        candidate["local_score"] = local
        candidate["freshness"] = fresh
        candidate["score"] = final_score
        candidate["filter_reason"] = reason

        candidates.append(
            candidate
        )

    if not candidates:
        return None

    # --------------------------------------------------------
    # ابتدا امتیاز نهایی
    # سپس امتیاز محلی
    # سپس تازگی
    # --------------------------------------------------------

    candidates.sort(
        key=lambda item: (
            item["score"],
            item["local_score"],
            item["freshness"],
            item["published"],
        ),
        reverse=True,
    )

    selected = candidates[0]

    log.info(
        "BEST candidate: "
        f"score={selected['score']} "
        f"local={selected['local_score']} "
        f"fresh={selected['freshness']} "
        f"title={selected['title']}"
    )

    return selected


# ============================================================
# OG IMAGE
# ============================================================

def get_og_image(url):
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
                and tag.get("content")
            ):

                return tag[
                    "content"
                ].strip()

    except Exception as exc:

        log.warning(
            f"OG image error: {exc}"
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
        return text[:max_length]

    return (
        text[: max_length - 3]
        .rsplit(" ", 1)[0]
        + "..."
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
        f"🗞 منبع: {item['source']}\n\n"
        "📱 جهان‌تاب"
    )

    return text


def build_keyboard(url):
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

    if not result.get("ok"):
        raise RuntimeError(
            result
        )

    return result


# ============================================================
# PUBLISH ITEM
# ============================================================

def publish_item(item):
    """
    ارسال هر خبر در try/except مستقل.
    """

    try:

        text = build_message(
            item
        )

        keyboard = build_keyboard(
            item["link"]
        )

        # ----------------------------------------------------
        # تلاش برای عکس
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
                    f"Photo publish failed: "
                    f"{exc}"
                )

        # ----------------------------------------------------
        # fallback text
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
        "=" * 60
    )

    log.info(
        "JAHANTAB | جهان‌تاب v8.0 START"
    )

    log.info(
        "=" * 60
    )

    if not acquire_lock():

        log.warning(
            "Another process is running"
        )

        return

    try:

        # ----------------------------------------------------
        # Cooldown
        # ----------------------------------------------------

        if not can_publish():

            log.info(
                "30-minute cooldown active"
            )

            return

        # ----------------------------------------------------
        # Load state
        # ----------------------------------------------------

        sent_links = (
            load_sent_links()
        )

        sent_titles = (
            load_sent_titles()
        )

        # ----------------------------------------------------
        # Collect
        # ----------------------------------------------------

        news = collect_news()

        log.info(
            f"Collected news: "
            f"{len(news)}"
        )

        # ----------------------------------------------------
        # Select
        # ----------------------------------------------------

        selected = select_best(
            news,
            sent_links,
            sent_titles,
        )

        if not selected:

            log.info(
                "No suitable local "
                "Sistan & Baluchestan "
                "news found"
            )

            return

        log.info(
            f"Selected: "
            f"[{selected['source']}] "
            f"{selected['title']}"
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
            f"Final score: "
            f"{selected['score']}"
        )

        # ----------------------------------------------------
        # Publish
        # ----------------------------------------------------

        published = publish_item(
            selected
        )

        if not published:

            log.error(
                "News was NOT published; "
                "state files will NOT be updated"
            )

            return

        # ----------------------------------------------------
        # Save state ONLY after successful publish
        # ----------------------------------------------------

        save_sent_link(
            selected["link"]
        )

        save_sent_title(
            selected["title"]
        )

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
                    "score"
                ],
            }
        )

        log.info(
            "Successfully published "
            "and state saved"
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