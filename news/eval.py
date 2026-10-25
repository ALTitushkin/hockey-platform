"""Прогон промпта по провайдерам на сохранённых реальных постах: сколько фраз проходит гард.

    python -m news.eval save 2026-10-20 2026-10-25              # посты этих утр (МСК) → news/fixtures/
    python -m news.eval run [--providers claude_cli,gigachat] [--runs 2]

Правило: правка промпта (news/prompts/) или смена модели принимается, только если прогон
не хуже прежнего по доле прохода гарда, а фразы прочитаны глазами — отчёт в news/out/eval_*.md.
Гард ловит числа, чужие фамилии и запретные слова, но не смысл: «кто победил» проверяет человек.
"""

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from news import guard, nhl, publish
from news.digest import render_night
from news.llm import PROVIDERS, _clean, prompt_for
from news.publish import OUT
from news.run import load

FIXTURES = Path(__file__).parent / "fixtures"


def cmd_save(args) -> int:
    reg, teams = load()
    players = {k: v for k, v in reg["players"].items() if v.get("ru")}
    FIXTURES.mkdir(exist_ok=True)
    day, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    while day <= end:
        reports = nhl.collect_night((day - timedelta(days=1)).isoformat(), {int(p) for p in players})
        text, facts = render_night(reports, players, teams, day.isoformat())
        if text:
            data = {"date": day.isoformat(), "text": text, "facts": {k: sorted(v) for k, v in facts.items()}}
            body = json.dumps(data, ensure_ascii=False, indent=1)
            (FIXTURES / f"night_{day}.json").write_text(body, encoding="utf-8")
            print(f"сохранён {day}: матчей {len(reports)}")
        day += timedelta(days=1)
    return 0


def cmd_run(args) -> int:
    reg, teams = load()
    players = {k: v for k, v in reg["players"].items() if v.get("ru")}
    fixtures = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURES.glob("night_*.json"))]
    if not fixtures:
        print("нет фикстур — сначала `python -m news.eval save …`")
        return 1
    report = [f"# Прогон промпта · {datetime.now():%Y-%m-%d %H:%M}", "",
              f"Фикстур: {len(fixtures)} · прогонов на фикстуру: {args.runs}", ""]
    summary = []
    for name in args.providers.split(","):
        ok = total = 0
        spent = 0.0
        report += [f"## {name}", ""]
        for fx in fixtures:
            facts = {k: set(v) for k, v in fx["facts"].items()}
            for _ in range(args.runs):
                total += 1
                t0 = time.time()
                try:
                    phrase = _clean(PROVIDERS[name](prompt_for(name, fx["text"])))
                except Exception as e:
                    phrase, issues = None, [f"ошибка {type(e).__name__}: {e}"[:150]]
                else:
                    issues = guard.check_lead(phrase, facts, players, teams) if phrase else ["нет ответа"]
                spent += time.time() - t0
                ok += not issues
                mark = "✅" if not issues else "❌ " + "; ".join(issues)
                report.append(f"- {fx['date']} · {mark} · {phrase or '—'}")
        rate = ok / total if total else 0
        summary.append(f"| {name} | {ok}/{total} | {rate:.0%} | {spent / max(total, 1):.1f} с |")
        report.append("")
    table = ["| Провайдер | Прошло гард | Доля | Среднее время |", "|---|---|---|---|", *summary]
    OUT.mkdir(exist_ok=True)
    path = OUT / f"eval_{datetime.now():%Y%m%d_%H%M}.md"
    path.write_text("\n".join(report[:4] + table + [""] + report[4:]), encoding="utf-8")
    print("\n".join(table))
    print(f"\nотчёт с фразами: {path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="news.eval")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save")
    s.add_argument("start")
    s.add_argument("end")
    r = sub.add_parser("run")
    r.add_argument("--providers", default="claude_cli")
    r.add_argument("--runs", type=int, default=1)
    args = ap.parse_args()
    publish.load_env()
    return {"save": cmd_save, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
