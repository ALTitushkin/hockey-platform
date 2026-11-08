"""Bounded source revision watching; updated URLs produce candidates, never silent replacements."""

import hashlib
import json
import time
from datetime import datetime, timedelta


def digest(headline: str, text: str, english: dict | None = None, raw: dict | None = None) -> str:
    raw = raw or {}
    # Only tag fields consumed by selection/identity. Labels and presentation data
    # change independently of the reported facts and must not reopen editorial work.
    tags = sorted({(tag.get("slug", ""), tag.get("extraData", {}).get("abbreviation", ""))
                   for tag in raw.get("tags", [])})
    payload = [headline, text, {str(pid): name for pid, name in (english or {}).items()}, tags,
               raw.get("contentDate")]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def remember(state: dict, raw: dict, story, now: datetime) -> None:
    origin = raw.get("_editorial_origin", story.eid)
    previous = state.setdefault("source_watch", {}).get(origin, {})
    versions = previous.get("versions", {})
    content_hash = digest(story.headline, story.text, getattr(story, "en", {}), raw)
    versions[content_hash] = story.eid
    state.setdefault("source_watch", {})[origin] = {
        "raw": raw, "hash": content_hash, "versions": dict(list(versions.items())[-128:]),
        "checked": now.isoformat(),
        "until": (story.date + timedelta(hours=48)).isoformat()}


def prepare(raw_items: list[dict], state: dict, now: datetime, parse, fetch_body,
            bounded_fetch=None, budget_seconds: float = 8) -> tuple[list[dict], dict]:
    """At most eight refreshes/tick; no LLM calls, including when a feed item disappears."""
    watch = state.setdefault("source_watch", {})
    if not isinstance(watch, dict):
        watch = state["source_watch"] = {}
    for origin, entry in list(watch.items()):
        try:
            if not isinstance(entry, dict) or not isinstance(entry.get("raw"), dict):
                raise ValueError("invalid watch")
            for field in ("until", "checked"):
                if datetime.fromisoformat(entry[field]).tzinfo is None:
                    raise ValueError("watch needs timezone")
        except (KeyError, TypeError, ValueError):
            del watch[origin]
    items = {item.get("_editorial_origin", item.get("_entityId", ("unidentified", i))): item
             for i, item in enumerate(raw_items)}
    prepared = {}
    budget = 8
    started = time.monotonic()
    for origin, entry in sorted(watch.items(), key=lambda pair: pair[1].get("checked", "")):
        if datetime.fromisoformat(entry["until"]) <= now:
            del watch[origin]
            continue
        remaining = budget_seconds - (time.monotonic() - started)
        if remaining <= 0:
            break
        if budget <= 0 or now - datetime.fromisoformat(entry["checked"]) < timedelta(minutes=15):
            continue
        current = items.get(origin, entry["raw"])
        try:
            story = parse(current)
        except (ValueError, KeyError, TypeError):
            continue
        if story is None:
            continue
        budget -= 1
        entry["checked"] = now.isoformat()
        try:
            text, english = bounded_fetch(story, min(5, remaining)) if bounded_fetch else fetch_body(story)
        except RuntimeError:
            continue  # Failure does not erase a snapshot or become evidence of no change.
        if not text.strip():
            continue
        body_hash = digest(story.headline, text, english, current)
        if body_hash == entry["hash"]:
            continue
        version_id = (entry.get("versions", {}).get(body_hash)
                      or hashlib.sha256((origin + ":" + body_hash).encode()).hexdigest())
        candidate = {**current, "_entityId": version_id, "_editorial_origin": origin}
        items[origin] = candidate
        prepared[version_id] = (text, english)
    return list(items.values()), prepared
