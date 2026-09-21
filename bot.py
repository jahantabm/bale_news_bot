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
# SOCIAL CHANNELS
# ============================================================

TELEGRAM_LINK = "https://t.me/Jahantab_news"
BALE_LINK = "https://ble.ir/jahantabnews"
SOROUSH_LINK = "https://splus.ir/jahantabnews"


# ============================================================
# APPROVED INTERNAL SOURCES
# ============================================================
#
# فقط لینک‌هایی که دامنه آنها در این فهرست باشد منتشر می‌شوند.
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
}


# ============================================================
# RSS SOURCES
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
# SISTAN & BALUCHESTAN + MAKran
# ============================================================

SISTAN_KEYWORDS = [
    "سیستان و بلوچستان",
    "سیستان",
    "بلوچستان",
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
    "دشتک",
    "کورین",
    "نوک‌آباد",
    "بزمان",
    "گشت",
    "پلان",
    "تلنگ",
    "زرآباد",
    "بخش زرآباد",
    "ساحل مکران",
    "سواحل مکران",
    "مکران",
    "دریای عمان",
]


# ============================================================
# VERY IMPORTANT NATIONAL NEWS
# ============================================================
#
# این فهرست عمداً محدود است.
# خبر عادی سیاسی/اقتصادی/ورزشی وارد بخش ایران نمی‌شود.
# ============================================================

NATIONAL_CRISIS_KEYWORDS = [
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
    "حمله آمریکا به ایران",
    "حمله اسرائیل به خاک ایران",
    "حمله نظامی به ایران",

    "حمله ایران به آمریکا",
    "حمله ایران به اسرائیل",
    "حمله ایران به پایگاه آمریکا",
    "حمله ایران به پایگاه‌های آمریکا",
    "حمله ایران به اسرائیل",

    "حمله موشکی به ایران",
    "حمله هوایی به ایران",
    "حملات هوایی به ایران",
    "حملات موشکی به ایران",

    "موشک ایران",
    "موشک‌های ایران",
    "موشک به اسرائیل",
    "موشک به آمریکا",

    "پایگاه آمریکا",
    "پایگاه‌های آمریکا",
    "پایگاه آمریکایی",

    "تأسیسات هسته‌ای ایران",
    "تاسیسات هسته‌ای ایران",
    "حمله به تأسیسات هسته‌ای",
    "حمله به تاسیسات هسته‌ای",

    "حمله به نیروگاه",
    "حمله به تأسیسات ایران",
    "حمله به تاسیسات ایران",

    "بمباران ایران",
    "بمباران اسرائیل",
    "بمباران آمریکا",

    "آتش‌بس ایران و اسرائیل",
    "آتش‌بس ایران و آمریکا",
    "آتش بس ایران و اسرائیل",
    "آتش بس ایران و آمریکا",

    "مذاکرات ایران و آمریکا",
    "توافق ایران و آمریکا",

    "مذاکرات ایران و اسرائیل",
    "توافق ایران و اسرائیل",

    "اعلام جنگ",
    "آغاز جنگ",
    "پایان جنگ",

    "حمله گسترده به ایران",
    "حمله گسترده اسرائیل",
    "حمله گسترده آمریکا",

    "عملیات نظامی علیه ایران",
    "عملیات نظامی اسرائیل علیه ایران",
    "عملیات نظامی آمریکا علیه ایران",

    "ترور مقام ایرانی",
    "ترور فرمانده ایرانی",

    "حمله به مراکز نظامی ایران",
    "حمله به پایگاه نظامی ایران",

    "وضعیت فوق‌العاده",
    "شرایط جنگی",
]


# کلمات تأییدکننده برای جلوگیری از اشتباه
IRAN_CONFIRMATION_KEYWORDS = [
    "ایران",
    "تهران",
    "اسرائیل",
    "آمریکا",
    "آمریکایی",
    "اسرائیلی",
    "سپاه",
    "نیروهای مسلح",
    "ارتش جمهوری اسلامی",
]


# ============================================================
# TEXT CLEANING
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
# URL
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
        domain = urlparse(url).netloc.lower()
        return domain.removeprefix("www.")
    except Exception:
        return ""


