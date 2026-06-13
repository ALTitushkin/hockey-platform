"""Telegram-бот хоккейного словаря. v0.6

Запуск: BOT_TOKEN=<токен> python bot.py
Или положи токен в bot/.env (BOT_TOKEN=...).
Прод: VPS, systemd-юнит hockey-bot, автодеплой из main.

v0.5: добавлен inline-режим (@bot термин в любом чате)
v0.6: inline отдаёт и главы истории при miss по словарю;
      username бота больше не захардкожен (берётся из bot.username).
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from search import (
    find_history_chapter,
    format_card,
    load_history,
    load_terms,
    search,
    suggest,
)

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("hockey-bot")

TERMS = load_terms()
HISTORY = load_history()
MISSING_LOG = Path(__file__).resolve().parent / "missing_queries.log"
QUERIES_LOG = Path(__file__).resolve().parent / "queries.log"

# Username бота. Дефолт — реальный @hockey_platform_bot; на старте перезаписывается
# фактическим значением из Telegram (см. _post_init), можно задать через env BOT_USERNAME.
BOT_USERNAME = os.environ.get("BOT_USERNAME", "hockey_platform_bot")

# ─── Логирование ─────────────────────────────────────────────────────────────

def _append(path: Path, line: str) -> None:
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        log.warning("Не удалось записать %s", path.name)


def log_query(query: str, hit: bool) -> None:
    """Все запросы (без user_id — только текст). Анализ раз в спринт, затем файл чистим."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    _append(QUERIES_LOG, f"{stamp}\t{'hit' if hit else 'miss'}\t{query.strip()[:200]}")
    if not hit:
        _append(MISSING_LOG, f"{stamp}\t{query.strip()[:200]}")

# ─── Форматирование для inline ────────────────────────────────────────────────

def format_inline_text(term: dict) -> str:
    """Текст карточки для inline-ответа (HTML)."""
    abbrs = ", ".join(term.get("abbr") or [])
    lines = [f"🏒 <b>{term['en']}</b> — {term['ru']}"]
    if abbrs:
        lines.append(f"<code>{abbrs}</code>")
    lines.append("")
    lines.append(term["definition"])
    if term.get("ru_slang"):
        lines.append(f"\n<i>Сленг: {term['ru_slang']}</i>")
    lines.append(f"\n🔗 <a href='https://altitushkin.github.io/hockey-platform/'>Весь словарь</a>")
    return "\n".join(lines)


def format_inline_history(chapter: dict) -> str:
    """Текст inline-карточки для главы истории (HTML)."""
    return (
        f"📚 <b>{chapter['title']}</b>\n\n"
        f"{chapter['summary']}\n\n"
        f"🔗 <a href='{chapter['url']}'>Читать статью</a>"
    )

# ─── Тексты ───────────────────────────────────────────────────────────────────

def help_text() -> str:
    """Текст /start. Username берётся из BOT_USERNAME (см. _post_init)."""
    return (
        "🏒 <b>Хоккейный словарь</b>\n"
        "<i>от канала «Хоккейный Овертайм»</i>\n\n"
        "Встретил незнакомый термин в статистике или разборе? "
        "Пришли его мне — объясню по-человечески.\n\n"
        "Понимаю любой формат:\n"
        "  📊 <code>xG</code>, <code>CF%</code>, <code>PDO</code>\n"
        "  🧩 <code>форчек</code>, <code>слот</code>, <code>цикл</code>\n"
        "  🇬🇧 <code>breakaway</code>, <code>one-timer</code>\n\n"
        f"В базе {len(TERMS)} терминов, пополняется от ваших запросов: "
        "не нашёл — всё равно отправь, добавим.\n\n"
        f"💡 <b>Inline:</b> набери <code>@{BOT_USERNAME} форчек</code> в любом чате — "
        "и поделись карточкой прямо там."
    )


def help_search() -> str:
    """Текст /help."""
    return (
        "🔍 <b>Как искать</b>\n\n"
        "Просто пришли термин сообщением — в любом виде:\n"
        "  • по-английски: <code>forecheck</code>, <code>one-timer</code>\n"
        "  • по-русски: <code>форчек</code>, <code>пятак</code>, <code>сухарь</code>\n"
        "  • аббревиатурой: <code>xG</code>, <code>CF%</code>, <code>SHO</code>\n"
        "  • даже с опечаткой: <code>корс</code> найдёт Corsi\n\n"
        "Если найдётся несколько похожих — пришлю до двух карточек.\n"
        "Не нашлось? Запрос сохранится, и термин появится в базе позже.\n\n"
        f"💡 <b>Inline-режим</b> — набери <code>@{BOT_USERNAME}</code> и термин "
        "прямо в строке чата, чтобы поделиться объяснением с собеседником.\n\n"
        "Категории: 📊 статистика · 🧩 тактика · 📏 правила · ⛸ позиции"
    )

