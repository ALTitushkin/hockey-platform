"""Офлайн-пилот RSS: python -m news.source_shadow dfo feed.xml --db news/out/sources.sqlite.

Никаких публикаций и обращений к модели. Сетевой планировщик подключается отдельно после пилота.
"""

import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from news.source_dedup import Ledger, canonical_url

MAX_FEED = 2 * 1024 * 1024
SOURCES = {"dfo": "https://www.dailyfaceoff.com/feed", "ahl": "https://theahl.com/feed"}


@dataclass(frozen=True)
class FeedItem:
    source: str
    item_id: str
    url: str
    title: str
    text: str


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", text))).strip()


def parse_feed(source: str, data: bytes) -> list[FeedItem]:
    """RSS2 DFO/AHL; ссылки сохраняем, вложенные статьи/изображения не загружаем."""
    if source not in SOURCES:
        raise ValueError("Неизвестный источник")
    # ElementTree не нужен DTD; отсечение также предотвращает расширение внутренних entities.
    if len(data) > MAX_FEED or b"\x00" in data or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("RSS превышает лимит или содержит DTD/entities")
    root = ET.fromstring(data)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("Ожидается RSS2 channel")
    result = []
    for row in root.findall("./channel/item")[:100]:
        title, url = plain(row.findtext("title") or ""), row.findtext("link") or ""
        if not title or not url:
            continue
        try:
            url = canonical_url(url)
        except ValueError:
            continue
        body = row.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
        body = plain(body or row.findtext("description") or "")
        # Изменение содержания с прежним GUID остаётся новой версией.
        result.append(FeedItem(source, (row.findtext("guid") or url).strip(), url, title,
                               title + "\n" + body))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=SOURCES)
    parser.add_argument("feed", type=Path)
    parser.add_argument("--db", type=Path, default=Path("news/out/sources.sqlite"))
    args = parser.parse_args()
    with args.feed.open("rb") as stream:
        items = parse_feed(args.source, stream.read(MAX_FEED + 1))
    args.db.parent.mkdir(parents=True, exist_ok=True)
    ledger, counts = Ledger(args.db), Counter()
    try:
        for item in items:
            decision = ledger.observe(item.source, item.item_id, item.url, item.text)
            counts[decision.kind] += 1
            print(json.dumps({"decision": decision.kind, "cluster": decision.cluster_id,
                              "title": item.title, "url": item.url}, ensure_ascii=False))
    finally:
        ledger.close()
    print(json.dumps({"source": args.source, "counts": dict(counts), "mode": "shadow"}))


if __name__ == "__main__":
    main()
