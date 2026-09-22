import os
import re
import json
import html
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

if not BOT_TOKEN:
    raise RuntimeError("BALE_BOT_TOKEN is not set")

if not CHAT_ID:
    raise RuntimeError("BALE_CHAT_ID is not set")


# ============================================================
# ONLY APPROVED INTERNAL NEWS SOURCES
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
# FORBIDDEN SOCIAL / VIDEO / AGGREGATOR DOMAINS
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
# SISTAN & BALUCHESTAN / MAKRAN
# ============================================================

PROVINCE_TERMS = [
    "سیستان و بلوچستان",
    "سیستان‌ و بلوچستان",
    "سیستان‌وبلوچستان",
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
    "بنت",
    "پیشین",
    "گشت",
    "تفتان",
    "دُرّی",
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
# MAKRAN
# ============================================================

MAKRAN_TERMS = [
    "سواحل مکران",
    "ساحل مکران",
    "مکران",
    "دریای عمان",
    "سواحل دریای عمان",
    "ساحل دریای عمان",
]


# ============================================================
# TERMS THAT INDICATE REAL LOCAL NEWS
# ============================================================

LOCAL_CONTEXT_TERMS = [
    # مدیریت و امور استان
    "استاندار",
    "استانداری",
    "فرماندار",
    "فرمانداری",
    "استانداری سیستان",
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

    # پروژه و توسعه
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

    # آب، برق، کشاورزی و محیط زیست
    "آب",
    "آبرسانی",
    "برق",
    "گاز",
    "کشاورزی",
    "دامداری",
    "صیادی",
    "ماهیگیری",
    "محیط زیست",
    "خشکسالی",

    # مکران و چابهار
    "بندر چابهار",
    "منطقه آزاد چابهار",
    "سواحل مکران",
    "ساحل مکران",
    "دریای عمان",
    "بندر",
    "کشتیرانی",
    "شیلات",
]


# ============================================================
# TOPICS THAT ARE NOT LOCAL NEWS
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

    # هنر و سرگرمی
    "خواننده",
    "بازیگر",
    "سلبریتی",
    "فیلم",
    "سریال",
    "موسیقی",
    "کنسرت",
    "سینما",
    "تلویزیون",
    "کتاب",
    "رمان",
    "آگاتا کریستی",
    "خانم مارپل",
    "مارپل",
    "آلپ",

    # موضوعات عمومی غیرمحلی
    "فال",
    "مد",
    "زیبایی",
    "سبک زندگی",
]


# ============================================================
# ONLY EXCEPTIONAL NATIONAL EVENTS
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
        "(compatible; JahantabNewsBot/4.0)"
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
        if domain.endswith("." + blocked):
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
# SENT STATE
# ============================================================

def load_sent_links():
    if not os.path.exists(STATE_FILE):
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
# LOCAL NEWS FILTER
# ============================================================

def contains_any(text, terms):
    return any(
        term in text
        for term in terms
    )


def count_terms(text, terms):
    return sum(
        1
        for term in terms
        if term in text
    )


def other_province_in_title(title):
    """
    Return another Iranian province found in the title.
    """

    for province in OTHER_PROVINCE_TERMS:

        if province in title:
            return province

    return None


def other_provinces_in_text(text):
    return [
        province
        for province in OTHER_PROVINCE_TERMS
        if province in text
    ]


def local_score(
    title,
    summary,
):
    title = clean_text(title)
    summary = clean_text(summary)

    full_text = (
        title
        + " "
        + summary
    )

    score = 0

    # --------------------------------------------------------
    # STRONG PROVINCE EVIDENCE
    # --------------------------------------------------------

    province_in_title = False

    for term in PROVINCE_TERMS:

        if term in title:
            score += 40
            province_in_title = True

        elif term in summary:
            score += 15

    # --------------------------------------------------------
    # CITY EVIDENCE
    # --------------------------------------------------------

    city_in_title = False

    for term in CITY_TERMS:

        if term in title:
            score += 12
            city_in_title = True

        elif term in summary:
            score += 5

    # --------------------------------------------------------
    # MAKRAN / OMAN SEA
    # --------------------------------------------------------

    for term in MAKRAN_TERMS:

        if term in title:
            score += 25

        elif term in summary:
            score += 10

    # --------------------------------------------------------
    # REAL LOCAL CONTEXT
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
    # OTHER PROVINCE IN TITLE
    # --------------------------------------------------------

    other_title_province = (
        other_province_in_title(title)
    )

    if other_title_province:

        # Another province in title without
        # Sistan & Baluchestan in title is a strong
        # indication that this is not our local news.
        if not contains_any(
            title,
            PROVINCE_TERMS,
        ):
            score -= 100

    # --------------------------------------------------------
    # OTHER PROVINCE IN SUMMARY
    # --------------------------------------------------------

    other_provinces = (
        other_provinces_in_text(full_text)
    )

    if (
        other_provinces
        and not province_in_title
        and not city_in_title
        and not contains_any(
            title,
            MAKRAN_TERMS,
        )
    ):
        score -= 40

    # --------------------------------------------------------
    # UNRELATED TOPICS
    # --------------------------------------------------------

    for term in LOCAL_EXCLUDE_TERMS:

        if term in full_text:
            score -= 60

    # --------------------------------------------------------
    # CITY WITHOUT LOCAL CONTEXT
    # --------------------------------------------------------

    if city_in_title and context_count == 0:
        score -= 25

    return score


