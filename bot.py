import os
import re
import json
import html
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urlparse

import requests
import feedparser
from bs4 import BeautifulSoup


# ============================================================
# تنظیمات اصلی
# ============================================================

BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
CHAT_ID = os.getenv("BALE_CHAT_ID")

STATE_FILE = "sent_links.txt"
TITLE_STATE_FILE = "sent_titles.txt"

if not BOT_TOKEN:
    raise RuntimeError("BALE_BOT_TOKEN is not set")

if not CHAT_ID:
    raise RuntimeError("BALE_CHAT_ID is not set")


# ============================================================
# کانال‌های جهان‌تاب
# ============================================================

TELEGRAM_LINK = "https://t.me/Jahantab_news"
BALE_LINK = "https://ble.ir/jahantabnews"
SOROUSH_LINK = "https://splus.ir/jahantabnews"


# ============================================================
# منابع داخلی مجاز
# ============================================================

APPROVED_DOMAINS = [
    "irna.ir",
    "isna.ir",
    "mehrnews.com",
    "farsnews.ir",
    "tasnimnews.com",
    "ilna.ir",
    "tabnak.ir",
    "asriran.com",
    "fararu.com",
    "jahannews.com",
    "khabaronline.ir",
    "khabarfouri.com",
    "akharinkhabar.ir",
    "roozplus.com",
    "hamshahrionline.ir",
    "jamejamonline.ir",
    "yjc.ir",
    "entekhab.ir",
    "iribnews.ir",
    "iribnews.com",
]


# ============================================================
# نام استان
# ============================================================

PROVINCE_NAMES = [
    "سیستان و بلوچستان",
    "سیستان‌ و بلوچستان",
    "سیستان‌وبلوچستان",
    "استان سیستان و بلوچستان",
    "استان سیستان‌وبلوچستان",
]


# ============================================================
# شهرستان‌ها و شهرهای استان
# ============================================================

CITIES_AND_COUNTIES = [
    "زاهدان",
    "زابل",
    "زهک",
    "هیرمند",
    "هامون",
    "نیمروز",
    "رامشار",
    "نصرت آباد",
    "نصرت‌آباد",
    "میرجاوه",
    "خاش",
    "تفتان",
    "سراوان",
    "سیب و سوران",
    "سیب‌وسوران",
    "مهرستان",
    "گلشن",
    "ایرانشهر",
    "بمپور",
    "بزمان",
    "دلگان",
    "گلمورتی",
    "سرباز",
    "راسک",
    "قصرقند",
    "نیکشهر",
    "فنوج",
    "کنارک",
    "چابهار",
    "دشتیاری",
    "زرآباد",
]


# ============================================================
# مناطق مهم
# ============================================================

IMPORTANT_LOCAL_AREAS = [
    "میلک",
    "مرز میلک",
    "ریمدان",
    "مرز ریمدان",
    "مرز شرقی",
    "مرزهای شرقی",
    "مرز افغانستان",
    "مرز پاکستان",
    "باهوکلات",
    "باهو کلات",
    "نگور",
    "طیس",
    "بندر چابهار",
    "بندر کنارک",
    "کنارک",
    "سواحل مکران",
    "ساحل مکران",
    "مکران",
    "دریای عمان",
    "هامون جازموریان",
    "جازموریان",
    "دریاچه هامون",
    "رودخانه هیرمند",
    "کوه تفتان",
    "کوه خواجه",
    "شهر سوخته",
    "میل نادر",
    "کورین",
    "منطقه سیستان",
    "منطقه بلوچستان",
]


# ============================================================
# موضوعات محلی
# ============================================================

LOCAL_SUBJECTS = [
    "سوخت‌بر",
    "سوخت بر",
    "سوختبران",
    "سوخت‌بران",
    "سوخت قاچاق",
    "مرزنشین",
    "مرزنشینان",
    "بازارچه مرزی",
    "بازارچه‌های مرزی",
    "صیاد",
    "صیادی",
    "ماهیگیری",
    "بندر",
    "منطقه آزاد چابهار",
    "کشاورزی",
    "خشکسالی",
    "گردوغبار",
    "ریزگرد",
    "طوفان",
    "سیلاب",
    "زلزله",
    "جاده",
    "راه",
    "مدرسه",
    "دانشگاه",
    "بیمارستان",
    "علوم پزشکی",
    "استاندار",
    "استانداری",
    "فرمانداری",
    "شهرداری",
    "دهیاری",
    "میراث فرهنگی",
    "گردشگری",
    "صنایع دستی",
    "اشتغال",
    "سرمایه‌گذاری",
    "پروژه عمرانی",
    "پروژه",
    "بندر",
    "ترانزیت",
    "گمرک",
    "صادرات",
    "واردات",
    "صیادان",
    "لنج",
    "کشتی",
]


