import os, re, html, time
from pathlib import Path
from urllib.parse import urljoin
import feedparser
import requests
from bs4 import BeautifulSoup

TOKEN = os.environ["BALE_BOT_TOKEN"]
CHAT_ID = os.environ["BALE_CHAT_ID"]
BALE_API = f"https://tapi.bale.ai/bot{TOKEN}"
SENT_FILE = Path("sent_links.txt")
MAX_SENT = 3000
MAX_POSTS_PER_RUN = 8

FEEDS = {
    "تابناک": "https://www.tabnak.ir/fa/rss/allnews",
    "فرارو": "https://fararu.com/fa/rss/allnews",
    "همشهری آنلاین": "https://www.hamshahrionline.ir/rss",
    "خبر فوری": "https://www.khabarfoori.com/rss",
    "آخرین خبر": "https://akharinkhabar.ir/rss",
    "مهر": "https://www.mehrnews.com/rss",
    "ایسنا": "https://www.isna.ir/rss",
    "ایرنا": "https://www.irna.ir/rss",
    "تسنیم": "https://www.tasnimnews.com/fa/rss",
}

SISTAN_TERMS = [
    "سیستان و بلوچستان","سیستان","بلوچستان","زاهدان","چابهار","ایرانشهر",
    "سراوان","زابل","نیکشهر","کنارک","خاش","دلگان","راسک","سرباز",
    "میرجاوه","هیرمند","زهک","هامون","بمپور","فنوج","قصرقند","دشتیاری",
    "تفتان","مهرستان","سیب و سوران","بزمان","جنوب شرق","مرز پاکستان",
    "مرز میرجاوه"
]
URGENT_TERMS = [
    "فوری","خبر فوری","آنی","لحظه به لحظه","کشته","جان باخت","انفجار",
    "آتش سوزی","آتش‌سوزی","زلزله","سیل","هشدار","تعطیلی","تعطیل",
    "قطعی","تصادف","واژگونی","عملیات","حمله","درگیری","بازداشت","حادثه",
    "مفقود","سقوط","ریزش","مسدود","حمله موشکی","اصابت","ترور",
    "تصمیم مهم","ابلاغ","تصویب","استعفا","انتخابات"
]
NATIONAL_TERMS = [
    "ایران","تهران","دولت","رئیس جمهور","مجلس","بانک مرکزی","وزارت کشور",
    "وزارت نفت","وزارت نیرو","وزارت دفاع","نیروهای مسلح","سپاه","ارتش",
    "پدافند","اقتصاد","ارز","دلار","بورس","بنزین","برق","گاز","نفت","آب",
    "مدارس","دانشگاه","پرواز","راه آهن","فرودگاه"
]
LOW_VALUE_TERMS = ["فال","سرگرمی","آشپزی","مد","لایف استایل","چهره","تبریک","تولد","عکس روز"]

def clean_text(text):
    text = html.unescape(text or "")
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()

def load_sent():
    if not SENT_FILE.exists(): return set()
    return {x.strip() for x in SENT_FILE.read_text(encoding="utf-8").splitlines() if x.strip()}

def save_sent(items):
    vals = list(items)[-MAX_SENT:]
    SENT_FILE.write_text("\n".join(vals) + ("\n" if vals else ""), encoding="utf-8")

def entry_text(entry):
    return f'{clean_text(entry.get("title",""))} {clean_text(entry.get("summary","") or entry.get("description",""))}'

def score_item(text):
    t = text.lower()
    sistan = sum(x.lower() in t for x in SISTAN_TERMS)
    urgent = sum(x.lower() in t for x in URGENT_TERMS)
    national = sum(x.lower() in t for x in NATIONAL_TERMS)
    low = sum(x.lower() in t for x in LOW_VALUE_TERMS)
    score = sistan * 10 + urgent * 6 + national * 2 - low * 8
    return score, (sistan > 0 or (urgent >= 1 and national >= 1))

def extract_summary(entry):
    title = clean_text(entry.get("title",""))
    raw = clean_text(entry.get("summary","") or entry.get("description",""))
    if not raw: return title
    sentences = [s.strip() for s in re.split(r"(?<=[.!؟])\s+", raw) if len(s.strip()) > 25]
    body = sentences[0] if sentences else raw
    return body if len(body) <= 280 else body[:277].rsplit(" ",1)[0] + "..."

def find_image(entry):
    for key in ("media_content","media_thumbnail"):
        media = entry.get(key) or []
        if media and media[0].get("url"): return media[0]["url"]
    for enc in entry.get("enclosures",[]) or []:
        url = enc.get("href") or enc.get("url")
        if url and ("image" in (enc.get("type") or "").lower() or not enc.get("type")): return url
    link = entry.get("link")
    if not link: return None
    try:
        r = requests.get(link, timeout=12, headers={"User-Agent":"Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        og = soup.find("meta", property="og:image")
        return urljoin(link, og["content"]) if og and og.get("content") else None
    except Exception:
        return None

def send_message(text, url):
    payload = {"chat_id": CHAT_ID, "text": text,
               "reply_markup":{"inline_keyboard":[[{"text":"🔗 مشاهده خبر","url":url}]]}}
    requests.post(f"{BALE_API}/sendMessage", json=payload, timeout=20).raise_for_status()

def send_photo(image_url, caption, url):
    payload = {"chat_id":CHAT_ID,"photo":image_url,"caption":caption,
               "reply_markup":{"inline_keyboard":[[{"text":"🔗 مشاهده خبر","url":url}]]}}
    requests.post(f"{BALE_API}/sendPhoto", json=payload, timeout=25).raise_for_status()

def publish(source, entry):
    title = clean_text(entry.get("title",""))
    url = (entry.get("link") or "").strip()
    caption = f"📰 {title}\n\n{extract_summary(entry)}\n\nمنبع: {source}"
    image = find_image(entry)
    if image:
        try:
            send_photo(image, caption, url); return
        except Exception:
            pass
    send_message(caption, url)

def main():
    sent = load_sent()
    candidates = []
    for source, feed_url in FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:40]:
                url = (entry.get("link") or "").strip()
                if not url or url in sent: continue
                score, accepted = score_item(entry_text(entry))
                if accepted: candidates.append((score, source, entry))
        except Exception as exc:
            print(f"[WARN] {source}: {exc}")
    candidates.sort(key=lambda x:x[0], reverse=True)
    published = 0
    for _, source, entry in candidates:
        url = (entry.get("link") or "").strip()
        if not url or url in sent: continue
        try:
            publish(source, entry); sent.add(url); published += 1; time.sleep(1)
            if published >= MAX_POSTS_PER_RUN: break
        except Exception as exc:
            print(f"[WARN] publish failed: {url} -> {exc}")
    save_sent(sent)
    print(f"Published: {published}; tracked links: {len(sent)}")

if __name__ == "__main__":
    main()