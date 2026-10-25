"""Тесты новостника без сети: шаблон, имена, гард. Запуск: python -m news.test_news"""

from news import guard
from news.digest import plural, render_night, with_lead
from news.nhl import parse_box

PLAYERS = {
    "1": {"ru": "Кирилл Капризов", "surname": "Капризов", "status": "confirmed"},
    "2": {"ru": "Илья Протас", "surname": "Протас", "status": "draft"},
    "3": {"ru": "Алексей Протас", "surname": "Протас", "status": "draft"},
    "4": {"ru": "Игорь Шестёркин", "surname": "Шестёркин", "status": "confirmed"},
    "5": {"ru": "Никита Кучеров", "surname": "Кучеров", "status": "confirmed"},
}
TEAMS = {"MIN": "Миннесота", "WSH": "Вашингтон", "NYR": "Рейнджерс", "TBL": "Тампа"}


def skater(pid, g, a, sog):
    return {"playerId": pid, "goals": g, "assists": a, "points": g + a, "sog": sog}


BOX = {
    "id": 100,
    "homeTeam": {"abbrev": "WSH", "score": 3},
    "awayTeam": {"abbrev": "MIN", "score": 4},
    "gameOutcome": {"lastPeriodType": "OT"},
    "playerByGameStats": {
        "homeTeam": {"forwards": [skater(2, 1, 0, 2), skater(3, 0, 0, 0), skater(999, 2, 0, 5)],
                     "defense": [], "goalies": []},
        "awayTeam": {"forwards": [skater(1, 2, 1, 6)], "defense": [],
                     "goalies": [{"playerId": 4, "saves": 30, "shotsAgainst": 33, "decision": "W"},
                                 {"playerId": 5, "saves": 0, "shotsAgainst": 0, "decision": None}]},
    },
}


def build():
    rep = parse_box(BOX, {1, 2, 3, 4, 5})
    return render_night([rep], PLAYERS, TEAMS, "2026-10-24")


def test_parse_box_keeps_only_ours_who_played():
    rep = parse_box(BOX, {1, 2, 3, 4, 5})
    assert {s.pid for s in rep.skaters} == {1, 2, 3}  # 999 не наш
    assert [g.pid for g in rep.goalies] == [4]  # 5 сидел на скамейке
    assert rep.last_period == "OT"


def test_render():
    text, _ = build()
    assert "Вашингтон — Миннесота 3:4 ОТ" in text
    assert "⭐ Главное: Капризов — 3 очка (2+1)" in text
    assert "И. Протас (Вашингтон) — 1+0, 2 броска" in text
    assert "А. Протас (Вашингтон) — без очков" in text
    assert "Шестёркин (Миннесота) — 30 сейвов из 33, победа" in text
    assert "999" not in text


def test_render_empty():
    assert render_night([], PLAYERS, TEAMS, "2026-10-24")[0] == ""


def test_plural():
    assert [plural(n, ("бросок", "броска", "бросков")) for n in (1, 2, 5, 11, 21, 22, 112)] == \
        ["бросок", "броска", "бросков", "бросков", "бросок", "броска", "бросков"]


def test_guard_template_clean():
    text, facts = build()
    assert guard.check(text, facts, PLAYERS, TEAMS) == []


def test_guard_catches_fabrication():
    text, facts = build()
    bad = text.replace("30 сейвов", "31 сейв") + "\nКучерова ждут. По слухам, Тампу продают."
    issues = " | ".join(guard.check(bad, facts, PLAYERS, TEAMS))
    assert "числа не из данных: 31" in issues
    assert "фамилия без данных: Кучеров" in issues
    assert "клуб без данных: Тампа" in issues
    assert "оборот-слух" in issues


def test_guard_lost_player_and_publish_mode():
    text, facts = build()
    issues = guard.check(text.replace("Шестёркин", "Вратарь"), facts, PLAYERS, TEAMS, publish=True)
    assert "потерян игрок: Игорь Шестёркин" in issues
    assert "написание не сверено: Илья Протас" in issues


def test_lead():
    _, facts = build()
    ok = "Капризов вытащил Миннесоту в овертайме"
    assert guard.check_lead(ok, facts, PLAYERS, TEAMS) == []
    for bad in ("Капризов оформил дубль", "Два гола Капризова", "Капризов впервые решил", "Капризов — 3 очка"):
        assert guard.check_lead(bad, facts, PLAYERS, TEAMS), bad
    assert with_lead("Заголовок\n\nТело", "Фраза") == "Заголовок\n\nФраза\n\nТело"


def test_llm_chain_falls_through():
    from news.llm import lead

    def boom(_):
        raise TimeoutError("лимит")

    accept = lambda p: [] if "Капризов" in p else ["нет"]  # noqa: E731
    fake = {"a": boom, "b": lambda _: None, "c": lambda _: "Кучеров молодец", "d": lambda _: "Капризов решил"}
    phrase, source, log = lead("пост", accept, chain="a,b,c,d", providers=fake)
    assert (phrase, source) == ("Капризов решил", "d")
    assert len(log) == 3 and "ошибка TimeoutError" in log[0] and "отклонена" in log[2]
    assert lead("пост", accept, chain="a,b", providers=fake)[:2] == (None, "шаблон")
    assert lead("пост", accept, chain="none,d", providers=fake)[:2] == (None, "шаблон")


def test_publish_gates():
    import os
    import tempfile
    from pathlib import Path

    from news import publish

    sent = []

    def fake_post(url, body, headers):
        sent.append((url.split("/")[-1].split("?")[0], body.get("chat_id"), body["text"][:12]))
        return {"ok": True, "result": {"message_id": len(sent)}} if "telegram" in url else {"message": {}}

    old_out, old_env = publish.OUT, dict(os.environ)
    publish.OUT = Path(tempfile.mkdtemp())
    os.environ.update({"NEWS_BOT_TOKEN": "t", "NEWS_CHANNEL": "@ch", "OWNER_CHAT_ID": "42"})
    os.environ.pop("MAX_BOT_TOKEN", None)
    try:
        assert publish.publish("2026-10-24", ["tg"], fake_post)[0] is False  # черновика нет
        publish.save_draft("2026-10-24", "Пост", ["выдумка: 7"], "шаблон")
        assert publish.publish("2026-10-24", ["tg"], fake_post)[0] is False and not sent  # гард не чист
        publish.save_draft("2026-10-24", "Пост", [], "шаблон")
        assert publish.review("2026-10-24", fake_post)[0] and {c for _, c, _ in sent} == {"42"}  # только в личку
        sent.clear()
        ok, report = publish.publish("2026-10-24", ["tg", "max"], fake_post)
        assert not ok and sent == [("sendMessage", "@ch", "Пост")] and "MAX не настроен" in report[1]
        ok, report = publish.publish("2026-10-24", ["tg"], fake_post)
        assert ok and len(sent) == 1 and "уже опубликовано" in report[0]  # дубль не уходит
        publish.save_draft("2026-10-24", "Пост v2", [], "шаблон")  # пересборка после выхода
        assert "уже опубликовано" in publish.publish("2026-10-24", ["tg"], fake_post)[1][0] and len(sent) == 1
    finally:
        publish.OUT = old_out
        os.environ.clear()
        os.environ.update(old_env)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"news: {len(tests)} тестов — ок")
