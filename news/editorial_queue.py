"""Durable editorial lifecycle, independent of feed processing and notification delivery."""

import copy
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from news import editorial_lifecycle


def fingerprint(draft: dict) -> str:
    """Bind decisions to content, facts and actual image bytes, never delivery metadata."""
    card = draft.get("card")
    image = hashlib.sha256(Path(card).read_bytes()).hexdigest() if card and Path(card).is_file() else card
    payload = {key: draft.get(key) for key in ("text", "issues", "variant", "data")}
    payload["data"] = copy.deepcopy(payload["data"])
    if isinstance(payload["data"], dict) and isinstance(payload["data"].get("source_snapshot"), dict):
        payload["data"]["source_snapshot"].pop("fetched_at", None)
    payload["card"] = image
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def decision(draft: dict, automatic: bool = False, kind: str | None = None) -> tuple[str, list[str]]:
    """One policy for CLI, callbacks and auto; publication ledger remains authoritative for duplicates."""
    if draft.get("editorial_closed"):
        return "closed", [draft["editorial_closed"].get("reason", "закрыто редактором")]
    if draft.get("rejected"):
        return "rejected", ["черновик отклонён"]
    if kind is not None:
        status, reasons = editorial_lifecycle.classify(draft, kind)
        if status != "ready":
            return status, reasons
    if draft.get("issues"):
        return "blocked", list(draft["issues"])
    data = draft.get("data") or {}
    if not isinstance(data, dict):
        return "blocked", ["неверная схема данных черновика"]
    expiry = data.get("expires_at")
    if expiry:
        try:
            expired = datetime.fromisoformat(expiry) <= datetime.now(timezone.utc)
        except (ValueError, TypeError):
            return "blocked", ["неверный срок актуальности"]
        if expired:
            return "expired", ["срок актуальности истёк"]
    if automatic and not data.get("auto", True):
        reasons = data.get("event_decision", {}).get("reasons") or ["требуется редакторская проверка"]
        return "needs_review", reasons
    return "ready", []


class Queue:
    """Additive SQLite tables; old JSON drafts can be indexed without sending anything."""

    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS editorial_tasks (
            name TEXT PRIMARY KEY, revision TEXT NOT NULL, status TEXT NOT NULL,
            reasons TEXT NOT NULL, notified TEXT, updated TEXT NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS editorial_history (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, revision TEXT NOT NULL,
            status TEXT NOT NULL, at TEXT NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS editorial_documents (
            name TEXT PRIMARY KEY, source TEXT NOT NULL, source_hash TEXT NOT NULL, observed TEXT NOT NULL)""")

    def close(self):
        self.db.close()

    def sync(self, name: str, draft: dict) -> str:
        revision = fingerprint(draft)
        kind = name.split("_", 1)[1].removesuffix(".json") if "_" in name else None
        status, reasons = decision(draft, automatic=True, kind=kind)
        metadata = draft.get("data") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        published = draft.get("published") or []
        targets = draft.get("delivery_targets") or ["tg"]
        if published:
            status = "published" if set(targets) <= set(published) else "partial_delivery"
        previous = self.db.execute("SELECT revision, status FROM editorial_tasks WHERE name=?", (name,)).fetchone()
        if previous and previous[1] == "delivery_unknown" and status != "published":
            status = "delivery_unknown"
        if previous and previous[0] == revision:
            # Preserve unresolved delivery and manual decisions through restart.
            if previous[1] in ("delivery_unknown", "approved", "superseded") and status not in (
                    "published", "rejected", "expired", "closed", "blocked", "legacy_review", "needs_revalidation"):
                status = previous[1]
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            source = metadata.get("source_snapshot") or {}
            if not isinstance(source, dict):
                source = {}
            if source.get("url") and source.get("content_hash") and source.get("fetched_at"):
                try:
                    stamp = datetime.fromisoformat(source["fetched_at"])
                    if stamp.tzinfo is None:
                        raise ValueError("snapshot needs timezone")
                    observed = stamp.astimezone(timezone.utc).isoformat()
                except (TypeError, ValueError):
                    status, reasons = "blocked", ["неверное время версии источника"]
                    observed = ""
                if not observed:
                    source = {}
            if source.get("url") and source.get("content_hash") and source.get("fetched_at"):
                self.db.execute("INSERT OR REPLACE INTO editorial_documents VALUES (?,?,?,?)",
                                (name, source["url"], source["content_hash"], observed))
                newer = self.db.execute(
                    "SELECT 1 FROM editorial_documents WHERE source=? AND observed>? AND source_hash<>?",
                    (source["url"], observed, source["content_hash"])).fetchone()
                if newer and status not in ("published", "rejected", "delivery_unknown", "closed"):
                    status = "superseded"
                self.db.execute("UPDATE editorial_tasks SET status='superseded' WHERE name IN "
                                "(SELECT name FROM editorial_documents "
                                "WHERE source=? AND observed<? AND source_hash<>?) "
                                "AND status NOT IN ('published','rejected','delivery_unknown','closed')",
                                (source["url"], observed, source["content_hash"]))
            self.db.execute("""INSERT INTO editorial_tasks VALUES (?,?,?,?,NULL,?)
                ON CONFLICT(name) DO UPDATE SET revision=excluded.revision,status=excluded.status,
                reasons=excluded.reasons,
                updated=CASE WHEN editorial_tasks.revision=excluded.revision
                    AND editorial_tasks.status=excluded.status THEN editorial_tasks.updated ELSE excluded.updated END,
                notified=CASE WHEN editorial_tasks.revision=excluded.revision
                    THEN editorial_tasks.notified ELSE NULL END""",
                            (name, revision, status, json.dumps(reasons, ensure_ascii=False), now))
            if previous != (revision, status):
                self.db.execute("INSERT INTO editorial_history(name,revision,status,at) VALUES (?,?,?,?)",
                                (name, revision, status, now))
        return revision

    def status(self, name: str) -> str | None:
        row = self.db.execute("SELECT status FROM editorial_tasks WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    def mark(self, name: str, revision: str, status: str):
        if status not in ("approved", "published", "delivery_unknown", "rejected"):
            raise ValueError("Неизвестный переход редакционной очереди")
        with self.db:
            changed = self.db.execute("UPDATE editorial_tasks SET status=? WHERE name=? AND revision=?",
                                      (status, name, revision)).rowcount
            if not changed:
                raise ValueError("Версия задачи изменилась")
            self.db.execute("INSERT INTO editorial_history(name,revision,status,at) VALUES (?,?,?,?)",
                            (name, revision, status, datetime.now(timezone.utc).isoformat()))

    def notified(self, name: str, revision: str, write: bool = False) -> bool:
        if write:
            with self.db:
                self.db.execute("UPDATE editorial_tasks SET notified=? WHERE name=? AND revision=?",
                                (revision, name, revision))
        row = self.db.execute("SELECT notified FROM editorial_tasks WHERE name=? AND revision=?",
                              (name, revision)).fetchone()
        return bool(row and row[0] == revision)

    def pending(self) -> list[dict]:
        fields = ("name", "revision", "status", "reasons", "updated")
        return [dict(zip(fields, row)) for row in self.db.execute(
            "SELECT name,revision,status,reasons,updated FROM editorial_tasks "
            "WHERE status NOT IN ('published','rejected','superseded','closed') ORDER BY updated")]
