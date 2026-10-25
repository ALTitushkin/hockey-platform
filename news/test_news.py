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
    assert blocks[3] == "📊 <b>Очки наших</b>\n<b>Капризов</b> 2+1 · Миннесота"
    assert blocks[4] == "<b>И. Протас</b> 1+0 · Вашингтон"  # группа «1 очко» — через пустую строку
    assert blocks[5] == "🥅 <b>Шестёркин</b> 30 из 33 · Миннесота, победа"
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
        assert ok and sent == [("sendMessage", "@ch", "Пост")] and "max: не подключён" in report[1]
        ok, report = publish.publish("2026-10-24", ["tg"], fake_post)
        assert ok and len(sent) == 1 and "уже опубликовано" in report[0]  # дубль не уходит
        publish.save_draft("2026-10-24", "Пост v2", [], "шаблон")  # пересборка после выхода
        assert "уже опубликовано" in publish.publish("2026-10-24", ["tg"], fake_post)[1][0] and len(sent) == 1
        # автопубликация: пост в канал, отчёт владельцу; повтор той же даты не уходит ни в канал, ни владельцу
        # (25.10.2026 повтор прислал владельцу «вышло автоматически», хотя в канал ничего не ушло)
        sent.clear()
        publish.save_draft("2026-10-25", "Пост", [], "шаблон")
        assert publish.auto_publish("2026-10-25", fake_post)[0]
        assert [c for _, c, _ in sent] == ["@ch", "42"]
        publish.auto_publish("2026-10-25", fake_post)
        assert [c for _, c, _ in sent] == ["@ch", "42"]
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


def test_service_buttons_and_schedule():
    import os
    import tempfile
    from datetime import datetime, time
    from pathlib import Path

    from news import publish, service

    calls = []

    def fake_post(url, body, headers, files=None):
        calls.append((url.rsplit("/", 1)[-1], body))
        return {"ok": True, "result": {"message_id": len(calls)}}

    old_out = publish.OUT
    publish.OUT = Path(tempfile.mkdtemp())
    os.environ.update({"NEWS_BOT_TOKEN": "t", "NEWS_CHANNEL": "@ch", "OWNER_CHAT_ID": "42"})
    try:
        publish.save_draft("2026-10-25", "Пост", [], "шаблон")
        assert publish.review("2026-10-25", fake_post)[0]
        keys = [b["callback_data"] for b in calls[-1][1]["reply_markup"]["inline_keyboard"][0]]
        assert keys == ["pub:night:2026-10-25", "rej:night:2026-10-25"]

        def press(who, data):
            calls.clear()
            upd = {"callback_query": {"id": "c", "from": {"id": who}, "data": data,
                                      "message": {"chat": {"id": 42}, "message_id": 7}}}
            return service.handle_update(upd, "42", fake_post)

        assert "игнор" in press(99, "pub:2026-10-25") and not any(m == "sendMessage" for m, _ in calls)
        assert press(42, "pub:2026-10-25").startswith("pub")
        assert ("sendMessage", "@ch") in [(m, b.get("chat_id")) for m, b in calls]  # ушло в канал
        assert calls[-1][0] == "editMessageText" and calls[-1][1]["reply_markup"] == {"inline_keyboard": []}
        publish.save_draft("2026-10-26", "Пост", [], "шаблон")
        press(42, "rej:2026-10-26")
        assert publish.publish("2026-10-26", ["tg"], fake_post)[0] is False  # отклонённый не уходит
        publish.save_draft("2026-10-27", "Пост", ["выдумка"], "шаблон")
        publish.review("2026-10-27", fake_post)
        assert [b["text"] for b in calls[-1][1]["reply_markup"]["inline_keyboard"][0]] == ["✖️ Отклонить"]
        # рубрики не путаются: кнопка «Ночи в НХЛ» публикует её черновик, «Ночь наших» той же даты не трогает
        publish.save_draft("2026-10-28", "Лига", [], "шаблон", kind="league")
        publish.save_draft("2026-10-28", "Наши", [], "шаблон")
        assert press(42, "pub:league:2026-10-28").startswith("pub league")
        assert [b.get("text") for m, b in calls if m == "sendMessage"] == ["Лига"]
        assert publish.publish("2026-10-28", ["tg"], fake_post)[0]  # «Ночь наших» ещё не выходила
    finally:
        publish.OUT = old_out
        for k in ("NEWS_BOT_TOKEN", "NEWS_CHANNEL", "OWNER_CHAT_ID"):
            os.environ.pop(k, None)

    at, dl = time(9, 30), time(12, 0)
    msk = service.MSK
    assert service.due(datetime(2026, 10, 25, 9, 0, tzinfo=msk), {}, at, dl) is None  # рано
    assert service.due(datetime(2026, 10, 25, 9, 31, tzinfo=msk), {}, at, dl) == "2026-10-25"
    assert service.due(datetime(2026, 10, 25, 10, 0, tzinfo=msk), {"built": "2026-10-25"}, at, dl) is None
    later = datetime(2026, 10, 25, 10, 0, tzinfo=msk)
    assert service.due(later, {"next_try": later.timestamp() + 60}, at, dl) is None  # ждём повтора
    noon = datetime(2026, 10, 25, 12, 1, tzinfo=msk)
    assert service.due(noon, {"next_try": noon.timestamp() + 60}, at, dl) == "2026-10-25"  # дедлайн

    # состояние старого формата (одна рубрика) читается как «Ночь наших» — выкат не повторит пост
    old_state = service.STATE
    service.STATE = Path(tempfile.mkdtemp()) / "state.json"
    try:
        service.STATE.write_text('{"built": "2026-10-25"}', encoding="utf-8")
        assert service.load_state() == {"night": {"built": "2026-10-25"}}
    finally:
        service.STATE = old_state


