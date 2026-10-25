"""CLI новостника «Культура хоккея». В каналы — только командой publish после проверки владельцем.

    python -m news.run night [--date YYYY-MM-DD] [--llm [chain]] [--review]  # «Ночь наших» (МСК)
    python -m news.run publish [--date YYYY-MM-DD] [--to tg,max]            # черновик → каналы
    python -m news.run sync-registry                       # новые наши из НХЛ → реестр со status=new

Черновики и отчёт гарда пишутся в news/out/ (в git не попадает). Секреты — news/.env.
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from news import guard, nhl, publish
from news.card import render_card
from news.digest import render_night, with_lead
from news.llm import lead

ROOT = Path(__file__).parent
PLAYERS = ROOT / "data" / "players.json"
TEAMS = ROOT / "data" / "teams.json"
SEASON = "20262027"


def load():
    return json.loads(PLAYERS.read_text(encoding="utf-8")), json.loads(TEAMS.read_text(encoding="utf-8"))


def cmd_night(args) -> int:
    reg, teams = load()
    players = {k: v for k, v in reg["players"].items() if v.get("ru")}
    msk = args.date or datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    # Утро по Москве = вечер предыдущей даты в Северной Америке.
    nhl_date = (date.fromisoformat(msk) - timedelta(days=1)).isoformat()

    reports = nhl.collect_night(nhl_date, {int(p) for p in players})
    text, facts = render_night(reports, players, teams, msk)
    if not text:
        print(f"{msk}: наши не играли (НХЛ {nhl_date}) — поста нет")
        return 0

    variant, final = "шаблон", text
    issues = guard.check(text, facts, players, teams)
    if args.llm is not None:  # голый --llm = цепочка из NEWS_LLM
        phrase, source, log = lead(text, lambda p: guard.check_lead(p, facts, players, teams), chain=args.llm or None)
        for line in log:
            print(f"  ↳ {line}")
        if phrase:
            variant, final = f"шаблон + вводная {source}", with_lead(text, phrase)

    card = render_card(reports, players, teams, msk, publish.OUT / f"{msk}_night.png")
    path = publish.save_draft(msk, final, issues, variant, str(card))
    print(final, "\n")
    print(f"— вариант: {variant} · матчей: {len(reports)} · гард: {'чисто' if not issues else '; '.join(issues)}")
    print(f"— черновик: {path}")
    if args.review:
        ok, info = publish.review(msk)
        print(f"— владельцу в личку: {'ок' if ok else 'ошибка'} — {info}")
    return 1 if issues else 0


def cmd_publish(args) -> int:
    msk = args.date or datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    ok, report = publish.publish(msk, args.to.split(","))
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
    sub.add_parser("sync-registry")
    args = ap.parse_args()
    publish.load_env()
    return {"night": cmd_night, "publish": cmd_publish, "sync-registry": cmd_sync}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
