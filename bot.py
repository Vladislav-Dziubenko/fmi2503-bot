import os
import time
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler
from flask import Flask
from threading import Thread

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get("BOT_TOKEN", "СЮДА_ВСТАВЬ_ТОКЕН")
URL = "https://fmi.usm.md"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
NO_PROXIES = {"http": None, "https": None}

# Кэш для хранения расписания (чтобы не перегружать сайт и хостинг)
cached_data = {
    "short": "⏳ Загружаю данные, подождите немного...",
    "full": "⏳ Загружаю данные, подождите немного...",
    "last_upd": 0
}

# --- WEB SERVER ДЛЯ RENDER ---
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

# --- ЛОГИКА ПАРСИНГА ---
def _parse_links():
    try:
        resp = requests.get(URL, headers=HEADERS, proxies=NO_PROXIES, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []
        seen = set()
        for link in soup.find_all("a", href=True):
            href = link.get("href", "").strip()
            text = link.get_text(strip=True) or ""
            if not href or len(text) < 3: continue
            if any(x in href.lower() for x in ["orar", ".pdf", "docs.google", "spreadsheets"]):
                if href not in seen:
                    seen.add(href)
                    items.append((text[:80], href))
        return items
    except Exception as e:
        logging.error(f"Ошибка парсинга: {e}")
        return None

def update_cache_loop():
    """Фоновая задача: обновляет данные раз в 30 минут"""
    while True:
        items = _parse_links()
        if items:
            # Формируем краткое
            short_content = "\n".join([f"• {t}\n  {h}" for t, h in items[:15]])
            cached_data["short"] = f"<b>📍 Краткое расписание</b>\n\n<blockquote expandable>{short_content}</blockquote>"
            
            # Формируем полное
            full_content = "\n".join([f"• {t}\n  {h}" for t, h in items])
            if len(full_content) > 3800: full_content = full_content[:3800] + "\n...(обрезано)"
            cached_data["full"] = f"<b>📚 Полный список ссылок</b>\n\n<blockquote expandable>{full_content}</blockquote>"
            
            cached_data["last_upd"] = time.strftime("%H:%M:%S")
            logging.info(f"Кэш обновлен в {cached_data['last_upd']}")
        
        time.sleep(1800) # 30 минут

# --- ОБРАБОТЧИКИ ТЕЛЕГРАМ ---
async def start(update, context):
    await update.message.reply_text(
        "👋 Привет! Я бот расписания FMI USM.\n\n"
        "Команды:\n"
        "/raspisanie — список последних обновлений\n"
        "/orar — все ссылки с сайта\n\n"
        "Данные обновляются автоматически раз в 30 минут."
    )

async def raspisanie(update, context):
    await update.message.reply_html(f"{cached_data['short']}\n\n🕒 Обновлено: {cached_data['last_upd']}")

async def orar(update, context):
    await update.message.reply_html(f"{cached_data['full']}\n\n🕒 Обновлено: {cached_data['last_upd']}")

# --- ЗАПУСК ---
logging.basicConfig(level=logging.INFO)

def main():
    # 1. Запуск веб-сервера (для Render)
    Thread(target=run_web, daemon=True).start()
    
    # 2. Запуск фонового обновления данных
    Thread(target=update_cache_loop, daemon=True).start()

    # 3. Запуск бота
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("raspisanie", raspisanie))
    bot_app.add_handler(CommandHandler("orar", orar))

    logging.info("Бот запущен...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()