def test_league_names_and_post():
    from news import names
    from news.digest import render_league
    from news.events import Event

    assert names.parse_label("Кучеров, Никита Игоревич (хоккеист)") == ("Никита", "Кучеров")
    assert names.parse_label("Немчинов Сергей Львович") == ("Сергей", "Немчинов")
    assert names.parse_label("Энтони Джеймс Эспозито") == ("Энтони", "Эспозито")
    assert names.parse_label("Майк Ван Рин") == ("Майк", "Ван Рин")
    assert names.parse_label("Sidney Crosby") is None

    rep = parse_box(BOX, None)  # вся лига: 999 тоже в отчёте
    assert {s.pid for s in rep.skaters} == {1, 2, 3, 999}
    league = {**PLAYERS, "999": {"ru": "Коннор Макдэвид", "surname": "Макдэвид", "status": "wikidata"}}
    hl = [(999, [Event(999, 55, "хет-трик")]), (1, [Event(1, 40, "победный гол")])]
    text, facts = render_league([rep], league, TEAMS, "2026-10-25", hl)
    assert text.startswith("🎩 <b>Макдэвид — хет-трик</b> · Вашингтон")
    assert "<b>Капризов</b> 2+1 · Миннесота" in text and "#НочьВНХЛ · 25 октября" in text
    assert guard.check(text, facts, league, TEAMS) == []
    # без русского имени игрока в посте нет — ни в событиях, ни в звёздах
    text, _ = render_league([rep], PLAYERS, TEAMS, "2026-10-25", hl)
    assert "999" not in text and "Макдэвид" not in text


def test_tonight():
    from news.digest import render_tonight
    from news.service import MSK

    games = [{"start": "2026-10-25T23:00:00Z", "home": "MIN", "away": "WSH"},
             {"start": "2026-10-26T00:30:00Z", "home": "TBL", "away": "NYR"}]
    ours = {"MIN": [(1, "Капризов")], "TBL": [(5, "Кучеров"), (4, "Шестёркин")]}
    # интриг нет — где больше всего наших; расписание по матчам — только на карточке
    text, facts = render_tonight(games, ours, TEAMS, "2026-10-25", MSK)
    assert text.startswith("📺 <b>Сегодня ночью в НХЛ</b> · 2 матча · 3 наших")
    assert "👀 Больше всего наших — <b>03:30</b> Тампа — Рейнджерс: 2" in text  # 00:30 UTC = 03:30 МСК
    assert "Миннесота" not in text
    assert guard.check(text, facts, PLAYERS, TEAMS) == []
    assert render_tonight([], {}, TEAMS, "2026-10-25", MSK)[0] == ""
    # интрига со временем матча; неиграющие — отдельными блоками
    items = [{"pid": 1, "rank": 0, "text": "🎯 <b>Капризов</b> — 2 гола до 250 в НХЛ", "numbers": ["2", "250"]}]
    text, facts = render_tonight(games, {"MIN": [(1, "Капризов")]}, TEAMS, "2026-10-25", MSK,
                                 {"TBL": [(5, "Кучеров", "травма"), (4, "Шестёркин", "не играл прошлый матч")]}, items)
    assert "🔥 <b>Интриги вечера</b>\n🎯 <b>Капризов</b> — 2 гола до 250 в НХЛ · 02:00" in text
    assert "🚑 <b>Не сыграют</b>\nКучеров — травма" in text
    assert "❔ <b>Под вопросом</b>\nШестёркин — не играл прошлый матч" in text
    assert guard.check(text, facts, PLAYERS, TEAMS) == []


