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


# Google News RSS searches
# تمرکز اصلی: سیستان و بلوچستان
SISTAN_FEEDS = [
    "https://news.google.com/rss/search?q="
    + quote('"سیستان و بلوچستان"')
    + "&hl=fa&gl=IR&ceid=IR:fa",

    "https://news.google.com/rss/search?q="
    + quote('"زاهدان" OR "زابل" OR "چابهار" OR "سراوان" OR "ایرانشهر" OR "خاش"')
    + "&hl=fa&gl=IR&ceid=IR:fa",
]


# اخبار مهم و فوری ایران
IRAN_FEEDS = [
    "https://news.google.com/rss/search?q="
    + quote('ایران (فوری OR مهم OR "خبر فوری" OR "آخرین خبر")')
    + "&hl=fa&gl=IR&ceid=IR:fa",

    "https://news.google.com/rss/search?q="
    + quote('"خبر فوری ایران" OR "فوری ایران"')
    + "&hl=fa&gl=IR&ceid=IR:fa",
]


# ============================================================
# FILTERS
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
    "زهک