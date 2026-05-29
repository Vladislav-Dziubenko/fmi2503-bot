import logging
import os
import random
import time
from threading import Thread

from flask import Flask, request as flask_request
from telegram import Message, Update
from telegram.ext import Application, CommandHandler
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

from schedule import (
    get_orar_text,
    get_raspisanie_text,
    get_smart_report,
    get_status_text,
    refresh_on_request,
    update_cache_loop,
)

flask_app = Flask("")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
# Динамически получаем адрес вашего пространства на Hugging Face
SPACE_ID = os.environ.get("SPACE_ID") 
WEBHOOK_URL = f"https://{SPACE_ID.replace('/', '-')}.hf.space/webhook" if SPACE_ID else None

COOLDOWN_MIN, COOLDOWN_MAX = 30, 45
_user_cooldowns = {}
_bot_messages = {}
MAX_TRACKED_MESSAGES = 100

# Создаем глобальный объект приложения бота
request_config = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
app = Application.builder().token(TOKEN).request(request_config).build()

@flask_app.route("/")
def home():
    return "Bot is alive!"

# Вебхук-обработчик для приема сообщений от Telegram
@flask_app.route("/webhook", methods=["POST"])
async def webhook():
    if flask_request.method == "POST":
        try:
            json_string = flask_request.get_json(force=True)
            update = Update.de_json(json_string, app.bot)
            await app.process_update(update)
        except Exception as e:
            logger.error(f"Ошибка обработки вебхука: {e}")
    return "OK"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

def _track_message(chat_id, message_id):
    ids = _bot_messages.setdefault(chat_id, [])
    ids.append(message_id)
    if len(ids) > MAX_TRACKED_MESSAGES:
        _bot_messages[chat_id] = ids[-MAX_TRACKED_MESSAGES:]

async def _reply_text(update, text, **kwargs):
    msg = await update.message.reply_text(text, **kwargs)
    _track_message(update.effective_chat.id, msg.message_id)
    return msg

async def _reply_html(update, text, **kwargs):
    msg = await update.message.reply_html(text, **kwargs)
    _track_message(update.effective_chat.id, msg.message_id)
    return msg

def check_cooldown(user_id):
    now = time.time()
    data = _user_cooldowns.get(user_id)
    if data and now - data["last"] < data["required"]:
        return f"⏳ Подождите {int(data['required'] - (now - data['last'])) + 1} сек."
    _user_cooldowns[user_id] = {"last": now, "required": random.randint(COOLDOWN_MIN, COOLDOWN_MAX)}
    return None

async def _reply_cooldown(update):
    msg = check_cooldown(update.effective_user.id)
    if msg:
        sent = await update.message.reply_text(msg)
        _track_message(update.effective_chat.id, sent.message_id)
        return True
    return False

async def start(update, context):
    await _reply_text(update,
        "👋 Бот расписания FMI USM\n\n"
        "/raspisanie — краткий список\n"
        "/orar — полный список\n"
        "/smart или /ai — умный анализ\n"
        "/status — статус\n"
        "/clear — удалить сообщения бота\n\n"
        "При вызове команды ищет обновления на сайте.\n"
        "Если сайт не отвечает — показывает сохранённое.\n"
        "Пауза между командами: 30–45 сек.")

async def raspisanie(update, context):
    if await _reply_cooldown(update): return
    body, footer = get_raspisanie_text()
    await _reply_html(update, f"{body}\n\n{footer}")

async def orar(update, context):
    if await _reply_cooldown(update): return
    body, footer = get_orar_text()
    await _reply_html(update, f"{body}\n\n{footer}")

async def smart(update, context):
    if await _reply_cooldown(update): return
    footer = refresh_on_request()
    await _reply_html(update, f"{get_smart_report()}\n\n{footer}")

async def status(update, context):
    if await _reply_cooldown(update): return
    await _reply_html(update, get_status_text())

async def clear_chat(update, context):
    chat_id = update.effective_chat.id
    ids = list(_bot_messages.get(chat_id, []))
    _bot_messages[chat_id] = []
    deleted = skipped = 0
    for mid in ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
            deleted += 1
        except TelegramError:
            skipped += 1
    note = f"\n\n⚠️ {skipped} не удалены (лимит Telegram 48ч)." if skipped else ""
    await _reply_text(update, f"🧹 Удалено: {deleted}.{note}")

def main():
    if not TOKEN:
        logger.error("BOT_TOKEN не задан!")
        raise SystemExit(1)
    
    Thread(target=update_cache_loop, daemon=True).start()
    
    for cmd, fn in [("start", start), ("raspisanie", raspisanie), ("orar", orar),
                    ("smart", smart), ("ai", smart), ("status", status), ("clear", clear_chat)]:
        app.add_handler(CommandHandler(cmd, fn))
        
    # Инициализируем бота внутри Flask-приложения
    with flask_app.app_context():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Настраиваем вебхук в Telegram
        if WEBHOOK_URL:
            logger.info(f"Установка вебхука на адрес: {WEBHOOK_URL}")
            try:
                loop.run_until_complete(app.bot.set_webhook(url=WEBHOOK_URL, allowed_updates=Update.ALL_TYPES))
            except Exception as e:
                logger.error(f"Не удалось установить вебхук: {e}")
        
        loop.run_until_complete(app.initialize())
        if app.updater:
            loop.run_until_complete(app.updater.initialize())
        loop.run_until_complete(app.start())

    logger.info("Бот запущен через вебхуки...")
    run_web()

if __name__ == "__main__":
    main()
