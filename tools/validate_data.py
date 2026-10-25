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
    learning = load("data/learning.json")

    term_ids = {t["id"] for t in terms}
    cluster_slugs = {c["slug"] for c in clusters}

    # terms
    if len(term_ids) != len(terms):
        err("terms: дублирующиеся id")
    for t in terms:
        tid = t["id"]
        if not isinstance(t.get("profiles"), list):
            err(f"terms[{tid}]: profiles должен быть списком")
        if t.get("status") not in ("verified", "unverified"):
            err(f"terms[{tid}]: status должен быть verified/unverified (сейчас {t.get('status')!r})")
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

    # terms → якорь ведёт в существующий раздел опубликованной главы; схема лежит на диске
    published = {ch["id"] for ch in history if ch.get("published")}
    for t in terms:
        a = t.get("anchor")
        if a and a.get("target", "").startswith("history/"):
            chap = a["target"].split("/")[-1].replace(".html", "")
            if chap not in published:
                err(f"terms[{t['id']}]: anchor ведёт в неопубликованную главу '{chap}'")
            elif a.get("anchor_id") not in chapter_sections.get(chap, set()):
                err(f"terms[{t['id']}]: anchor_id '{a.get('anchor_id')}' — нет раздела в главе '{chap}'")
        if t.get("visual_type") == "scheme" and not (ROOT / "docs" / (t.get("visual") or "")).is_file():
            err(f"terms[{t['id']}]: схемы '{t.get('visual')}' нет в docs/")

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

    # learning → маршруты ссылаются на живые термины и разделы опубликованных глав
    route_ids = set()
    for r in learning:
        rid = r.get("id")
        if rid in route_ids:
            err(f"learning: дублирующийся id маршрута '{rid}'")
        route_ids.add(rid)
        if r.get("level") not in ("novice", "fan", "geek"):
            err(f"learning[{rid}]: level должен быть novice/fan/geek")
        for p in r.get("profiles", []):
            if p not in ("general", "player", "coach", "analyst", "scout"):
                err(f"learning[{rid}]: неизвестный профиль '{p}'")
        if not r.get("steps"):
            err(f"learning[{rid}]: нет шагов")
        step_ids = set()
        for s in r.get("steps", []):
            where = f"learning[{rid}].{s.get('id')}"
            if s.get("id") in step_ids:
                err(f"{where}: дублирующийся id шага")
            step_ids.add(s.get("id"))
            for k in ("title", "text", "terms"):
                if not s.get(k):
                    err(f"{where}: нет поля {k}")
            for tid in s.get("terms", []):
                if tid not in term_ids:
                    err(f"{where}: термин '{tid}' — нет в terms.json")
            h = s.get("history")
            if h:
                chap = h.get("target", "").split("/")[-1].replace(".html", "")
                if chap not in published:
                    err(f"{where}: history ведёт в неопубликованную главу '{chap}'")
                elif h.get("anchor_id") not in chapter_sections.get(chap, set()):
                    err(f"{where}: anchor_id '{h.get('anchor_id')}' — нет раздела в главе '{chap}'")
            c = s.get("check")
            if c and not (isinstance(c.get("answer"), int) and 0 <= c["answer"] < len(c.get("options", []))):
                err(f"{where}: check.answer вне списка options")

    # зеркала
    for name in ("terms.json", "clusters.json", "quick_answers.json", "history.json", "learning.json", "parents.json"):
        check_mirror(name)

    if errors:
        print("❌ Ошибки целостности данных:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"✅ Данные валидны: {len(terms)} терминов, {len(clusters)} кластеров, "
          f"{len(history)} глав истории, {len(quick)} быстрых ответов, {len(learning)} учебных маршрутов.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
