"""CLI новостника «Культура хоккея». Сервис публикует сам при чистом гарде (NEWS_AUTO_PUBLISH=1).

    python -m news.run night [--date YYYY-MM-DD] [--llm [chain]] [--review]  # «Ночь наших» (МСК)
    python -m news.run league [--date YYYY-MM-DD] [--review]                 # «Ночь в НХЛ» — вся лига
    python -m news.run publish [--date YYYY-MM-DD] [--to tg,max] [--kind night|league]  # черновик → каналы
    python -m news.run sync-registry                       # новые наши из НХЛ → реестр со status=new
    python -m news.run sync-names                          # русские имена всей лиги из Wikidata
    python -m news.run serve                               # сервис: сбор по утрам + кнопки в личке

Черновики и отчёт гарда пишутся в news/out/ (в git не попадает). Секреты — news/.env.
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from news import events, guard, injuries, intrigue, levels, names, nhl, publish, service, stories
from news.card import render_card, render_tonight_card
from news.digest import NOT_PLAYED, render_caption, render_league, render_night, render_tonight, tonight_hook
from news.llm import ask, lead

ROOT = Path(__file__).parent
PLAYERS = ROOT / "data" / "players.json"
TEAMS = ROOT / "data" / "teams.json"
SEASON = "20262027"


def load():
    return json.loads(PLAYERS.read_text(encoding="utf-8")), json.loads(TEAMS.read_text(encoding="utf-8"))


def build_night(msk: str, chain: str | None, review: bool, last_try: bool = True) -> str:
    """Собрать выпуск даты (МСК) → "ok" | "nogames" | "pending" | "guard" (гард нашёл проблемы).
    chain=None — без модели, "" — цепочка из NEWS_LLM. last_try=False и матчи ещё идут → "pending"."""
    reg, teams = load()
    players = {k: v for k, v in reg["players"].items() if v.get("ru")}
    # Утро по Москве = вечер предыдущей даты в Северной Америке.
    nhl_date = (date.fromisoformat(msk) - timedelta(days=1)).isoformat()
    if not last_try and nhl.pending_games(nhl_date):
        return "pending"

    reports = nhl.collect_night(nhl_date, {int(p) for p in players})
    try:
        highlights = events.headline(events.detect(reports, events.context(reports)))
    except RuntimeError as e:  # нет событий — не повод молчать: «Главное» выберется по очкам
        print(f"  ↳ события не собраны: {e}")
        highlights = []
    text, facts = render_night(reports, players, teams, msk, highlights)
    if not text:
        print(f"{msk}: наши не играли (НХЛ {nhl_date}) — поста нет")
        return "nogames"

    variant, phrase = "шаблон", None
    if chain is not None:
        phrase, source, log = lead(text, lambda p: guard.check_lead(p, facts, players, teams), chain=chain or None)
        for line in log:
            print(f"  ↳ {line}")
        if phrase:
            variant = f"шаблон + вводная {source}"
    # Модели дали полный текст по матчам (render_night) — ей нужен контекст. В канал идёт подпись
    # к карточке: счёт матчей на картинке, в тексте сюжет и очки наших.
    final, facts = render_caption(reports, players, teams, msk, highlights, phrase)
    if publish.visible_len(final) > publish.CAPTION_LIMIT:  # не влезает в подпись — без клубов в скобках
        final, facts = render_caption(reports, players, teams, msk, highlights, phrase, with_teams=False)
        variant += " · компактно"
    issues = guard.check(final, facts, players, teams)

    card = render_card(reports, players, teams, msk, publish.OUT / f"{msk}_night.png", highlights)
    path = publish.save_draft(msk, final, issues, variant, str(card))
    print(final, "\n")
    print(f"— вариант: {variant} · матчей: {len(reports)} · гард: {'чисто' if not issues else '; '.join(issues)}")
    print(f"— черновик: {path}")
    if review and not issues and os.environ.get("NEWS_AUTO_PUBLISH") == "1":
        ok, info = publish.auto_publish(msk)
        print(f"— автопубликация: {'ок' if ok else 'ошибка'} — {info}")
    elif review:  # гард не чист или автопубликация выключена — черновик владельцу с кнопками
        ok, info = publish.review(msk)
        print(f"— владельцу в личку: {'ок' if ok else 'ошибка'} — {info}")
    return "guard" if issues else "ok"


def build_league(msk: str, review: bool, last_try: bool = True) -> str:
    """«Ночь в НХЛ»: все матчи, события всей лиги. Без вводной от модели — промпт под лигу ещё не прогнан
    через eval. В посте только игроки с русским именем (наш реестр или Wikidata)."""
    reg, teams = load()
    nhl_date = (date.fromisoformat(msk) - timedelta(days=1)).isoformat()
    if not last_try and nhl.pending_games(nhl_date):
        return "pending"
    reports = nhl.collect_night(nhl_date, None)
    if not reports:
        print(f"{msk}: в НХЛ матчей не было ({nhl_date}) — поста нет")
        return "nogames"
    pids = {ln.pid for r in reports for ln in r.skaters + r.goalies}
    players = names.league_players(pids, reg["players"])
    try:
        found = [e for e in events.detect(reports, events.context(reports)) if str(e.pid) in players]
        highlights = events.headline(found, limit=5)
    except RuntimeError as e:
        print(f"  ↳ события не собраны: {e}")
        highlights = []
    text, facts = render_league(reports, players, teams, msk, highlights)
    issues = guard.check(text, facts, players, teams)
    card = render_card(reports, players, teams, msk, publish.OUT / f"{msk}_league.png", highlights, league=True)
    path = publish.save_draft(msk, text, issues, "шаблон", str(card), kind="league")
    print(text, "\n")
    print(f"— матчей: {len(reports)} · с русским именем {len(players)} из {len(pids)} · "
          f"гард: {'чисто' if not issues else '; '.join(issues)}\n— черновик: {path}")
    if review and not issues and os.environ.get("NEWS_AUTO_PUBLISH") == "1":
        ok, info = publish.auto_publish(msk, kind="league")
        print(f"— автопубликация: {'ок' if ok else 'ошибка'} — {info}")
    elif review:
        ok, info = publish.review(msk, kind="league")
        print(f"— владельцу в личку: {'ок' if ok else 'ошибка'} — {info}")
    return "guard" if issues else "ok"


MSK = ZoneInfo("Europe/Moscow")
# статус ESPN → пометка в посте; «Day-To-Day» в injuries.OUT не входит — такие часто играют
WHY = {"Injured Reserve": "травма", "Long Term Injured Reserve": "травма", "Out": "травма",
       "Suspension": "дисквалификация"}


def tonight_roster(teams_playing: set[str], players: dict, msk: str) -> dict[str, list[dict]]:
    """Наши в клубах вечера и сыграл ли каждый в прошлом матче клуба. Дорогая часть (2 запроса на клуб),
    поэтому один раз при сборке: до сегодняшних матчей прошлый матч не меняется."""
    lineups = {t: nhl.last_lineup(t, SEASON, msk) for t in teams_playing}
    roster: dict[str, list[dict]] = {}
    for p in nhl.fetch_nationals(SEASON):
        rec = players.get(str(p["pid"]))
        if rec and p.get("team") in teams_playing:
            roster.setdefault(p["team"], []).append({"pid": p["pid"], "surname": rec["surname"],
                                                     "name": p["name"], "played": p["pid"] in lineups[p["team"]],
                                                     "goalie": p.get("goalie", False)})
    return roster


def split_roster(roster: dict[str, list[dict]], out: dict[str, str]) -> tuple[dict, dict]:
    """→ (наши в составах, не сыграют с причиной). Статистика сезона одна не годится: Романов и Демидов
    на травме, а 25.10.2026 попали в пост (замечание владельца). Теперь такие — с пометкой, не пропадают."""
    ours: dict[str, list[tuple[int, str]]] = {}
    skip: dict[str, list[tuple[int, str, str]]] = {}
    for team, recs in roster.items():
        for r in recs:
            status = out.get(injuries.norm(r["name"]))
            if status:
                skip.setdefault(team, []).append((r["pid"], r["surname"], WHY.get(status, "травма")))
            elif not r["played"]:
                skip.setdefault(team, []).append((r["pid"], r["surname"], NOT_PLAYED))
            else:
                ours.setdefault(team, []).append((r["pid"], r["surname"]))
    return ours, skip


def render_tonight_post(games: list[dict], ours: dict, skip: dict, players: dict, teams: dict, msk: str,
                        items: list[dict], roster: dict):
    playing = {pid for recs in ours.values() for pid, _ in recs}
    goalies = {r["pid"] for recs in roster.values() for r in recs if r.get("goalie")}
    text, facts = render_tonight(games, ours, teams, msk, MSK, skip, intrigue.pick(items, playing),
                                 tonight_hook(games, ours, goalies, teams))
    issues = guard.check(text, facts, players, teams) if text else []
    card = render_tonight_card(games, ours, teams, msk, MSK, publish.OUT / f"{msk}_tonight.png") \
        if text else None
    return text, issues, card


def build_tonight(msk: str, review: bool) -> str:
    """«Сегодня ночью»: матчи НХЛ, которые ещё не начались, по московскому времени, и наши в составах.
    Вечер по Москве = та же дата в Северной Америке. Травмы потом перепроверяет refresh_tonight."""
    reg, teams = load()
    games = nhl.upcoming_games(msk)
    players = {k: v for k, v in reg["players"].items() if v.get("ru")}
    roster = tonight_roster({t for g in games for t in (g["home"], g["away"])}, players, msk)
    out = injuries.injured()
    ours, skip = split_roster(roster, out)
    # один запрос на нашего в составе + таблица — только при сборке, перепроверка их не повторяет
    items = intrigue.collect(ours) + intrigue.team_items({t for g in games for t in (g["home"], g["away"])}, teams)
    text, issues, card = render_tonight_post(games, ours, skip, players, teams, msk, items, roster)
    if not text:
        print(f"{msk}: матчей впереди нет — поста нет")
        return "nogames"
    path = publish.save_draft(msk, text, issues, "шаблон", str(card), kind="tonight",
                              data={"games": games, "roster": roster, "out": out, "items": items})
    print(text, f"\n\n— гард: {'чисто' if not issues else '; '.join(issues)}\n— черновик: {path}")
    if review and not issues and os.environ.get("NEWS_AUTO_PUBLISH") == "1":
        ok, info = publish.auto_publish(msk, kind="tonight")
        print(f"— автопубликация: {'ок' if ok else 'ошибка'} — {info}")
    elif review:
        ok, info = publish.review(msk, kind="tonight")
        print(f"— владельцу в личку: {'ок' if ok else 'ошибка'} — {info}")
    return "guard" if issues else "ok"


def refresh_tonight(msk: str, now: datetime, fetch=None) -> str | None:
    """Перепроверка вышедшей «Сегодня ночью»: травмы объявляют днём и вечером. Один запрос к ESPN, без
    повторного обхода клубов; клубы, чей матч уже начался, не трогаем. Изменилось — правим пост в канале
    (editMessageMedia), владельцу отчёт. → строка для лога или None, если проверять нечего."""
    path = publish.draft_path(msk, "tonight")
    if not path.exists():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    data, mids = d.get("data"), d.get("messages", {}).get("tg")
    if not data or "roster" not in data or not mids or "tg" not in d.get("published", []):
        return None
    if len(mids) > 1:  # подпись не влезла и ушла отдельным текстом — правкой картинки не обновить
        return None
    games, roster, old_out = data["games"], data["roster"], data["out"]
    soon = {t for g in games if datetime.fromisoformat(g["start"].replace("Z", "+00:00")) > now
            for t in (g["home"], g["away"])}
    if not soon:
        return None
    fresh = injuries.injured(fetch) if fetch else injuries.injured()
    if not fresh:  # ESPN не ответил — не путаем «нет данных» с «все выздоровели»
        return "травмы недоступны"
    names = {injuries.norm(r["name"]) for t in soon for r in roster.get(t, [])}
    out = {k: v for k, v in old_out.items() if k not in names} | {k: v for k, v in fresh.items() if k in names}
    old_ours, old_skip = split_roster(roster, old_out)
    ours, skip = split_roster(roster, out)
    if ours == old_ours and skip == old_skip:
        return "состав без изменений"
    was = {s for v in old_ours.values() for _, s in v}
    now_in = {s for v in ours.values() for _, s in v}
    change = "; ".join(x for x in ("не сыграют: " + ", ".join(sorted(was - now_in)) if was - now_in else "",
                                   "вернулись: " + ", ".join(sorted(now_in - was)) if now_in - was else "") if x) \
        or "сменилась причина"
    reg, teams = load()
    players = {k: v for k, v in reg["players"].items() if v.get("ru")}
    text, issues, card = render_tonight_post(games, ours, skip, players, teams, msk, data.get("items", []), roster)
    owner = os.environ.get("OWNER_CHAT_ID", "")
    if issues:
        publish.tg_call("sendMessage", {"chat_id": owner, "text": f"⚠️ «Сегодня ночью»: состав изменился ({change}), "
                                        "но гард не пропустил правку — пост не тронут"})
        return f"гард: {'; '.join(issues)}"
    ok, info = publish.edit_photo(os.environ.get("NEWS_CHANNEL", ""), mids[0], text, str(card))
    if not ok:
        return f"правка не прошла: {info}"
    d.update(text=text, card=str(card), data={**data, "out": out})
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    publish.tg_call("sendMessage", {"chat_id": owner, "text": f"🔄 «Сегодня ночью»: обновил пост — {change}"})
    return f"обновлено: {change}"


def cmd_tonight(args) -> int:
    msk = args.date or datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    return 1 if build_tonight(msk, args.review) == "guard" else 0


def cmd_league(args) -> int:
    msk = args.date or datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    return 1 if build_league(msk, args.review) == "guard" else 0


def cmd_sync_names(_args) -> int:
    print(f"Русских имён из Wikidata: {names.sync()} → {names.FILE}")
    return 0


def cmd_night(args) -> int:
    msk = args.date or datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    return 1 if build_night(msk, args.llm, args.review) == "guard" else 0


def run_stories(now: datetime) -> list[str]:
    """Проход по ленте NHL.com. Черновики владельцу, пока не включена NEWS_STORIES_AUTO=1:
    рубрика новая, гард пересказа ещё не обкатан на живых новостях."""
    reg, teams = load()
    registry = {k: v for k, v in reg["players"].items() if v.get("ru")}
    owner = os.environ.get("OWNER_CHAT_ID", "")

    def write(prompt, accept):
        return ask(prompt, accept, stories.clean)

    def deliver(msk: str, kind: str) -> str:
        d = json.loads(publish.draft_path(msk, kind).read_text(encoding="utf-8"))
        if os.environ.get("NEWS_STORIES_AUTO") == "1" and d["data"].get("auto"):
            ok, info = publish.auto_publish(msk, kind=kind)
        else:
            ok, info = publish.review(msk, kind=kind)
        return f"{'ок' if ok else 'ошибка'} — {info}"

    def notify(text: str) -> None:
        publish.tg_call("sendMessage", {"chat_id": owner, "text": text, "link_preview_options": {"is_disabled": True}})

    return stories.process(now, nhl.fetch_json, registry, teams, names.league_players, write,
                           lambda: nhl.fetch_nationals(SEASON), deliver, notify)


def cmd_stories(args) -> int:
    now = datetime.now(MSK)
    if args.since:  # ручной прогон: взять новости за последние N часов, даже если сервис их уже видел
        state = stories.load_state(now)
        state["since"] = (now - timedelta(hours=args.since)).isoformat()
        state["seen"] = {}
        stories.save_state(state)
    for line in run_stories(now):
        print(line)
    return 0


def discussion_levels():
    """Уровни в чате обсуждений канала; чат не привязан или Telegram не ответил — без уровней."""
    chat_id = publish.tg_call("getChat", {"chat_id": os.environ.get("NEWS_CHANNEL", "")}) \
        .get("result", {}).get("linked_chat_id")
    if not chat_id:
        print("уровни: чат обсуждений не найден — выключены", flush=True)
        return None
    print(f"уровни: чат обсуждений {chat_id}", flush=True)
    owner = int(os.environ.get("OWNER_CHAT_ID") or 0)
    return levels.Levels(chat_id, skip={owner}).on_update


def cmd_serve(_args) -> int:
    # гард не чист — черновик всё равно у владельца (без кнопки «Опубликовать»), день закрыт
    def night(msk: str, last_try: bool) -> str:
        result = build_night(msk, "", True, last_try)
        return "ok" if result == "guard" else result

    def league(msk: str, last_try: bool) -> str:
        result = build_league(msk, True, last_try)
        return "ok" if result == "guard" else result

    def tonight(msk: str, _last_try: bool) -> str:
        result = build_tonight(msk, True)
        return "ok" if result == "guard" else result

    def recheck(now: datetime) -> list[str]:
        # матчи западного побережья начинаются до 06:00 МСК — после полуночи пост ещё вчерашний
        dates = [(now - timedelta(days=k)).date().isoformat() for k in (0, 1)]
        return [f"перепроверка {msk}: {r}" for msk in dates if (r := refresh_tonight(msk, now))]

    service.run_forever([("league", "NEWS_LEAGUE_AT", "09:00", league),
                         ("night", "NEWS_REVIEW_AT", "09:30", night),
                         ("tonight", "NEWS_TONIGHT_AT", "18:00", tonight)],
                        ticks=[(int(os.environ.get("NEWS_RECHECK_MIN", "30")) * 60, recheck),
                               (int(os.environ.get("NEWS_STORIES_MIN", "15")) * 60, run_stories)],
                        chat=discussion_levels())
    return 0


def cmd_publish(args) -> int:
    msk = args.date or datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    ok, report = publish.publish(msk, args.to.split(","), kind=args.kind)
    print("\n".join(report))
    return 0 if ok else 1


def cmd_sync(_args) -> int:
    reg, _ = load()
    added = []
    for p in nhl.fetch_nationals(SEASON):
        key = str(p["pid"])
        if key not in reg["players"]:
            reg["players"][key] = {"ru": None, "surname": None, "country": p["country"], "status": "new",
                                   "en": p["name"]}
            added.append(f"{p['name']} ({p['team']}, {p['country']})")
    if added:
        reg["_meta"]["updated"] = date.today().isoformat()
        PLAYERS.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Новые в реестре (нужно русское написание):\n  " + "\n  ".join(added) if added else "Новых нет")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="news.run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("night")
    n.add_argument("--date", help="дата поста по МСК, по умолчанию сегодня")
    n.add_argument("--llm", nargs="?", const="", default=None,
                   help="вводная фраза от модели; цепочка провайдеров через запятую, по умолчанию NEWS_LLM")
    n.add_argument("--review", action="store_true", help="отправить черновик владельцу в личку бота")
    p = sub.add_parser("publish")
    p.add_argument("--date", help="дата черновика по МСК, по умолчанию сегодня")
    p.add_argument("--to", default="tg,max", help="куда: tg, max или оба через запятую")
    p.add_argument("--kind", default="night", choices=["night", "league", "tonight"], help="рубрика")
    lg = sub.add_parser("league")
    lg.add_argument("--date", help="дата поста по МСК, по умолчанию сегодня")
    lg.add_argument("--review", action="store_true", help="опубликовать (автопубликация) или в личку владельцу")
    tn = sub.add_parser("tonight")
    tn.add_argument("--date", help="дата по МСК, по умолчанию сегодня")
    tn.add_argument("--review", action="store_true", help="опубликовать (автопубликация) или в личку владельцу")
    st = sub.add_parser("stories", help="⚡ инфоповоды из ленты NHL.com → черновики владельцу")
    st.add_argument("--since", type=int, help="взять новости за последние N часов (сбрасывает «уже видел»)")
    sub.add_parser("sync-registry")
    sub.add_parser("sync-names")
    sub.add_parser("serve", help="сервис: утренний сбор + кнопки «Опубликовать/Отклонить» в личке")
    args = ap.parse_args()
    publish.load_env()
    cmds = {"night": cmd_night, "league": cmd_league, "tonight": cmd_tonight, "publish": cmd_publish,
            "sync-registry": cmd_sync, "sync-names": cmd_sync_names, "serve": cmd_serve, "stories": cmd_stories}
    return cmds[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
