#!/usr/bin/env python3
"""Сборка SEO-артефактов платформы (запуск из корня репо):

    python tools/build_seo.py

Делает две вещи, обе — идемпотентно и только на чтение из data/:
  1. Пересобирает docs/sitemap.xml из реестров (статические страницы +
     только published-главы из history.json).
  2. Инжектит статический JSON-LD DefinedTermSet/DefinedTerm в
     docs/dictionary.html между маркерами SEO:DEFINEDTERMS (краулеры и LLM
     не исполняют JS, поэтому разметка словаря должна быть в HTML, не fetch).

НЕ трогает data/ и docs/data/ — паритет зеркал и validate_data.py не задеты.
Без внешних зависимостей. Код возврата 1 при проблеме — годится для CI.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BASE = "https://altitushkin.github.io/hockey-platform/"
TERMSET_ID = BASE + "dictionary.html#termset"

# Статические страницы сайта: (отн. путь от BASE, приоритет).
# "" = корень (канонический URL главной — без index.html).
STATIC_PAGES = [
    ("", "1.0"),
    ("dictionary.html", "0.9"),
    ("history.html", "0.8"),
]

MARK_START = "<!-- SEO:DEFINEDTERMS:START (генерится tools/build_seo.py — вручную не править) -->"
MARK_END = "<!-- SEO:DEFINEDTERMS:END -->"


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


# ── 1. sitemap.xml ────────────────────────────────────────────────────────
def build_sitemap() -> str:
    today = date.today().isoformat()
    history = load("data/history.json")
    urls = []  # (loc, lastmod, priority)

    for path, prio in STATIC_PAGES:
        urls.append((BASE + path, today, prio))

    for ch in history:
        if not ch.get("published"):
            continue
        loc = ch.get("url")
        if not loc:
            print(f"⚠️  published-глава '{ch['id']}' без url — пропущена в sitemap",
                  file=sys.stderr)
            continue
        lastmod = ch.get("dateModified") or ch.get("added") or today
        urls.append((loc, lastmod, "0.7"))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, prio in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(loc)}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append(f"    <priority>{prio}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


# ── 2. DefinedTerm JSON-LD ────────────────────────────────────────────────
def build_definedterms_jsonld() -> str:
    terms = load("data/terms.json")
    items = []
    for t in terms:
        alt = [t["en"]] + [a for a in t.get("abbr", []) if a]
        # уникализируем, сохраняя порядок
        seen, alt_clean = set(), []
        for a in alt:
            if a not in seen:
                seen.add(a)
                alt_clean.append(a)
        item = {
            "@type": "DefinedTerm",
            "@id": f"{BASE}dictionary.html#term-{t['id']}",
            "name": t["ru"],
            "alternateName": alt_clean if len(alt_clean) > 1 else alt_clean[0],
            "description": t["definition"],
            "inDefinedTermSet": TERMSET_ID,
        }
        items.append(item)

    termset = {
        "@context": "https://schema.org",
        "@type": "DefinedTermSet",
        "@id": TERMSET_ID,
        "name": "Хоккейный словарь «Культуры хоккея»",
        "url": BASE + "dictionary.html",
        "inLanguage": "ru",
        "hasDefinedTerm": items,
    }
    payload = json.dumps(termset, ensure_ascii=False, indent=2)
    return (f'<script type="application/ld+json">\n{payload}\n</script>')


def inject_definedterms() -> bool:
    path = DOCS / "dictionary.html"
    html = path.read_text(encoding="utf-8")
    if MARK_START not in html or MARK_END not in html:
        print("❌ В dictionary.html нет маркеров SEO:DEFINEDTERMS:START/END",
              file=sys.stderr)
        return False
    block = build_definedterms_jsonld()
    new_inner = f"{MARK_START}\n{block}\n{MARK_END}"
    pattern = re.compile(re.escape(MARK_START) + r".*?" + re.escape(MARK_END),
                         re.DOTALL)
    new_html = pattern.sub(lambda _m: new_inner, html)
    if new_html != html:
        path.write_text(new_html, encoding="utf-8")
    return True


def main() -> int:
    sitemap = build_sitemap()
    (DOCS / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    n_urls = sitemap.count("<url>")
    ok = inject_definedterms()
    n_terms = len(load("data/terms.json"))
    if not ok:
        return 1
    print(f"✅ sitemap.xml: {n_urls} URL · DefinedTerm: {n_terms} терминов в dictionary.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
