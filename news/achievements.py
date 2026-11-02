"""Weekly achievements from published daily drafts. No requests or model calls."""

import html
import json
import re
from datetime import date, timedelta
from pathlib import Path


def weight(text: str) -> int:
    """Only known factual achievement templates; never infer a milestone from points."""
    patterns = (
        (100, r"лучший (?:бомбардир|снайпер|ассистент) в истории клуба: \d+ "
              r"(?:очко|очка|очков|гол|гола|голов|передача|передачи|передач)"),
        (85, r"\d+-(?:й гол|е очко|й матч) в НХЛ"),
        (70, r"(?:первый гол|первые голы|первое очко) в НХЛ"),
        (65, r"\d+-я (?:победа|игра с очками) подряд"),
        (55, r"хет-трик|[4-9] гола за матч"),
        (50, r"сухой матч"),
        (45, r"[4-9] (?:очка|очков) за матч"),
    )
    return next((score for score, pattern in patterns if re.fullmatch(pattern, text)), 0)


def snapshot(highlights: list, text: str, nhl_date: str) -> dict:
    """Persist only events that are actually visible in the final published caption."""
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    records = [{"pid": pid, "text": e.text} for pid, events in highlights for e in events
               if weight(e.text) and e.text in plain]
    return {"nhl_date": nhl_date, "achievements": records}


def permalink(channel: str, message_id: int) -> str | None:
    if not isinstance(channel, str) or type(message_id) is not int or message_id <= 0:
        return None
    channel = channel.strip()
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{4,31}", channel):
        return f"https://t.me/{channel.lstrip('@')}/{message_id}"
    if re.fullmatch(r"-100[1-9]\d{5,}", channel):
        return f"https://t.me/c/{channel[4:]}/{message_id}"
    return None


def legacy_records(text: str, players: dict) -> list[dict]:
    """Read old deterministic headline/highlight lines, never narrative LLM prose."""
    aliases: dict[str, set[int]] = {}
    for pid, rec in players.items():
        full, surname = rec.get("ru"), rec.get("surname")
        if not full or not surname:
            continue
        for alias in (full, surname, f"{full[0]}. {surname}"):
            aliases.setdefault(alias, set()).add(int(pid))
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    records = []
    for line in plain.splitlines():
        match = re.fullmatch(r"[🏆🎯🎖✨🎩🧱💥]\s+(.+?) — (.+)", line.strip())
        if not match:
            continue
        label, description = match.groups()
        ids = aliases.get(label, set())
        if len(ids) != 1:
            continue
        for phrase in description.partition(" · ")[0].split(", "):
            if weight(phrase):
                records.append({"pid": next(iter(ids)), "text": phrase})
    return records


def load(out: Path, start: str, end: str, players: dict, channel: str, limit: int = 5) -> list[dict]:
    """At most 14 daily files. Morning post date = NHL game date + one day.

    Link the final text message if a daily post was split into image + text. Prefer
    the national recap over league recap for the same achievement, then the latest.
    """
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if not 0 <= (last - first).days <= 6:
        raise ValueError("Архив достижений читается только за одну неделю")
    found = {}
    for offset in range((last - first).days + 1):
        game_date = (first + timedelta(days=offset)).isoformat()
        post_date = (first + timedelta(days=offset + 1)).isoformat()
        for kind in ("league", "night"):
            path = out / f"{post_date}_{kind}.json"
            try:
                if path.stat().st_size > 128 * 1024:
                    continue
                draft = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(draft, dict) or draft.get("date") != post_date:
                continue
            published = draft.get("published")
            if not isinstance(published, list) or "tg" not in published or draft.get("rejected") or draft.get("issues"):
                continue
            if any(not isinstance(draft.get(k, {}), dict) for k in ("messages", "channels", "deleted_messages")):
                continue
            messages = draft.get("messages", {}).get("tg", [])
            if not isinstance(messages, list) or not messages:
                continue
            # A missing text message is not replaced by an unrelated media message.
            mid = messages[-1]
            deleted = draft.get("deleted_messages", {}).get("tg", [])
            if not isinstance(deleted, list) or mid in deleted:
                continue
            url = permalink(channel, mid)
            if not url:
                continue
            bound = draft.get("channels", {}).get("tg")
            if "tg" in draft.get("channels", {}) and not isinstance(bound, str):
                continue
            if bound and permalink(bound, mid) != url:
                continue
            data = draft.get("data") or {}
            if not isinstance(data, dict):
                continue
            if data.get("nhl_date", game_date) != game_date:
                continue
            text = draft.get("text", "")
            if not isinstance(text, str):
                continue
            plain = html.unescape(re.sub(r"<[^>]+>", "", text))
            records = data.get("achievements")
            if records is None:
                # Old league captions can have a foreign namesake. Without NHL IDs
                # only the national recap proves that the named player is ours.
                if kind != "night":
                    continue
                records = legacy_records(text, players)
            if not isinstance(records, list):
                continue
            visible = {(r["pid"], r["text"]) for r in legacy_records(text, players)}
            for record in records:
                if not isinstance(record, dict):
                    continue
                pid, phrase = record.get("pid"), record.get("text")
                if type(pid) is not int or str(pid) not in players or not isinstance(phrase, str):
                    continue
                score = weight(phrase)
                surname = players[str(pid)].get("surname")
                if (not score or not surname or phrase not in plain or surname not in plain
                        or (pid, phrase) not in visible):
                    continue
                entry = {"pid": pid, "text": phrase, "url": url, "nhl_date": game_date, "weight": score,
                         "post_date": post_date, "message_id": mid, "kind": kind}
                key = (pid, phrase)
                previous = found.get(key)
                if not previous or (kind == "night", game_date) > (previous["kind"] == "night", previous["nhl_date"]):
                    found[key] = entry
    return sorted(found.values(), key=lambda r: (-r["weight"], r["nhl_date"], r["pid"], r["text"]))[:limit]
