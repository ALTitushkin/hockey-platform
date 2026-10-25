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

from news import events, guard, names, nhl, publish, service
from news.card import render_card, render_tonight_card
from news.digest import render_caption, render_league, render_night, render_tonight
from news.llm import lead

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


def build_tonight(msk: str, review: bool) -> str:
    """«Сегодня ночью»: матчи НХЛ, которые ещё не начались, по московскому времени, и наши в составах.
    Вечер по Москве = та же дата в Северной Америке. Клуб игрока — из статистики сезона НХЛ."""
    reg, teams = load()
    games = nhl.upcoming_games(msk)
    players = {k: v for k, v in reg["players"].items() if v.get("ru")}
    ours: dict[str, list[tuple[int, str]]] = {}
    for p in nhl.fetch_nationals(SEASON):
        rec = players.get(str(p["pid"]))
        if rec and p.get("team"):
            ours.setdefault(p["team"], []).append((p["pid"], rec["surname"]))
    text, facts = render_tonight(games, ours, teams, msk, ZoneInfo("Europe/Moscow"))
    if not text:
        print(f"{msk}: матчей впереди нет — поста нет")
        return "nogames"
    issues = guard.check(text, facts, players, teams)
    card = render_tonight_card(games, ours, teams, msk, ZoneInfo("Europe/Moscow"), publish.OUT / f"{msk}_tonight.png")
    path = publish.save_draft(msk, text, issues, "шаблон", str(card), kind="tonight")
    print(text, f"\n\n— гард: {'чисто' if not issues else '; '.join(issues)}\n— черновик: {path}")
    if review and not issues and os.environ.get("NEWS_AUTO_PUBLISH") == "1":
        ok, info = publish.auto_publish(msk, kind="tonight")
        print(f"— автопубликация: {'ок' if ok else 'ошибка'} — {info}")
    elif review:
        ok, info = publish.review(msk, kind="tonight")
        print(f"— владельцу в личку: {'ок' if ok else 'ошибка'} — {info}")
    return "guard" if issues else "ok"


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

    service.run_forever([("league", "NEWS_LEAGUE_AT", "09:00", league),
                         ("night", "NEWS_REVIEW_AT", "09:30", night),
                         ("tonight", "NEWS_TONIGHT_AT", "18:00", tonight)])
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
    sub.add_parser("sync-registry")
    sub.add_parser("sync-names")
    sub.add_parser("serve", help="сервис: утренний сбор + кнопки «Опубликовать/Отклонить» в личке")
    args = ap.parse_args()
    publish.load_env()
    cmds = {"night": cmd_night, "league": cmd_league, "tonight": cmd_tonight, "publish": cmd_publish,
            "sync-registry": cmd_sync, "sync-names": cmd_sync_names, "serve": cmd_serve}
    return cmds[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
