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
    assert "🥅 Шестёркин — 30 сейвов из 33 (90,9%), победа" in text
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
    assert blocks[5] == "🥅 <b>Шестёркин</b> 30 из 33 (90,9%) · Миннесота, победа"
    from news.digest import save_pct
    f = {"numbers": set()}
    assert save_pct(27, 27, f) == "100%" and save_pct(18, 23, f) == "78,3%" and f["numbers"] == {100, 78, 3}
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

    # хук: играет наш полевой — «кто из наших забьёт»; только вратари или никого — прогноз на матч
    from news.digest import tonight_hook
    assert tonight_hook(games, {"TBL": [(5, "Кучеров")]}, set(), TEAMS)[0].startswith("💬 Кто из наших забьёт")
    line, used = tonight_hook(games, {"TBL": [(4, "Шестёркин")]}, {4}, TEAMS)
    assert line == "💬 Ваш прогноз на матч Тампа — Рейнджерс? Пишите в комментариях" and used == ["Тампа", "Рейнджерс"]
    assert "наших" not in tonight_hook(games, {}, set(), TEAMS)[0]
    text, facts = render_tonight(games, {}, TEAMS, "2026-10-25", MSK, hook=(line, used))
    assert line in text and guard.check(text, facts, PLAYERS, TEAMS) == []


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
    assert ("setChatMemberTag", {"chat_id": -100, "user_id": 1, "tag": "Проспект"}) in calls  # с 3 баллов
    assert ("setChatMemberTag", {"chat_id": -100, "user_id": 1, "tag": "Фарм"}) in calls
    assert calls[-1] == ("sendMessage", {"chat_id": -100, "text": "🌾 Аня — теперь «Фарм»"})
    lv.on_update(react(0, bob))
    lv.on_update(react(0, bob, old=[{"type": "emoji", "emoji": "🔥"}]))  # сменил реакцию — не второй раз
    lv.on_update(react(0, bob))  # снял и поставил снова — тоже нет
    lv.on_update(react(1, ann))  # своё сообщение
    assert lv.points["1"] == 12
    lv.on_update(msg(50, None, sender_chat={"id": -5}, is_automatic_forward=True))  # пост канала — мимо
    lv.on_update({"message": {"message_id": 51, "chat": {"id": -100}, "from": ann, "text": "/level"}})
    assert calls[-1][1]["text"] == "🌾 «Фарм» · 12 баллов · до «Основа» — 18"
    assert levels.Levels(-100, lambda m, b: {}, lv.path).points == {"1": 12}  # пережило рестарт
    own = levels.Levels(-100, lambda m, b: {}, Path(tempfile.mkdtemp()) / "o.json", skip={1})
    own.on_update(msg(60, ann))
    assert own.points == {}  # владельцу баллы не идут
    assert levels.level(2) is None and levels.level(300)[1] == "Капитан" and levels.level(1000)[1] == "Легенда"
    assert all(len(name) <= 16 for _, name, _ in levels.LEVELS)  # лимит тега Telegram


