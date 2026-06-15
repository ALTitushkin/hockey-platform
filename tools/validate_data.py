#!/usr/bin/env python3
"""Проверка целостности данных платформы (запуск из корня репо):

    python tools/validate_data.py

Проверяет ссылочную целостность реестров и паритет data/ ↔ docs/data/.
Без зависимостей. Возвращает код 1 при любой ошибке — годится для CI.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def err(msg: str):
    errors.append(msg)


def check_mirror(name: str):
    """data/<name> и docs/data/<name> должны совпадать байт-в-байт по содержимому."""
    a = load(f"data/{name}")
    b = load(f"docs/data/{name}")
    if a != b:
        err(f"mirror: data/{name} ≠ docs/data/{name}")


def main() -> int:
    terms = load("data/terms.json")
    clusters = load("data/clusters.json")
    history = load("data/history.json")
    quick = load("data/quick_answers.json")

    term_ids = {t["id"] for t in terms}
    cluster_slugs = {c["slug"] for c in clusters}

    # terms
    if len(term_ids) != len(terms):
        err("terms: дублирующиеся id")
    for t in terms:
        tid = t["id"]
        if not isinstance(t.get("profiles"), list):
            err(f"terms[{tid}]: profiles должен быть списком")
        cl = t.get("cluster")
        if cl is not None and cl not in cluster_slugs:
            err(f"terms[{tid}]: cluster '{cl}' нет в clusters.json")
        for sid in t.get("see_also", []):
            if sid not in term_ids:
                err(f"terms[{tid}]: see_also '{sid}' — нет такого термина")
            if sid == tid:
                err(f"terms[{tid}]: see_also ссылается сам на себя")
        a = t.get("anchor")
        if a is not None and not all(k in a for k in ("target", "anchor_id", "label")):
            err(f"terms[{tid}]: anchor должен иметь target/anchor_id/label")

    # clusters
    if len(cluster_slugs) != len(clusters):
        err("clusters: дублирующиеся slug")
    for c in clusters:
        tid = c.get("term_id")
        if tid is not None and tid not in term_ids:
            err(f"clusters[{c['slug']}]: term_id '{tid}' — нет такого термина")

    # history
    chapter_sections = {}
    for ch in history:
        if not isinstance(ch.get("published"), bool):
            err(f"history[{ch['id']}]: published должен быть bool")
        ids = set()
        for sec in ch.get("sections", []):
            if "id" not in sec or "title" not in sec:
                err(f"history[{ch['id']}]: section без id/title")
            ids.add(sec.get("id"))
        chapter_sections[ch["id"]] = ids
        # опубликованная глава обязана иметь url; черновик (published:false) — url может быть null
        if ch.get("published") and not ch.get("url"):
            err(f"history[{ch['id']}]: published-глава без url")

    # quick_answers → цели существуют
    for i, q in enumerate(quick):
        for k in ("q", "summary", "target_url", "anchor_id"):
            if k not in q:
                err(f"quick_answers[{i}]: нет поля {k}")
        url, anchor = q.get("target_url", ""), q.get("anchor_id")
        if url == "dictionary.html":
            if anchor not in term_ids:
                err(f"quick_answers[{i}]: anchor_id '{anchor}' — нет термина")
        elif url.startswith("history/"):
            chap = url.split("/")[-1].replace(".html", "")
            if anchor not in chapter_sections.get(chap, set()):
                err(f"quick_answers[{i}]: anchor_id '{anchor}' — нет раздела в главе '{chap}'")
        else:
            err(f"quick_answers[{i}]: неизвестный target_url '{url}'")

    # зеркала
    for name in ("terms.json", "clusters.json", "quick_answers.json", "history.json"):
        check_mirror(name)

    if errors:
        print("❌ Ошибки целостности данных:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"✅ Данные валидны: {len(terms)} терминов, {len(clusters)} кластеров, "
          f"{len(history)} глав истории, {len(quick)} быстрых ответов.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
