"""Persistent, conservative event revisions and at-most-once publication claims.

An actor is a relation key, never a reason to discard a story. Only complete,
identical event facts can suppress publication. Unknown facts require review.
"""

import hashlib
import json
import re
import sqlite3
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

WEEKDAYS = dict(zip("monday tuesday wednesday thursday friday saturday sunday".split(), range(7)))
NUMBERS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve"
                                    " thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def revision_key(event):
    payload = {k: event[k] for k in ("family", "actors", "clubs", "effective_date", "phase", "facts")}
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def topic_key(event):
    return canonical({k: event[k] for k in ("family", "actors", "clubs")})


def complete(event):
    if not isinstance(event, dict) or event.get("complete") is not True or event.get("version") != 1:
        return False
    if event.get("family") not in ("signing", "health") or not isinstance(event.get("facts"), dict):
        return False
    if not isinstance(event.get("actors"), list) or len(event["actors"]) != 1:
        return False
    if type(event["actors"][0]) is not int or event["actors"][0] <= 0:
        return False
    if not isinstance(event.get("clubs"), list) or len(event["clubs"]) != 1:
        return False
    if not isinstance(event["clubs"][0], str) or not re.fullmatch(r"[A-Z]{3}", event["clubs"][0]):
        return False
    from datetime import date
    try:
        date.fromisoformat(event["effective_date"])
    except (ValueError, TypeError, KeyError):
        return False
    allowed = {"signing": {"pto", "standard", "entry_level", "terminated"},
               "health": {"surgery", "practice", "activated", "return", "left_game", "unavailable"}}
    return (isinstance(event.get("phase"), str) and event["phase"] in allowed[event["family"]]
            and not event.get("reasons")
            and event.get("date_basis") in ("explicit", "action_weekday"))


def links(text):
    result = set()
    for url in re.findall(r'https://[^\s)<>"\]]+', text):
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.hostname in ("nhl.com", "www.nhl.com"):
            result.add(parsed.path.rstrip("/").split("/")[-1])
    return result


