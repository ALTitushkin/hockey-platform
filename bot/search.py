"""Поиск по базе терминов. Не зависит от Telegram — чистая логика.

Используется ботом (bot.py) и тестами (test_search.py).
Источник данных: data/terms.json + data/expert_review.json.
История: data/history.json.
"""

import difflib
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# Сайт платформы: ссылки из карточки ведут в словарь, на схему и в главу истории.
SITE_URL = "https://altitushkin.github.io/hockey-platform/"

CATEGORY_RU = {
    "stat": "Статистика",
    "tactic": "Тактика",
    "position": "Позиция",
    "rule": "Правила",
    "basics": "Базовое / техника",
    "org": "Лиги / организации",
}


def load_terms() -> list[dict]:
    """Грузит verified-термины и unverified-сленг в один список."""
    terms = json.loads((DATA_DIR / "terms.json").read_text(encoding="utf-8"))
    review_path = DATA_DIR / "expert_review.json"
    if review_path.exists():
        terms += json.loads(review_path.read_text(encoding="utf-8"))
    return terms


def load_review() -> list[dict]:
    """Грузит только unverified-сленг (expert_review.json) — для счётчиков."""
    path = DATA_DIR / "expert_review.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _keys(term: dict) -> list[str]:
    """Все строки, по которым термин можно найти."""
    keys = [term["en"], term["ru"], term["id"]]
    keys += term.get("abbr") or []
    slang = term.get("ru_slang")
    if slang:
        keys += [s.strip() for s in slang.split(",")]
    return [k.lower() for k in keys if k]


def _digit_typo(q: str, k: str) -> bool:
    """«н0л» → «нхл»: та же длина, отличие ровно в одной позиции, и там в запросе цифра.
    Короткие аббревиатуры по SequenceMatcher так не ловятся (2/3 букв = 0.67 < порога),
    а снижать порог нельзя — полезут ложные совпадения. Цифра посреди букв — почти
    всегда промах по клавише, поэтому правило узкое и безопасное."""
    if len(q) != len(k) or len(q) < 3:
        return False
    diff = [i for i, (a, b) in enumerate(zip(q, k)) if a != b]
    return len(diff) == 1 and q[diff[0]].isdigit() and not k[diff[0]].isdigit()


def search(query: str, terms: list[dict], limit: int = 3) -> list[dict]:
    """Возвращает до `limit` терминов: точные совпадения, затем нечёткие."""
    q = query.strip().lower()
    if not q:
        return []

    exact, prefix, fuzzy = [], [], []
    for term in terms:
        keys = _keys(term)
        if q in keys:
            exact.append(term)
        elif any(k.startswith(q) or q in k for k in keys):
            prefix.append(term)
        else:
            best = max(
                (difflib.SequenceMatcher(None, q, k).ratio() for k in keys),
                default=0,
            )
            if best < 0.75 and any(_digit_typo(q, k) for k in keys):
                best = 0.75
            if best >= 0.75:
                fuzzy.append((best, term))

    fuzzy.sort(key=lambda x: -x[0])
    # Нечёткие совпадения подключаем ТОЛЬКО если нет точных/префиксных —
    # иначе близкие по буквам термины лезут как ложные (напр. «нмхл» → «нхл»).
    results = exact + prefix if (exact or prefix) else [t for _, t in fuzzy]
    # убрать дубликаты, сохранив порядок
    seen, out = set(), []
    for t in results:
        if t["id"] not in seen:
            seen.add(t["id"])
            out.append(t)
    return out[:limit]


# Раскладка ЙЦУКЕН поверх QWERTY: «cbkjdjq» — это «силовой», набранный не в той раскладке.
_LAYOUT = str.maketrans("qwertyuiop[]asdfghjkl;'zxcvbnm,.`", "йцукенгшщзхъфывапролджэячсмитьбюё")


def fix_layout(query: str) -> str | None:
    """Запрос в английской раскладке вместо русской → русский вариант, иначе None.
    Звать только при пустой выдаче: настоящие латинские термины (Corsi, xG) уже нашлись."""
    q = query.strip().lower()
    if not q or not re.fullmatch(r"[a-z\[\];',.`\s]+", q):
        return None
    return q.translate(_LAYOUT)


def suggest(query: str, terms: list[dict], limit: int = 3) -> list[str]:
    """Ближайшие названия для «ничего не нашлось»."""
    all_keys = sorted({k for t in terms for k in _keys(t)})
    return difflib.get_close_matches(query.strip().lower(), all_keys, n=limit, cutoff=0.5)


CATEGORY_EMOJI = {
    "stat": "📊",
    "tactic": "🧩",
    "rule": "📏",
    "position": "⛸",
    "basics": "🏒",
    "org": "🏛",
}


def format_card(term: dict) -> str:
    """Карточка термина для Telegram (HTML-разметка)."""
    emoji = CATEGORY_EMOJI.get(term["category"], "🏒")
    lines = [f"{emoji} <b>{term['en']}</b> — {term['ru']}"]
    meta = [CATEGORY_RU.get(term["category"], term["category"])]
    if term.get("abbr"):
        meta.append(" ".join(f"<code>{a}</code>" for a in term["abbr"]))
    lines.append(f"<i>{meta[0]}</i>" + (f" · {meta[1]}" if len(meta) > 1 else ""))
    lines.append("")
    lines.append(term["definition"])
    if term.get("ru_slang"):
        lines.append(f"\n💬 <i>Сленг:</i> {term['ru_slang']}")
    if term.get("status") != "verified":
        lines.append("\n⚠️ <i>Термин на выверке у эксперта — возможны неточности.</i>")
    links = term_links(term)
    if links:
        lines.append("\n" + " · ".join(links))
    return "\n".join(lines)


def term_links(term: dict) -> list[str]:
    """Ссылки карточки на сайт: схема, глава истории, сам термин в словаре.

    Термины на выверке (expert_review) на сайте не публикуются — им ссылок не даём.
    """
    if term.get("status") != "verified":
        return []
    links = []
    if term.get("visual_type") == "scheme" and term.get("visual"):
        links.append(f'🗺 <a href="{SITE_URL}{term["visual"]}">Схема</a>')
    anchor = term.get("anchor")
    if anchor and anchor.get("target"):
        frag = f'#{anchor["anchor_id"]}' if anchor.get("anchor_id") else ""
        links.append(f'📚 <a href="{SITE_URL}{anchor["target"]}{frag}">{anchor.get("label") or "История"}</a>')
    links.append(f'📖 <a href="{SITE_URL}dictionary.html#t-{term["id"]}">В словаре</a>')
    return links


# ─── История ────────────────────────────────────────────────────────────────

# Минимальная длина запроса/ключевого слова, чтобы не ловить случайные совпадения.
_MIN_HISTORY_LEN = 3


def load_history() -> list[dict]:
    """Грузит главы истории из data/history.json. Пустой список, если файла нет."""
    path = DATA_DIR / "history.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def find_history_chapter(query: str, history: list[dict]) -> dict | None:
    """Глава истории по ключевым словам. Только при miss в словаре.

    Совпадение ищется по границам слов (а не подстрокой), чтобы короткие
    ключи вроде «нхл» не срабатывали внутри других слов. Запросы и ключи
    короче _MIN_HISTORY_LEN символов игнорируются.
    """
    q = query.strip().lower()
    if len(q) < _MIN_HISTORY_LEN:
        return None
    for chapter in history:
        for kw in chapter.get("keywords", []):
            kw = kw.strip().lower()
            if len(kw) < _MIN_HISTORY_LEN:
                continue
            if re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", q):
                return chapter
    return None
