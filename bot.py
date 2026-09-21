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
# OFFICIAL CHANNELS
# ============================================================

TELEGRAM_LINK = "https://t.me/Jahantab_news"
BALE_LINK = "https://ble.ir/jahantabnews"
SOROUSH_LINK = "https://splus.ir/jahantabnews"


# ============================================================
# APPROVED INTERNAL NEWS SOURCES
# ============================================================

APPROVED_DOMAINS = {
    "irna.ir",
    "isna.ir",
    "mehrnews.com",
    "tasnimnews.com",
    "farsnews.ir",
    "tabnak.ir",
    "asriran.com",
    "fararu.com",
    "jahannews.com",
    "khabarfouri.com",
    "akharinkhabar.ir",
    "roozplus.com",
    "khabaronline.ir",
    "ilna.ir",
    "iribnews.ir",
    "iribnews.com",
}


# ============================================================
# RSS FEEDS
# ============================================================

RSS_FEEDS = [
    {
        "name": "ایرنا",
        "url": "https://www.irna.ir/rss",
    },
    {
        "name": "ایسنا",
        "url": "https://www.isna.ir/rss",
    },
    {
        "name": "مهر",
        "url": "https://www.mehrnews.com/rss",
    },
    {
        "name": "فارس",
        "url": "https://www.farsnews.ir/rss",
    },
    {
        "name": "ایلنا",
        "url": "https://www.ilna.ir/rss",
    },
    {
        "name": "تابناک",
        "url": "https://www.tabnak.ir/fa/rss/allnews",
    },
    {
        "name": "عصر ایران",
        "url": "https://www.asriran.com/fa/rss/allnews",
    },
    {
        "name": "فرارو",
        "url": "https://fararu.com/fa/rss",
    },
    {
        "name": "خبرآنلاین",
        "url": "https://www.khabaronline.ir/rss",
    },
]


# ============================================================
# SIستان و بلوچستان
# ============================================================

PROVINCE_TERMS = [
    "سیستان و بلوچستان",
    "سیستان‌ و بلوچستان",
    "سیستان‌وبلوچستان",
    "سیستان بلوچستان",
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
    "لاشار",
    "نوک‌آباد",
    "گشت",
    "پلان",
    "تلنگ",
    "زرآباد",
    "کورین",
    "پیشین",
]


MAKRAN_TERMS = [
    "سواحل مکران",
    "ساحل مکران",
    "مکران",
    "دریای عمان",
]


# ============================================================
# WORDS THAT SHOULD NEVER ENTER LOCAL NEWS
# ============================================================

SPORT_TERMS = [
    "فوتبال",
    "تیم ملی",
    "جام جهانی",
    "لیگ برتر",
    "لیگ قهرمانان",
    "پرسپولیس",
    "استقلال",
    "سپاهان",
    "تراکتور",
    "سردار آزمون",
    "مهدی طارمی",
    "والیبال",
    "بسکتبال",
    "کشتی",
    "تنیس",
    "نسکار",
    "NASCAR",
]


ENTERTAINMENT_TERMS = [
    "بازیگر",
    "خواننده",
    "سلبریتی",
    "سینما",
    "فیلم",
    "سریال",
    "موسیقی",
    "کنسرت",
    "تلویزیون",
]


# ============================================================
# VERY IMPORTANT NATIONAL EVENTS
# ============================================================

