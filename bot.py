import logging
import os
import random
import time
from threading import Thread

from flask import Flask
from telegram import Message, Update
from telegram.ext import Application, CommandHandler
from telegram.error import TelegramError

from schedule import cached_data, get_smart_report, get_status_text, update_cache_loop

flask_app = Flask("")

@flask_app.route("/")
def home():
    return "Bot is alive!"

def run_web() -> None:
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

def keep_alive() -> None:
    Thread(target=run_web, daemon=True).start()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
COOLDOWN_MIN = 30
COOLDOWN_MAX = 45

_user_cooldowns: dict[int, dict] = {}
_bot_messages: dict[int, list[int]] = {}
MAX_TRACKED_MESSAGES = 100

def _track_message(chat_id: int, message_id: int) -> None:
    ids = _bot_messages.setdefault(chat_id, [])
    ids.append(message_id)
    if len(ids) > MAX_TRACKED_MESSAGES:
        _bot_messages[chat_id] = ids[-MAX_TRACKED_MESSAGES:]

async def _reply_text(update: Update, text: str, **kwargs) -> Message:
    msg = await update.message.reply_text(text, **kwargs)
    _track_message(update.effective_chat.id, msg.message_id)
    return msg

async def _reply_html(update: Update, text: str, **kwargs) -> Message:
    msg = await update.message.reply_html(text, **kwargs)
    _track_message(update.effective_chat.id, msg.message_id)
    return msg

def check_cooldown(user_id: int) -> str | None:
    now = time.time()
    data = _user_cooldowns.get(user_id)
    if data:
        elapsed = now - data["last"]
        if elapsed < data["required"]:
            left = int(data["required"] - elapsed) + 1
            return f"⏳ Подождите {left} сек перед следующей командой."
    _user_cooldowns[user_id] = {
        "last": now,
        "required": random.randint(COOLDOWN_MIN, COOLDOWN_MAX),
    }
    return None

async def _reply_cooldown(update: Update) -> bool:
    user_id = update.effective_user.id
    msg = check_cooldown(user_id)
    if msg:
        sent = await update.message.reply_text(msg)
        _track_message(update.effective_chat.id, sent.message_id)
        return True
    return False

async def start(update: Update, context) -> None:
    await _reply_text(
        update,
        "👋 Привет! Я бот расписания FMI USM.\n\n"
        "Команды:\n"
        "/raspisanie — краткий список ссылок\n"
        "/orar — полный список с сайта\n"
        "/smart — умный анализ ключевых дат (локально)\n"
        "/ai — то же, что /smart\n"
        "/status — статус обновления данных\n"
        "/clear — удалить сообщения бота в этом чате\n\n"
        "Данные обновляются автоматически раз в 30 минут.\n"
        "Между командами — пауза 30–45 сек.",
    )

async def raspisanie(update: Update, context) -> None:
    if await _reply_cooldown(update):
        return
    await _reply_html(
        update,
        f"{cached_data['short']}\n\n🕒 Обновлено: {cached_data['last_upd']}",
    )

async def orar(update: Update, context) -> None:
    if await _reply_cooldown(update):
        return
    await _reply_html(
        update,
        f"{cached_data['full']}\n\n🕒 Обновлено: {cached_data['last_upd']}",
    )

async def smart(update: Update, context) -> None:
    if await _reply_cooldown(update):
        return
    await _reply_html(update, get_smart_report())

async def status(update: Update, context) -> None:
    if await _reply_cooldown(update):
        return
    await _reply_html(update, get_status_text())

async def clear_chat(update: Update, context) -> None:
    chat_id = update.effective_chat.id
    ids = list(_bot_messages.get(chat_id, []))
    _bot_messages[chat_id] = []
    deleted = 0
    skipped = 0
    for message_id in ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            deleted += 1
        except TelegramError:
            skipped += 1
    note = ""
    if skipped:
        note = f"\n\n⚠️ {skipped} сообщ. не удалены (старше 48 ч или уже удалены)."
    await _reply_text(update, f"🧹 Удалено сообщений бота: {deleted}.{note}")

def main() -> None:
    if not TOKEN:
        logger.error("BOT_TOKEN не задан в переменных окружения!")
        raise SystemExit(1)
    keep_alive()
    Thread(target=update_cache_loop, daemon=True).start()
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("raspisanie", raspisanie))
    bot_app.add_handler(CommandHandler("orar", orar))
    bot_app.add_handler(CommandHandler("smart", smart))
    bot_app.add_handler(CommandHandler("ai", smart))
    bot_app.add_handler(CommandHandler("status", status))
    bot_app.add_handler(CommandHandler("clear", clear_chat))
    logger.info("Бот запущен...")
    bot_app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