def test_stories():
    import json
    import tempfile
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    from news import publish, stories

    k = stories.kind_of
    assert k("Reimer signs one-year contract with Rangers, returns to NHL at age 38") == "signing"
    assert k("Hellebuyck Acquired by Devils | RELEASE") == "trade"
    assert k("RELEASE: Blackhawks Activate Andrew Mangiapane From Injured Reserve") == "return"
    assert k("NHL Status Report: McCann out 10 weeks for Kraken") == "injury"
    assert k("Capitals Claim Defenseman Jack St. Ivany") == "claim"
    assert k("INSIDER: Alex Laferriere Staking His Claim On First Line") is None
    assert k("Jets get ‘relief’ with Hellebuyck trade, begin new era") is None  # разбор, не событие
    assert k("Predators Assign Jack Ahcan to Milwaukee (AHL)") == "assign"

    now = datetime(2026, 10, 25, 17, 0, tzinfo=timezone.utc)

    def item(eid, headline, tags, minutes_ago, summary=""):
        return {"_entityId": eid, "slug": eid, "headline": headline, "summary": summary,
                "contentDate": (now - timedelta(minutes=minutes_ago)).isoformat(), "selfUrl": f"u/{eid}",
                "tags": [{"slug": t} for t in tags] + [{"slug": "teamid-3", "extraData": {"abbreviation": "NYR"}}]}

    assert stories.parse_item(item("x", "INSIDER: Reimer signs", ["lak-insider"], 5)) is None
    assert stories.parse_item(item("x", "Rangers recap: Reimer signs", ["game-recap"], 5)) is None
    team = stories.parse_item(item("pr", "Rangers Agree to Terms with James Reimer", ["press-release"], 40))
    nhl = stories.parse_item(item("nhl", "Reimer signs one-year contract with Rangers",
                                  ["nhl-created", "playerid-8473503"], 20))
    minor = stories.parse_item(item("ah", "Rangers Assign Some Guy to Hartford", ["playerid-1"], 90))
    ours = stories.parse_item(item("rc", "Rangers recall Matvei Michkov", ["press-release"], 90))
    assert stories.same_event(team, nhl)  # клуб без тега игрока, но общий клуб и «Reimer» в заголовке
    state = {"since": (now - timedelta(hours=6)).isoformat(), "seen": {}}
    got = stories.select([team, nhl, minor, ours], state, now, {4}, {"Matvei Michkov": 4})
    assert [s.eid for s in got] == ["rc", "nhl"]  # текст NHL.com вместо релиза; мелочь не нашего — мимо
    assert "ah" in state["seen"] and "pr" not in state["seen"]
    state["seen"].update({"rc": now.isoformat(), "nhl": now.isoformat()})
    assert stories.select([team, nhl], state, now, set(), {}) == [] and "pr" in state["seen"]  # дубль

    # травма/возвращение не нашего — только заметного игрока; сводка NHL.com — всегда
    ir = stories.parse_item(item("ir", "LA Kings Place Forward Mats Zuccarello On Injured Reserve",
                                 ["press-release", "playerid-777"], 90))
    back = stories.parse_item(item("st", "NHL Status Report: Hall activated by Hurricanes", ["nhl-created"], 90))
    st2 = {"since": (now - timedelta(hours=6)).isoformat(), "seen": {}}
    assert [s.eid for s in stories.select([ir, back], st2, now, set(), {}, lambda p: p == 777)] == ["ir", "st"]
    st3 = {"since": (now - timedelta(hours=6)).isoformat(), "seen": {}}
    assert [s.eid for s in stories.select([ir], st3, now, set(), {}, lambda p: False)] == [] and "ir" in st3["seen"]
    star = {"featuredStats": {"regularSeason": {"career": {"points": 700}, "subSeason": {"points": 10}}}}
    rookie = {"featuredStats": {"regularSeason": {"career": {"points": 20}, "subSeason": {"points": 20}}}}
    goalie = {"position": "G", "featuredStats": {"regularSeason": {"subSeason": {"gamesPlayed": 45}}}}
    assert stories.is_notable(star) and not stories.is_notable(rookie) and stories.is_notable(goalie)

    alone = stories.parse_item(item("solo", "Rangers Agree to Terms with Someone", ["press-release"], 10))
    later = stories.select([alone], {"since": state["since"], "seen": {}}, now, set(), {})
    assert later == []  # релиз клуба ждёт текст NHL.com час
    assert [s.eid for s in stories.select([alone], {"since": state["since"], "seen": {}},
                                          now + timedelta(hours=1), set(), {})] == ["solo"]

    names = {"8473503": {"ru": "Джеймс Раймер", "surname": "Раймер"}, "4": PLAYERS["4"]}
    nhl.text = "He signed a one-year, $850,000 contract. Igor Shesterkin is out for the season."
    nhl.mentioned = {4}
    reg = {"4": PLAYERS["4"], "5": PLAYERS["5"]}
    good = ("Раймер подписал контракт с Рейнджерс\n\nКонтракт на 1 год и 850 тысяч долларов. "
            "Шестёркин выбыл до конца сезона.")
    assert stories.check(good, nhl, names, reg, TEAMS, {4, 5}) == ([], [])
    issues, _ = stories.check(good.replace("850", "900") + " Кучеров рад. Tampa", nhl, names, reg, TEAMS, {4, 5})
    assert any("числа не из данных: 900" in i for i in issues) and any("Кучеров" in i for i in issues)
    assert "латиница в тексте" in issues
    issues, _ = stories.check("Рейнджерс подписали вратаря\n\nНа 1 год.", nhl, names, reg, TEAMS, {4, 5})
    assert "не назван герой новости: Джеймс Раймер" in issues and "потерян игрок: Игорь Шестёркин" in issues
    _, notes = stories.check(good + " Его хвалил Дрюри.", nhl, names, reg, TEAMS, {4, 5})
    assert notes and "Дрюри" in notes[0]  # незнакомое имя — не запрет, а «проверь глазами»

    assert stories.clean("Заголовок: Раймер вернулся\n\nТекст: Он подписал.") == "Раймер вернулся\n\nОн подписал."
    assert stories.clean("одна строка") is None
    post = stories.render(nhl, "Раймер вернулся\n\nОн подписал.", "2026-10-25")
    assert post.startswith("✍️ <b>Раймер вернулся</b>\n\nОн подписал.")
    assert post.endswith("NHL.com</a>\n⚡ #Контракты · 25 октября") and "nhl.com/news/nhl" in post

    landing = {"8473503": {"position": "G", "featuredStats": {"season": 20252026, "regularSeason": {"subSeason": {
        "gamesPlayed": 14, "goalsAgainstAvg": 2.421179, "savePctg": 0.885813}}}},
        "4": {"position": "G", "featuredStats": {"season": 20262027, "regularSeason": {"subSeason": {}}}}}
    goalies = stories.goalie_stats(nhl, names, {4}, lambda url: landing[url.split("/")[-2]])
    lines = [stories.goalie_line(g) for g in goalies]
    assert lines == ["🥅 <b>Раймер</b> · 2025/26: 14 матчей, КН 2,42, %ОБ 88,6"]  # без матчей в сезоне — без строки
    assert "%ОБ 88,6\n\n🔗" in stories.render(nhl, "З\n\nТ", "2026-10-25", lines)
    assert stories.hero_of(nhl, names, {4}) == 8473503
    pic = stories.card(nhl, "Раймер подписал контракт с Рейнджерс\n\nТекст", names, {4}, goalies, TEAMS,
                       "2026-10-25", Path(tempfile.mkdtemp()) / "c.png")
    from PIL import Image
    assert Image.open(pic).size == (1080, 1350)

    # полный проход: черновик сохранён и отдан на доставку; гард не прошёл — владелец узнаёт о новости
    out = Path(tempfile.mkdtemp())
    publish.OUT, stories.STATE = out, out / "stories_state.json"
    stories.save_state({"since": (now - timedelta(hours=6)).isoformat(), "seen": {}})
    feed = {"items": [item("nhl", "Reimer signs one-year contract with Rangers", ["nhl-created", "playerid-8473503"],
                           20)]}
    tagged = '<forge-entity slug="igor-shesterkin-0000004" code="player">Igor Shesterkin</forge-entity>'
    full = {"parts": [{"type": "markdown", "content": nhl.text.replace("Igor Shesterkin", tagged)}]}
    fetch = lambda url: feed if url == stories.FEED else full  # noqa: E731
    sent, told = [], []

    def run(answer):
        def write(prompt, accept):
            assert "Джеймс Раймер" in prompt("claude_cli") and "Игорь Шестёркин" in prompt("claude_cli")
            text = stories.clean(answer)
            return (text, "fake", []) if not accept(text) else (None, "шаблон", ["fake: отклонена"])
        return stories.process(now, fetch, reg, TEAMS, lambda p, r: names, write, lambda: [],
                               lambda msk, kind: sent.append(kind) or "ок", told.append)

    log = run(good)
    assert sent == ["story-nhl"] and "(signing): ок" in log[0]
    d = json.loads(publish.draft_path("2026-10-25", "story-nhl").read_text(encoding="utf-8"))
    assert d["issues"] == [] and d["data"]["auto"] and "⚡ #Контракты" in d["text"]
    assert run(good) == []  # второй проход: новость уже видели
    stories.save_state({"since": (now - timedelta(hours=6)).isoformat(), "seen": {}})
    run(good.replace("850", "900"))
    assert told and "Инфоповод без поста" in told[0] and len(sent) == 1
    assert publish.title("story-nhl") == "«Инфоповод»" and publish.title("night") == "«Ночь наших»"


