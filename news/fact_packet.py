"""Small evidence-backed templates. Unknown prose stays review, never guessed by the renderer."""

import hashlib
import html
import json
import re
from datetime import timedelta
from types import SimpleNamespace

from news.digest import MONTHS, plural

WEEKDAYS = {word: n for n, word in enumerate(
    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))}


def snapshot(story) -> dict:
    """A frozen body version, independent of the feed document ID."""
    text = story.text
    source = {"document_id": story.eid, "url": story.link, "published_at": story.date.isoformat(),
              "headline": story.headline, "text": text, "kind": story.kind,
              "actors": sorted(story.pids), "clubs": sorted(story.teams),
              "english": {str(pid): name for pid, name in story.en.items()}}
    source["content_hash"] = source_hash(source)
    return source


def source_hash(source: dict) -> str:
    fields = ("url", "published_at", "headline", "text", "kind", "actors", "clubs", "english")
    return key({field: source.get(field) for field in fields})


def restore(source: dict):
    """Reconstruct the frozen input for replay/verification without touching the network."""
    from datetime import datetime
    return SimpleNamespace(eid=source["document_id"], link=source["url"],
                           date=datetime.fromisoformat(source["published_at"]), kind=source["kind"],
                           headline=source["headline"], text=source["text"],
                           pids=set(source["actors"]), teams=set(source["clubs"]),
                           en={int(pid): name for pid, name in source["english"].items()})