NATIONAL_KEYWORDS = [
    "جنگ ایران و آمریکا",
    "جنگ ایران و اسرائیل",
    "جنگ ایران آمریکا",
    "جنگ ایران اسرائیل",

    "درگیری ایران و آمریکا",
    "درگیری ایران و اسرائیل",
    "درگیری ایران با آمریکا",
    "درگیری ایران با اسرائیل",

    "حمله آمریکا به ایران",
    "حمله اسرائیل به ایران",
    "حمله نظامی به ایران",
    "حمله هوایی به ایران",
    "حمله موشکی به ایران",

    "حمله ایران به اسرائیل",
    "حمله ایران به آمریکا",
    "حمله ایران به پایگاه آمریکا",
    "حمله ایران به پایگاه‌های آمریکا",

    "حمله به تأسیسات هسته‌ای ایران",
    "حمله به تاسیسات هسته‌ای ایران",
    "حمله به تأسیسات ایران",
    "حمله به تاسیسات ایران",

    "بمباران ایران",
    "بمباران اسرائیل",
    "بمباران آمریکا",

    "موشک ایران",
    "موشک‌های ایران",
    "موشک به اسرائیل",

    "پایگاه آمریکا",
    "پایگاه‌های آمریکا",
    "پایگاه آمریکایی",

    "آتش‌بس ایران و اسرائیل",
    "آتش‌بس ایران و آمریکا",
    "آتش بس ایران و اسرائیل",
    "آتش بس ایران و آمریکا",

    "مذاکرات ایران و آمریکا",
    "توافق ایران و آمریکا",

    "اعلام جنگ",
    "آغاز جنگ",
    "پایان جنگ",

    "عملیات نظامی علیه ایران",
    "عملیات نظامی اسرائیل علیه ایران",
    "عملیات نظامی آمریکا علیه ایران",

    "ترور مقام ایرانی",
    "ترور فرمانده ایرانی",

    "حمله به مراکز نظامی ایران",
    "حمله به پایگاه نظامی ایران",

    "شرایط جنگی",
]


NATIONAL_CONFIRMATION = [
    "ایران",
    "ایرانی",
    "تهران",
    "اسرائیل",
    "اسرائیلی",
    "آمریکا",
    "آمریکایی",
    "سپاه",
    "ارتش",
    "نیروهای مسلح",
]


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(value):

    if not value:
        return ""

    value = html.unescape(value)

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


# ============================================================
# URL HELPERS
# ============================================================

def normalize_url(url):

    if not url:
        return ""

    url = url.strip()

    url = re.sub(
        r"[?&](utm_[^&]+|fbclid|gclid)=[^&]*",
        "",
        url,
    )

    return url.rstrip("?&")


def get_domain(url):

    try:

        domain = urlparse(
            url
        ).netloc.lower()

        return domain.removeprefix(
            "www."
        )

    except Exception:

        return ""


def is_approved_domain(url):

    domain = get_domain(url)

    if not domain:
        return False

    if domain in APPROVED_DOMAINS:
        return True

    return any(
        domain.endswith(
            "." + approved
        )
        for approved in APPROVED_DOMAINS
    )


# ============================================================
# STATE
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

        if getattr(
            entry,
            "published_parsed",
            None,
        ):

            import calendar

            timestamp = calendar.timegm(
                entry.published_parsed
            )

            return datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            )

        if getattr(
            entry,
            "updated_parsed",
            None,
        ):

            import calendar

            timestamp = calendar.timegm(
                entry.updated_parsed
            )

            return datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            )

    except Exception:
        pass

    return None


# ============================================================
# SUMMARY
# ============================================================

