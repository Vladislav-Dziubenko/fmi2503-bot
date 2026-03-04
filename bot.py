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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
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

def format_as_expandable(title, items):
    """Форматирует список в сворачиваемую цитату HTML"""
    # Заголовок жирным, список внутри сворачиваемой цитаты
    content = "\n".join([f"• {text}\n  {href}" for text, href in items])
    return f"<b>{title}</b>\n\n<blockquote expandable>{content}</blockquote>\n\n<a href='{URL}'>Сайт факультета</a>"

def get_short_schedule():
    try:
        resp = requests.get(URL, headers=HEADERS, proxies=NO_PROXIES, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return f"Ошибка при загрузке: {e}"
    soup = BeautifulSoup(resp.text, "html.parser")
    items = _parse_links(soup)
    if not items:
        return "Расписание не найдено."
    return format_as_expandable("Расписание FMI USM (кратко)", items[:15])

def fetch_schedule():
    try:
        resp = requests.get(URL, headers=HEADERS, proxies=NO_PROXIES, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return f"Ошибка при загрузке сайта: {e}"
    soup = BeautifulSoup(resp.text, "html.parser")
    items = _parse_links(soup)
    if not items:
        return "Расписание не найдено."
    return format_as_expandable("Расписание FMI USM (полное)", items)

def _check_cooldown(user_id, chat_id):
    key = (user_id, chat_id)
    now = time.time()
    last = _last_request.get(key, 0)
    if now - last < COOLDOWN_SECONDS:
        left = int(COOLDOWN_SECONDS - (now - last))
        return f"Подожди {left} сек."
    _last_request[key] = now
    return None

async def start(update, context):
    await update.message.reply_text(
        "Привет! Я бот с расписанием FMI USM.\n\n"
        "Команды:\n"
        "/raspisanie — краткий список\n"
        "/orar — полный список (свернут)"
    )

async def raspisanie(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    msg = _check_cooldown(user_id, chat_id)
    if msg:
        await update.message.reply_text(msg)
        return
    text = get_short_schedule()
    # parse_mode='HTML' критически важен!
    await update.message.reply_html(text)

async def orar(update, context):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    msg = _check_cooldown(user_id, chat_id)
    if msg:
        await update.message.reply_text(msg)
        return
    status_msg = await update.message.reply_text("Загружаю с сайта...")
    text = fetch_schedule()
    if len(text) > 4000:
        text = text[:3800] + "</blockquote>\n\n(Обрезано из-за лимита)"
    
    await status_msg.delete() # Удаляем "Загружаю..."
    await update.message.reply_html(text)

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

