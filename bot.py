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
# APPROVED INTERNAL SOURCES
# ============================================================

APPROVED_DOMAINS = {
    "tabnak.ir",
    "asriran.com",
    "isna.ir",
    "mehrnews.com",
    "tasnimnews.com",
    "khabaronline.ir",
}


RSS_FEEDS = [
    {
        "name": "تابناک",
        "url": "https://www.tabnak.ir/fa/rss/allnews",
    },
    {
        "name": "عصر ایران",
        "url": "https://www.asriran.com/fa/rss/allnews",
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
        "name": "تسنیم",
        "url": (
            "https://www.tasnimnews.com/fa/rss/feed/"
            "0/8/0/%D9%85%D9%87%D9%85%D8%AA%D8%B1%DB%8C%D9%86-%D8%A7%D8%AE%D8%A8%D8%A7%D8%B1-%D8%AA%D8%B3%D9%86%DB%8C%D9%85"
        ),
    },
    {
        "name": "خبرآنلاین",
        "url": "https://www.khabaronline.ir/rss",
    },
]


# ============================================================
# SOCIAL LINKS
# ============================================================

TELEGRAM_LINK = "https://t.me/jahantab_newd"
BALE_LINK = "https://ble.ir/jahantabnews"
SOROUSH_LINK = "https://splus.ir/jahantabnews"


# ============================================================
# SISTAN AND BALUCHESTAN
# ============================================================

SISTAN_KEYWORDS = [
    "سیستان",
    "بلوچستان",
    "سیستان و بلوچستان",
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
]


# ============================================================
# IMPORTANT / URGENT IRAN
# ============================================================

URGENT_KEYWORDS = [
    "فوری",
    "خبر فوری",
    "لحظه‌ای",
    "لحظاتی پیش",
    "هشدار",
    "زلزله",
    "سیل",
    "طوفان",
    "انفجار",
    "آتش‌سوزی",
    "حادثه",
    "حمله",
    "درگیری",
    "تعطیلی سراسری",
    "قطعی گسترده",
    "تصمیم مهم",
    "تصمیم جدید",
    "اعلام شد",
    "لغو شد",
    "آغاز شد",
    "پایان یافت",
]


# ============================================================
# TEXT HELPERS
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

    if len(description) > 450:
        description = (
            description[:447]
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


def is_important_iran_news(title, summary):
    text = f"{title} {summary}"

    return any(
        keyword in text
        for keyword in URGENT_KEYWORDS
    )


def classify_news(title, summary):
    if is_sistan_news(
        title,
        summary,
    ):
        return "سیستان و بلوچستان"

    if is_important_iran_news(
        title,
        summary,
    ):
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

            # Only approved internal sources
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
                }
            )

    collected.sort(
        key=lambda item:
            item["published"],
        reverse=True,
    )

    return collected


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
# SOCIAL FOOTER
# ============================================================

def social_footer():
    return (
        "📱 جهان‌تاب\n"
        f"📨 تلگرام: {TELEGRAM_LINK}\n"
        f"🟦 بله: {BALE_LINK}\n"
        f"🟠 سروش: {SOROUSH_LINK}"
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
            summary
            + "\n\n"
        )

    text += (
        f"🗞 منبع: {source}\n\n"
        f"🔗 مشاهده خبر\n"
        f"{link}\n\n"
        f"{social_footer()}"
    )

    reply_markup = json.dumps(
        {
            "inline_keyboard": [
                [
                    {
                        "text": "مشاهده خبر",
                        "url": link,
                    }
                ]
            ]
        },
        ensure_ascii=False,
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
            summary
            + "\n\n"
        )

    caption += (
        f"🗞 منبع: {source}\n\n"
        f"🔗 مشاهده متن کامل خبر\n\n"
        f"{social_footer()}"
    )

    caption = caption[:1000]

    reply_markup = json.dumps(
        {
            "inline_keyboard": [
                [
                    {
                        "text": "مشاهده خبر",
                        "url": link,
                    }
                ]
            ]
        },
        ensure_ascii=False,
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

    new_count = 0

    for item in news[:5]:

        link = item["link"]

        if link in sent_links:
            continue

        print(
            f"Publishing: "
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

            print(
                "Published successfully."
            )

        except Exception as exc:

            print(
                f"Publish failed: "
                f"{exc}"
            )

    print(
        f"New published news: "
        f"{new_count}"
    )


if __name__ == "__main__":
    main()