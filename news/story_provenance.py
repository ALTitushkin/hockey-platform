"""Resolve event references against durable publication receipts, not the live feed."""

import json
import re
from datetime import date, timedelta
from urllib.parse import urlsplit


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
