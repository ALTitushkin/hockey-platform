#!/usr/bin/env python3
"""
tools/add_term.py — CLI для добавления нового термина в базу.

Запуск из корня репо:
    python tools/add_term.py

Обновляет оба файла: data/terms.json и docs/data/terms.json
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERM_FILES = [
    ROOT / "data" / "terms.json",
    ROOT / "docs" / "data" / "terms.json",
]

CATEGORIES = ["stat", "tactic", "rule", "position"]
LEVELS     = ["novice", "fan", "geek"]


def ask(prompt: str, choices: list[str] | None = None, required: bool = True) -> str:
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


def ask_list(prompt: str) -> list[str]:
    raw = input(f"  {prompt} (через запятую, Enter — пропустить): ").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: list[dict]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_id(en: str) -> str:
    return en.lower().replace(" ", "-").replace("/", "-")


def main() -> None:
    print("\n🏒 Добавление нового термина в хоккейный словарь")
    print("─" * 50)

    terms = load(TERM_FILES[0])
    existing_ids = {t["id"] for t in terms}

    en = ask("Английский термин (en)")
    term_id = build_id(en)
    if term_id in existing_ids:
        print(f"\n  ⚠ Термин с id='{term_id}' уже существует. Прерываю.")
        sys.exit(1)

    ru        = ask("Русский перевод (ru)")
    category  = ask("Категория", choices=CATEGORIES)
    level     = ask("Уровень", choices=LEVELS)
    definition= ask("Определение (definition)")
    abbr      = ask_list("Аббревиатуры (abbr)")
    ru_slang  = ask("Сленговое название (ru_slang)", required=False)
    status_val= ask("Статус", choices=["verified", "expert_review"], required=False) or "verified"

    new_term: dict = {
        "id":         term_id,
        "en":         en,
        "ru":         ru,
        "abbr":       abbr,
        "category":   category,
        "level":      level,
        "definition": definition,
    }
    if ru_slang:
        new_term["ru_slang"] = ru_slang
    if status_val != "verified":
        new_term["status"] = status_val

    print("\n─" * 25)
    print("Новый термин:")
    print(json.dumps(new_term, ensure_ascii=False, indent=2))
    print()

    confirm = input("  Записать? [y/N]: ").strip().lower()
    if confirm != "y":
        print("  Отменено.")
        sys.exit(0)

    for path in TERM_FILES:
        data = load(path)
        data.append(new_term)
        save(path, data)
        print(f"  ✓ {path.relative_to(ROOT)}")

    print(f"\n  Термин '{en}' добавлен (id: {term_id}).")
    print("\n  Следующий шаг:")
    print("    git add data/terms.json docs/data/terms.json")
    print(f'    git commit -m "feat(terms): добавлен термин {en}"')
    print("    git push origin main\n")


if __name__ == "__main__":
    main()
