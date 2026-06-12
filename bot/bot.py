"""Telegram-бот хоккейного словаря.

Запуск: BOT_TOKEN=<токен> python bot.py
Или положи токен в bot/.env (BOT_TOKEN=...).
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from search import format_card, load_terms, search, suggest

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("hockey-bot")

TERMS = load_terms()
MISSING_LOG = Path(__file__).resolve().parent / "missing_queries.log"


def log_missing(query: str) -> None:
    """Ненайденный запрос — сырьё для наполнения базы."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    try:
        with MISSING_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{stamp}\t{query.strip()}\n")
    except OSError:
        log.warning("Не удалось записать missing_queries.log")

HELP_TEXT = (
    "🏒 <b>Хоккейный словарь</b>\n\n"
    "Пришли термин — отвечу карточкой с объяснением.\n"
    "Понимаю английский, русский и аббревиатуры:\n"
    "  • <code>xG</code>\n"
    "  • <code>корси</code>\n"
    "  • <code>forecheck</code>\n\n"
    f"В базе сейчас {len(TERMS)} терминов.\n"
    "Полный словарь: altitushkin.github.io/hockey-platform"
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text
    results = search(query, TERMS)
    if results:
        for term in results[:2]:
            await update.message.reply_text(format_card(term), parse_mode=ParseMode.HTML)
        return

    log_missing(query)
    hints = suggest(query, TERMS)
    if hints:
        msg = "Не нашёл точного совпадения. Возможно, ты имел в виду:\n" + "\n".join(
            f"  • {h}" for h in hints
        )
    else:
        msg = (
            "Такого термина в базе пока нет. 🤷\n"
            "База пополняется — попробуй другой запрос или напиши /help."
        )
    await update.message.reply_text(msg)


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    _load_dotenv()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Нет токена: задай переменную окружения BOT_TOKEN или создай bot/.env")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_query))

    log.info("Бот запущен, терминов в базе: %d", len(TERMS))
    app.run_polling()


if __name__ == "__main__":
    main()
