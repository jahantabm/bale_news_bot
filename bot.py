
import os
import re
import time
import html
import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests
import feedparser
from bs4 import BeautifulSoup

BALE_TOKEN = os.getenv("BALE_BOT_TOKEN", "").strip()
BALE_CHAT_ID = os.getenv("BALE_CHAT_ID", "").strip()

if not BALE_TOKEN:
    raise RuntimeError("BALE_BOT_TOKEN is not set")
if not BALE_CHAT_ID:
    raise RuntimeError("BALE_CHAT_ID is not set")

API = f"https://tapi.bale.ai/bot{BALE_TOKEN}"
STATE_FILE = Path("sent_links.txt")
MAX_SENT = 5000

# Direct RSS feeds. If a feed changes, edit only this list.
FEEDS = [
    ("تابناک", "https://www.tabnak.ir/fa/rss/allnews"),
    ("فرارو", "https://fararu.com/fa/rss/allnews"),
    ("همشهری آنلاین", "https://www.hamshahrionline.ir/rss"),
    ("خبر فوری", "https://www.khabarfoori.com/rss"),
    ("مهر", "https://www.mehrnews.com/rss"),
    ("ایسنا", "https://www.isna.ir/rss"),
    ("ایرنا", "https://www.irna.ir/rss"),
    ("تسنیم", "https://www.tasnimnews.com/fa/rss"),
]

# Topics requested by the channel owner.
KEYWORDS = {
    "ایران و آمریکا": [
        "ایران", "آمریکا", "امریکا", "ایالات متحده", "واشنگتن",
        "ترامپ", "پنتاگون", "نیروهای آمریکایی", "پایگاه آمریکا",
    ],
    "حزب‌الله لبنان": [
        "حزب‌الله", "حزب الله", "لبنان", "حزب‌الله لبنان",
    ],
    "انصارالله یمن": [
        "انصارالله", "انصار الله", "حوثی", "حوثی‌ها", "یمن",
    ],
    "تنگه هرمز": [
        "تنگه هرمز", "هرمز", "خلیج فارس", "کشتیرانی", "کشتی",
        "نفتکش", "نفت‌کش",
    ],
    "جنگ و درگیری منطقه‌ای": [
        "حمله", "موشک", "پهپاد", "درگیری", "جنگ", "حملات",
        "انفجار", "عملیات نظامی", "آتش‌بس", "حمله هوایی",
    ],
}

URGENT = [
    "فوری", "خبر فوری", "لحظه‌ای", "لحظاتی پیش", "فورا",
    "حمله", "حملات", "موشک", "پهپاد", "انفجار", "کشته",
    "آتش‌بس", "عملیات", "بسته شدن", "مسدود", "اعلام جنگ",
]

