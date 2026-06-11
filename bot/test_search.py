"""Тесты поиска. Запуск: python test_search.py (без зависимостей)."""

from search import format_card, load_terms, search, suggest

TERMS = load_terms()


def check(query: str, expected_id: str) -> None:
    results = search(query, TERMS)
    assert results, f"'{query}': ничего не найдено"
    got = results[0]["id"]
    assert got == expected_id, f"'{query}': ожидал {expected_id}, получил {got}"
    print(f"  ok: '{query}' → {results[0]['en']}")


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
    assert "требует проверки" in card, "unverified без плашки!"
    card = format_card(search("corsi", TERMS)[0])
    assert "требует проверки" not in card, "verified с плашкой!"
    print("  ok: плашка unverified работает")

    print(f"\nВсе тесты пройдены. Терминов в базе: {len(TERMS)}")


if __name__ == "__main__":
    main()
