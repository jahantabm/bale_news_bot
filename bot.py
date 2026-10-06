# -*- coding: utf-8 -*-

"""
JAHANTAB | جهان‌تاب
Telegram -> Bale Mirror

هر چیزی که در کانال تلگرام @jahantab_news منتشر شود:
- متن
- عکس
- ویدئو
- آهنگ / Audio
- Voice
- فایل / Document
- GIF / Animation

به کانال بله منتقل می‌شود.

هیچ RSS یا تولید خبر مستقلی در این نسخه وجود ندارد.
"""

import os
import json
import time
import logging
import tempfile
from pathlib import Path

import requests


# ============================================================
# CONFIG
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BALE_BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
BALE_CHAT_ID = os.getenv("BALE_CHAT_ID")

TELEGRAM_CHANNEL_USERNAME = os.getenv(
    "TELEGRAM_CHANNEL_USERNAME",
    "jahantab_news"
).lstrip("@").lower()

OFFSET_FILE = "telegram_offset.json"

TELEGRAM_API = "https://api.telegram.org/bot"
TELEGRAM_FILE_API = "https://api.telegram.org/file/bot"
BALE_API = "https://tapi.bale.ai/bot"

TELEGRAM_URL = "https://t.me/jahantab_news"
BALE_URL = "https://ble.ir/jahantabnews"
SOROUSH_URL = "https://splus.ir/jahantabnews"

TIMEOUT = 90

# Telegram getUpdates
MAX_UPDATES = 100

# Bale text/caption safe limits
BALE_TEXT_LIMIT = 3900
BALE_CAPTION_LIMIT = 950


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("JAHANTAB-BRIDGE")


# ============================================================
# HTTP SESSION
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": "JAHANTAB-Telegram-Bale-Bridge/2.0"
})


# ============================================================
# VALIDATION
# ============================================================

def validate_config():
    missing = []

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not BALE_BOT_TOKEN:
        missing.append("BALE_BOT_TOKEN")

    if not BALE_CHAT_ID:
        missing.append("BALE_CHAT_ID")

    if missing:
        raise RuntimeError(
            "Missing environment variables: "
            + ", ".join(missing)
        )


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_call(method, payload=None):

    url = (
        f"{TELEGRAM_API}"
        f"{TELEGRAM_BOT_TOKEN}/"
        f"{method}"
    )

    response = session.post(
        url,
        json=payload or {},
        timeout=TIMEOUT
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {data}"
        )

    return data.get("result")


# ============================================================
# BALE API
# ============================================================

