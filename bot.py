import os
import re
import json
import html
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

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
# RSS FEEDS
# ============================================================

SISTAN_FEEDS = [
    "https://news.google.com/rss/search?q="
    + quote('"سیستان و بلوچستان"')
    + "&hl=fa&gl=IR&ceid=IR:fa",

    "https://news.google.com/rss/search?q="
    + quote(
        '"زاهدان" OR "زابل" OR "چابهار" OR "سراوان" '
        'OR "ایرانشهر" OR "خاش"'
    )
    + "&hl=fa&gl=IR&ceid=IR:fa",
]


IRAN_FEEDS = [
    "https://news.google.com/rss/search?q="
    + quote(
        'ایران (فوری OR مهم OR "خبر فوری" OR "آخرین خبر")'
    )
    + "&hl=fa&gl=IR&ceid=IR:fa",

    "https://news.google.com/rss/search?q="
    + quote('"خبر فوری ایران" OR "فوری ایران"')
    + "&hl=fa&gl=IR&ceid=IR:fa",
]


# ============================================================
# KEYWORDS
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


URGENT_KEYWORDS = [
    "فوری",
    "خبر فوری",
    "لحظه‌ای",
    "لحظاتی پیش",
    "آخرین خبر",
    "هشدار",
    "زلزله",
    "سیل",
    "طوفان",
    "انفجار",
    "آتش‌سوزی",
    "حادثه",
    "تصادف",
    "کشته",
    "مجروح",
    "بازداشت",
    "حمله",
    "درگیری",
    "تعطیلی",
    "قطع",
    "فوت",
    "فوتی",
    "ترور",
]


IMPORTANT_IRAN_KEYWORDS = [
    "فوری",
    "خبر فوری",
    "هشدار",
    "زلزله",
    "سیل",
    "انفجار",
    "آتش‌سوزی",
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

    return datetime.now(timezone.utc)


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
                "User-Agent": (
                    "Mozilla/5.0 "
                    "JahantabNewsBot/1.0"
                )
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

    if len(description) > 450:
        description = (
            description[:447]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return description


# ============================================================
# SCORING
# ============================================================

def score_sistan(
    title,
    summary,
):
    text = f"{title} {summary}"

    score = 0

    for keyword in SISTAN_KEYWORDS:
        if keyword in text:
            score += 2

    for keyword in URGENT_KEYWORDS:
        if keyword in text:
            score += 2

    return score


def score_iran(
    title,
    summary,
):
    text = f"{title} {summary}"

    score = 0

    for keyword in IMPORTANT_IRAN_KEYWORDS:
        if keyword in text:
            score += 2

    return score


# ============================================================
# RSS
# ============================================================

def fetch_feed(url):
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "JahantabNewsBot/1.0"
                )
            },
        )

        response.raise_for_status()

        feed = feedparser.parse(
            response.content
        )

        print(
            f"RSS URL: {url}"
        )

        print(
            f"RSS entries: "
            f"{len(feed.entries)}"
        )

        if getattr(
            feed,
            "bozo",
            False,
        ):
            print(
                "RSS parse warning:",
                feed.bozo_exception,
            )

        if feed.entries:
            for entry in feed.entries[:3]:
                print(
                    "RSS title:",
                    clean_text(
                        getattr(
                            entry,
                            "title",
                            "",
                        )
                    ),
                )

        return feed

    except Exception as exc:
        print(
            f"Feed error: {exc}"
        )

        return None


# ============================================================
# COLLECT NEWS
# ============================================================

def collect_news():
    now = datetime.now(
        timezone.utc
    )

    max_age = timedelta(
        hours=18
    )

    collected = []

    # --------------------------------------------------------
    # Sistan & Baluchestan
    # --------------------------------------------------------

    for feed_url in SISTAN_FEEDS:

        feed = fetch_feed(
            feed_url
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

            published = parse_date(
                entry
            )

            if (
                now - published
                > max_age
            ):
                continue

            summary = make_summary(
                entry
            )

            score = score_sistan(
                title,
                summary,
            )

            if score < 2:
                continue

            collected.append(
                {
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": published,
                    "category": (
                        "سیستان و بلوچستان"
                    ),
                    "score": score,
                }
            )

    # --------------------------------------------------------
    # Important Iran
    # --------------------------------------------------------

    for feed_url in IRAN_FEEDS:

        feed = fetch_feed(
            feed_url
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

            published = parse_date(
                entry
            )

            if (
                now - published
                > max_age
            ):
                continue

            summary = make_summary(
                entry
            )

            score = score_iran(
                title,
                summary,
            )

            if score < 2:
                continue

            collected.append(
                {
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": published,
                    "category": "ایران",
                    "score": score,
                }
            )

    collected.sort(
        key=lambda item: (
            item["score"],
            item["published"],
        ),
        reverse=True,
    )

    unique = {}

    for item in collected:

        if item["link"] not in unique:
            unique[item["link"]] = item

    return list(
        unique.values()
    )


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
# SEND TEXT
# ============================================================

def send_text(item):

    title = item["title"]
    summary = item["summary"]
    link = item["link"]
    category = item["category"]

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
        f"🔗 {link}"
    )

    reply_markup = json.dumps(
        {
            "inline_keyboard": [
                [
                    {
                        "text": (
                            "مشاهده خبر"
                        ),
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
            "reply_markup": (
                reply_markup
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

    title = item["title"]
    summary = item["summary"]
    link = item["link"]
    category = item["category"]

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
        "🔗 مشاهده متن کامل خبر"
    )

    caption = caption[:1000]

    reply_markup = json.dumps(
        {
            "inline_keyboard": [
                [
                    {
                        "text": (
                            "مشاهده خبر"
                        ),
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
                "User-Agent": (
                    "Mozilla/5.0 "
                    "JahantabNewsBot/1.0"
                )
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
                "reply_markup": (
                    reply_markup
                ),
            },
            files=files,
        )

    except Exception as exc:

        print(
            f"Photo send failed: {exc}"
        )

        return send_text(
            item
        )


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
        f"Relevant news found: "
        f"{len(news)}"
    )

    new_count = 0

    for item in news[:5]:

        link = item["link"]

        if link in sent_links:
            continue

        print(
            f"Publishing: "
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