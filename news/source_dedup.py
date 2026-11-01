"""Дедуп теневого сбора. Наблюдение источника не является подтверждением публикации."""

import hashlib
import json
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Нужна HTTP(S) ссылка без credentials")
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(query), ""))


def fingerprint(text: str) -> str:
    """Сохраняем числа, отрицания и пунктуацию: обновлённый срок не является дублем."""
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()
    return hashlib.sha256(normalized.encode()).hexdigest()


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class Event:
    """Только явно установленные сущности/действие/эпизод, без сходства заголовков.

    entities: NHL ID с типом (player:8481611), episode: дата/ID конкретного события.
    facts включает статус expected/confirmed, сроки, суммы и участников, если они известны.
    Исправление/отзыв старого сообщения включает отдельный revision: повтор старой версии — дубль.
    Разные модели/периоды аналитики должны иметь разные action/episode.
    """

    entities: tuple[str, ...]
    action: str
    episode: str
    facts: dict

    def key(self) -> str:
        if not self.entities or not all(self.entities) or not self.action or not self.episode or not self.facts:
            raise ValueError("Неполное событие нельзя использовать для подавления дублей")
        return _json([sorted(set(self.entities)), self.action, self.episode])


@dataclass(frozen=True)
class Decision:
    kind: str  # new / duplicate / update
    cluster_id: int
    reason: str


class Ledger:
    """SQLite-транзакция хранит все версии и ссылки, включая повторные документы."""

    def __init__(self, path, clock=time.time):
        self.clock = clock
        self.db = sqlite3.connect(path, timeout=10)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS clusters(id INTEGER PRIMARY KEY, event_key TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS versions(cluster_id INTEGER, digest TEXT, facts TEXT, observed_at REAL,
                UNIQUE(cluster_id, digest, facts));
            CREATE TABLE IF NOT EXISTS documents(source TEXT, item_id TEXT, url TEXT, digest TEXT,
                cluster_id INTEGER, PRIMARY KEY(source, item_id));
            CREATE TABLE IF NOT EXISTS document_urls(url TEXT, cluster_id INTEGER, UNIQUE(url, cluster_id));
            CREATE INDEX IF NOT EXISTS document_url ON documents(url);
            CREATE INDEX IF NOT EXISTS version_digest ON versions(digest);
        """)

    def close(self):
        self.db.close()

    def observe(self, source: str, item_id: str, url: str, text: str, event: Event | None = None) -> Decision:
        if not source or not item_id or not text.strip():
            raise ValueError("Нужны source, item_id и содержательный текст")
        url, digest = canonical_url(url), fingerprint(text)
        key, facts = (event.key(), _json(event.facts)) if event else (None, "")
        now = self.clock()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            # Событие имеет приоритет над URL: одна сводная страница содержит разные события.
            row = self.db.execute("SELECT id FROM clusters WHERE event_key=?", (key,)).fetchone() if key else None
            reason = "event" if row else "document"
            if row is None and key is None:
                row = self.db.execute("SELECT cluster_id FROM documents WHERE source=? AND item_id=?",
                                      (source, item_id)).fetchone()
                if row is None:
                    history = self.db.execute("SELECT MIN(cluster_id), COUNT(DISTINCT cluster_id) "
                                              "FROM document_urls WHERE url=?", (url,)).fetchone()
                    row = (history[0],) if history[1] == 1 else None
                if row is None:
                    row = self.db.execute("SELECT cluster_id FROM versions WHERE digest=? AND observed_at>=? "
                                          "ORDER BY observed_at DESC LIMIT 1", (digest, now - 3 * 86400)).fetchone()
            if row is None:
                cluster = self.db.execute("INSERT INTO clusters(event_key) VALUES (?)", (key,)).lastrowid
                kind = "new"
            else:
                cluster = row[0]
                field, value = ("facts", facts) if event else ("digest", digest)
                same = self.db.execute(f"SELECT 1 FROM versions WHERE cluster_id=? AND {field}=?",
                                       (cluster, value)).fetchone()
                kind = "duplicate" if same else "update"
            self.db.execute("INSERT OR IGNORE INTO versions VALUES (?,?,?,?)", (cluster, digest, facts, now))
            self.db.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?)",
                            (source, item_id, url, digest, cluster))
            self.db.execute("INSERT OR IGNORE INTO document_urls VALUES (?,?)", (url, cluster))
        return Decision(kind, cluster, reason)
