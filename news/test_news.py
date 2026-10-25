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
    assert "⭐ <b>Главное:</b> Капризов — 3 очка (2+1)" in text
    assert "🏒 И. Протас — <b>1+0</b>" in text
    assert "<blockquote expandable>Без очков: А. Протас</blockquote>" in text
    assert "🥅 Шестёркин — 30 сейвов из 33, победа" in text
    assert "московск" not in text



def test_caption():
    from news.digest import render_caption
    from news.events import Event

    rep = parse_box(BOX, {1, 2, 3, 4, 5})
    hl = [(1, [Event(1, 60, "победный гол в овертайме")]), (2, [Event(2, 70, "первый гол в НХЛ")])]
    text, facts = render_caption([rep], PLAYERS, TEAMS, "2026-10-24", hl, "Капризов вытащил Миннесоту")
    blocks = text.split("\n\n")
    assert blocks[0] == "🚨 <b>Капризов — победный гол в овертайме</b>"  # заголовок-новость
    assert blocks[1] == "Капризов вытащил Миннесоту"
    assert blocks[2] == "⭐ <b>Ещё главное</b>\n✨ И. Протас — первый гол в НХЛ"
    assert "Капризов (Миннесота) — <b>2+1</b>" in blocks[3]
    assert "🥅 Шестёркин (Миннесота) — 30 из 33, победа" in blocks[3]
    assert blocks[-1] == "🌙 #НочьНаших · 24 октября"
    assert guard.check(text, facts, PLAYERS, TEAMS) == []
    short, _ = render_caption([rep], PLAYERS, TEAMS, "2026-10-24", with_teams=False)
    assert short.startswith("🌙 <b>Ночь наших · 24 октября</b>") and "(Миннесота)" not in short
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
    assert with_lead("Заголовок\n\nТело", "Фраза") == "Заголовок\n\n<blockquote>Фраза</blockquote>\n\nТело"


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

    def fake_post(url, body, headers, files=None):
        sent.append((url.split("/")[-1].split("?")[0], body.get("chat_id"), body.get("text", "")[:12]))
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


def test_events():
    from news import events

    rep = parse_box(BOX, {1, 2, 3, 4, 5})  # Миннесота выиграла 4:3 в ОТ, у Капризова 2+1, у И. Протаса 1+0
    scoring = [{"periodDescriptor": {"periodType": "REG"}, "goals": [
                   {"teamAbbrev": {"default": "MIN"}, "playerId": 1}, {"teamAbbrev": "WSH", "playerId": 2},
                   {"teamAbbrev": "MIN", "playerId": 7}, {"teamAbbrev": "MIN", "playerId": 8},
                   {"teamAbbrev": "WSH", "playerId": 9}, {"teamAbbrev": "WSH", "playerId": 10}]},
               {"periodDescriptor": {"periodType": "OT"}, "goals": [{"teamAbbrev": "MIN", "playerId": 1}]}]
    ctx = {"games": {100: {"scoring": scoring}}, "players": {
        # Капризов: после матча 500 очков за клуб, прежний рекордсмен — 498 → рекорд и юбилей
        1: {"this_game": True, "regular": True, "career": {"goals": 240, "assists": 260, "points": 500, "games": 600},
            "franchise": {"points": [(1, 500), (77, 498)], "goals": [(77, 260), (1, 240)]}},
        # И. Протас: первый гол; профиль Шестёркина не нужен — сухого матча нет
        2: {"this_game": True, "regular": True, "career": {"goals": 1, "assists": 3, "points": 4, "games": 90},
            "franchise": {}},
        # А. Протас без очков — карьерные события не считаются
    }}
    by = {pid: [e.text for e in evs] for pid, evs in events.headline(events.detect([rep], ctx), 5)}
    assert by[1] == ["лучший бомбардир в истории клуба: 500 очков", "500-е очко в НХЛ", "победный гол в овертайме"]
    assert by[2] == ["первый гол в НХЛ"]
    assert list(by)[0] == 1
    # профиль не обновился — молчим, а не объявляем «первый гол»
    ctx["players"][2]["this_game"] = False
    assert 2 not in {e.pid for e in events.detect([rep], ctx)}
    # блок «Главное» в тексте и числа событий в фактах гарда
    text, facts = render_night([rep], PLAYERS, TEAMS, "2026-10-24", events.headline(events.detect([rep], ctx)))
    assert "⭐ <b>Главное</b>\n<b>Капризов</b> — лучший бомбардир в истории клуба: 500 очков" in text
    assert guard.check(text, facts, PLAYERS, TEAMS) == []


def test_photo_caption_or_split():
    import os
    import tempfile
    from pathlib import Path

    from news import publish

    calls = []

    def fake_post(url, body, headers, files=None):
        calls.append((url.rsplit("/", 1)[-1], "caption" in body, bool(files)))
        return {"ok": True, "result": {"message_id": len(calls)}}

    png = Path(tempfile.mkdtemp()) / "c.png"
    png.write_bytes(b"png")
    os.environ["NEWS_BOT_TOKEN"] = "t"
    try:
        assert publish.visible_len("<b>а&amp;б</b>") == 3
        assert publish.tg_send("@ch", "<b>Коротко</b>", fake_post, str(png))[0]
        assert calls == [("sendPhoto", True, True)]
        calls.clear()
        publish.tg_send("@ch", "<b>" + "я" * 1025 + "</b>", fake_post, str(png))
        assert calls == [("sendPhoto", False, True), ("sendMessage", False, False)]
    finally:
        os.environ.pop("NEWS_BOT_TOKEN")


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"news: {len(tests)} тестов — ок")
