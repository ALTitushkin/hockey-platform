"""Stdlib-only contracts and optional local snapshot replay; never calls a model or sends posts."""

import argparse
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def replay(path: Path) -> dict:
    from news import fact_packet
    names = {"8475166": {"ru": "Джон Таварес"}, "8477018": {"ru": "Бен Хаттон"},
             "8482122": {"ru": "Брок Фейбер"}}
    clubs = {"TOR": "Торонто", "NYI": "Айлендерс", "MIN": "Миннесота"}
    aliases = {"TOR": ("Toronto", "Maple Leafs"), "NYI": ("", "Islanders"), "MIN": ("Minnesota", "Wild")}
    results = []
    for draft in json.loads(path.read_text(encoding="utf-8")):
        data = draft["data"]
        source = data["source_event"]
        story = SimpleNamespace(eid=data["slug"], kind=source["kind"], headline=source["headline"],
                                text=source["text"], date=datetime.fromisoformat(source["date"]),
                                en={int(pid): name for pid, name in source["en"].items()},
                                pids=set(source["pids"]), teams=set(source["teams"]),
                                link="https://www.nhl.com/news/" + data["slug"])
        packet = fact_packet.extract(story, names, clubs, aliases)
        errors = fact_packet.verify(packet, fact_packet.snapshot(story), fact_packet.render(packet)) if packet else []
        results.append({"slug": data["slug"], "previous_auto": data.get("auto", False),
                        "new_decision": "ready" if packet and not errors else "needs_review",
                        "source_hash": fact_packet.snapshot(story)["content_hash"],
                        "text": fact_packet.render(packet) if packet else None, "issues": errors})
    return {"cases": results, "model_calls": 0, "messages_sent": 0,
            "limitation": "Four saved articles; no claim about population accuracy or live delivery"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.archive:
        result = replay(args.archive)
        if args.report:
            args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(any(case["issues"] for case in result["cases"]))
    patterns = ("test_pipeline_core.py", "test_fact_packets.py", "test_source_watch.py",
                "test_pipeline_adversarial_qa.py", "test_queue_lifecycle_qa.py")
    suite = unittest.TestSuite(unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=p) for p in patterns)
    result = unittest.TextTestRunner().run(suite)
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    raise SystemExit(main())