def test_guard_mentions():
    from news.guard import mentions
    # 26.10.2026: «Джонс» находился внутри «Джонстон» — «Ночь в НХЛ» не вышла
    assert not mentions("Джонстон — победный гол", "Джонс") and mentions("гол Джонса", "Джонс")
    for text, word in (("над Тампой", "Тампа"), ("Монреалем", "Монреаль"), ("Ковалёвского", "Ковалёвский"),
                       ("Кучеровым", "Кучеров"), ("Лос-Анджелесом", "Лос-Анджелес"), ("братья Протасы", "Протас")):
        assert mentions(text, word), (text, word)
    assert not mentions("Ивановский", "Иванов") and not mentions("Ковальчук", "Коваль")


def test_night_card_rows():
    from news.card import player_rows
    rows, idle = player_rows([parse_box(BOX, {1, 2, 3, 4, 5})], {1: "Капризов", 2: "И. Протас", 3: "А. Протас",
                                                                 4: "Шестёркин", 5: "Кучеров"})
    assert rows[0] == ("MIN", "Капризов", "2+1", "победа 4:3 ОТ", True)
    assert rows[1] == ("WSH", "И. Протас", "1+0", "поражение 3:4 ОТ", True)
    assert rows[2] == ("MIN", "Шестёркин", "30/33", "90,9% · победа 4:3 ОТ", False)
    assert idle == ["А. Протас"]