def is_approved_source(url):
    domain = get_domain(url)

    if not domain:
        return False

    if domain in APPROVED_DOMAINS:
        return True

    return any(
        domain.endswith("." + approved)
        for approved in APPROVED_DOMAINS
    )


# ============================================================
# STATE
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
        file.write(link + "\n")


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

        if image and image.get("content"):
            return image["content"].strip()

        image = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            },
        )

        if image and image.get("content"):
            return image["content"].strip()

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
# CLASSIFICATION
# ============================================================

def is_sistan_news(title, summary):
    text = f"{title} {summary}"

    return any(
        keyword in text
        for keyword in SISTAN_KEYWORDS
    )


def national_news_score(title, summary):
    text = f"{title} {summary}"

    score = 0

    for keyword in NATIONAL_CRISIS_KEYWORDS:
        if keyword in text:
            score += 10

    confirmation = any(
        keyword in text
        for keyword in IRAN_CONFIRMATION_KEYWORDS
    )

    if not confirmation:
        return 0

    return score


def classify_news(title, summary):
    if is_sistan_news(
        title,
        summary,
    ):
        return "استان سیستان و بلوچستان"

    if national_news_score(
        title,
        summary,
    ) >= 10:
        return "ایران"

    return None


# ============================================================
# COLLECT NEWS
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

        feed = fetch_feed(source)

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

            # ----------------------------------------------
            # HARD SOURCE FILTER
            # ----------------------------------------------

            if not is_approved_source(link):
                print(
                    "Rejected source:",
                    link,
                )
                continue

            published = parse_date(entry)

            if published:
                age = now - published

                if (
                    age < timedelta(0)
                    or age > max_age
                ):
                    continue

            summary = make_summary(entry)

            category = classify_news(
                title,
                summary,
            )

            if not category:
                continue

            if link in seen:
                continue

            seen.add(link)

            score = 0

            if category == "استان سیستان و بلوچستان":
                score = 100

                for keyword in SISTAN_KEYWORDS:
                    if keyword in (
                        f"{title} {summary}"
                    ):
                        score += 2

            else:
                score = national_news_score(
                    title,
                    summary,
                )

            collected.append(
                {
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": (
                        published or now
                    ),
                    "category": category,
                    "source": source["name"],
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

    selected_local = local_news[:3]
    selected_national = national_news[:1]

    selected = (
        selected_local
        + selected_national
    )

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
# SOCIAL BUTTONS
# ============================================================

def make_reply_markup(news_link):
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

    title = item["title"]
    summary = item["summary"]
    link = item["link"]
    category = item["category"]
    source = item["source"]

    text = (
        f"🚨 {category}\n\n"
        f"📰 {title}\n\n"
    )

    if summary:
        text += (
            f"{summary}\n\n"
        )

    text += (
        f"🗞 منبع: {source}\n\n"
        f"🌐 جهان‌تاب"
    )

    reply_markup = make_reply_markup(
        link
    )

    return bale_request(
        "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
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

    title = item["title"]
    summary = item["summary"]
    link = item["link"]
    category = item["category"]
    source = item["source"]

    caption = (
        f"🚨 {category}\n\n"
        f"📰 {title}\n\n"
    )

    if summary:
        caption += (
            f"{summary}\n\n"
        )

    caption += (
        f"🗞 منبع: {source}\n\n"
        f"🌐 جهان‌تاب"
    )

    # Bale caption limit
    caption = caption[:1000]

    reply_markup = make_reply_markup(
        link
    )

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
                "reply_markup": reply_markup,
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
        f"Selected news: "
        f"{len(selected)}"
    )

    local_count = 0
    national_count = 0
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
            f"Publishing: "
            f"[{item['category']}] "
            f"[{item['source']}] "
            f"{item['title']}"
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

            if item["category"] == (
                "استان سیستان و بلوچستان"
            ):
                local_count += 1
            else:
                national_count += 1

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
        f"Local published: "
        f"{local_count}"
    )

    print(
        f"National published: "
        f"{national_count}"
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