def test_intrigue():
    from news import intrigue

    sk = {"position": "C", "careerTotals": {"regularSeason": {"goals": 248, "points": 494, "assists": 246,
                                                              "gamesPlayed": 409}},
          "last5Games": [{"gameTypeId": 2, "goals": 1, "points": 2}, {"gameTypeId": 2, "goals": 0, "points": 1},
                         {"gameTypeId": 2, "goals": 1, "points": 1}, {"gameTypeId": 2, "goals": 1, "points": 1},
                         {"gameTypeId": 2, "goals": 0, "points": 0}],
          "featuredStats": {"regularSeason": {"subSeason": {"gamesPlayed": 12, "goals": 12}}}}
    texts = [i["text"] for i in intrigue.player_items(1, "Капризов", sk)]
    assert texts == ["🎯 <b>Капризов</b> — 2 гола до 250 в НХЛ",
                     "🔥 <b>Капризов</b> набирает очки 4 матча подряд",
                     "📊 <b>Капризов</b> — 12 голов в 12 матчах сезона"]
    g = {"position": "G", "careerTotals": {"regularSeason": {"wins": 199, "shutouts": 30}},
         "last5Games": [{"gameTypeId": 2, "decision": "W"}] * 3 + [{"gameTypeId": 2, "decision": "L"}]}
    texts = [i["text"] for i in intrigue.player_items(4, "Шестёркин", g)]
    assert texts == ["🎯 <b>Шестёркин</b> — одна победа до 200 в НХЛ", "🥅 <b>Шестёркин</b> — 3 победы подряд"]
    items = intrigue.player_items(1, "Капризов", sk) + intrigue.player_items(4, "Шестёркин", g)
    assert [i["pid"] for i in intrigue.pick(items, {1, 4})] == [1, 4]  # по одной на игрока, важнейшие
    assert intrigue.pick(items, {4})[0]["pid"] == 4  # не в составе — без интриги


def test_tonight_recheck():
    import json
    import os
    import tempfile
    from datetime import datetime
    from pathlib import Path

    from news import publish, run
    from news.service import MSK

    roster = {"MIN": [{"pid": 1, "surname": "Капризов", "name": "Kirill Kaprizov", "played": True}],
              "TBL": [{"pid": 5, "surname": "Кучеров", "name": "Nikita Kucherov", "played": True},
                      {"pid": 4, "surname": "Шестёркин", "name": "Igor Shesterkin", "played": False}]}
    ours, skip = run.split_roster(roster, {"nikita kucherov": "Suspension"})
    assert ours == {"MIN": [(1, "Капризов")]}
    assert skip == {"TBL": [(5, "Кучеров", "дисквалификация"), (4, "Шестёркин", "не играл прошлый матч")]}

    games = [{"start": "2026-10-25T23:00:00Z", "home": "MIN", "away": "WSH"},
             {"start": "2026-10-26T00:30:00Z", "home": "TBL", "away": "NYR"}]
    old_out, old_load = publish.OUT, run.load
    publish.OUT = Path(tempfile.mkdtemp())
    run.load = lambda: ({"players": PLAYERS}, TEAMS)
    edits, notes = [], []
    old_edit, old_call = publish.edit_photo, publish.tg_call
    publish.edit_photo = lambda chat, mid, text, card: (edits.append((mid, text)), (True, "ок"))[1]
    publish.tg_call = lambda method, body: notes.append(body["text"]) or {"ok": True}
    try:
        publish.save_draft("2026-10-25", "пост", [], "шаблон", None, kind="tonight",
                           data={"games": games, "roster": roster, "out": {}})
        path = publish.draft_path("2026-10-25", "tonight")
        now = datetime(2026, 10, 26, 2, 30, tzinfo=MSK)  # Миннесота уже играет, Тампа — впереди
        assert run.refresh_tonight("2026-10-25", now, lambda url: {}) is None  # ещё не в канале — не трогаем
        d = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**d, "published": ["tg"], "messages": {"tg": [7]}}), encoding="utf-8")
        hurt = {"injuries": [{"injuries": [
            {"status": "Out", "athlete": {"displayName": "Nikita Kucherov"}},
            {"status": "Out", "athlete": {"displayName": "Kirill Kaprizov"}}]}]}  # его матч начался — не трогаем
        assert run.refresh_tonight("2026-10-25", now, lambda url: hurt) == "обновлено: не сыграют: Кучеров"
        assert edits[0][0] == 7 and "Кучеров — травма" in edits[0][1] and "Капризов" not in edits[0][1]
        assert "обновил пост" in notes[-1]
        assert run.refresh_tonight("2026-10-25", now, lambda url: hurt) == "состав без изменений"
        assert len(edits) == 1  # повтор без изменений — канал не трогаем
        later = datetime(2026, 10, 26, 4, 0, tzinfo=MSK)
        assert run.refresh_tonight("2026-10-25", later, lambda url: hurt) is None  # всё началось — не проверяем
    finally:
        publish.OUT, run.load, publish.edit_photo, publish.tg_call = old_out, old_load, old_edit, old_call
        os.environ.pop("OWNER_CHAT_ID", None)