def bale_call(method, data=None, files=None):

    url = (
        f"{BALE_API}"
        f"{BALE_BOT_TOKEN}/"
        f"{method}"
    )

    response = session.post(
        url,
        data=data or {},
        files=files,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok", False):
        raise RuntimeError(
            f"Bale API error: {result}"
        )

    return result.get("result")


# ============================================================
# OFFSET
# ============================================================

def load_offset():

    path = Path(OFFSET_FILE)

    if not path.exists():
        return None

    try:

        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        return int(data["offset"])

    except Exception as exc:

        log.warning(
            "Could not read offset: %s",
            exc
        )

        return None


def save_offset(offset):

    path = Path(OFFSET_FILE)
    tmp = Path(str(path) + ".tmp")

    tmp.write_text(
        json.dumps(
            {"offset": int(offset)},
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    tmp.replace(path)

    log.info(
        "Saved offset: %s",
        offset
    )


# ============================================================
# GET TELEGRAM UPDATES
# ============================================================

def get_updates(offset=None):

    payload = {
        "limit": MAX_UPDATES,
        "timeout": 5,
        "allowed_updates": [
            "channel_post"
        ]
    }

    if offset is not None:
        payload["offset"] = offset

    return telegram_call(
        "getUpdates",
        payload
    )


# ============================================================
# CHECK TARGET CHANNEL
# ============================================================

def is_target_channel(message):

    chat = message.get("chat") or {}

    if chat.get("type") != "channel":
        return False

    username = (
        chat.get("username") or ""
    ).lstrip("@").lower()

    return username == TELEGRAM_CHANNEL_USERNAME


# ============================================================
# DOWNLOAD TELEGRAM FILE
# ============================================================

def download_telegram_file(
    file_id,
    suffix=""
):

    info = telegram_call(
        "getFile",
        {
            "file_id": file_id
        }
    )

    file_path = info.get("file_path")

    if not file_path:
        raise RuntimeError(
            "Telegram did not return file_path"
        )

    url = (
        f"{TELEGRAM_FILE_API}"
        f"{TELEGRAM_BOT_TOKEN}/"
        f"{file_path}"
    )

    response = session.get(
        url,
        timeout=TIMEOUT,
        stream=True
    )

    response.raise_for_status()

    if not suffix and "." in file_path:
        suffix = "." + file_path.split(".")[-1]

    temp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix
    )

    try:

        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):

            if chunk:
                temp.write(chunk)

        temp.close()

        return temp.name

    except Exception:

        temp.close()

        try:
            os.unlink(temp.name)
        except Exception:
            pass

        raise


# ============================================================
# TEXT / CAPTION
# ============================================================

def get_text(message):

    return (
        message.get("text")
        or message.get("caption")
        or ""
    ).strip()


def split_text(text):

    if not text:
        return []

    if len(text) <= BALE_TEXT_LIMIT:
        return [text]

    result = []

    remaining = text

    while len(remaining) > BALE_TEXT_LIMIT:

        cut = remaining.rfind(
            "\n",
            0,
            BALE_TEXT_LIMIT
        )

        if cut < 100:
            cut = remaining.rfind(
                " ",
                0,
                BALE_TEXT_LIMIT
            )

        if cut < 100:
            cut = BALE_TEXT_LIMIT

        result.append(
            remaining[:cut].strip()
        )

        remaining = remaining[cut:].strip()

    if remaining:
        result.append(remaining)

    return result


# ============================================================
# CHANNEL BUTTONS
# ============================================================

def extract_source_url(text):

    if not text:
        return None

    import re

    urls = re.findall(
        r"https?://[^\s<>\]\)]+",
        text,
        flags=re.IGNORECASE
    )

    for url in urls:

        url = url.rstrip(
            ".,،؛:!؟)]}"
        )

        lower = url.lower()

        if (
            "t.me/jahantab_news" in lower
            or "ble.ir/jahantabnews" in lower
            or "splus.ir/jahantabnews" in lower
        ):
            continue

        return url

    return None


def build_keyboard(text=""):

    rows = []

    source_url = extract_source_url(text)

    if source_url:

        rows.append([
            {
                "text": "🔗 مشاهده خبر",
                "url": source_url
            }
        ])

    rows.append([
        {
            "text": "📨 تلگرام",
            "url": TELEGRAM_URL
        },
        {
            "text": "🟦 بله",
            "url": BALE_URL
        },
        {
            "text": "🟠 سروش",
            "url": SOROUSH_URL
        }
    ])

    return json.dumps(
        {
            "inline_keyboard": rows
        },
        ensure_ascii=False
    )


# ============================================================
# SEND TEXT
# ============================================================

def send_text(text):

    parts = split_text(text)

    if not parts:
        return False

    keyboard = build_keyboard(text)

    for index, part in enumerate(parts):

        data = {
            "chat_id": BALE_CHAT_ID,
            "text": part
        }

        if index == len(parts) - 1:
            data["reply_markup"] = keyboard

        bale_call(
            "sendMessage",
            data=data
        )

    return True


# ============================================================
# SEND MEDIA
# ============================================================

def send_media(
    method,
    field,
    file_path,
    caption="",
    original_text=""
):

    caption = caption or ""

    # Caption fits into one Bale media message.
    if len(caption) <= BALE_CAPTION_LIMIT:

        data = {
            "chat_id": BALE_CHAT_ID,
            "caption": caption,
            "reply_markup": build_keyboard(
                original_text or caption
            )
        }

        with open(
            file_path,
            "rb"
        ) as media:

            bale_call(
                method,
                data=data,
                files={
                    field: media
                }
            )

        return True

    # Caption is too long:
    # send media first, then complete text.
    data = {
        "chat_id": BALE_CHAT_ID
    }

    with open(
        file_path,
        "rb"
    ) as media:

        bale_call(
            method,
            data=data,
            files={
                field: media
            }
        )

    send_text(caption)

    return True


# ============================================================
# PHOTO
# ============================================================

def mirror_photo(message):

    photos = message.get("photo") or []

    if not photos:
        return False

    photo = photos[-1]

    file_id = photo.get("file_id")

    if not file_id:
        return False

    caption = get_text(message)

    path = download_telegram_file(
        file_id,
        ".jpg"
    )

    try:

        return send_media(
            "sendPhoto",
            "photo",
            path,
            caption,
            caption
        )

    finally:

        try:
            os.unlink(path)
        except Exception:
            pass


# ============================================================
# VIDEO
# ============================================================

def mirror_video(message):

    video = message.get("video")

    if not video:
        return False

    file_id = video.get("file_id")

    if not file_id:
        return False

    caption = get_text(message)

    path = download_telegram_file(
        file_id,
        ".mp4"
    )

    try:

        return send_media(
            "sendVideo",
            "video",
            path,
            caption,
            caption
        )

    finally:

        try:
            os.unlink(path)
        except Exception:
            pass


# ============================================================
# AUDIO / MUSIC
# ============================================================

def mirror_audio(message):

    audio = message.get("audio")

    if not audio:
        return False

    file_id = audio.get("file_id")

    if not file_id:
        return False

    caption = get_text(message)

    file_name = audio.get(
        "file_name",
        "audio"
    )

    suffix = ""

    if "." in file_name:
        suffix = "." + file_name.split(".")[-1]

    path = download_telegram_file(
        file_id,
        suffix
    )

    try:

        return send_media(
            "sendAudio",
            "audio",
            path,
            caption,
            caption
        )

    finally:

        try:
            os.unlink(path)
        except Exception:
            pass


# ============================================================
# VOICE
# ============================================================

def mirror_voice(message):

    voice = message.get("voice")

    if not voice:
        return False

    file_id = voice.get("file_id")

    if not file_id:
        return False

    caption = get_text(message)

    path = download_telegram_file(
        file_id,
        ".ogg"
    )

    try:

        return send_media(
            "sendVoice",
            "voice",
            path,
            caption,
            caption
        )

    finally:

        try:
            os.unlink(path)
        except Exception:
            pass


# ============================================================
# DOCUMENT / FILE
# ============================================================

def mirror_document(message):

    document = message.get("document")

    if not document:
        return False

    file_id = document.get("file_id")

    if not file_id:
        return False

    caption = get_text(message)

    file_name = document.get(
        "file_name",
        "file"
    )

    suffix = ""

    if "." in file_name:
        suffix = "." + file_name.split(".")[-1]

    path = download_telegram_file(
        file_id,
        suffix
    )

    try:

        return send_media(
            "sendDocument",
            "document",
            path,
            caption,
            caption
        )

    finally:

        try:
            os.unlink(path)
        except Exception:
            pass


# ============================================================
# ANIMATION / GIF
# ============================================================

def mirror_animation(message):

    animation = message.get("animation")

    if not animation:
        return False

    file_id = animation.get("file_id")

    if not file_id:
        return False

    caption = get_text(message)

    path = download_telegram_file(
        file_id,
        ".mp4"
    )

    try:

        return send_media(
            "sendAnimation",
            "animation",
            path,
            caption,
            caption
        )

    finally:

        try:
            os.unlink(path)
        except Exception:
            pass


# ============================================================
# ROUTER
# ============================================================

def mirror_post(message):

    message_id = message.get(
        "message_id"
    )

    log.info(
        "Processing Telegram post %s",
        message_id
    )

    if not is_target_channel(message):

        chat = message.get("chat") or {}

        log.info(
            "Skipped channel: %s",
            chat.get("username")
            or chat.get("title")
        )

        return True

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    if message.get("photo"):

        log.info(
            "Post %s -> PHOTO",
            message_id
        )

        return mirror_photo(message)

    # --------------------------------------------------------
    # VIDEO
    # --------------------------------------------------------

    if message.get("video"):

        log.info(
            "Post %s -> VIDEO",
            message_id
        )

        return mirror_video(message)

    # --------------------------------------------------------
    # AUDIO / MUSIC
    # --------------------------------------------------------

    if message.get("audio"):

        log.info(
            "Post %s -> AUDIO",
            message_id
        )

        return mirror_audio(message)

    # --------------------------------------------------------
    # VOICE
    # --------------------------------------------------------

    if message.get("voice"):

        log.info(
            "Post %s -> VOICE",
            message_id
        )

        return mirror_voice(message)

    # --------------------------------------------------------
    # DOCUMENT
    # --------------------------------------------------------

    if message.get("document"):

        log.info(
            "Post %s -> DOCUMENT",
            message_id
        )

        return mirror_document(message)

    # --------------------------------------------------------
    # ANIMATION
    # --------------------------------------------------------

    if message.get("animation"):

        log.info(
            "Post %s -> ANIMATION",
            message_id
        )

        return mirror_animation(message)

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    if message.get("text"):

        log.info(
            "Post %s -> TEXT",
            message_id
        )

        return send_text(
            message.get("text", "")
        )

    # --------------------------------------------------------
    # UNSUPPORTED
    # --------------------------------------------------------

    log.warning(
        "Post %s has unsupported Telegram content type.",
        message_id
    )

    # Mark as processed so the workflow does not get stuck.
    return True


# ============================================================
# PROCESS UPDATES
# ============================================================

def process_updates():

    offset = load_offset()

    updates = get_updates(offset)

    if not updates:

        log.info(
            "No new Telegram posts."
        )

        return

    log.info(
        "Received %d update(s).",
        len(updates)
    )

    for update in updates:

        update_id = update.get(
            "update_id"
        )

        if update_id is None:
            continue

        channel_post = update.get(
            "channel_post"
        )

        # We only process channel_post.
        if not channel_post:

            save_offset(
                update_id + 1
            )

            continue

        try:

            success = mirror_post(
                channel_post
            )

            if not success:
                raise RuntimeError(
                    "Mirror returned False"
                )

            # Only after successful publishing.
            save_offset(
                update_id + 1
            )

            log.info(
                "Update %s completed.",
                update_id
            )

        except Exception as exc:

            log.error(
                "Update %s failed: %s",
                update_id,
                exc
            )

            # Do NOT advance offset.
            # The next GitHub Actions run will retry it.
            raise


# ============================================================
# MAIN
# ============================================================

def main():

    log.info("=" * 60)
    log.info(
        "JAHANTAB TELEGRAM -> BALE MIRROR"
    )
    log.info("=" * 60)

    validate_config()

    log.info(
        "Source: @%s",
        TELEGRAM_CHANNEL_USERNAME
    )

    log.info(
        "Destination: %s",
        BALE_CHAT_ID
    )

    process_updates()

    log.info(
        "Run completed successfully."
    )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        log.info(
            "Stopped."
        )

    except Exception as exc:

        log.exception(
            "Bridge failed: %s",
            exc
        )

        raise