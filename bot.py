import logging
import os
import random
import time
from threading import Thread
 
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler
from telegram.error import TelegramError
 
flask_app = Flask("")
 
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
 
TOKEN = os.environ.get("BOT_TOKEN")
# Твой URL на Hugging Face — замени USERNAME и SPACENAME
# Пример: https://vladislav228912-my-telegram-bot.hf.space
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
 
COOLDOWN_MIN, COOLDOWN_MAX = 30, 45
_user_cooldowns = {}
_bot_messages = {}
MAX_TRACKED_MESSAGES = 100
 
# Глобальное приложение
_app: Application = None
 
@flask_app.route("/")
def home():
    return "Bot is alive and running!"
 
@flask_app.route(f"/webhook", methods=["POST"])
def webhook():
    """Telegram шлёт сюда все updates"""
    global _app
    if _app is None:
        return "not ready", 503
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, _app.bot)
    _app.update_queue.put_nowait(update)
    return "ok", 200
 
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
    from schedule import get_raspisanie_text
    body, footer = get_raspisanie_text()
    await _reply_html(update, f"{body}\n\n{footer}")
 
async def orar(update, context):
    if await _reply_cooldown(update): return
    from schedule import get_orar_text
    body, footer = get_orar_text()
    await _reply_html(update, f"{body}\n\n{footer}")
 
async def smart(update, context):
    if await _reply_cooldown(update): return
    from schedule import refresh_on_request, get_smart_report
    footer = refresh_on_request()
    await _reply_html(update, f"{get_smart_report()}\n\n{footer}")
 
async def status(update, context):
    if await _reply_cooldown(update): return
    from schedule import get_status_text
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
 
async def setup_webhook(app: Application):
    """Регистрируем webhook в Telegram при старте"""
    url = f"{WEBHOOK_URL}/webhook"
    await app.bot.set_webhook(url=url)
    logger.info("Webhook установлен: %s", url)
 
def main():
    global _app
 
    if not TOKEN:
        logger.error("BOT_TOKEN не задан!")
        raise SystemExit(1)
 
    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL не задан! Пример: https://vladislav228912-my-telegram-bot.hf.space")
        raise SystemExit(1)
 
    from schedule import update_cache_loop
    Thread(target=update_cache_loop, daemon=True).start()
 
    # Строим приложение
    app = Application.builder().token(TOKEN).updater(None).build()
    _app = app
 
    for cmd, fn in [("start", start), ("raspisanie", raspisanie), ("orar", orar),
                    ("smart", smart), ("ai", smart), ("status", status), ("clear", clear_chat)]:
        app.add_handler(CommandHandler(cmd, fn))
 
    # Запускаем обработку updates в фоне
    import asyncio
 
    async def run_app():
        await app.initialize()
        await setup_webhook(app)
        await app.start()
        logger.info("Бот запущен в режиме Webhook.")
 
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_app())
    Thread(target=loop.run_forever, daemon=True).start()
 
    # Flask слушает входящие запросы от Telegram
    port = int(os.environ.get("PORT", 8080))
    logger.info("Flask запущен на порту %d", port)
    flask_app.run(host="0.0.0.0", port=port)
 
if __name__ == "__main__":
    main()