# ============================================================
# مواردی که معمولاً خبر نامرتبط ایجاد می‌کنند
# ============================================================

UNRELATED_TERMS = [
    "سردار آزمون",
    "مهدی طارمی",
    "رونالدو",
    "مسی",
    "بارسلونا",
    "رئال مادرید",
    "پرسپولیس",
    "استقلال تهران",
    "سپاهان",
    "تراکتور",
    "تیم ملی فوتبال",
    "لیگ برتر فوتبال",
    "جام جهانی فوتبال",
    "لیگ قهرمانان اروپا",
    "بازیگر",
    "خواننده",
    "سلبریتی",
    "کنسرت",
    "فیلم سینمایی",
    "سریال",
]


# ============================================================
# عبارت‌های جست‌وجوی محلی
# ============================================================

SEARCH_TERMS = [
    "سیستان و بلوچستان",
    "زاهدان",
    "زابل",
    "زهک",
    "هیرمند",
    "هامون",
    "نیمروز",
    "رامشار",
    "نصرت آباد",
    "میرجاوه",
    "خاش",
    "تفتان",
    "سراوان",
    "سیب و سوران",
    "مهرستان",
    "گلشن",
    "ایرانشهر",
    "بمپور",
    "بزمان",
    "دلگان",
    "گلمورتی",
    "سرباز",
    "راسک",
    "قصرقند",
    "نیکشهر",
    "فنوج",
    "کنارک",
    "چابهار",
    "دشتیاری",
    "زرآباد",
    "میلک",
    "ریمدان",
    "باهوکلات",
    "نگور",
    "طیس",
    "سواحل مکران",
    "دریای عمان",
    "جازموریان",
    "کوه تفتان",
    "کوه خواجه",
    "شهر سوخته",
    "میل نادر",
    "کورین",
]


# ============================================================
# پاکسازی متن
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
# نرمال‌سازی لینک
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


# ============================================================
# نرمال‌سازی عنوان برای تشخیص خبر تکراری
# ============================================================