def test_injuries_and_lineup():
    from news import injuries, nhl

    feed = {"injuries": [{"injuries": [
        {"status": "Injured Reserve", "athlete": {"displayName": "Alexander Romanov"}},
        {"status": "Day-To-Day", "athlete": {"displayName": "Kirill Kaprizov"}}]}]}
    out = injuries.injured(lambda url: feed)
    assert injuries.norm("Alexander  Romanov") in out and injuries.norm("Kirill Kaprizov") not in out
    assert injuries.injured(lambda url: (_ for _ in ()).throw(RuntimeError("нет сети"))) == {}

    schedule = {"games": [{"id": 1, "gameType": 2, "gameState": "OFF", "gameDate": "2026-10-22"},
                          {"id": 2, "gameType": 2, "gameState": "FUT", "gameDate": "2026-10-25"}]}

    def fetch(url):
        return schedule if "club-schedule" in url else BOX

    old = nhl.fetch_json
    nhl.fetch_json = fetch
    try:
        # в прошлом матче Миннесоты: полевой 1 и оба вратаря, включая сидевшего на скамейке 5
        assert nhl.last_lineup("MIN", "20262027", "2026-10-25") == {1, 4, 5}
    finally:
        nhl.fetch_json = old


def test_http_post_survives_network_errors():
    from unittest import mock

    from news import publish

    with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("read timed out")):
        r = publish.http_post("https://api.telegram.org/x", {}, {})
    assert r == {"ok": False, "description": "сеть: TimeoutError"}


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


def test_levels():
    import tempfile
    from pathlib import Path

    from news import levels

    calls = []
    lv = levels.Levels(-100, lambda m, b: calls.append((m, b)) or {"ok": True}, Path(tempfile.mkdtemp()) / "l.json")
    ann, bob = {"id": 1, "first_name": "Аня"}, {"id": 2, "first_name": "Боб"}

    def msg(mid, user, **kw):
        return {"message": {"message_id": mid, "chat": {"id": -100}, "from": user, "text": "шайба", **kw}}

    def react(mid, user, old=()):
        return {"message_reaction": {"chat": {"id": -100}, "message_id": mid, "user": user,
                                     "old_reaction": list(old), "new_reaction": [{"type": "emoji", "emoji": "🔥"}]}}

    for i in range(12):  # в зачёт только 10 сообщений в сутки
        lv.on_update(msg(i, ann))
    assert lv.points["1"] == 10
    assert ("setChatMemberTag", {"chat_id": -100, "user_id": 1, "tag": "Фарм"}) in calls
    assert calls[-1] == ("sendMessage", {"chat_id": -100, "text": "🌾 Аня — теперь «Фарм»"})
    lv.on_update(react(0, bob))
    lv.on_update(react(0, bob, old=[{"type": "emoji", "emoji": "🔥"}]))  # сменил реакцию — не второй раз
    lv.on_update(react(0, bob))  # снял и поставил снова — тоже нет
    lv.on_update(react(1, ann))  # своё сообщение
    assert lv.points["1"] == 12
    lv.on_update(msg(50, None, sender_chat={"id": -5}, is_automatic_forward=True))  # пост канала — мимо
    lv.on_update({"message": {"message_id": 51, "chat": {"id": -100}, "from": ann, "text": "/level"}})
    assert calls[-1][1]["text"] == "🌾 «Фарм» · 12 баллов · до «Дебютант» — 38"
    assert levels.Levels(-100, lambda m, b: {}, lv.path).points == {"1": 12}  # пережило рестарт
    assert levels.level(9) is None and levels.level(1000)[1] == "Капитан"
    assert all(len(name) <= 16 for _, name, _ in levels.LEVELS)  # лимит тега Telegram


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"news: {len(tests)} тестов — ок")
