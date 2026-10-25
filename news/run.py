"""CLI новостника «Культура хоккея». Сейчас — теневой режим: ничего не публикует.

    python -m news.run night [--date YYYY-MM-DD] [--llm [claude_cli,gigachat,...]]  # «Ночь наших» (МСК)
    python -m news.run sync-registry                       # новые наши из НХЛ → реестр со status=new

Черновики и отчёт гарда пишутся в news/out/ (в git не попадает).
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from news import guard, nhl
from news.digest import render_night, with_lead
from news.llm import lead

ROOT = Path(__file__).parent
PLAYERS = ROOT / "data" / "players.json"
TEAMS = ROOT / "data" / "teams.json"
OUT = ROOT / "out"
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

    OUT.mkdir(exist_ok=True)
    path = OUT / f"{msk}_night.html"
    path.write_text(final, encoding="utf-8")
    print(final, "\n")
    print(f"— вариант: {variant} · матчей: {len(reports)} · гард: {'чисто' if not issues else '; '.join(issues)}")
    print(f"— черновик: {path}")
    return 1 if issues else 0


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
    sub.add_parser("sync-registry")
    args = ap.parse_args()
    return {"night": cmd_night, "sync-registry": cmd_sync}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