def is_real_local_news(
    title,
    summary,
):
    title = clean_text(title)
    summary = clean_text(summary)

    full_text = (
        title
        + " "
        + summary
    )

    # --------------------------------------------------------
    # EMPTY TITLE
    # --------------------------------------------------------

    if not title:
        return False

    # --------------------------------------------------------
    # HARD REJECTION:
    # EXPLICITLY UNRELATED TOPICS
    # --------------------------------------------------------

    for term in LOCAL_EXCLUDE_TERMS:

        if term in full_text:
            return False

    # --------------------------------------------------------
    # LOCAL LOCATION
    # --------------------------------------------------------

    has_province = contains_any(
        full_text,
        PROVINCE_TERMS,
    )

    has_city = contains_any(
        full_text,
        CITY_TERMS,
    )

    has_makran = contains_any(
        full_text,
        MAKRAN_TERMS,
    )

    # --------------------------------------------------------
    # NO LOCAL LOCATION
    # --------------------------------------------------------

    if not (
        has_province
        or has_city
        or has_makran
    ):
        return False

    # --------------------------------------------------------
    # OTHER PROVINCE IN TITLE
    # --------------------------------------------------------

    other_title_province = (
        other_province_in_title(title)
    )

    if other_title_province:

        # Another province is in the title.
        # Unless Sistan & Baluchestan is ALSO explicitly
        # in the title, reject.
        if not contains_any(
            title,
            PROVINCE_TERMS,
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
    # EXPLICIT PROVINCE IN TITLE
    # --------------------------------------------------------

    if contains_any(
        title,
        PROVINCE_TERMS,
    ):
        return score >= 30

    # --------------------------------------------------------
    # MAKRAN IN TITLE
    # --------------------------------------------------------

    if contains_any(
        title,
        MAKRAN_TERMS,
    ):
        return score >= 25

    # --------------------------------------------------------
    # CITY IN TITLE
    # --------------------------------------------------------

    if contains_any(
        title,
        CITY_TERMS,
    ):

        context_count = count_terms(
            full_text,
            LOCAL_CONTEXT_TERMS,
        )

        if context_count < 1:
            return False

        return score >= 15

    # --------------------------------------------------------
    # LOCATION ONLY IN SUMMARY
    # --------------------------------------------------------

    if has_province or has_makran:

        context_count = count_terms(
            full_text,
            LOCAL_CONTEXT_TERMS,
        )

        if context_count < 1:
            return False

        return score >= 15

    return False


# ============================================================
# VERY IMPORTANT NATIONAL NEWS
# ============================================================

def national_score(
    title,
    summary,
):
    text = (
        clean_text(title)
        + " "
        + clean_text(summary)
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

            if is_blocked_url(link):
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
        hours=24
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
# SELECT 3 LOCAL NEWS
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

        candidates.append(item)

    candidates.sort(
        key=lambda x: (
            x["score"],
            x["published"],
        ),
        reverse=True,
    )

    selected = []

    seen_titles = set()

    for item in candidates:

        title_key = re.sub(
            r"\W+",
            "",
            item["title"].lower(),
        )

        if title_key in seen_titles:
            continue

        seen_titles.add(
            title_key
        )

        selected.append(item)

        if len(selected) == 3:
            break

    return selected


# ============================================================
# SELECT ONLY ONE EXCEPTIONAL NATIONAL NEWS
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
        "سیستان و بلوچستان",
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

    return text


# ============================================================
# INLINE LINK BOX
# ============================================================

def make_reply_markup(item):

    return json.dumps(
        {
            "inline_keyboard": [

                # --------------------------------------------
                # NEWS LINK
                # --------------------------------------------

                [
                    {
                        "text": "🔗 مشاهده خبر",
                        "url": item["link"],
                    }
                ],

                # --------------------------------------------
                # SOCIAL LINKS
                # --------------------------------------------

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

    reply_markup = make_reply_markup(
        item
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

        reply_markup = make_reply_markup(
            item
        )

        caption = build_message(
            item
        )

        # Bale caption limit protection
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
# MAIN
# ============================================================

def main():

    print(
        "==================================="
    )

    print(
        "Jahantab Bale News Bot"
    )

    print(
        "Sistan & Baluchestan ONLY"
    )

    print(
        "==================================="
    )

    sent_links = load_sent_links()

    print(
        "Previously sent links: "
        f"{len(sent_links)}"
    )

    all_news = collect_all_news()

    print(
        "Approved-source news: "
        f"{len(all_news)}"
    )

    # --------------------------------------------------------
    # 3 LOCAL NEWS
    # --------------------------------------------------------

    local_news = select_local_news(
        all_news,
        sent_links,
    )

    print(
        "Selected local news: "
        f"{len(local_news)}"
    )

    for item in local_news:

        item["category"] = (
            "سیستان و بلوچستان"
        )

        print(
            "Publishing local: "
            f"[{item['source']}] "
            f"{item['title']}"
        )

        try:

            publish_item(item)

            save_sent_link(
                item["link"]
            )

            sent_links.add(
                item["link"]
            )

            print(
                "Published successfully."
            )

        except Exception as exc:

            print(
                f"Publish failed: "
                f"{exc}"
            )

    # --------------------------------------------------------
    # OPTIONAL: ONE EXCEPTIONAL NATIONAL NEWS
    # --------------------------------------------------------

    national = select_national_news(
        all_news,
        sent_links,
    )

    if national:

        national["category"] = "ایران"

        print(
            "Publishing exceptional national: "
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

            sent_links.add(
                national["link"]
            )

            print(
                "National news published."
            )

        except Exception as exc:

            print(
                f"National publish failed: "
                f"{exc}"
            )

    else:

        print(
            "No exceptional national news."
        )

    print(
        "==================================="
    )

    print(
        "Jahantab Bale News Bot finished."
    )

    print(
        "==================================="
    )


if __name__ == "__main__":
    main()