def extract(story):
    family = "health" if story.kind in ("injury", "injury_minor", "return") else story.kind
    lead = next((p.strip() for p in story.text.splitlines() if p.strip() and not p.startswith("#")), "")
    scope = f"{story.headline}\n{lead}".lower()
    head = story.headline.lower()
    facts, phase = {}, "unknown"
    if family == "signing":
        if re.search(r"\breleased?\b|\bterminat", head):
            phase = "terminated"
        elif re.search(r"\bpto\b|professional tryout", scope):
            phase = "pto"
        elif "entry-level" in scope:
            phase = "entry_level"
        elif re.search(r"sign|contract|extension|agrees?", scope):
            phase = "standard"
        term = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight)[- ]year", scope)
        if term:
            value = term[1]
            facts["years"] = int(value) if value.isdigit() else NUMBERS[value]
        money = re.findall(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(million|thousand)?", scope)
        if money:
            from decimal import Decimal
            facts["amounts"] = sorted({format((Decimal(n.replace(",", "")) *
                                              {"million": 1000000, "thousand": 1000, "": 1}[unit]).normalize(), "f")
                                       for n, unit in money})
    elif family == "health":
        for pattern, value in ((r"\b(?:surgery|operation)\b", "surgery"),
                               (r"return.*practice|resume.*skat", "practice"),
                               (r"\bactivat", "activated"), (r"\breturn", "return"),
                               (r"\bleav|\bleft", "left_game"),
                               (r"\bout\b|\bmiss|day.to.day|week.to.week|injur", "unavailable")):
            if re.search(pattern, head):
                phase = value
                break
        for region in ("upper", "lower"):
            if re.search(rf"\b{region}[- ]body\b", scope):
                facts["region"] = region
        for diagnosis in ("concussion", "fracture"):
            if diagnosis in scope:
                facts["diagnosis"] = diagnosis
        if re.search(r"did not return|not return", scope):
            facts["did_not_return"] = True
        for state in ("day-to-day", "week-to-week", "indefinitely"):
            if state in scope:
                facts["availability"] = state
        number = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
        duration = re.search(rf"\b{number}(?:\s*(?:-|–|to)\s*{number})?[- ]+(days?|weeks?|months?)\b", scope)
        if duration:
            def numeric(value):
                return int(value) if value.isdigit() else NUMBERS[value]
            facts["duration"] = {"min": numeric(duration[1]), "max": numeric(duration[2] or duration[1]),
                                 "unit": duration[3].rstrip("s")}
    day, basis = story.date.date(), "publication"
    # Date belongs to the action clause, not an incidental practice mentioned earlier.
    dated = re.search(r"(?:signed|signs|acquired|traded|injured|left|returned|announced)(?:[^.\n]|\.(?=\d)){0,240}?"
                      r"\b(?:on )?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", scope)
    explicit = re.search(r"(?:signed|signs|acquired|traded|injured|left|returned|announced)"
                         r"(?:[^.\n]|\.(?=\d)){0,240}?\b(20\d\d-\d\d-\d\d)\b", lead.lower())
    if dated:
        day -= timedelta(days=(day.weekday() - WEEKDAYS[dated[1]]) % 7)
        basis = "action_weekday"
    elif explicit:
        from datetime import date
        try:
            day = date.fromisoformat(explicit[1])
            basis = "explicit"
        except ValueError:
            pass
    reasons = []
    if len(story.pids) != 1 or len(story.teams) != 1:
        reasons.append("неоднозначные участники/клуб события")
    if family not in ("signing", "health") or phase == "unknown":
        reasons.append("неподдержанное или неустановленное действие")
    if phase in ("standard", "entry_level") and "years" not in facts:
        reasons.append("неполные условия контракта")
    if basis == "publication":
        reasons.append("дата события не отделена от даты статьи")
    if re.search(r"\bcould\b|\bmight\b|\bmay\b|questionable|expected", head) or ("looking to" in head and not dated):
        reasons.append("прогноз/обзор, а не подтверждённый переход")
    if "status report" in head:
        reasons.append("многособытийная сводка требует выбора одного факта")
    # Do not suppress an entire article because its opening repeats an old event.
    # Unbound new state/medical/contract facts later in the article need review;
    # they must not be silently assigned to the headline player or discarded.
    tail = story.text.partition(lead)[2].lower() if lead else ""
    if family == "health":
        attributes = {"upper-body", "lower-body", "concussion", "fracture", "day-to-day", "week-to-week"}
        new_attributes = {a for a in attributes if a in tail and a not in scope}
        new_duration = re.search(rf"\b{number}(?:\s*(?:-|–|to)\s*{number})?[- ]+(days?|weeks?|months?)\b", tail)
        changed_duration = new_duration and new_duration.group() not in scope
        new_transition = re.search(r"\b(?:surgery|activated|cleared|returned|diagnosed)\b", tail)
        if new_attributes or changed_duration or new_transition:
            reasons.append("вне вводного абзаца есть несопоставленные факты о состоянии игрока")
    elif family == "signing":
        if re.search(r"\b(?:released|terminated|waived|full-time|extension)\b|\$|"
                     r"\b(?:\d+|one|two|three|four|five|six|seven|eight)[- ]year", tail):
            reasons.append("вне вводного абзаца есть несопоставленные условия/переходы контракта")
    return {"version": 1, "family": family, "actors": sorted(story.pids), "clubs": sorted(story.teams),
            "effective_date": day.isoformat(), "date_basis": basis, "phase": phase, "facts": facts,
            "complete": not reasons, "reasons": reasons}


class Registry:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS documents(
              id TEXT PRIMARY KEY, slug TEXT, event TEXT, evidence TEXT);
            CREATE INDEX IF NOT EXISTS documents_slug ON documents(slug);
            CREATE TABLE IF NOT EXISTS revisions(
              id TEXT PRIMARY KEY, topic TEXT NOT NULL, event TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS revisions_topic ON revisions(topic);
            CREATE TABLE IF NOT EXISTS publications(
              revision TEXT NOT NULL REFERENCES revisions(id), channel TEXT NOT NULL,
              document TEXT NOT NULL, status TEXT NOT NULL, messages TEXT,
              PRIMARY KEY(revision,channel));
            CREATE TABLE IF NOT EXISTS archive_files(path TEXT PRIMARY KEY, stamp TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS resolutions(
              revision TEXT, channel TEXT, outcome TEXT, note TEXT, resolved_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)

    def close(self):
        self.db.close()

    def register(self, document, slug, event, evidence):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO documents VALUES(?,?,?,?)",
                            (document, slug, canonical(event) if event else None, canonical(evidence)))
            if complete(event):
                self.db.execute("INSERT OR IGNORE INTO revisions VALUES(?,?,?)",
                                (revision_key(event), topic_key(event), canonical(event)))

    def bind_reference(self, event, text):
        related = []
        for slug in links(text):
            rows = self.db.execute("SELECT event FROM documents WHERE slug=? AND event IS NOT NULL", (slug,))
            for (raw,) in rows:
                previous = json.loads(raw)
                if complete(previous) and topic_key(previous) == topic_key(event):
                    receipt = self.db.execute("SELECT 1 FROM publications WHERE revision=? AND status='published'",
                                              (revision_key(previous),)).fetchone()
                    if receipt:
                        related.append(previous)
        # A backlink alone cannot date a fresh injury or contract. Keep uncertainty
        # explicit; links establish relationships, not equality of event revisions.
        return {**event, "references": sorted({revision_key(e) for e in related})}

    def classify(self, event):
        if not complete(event):
            return {"status": "review", "reasons": event.get("reasons", [])}
        key = revision_key(event)
        published = self.db.execute("SELECT document,status FROM publications WHERE revision=?", (key,)).fetchall()
        if any(row[1] == "published" for row in published):
            return {"status": "duplicate", "documents": [row[0] for row in published]}
        if published:
            return {"status": "review", "reasons": ["исход предыдущей отправки этой версии требует сверки"]}
        rows = self.db.execute("SELECT event FROM revisions WHERE topic=? AND id<>?", (topic_key(event), key))
        related = [json.loads(raw) for (raw,) in rows]
        updated = any(e["effective_date"] == event["effective_date"] for e in related) or bool(event.get("references"))
        return {"status": "update" if updated else "new", "related": len(related)}

    def sync_archive(self, out):
        for path in out.glob("????-??-??_story-*.json"):
            try:
                stat = path.stat()
            except OSError:
                continue
            stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
            old = self.db.execute("SELECT stamp FROM archive_files WHERE path=?", (path.name,)).fetchone()
            if old and old[0] == stamp:
                continue
            try:
                if path.stat().st_size > 128 * 1024:
                    continue
                draft = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(draft, dict) or not isinstance(draft.get("data"), dict):
                continue
            data = draft["data"]
            event = data.get("event_revision")
            self.register(path.name, data.get("slug"), event, data.get("source_event", {}))
            receipts = draft.get("event_receipts", {})
            if not isinstance(receipts, dict):
                continue
            for target, receipt in receipts.items():
                if target not in ("tg", "max") or not isinstance(receipt, dict):
                    continue
                frozen = receipt.get("event")
                channel = receipt.get("channel")
                if not complete(frozen) or not isinstance(channel, str) or not channel.startswith(f"{target}:"):
                    continue
                with self.db:
                    self.db.execute("INSERT OR IGNORE INTO revisions VALUES(?,?,?)",
                                    (revision_key(frozen), topic_key(frozen), canonical(frozen)))
                    self.db.execute("INSERT OR IGNORE INTO publications VALUES(?,?,?,?,?)",
                                    (revision_key(frozen), channel, path.name, "published",
                                     canonical(receipt.get("messages", []))))
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO archive_files VALUES(?,?)", (path.name, stamp))

    def reserve(self, event, channel, document):
        if not complete(event):
            raise ValueError("Only complete event facts can acquire a publication claim")
        key = revision_key(event)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO revisions VALUES(?,?,?)",
                            (key, topic_key(event), canonical(event)))
            inserted = self.db.execute("INSERT OR IGNORE INTO publications VALUES(?,?,?,?,?)",
                                       (key, channel, document, "sending", "[]")).rowcount
            row = self.db.execute("SELECT document,status,messages FROM publications WHERE revision=? AND channel=?",
                                  (key, channel)).fetchone()
        if inserted:
            return "new", []
        if row[1] == "verified_not_sent":
            with self.db:
                acquired = self.db.execute("UPDATE publications SET document=?,status='sending',messages='[]' "
                                           "WHERE revision=? AND channel=? AND status='verified_not_sent'",
                                           (document, key, channel)).rowcount
            return ("new" if acquired else "uncertain"), []
        if row[0] == document and row[1] == "published":
            return "done_own", json.loads(row[2])
        return ("duplicate" if row[1] == "published" else "uncertain"), json.loads(row[2])

    def finish(self, event, channel, success, messages):
        with self.db:
            self.db.execute("UPDATE publications SET status=?,messages=? WHERE revision=? AND channel=?",
                            ("published" if success else "uncertain", canonical(messages),
                             revision_key(event), channel))

    def resolve(self, event, channel, *, sent, messages, note):
        """Operator-only reconciliation after checking the actual channel history.

        No automatic expiry/retry of ambiguous network effects is safe.
        """
        if type(sent) is not bool or not isinstance(note, str) or not note.strip():
            raise ValueError("Explicit outcome and verification note required")
        if not isinstance(messages, list) or any(type(mid) is not int or mid <= 0 for mid in messages):
            raise ValueError("Invalid message IDs")
        if sent != bool(messages):
            raise ValueError("Sent requires message IDs; not-sent requires an empty list")
        with self.db:
            changed = self.db.execute("UPDATE publications SET status=?,messages=? "
                                      "WHERE revision=? AND channel=? AND status IN ('sending','uncertain')",
                                      ("published" if sent else "verified_not_sent", canonical(messages),
                                       revision_key(event), channel)).rowcount
            if changed != 1:
                raise ValueError("No unresolved publication claim")
            self.db.execute("INSERT INTO resolutions(revision,channel,outcome,note) VALUES(?,?,?,?)",
                            (revision_key(event), channel, "sent" if sent else "not_sent", note))
