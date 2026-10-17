"""Тесты поиска. Запуск: python test_search.py (без зависимостей)."""

from search import (
    find_history_chapter,
    fix_layout,
    format_card,
    load_history,
    load_terms,
    search,
    suggest,
)

TERMS = load_terms()
HISTORY = load_history()


def check_not_in(query: str, not_id: str) -> None:
    ids = [r["id"] for r in search(query, TERMS)]
    assert not_id not in ids, f"'{query}': {not_id} не должен попадать (получил {ids})"
    print(f"  ok: '{query}' → {ids} (без {not_id})")


def check(query: str, expected_id: str) -> None:
    results = search(query, TERMS)
    assert results, f"'{query}': ничего не найдено"
    got = results[0]["id"]
    assert got == expected_id, f"'{query}': ожидал {expected_id}, получил {got}"
    print(f"  ok: '{query}' → {results[0]['en']}")


def check_history(query: str, expected_id: str | None) -> None:
    chapter = find_history_chapter(query, HISTORY)
    got = chapter["id"] if chapter else None
    assert got == expected_id, f"'{query}': ожидал главу {expected_id}, получил {got}"
    print(f"  ok: '{query}' → {got or '— (нет главы, верно)'}")


def main() -> None:
    print("Точные совпадения:")
    check("xG", "expected-goals")
    check("корси", "corsi")
    check("Corsi", "corsi")
    check("PDO", "pdo")
    check("форчек", "forecheck")
    check("forecheck", "forecheck")
    check("рыбачок", "fisherman")

    print("Опечатки / частичный ввод:")
    check("корс", "corsi")
    check("forechek", "forecheck")

    print("Пустой и мусорный ввод:")
    assert search("", TERMS) == []
    assert search("квантовая физика", TERMS) == []
    hints = suggest("корссси", TERMS)
    assert hints, "suggest должен вернуть подсказки"
    print(f"  ok: suggest('корссси') → {hints}")

    print("Карточка:")
    card = format_card(search("рыбачок", TERMS)[0])
    assert "на выверке" in card, "unverified без плашки!"
    card = format_card(search("corsi", TERMS)[0])
    assert "на выверке" not in card, "verified с плашкой!"
    print("  ok: плашка unverified работает")

    # Подпись сленга: «Сленг:», и скрытие пустого ru_slang (Трек C)
    card = format_card(search("форчек", TERMS)[0])  # forecheck: ru_slang «прессинг, пресс» (не дубль названия)
    assert "Сленг:" in card and "У нас говорят" not in card, "подпись сленга не обновлена"
    card = format_card(search("шайба", TERMS)[0])
    assert "Сленг:" not in card, "пустой ru_slang не должен показывать строку сленга"
    print("  ok: подпись «Сленг:» + пустой ru_slang скрыт")

    # Ссылки на сайт: схема / глава истории / термин в словаре; у unverified — никаких
    card = format_card(search("форчек", TERMS)[0])
    assert "diagrams/forecheck.svg" in card and "dictionary.html#t-forecheck" in card, "нет ссылок схемы/словаря"
    card = format_card(search("corsi", TERMS)[0])
    assert "history/modern-game.html#counting-shots" in card, "нет ссылки на главу истории"
    assert "Схема" not in card, "ссылка на схему у термина без схемы"
    card = format_card(search("рыбачок", TERMS)[0])
    assert "dictionary.html" not in card, "unverified-термин ведёт на сайт, где его нет"
    print("  ok: ссылки карточки на схему, историю и словарь")

    print("Поиск — новые термины S7 + антиложные совпадения:")
    check("хват", "handedness")
    check("правый хват", "handedness")
    check("левый хват", "handedness")
    check("хит", "body-check")
    check("силовой", "body-check")
    check("драфт", "draft")
    check("рхл", "rhl")
    check("нмхл", "rhl")
    check_not_in("нмхл", "nhl")   # «нмхл» не должен тащить «нхл» нечётко
    check("нхл", "nhl")
    check("Н0л", "nhl")           # цифра вместо буквы в аббревиатуре (лог S8)
    check("кх1", "khl")
    assert not search("н0", TERMS) or search("н0", TERMS)[0]["id"] != "nhl", "2 символа — не опечатка"

    print("Не та раскладка (fix_layout):")
    assert fix_layout("cbkjdjq") == "силовой", fix_layout("cbkjdjq")
    assert search(fix_layout("cbkjdjq"), TERMS)[0]["id"] == "body-check"
    assert fix_layout("форчек") is None and fix_layout("5 на 3") is None
    print("  ok: 'cbkjdjq' → 'силовой' → body-check; кириллица/цифры не трогаем")

    print("История (find_history_chapter):")
    check_history("история хоккея", "origins")
    check_history("откуда появился хоккей", "origins")
    check_history("кубок стэнли", "origins")
    check_history("нхл", "origins")
    # не должно ловить термины аналитики и короткие/общие слова
    check_history("форчек", None)
    check_history("corsi", None)
    check_history("ну", None)
    # «нхл» как подстрока внутри слова не должна срабатывать (границы слов)
    check_history("снхлынск", None)
    # главы 2–9: у каждой опубликованной главы есть свои триггеры
    check_history("оригинальная шестёрка", "golden-age-canada")
    check_history("система тарасова", "tarasov-system")
    check_history("суперсерия 1972", "summit-1972")
    check_history("кубок канады", "canada-cup")
    check_history("русская пятёрка", "exodus")
    check_history("локаут и аналитика", "modern-game")
    check_history("кубок гагарина", "russia-future")

    print(f"\nВсе тесты пройдены. Терминов в базе: {len(TERMS)}, глав истории: {len(HISTORY)}")


if __name__ == "__main__":
    main()
