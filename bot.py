
# -*- coding: utf-8 -*-
"""
JAHANTAB | Telegram -> Bale + Rubika
"""

import os
import json
import logging
import tempfile
import re
from pathlib import Path

import requests

# ============================================================
# CONFIG
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BALE_BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")
BALE_CHAT_ID = os.getenv("BALE_CHAT_ID")

RUBIKA_BOT_TOKEN = os.getenv("RUBIKA_BOT_TOKEN")
RUBIKA_CHAT_ID = os.getenv("RUBIKA_CHAT_ID")

TELEGRAM_CHANNEL_USERNAME = os.getenv(
    "TELEGRAM_CHANNEL_USERNAME", "jahantab_news"
).lstrip("@").lower()

OFFSET_FILE = "telegram_offset.json"
DELIVERY_FILE = "delivery_state.json"

TELEGRAM_API = "https://api.telegram.org/bot"
TELEGRAM_FILE_API = "https://api.telegram.org/file/bot"
BALE_API = "https://tapi.bale.ai/bot"
RUBIKA_API = "https://botapi.rubika.ir/v3"

TELEGRAM_URL = "https://t.me/jahantab_news"
BALE_URL = "https://ble.ir/jahantabnews"
SOROUSH_URL = "https://splus.ir/jahantabnews"

TIMEOUT = 90
MAX_UPDATES = 100
BALE_TEXT_LIMIT = 3900
BALE_CAPTION_LIMIT = 950
RUBIKA_TEXT_LIMIT = 4000
RUBIKA_CAPTION_LIMIT = 900

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("JAHANTAB-BRIDGE")

session = requests.Session()
session.headers.update({
    "User-Agent": "JAHANTAB-Telegram-Bridge/5.0"
})


# ============================================================
# CONFIG VALIDATION
# ============================================================

def validate_config():
    config = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "BALE_BOT_TOKEN": os.getenv("BALE_BOT_TOKEN"),
        "BALE_CHAT_ID": os.getenv("BALE_CHAT_ID"),
        "RUBIKA_BOT_TOKEN": os.getenv("RUBIKA_BOT_TOKEN"),
        "RUBIKA_CHAT_ID": os.getenv("RUBIKA_CHAT_ID"),
    }

    missing = [
        name for name, value in config.items()
        if not value or not value.strip()
    ]

    log.info(
        "RUBIKA_CHAT_ID available: %s",
        bool(config["RUBIKA_CHAT_ID"])
    )

    if missing:
        raise RuntimeError(
            "Missing GitHub Actions variables/secrets: "
            + ", ".join(missing)
        )


# ============================================================
# API HELPERS
# ============================================================

def telegram_call(method, payload=None):
    url = f"{TELEGRAM_API}{TELEGRAM_BOT_TOKEN}/{method}"
    response = session.post(
        url, json=payload or {}, timeout=TIMEOUT
    )
    response.raise_for_status()
    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram API error in {method}: "
            f"{json.dumps(result, ensure_ascii=False)[:1000]}"
        )

    return result.get("result")


def bale_call(method, data=None, files=None):
    url = f"{BALE_API}{BALE_BOT_TOKEN}/{method}"
    response = session.post(
        url, data=data or {}, files=files, timeout=TIMEOUT
    )
    response.raise_for_status()
    result = response.json()

    if not result.get("ok", False):
        raise RuntimeError(
            f"Bale API error in {method}: "
            f"{json.dumps(result, ensure_ascii=False)[:1000]}"
        )

    return result.get("result")


def rubika_call(method, payload=None, files=None):
    url = f"{RUBIKA_API}/{RUBIKA_BOT_TOKEN}/{method}"

    try:
        if files:
            response = session.post(
                url,
                data=payload or {},
                files=files,
                timeout=TIMEOUT
            )
        else:
            response = session.post(
                url,
                json=payload or {},
                timeout=TIMEOUT
            )
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Rubika network error in {method}: "
            f"{type(exc).__name__}: {str(exc)[:500]}"
        ) from exc

    if not response.ok:
        raise RuntimeError(
            f"Rubika HTTP {response.status_code} in {method}: "
            f"{response.text[:1200]}"
        )

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Rubika returned non-JSON response in {method}: "
            f"{response.text[:1200]}"
        ) from exc

    status = str(result.get("status", "")).lower()

    if status not in ("ok", "success"):
        # Never print the request URL: it contains the bot token.
        safe_result = dict(result)
        for key in ("token", "auth", "bot_token"):
            safe_result.pop(key, None)

        raise RuntimeError(
            f"Rubika API error in {method}: "
            f"{json.dumps(safe_result, ensure_ascii=False)[:1500]}"
        )

    return result.get("data", result)


