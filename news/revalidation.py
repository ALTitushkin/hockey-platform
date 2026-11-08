"""Explicit refresh of one review task; never publishes or silently clears a decision."""

import json
import uuid
from datetime import datetime

from news import editorial_queue, event_registry, fact_packet, publish, stories, story_validation


def refresh(msk: str, kind: str, expected: str, now: datetime, fetch, registry: dict,
            teams: dict, wiki) -> tuple[bool, str]:
    path = publish.draft_path(msk, kind)
    original = json.loads(path.read_text(encoding="utf-8"))

    def unchanged():
        current = json.loads(path.read_text(encoding="utf-8"))
        if editorial_queue.fingerprint(current)[:16] != expected:
            raise ValueError("Версия изменилась: откройте новое ревью")
        if current.get("published") or current.get("rejected") or current.get("editorial_closed"):
            raise ValueError("Материал уже опубликован или закрыт")
        queue = editorial_queue.Queue(publish.OUT / "editorial.sqlite3")
        try:
            if queue.status(path.name) in ("delivery_unknown", "sending", "superseded"):
                raise ValueError("Задача заменена либо доставка требует сверки")
        finally:
            queue.close()
        if (publish.OUT / "event_registry.sqlite3").exists():
            ledger = event_registry.Registry(publish.OUT / "event_registry.sqlite3")
            try:
                if ledger.db.execute("SELECT 1 FROM publications WHERE document=? "
                                     "AND status IN ('published','sending','uncertain')", (path.name,)).fetchone():
                    raise ValueError("Сначала сверить предыдущую доставку в реестре")
            finally:
                ledger.close()

    unchanged()
    if not kind.startswith("story-"):
        return False, "Перепроверка доступна для инфоповодов"
    slug = original.get("data", {}).get("slug")
    # Fetch current feed metadata; stale article dates must not be advanced to now.
    raw = next((item for item in fetch(stories.FEED).get("items", []) if item.get("slug") == slug), None)
    if raw is None:
        return False, "Источник отсутствует в текущей ленте; автоматическая перепроверка недоступна"
    story = stories.parse_item(raw)
    if story is None:
        return False, "Источник больше не соответствует поддержанному сценарию"
    story.text, story.en = stories.body_text(fetch(story.url))
    story.mentioned = set(story.en)
    names = wiki(story.pids | story.mentioned, registry)
    packet = fact_packet.extract(story, names, teams, stories.TEAM_EN)
    if packet is None:
        return False, "Источник получен, но факт/дата/клуб не разобраны однозначно. Публикация не разрешена"
    source = fact_packet.snapshot(story)
    source["fetched_at"] = now.isoformat()
    errors = fact_packet.verify(packet, source, fact_packet.render(packet))
    if errors:
        return False, "; ".join(errors)
    revision = fact_packet.revision(packet)
    ledger = event_registry.Registry(publish.OUT / "event_registry.sqlite3")
    try:
        ledger.sync_archive(publish.OUT)
        decision = ledger.classify(revision)
    finally:
        ledger.close()
    if decision["status"] not in ("new", "update"):
        return False, "Факт уже опубликован либо прежняя доставка требует сверки"
    unchanged()  # CAS after I/O: an old callback must not overwrite a newer decision.
    publication_date = now.date().isoformat()
    pic = stories.card(story, fact_packet.render(packet), names, {int(pid) for pid in registry}, [], teams,
                       publication_date, publish.OUT / f"{msk}_{kind}-rev-{uuid.uuid4().hex}.png", packet=packet)
    data = {"slug": slug, "auto": True, "publication_date": publication_date,
            "source_snapshot": source, "fact_packet": packet,
            "packet_hash": fact_packet.key(packet), "event_revision": revision, "event_decision": decision,
            "card_spec": fact_packet.card_spec(packet), "card_hash": story_validation.image_hash(pic),
            "source_event": {"kind": story.kind, "pids": sorted(story.pids), "teams": sorted(story.teams),
                             "headline": story.headline, "date": story.date.isoformat(), "text": story.text,
                             "en": story.en}}
    expiry = fact_packet.expires_at(packet)
    if expiry:
        data["expires_at"] = expiry
    unchanged()  # Rendering can perform asset I/O; never overwrite the old image or decision.
    # Same task, new evidence-bound version. Explicit refresh is never an auto-send.
    publish.save_draft(msk, fact_packet.caption(packet, source, publication_date), [], "перепроверено по источнику",
                       str(pic), kind=kind, data=data)
    return True, "Источник перепроверен; откройте новую версию. Пост не отправлен"