def normalize_title(title):
    title = clean_text(title)

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
        title = title.replace(old, new)

    # حذف عبارت‌های رایج غیرمؤثر
    title = re.sub(
        r"^\s*(ببینید|ویدئو|فیلم|عکس|گزارش تصویری)\s*[:：-]?\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )

    # حذف علائم
    title = re.sub(
        r"[^\w\sآ-ی]",
        " ",
        title,
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    return title.strip().lower()


# ============================================================
# دامنه سایت
# ============================================================

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

    return any(
        domain == approved
        or domain.endswith("." + approved)
        for approved in APPROVED_DOMAINS
    )


# ============================================================
# نام رسانه
# ============================================================

def get_source_name(url):
    domain = get_domain(url)

    source_names = {
        "irna.ir": "ایرنا",
        "isna.ir": "ایسنا",
        "mehrnews.com": "مهر",
        "farsnews.ir": "فارس",
        "tasnimnews.com": "تسنیم",
        "ilna.ir": "ایلنا",
        "tabnak.ir": "تابناک",
        "asriran.com": "عصر ایران",
        "fararu.com": "فرارو",
        "jahannews.com": "جهان نیوز",
        "khabaronline.ir": "خبرآنلاین",
        "khabarfouri.com": "خبر فوری",
        "akharinkhabar.ir": "آخرین خبر",
        "roozplus.com": "روزپلاس",
        "hamshahrionline.ir": "همشهری",
        "jamejamonline.ir": "جام جم",
        "yjc.ir": "باشگاه خبرنگاران جوان",
        "entekhab.ir": "انتخاب",
        "iribnews.ir": "خبرگزاری صداوسیما",
        "iribnews.com": "خبرگزاری صداوسیما",
    }

    return source_names.get(
        domain,
        domain,
    )


# ============================================================
# وضعیت خبرهای ارسال‌شده
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


def load_sent_titles():
    if not os.path.exists(TITLE_STATE_FILE):
        return set()

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


def save_sent_title(title):
    normalized = normalize_title(title)

    if not normalized:
        return

    with open(
        TITLE_STATE_FILE,
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            normalized + "\n"
        )


# ============================================================
# تاریخ خبر
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
# خلاصه خبر
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

    if len(description) > 600:
        description = (
            description[:597]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return description


# ============================================================
# ساخت RSS جست‌وجوی Google News
# ============================================================

def make_rss_url(term):
    domains = " OR ".join(
        f"site:{domain}"
        for domain in APPROVED_DOMAINS
    )

    query = (
        f'"{term}" ({domains})'
    )

    return (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + "&hl=fa&gl=IR&ceid=IR:fa"
    )


# ============================================================
# امتیاز ارتباط خبر با استان
# ============================================================

def local_score(title, summary):
    title = clean_text(title)
    summary = clean_text(summary)

    score = 0

    # نام صریح استان در عنوان
    for term in PROVINCE_NAMES:
        if term in title:
            score += 100

    # شهرستان‌ها و مناطق در عنوان
    for term in (
        CITIES_AND_COUNTIES
        + IMPORTANT_LOCAL_AREAS
    ):
        if term in title:
            score += 50

    # موضوعات محلی در عنوان
    for term in LOCAL_SUBJECTS:
        if term in title:
            score += 25

    # ارتباط محلی در خلاصه
    summary_local_count = 0

    for term in (
        PROVINCE_NAMES
        + CITIES_AND_COUNTIES
        + IMPORTANT_LOCAL_AREAS
    ):
        if term in summary:
            summary_local_count += 1

    if summary_local_count >= 2:
        score += 20

    # حذف خبرهای مشخصاً نامرتبط
    for term in UNRELATED_TERMS:
        if term in title:

            has_local_title = any(
                local_term in title
                for local_term in (
                    PROVINCE_NAMES
                    + CITIES_AND_COUNTIES
                    + IMPORTANT_LOCAL_AREAS
                )
            )

            if not has_local_title:
                return 0

    return score


# ============================================================
# تشخیص واقعی بودن ارتباط خبر
# ============================================================

def is_local_news(title, summary):
    title = clean_text(title)
    summary = clean_text(summary)

    # استان صریحاً در عنوان
    if any(
        term in title
        for term in PROVINCE_NAMES
    ):
        return True

    # شهر یا منطقه مشخص در عنوان
    if any(
        term in title
        for term in (
            CITIES_AND_COUNTIES
            + IMPORTANT_LOCAL_AREAS
        )
    ):
        return True

    # موضوع محلی + زمینه محلی
    has_local_subject = any(
        term in title
        for term in LOCAL_SUBJECTS
    )

    has_local_context = any(
        term in summary
        for term in (
            PROVINCE_NAMES
            + CITIES_AND_COUNTIES
            + IMPORTANT_LOCAL_AREAS
        )
    )

    if (
        has_local_subject
        and has_local_context
    ):
        return True

    return False


# ============================================================
# دریافت RSS
# ============================================================

def fetch_feed(url):
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "JahantabNewsBot/3.0"
            },
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


# ============================================================
# پیدا کردن تصویر خبر
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
                    "Mozilla/5.0 "
                    "JahantabNewsBot/3.0"
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
            return image[
                "content"
            ].strip()

        image = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            },
        )

        if image and image.get("content"):
            return image[
                "content"
            ].strip()

    except Exception as exc:
        print(
            f"Image lookup failed: {exc}"
        )

    return None


# ============================================================
# جمع‌آوری اخبار
# ============================================================