# ============================================================
# STATE FILES
# ============================================================

def read_json(path, default):
    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ValueError, OSError):
        return default


def write_json(path, data):
    target = Path(path)
    temp = Path(str(target) + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    temp.replace(target)


def load_offset():
    data = read_json(OFFSET_FILE, {})
    try:
        return int(data["offset"])
    except (KeyError, TypeError, ValueError):
        return None


def save_offset(offset):
    write_json(OFFSET_FILE, {"offset": int(offset)})
    log.info("Saved Telegram offset: %s", offset)


def load_delivery_state():
    state = read_json(DELIVERY_FILE, {})
    return state if isinstance(state, dict) else {}


def save_delivery_state(state):
    if len(state) > 1000:
        keys = sorted(
            state.keys(),
            key=lambda x: int(x) if x.isdigit() else 0
        )
        for key in keys[:-800]:
            state.pop(key, None)

    write_json(DELIVERY_FILE, state)


# ============================================================
# TELEGRAM UPDATES / FILES
# ============================================================

def get_updates(offset=None):
    payload = {
        "limit": MAX_UPDATES,
        "timeout": 5,
        "allowed_updates": ["channel_post"]
    }

    if offset is not None:
        payload["offset"] = offset

    return telegram_call("getUpdates", payload)


def is_target_channel(message):
    chat = message.get("chat") or {}
    username = (chat.get("username") or "").lstrip("@").lower()

    return (
        chat.get("type") == "channel"
        and username == TELEGRAM_CHANNEL_USERNAME
    )


def download_telegram_file(file_id, suffix=""):
    info = telegram_call("getFile", {"file_id": file_id})
    file_path = info.get("file_path")

    if not file_path:
        raise RuntimeError("Telegram did not return file_path")

    url = f"{TELEGRAM_FILE_API}{TELEGRAM_BOT_TOKEN}/{file_path}"
    response = session.get(url, timeout=TIMEOUT, stream=True)
    response.raise_for_status()

    if not suffix and "." in file_path:
        suffix = "." + file_path.rsplit(".", 1)[-1]

    temp = tempfile.NamedTemporaryFile(
        delete=False, suffix=suffix
    )

    try:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                temp.write(chunk)

        temp.close()
        return temp.name

    except Exception:
        temp.close()
        try:
            os.unlink(temp.name)
        except OSError:
            pass
        raise


# ============================================================
# TEXT / BUTTONS
# ============================================================

def get_text(message):
    return (
        message.get("text")
        or message.get("caption")
        or ""
    ).strip()


def split_text(text, limit):
    if not text:
        return []

    parts = []
    remaining = text.strip()

    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)

        if cut < 100:
            cut = remaining.rfind(" ", 0, limit)

        if cut < 100:
            cut = limit

        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    if remaining:
        parts.append(remaining)

    return parts


def extract_source_url(text):
    if not text:
        return None

    urls = re.findall(
        r"https?://[^\s<>\]\)]+",
        text,
        flags=re.I
    )

    for url in urls:
        url = url.rstrip(".,،؛:!؟)]}")
        low = url.lower()

        if any(x in low for x in (
            "t.me/jahantab_news",
            "ble.ir/jahantabnews",
            "splus.ir/jahantabnews"
        )):
            continue

        return url

    return None


def build_bale_keyboard(text=""):
    rows = []
    source_url = extract_source_url(text)

    if source_url:
        rows.append([{
            "text": "🔗 مشاهده خبر",
            "url": source_url
        }])

    rows.append([
        {"text": "📨 تلگرام", "url": TELEGRAM_URL},
        {"text": "🟦 بله", "url": BALE_URL},
        {"text": "🟠 سروش", "url": SOROUSH_URL}
    ])

    return json.dumps(
        {"inline_keyboard": rows},
        ensure_ascii=False
    )