START_KEYBOARD = InlineKeyboardMarkup(
    [[InlineKeyboardButton("📖 Открыть весь словарь", url="https://altitushkin.github.io/hockey-platform/")]]
)

# ─── Handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        help_text(), parse_mode=ParseMode.HTML, reply_markup=START_KEYBOARD
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(help_search(), parse_mode=ParseMode.HTML)


async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Игнорируем эхо собственных inline-карточек и сообщения, отправленные «через бота».
    if update.message.via_bot is not None:
        return
    query = update.message.text
    results = search(query, TERMS)

    if results:
        log_query(query, hit=True)
        for term in results[:2]:
            await update.message.reply_text(format_card(term), parse_mode=ParseMode.HTML)
        return

    # Словарь не нашёл — проверяем исторический раздел
    chapter = find_history_chapter(query, HISTORY)
    if chapter:
        log_query(query, hit=True)  # глава истории — это попадание, не miss
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"📖 {chapter['title']}", url=chapter["url"])]]
        )
        await update.message.reply_text(
            f"Это из истории хоккея, а не термин аналитики.\n\n"
            f"📚 <b>{chapter['title']}</b>\n"
            f"<i>{chapter['summary']}</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        return

    # Ничего не найдено — записываем miss
    log_query(query, hit=False)
    hints = suggest(query, TERMS)
    if hints:
        msg = "Не нашёл точного совпадения. Возможно, ты имел в виду:\n" + "\n".join(
            f"  • {h}" for h in hints
        )
    else:
        msg = (
            "Такого термина в базе пока нет — но я его записал, "
            "разберём и добавим. 📝\n"
            "А пока попробуй другой запрос или /help."
        )
    await update.message.reply_text(msg)


async def handle_inline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline-режим: @bot термин → карточка прямо в чат."""
    query = (update.inline_query.query or "").strip()

    if len(query) < 2:
        # Показываем подсказку пока запрос пустой/короткий
        await update.inline_query.answer(
            [],
            switch_pm_text="Введи термин (мин. 2 символа)",
            switch_pm_parameter="inline_help",
            cache_time=10,
        )
        return

    results_list = search(query, TERMS, limit=5)

    if not results_list:
        # Словарь не нашёл — пробуем отдать главу истории
        chapter = find_history_chapter(query, HISTORY)
        if chapter:
            description = chapter["summary"][:100] + ("…" if len(chapter["summary"]) > 100 else "")
            await update.inline_query.answer(
                [
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=f"📚 {chapter['title']}",
                        description=description,
                        input_message_content=InputTextMessageContent(
                            message_text=format_inline_history(chapter),
                            parse_mode=ParseMode.HTML,
                        ),
                    )
                ],
                cache_time=300,
            )
            return

        await update.inline_query.answer(
            [],
            switch_pm_text="Термин не найден — спроси в боте",
            switch_pm_parameter="inline_miss",
            cache_time=10,
        )
        return

    answers = []
    for term in results_list:
        abbrs = ", ".join(term.get("abbr") or [])
        description = term["definition"][:100] + ("…" if len(term["definition"]) > 100 else "")
        if abbrs:
            description = f"{abbrs} · {description}"

        answers.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"{term['en']} — {term['ru']}",
                description=description,
                input_message_content=InputTextMessageContent(
                    message_text=format_inline_text(term),
                    parse_mode=ParseMode.HTML,
                ),
            )
        )

    await update.inline_query.answer(answers, cache_time=300)

# ─── Bootstrap ────────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    env = Path(__file__).resolve().parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


async def _post_init(app: Application) -> None:
    """После старта берём реальный username бота из Telegram — без хардкода."""
    global BOT_USERNAME
    me = await app.bot.get_me()
    if me.username:
        BOT_USERNAME = me.username
    log.info(
        "Бот запущен v0.6 (@%s), терминов: %d, глав истории: %d",
        BOT_USERNAME, len(TERMS), len(HISTORY),
    )


def main() -> None:
    _load_dotenv()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("Нет токена: задай переменную окружения BOT_TOKEN или создай bot/.env")

    app = Application.builder().token(token).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(InlineQueryHandler(handle_inline))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_query))

    app.run_polling()


if __name__ == "__main__":
    main()
