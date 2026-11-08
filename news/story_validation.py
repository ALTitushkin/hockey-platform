"""One pre-send contract for evidence, caption and the actual story image."""

import hashlib
from pathlib import Path

from news import event_registry, fact_packet


def image_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(draft: dict, msk: str) -> list[str]:
    data = draft.get("data") or {}
    packet = data.get("fact_packet")
    if not packet:
        return []  # Unsupported prose is already excluded from auto by editorial policy.
    try:
        if fact_packet.key(packet) != data.get("packet_hash"):
            return ["пакет фактов изменён"]
        event = data.get("event_revision")
        expected_event = fact_packet.revision(packet)
        if (not event_registry.complete(event) or
                {k: v for k, v in event.items() if k != "references"} !=
                {k: v for k, v in expected_event.items() if k != "references"}):
            return ["реестр доставки не соответствует проверенным фактам"]
        source = data.get("source_snapshot", {})
        errors = fact_packet.verify(packet, source, fact_packet.render(packet))
        if errors:
            return errors
        if draft["text"] != fact_packet.caption(packet, source, data.get("publication_date", msk)):
            return ["текст не соответствует проверенному пакету фактов"]
        expected_expiry = fact_packet.expires_at(packet)
        if expected_expiry and data.get("expires_at") != expected_expiry:
            return ["окно публикации не соответствует дате факта"]
        if draft.get("card"):
            if data.get("card_spec") != fact_packet.card_spec(packet):
                return ["карточка не соответствует проверенному пакету фактов"]
            if data.get("card_hash") != image_hash(draft["card"]):
                return ["изображение карточки изменено"]
    except (KeyError, TypeError, ValueError, IndexError, OSError):
        return ["неполный или повреждённый публикационный пакет"]
    return []