HEADERS = {
    "User-Agent": "Jahantab-News-Bot/1.0 (+https://github.com/jahantabm/telegram_news_bot)"
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def normalize(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.replace("ي", "ی").replace("ك", "ک").strip()


def load_sent() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    return {x.strip() for x in STATE_FILE.read_text(encoding="utf-8").splitlines() if x.strip()}


def save_sent(items: set[str]):
    latest = list(items)[-MAX_SENT:]
    STATE_FILE.write_text("\n".join(latest) + "\n", encoding="utf-8")


def strip_html(text: str) -> str:
    return normalize(BeautifulSoup(text or "", "html.parser").get_text(" "))


def entry_text(entry) -> str:
    title = normalize(entry.get("title", ""))
    summary = strip_html(entry.get("summary", "") or entry.get("description", ""))
    return f"{title} {summary}"


def find_topics(text: str) -> list[str]:
    hits = []
    for topic, words in KEYWORDS.items():
        if any(w in text for w in words):
            hits.append(topic)
    return hits


def score_item(title: str, text: str, topics: list[str]) -> int:
    score = min(len(topics) * 3, 12)
    low = f"{title} {text}"
    score += sum(2 for w in URGENT if w in low)
    if "فوری" in title or "لحظه‌ای" in title:
        score += 5
    return score


def get_image(entry, article_url: str) -> str | None:
    # RSS media/enclosure first.
    for key in ("media_content", "media_thumbnail"):
        for item in entry.get(key, []) or []:
            url = item.get("url")
            if url and url.startswith("http"):
                return url

    enclosure = entry.get("enclosures", []) or []
    for item in enclosure:
        url = item.get("href") or item.get("url")
        if url and ("image" in item.get("type", "") or url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp"))):
            return url

    # Fallback: inspect article og:image.
    try:
        r = requests.get(article_url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        tag = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
        if tag and tag.get("content", "").startswith("http"):
            return tag["content"]
    except Exception as exc:
        logging.warning("image lookup failed: %s", exc)
    return None


def make_summary(entry, title: str) -> str:
    raw = strip_html(entry.get("summary", "") or entry.get("description", ""))
    if not raw:
        return "جزئیات بیشتر در منبع اصلی خبر منتشر شده است."

    # Extractive, source-faithful summary: no invented facts.
    sentences = re.split(r"(?<=[.!؟])\s+", raw)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    summary = " ".join(sentences[:3])
    if len(summary) > 650:
        summary = summary[:647].rsplit(" ", 1)[0] + "..."
    return summary


def source_domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "")


def build_caption(source: str, title: str, summary: str, topics: list[str]) -> str:
    topic = "، ".join(topics[:3])
    caption = (
        f"🔴 {title}\n\n"
        f"{summary}\n\n"
        f"📰 منبع: {source}\n"
        f"🏷 موضوع: {topic}\n\n"
        f"جهان‌تاب | اخبار مهم و فوری"
    )
    return caption[:1000]


def bale_call(method: str, payload: dict, files=None) -> dict:
    url = f"{API}/{method}"
    if files:
        r = requests.post(url, data=payload, files=files, timeout=30)
    else:
        r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", str(data)))
    return data


def send_news(caption: str, article_url: str, image_url: str | None):
    markup = {
        "inline_keyboard": [[
            {"text": "🔗 مشاهده خبر", "url": article_url}
        ]]
    }

    if image_url:
        try:
            bale_call("sendPhoto", {
                "chat_id": BALE_CHAT_ID,
                "photo": image_url,
                "caption": caption,
                "reply_markup": markup,
            })
            return
        except Exception as exc:
            logging.warning("sendPhoto with URL failed; falling back to text: %s", exc)

    bale_call("sendMessage", {
        "chat_id": BALE_CHAT_ID,
        "text": caption,
        "reply_markup": markup,
    })


def fetch_feed(source: str, url: str):
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        if getattr(feed, "bozo", 0) and not feed.entries:
            raise RuntimeError("invalid RSS")
        return feed.entries[:20]
    except Exception as exc:
        logging.warning("feed failed [%s] %s: %s", source, url, exc)
        return []


def stable_id(url: str, title: str) -> str:
    return hashlib.sha256((url or title).encode("utf-8")).hexdigest()


def main():
    sent = load_sent()
    candidates = []

    for source, feed_url in FEEDS:
        for entry in fetch_feed(source, feed_url):
            title = normalize(entry.get("title", ""))
            url = entry.get("link", "").strip()
            if not title or not url:
                continue

            sid = stable_id(url, title)
            if sid in sent:
                continue

            text = entry_text(entry)
            topics = find_topics(text)
            if not topics:
                continue

            score = score_item(title, text, topics)
            if score < 5:
                continue

            candidates.append((score, source, title, url, entry, topics, sid))

    # Most relevant first, then limit each run.
    candidates.sort(key=lambda x: x[0], reverse=True)
    candidates = candidates[:8]

    if not candidates:
        logging.info("No new relevant news.")
        return

    for score, source, title, url, entry, topics, sid in candidates:
        try:
            summary = make_summary(entry, title)
            image = get_image(entry, url)
            caption = build_caption(source, title, summary, topics)
            send_news(caption, url, image)
            sent.add(sid)
            logging.info("sent: [%s] %s", source, title)
            time.sleep(1.5)
        except Exception as exc:
            logging.exception("failed to publish %s: %s", title, exc)

    save_sent(sent)


if __name__ == "__main__":
    main()