def collect_news():
    now = datetime.now(
        timezone.utc
    )

    max_age = timedelta(
        hours=24
    )

    collected = {}

    for term in SEARCH_TERMS:

        print(
            f"RSS search: {term}"
        )

        rss_url = make_rss_url(
            term
        )

        feed = fetch_feed(
            rss_url
        )

        if not feed:
            continue

        print(
            f"RSS entries for "
            f"{term}: "
            f"{len(feed.entries)}"
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

            # فقط رسانه‌های مجاز
            if not is_approved_source(
                link
            ):
                continue

            published = parse_date(
                entry
            )

            if published:

                age = now - published

                if (
                    age < timedelta(0)
                    or age > max_age
                ):
                    continue

            summary = make_summary(
                entry
            )

            # فیلتر محلی
            if not is_local_news(
                title,
                summary,
            ):

                print(
                    "Rejected unrelated:",
                    title,
                )

                continue

            score = local_score(
                title,
                summary,
            )

            # خبر تکراری در همان اجرای برنامه
            if link in collected:
                continue

            collected[link] = {
                "title": title,
                "summary": summary,
                "link": link,
                "published": (
                    published
                    or now
                ),
                "score": score,
                "source": get_source_name(
                    link
                ),
            }

    news = list(
        collected.values()
    )

    news.sort(
        key=lambda item: (
            item["score"],
            item["published"],
        ),
        reverse=True,
    )

    return news


# ============================================================
# تشخیص محل خبر
# ============================================================

def detect_location(title, summary):
    text = (
        title
        + " "
        + summary
    )

    if any(
        term in text
        for term in PROVINCE_NAMES
    ):
        return "سیستان و بلوچستان"

    # ابتدا مناطق دقیق
    for term in (
        CITIES_AND_COUNTIES
        + IMPORTANT_LOCAL_AREAS
    ):
        if term in title:
            return term

    for term in (
        CITIES_AND_COUNTIES
        + IMPORTANT_LOCAL_AREAS
    ):
        if term in summary:
            return term

    return "سیستان و بلوچستان"


# ============================================================
# دکمه‌های زیر خبر
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
# درخواست به API بله
# ============================================================

def bale_request(
    method,
    data=None,
    files=None,
):
    url = (
        f"https://tapi.bale.ai/"
        f"bot{BOT_TOKEN}/"
        f"{method}"
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
# ارسال متن
# ============================================================

def send_text(item):
    title = item["title"]
    summary = item["summary"]
    link = item["link"]
    source = item["source"]

    location = detect_location(
        title,
        summary,
    )

    text = (
        f"🚨 {location}\n\n"
        f"📰 {title}\n\n"
    )

    if summary:
        text += (
            summary
            + "\n\n"
        )

    text += (
        f"🗞 منبع: {source}\n\n"
        f"🌐 جهان‌تاب"
    )

    return bale_request(
        "sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "reply_markup":
                make_reply_markup(
                    link
                ),
        },
    )


# ============================================================
# ارسال عکس
# ============================================================

def send_photo(
    item,
    image_url,
):
    title = item["title"]
    summary = item["summary"]
    link = item["link"]
    source = item["source"]

    location = detect_location(
        title,
        summary,
    )

    caption = (
        f"🚨 {location}\n\n"
        f"📰 {title}\n\n"
    )

    if summary:
        caption += (
            summary
            + "\n\n"
        )

    caption += (
        f"🗞 منبع: {source}\n\n"
        f"🌐 جهان‌تاب"
    )

    caption = caption[:1000]

    try:

        image_response = requests.get(
            image_url,
            timeout=15,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "JahantabNewsBot/3.0"
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
                        link
                    ),
            },
            files=files,
        )

    except Exception as exc:

        print(
            f"Photo send failed: {exc}"
        )

        # اگر ارسال عکس مشکل داشت،
        # متن خبر ارسال می‌شود.
        return send_text(
            item
        )


# ============================================================
# اجرای اصلی
# ============================================================

def main():

    print(
        "==================================="
    )

    print(
        "Jahantab Bale News Bot"
    )

    print(
        "Sistan & Baluchestan Edition"
    )

    print(
        "==================================="
    )

    sent_links = (
        load_sent_links()
    )

    sent_titles = (
        load_sent_titles()
    )

    print(
        f"Previously sent links: "
        f"{len(sent_links)}"
    )

    print(
        f"Previously sent titles: "
        f"{len(sent_titles)}"
    )

    news = collect_news()

    print(
        "-----------------------------------"
    )

    print(
        f"Relevant local news found: "
        f"{len(news)}"
    )

    print(
        "-----------------------------------"
    )

    # حداکثر ۵ خبر در هر اجرای ۱۰ دقیقه‌ای
    MAX_PER_RUN = 5

    new_count = 0

    for item in news:

        if new_count >= MAX_PER_RUN:
            break

        link = item["link"]

        normalized_title = (
            normalize_title(
                item["title"]
            )
        )

        # -----------------------------------------------
        # جلوگیری از تکرار بر اساس لینک
        # -----------------------------------------------

        if link in sent_links:

            print(
                "Already sent by link:",
                item["title"],
            )

            continue

        # -----------------------------------------------
        # جلوگیری از تکرار بر اساس عنوان
        # -----------------------------------------------

        if normalized_title in sent_titles:

            print(
                "Already sent by title:",
                item["title"],
            )

            continue

        print(
            "Publishing:",
            item["title"],
        )

        print(
            "Source:",
            item["source"],
        )

        print(
            "Location:",
            detect_location(
                item["title"],
                item["summary"],
            ),
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

            # -------------------------------------------
            # فقط بعد از ارسال موفق ذخیره شود
            # -------------------------------------------

            save_sent_link(
                link
            )

            sent_links.add(
                link
            )

            save_sent_title(
                item["title"]
            )

            sent_titles.add(
                normalized_title
            )

            new_count += 1

            print(
                "Published successfully."
            )

        except Exception as exc:

            print(
                "Publish failed:",
                exc,
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


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()