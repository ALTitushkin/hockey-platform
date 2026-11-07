"""Coordinate neighbouring recaps without suppressing a player's relevant facts."""

import html
import json
import re
from pathlib import Path


def previous_headline(path: Path) -> str:
    try:
        draft = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return ""
    if "tg" not in draft.get("published", []) or draft.get("rejected") or not draft.get("messages", {}).get("tg"):
        return ""
    match = re.search(r"<b>(.*?)</b>", draft.get("text", ""))
    return html.unescape(match[1]) if match else ""


def choose(highlights: list, players: dict, previous: str) -> tuple[list, bool]:
    """Choose another supported angle; keep every event in the remaining blocks."""
    if not highlights or not previous:
        return highlights, False
    def repeats(item):
        pid, events = item
        record = players.get(str(pid), {})
        return bool(record.get("surname") and record["surname"] in previous and events[0].text in previous)
    if not repeats(highlights[0]):
        return highlights, False
    for i, item in enumerate(highlights[1:], 1):
        if not repeats(item):
            return [item, *highlights[:i], *highlights[i + 1:]], False
    return highlights, True
