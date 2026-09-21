import os
import yaml
import requests
from bale import Bot, Message


BOT_TOKEN = os.getenv("BALE_BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BALE_BOT_TOKEN is not set")


def load_news():
    try:
        with open("news.yml", "r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
            return data.get("news", [])
    except FileNotFoundError:
        return []


bot = Bot(token=BOT_TOKEN)


@bot.event
async def on_ready():
    print("Bot is ready!")


@bot.event
async def on_message(message: Message):
    if not message.content:
        return

    if message.content == "/start":
        await message.reply(
            "سلام 👋\n"
            "به ربات اخبار خوش آمدید.\n\n"
            "برای دریافت اخبار، دستور /news را ارسال کنید."
        )

    elif message.content == "/news":
        news = load_news()

        if not news:
            await message.reply("در حال حاضر خبری وجود ندارد.")
            return

        for item in news:
            title = item.get("title", "بدون عنوان")
            text = item.get("text", "")
            link = item.get("link", "")

            response = f"📰 {title}\n\n{text}"

            if link:
                response += f"\n\n🔗 {link}"

            await message.reply(response)


bot.run()