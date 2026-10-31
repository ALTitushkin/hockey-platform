"""Пилот без публикаций: python -m news.benchmark_codex --output news/out/codex-pilot.

Получает до трёх свежих исходников NHL.com, сохраняет источник, пересказ, гард и токены.
Повторный запуск переиспользует inputs.json; --inputs задаёт сохранённую выборку.
"""
import argparse
import json
from pathlib import Path

from news import codex_provider, names, nhl, publish, registry, stories


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--inputs", type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    publish.OUT = args.output / "runtime"
    reg = {k: v for k, v in registry.load()["players"].items() if v.get("ru")}
    teams = json.loads((Path(__file__).parent / "data/teams.json").read_text(encoding="utf-8"))
    inputs = args.inputs or args.output / "inputs.json"
    if not inputs.exists():
        rows = []
        for item in nhl.fetch_json(stories.FEED).get("items", []):
            s = stories.parse_item(item)
            if not s:
                continue
            full = nhl.fetch_json(s.url)
            rows.append({"item": item, "full": full})
            if len(rows) == 3:
                break
        inputs.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = json.loads(inputs.read_text(encoding="utf-8"))
    results = []
    for row in rows:
        s = stories.parse_item(row["item"])
        s.text, s.en = stories.body_text(row["full"])
        s.mentioned = set(s.en)
        people = names.league_players(s.mentioned | s.pids, reg)
        prompt = stories.prompt_for(s, people, teams, {int(p) for p in reg})
        raw = codex_provider.generate(prompt)
        body = stories.clean(raw)
        issues, notes = stories.check(body, s, people, reg, teams, {int(p) for p in reg}) \
            if body and body != "SKIP" else (["нет пересказа"] if not body else [], [])
        post = stories.render(s, body, s.date.date().isoformat()) if body and body != "SKIP" else None
        results.append({"headline": s.headline, "link": s.link, "source": s.text,
                        "body": body, "issues": issues, "notes": notes,
                        "post": post})
    (args.output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    metrics = codex_provider.read_state()
    cgroup = Path("/sys/fs/cgroup")
    resources = {name: (cgroup / name).read_text().strip() for name in (
        "memory.peak", "memory.swap.current", "memory.events", "cpu.stat") if (cgroup / name).exists()}
    (args.output / "resources.json").write_text(json.dumps(resources, indent=2), encoding="utf-8")
    print(json.dumps({"stories": len(results), "passed": sum(bool(r["body"]) and not r["issues"] for r in results),
                      "runs": metrics["runs"], "resources": resources}, ensure_ascii=False, indent=2))
    return 0 if results and all(r["body"] and not r["issues"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
