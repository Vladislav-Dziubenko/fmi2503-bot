import os
import time
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler
from flask import Flask
from threading import Thread

# --- WEB SERVER ДЛЯ RENDER ---
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web, daemon=True)
    t.start()
# -------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "СЮДА_ВСТАВЬ_ТОКЕН")
COOLDOWN_SECONDS = 30
_last_request = {}
URL = "https://fmi.usm.md/orar/"

# Настройки для обхода блокировок
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
# Отключаем использование системного прокси хостинга
NO_PROXIES = {"http": None, "https": None}

def _parse_links(soup):
    items = []
    seen = set()
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        text = link.get_text(strip=True) or ""
        if not href or not text or len(text) < 3:
            continue
        if "orar" in href.lower() or ".pdf" in href or "docs.google" in href or "spreadsheets" in href:
            if href not in seen:
                seen.add(href)
                items.append((text[:80], href))
    return items


def get_short_schedule():
    try:
        # Добавлены headers и proxies для фикса 403 Forbidden
        resp = requests.get(URL, headers=HEADERS, proxies=NO_PROXIES, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return f"Ошибка при загрузке: {e}"
    soup = BeautifulSoup(resp.text, "html.parser")
    items = _parse_links(soup)
    if not items:
        return "Расписание не найдено. Сайт: https://fmi.usm.md/orar/"
    lines = ["Расписание FMI USM (с сайта)\n"]
    for text, href in items[:25]:
        lines.append(f"• {text}\n  {href}")
    lines.append("\nСайт: https://fmi.usm.md/orar/")
    return "\n".join(lines)


def fetch_schedule():
    try:
        # Добавлены headers и proxies для фикса 403 Forbidden
        resp = requests.get(URL, headers=HEADERS, proxies=NO_PROXIES, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return f"Ошибка при загрузке сайта: {e}"
    soup = BeautifulSoup(resp.text, "html.parser")
    items = _parse_links(soup)
    if not items:
        return "Расписание не найдено. https://fmi.usm.md/orar/"
    result = ["Расписание FMI USM (полное)\n"]
    for text, href in items:
        result.append(f"• {text}\n  {href}")
    result.append("\nСайт: https://fmi.usm.md/orar/")
    return "\n".join(result)


def _check_cooldown(user_id, chat_id):
    key = (user_id, chat_id)
    now = time.time()
    last = _last_request.get(key, 0)
    if now - last < COOLDOWN_SECONDS:
        left = int(COOLDOWN_SECONDS - (now - last))
        return f"Подожди {left} сек перед следующим запросом."
    _last_request[key] = now
    return None


async def start(update, context):
    await update.message.reply_text(
        "Привет! Я бот с расписанием FMI USM.\n\n"
        "Команды:\n"
        "/raspisanie — основное расписание\n"
        "/orar — полное расписание с сайта"
    )


async def raspisanie(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    msg = _check_cooldown(user_id, chat_id)
    if msg:
        await update.message.reply_text(msg)
        return
    text = get_short_schedule()
    await update.message.reply_text(text)


async def orar(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    msg = _check_cooldown(user_id, chat_id)
    if msg:
        await update.message.reply_text(msg)
        return
    await update.message.reply_text("Загружаю с сайта...")
    text = fetch_schedule()
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (обрезано)"
    await update.message.reply_text(text)


def main():
    keep_alive()

    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("raspisanie", raspisanie))
    bot_app.add_handler(CommandHandler("orar", orar))

    logger.info("Бот запущен...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
