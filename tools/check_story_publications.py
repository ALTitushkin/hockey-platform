"""Replay saved story sources through the real template/image/send contract, with no network."""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def replay(directory: Path, output: Path, now: datetime) -> dict:
    from news import editorial_lifecycle, fact_packet, names, stories, story_validation
    registry = json.loads((ROOT / "news/data/players.json").read_text(encoding="utf-8"))["players"]
    teams = json.loads((ROOT / "news/data/teams.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sorted(directory.glob("????-??-??_story-*.json")):
        draft = json.loads(path.read_text(encoding="utf-8"))
        source = draft["data"]["source_event"]
        story = stories.Story(path.stem, draft["data"]["slug"], source["headline"], "",
                              datetime.fromisoformat(source["date"]), source["kind"],
                              set(source["pids"]), set(source["teams"]), True,
                              text=source["text"], en={int(pid): name for pid, name in source["en"].items()})
        story.mentioned = set(story.en)
        records = names.league_players(story.pids | story.mentioned, registry)
        packet = fact_packet.extract(story, records, teams, stories.TEAM_EN)
        item = {"file": path.name, "previous_auto": draft["data"].get("auto"), "decision": "needs_review"}
        if packet:
            snapshot = fact_packet.snapshot(story)
            image = output / (path.stem + ".png")
            # A missing local font/asset is a replay failure, not permission to fetch it.
            with patch("urllib.request.urlopen", side_effect=AssertionError("Offline replay attempted network")):
                stories.card(story, fact_packet.render(packet), records, {int(pid) for pid in registry}, [],
                             teams, path.name[:10], image, packet=packet)
            candidate = {"date": path.name[:10], "text": fact_packet.caption(packet, snapshot, path.name[:10]),
                         "card": str(image), "data": {"fact_packet": packet, "packet_hash": fact_packet.key(packet),
                         "source_snapshot": snapshot, "event_revision": fact_packet.revision(packet),
                         "expires_at": fact_packet.expires_at(packet), "card_spec": fact_packet.card_spec(packet),
                         "card_hash": story_validation.image_hash(image)}}
            errors = story_validation.check(candidate, path.name[:10])
            status, reasons = editorial_lifecycle.classify(candidate, path.stem.split("_", 1)[1], now)
            item.update(decision="blocked" if errors else status, errors=errors, reasons=reasons,
                        spec=fact_packet.card_spec(packet), text=candidate["text"], image=str(image),
                        fact_key=fact_packet.key(fact_packet.revision(packet)))
        results.append(item)
    report = {"at": now.isoformat(), "cases": results, "counts": dict(Counter(r["decision"] for r in results)),
              "unique_ready_facts": len({r["fact_key"] for r in results if r["decision"] == "ready"}),
              "model_calls": 0, "messages_sent": 0}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drafts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--at", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    if args.at.tzinfo is None:
        parser.error("--at requires a timezone")
    report = replay(args.drafts, args.output, args.at)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False))
    return int(any(r.get("errors") for r in report["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