def key(packet: dict) -> str:
    return hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def left_game(story, pid: int, club: str, record: dict, teams: dict, club_names: dict) -> dict | None:
    """A dated game incident, not a diagnosis or a forecast about the next game."""
    if story.kind not in ("injury", "injury_minor"):
        return None
    paragraphs = story.text.strip().split("\n\n")
    lead = paragraphs[0]
    english = story.en[pid]
    subject = r"[-\s]+".join(re.escape(part) for part in re.split(r"[-\s]+", english))
    if not re.search(subject + r"\s+(?:sustained|left|was hit|was injured)\b", lead, re.I):
        return None
    # Do not use a past incident quoted/reported in a later update as current news.
    if re.search(r'"|“|”|\b(?:last|previous|earlier|reportedly|had sustained)\b', lead, re.I):
        return None
    if re.search(r"\b(?:initially|later|but|returned|returning)\b|\b20\d{2}\b|"
                 r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
                 r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b|\d+/\d+", lead, re.I):
        return None  # An explicit calendar date needs its own parser, not weekday inference.
    if not re.search(r"\bdid not return(?: to (?:the )?game)?\b", lead, re.I):
        return None
    owner = " ".join(part for part in club_names[club] if part)
    ownership = (re.search(r"\bfor (?:the )?" + re.escape(owner) + r"\b", lead, re.I)
                 or (len(paragraphs) > 1 and re.match(
                     r"The " + re.escape(owner) + r" (?:forward|defenseman|goaltender)\b", paragraphs[1], re.I)))
    if not ownership:
        return None
    weekdays = re.findall(r"\bon (" + "|".join(WEEKDAYS) + r")\b", lead, re.I)
    if len(set(day.lower() for day in weekdays)) != 1:
        return None
    action_day = story.date.date() - timedelta(days=(story.date.weekday() - WEEKDAYS[weekdays[0].lower()]) % 7)
    return {"version": 1, "source_hash": snapshot(story)["content_hash"],
            "claims": [{"subject": pid, "club": club, "kind": "left_game", "modality": "confirmed",
                        "date": action_day.isoformat(), "evidence": "\n\n".join(paragraphs[:2])}],
            "actor_name": record["ru"], "club_name": teams[club], "club_alias": list(club_names[club])}


def report_packet(story, names: dict, teams: dict, club_names: dict) -> dict | None:
    """Only the unique headline actor in one explicitly owned section is selected."""
    def in_head(name):
        surname = re.split(r"[-\s]+", name)[-1]
        return bool(re.search(r"\b" + re.escape(surname) + r"\b", story.headline, re.I))
    actors = [pid for pid, name in story.en.items() if in_head(name)]
    if len(actors) != 1:
        return None
    pid = actors[0]
    sections = []
    for section in re.split(r"(?m)^#{1,6}\s+", story.text)[1:]:
        heading, _, text = section.partition("\n")
        if not re.search(r"\b" + re.escape(story.en[pid]) + r"\b", text, re.I):
            continue
        clubs = [club for club, alias in club_names.items()
                 if alias[1] and re.search(r"\b" + re.escape(alias[1]) + r"\b", heading, re.I)]
        if len(clubs) == 1:
            sections.append((clubs[0], text.strip()))
    if len(sections) != 1:
        return None
    club, text = sections[0]
    # The source is a league-wide report; bind only its first factual sentence
    # for this uniquely identified headline actor and club section. Later injury
    # history, stats and quotes must not leak into the new event.
    lead = text.split("\n\n")[0].strip()
    english = story.en[pid]
    subject = r"[-\s]+".join(re.escape(part) for part in re.split(r"[-\s]+", english))
    weekday = "(" + "|".join(WEEKDAYS) + ")"
    patterns = (
        ("season_debut", "confirmed", rf"{subject} made his season debut "
         rf"(?:for the {re.escape(club_names[club][1])} )?against .+? on {weekday}"),
        ("expected_debut", "expected",
         rf"{subject} is expected to make his season debut "
         rf"(?:for the {re.escape(club_names[club][1])} )?against .+? on {weekday}"),
        ("expected_debut", "expected",
         rf"{subject} could make his season debut "
         rf"(?:for the {re.escape(club_names[club][1])} )?against .+? on {weekday}"),
        ("expected_return", "expected",
         rf"{subject} will return to the lineup for (?:the )?{re.escape(club_names[club][1])} "
         rf"against .+? on {weekday}"),
    )
    for kind, modality, pattern in patterns:
        match = re.match(pattern + r"(?:\s*\([^)]*\))?[.,]?", lead, re.I)
        if not match:
            continue
        day_word = match[1].lower()
        target = WEEKDAYS[day_word]
        if modality == "expected":
            delta = (target - story.date.weekday()) % 7
            if delta > 3:
                continue
            action_day = story.date.date() + timedelta(days=delta)
        else:
            action_day = story.date.date() - timedelta(days=(story.date.weekday() - target) % 7)
        packet = {"version": 1, "source_hash": snapshot(story)["content_hash"],
                  "claims": [{"subject": pid, "club": club, "kind": kind, "modality": modality,
                              "date": action_day.isoformat(), "evidence": match[0].strip()}],
                  "actor_name": names[str(pid)]["ru"], "club_name": teams[club],
                  "club_alias": list(club_names[club])}
        return packet
    return None


def debut(story, pid, club, record, teams, club_names):
    """Explicit season debut, preserving expected versus completed action."""
    subject = r"[-\s]+".join(re.escape(p) for p in re.split(r"[-\s]+", story.en[pid]))
    city, nickname = club_names[club]
    club_name = r"(?:" + "|".join(re.escape(x) for x in (nickname, " ".join((city, nickname))) if x) + r")"
    lead = story.text.strip().split("\n\n")[0]
    if re.search(r"\b(?:but|not|cancelled|canceled|ruled out|setback|initially)\b|\b20\d{2}\b", lead, re.I):
        return None
    match = re.match(subject + r" (?P<action>made|will make|is expected to make|could make) his season debut "
                         r"(?:for (?:the )?" + club_name + r"\s+)?against [^.\n]+?\bon ("
                         + "|".join(WEEKDAYS) + r")(?:\s*\([^\n]*?\))?\.(?=\s|$)", lead, re.I)
    if not match:
        return None
    expected = match["action"].lower() != "made"
    weekday = WEEKDAYS[match[2].lower()]
    delta = (weekday - story.date.weekday()) % 7 if expected else -((story.date.weekday() - weekday) % 7)
    if expected and delta > 3:
        return None  # A stale weekday forecast must not silently roll into next week.
    return {"version": 1, "source_hash": snapshot(story)["content_hash"],
            "claims": [{"subject": pid, "club": club, "kind": "expected_debut" if expected else "season_debut",
                        "modality": "expected" if expected else "confirmed",
                        "date": (story.date.date() + timedelta(days=delta)).isoformat(), "evidence": match[0]}],
            "actor_name": record["ru"], "club_name": teams[club], "club_alias": list(club_names[club])}


def paired_injury(story, names, teams, club_names):
    """A narrow two-player injury lead: both named actors, one club and one dated game fact."""
    if story.kind not in ("injury", "injury_minor") or len(story.pids) != 2 or len(story.teams) != 1:
        return None
    club = next(iter(story.teams))
    if club not in teams or club not in club_names:
        return None
    lead = story.text.strip().split("\n\n")[0]
    if re.search(r"\b20\d{2}\b|\b(?:initially|later|returned|but)\b", lead, re.I):
        return None
    actors = []
    for pid in story.pids:
        english, record = story.en.get(pid), names.get(str(pid))
        if not english or not record or not record.get("ru") or english not in lead:
            return None
        actors.append((lead.index(english), pid, english, record["ru"]))
    actors.sort()
    (_, first, english_a, ru_a), (_, second, english_b, ru_b) = actors
    subject_a = r"[-\s]+".join(re.escape(x) for x in re.split(r"[-\s]+", english_a))
    subject_b = r"[-\s]+".join(re.escape(x) for x in re.split(r"[-\s]+", english_b))
    city, nickname = club_names[club]
    owner = r"(?:the\s+)?" + re.escape(" ".join(x for x in (city, nickname) if x))
    weekday = "(" + "|".join(WEEKDAYS) + ")"
    pattern = (rf"{subject_a}\s+and\s+{subject_b}\s+each sustained a lower-body injury "
               rf"in the second period of a \d+-\d+ (?:overtime )?loss for {owner} "
               rf"against .+? on {weekday}")
    match = re.match(pattern + r"[.,]?", lead, re.I)
    if not match:
        return None
    day_word = match[1].lower()
    action_day = story.date.date() - timedelta(days=(story.date.weekday() - WEEKDAYS[day_word]) % 7)
    evidence = match[0].strip()
    actor_names = {str(first): ru_a, str(second): ru_b}
    return {"version": 1, "source_hash": snapshot(story)["content_hash"],
            "claims": [{"subject": pid, "club": club, "kind": "injury_event", "modality": "confirmed",
                        "date": action_day.isoformat(), "evidence": evidence}
                       for pid in (first, second)],
            "actor_name": f"{ru_a} и {ru_b}", "actor_names": actor_names,
            "club_name": teams[club], "club_alias": list(club_names[club])}


def extract(story, names: dict, teams: dict, club_names: dict | None = None) -> dict | None:
    """One actor/club and explicit action wording only; multiple health events remain review."""
    if "status report" in story.headline.lower():
        return report_packet(story, names, teams, club_names or {})
    paired = paired_injury(story, names, teams, club_names or {})
    if paired:
        return paired
    if len(story.pids) != 1 or len(story.teams) != 1:
        return None
    if getattr(story, "kind", None) not in ("return", "injury", "injury_minor", "signing"):
        return None
    pid, club = next(iter(story.pids)), next(iter(story.teams))
    english = story.en.get(pid)
    record = names.get(str(pid))
    if not english or not record or not record.get("ru") or club not in teams:
        return None
    # Exact source spans are retained. A surname is safe only when unique in this document.
    surname = english.split()[-1]
    aliases = [english]
    if sum(name.split()[-1].lower() == surname.lower() for name in story.en.values()) == 1:
        aliases.append(surname)
    subject = r"(?:" + "|".join(re.escape(a) for a in aliases) + r")"
    if not club_names or club not in club_names:
        return None
    first_game = debut(story, pid, club, record, teams, club_names)
    if first_game:
        return first_game
    incident = left_game(story, pid, club, record, teams, club_names)
    if incident:
        return incident
    if re.search(r"\blast (?:season|year|month|week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
                 r"|previously expected|cancell?ed|no longer|ruled out|will not|won't|not expected|setback",
                 story.text, re.I):
        return None
    city, nickname = club_names[club]
    owner = re.escape(" ".join(part for part in (city, nickname) if part))
    if story.kind == "return":
        lead = story.text.strip().split("\n\n")[0]
        city_names = {city, "LA" if club == "LAK" else city}
        club_forms = "|".join(re.escape(" ".join(x for x in (name, nickname) if x))
                               for name in city_names)
        activation = re.fullmatch(r"(?:The\s+)?(?:" + club_forms + r")\s+have activated\s+"
                                 r"(?:forward\s+|defenseman\s+|goaltender\s+)?\*{0,2}" + re.escape(english) +
                                 r"\*{0,2}\s+from injured reserve(?:\s*\(IR\))?\.?", lead, re.I)
        if activation:
            return {"version": 1, "source_hash": snapshot(story)["content_hash"],
                    "claims": [{"subject": pid, "club": club, "kind": "activation", "modality": "confirmed",
                                "date": story.date.date().isoformat(), "evidence": activation[0]}],
                    "actor_name": record["ru"], "club_name": teams[club],
                    "club_alias": list(club_names[club])}
    if story.kind == "signing":
        lead = re.split(r"(?<=[.!?])\s+|\n\s*\n", story.text.strip())[0]
        contract = re.fullmatch(r"(?:The\s+)?" + owner + r"\s+announced\s+today\s+that\s+"
                               r"(?:forward\s+|defenseman\s+|goaltender\s+)?" + re.escape(english) +
                               r"\s+has signed\s+a\s+(one|two|three|four|five|six|seven|eight)[- ]year\s+"
                               r"(entry-level\s+)?contract\.?", lead, re.I)
        if not contract:
            return None
        years = ("one", "two", "three", "four", "five", "six", "seven", "eight").index(contract[1].lower()) + 1
        return {"version": 1, "source_hash": snapshot(story)["content_hash"],
                "claims": [{"subject": pid, "club": club, "kind": "signing", "modality": "confirmed",
                            "date": story.date.date().isoformat(), "years": years,
                            "phase": "entry_level" if contract[2] else "standard", "evidence": lead}],
                "actor_name": record["ru"], "club_name": teams[club], "club_alias": [city, nickname]}
    if not re.search(subject + r"\s+(?:is\s+)?(?:(?:likely|expected)\s+to\s+|could\s+|will\s+)?"
                     r"(?:return(?: to| for)|rejoin|practiced with|practices with|of)\s+(?:the\s+)?" + owner,
                     story.text, re.I):
        return None
    claims = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n\s*\n", story.text):
        sentence = sentence.strip().strip("*")
        # Do not interpret quotations, negatives or reported historical anecdotes as current action.
        if any(char in sentence for char in ('"', '“', '”')) or re.search(r"\bnot\b|\bno\b", sentence, re.I):
            continue
        match = re.search(r"\b" + subject + r"\s+(?:is\s+)?(?:(?:likely|expected)\s+to\s+|could\s+|will\s+)"
                          r"(?:return|rejoin)[^.\n]{0,180}?\bon\s+(" + "|".join(WEEKDAYS) + r")\b",
                          sentence, re.I)
        kind = "expected_return"
        if match and re.search(r"practice|training|skating|conditioning|\bice\b", match[0], re.I):
            match = None
        if not match:
            match = re.search(r"\b" + subject + r"\s+on\s+(" + "|".join(WEEKDAYS) + r")\s+"
                              r"(?:participated in|completed|took part in)\s+(?:his\s+)?"
                              r"(?:first\s+)?full\s+practice\b", sentence, re.I)
            kind = "practice"
        if not match:
            continue
        weekday = WEEKDAYS[match[1].lower()]
        delta = (weekday - story.date.weekday()) % 7 if kind == "expected_return" else -(
            (story.date.weekday() - weekday) % 7)
        if kind == "expected_return" and delta > 3:
            continue
        action_day = story.date.date() + timedelta(days=delta)
        claims.append({"subject": pid, "club": club, "kind": kind, "date": action_day.isoformat(),
                       "modality": "expected" if kind == "expected_return" else "confirmed",
                       "evidence": sentence})
    if not claims:
        return None
    # Contradictory dates or repeated extraction require a human decision, not first-match wins.
    for kind in {c["kind"] for c in claims}:
        if len({c["date"] for c in claims if c["kind"] == kind}) != 1:
            return None
    source = snapshot(story)
    return {"version": 1, "source_hash": source["content_hash"], "claims": claims,
            "actor_name": record["ru"], "club_name": teams[club], "club_alias": [city, nickname]}


def render(packet: dict) -> str:
    """No free model prose: every factual sentence consumes a typed claim."""
    claims = packet["claims"]
    expectation = next((c for c in claims if c["kind"] == "expected_return"), None)
    practice = next((c for c in claims if c["kind"] == "practice"), None)
    def day(claim):
        from datetime import date
        parsed = date.fromisoformat(claim["date"])
        return f"{parsed.day} {MONTHS[parsed.month - 1]}"
    if claims[0]["kind"] in ("season_debut", "expected_debut"):
        action = ("может впервые сыграть в сезоне" if claims[0]["kind"] == "expected_debut"
                  else "провёл первый матч в сезоне")
        return (f"{packet['actor_name']} {action} {day(claims[0])}\n\n"
                f"Команда — «{packet['club_name']}».")
    if claims[0]["kind"] == "injury_event":
        return (f"{packet['actor_name']} получили повреждения в матче {day(claims[0])}\n\n"
                f"Оба игрока выступают за «{packet['club_name']}».")
    if claims[0]["kind"] == "activation":
        return (f"{packet['actor_name']} активирован из списка травмированных {day(claims[0])}\n\n"
                f"Клуб «{packet['club_name']}» вернул игрока в состав.")
    if expectation:
        headline = f"{packet['actor_name']} может вернуться в состав {day(expectation)}"
    elif claims[0]["kind"] == "left_game":
        headline = f"{packet['actor_name']} не смог продолжить матч {day(claims[0])}"
        return headline + f"\n\nИгрок «{packet['club_name']}» покинул лёд и не вернулся в игру."
    elif practice:
        headline = f"{packet['actor_name']} провёл полноценную тренировку {day(practice)}"
    else:
        signing = claims[0]
        years = signing["years"]
        label = "контракт новичка" if signing["phase"] == "entry_level" else "контракт"
        headline = (f"{packet['actor_name']} подписал {label} с «{packet['club_name']}» "
                    f"на {years} {plural(years, ('год', 'года', 'лет'))}")
        return headline + f"\n\nКлуб объявил о подписании {day(signing)}."
    body = f"Команда — «{packet['club_name']}»."
    if expectation and practice:
        body = f"{day(practice)} провёл полноценную тренировку с командой «{packet['club_name']}»."
    return headline + "\n\n" + body


def revision(packet: dict) -> dict:
    """Use the existing ledger, with modality preserved in phase/facts."""
    main = next((c for c in packet["claims"] if c["kind"] == "expected_return"), packet["claims"][0])
    signing = main["kind"] == "signing"
    actors = sorted({claim["subject"] for claim in packet["claims"]})
    return {"version": 1, "family": "signing" if signing else "health", "actors": actors,
            "clubs": [main["club"]], "effective_date": main["date"],
            "date_basis": ("explicit" if signing else
                           ("publication_date" if main["kind"] == "activation" else "action_weekday")),
            "phase": (main["phase"] if signing else
                      {"season_debut": "return", "expected_debut": "expected_return",
                       "activation": "activated", "injury_event": "injury"}.get(main["kind"], main["kind"])),
            "facts": ({"years": main["years"]} if signing else
                      {"modality": main["modality"], **({"action": main["kind"]}
                       if main["kind"] in ("season_debut", "expected_debut", "injury_event") else {})}),
            "complete": True, "reasons": [], "references": []}


def caption(packet: dict, source: dict, msk: str) -> str:
    """The public caption is rendered once by the same pure contract used before sending."""
    from datetime import date
    parsed = date.fromisoformat(msk)
    head, _, body = render(packet).partition("\n\n")
    signing = packet["claims"][0]["kind"] == "signing"
    injury = packet["claims"][0]["kind"] in ("left_game", "injury_event")
    debut = packet["claims"][0]["kind"] in ("season_debut", "expected_debut")
    emoji, tag = (("✍️", "#Контракты") if signing else
                  (("🚑", "#Травмы") if injury else
                   (("🏒", "#Дебюты") if debut else ("✅", "#Возвращения"))))
    return (f"{emoji} <b>{html.escape(head)}</b>\n\n{html.escape(body)}\n\n"
            f"🔗 <a href=\"{html.escape(source['url'], quote=True)}\">NHL.com</a>\n"
            f"⚡ {tag} · {parsed.day} {MONTHS[parsed.month - 1]}")


def expires_at(packet: dict) -> str | None:
    """Forecast until its stated day ends; dated practice/game news through the following day."""
    from datetime import date, datetime, time, timezone
    main = next((c for c in packet["claims"] if c["kind"] == "expected_return"), packet["claims"][0])
    if main["kind"] == "signing":
        return None
    days = 1 if main["kind"] in ("expected_return", "expected_debut") else 2
    return datetime.combine(date.fromisoformat(main["date"]) + timedelta(days=days), time.min,
                            timezone(timedelta(hours=3))).isoformat()


def card_spec(packet: dict) -> dict:
    """Render inputs come from the same claims as the caption, never from word matching."""
    claim = packet["claims"][0]
    kind = claim["kind"]
    label = ("КОНТРАКТ" if kind == "signing" else
             ("ТРАВМА" if kind in ("left_game", "injury_event") else
              ("ДЕБЮТ" if kind in ("season_debut", "expected_debut") else "ВОЗВРАЩЕНИЕ")))
    actor_ids = sorted({item["subject"] for item in packet["claims"]})
    return {"version": 1, "hero_id": actor_ids[0] if len(actor_ids) == 1 else actor_ids,
            "hero": packet["actor_name"],
            "teams": [claim["club"]], "headline": render(packet).partition("\n\n")[0],
            "label": label}


def verify(packet: dict, source: dict, body: str) -> list[str]:
    """Validate the supported contract, not just the presence of numbers or names."""
    if not isinstance(packet, dict) or not isinstance(source, dict):
        return ["неверная схема пакета фактов"]
    claims = packet.get("claims")
    if (not isinstance(claims, list) or not claims or any(not isinstance(c, dict) for c in claims)
            or any(c.get("kind") not in ("practice", "expected_return", "signing", "left_game",
                                          "season_debut", "expected_debut", "activation", "injury_event")
                   for c in claims)):
        return ["нет поддержанных утверждений"]
    required = ("subject", "club", "kind", "date", "modality", "evidence")
    if any(any(field not in c for field in required) or type(c["subject"]) is not int
           or not isinstance(c["evidence"], str) for c in claims):
        return ["неполный контракт утверждения"]
    if any(not isinstance(packet.get(field), str) for field in ("actor_name", "club_name")):
        return ["нет подтверждённых имён"]
    try:
        rendered = render(packet)
    except (KeyError, ValueError, TypeError, IndexError):
        return ["неверные параметры утверждения"]
    if packet.get("version") != 1 or packet.get("source_hash") != source.get("content_hash"):
        return ["версия фактов не соответствует источнику"]
    actual = source_hash(source)
    if actual != source.get("content_hash"):
        return ["сохранённый источник изменён"]
    if any(c.get("evidence", "") not in source.get("text", "") or not c.get("evidence")
           for c in packet.get("claims", [])):
        return ["для факта нет сохранённого доказательства"]
    if body != rendered:
        return ["текст изменён вне проверенного шаблона"]
    try:
        original = restore(source)
        claims = packet["claims"]
        club = claims[0]["club"]
        actor_names = packet.get("actor_names") or {str(claims[0]["subject"]): packet["actor_name"]}
        names = {str(claim["subject"]): {"ru": actor_names[str(claim["subject"])]} for claim in claims}
        rebuilt = extract(original, names, {club: packet["club_name"]}, {club: packet["club_alias"]})
    except (KeyError, TypeError, ValueError, IndexError):
        return ["неполный контракт фактов/источника"]
    if rebuilt != packet:
        return ["утверждения не соответствуют повторному разбору доказательств"]
    return []