def test_registry():
    import json
    import tempfile
    from pathlib import Path

    from news import publish, registry

    base = Path(tempfile.mkdtemp()) / "players.json"
    base.write_text(json.dumps({"_meta": {}, "players": {
        "8000001": {"ru": "Игорь Шестёркин", "surname": "Шестёркин", "country": "RUS", "status": "confirmed"},
        "8000002": {"ru": "Иван Уехавший", "surname": "Уехавший", "country": "RUS", "status": "confirmed"},
    }}), encoding="utf-8")
    registry.BASE, publish.OUT = base, Path(tempfile.mkdtemp())
    p = lambda pid, first, last, c="RUS": {"id": pid, "firstName": {"default": first},  # noqa: E731
                                          "lastName": {"default": last}, "birthCountry": c}
    rosters = {"NYR": {"goalies": [p(8000001, "Igor", "Shesterkin")], "forwards": [p(9, "Joe", "Canadian", "CAN")]},
               "CAR": {"defensemen": [p(8000003, "Alexander", "Nikishin")]}}
    landing = {"8000002": {}}  # клуба НХЛ нет — уехал

    def fetch(url):
        if "/roster/" in url:
            return rosters[url.split("/")[-2]]
        return landing[url.split("/")[-2]]

    wiki = {"8000003": "Александр Никишин"}
    report = registry.audit(fetch, ["NYR", "CAR"], lambda: [], wiki, "2026-10-26")
    assert report == ["➕ Александр Никишин (CAR)", "➖ Иван Уехавший: вне НХЛ (был без клуба)"]
    reg = registry.load()["players"]
    assert reg["8000003"]["surname"] == "Никишин" and reg["8000003"]["status"] == "wikidata"
    assert reg["8000001"]["team"] == "NYR" and reg["8000002"]["team"] is None
    assert reg["8000002"]["ru"] == "Иван Уехавший"  # запись не удаляем — вдруг вернётся

    assert registry.audit(fetch, ["NYR", "CAR"], lambda: [], wiki, "2026-10-27") == []  # ничего не менялось
    rosters["NYR"]["goalies"], rosters["CAR"]["goalies"] = [], [p(8000001, "Igor", "Shesterkin")]
    assert registry.audit(fetch, ["NYR", "CAR"], lambda: [], wiki, "2026-10-28") == ["🔁 Игорь Шестёркин: NYR → CAR"]
    assert registry.audit(lambda url: (_ for _ in ()).throw(RuntimeError("нет сети")), ["NYR"], lambda: [], wiki,
                          "2026-10-29") == []  # API лёг — никого «вне НХЛ» не объявляем

    landing["8000004"] = {"birthCountry": "BLR", "firstName": {"default": "New"}, "lastName": {"default": "Guy"},
                          "currentTeamAbbrev": "SEA"}
    landing["8000005"] = {"birthCountry": "CAN"}
    lines, records = registry.from_story({8000004, 8000005, 8000001}, fetch, {}, "2026-10-29")
    assert lines == ["➕ New Guy (SEA) — из инфоповода — нет русского имени: /name 8000004 Имя Фамилия"]
    assert set(records) == {"8000004"} and records["8000004"]["ru"] is None
    assert "8000004" in registry.load()["players"]

    assert registry.owner_command("привет") is None
    assert registry.owner_command("/name 8000004 new guy").startswith("Формат")
    assert registry.owner_command("/name 8000004 Новый Парень").startswith("✅")
    rec = registry.load()["players"]["8000004"]
    assert (rec["ru"], rec["surname"], rec["status"]) == ("Новый Парень", "Парень", "confirmed")


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"news: {len(tests)} тестов — ок")
