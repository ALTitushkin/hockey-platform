"""Тесты рубрики «В этот день». Запуск: python test_calendar.py (без зависимостей/токена)."""

from calendar_feature import (  # noqa: F401 — см. примечание ниже
    events_for_date,
    format_day_card,
    load_calendar,
    parse_date,
    today_mmdd,
)

CAL = load_calendar()


def check_parse(text: str, expected: str | None) -> None:
    got = parse_date(text)
    assert got == expected, f"parse_date({text!r}): ожидал {expected}, получил {got}"
    print(f"  ok: {text!r:26} → {got}")


def test_parse_valid() -> None:
    print("parse_date — валидные форматы:")
    cases = {
        "2 января": "01-02",
        "2 янв": "01-02",
        "14 марта": "03-14",
        "что было 2 января": "01-02",     # слова-обёртки игнорируются
        "14 марта в хоккее": "03-14",
        "02.01": "01-02",
        "2.1": "01-02",
        "14.03": "03-14",
        "02-01": "01-02",
        "14-03": "03-14",
        "14/03": "03-14",
        "31 декабря": "12-31",
        "1 МАЯ": "05-01",                  # регистр игнорируется
    }
    for t, exp in cases.items():
        check_parse(t, exp)


def test_parse_rejects() -> None:
    print("parse_date — антиколлизия (должны быть None):")
    for t in ["март", "14", "xG", "форчек", "one-timer", "5 на 3",
              "32 марта", "0 января", "12.2024", "корси", "", "слот"]:
        check_parse(t, None)


def test_events_sorted() -> None:
    print("events_for_date — сортировка по году:")
    ev = events_for_date("12-31", CAL)
    assert ev, "12-31: ожидались события"
    years = [e["year"] for e in ev]
    assert years == sorted(years), f"12-31: не отсортировано: {years}"
    print(f"  ok: 12-31 → {years}")


def test_empty_date() -> None:
    print("events_for_date — пустая дата:")
    ev = events_for_date("06-28", CAL)  # сегодня без события на момент написания
    assert ev == [], f"06-28: ожидался пустой список, получил {len(ev)}"
    card = format_day_card("06-28", ev)
    assert "рубрика ещё наполняется" in card, "пустая дата: нет заглушки"
    assert "28 июня" in card, "пустая дата: нет человекочитаемой даты"
    print("  ok: пустая дата → дружелюбная заглушка")


def test_card_format() -> None:
    print("format_day_card — структура карточки:")
    ev = events_for_date("12-31", CAL)
    card = format_day_card("12-31", ev)
    assert card.startswith("📅 <b>31 декабря</b>"), "нет заголовка с датой"
    for e in ev:
        assert str(e["year"]) in card, f"нет года {e['year']}"
        assert e["text"] in card, "нет текста события"
    print("  ok: заголовок + годы + тексты на месте")


def test_today_format() -> None:
    print("today_mmdd — формат:")
    t = today_mmdd()
    assert len(t) == 5 and t[2] == "-", f"today_mmdd вернул {t!r}"
    print(f"  ok: today_mmdd() = {t}")


if __name__ == "__main__":
    test_parse_valid()
    test_parse_rejects()
    test_events_sorted()
    test_empty_date()
    test_card_format()
    test_today_format()
    print("\n✅ Все тесты календаря прошли.")