def make_summary(entry):

    description = ""

    if getattr(
        entry,
        "summary",
        None,
    ):

        description = clean_text(
            entry.summary
        )

    if not description and getattr(
        entry,
        "description",
        None,
    ):

        description = clean_text(
            entry.description
        )

    if not description:
        return ""

    description = re.sub(
        r"\s*\.\.\.\s*$",
        "",
        description,
    )

    if len(description) > 500:

        description = (
            description[:497]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return description


# ============================================================
# IMAGE
# ============================================================

def get_image_from_article(url):

    if not url:
        return None

    try:

        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent":
                    "Mozilla/5.0 JahantabNewsBot/1.0"
            },
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

        if image and image.get(
            "content"
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

        if image and image.get(
            "content"
        ):

            return image[
                "content"
            ].strip()

    except Exception as exc:

        print(
            f"Image lookup failed: {exc}"
        )

    return None


# ============================================================
# RSS
# ============================================================

def fetch_feed(source):

    try:

        response = requests.get(
            source["url"],
            timeout=20,
            headers={
                "User-Agent":
                    "Mozilla/5.0 JahantabNewsBot/1.0"
            },
        )

        response.raise_for_status()

        feed = feedparser.parse(
            response.content
        )

        print(
            f"{source['name']}: "
            f"{len(feed.entries)} entries"
        )

        return feed

    except Exception as exc:

        print(
            f"{source['name']} feed error: "
            f"{exc}"
        )

        return None


# ============================================================
# STRICT LOCAL FILTER
# ============================================================

def local_score(
    title,
    summary,
):

    title = clean_text(
        title
    )

    summary = clean_text(
        summary
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # The LOCALITY must be in the TITLE.
    # Mentioning Zahedan/Chabahar only in the body
    # is NOT enough.
    # --------------------------------------------------------

    title_local = False
    score = 0

    for term in PROVINCE_TERMS:

        if term in title:

            title_local = True
            score += 50

    for term in CITY_TERMS:

        if term in title:

            title_local = True
            score += 30

    # --------------------------------------------------------
    # Makran / Oman Sea
    # --------------------------------------------------------

    for term in MAKRAN_TERMS:

        if term in title:

            title_local = True
            score += 35

    # --------------------------------------------------------
    # If no local location exists in TITLE,
    # reject immediately.
    # --------------------------------------------------------

    if not title_local:
        return 0

    # --------------------------------------------------------
    # Reject sports
    # --------------------------------------------------------

    for term in SPORT_TERMS:

        if term in title:

            return 0

    # --------------------------------------------------------
    # Reject entertainment
    # --------------------------------------------------------

    for term in ENTERTAINMENT_TERMS:

        if term in title:

            return 0

    # --------------------------------------------------------
    # Extra protection against generic national stories
    # --------------------------------------------------------

    generic_national_terms = [
        "رئیس جمهور",
        "هیئت دولت",
        "دولت",
        "مجلس",
        "نمایندگان",
        "وزیر",
        "وزارتخانه",
        "بانک مرکزی",
        "بورس",
        "ارز",
        "دلار",
        "خودرو",
        "قیمت",
        "انتخابات",
    ]

    # If the title is clearly national and
    # local place is only incidental, reject.
    #
    # We only apply this when the title contains
    # no strong local action/subject.

    strong_local_subjects = [
        "استاندار",
        "استان",
        "فرماندار",
        "شهردار",
        "شهرستان",
        "بندر",
        "بندرگاه",
        "منطقه آزاد",
        "دانشگاه",
        "مدرسه",
        "بیمارستان",
        "نیروی انتظامی",
        "پلیس",
        "هلال احمر",
        "زلزله",
        "سیل",
        "طوفان",
        "گردوغبار",
        "بارندگی",
        "تصادف",
        "آتش‌سوزی",
        "حادثه",
        "صیاد",
        "ماهیگیری",
        "صادرات",
        "واردات",
        "مرز",
        "مرزبان",
        "سوخت",
        "سوختبر",
        "بندر",
        "ساحل",
        "دریا",
        "مکران",
    ]

    has_strong_local_subject = any(
        term in title
        for term in strong_local_subjects
    )

    if (
        any(
            term in title
            for term in generic_national_terms
        )
        and not has_strong_local_subject
    ):
        return 0

    return score


def is_local_news(
    title,
    summary,
):

    return (
        local_score(
            title,
            summary,
        )
        > 0
    )


# ============================================================
# NATIONAL VERY IMPORTANT FILTER
# ============================================================

def national_score(
    title,
    summary,
):

    title = clean_text(
        title
    )

    summary = clean_text(
        summary
    )

    # National breaking stories should
    # primarily be identified from TITLE.

    score = 0

    for keyword in NATIONAL_KEYWORDS:

        if keyword in title:

            score += 100

    # Allow a few extremely important headlines
    # where the title contains Iran + a major action.

    major_actions = [
        "حمله",
        "جنگ",
        "بمباران",
        "موشک",
        "مذاکرات",
        "آتش‌بس",
        "آتش بس",
        "ترور",
        "عملیات نظامی",
    ]

    has_iran = any(
        word in title
        for word in [
            "ایران",
            "ایرانی",
        ]
    )

    has_major_action = any(
        word in title
        for word in major_actions
    )

    if (
        has_iran
        and has_major_action
    ):

        score += 50

    # Never accept national news
    # without an Iran-related confirmation.

    if not any(
        word in title
        for word in NATIONAL_CONFIRMATION
    ):

        return 0

    return score


def is_very_important_national(
    title,
    summary,
):

    return (
        national_score(
            title,
            summary,
        )
        >= 100
    )


# ============================================================
# CLASSIFY
# ============================================================

def classify_news(
    title,
    summary,
):

    # LOCAL HAS PRIORITY
    if is_local_news(
        title,
        summary,
    ):

        return (
            "استان سیستان و بلوچستان"
        )

    # ONLY VERY IMPORTANT NATIONAL
    if is_very_important_national(
        title,
        summary,
    ):

        return "ایران"

    return None


# ============================================================
# COLLECT
# ============================================================

def collect_news():

    now = datetime.now(
        timezone.utc
    )

    max_age = timedelta(
        hours=24
    )

    collected = []
    seen = set()

    for source in RSS_FEEDS:

        feed = fetch_feed(
            source
        )

        if not feed:
            continue

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

            # ------------------------------------------------
            # ONLY INTERNAL SOURCES
            # ------------------------------------------------

            if not is_approved_domain(
                link
            ):

                print(
                    "Rejected source:",
                    link,
                )

                continue

            published = parse_date(
                entry
            )

            if published:

                age = (
                    now - published
                )

                if (
                    age < timedelta(0)
                    or age > max_age
                ):

                    continue

            summary = make_summary(
                entry
            )

            category = classify_news(
                title,
                summary,
            )

            if not category:
                continue

            if link in seen:
                continue

            seen.add(link)

            if category == (
                "استان سیستان و بلوچستان"
            ):

                score = local_score(
                    title,
                    summary,
                )

            else:

                score = national_score(
                    title,
                    summary,
                )

            collected.append(
                {
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": (
                        published
                        or now
                    ),
                    "category": category,
                    "source": source[
                        "name"
                    ],
                    "score": score,
                }
            )

    return collected


# ============================================================
# SELECT EXACTLY:
# 3 LOCAL + 1 NATIONAL
# ============================================================

def select_news(news):

    local_news = [
        item
        for item in news
        if item["category"]
        == "استان سیستان و بلوچستان"
    ]

    national_news = [
        item
        for item in news
        if item["category"]
        == "ایران"
    ]

    # Highest relevance first.
    local_news.sort(
        key=lambda item: (
            item["score"],
            item["published"],
        ),
        reverse=True,
    )

    national_news.sort(
        key=lambda item: (
            item["score"],
            item["published"],
        ),
        reverse=True,
    )

    selected = []

    # Maximum 3 local stories.
    for item in local_news[:3]:
        selected.append(item)

    # Maximum 1 national story.
    for item in national_news[:1]:
        selected.append(item)

    return selected


# ============================================================
# BALE API
# ============================================================

def bale_request(
    method,
    data=None,
    files=None,
):

    url = (
        f"https://tapi.bale.ai/"
        f"bot{BOT_TOKEN}/{method}"
    )

    response = requests.post(
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
            f"Bale API error: {result}"
        )

    return result


# ============================================================
# BUTTONS
# ============================================================

def make_reply_markup(
    news_link,
):

    return json.dumps(
        {
            "inline_keyboard": [

                [
                    {
                        "text": "🔗 مشاهده خبر",
                        "url": news_link,
                    }
                ],

                [
                    {
                        "text": "📨 تلگرام",
                        "url": TELEGRAM_LINK,
                    },
                    {
                        "text": "🟦 بله",
                        "url": BALE_LINK,
                    },
                    {
                        "text": "🟠 سروش",
                        "url": SOROUSH_LINK,
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

    text = (
        f"🚨 {item['category']}\n\n"
        f"📰 {item['title']}\n\n"
    )

    if item["summary"]:

        text += (
            f"{item['summary']}\n\n"
        )

    text += (
        f"🗞 منبع: {item['source']}\n\n"
        f"🌐 جهان‌تاب"
    )

    return bale_request(
        "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "reply_markup":
                make_reply_markup(
                    item["link"]
                ),
        },
    )


# ============================================================
# SEND PHOTO
# ============================================================

def send_photo(
    item,
    image_url,
):

    caption = (
        f"🚨 {item['category']}\n\n"
        f"📰 {item['title']}\n\n"
    )

    if item["summary"]:

        caption += (
            f"{item['summary']}\n\n"
        )

    caption += (
        f"🗞 منبع: {item['source']}\n\n"
        f"🌐 جهان‌تاب"
    )

    caption = caption[:1000]

    try:

        image_response = requests.get(
            image_url,
            timeout=15,
            headers={
                "User-Agent":
                    "Mozilla/5.0 JahantabNewsBot/1.0"
            },
        )

        image_response.raise_for_status()

        content_type = (
            image_response.headers.get(
                "Content-Type",
                "",
            )
        )

        if not content_type.startswith(
            "image/"
        ):

            raise RuntimeError(
                "URL did not return an image"
            )

        extension = ".jpg"

        if "png" in content_type:
            extension = ".png"

        elif "webp" in content_type:
            extension = ".webp"

        files = {
            "photo": (
                f"news{extension}",
                image_response.content,
                content_type,
            )
        }

        return bale_request(
            "sendPhoto",
            data={
                "chat_id": CHAT_ID,
                "caption": caption,
                "reply_markup":
                    make_reply_markup(
                        item["link"]
                    ),
            },
            files=files,
        )

    except Exception as exc:

        print(
            f"Photo send failed: {exc}"
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
        "STRICT LOCAL / NATIONAL MODE"
    )

    print(
        "==================================="
    )

    sent_links = load_sent_links()

    print(
        f"Previously sent links: "
        f"{len(sent_links)}"
    )

    news = collect_news()

    print(
        f"Relevant approved news found: "
        f"{len(news)}"
    )

    selected = select_news(
        news
    )

    print(
        f"Selected for publication: "
        f"{len(selected)}"
    )

    local_selected = sum(
        1
        for item in selected
        if item["category"]
        == "استان سیستان و بلوچستان"
    )

    national_selected = sum(
        1
        for item in selected
        if item["category"]
        == "ایران"
    )

    print(
        f"Selected local: "
        f"{local_selected}"
    )

    print(
        f"Selected national: "
        f"{national_selected}"
    )

    new_count = 0

    for item in selected:

        link = item["link"]

        if link in sent_links:

            print(
                "Already sent:",
                item["title"],
            )

            continue

        print(
            "Publishing:",
            f"[{item['category']}]",
            f"[{item['source']}]",
            item["title"],
        )

        image_url = (
            get_image_from_article(
                link
            )
        )

        try:

            if image_url:

                send_photo(
                    item,
                    image_url,
                )

            else:

                send_text(
                    item
                )

            save_sent_link(
                link
            )

            sent_links.add(
                link
            )

            new_count += 1

            print(
                "Published successfully."
            )

        except Exception as exc:

            print(
                f"Publish failed: "
                f"{exc}"
            )

    print(
        "-----------------------------------"
    )

    print(
        f"New published news: "
        f"{new_count}"
    )

    print(
        "==================================="
    )


if __name__ == "__main__":
    main()