# ============================================================
# SEND TEXT TO BALE
# ============================================================

def send_bale_text(text):
    parts = split_text(text, BALE_TEXT_LIMIT)

    if not parts:
        return True

    keyboard = build_bale_keyboard(text)

    for index, part in enumerate(parts):
        data = {
            "chat_id": BALE_CHAT_ID,
            "text": part
        }

        if index == len(parts) - 1:
            data["reply_markup"] = keyboard

        bale_call("sendMessage", data=data)

    return True


# ============================================================
# SEND MEDIA TO BALE
# ============================================================

def send_bale_media(
    method, field, file_path, caption="", original_text=""
):
    caption = caption or ""

    if len(caption) <= BALE_CAPTION_LIMIT:
        data = {
            "chat_id": BALE_CHAT_ID,
            "caption": caption,
            "reply_markup": build_bale_keyboard(
                original_text or caption
            )
        }

        with open(file_path, "rb") as media:
            bale_call(
                method,
                data=data,
                files={field: media}
            )

    else:
        with open(file_path, "rb") as media:
            bale_call(
                method,
                data={"chat_id": BALE_CHAT_ID},
                files={field: media}
            )

        send_bale_text(caption)

    return True


# ============================================================
# SEND TEXT TO RUBIKA
# ============================================================

def send_rubika_text(text):
    parts = split_text(text, RUBIKA_TEXT_LIMIT)

    if not parts:
        return True

    for part in parts:
        rubika_call(
            "sendMessage",
            {
                "chat_id": RUBIKA_CHAT_ID,
                "text": part
            }
        )

    return True


# ============================================================
# SEND MEDIA TO RUBIKA
# ============================================================

def send_rubika_media(method, field, file_path, caption=""):
    caption = caption or ""

    if len(caption) > RUBIKA_CAPTION_LIMIT:
        caption_for_media = caption[:RUBIKA_CAPTION_LIMIT]
        remainder = caption[RUBIKA_CAPTION_LIMIT:].strip()
    else:
        caption_for_media = caption
        remainder = ""

    payload = {
        "chat_id": RUBIKA_CHAT_ID,
        "caption": caption_for_media
    }

    with open(file_path, "rb") as media:
        rubika_call(
            method,
            payload=payload,
            files={field: media}
        )

    if remainder:
        send_rubika_text(remainder)

    return True


# ============================================================
# COMMON MEDIA ROUTER
# ============================================================

def media_details(message):
    if message.get("photo"):
        item = message["photo"][-1]
        return (
            "photo", "sendPhoto", "photo",
            item.get("file_id"), ".jpg"
        )

    if message.get("video"):
        item = message["video"]
        return (
            "video", "sendVideo", "video",
            item.get("file_id"), ".mp4"
        )

    if message.get("audio"):
        item = message["audio"]
        name = item.get("file_name", "audio")
        suffix = (
            "." + name.rsplit(".", 1)[-1]
            if "." in name else ".mp3"
        )
        return (
            "audio", "sendAudio", "audio",
            item.get("file_id"), suffix
        )

    if message.get("voice"):
        item = message["voice"]
        return (
            "voice", "sendVoice", "voice",
            item.get("file_id"), ".ogg"
        )

    if message.get("document"):
        item = message["document"]
        name = item.get("file_name", "file")
        suffix = (
            "." + name.rsplit(".", 1)[-1]
            if "." in name else ""
        )
        return (
            "document", "sendDocument", "document",
            item.get("file_id"), suffix
        )

    if message.get("animation"):
        item = message["animation"]
        return (
            "animation", "sendAnimation", "animation",
            item.get("file_id"), ".mp4"
        )

    return None


