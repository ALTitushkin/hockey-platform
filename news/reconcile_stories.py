"""Read-only reconciliation of saved story drafts and Telegram receipts."""

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from news import editorial_lifecycle, event_registry


def rows(path, query):
    if not path.is_file():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute(query).fetchall()


def reconcile(root: Path, start: date, now: datetime) -> dict:
    editorial = {name: (status, json.loads(reasons)) for name, status, reasons in rows(
        root / "editorial.sqlite3", "SELECT name,status,reasons FROM editorial_tasks")}
    ledger = {}
    for revision, document, status, messages in rows(
            root / "event_registry.sqlite3",
            "SELECT revision,document,status,messages FROM publications WHERE channel LIKE 'tg:%'"):
        ledger.setdefault(revision, []).append((document, status, json.loads(messages or "[]")))
    cases = []
    for path in sorted(root.glob("????-??-??_story-*.json")):
        if path.name[:10] < start.isoformat():
            continue
        case = {"document": path.name}
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
            data = draft.get("data") or {}
            case["slug"] = data.get("slug")
            case.update(classify(path, draft, data, editorial, ledger, now))
        except (OSError, ValueError, TypeError, AttributeError) as error:
            case.update(outcome="unreadable", reasons=[type(error).__name__])
        cases.append(case)
    journal = root / "story_feed_audit.json"
    feed = json.loads(journal.read_text(encoding="utf-8")) if journal.is_file() else {}
    by_document = {case["document"]: case for case in cases}
    observed = []
    for ident, item in feed.items():
        if item["at"][:10] >= start.isoformat():
            delivery = by_document.get(item.get("document"), {})
            observed.append({"id": ident, "feed_outcome": item["outcome"], **item, **delivery})
    return {"since": start.isoformat(), "at": now.isoformat(),
            "counts": dict(Counter(c["outcome"] for c in cases)), "cases": cases,
            "feed_counts": dict(Counter(c["outcome"] for c in observed)), "feed": observed}


def record_pass(root: Path, observations: dict, now: datetime) -> list[str]:
    path = root / "story_feed_audit.json"
    root.mkdir(parents=True, exist_ok=True)
    prior = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    for ident, item in observations.items():
        if ident in prior and item["outcome"] == "already_processed":
            item = {**prior[ident], "at": item["at"]}
        prior[ident] = item
    recent = sorted(prior.items(), key=lambda pair: pair[1]["at"])[-2000:]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(recent), ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    report = reconcile(root, now.date(), now)
    counts = report["feed_counts"]
    warnings = [case["document"] for case in report["cases"]
                if case["outcome"] in ("delivery_unknown", "ready_without_receipt")]
    lines = ["сверка инфоповодов: " + json.dumps(counts, sort_keys=True)]
    if warnings:
        lines.append("инфоповоды без подтверждения доставки: " + ", ".join(warnings))
    return lines


def classify(path, draft, data, editorial, ledger, now):
    def result(outcome, reasons=(), **details):
        return {"outcome": outcome, "reasons": list(reasons), **details}

    event = data.get("event_revision")
    entries = ledger.get(event_registry.revision_key(event), []) if event_registry.complete(event) else []
    own_receipts = [mid for document, status, mids in entries if document == path.name and status == "published"
                    for mid in mids if type(mid) is int and mid > 0]
    draft_mids = (draft.get("messages") or {}).get("tg") or []
    confirmed = own_receipts or [mid for mid in draft_mids if type(mid) is int and mid > 0]
    if own_receipts or ("tg" in draft.get("published", []) and confirmed):
        return result("published", telegram_message_ids=confirmed)
    status, reasons = editorial.get(path.name, ("", []))
    if ("tg" in draft.get("published", []) or status == "delivery_unknown"
            or any(state in ("sending", "uncertain") for _, state, _ in entries)
            or any(document == path.name and state == "published" for document, state, _ in entries)):
        return result("delivery_unknown", reasons)
    duplicates = [document for document, state, mids in entries
                  if document != path.name and state == "published" and any(type(m) is int and m > 0 for m in mids)]
    if duplicates:
        return result("duplicate", confirmed_documents=sorted(set(duplicates)))
    if draft.get("editorial_closed") or draft.get("rejected") or status in ("closed", "rejected", "superseded"):
        return result(status if status in ("closed", "rejected", "superseded") else "closed", reasons)
    lifecycle, expiry_reasons = editorial_lifecycle.classify(draft, path.stem.split("_", 1)[1], now)
    if lifecycle == "expired":
        return result("expired", expiry_reasons)
    if not data.get("fact_packet") or not data.get("auto") or draft.get("issues"):
        why = (data.get("event_decision") or {}).get("reasons") or reasons or draft.get("issues") or expiry_reasons
        return result("review", why or ["нет подтверждённого допуска к автопубликации"])
    if lifecycle != "ready":
        return result(lifecycle, expiry_reasons)
    return result("ready_without_receipt", reasons)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("news/out"))
    parser.add_argument("--since", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    if not args.out.is_dir():
        parser.error("runtime directory does not exist")
    print(json.dumps(reconcile(args.out, args.since, datetime.now(timezone.utc)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
