"""Поиск по базе терминов. Не зависит от Telegram — чистая логика.

Используется ботом (bot.py) и тестами (test_search.py).
Источник данных: data/terms.json + data/expert_review.json.
"""

import difflib
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CATEGORY_RU = {
    "stat": "Статистика",
    "tactic": "Тактика",
    "position": "Позиция",
    "rule": "Правила",
}


def load_terms() -> list[dict]:
    """Грузит verified-термины и unverified-сленг в один список."""
    terms = json.loads((DATA_DIR / "terms.json").read_text(encoding="utf-8"))
    review_path = DATA_DIR / "expert_review.json"
    if review_path.exists():
        terms += json.loads(review_path.read_text(encoding="utf-8"))
    return terms


def _keys(term: dict) -> list[str]:
    """Все строки, по которым термин можно найти."""
    keys = [term["en"], term["ru"], term["id"]]
    keys += term.get("abbr") or []
    slang = term.get("ru_slang")
    if slang:
        keys += [s.strip() for s in slang.split(",")]
    return [k.lower() for k in keys if k]


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
            if best >= 0.75:
                fuzzy.append((best, term))

    fuzzy.sort(key=lambda x: -x[0])
    results = exact + prefix + [t for _, t in fuzzy]
    # убрать дубликаты, сохранив порядок
    seen, out = set(), []
    for t in results:
        if t["id"] not in seen:
            seen.add(t["id"])
            out.append(t)
    return out[:limit]


def suggest(query: str, terms: list[dict], limit: int = 3) -> list[str]:
    """Ближайшие названия для «ничего не нашлось»."""
    all_keys = sorted({k for t in terms for k in _keys(t)})
    return difflib.get_close_matches(query.strip().lower(), all_keys, n=limit, cutoff=0.5)


def format_card(term: dict) -> str:
    """Карточка термина для Telegram (HTML-разметка)."""
    lines = [f"<b>{term['en']}</b> · {term['ru']}"]
    meta = [CATEGORY_RU.get(term["category"], term["category"])]
    if term.get("abbr"):
        meta.append(", ".join(term["abbr"]))
    lines.append(f"<i>{' · '.join(meta)}</i>")
    lines.append("")
    lines.append(term["definition"])
    if term.get("ru_slang"):
        lines.append(f"\n💬 Сленг: {term['ru_slang']}")
    if term.get("status") != "verified":
        lines.append("\n⚠️ <i>Термин требует проверки экспертом — возможны неточности.</i>")
    return "\n".join(lines)