def send_to_bale(message):
    text = get_text(message)
    details = media_details(message)

    if not details:
        if message.get("text"):
            return send_bale_text(message["text"])

        log.warning("Unsupported Telegram post type for Bale.")
        return True

    kind, method, field, file_id, suffix = details

    if not file_id:
        raise RuntimeError(f"Missing Telegram file_id for {kind}")

    path = download_telegram_file(file_id, suffix)

    try:
        return send_bale_media(
            method, field, path, text, text
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def send_to_rubika(message):
    text = get_text(message)
    details = media_details(message)

    if not details:
        if message.get("text"):
            return send_rubika_text(message["text"])

        log.warning("Unsupported Telegram post type for Rubika.")
        return True

    kind, method, field, file_id, suffix = details

    if not file_id:
        raise RuntimeError(f"Missing Telegram file_id for {kind}")

    path = download_telegram_file(file_id, suffix)

    try:
        return send_rubika_media(
            method, field, path, text
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ============================================================
# DELIVERY ROUTER
# ============================================================

def mirror_post(message, update_id, state, stats):
    if not is_target_channel(message):
        chat = message.get("chat") or {}
        log.info(
            "Skipped non-target channel: %s",
            chat.get("username") or chat.get("title")
        )
        stats["skipped"] += 1
        return True

    stats["received"] += 1
    key = str(update_id)

    entry = state.setdefault(
        key, {"bale": False, "rubika": False}
    )

    if not entry.get("bale"):
        try:
            send_to_bale(message)
            entry["bale"] = True
            stats["bale_ok"] += 1

            log.info(
                "BALE SUCCESS | update=%s",
                update_id
            )

        except Exception as exc:
            stats["bale_failed"] += 1

            log.error(
                "BALE FAILED | update=%s | %s: %s",
                update_id,
                type(exc).__name__,
                str(exc)[:1500]
            )

        finally:
            save_delivery_state(state)

    if not entry.get("rubika"):
        try:
            send_to_rubika(message)
            entry["rubika"] = True
            stats["rubika_ok"] += 1

            log.info(
                "RUBIKA SUCCESS | update=%s",
                update_id
            )

        except Exception as exc:
            stats["rubika_failed"] += 1

            log.error(
                "RUBIKA FAILED | update=%s | %s: %s",
                update_id,
                type(exc).__name__,
                str(exc)[:1500]
            )

        finally:
            save_delivery_state(state)

    return bool(entry.get("bale") and entry.get("rubika"))


# ============================================================
# FINAL REPORT
# ============================================================

def log_report(stats):
    log.info("=" * 50)
    log.info("JAHANTAB DELIVERY REPORT")
    log.info("Telegram posts processed: %d", stats["received"])
    log.info(
        "BALE | successful=%d | failed=%d",
        stats["bale_ok"], stats["bale_failed"]
    )
    log.info(
        "RUBIKA | successful=%d | failed=%d",
        stats["rubika_ok"], stats["rubika_failed"]
    )
    log.info("Completed for both: %d", stats["completed"])
    log.info("Skipped updates: %d", stats["skipped"])
    log.info("=" * 50)


# ============================================================
# PROCESS UPDATES
# ============================================================

def process_updates():
    stats = {
        "received": 0,
        "bale_ok": 0,
        "bale_failed": 0,
        "rubika_ok": 0,
        "rubika_failed": 0,
        "completed": 0,
        "skipped": 0
    }

    try:
        offset = load_offset()
        updates = get_updates(offset)

        if not updates:
            log.info("No new Telegram posts.")
            return

        log.info(
            "Received %d Telegram update(s).",
            len(updates)
        )

        state = load_delivery_state()

        for update in updates:
            update_id = update.get("update_id")

            if update_id is None:
                continue

            message = update.get("channel_post")

            if not message:
                save_offset(update_id + 1)
                stats["skipped"] += 1
                continue

            success = mirror_post(
                message, update_id, state, stats
            )

            if not success:
                # Keep the offset unchanged for this update.
                # Successful destinations are remembered in delivery_state.json.
                raise RuntimeError(
                    f"Delivery incomplete for Telegram update "
                    f"{update_id}; failed destinations will be retried."
                )

            save_offset(update_id + 1)
            stats["completed"] += 1

            log.info(
                "Update %s completed for both destinations.",
                update_id
            )

    finally:
        log_report(stats)


# ============================================================
# MAIN
# ============================================================

def main():
    log.info("=" * 50)
    log.info("JAHANTAB TELEGRAM -> BALE + RUBIKA")
    log.info("=" * 50)

    validate_config()

    log.info("Source: @%s", TELEGRAM_CHANNEL_USERNAME)
    log.info("Bale destination configured.")
    log.info("Rubika destination configured.")

    process_updates()
    log.info("Run completed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log.error(
            "RUN FAILED | %s: %s",
            type(exc).__name__,
            str(exc)[:1500]
        )
        raise
