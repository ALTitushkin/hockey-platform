"""Resolve event references against durable publication receipts, not the live feed."""

import json
import re
from datetime import date, timedelta
from urllib.parse import urlsplit

from news import event_registry, fact_packet


def equivalent_draft(story, packet, out, msk):
    """Reuse work for identical source or supported facts, including unresolved review."""
    today = date.fromisoformat(msk)
    source_hash = fact_packet.snapshot(story)["content_hash"]
    revision = fact_packet.revision(packet) if packet else None
    for offset in range(4):
        for path in sorted(out.glob(f"{today - timedelta(days=offset)}_story-*.json")):
            try:
                if path.stat().st_size > 128 * 1024:
                    continue
                draft = json.loads(path.read_text(encoding="utf-8"))
                data = draft.get("data") or {}
                old = data.get("event_revision")
                # New extraction capabilities must not silently auto-publish the old
                # review backlog. Reinterpret its frozen evidence for comparison only.
                frozen = data.get("source_snapshot") or {}
                if (packet and not event_registry.complete(old) and frozen.get("content_hash")
                        and fact_packet.source_hash(frozen) == frozen["content_hash"]):
                    claim = packet["claims"][0]
                    rebuilt = fact_packet.extract(fact_packet.restore(frozen),
                        {str(claim["subject"]): {"ru": packet["actor_name"]}},
                        {claim["club"]: packet["club_name"]}, {claim["club"]: packet["club_alias"]})
                    if rebuilt:
                        old = fact_packet.revision(rebuilt)
                same_source = (data.get("slug") == story.slug
                               and data.get("source_snapshot", {}).get("content_hash") == source_hash)
                same_facts = (revision and event_registry.complete(old)
                              and event_registry.revision_key(old) == event_registry.revision_key(revision))
                if same_source or same_facts:
                    return path, draft
            except (OSError, ValueError, AttributeError, TypeError, KeyError):
                continue
    return None


def published_reference(story, out, msk):
    today = date.fromisoformat(msk)
    for offset in range(4):
        for path in out.glob(f"{today - timedelta(days=offset)}_story-*.json"):
            try:
                if path.stat().st_size > 128 * 1024:
                    continue
                draft = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(draft, dict):
                continue
            messages, data, published = draft.get("messages"), draft.get("data"), draft.get("published")
            if not isinstance(messages, dict) or not isinstance(data, dict) or not isinstance(published, list):
                continue
            if (not messages.get("tg") or "tg" not in published
                    or draft.get("rejected") or draft.get("deleted_messages")):
                continue
            slug = data.get("slug")
            # An explicit source backlink proves continuity even after the first
            # article has disappeared from the current Forge feed.
            urls = re.findall(r'https://[^\s)<>"\]]+', story.text)
            referenced = False
            for url in urls:
                try:
                    parsed = urlsplit(url)
                except ValueError:
                    continue
                if parsed.hostname in ("www.nhl.com", "nhl.com") and parsed.path.rstrip("/").split("/")[-1] == slug:
                    referenced = True
                    break
            if slug and slug != story.slug and referenced:
                return {"slug": slug, "messages": draft["messages"]["tg"]}
    return None
