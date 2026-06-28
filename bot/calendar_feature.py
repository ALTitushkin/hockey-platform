"""Рубрика «В этот день в истории хоккея». Чистая логика, без Telegram.

Используется ботом (bot.py) и тестами (test_calendar.py).
Источник данных: data/calendar.json — словарь {"MM-DD": [событие, ...]}.

Событие: {year:int, text:str, cat:str, reg:str, conf:str, video?:str}
  cat — Рождение/Гибель/Дебют/Рекорд/Матч/Турнир/Переход/Возвращение/Достижение/Организация
  reg — RU/NHL/INT/WORLD ; conf — high/med ; video (опц.) — ссылка на момент.

Таймзона рубрики — Europe/Moscow (фикс. +03:00; в РФ нет переходов на летнее время).
"""

import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MSK = timezone(timedelta(hours=3))  # Europe/Moscow, фиксированный офсет

# ─── Месяцы ───────────────────────────────────────────────────────────────────
# Родительный падеж для вывода («14 марта»).
MONTH_GEN = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}
# Все формы, которые принимаем во входе (ё уже заменена на е). Именительный,
# родительный и распространённые сокращения.
_MONTH_FORMS = {
    1: ["январь", "января", "янв"],
    2: ["февраль", "февраля", "фев"],
    3: ["март", "марта", "мар"],
    4: ["апрель", "апреля", "апр"],
    5: ["май", "мая"],
    6: ["июнь", "июня", "июн"],
    7: ["июль", "июля", "июл"],
    8: ["август", "августа", "авг"],
    9: ["сентябрь", "сентября", "сент", "сен"],
    10: ["октябрь", "октября", "окт"],
    11: ["ноябрь", "ноября", "ноя"],
    12: ["декабрь", "декабря", "дек"],
}
MONTH_LOOKUP = {form: num for num, forms in _MONTH_FORMS.items() for form in forms}

CAT_EMOJI = {
    "Рождение": "🎂", "Гибель": "🕯", "Дебют": "🌟", "Рекорд": "🏆",
    "Матч": "🏒", "Турнир": "🥇", "Переход": "🔄", "Возвращение": "↩️",
    "Достижение": "🏅", "Организация": "🏛",
}

SITE_URL = "https://altitushkin.github.io/hockey-platform/"
_KEY_RE = re.compile(r"^\d{2}-\d{2}$")


# ─── Загрузка/валидация ───────────────────────────────────────────────────────
def load_calendar() -> dict[str, list[dict]]:
    """Грузит и валидирует data/calendar.json. Пустой словарь, если файла нет."""
    path = DATA_DIR / "calendar.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("calendar.json: ожидался объект {MM-DD: [...]}")
    for key, events in data.items():
        if not _KEY_RE.match(key):
            raise ValueError(f"calendar.json: ключ '{key}' не в формате MM-DD")
        mm, dd = int(key[:2]), int(key[3:])
        if not (1 <= mm <= 12 and 1 <= dd <= 31):
            raise ValueError(f"calendar.json: некорректная дата '{key}'")
        if not isinstance(events, list):
            raise ValueError(f"calendar.json[{key}]: значение должно быть списком")
        for ev in events:
            if not isinstance(ev.get("year"), int) or not ev.get("text"):
                raise ValueError(f"calendar.json[{key}]: событие без year/text")
    return data


# ─── Доступ к данным ──────────────────────────────────────────────────────────
def events_for_date(mmdd: str, calendar: dict[str, list[dict]]) -> list[dict]:
    """Все события дня MM-DD, отсортированные по году (по возрастанию)."""
    return sorted(calendar.get(mmdd, []), key=lambda e: e.get("year", 0))


def today_mmdd() -> str:
    """Сегодняшняя дата (Europe/Moscow) в формате MM-DD."""
    return datetime.now(MSK).strftime("%m-%d")


def random_day(calendar: dict[str, list[dict]]) -> str | None:
    """Случайная дата, у которой есть события (для кнопки «Случайный день»)."""
    keys = [k for k, v in calendar.items() if v]
    return random.choice(keys) if keys else None


# ─── Разбор человеческой даты ─────────────────────────────────────────────────
_WORD_RE = re.compile(r"(?<!\d)(\d{1,2})\s+([а-я]+)")
_NUM_RE = re.compile(r"(\d{1,2})\s*[.\-/]\s*(\d{1,2})")


def parse_date(text: str) -> str | None:
    """Человеческая дата → 'MM-DD' (день-первым) или None.

    Понимает: «сегодня»/«завтра»/«вчера», «2 января», «2 янв», «14 марта», «02.01», «2.1», «14-03», «14/03».
    Игнорирует регистр, ё и слова-обёртки («что было 2 января»).
    Антиколлизия со словарём: срабатывает ТОЛЬКО на явный дате-паттерн —
    число + месяц-слово, либо строка целиком вида DD.MM/DD-DD. Одиночные слова
    («март»), одиночные числа и термины → None.
    """
    if not text:
        return None
    t = text.strip().lower().replace("ё", "е")

    # 0) Относительные слова: сегодня / завтра / вчера (по Москве).
    rel = {"сегодня": 0, "завтра": 1, "вчера": -1}
    m = re.search(r"(?<!\w)(сегодня|завтра|вчера)(?!\w)", t)
    if m:
        d = datetime.now(MSK) + timedelta(days=rel[m.group(1)])
        return d.strftime("%m-%d")

    # 1) «день + месяц-слово» — ищем внутри текста (сильный сигнал).
    for m in _WORD_RE.finditer(t):
        day = int(m.group(1))
        month = MONTH_LOOKUP.get(m.group(2))
        if month and 1 <= day <= 31:
            return f"{month:02d}-{day:02d}"

    # 2) Числовой DD.MM / DD-MM / DD/MM — только если вся строка и есть дата.
    m = _NUM_RE.fullmatch(t)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{month:02d}-{day:02d}"

    return None


# ─── Форматирование карточки ──────────────────────────────────────────────────
def _human_date(mmdd: str) -> str:
    mm, dd = int(mmdd[:2]), int(mmdd[3:])
    return f"{dd} {MONTH_GEN.get(mm, mmdd)}"


def format_day_card(mmdd: str, events: list[dict]) -> str:
    """HTML-карточка дня для Telegram. events предполагаются отсортированными."""
    head = f"📅 <b>{_human_date(mmdd)}</b> в истории хоккея"
    if not events:
        return (
            f"{head}\n\n"
            "На эту дату пока не нашли событие — рубрика ещё наполняется. "
            "Загляни в другой день или жми «Случайный день».\n\n"
            f"🔗 <a href=\"{SITE_URL}\">Культура хоккея</a>"
        )
    blocks = []
    for ev in events:
        emoji = CAT_EMOJI.get(ev.get("cat", ""), "🏒")
        lines = [f"<b>{ev['year']}</b> — {ev['text']}", f"{emoji} <i>{ev.get('cat', '')}</i>"]
        if ev.get("video"):
            lines.append(f"🎥 <a href=\"{ev['video']}\">Смотреть момент</a>")
        blocks.append("\n".join(lines))
    body = "\n\n".join(blocks)
    return f"{head}\n\n{body}\n\n🔗 <a href=\"{SITE_URL}\">Культура хоккея</a>"
