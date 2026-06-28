#!/usr/bin/env python3
"""
tools/add_term.py — добавление терминов в базу (схема v2.0).

Интерактивно (один термин):
    python tools/add_term.py

Пакетно (bulk, без ввода — для пополнения из лога спроса):
    python tools/add_term.py --batch path/to/batch.json
    # batch.json — объект или список объектов с полями термина (частичными;
    # недостающие поля схемы v2.0 заполняются дефолтами).

Обновляет оба файла: data/terms.json и docs/data/terms.json.
Каждая запись пишется полным набором полей схемы v2.0
(profiles/cluster/see_also/anchor/source/added/status), чтобы проходить
tools/validate_data.py.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERM_FILES = [
    ROOT / "data" / "terms.json",
    ROOT / "docs" / "data" / "terms.json",
]
CLUSTERS_FILE = ROOT / "data" / "clusters.json"

CATEGORIES = ["stat", "tactic", "rule", "position", "basics", "org"]
LEVELS     = ["novice", "fan", "geek"]

# Канонический порядок полей — совпадает с существующими записями terms.json.
FIELD_ORDER = [
    "id", "en", "ru", "category", "abbr", "definition", "ru_slang",
    "visual", "visual_type", "source", "status", "added", "notes",
    "level", "profiles", "cluster", "see_also", "anchor",
]


def load(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: list) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_id(en: str) -> str:
    return en.lower().replace(" ", "-").replace("/", "-")


def cluster_slugs() -> set:
    if CLUSTERS_FILE.exists():
        return {c["slug"] for c in load(CLUSTERS_FILE)}
    return set()


def make_record(raw: dict) -> dict:
    """Частичный dict -> полная запись схемы v2.0 с дефолтами и валидацией."""
    en = (raw.get("en") or "").strip()
    if not en:
        raise ValueError("поле 'en' обязательно")
    rec = {
        "id":          raw.get("id") or build_id(en),
        "en":          en,
        "ru":          (raw.get("ru") or "").strip(),
        "category":    raw.get("category"),
        "abbr":        raw.get("abbr") or [],
        "definition":  (raw.get("definition") or "").strip(),
        "ru_slang":    (raw.get("ru_slang") or None),
        "visual":      raw.get("visual"),
        "visual_type": raw.get("visual_type"),
        "source":      (raw.get("source") or "").strip(),
        "status":      raw.get("status", "verified"),
        "added":       raw.get("added") or date.today().isoformat(),
        "notes":       raw.get("notes") or "",
        "level":       raw.get("level"),
        "profiles":    raw.get("profiles") or [],
        "cluster":     raw.get("cluster"),
        "see_also":    raw.get("see_also") or [],
        "anchor":      raw.get("anchor"),
    }
    if not rec["ru"]:
        raise ValueError(f"{rec['id']}: поле 'ru' обязательно")
    if not rec["definition"]:
        raise ValueError(f"{rec['id']}: поле 'definition' обязательно")
    if not rec["source"]:
        raise ValueError(f"{rec['id']}: поле 'source' обязательно")
    if rec["category"] not in CATEGORIES:
        raise ValueError(f"{rec['id']}: category '{rec['category']}' не из {CATEGORIES}")
    if rec["level"] not in LEVELS:
        raise ValueError(f"{rec['id']}: level '{rec['level']}' не из {LEVELS}")
    cl = rec["cluster"]
    if cl is not None and cl not in cluster_slugs():
        raise ValueError(f"{rec['id']}: cluster '{cl}' нет в clusters.json")
    return {k: rec[k] for k in FIELD_ORDER}


def append_terms(records: list) -> None:
    for path in TERM_FILES:
        existing = {t["id"] for t in load(path)}
        for rec in records:
            if rec["id"] in existing:
                raise SystemExit(
                    f"  ⚠ id='{rec['id']}' уже есть в {path.name}. "
                    f"Прерываю, ничего не записано."
                )
    for path in TERM_FILES:
        data = load(path)
        data.extend(records)
        save(path, data)
        print(f"  ✓ {path.relative_to(ROOT)} (+{len(records)})")


def git_hint() -> None:
    print("\n  Следующий шаг:")
    print("    python tools/validate_data.py")
    print("    git add data/terms.json docs/data/terms.json")
    print('    git commit -m "feat(terms): пополнение базы (S7 Трек B)"')
    print("    git push origin main\n")


def run_batch(batch_path: str) -> None:
    raw = json.loads(Path(batch_path).read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else [raw]
    records = [make_record(r) for r in items]
    ids = [r["id"] for r in records]
    if len(set(ids)) != len(ids):
        raise SystemExit("  ⚠ дублирующиеся id внутри батча")
    print(f"\n🏒 Пакетное добавление: {len(records)} терминов")
    for r in records:
        print(f"   • {r['id']:<18} [{r['category']}/{r['level']}]  {r['ru']}")
    append_terms(records)
    print(f"\n  Добавлено {len(records)}: {', '.join(ids)}")
    git_hint()


def ask(prompt: str, choices=None, required: bool = True) -> str:
    if choices:
        prompt += f" [{'/'.join(choices)}]"
    while True:
        val = input(f"  {prompt}: ").strip()
        if val:
            if choices and val not in choices:
                print(f"    ⚠ Выбери одно из: {', '.join(choices)}")
                continue
            return val
        if not required:
            return ""
        print("    ⚠ Поле обязательное")


def ask_list(prompt: str) -> list:
    raw = input(f"  {prompt} (через запятую, Enter — пропустить): ").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def run_interactive() -> None:
    print("\n🏒 Добавление нового термина в хоккейный словарь (схема v2.0)")
    print("─" * 50)
    raw = {
        "en":         ask("Английский термин (en)"),
        "ru":         ask("Русский перевод (ru)"),
        "category":   ask("Категория", choices=CATEGORIES),
        "level":      ask("Уровень", choices=LEVELS),
        "definition": ask("Определение (definition)"),
        "abbr":       ask_list("Аббревиатуры (abbr)"),
        "ru_slang":   ask("Сленг (ru_slang)", required=False) or None,
        "source":     ask("Источник (source)"),
        "cluster":    ask("Кластер (cluster slug)", required=False) or None,
        "see_also":   ask_list("См. также (see_also id)"),
        "status":     ask("Статус", choices=["verified", "unverified"], required=False) or "verified",
    }
    try:
        rec = make_record(raw)
    except ValueError as e:
        print(f"\n  ⚠ {e}")
        sys.exit(1)
    print("\nНовый термин:")
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    if input("\n  Записать? [y/N]: ").strip().lower() != "y":
        print("  Отменено.")
        sys.exit(0)
    append_terms([rec])
    print(f"\n  Термин '{rec['en']}' добавлен (id: {rec['id']}).")
    git_hint()


def main() -> None:
    parser = argparse.ArgumentParser(description="Добавление терминов в базу (схема v2.0).")
    parser.add_argument("--batch", metavar="PATH",
                        help="JSON-файл (объект или список) для пакетного добавления")
    args = parser.parse_args()
    if args.batch:
        run_batch(args.batch)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
