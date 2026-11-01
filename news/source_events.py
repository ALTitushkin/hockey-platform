"""Консервативные события для теневого пилота; неизвестные факты не считаем одинаковыми."""

import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

from news.source_dedup import Event, fingerprint

RULES = [
    ("return", r"\breturns?\b|\bactivat\w*|\bback in (the )?lineup\b"),
    ("trade", r"\bacquir\w*|\btraded?\b|\btrades\b"),
    ("signing", r"\bsigns?\b|\bre-sign\w*|\bextension\b|\bagrees? to terms\b"),
    ("fine", r"\bfined\b|\bfine for\b"),
    ("injury", r"\binjur\w*|\bsurgery\b|\b(out|miss|misses)\b|\bsidelined\b"),
    ("recall", r"\brecall\w*|\bcalled up\b"),
    ("assign", r"\bassign\w*|\bloan\w*|\bsent down\b"),
    ("waivers", r"\bwaivers\b"),
]
WORDS = dict(zip("one two three four five six seven eight nine ten".split(), range(1, 11), strict=True))


def normalized(text: str) -> str:
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.replace("’", "'")).strip().casefold()


def build_aliases(items: list[dict]) -> dict[str, int]:
    """English full name→NHL ID только из доверенных тегов NHL, не из RSS."""
    aliases = {}
    ambiguous = set()
    for item in items:
        for tag in item.get("tags", []):
            match = re.fullmatch(r"playerid-(\d{7})", tag.get("slug", ""))
            name = normalized(tag.get("title") or "")
            if match and len(name.split()) >= 2:
                pid = int(match[1])
                if name in aliases and aliases[name] != pid:
                    ambiguous.add(name)
                aliases[name] = pid
    return {name: pid for name, pid in aliases.items() if name not in ambiguous}


@lru_cache(maxsize=2)
def _index(entries: tuple, trusted_ids: tuple):
    aliases = dict(entries)
    surnames = {}
    for name, pid in aliases.items():
        surnames.setdefault(normalized(name).split()[-1], set()).add(int(pid))
    choices = {}
    for name, pid in aliases.items():
        full = normalized(name)
        choices[full] = int(pid)
        surname = full.split()[-1]
        if int(pid) in trusted_ids and len(surnames[surname]) == 1:
            choices[surname] = int(pid)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(x) for x in sorted(choices, key=len, reverse=True))
                         + r")(?!\w)") if choices else None
    return pattern, choices


def _people(text: str, aliases: dict, trusted_ids: tuple = ()) -> list[tuple[int, int]]:
    pattern, choices = _index(tuple(sorted(aliases.items())), tuple(sorted(trusted_ids)))
    return [(m.start(), choices[m[0]]) for m in pattern.finditer(normalized(text))] if pattern else []


def extract_event(title: str, text: str, published_at: str, aliases: dict,
                  trusted_ids=()) -> Event | None:
    """Известный герой/действие/дата; неполная версия не подавляет другой пересказ."""
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if published.tzinfo is None:
            return None
        episode = published.astimezone(timezone.utc).date().isoformat()
    except (ValueError, AttributeError):
        return None
    head = normalized(title)
    action = next((kind for kind, rule in RULES if re.search(rule, head)), None)
    trusted_ids = tuple(trusted_ids)
    people = _people(title, aliases, trusted_ids)
    if not action or not people:
        return None
    hero = people[0][1]
    # Статистика карьеры и чужие события ниже статьи не становятся фактами главной новости.
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text[:6000])[:30]
    relevant = [s for s in sentences if hero in {p for _, p in _people(s, aliases, trusted_ids)}][:4]
    lead = normalized(title + " " + " ".join(relevant))
    status = "confirmed"
    if re.search(r"\b(not|won't|denies|denied)\b", head):
        status = "denied"
    elif re.search(r"\b(could|may|might|expected|reportedly|likely|nears|rumou?r\w*)\b", head):
        status = "expected"
    facts = {"status": status}
    amounts = []
    for amount, unit in re.findall(r"\$([\d,]+(?:\.\d+)?)\s*(million|thousand)?", lead):
        value = Decimal(amount.replace(",", "")) * {"million": 1000000, "thousand": 1000, "": 1}[unit]
        amounts.append(str(value.normalize()))
    if amounts:
        facts["usd"] = sorted(set(amounts))
    duration = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
                         r"(?:\s*(?:-|–|to)\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten))?"
                         r"\s+(days?|weeks?|months?|years?)\b", lead)
    if duration:
        number = lambda v: WORDS[v] if v in WORDS else int(v)  # noqa: E731
        facts["duration"] = [number(duration[1]), number(duration[2] or duration[1]), duration[3].rstrip("s")]
    modifiers = sorted(set(re.findall(r"lower.body|upper.body|acl|fracture|surgery|season.ending|indefinitely", lead)))
    if modifiers:
        facts["injury_details"] = modifiers
    # Полноценное подавление парафраз ограничено штрафами с суммой, нарушением и известной второй стороной.
    # Для прочих видов это пока связь кандидатов: разные тексты остаются разными версиями.
    others = sorted({p for _, p in _people(lead, aliases, trusted_ids)} - {hero})
    infraction = re.search(r"roughing|elbowing|slashing|cross.checking|boarding|high.sticking|tripping", lead)
    residual = re.sub(r"\$[\d,]+(?:\.\d+)?\s*(million|thousand)?", "", normalized(text))
    extra = len(text) > 1200 or re.search(r"\d|\b(not|no|never|suspend\w*|appeal\w*|injur\w*)\b", residual)
    if action == "fine" and amounts and others and infraction and status == "confirmed" and not extra:
        facts.update(targets=others, infraction=infraction[0])
    else:
        facts["evidence"] = fingerprint(text)
        facts["partial"] = True
    # Наблюдение новых чисел/отрицаний не теряется даже при совпадающей цене/сроке.
    facts["numbers"] = sorted(set(re.findall(r"\b\d+(?:[.,]\d+)?\b", lead))) if facts.get("partial") else []
    return Event((f"player:{hero}",), action, episode, facts)
