#!/usr/bin/env python3
"""Сборка HTML-страниц глав истории из принятых markdown-черновиков.

    python tools/build_chapter.py <id> [<id> ...]   # собрать главы
    python tools/build_chapter.py --all             # пересобрать все главы с черновиками
    python tools/build_chapter.py --relink          # только перешить навигацию между главами

Черновик `docs/history/drafts/<id>.md` начинается с frontmatter — всё, что раньше
правилось в блоке CONFIG этого скрипта, теперь живёт рядом с текстом главы:

    ---
    published: 2026-07-05          # дата первой публикации (date-only)
    modified: 2026-07-05           # опц., дата обновления; по умолчанию = published
    subtitle: ...
    breadcrumb: Суперсерия-1972    # короткое имя для хлебных крошек и <title>
    og_title: ...
    og_desc: ...
    meta_desc: ...
    article_desc: ...
    sections: prologue, rosters, ...   # id-якоря h2-разделов по порядку
    keywords: суперсерия, хендерсон    # опц., триггеры бота (find_history_chapter)
    ---

Страница верстается по шаблону `docs/history/origins.html` (стили берутся оттуда),
проставляется JSON-LD (Article + BreadcrumbList), обновляются `data/history.json` и
`docs/data/history.json` (published/url/summary/sections/keywords). После сборки
навигация «← предыдущая / следующая →» перешивается на всех опубликованных главах:
ссылка на следующую главу включается, как только та опубликована.
Затем запусти `python tools/build_seo.py`, чтобы глава попала в sitemap.

`h1` и заголовок в Article — `title` из history.json (канон), номер главы — `n`.
Читает только docs/ и data/; бот (bot/**) не задевается.

⚠️ Формат дат: в Article (datePublished/dateModified) и в og:article:*_time —
полный ISO 8601 с поясом Europe/Moscow (см. iso()). Видимая дата «Обновлено»
остаётся date-only в атрибуте <time datetime>. Так Rich Results не ругается.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://altitushkin.github.io/hockey-platform/"
DRAFTS = ROOT / "docs/history/drafts"
PAGES = ROOT / "docs/history"
HISTORY_FILES = ["data/history.json", "docs/data/history.json"]

REQUIRED = ("published", "subtitle", "breadcrumb", "og_title", "og_desc", "meta_desc", "article_desc", "sections")
LIST_KEYS = ("sections", "keywords")

FONTS = (
    "https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700"
    "&family=PT+Serif:ital,wght@0,400;0,700;1,400;1,700&family=PT+Mono&display=swap"
)
SOURCES_CSS = """  .sources { list-style: none; margin: 8px 0 0; padding: 0; }
  .sources li { font-size: 14px; line-height: 1.5; margin-bottom: 10px; padding-left: 16px; position: relative;
    color: var(--ink-soft); }
  .sources li::before { content: "→"; position: absolute; left: 0; color: var(--steel); }
  .sources a { color: var(--steel); }
</style>"""
SITE_HEADER = """  <header class="site-header">
    <div class="rules"></div>
    <div class="logo">
      <a href="../index.html">
        <img class="logo-img" src="../logo.png" alt="Хоккейный словарь" width="68" height="68">
      </a>
    </div>
    <p class="site-name">Хоккейный словарь</p>
    <p class="tagline">Исторический раздел</p>
    <p class="channel">приложение к каналу «Хоккейный Овертайм»</p>
  </header>"""
SITE_FOOTER = """  <footer class="site-footer">
    <a href="https://t.me/lifeinovertime" rel="noopener">Telegram · Хоккейный Овертайм</a><br>
    <a href="https://github.com/altitushkin/hockey-platform" rel="noopener">GitHub · hockey-platform</a>
  </footer>"""
NAV_RE = re.compile(r'    <nav class="nav-footer">.*?</nav>', re.S)
DISABLED = 'style="opacity:0.45;pointer-events:none;cursor:default"'

MONTHS_RU = {1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
             7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"}


class DraftError(Exception):
    pass


def iso(d: str) -> str:
    """date-only → полный ISO 8601, полдень по Москве (Europe/Moscow, +03:00)."""
    return f"{d}T12:00:00+03:00"


def human_date(d: str) -> str:
    y, m, dd = d.split("-")
    return f"{int(dd)} {MONTHS_RU[int(m)]} {y}"


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def inline(t: str) -> str:
    t = esc(t)
    # [текст](url) в абзаце — например, deep-link в словарь: ../dictionary.html#t-corsi
    t = re.sub(r"\[([^\]]+)\]\(([^()\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    return t


def short_title(chapter: dict) -> str:
    """Короткое имя главы для навигации: заголовок до двоеточия, без «(годы)»."""
    t = chapter["title"].split(":")[0]
    return re.sub(r"\s*\(.*?\)\s*$", "", t).strip()


def load_history(rel: str = HISTORY_FILES[0]) -> list[dict]:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def parse_draft(text: str, cid: str) -> tuple[dict, str]:
    """frontmatter → dict (списки — через запятую), остальное — тело черновика."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise DraftError(f"{cid}: нет frontmatter (--- ... ---) в начале черновика")
    meta: dict = {}
    for ln in m.group(1).split("\n"):
        ln = re.sub(r"\s+#\s.*$", "", ln).strip()
        if not ln:
            continue
        key, _, val = ln.partition(":")
        key, val = key.strip(), val.strip()
        meta[key] = [v.strip() for v in val.split(",") if v.strip()] if key in LIST_KEYS else val
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise DraftError(f"{cid}: во frontmatter нет полей {missing}")
    meta.setdefault("modified", meta["published"])
    return meta, text[m.end():]


def split_blocks(body: str) -> list[str]:
    blocks, cur = [], []
    for ln in body.split("\n"):
        if ln.strip():
            cur.append(ln)
        elif cur:
            blocks.append("\n".join(cur))
            cur = []
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def render_timeline(block: str) -> str:
    rows = []
    for ln in block.split("\n"):
        ln = re.sub(r"^\s*-\s*", "", ln).strip()
        m = re.match(r"\*\*(.+?)\*\*\s*—\s*(.*)", ln)
        if m:
            rows.append(f'\n        <div class="timeline-item">\n          <div class="year">{esc(m.group(1))}</div>'
                        f'\n          <p>{inline(m.group(2))}</p>\n        </div>')
    return f'      <h2 id="timeline">Таймлайн</h2>\n      <div class="timeline">{"".join(rows)}\n      </div>'


def render_sources(block: str) -> str:
    lis = []
    for ln in block.split("\n"):
        ln = re.sub(r"^\s*-\s*", "", ln).strip()
        if not ln:
            continue
        # одна строка = один источник; ссылок в ней может быть несколько
        # ([текст](url) и [текст](url) — описание). Рендерим все ссылки,
        # текст между ними и описание — как inline (связки, тире, курсив).
        parts, pos = [], 0
        # URL может содержать скобки: Wikipedia …_(1942–1967) — допускаем один уровень
        for m in re.finditer(r"\[(.+?)\]\(((?:[^()\s]|\([^()\s]*\))+)\)", ln):
            if m.start() > pos:
                parts.append(inline(ln[pos:m.start()]))
            parts.append(f'<a href="{m.group(2)}" rel="noopener" target="_blank">{esc(m.group(1))}</a>')
            pos = m.end()
        if pos < len(ln):
            parts.append(inline(ln[pos:]))
        if parts:
            lis.append(f'\n        <li>{"".join(parts)}</li>')
    return f'      <h2 id="sources">Источники</h2>\n      <ul class="sources">{"".join(lis)}\n      </ul>'


def render_body(body: str, slugs: list[str], cid: str) -> tuple[str, str | None, list[dict]]:
    """Тело черновика → (html, лид из «Краткого резюме», sections для history.json)."""
    blocks = split_blocks(body)
    h2_count = sum(1 for b in blocks if b.startswith("## ") and not b.startswith(
        ("## Краткое резюме", "## Таймлайн", "## Источники")))
    if h2_count != len(slugs):
        raise DraftError(f"{cid}: разделов h2 — {h2_count}, а slug'ов в sections — {len(slugs)}")

    slug_it = iter(slugs)
    sections, out, lede = [], [], None
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.startswith("# "):
            i += 1
        elif b.startswith("## Краткое резюме"):
            lede = blocks[i + 1]
            i += 2
        elif b.startswith("## Таймлайн"):
            out.append(render_timeline(blocks[i + 1]))
            i += 2
        elif b.startswith("## Источники"):
            out.append(render_sources(blocks[i + 1]))
            i += 2
        elif b.startswith("### Fact-box:"):
            label = b.split(":", 1)[1].strip()
            out.append(f'      <div class="fact-box">\n        <span class="fact-label">{inline(label)}</span>'
                       f'\n        {inline(blocks[i + 1])}\n      </div>')
            i += 2
        elif b.startswith("## "):
            title, slug = b[3:].strip(), next(slug_it)
            sections.append({"id": slug, "title": title})
            out.append(f'      <h2 id="{slug}">{inline(title)}</h2>')
            i += 1
        else:
            out.append(f"      <p>{inline(b)}</p>")
            i += 1

    if lede:
        out.insert(0, f"      <p>{inline(lede)}</p>")
    return "\n\n".join(out), lede, sections


def nav_html(hist: list[dict], idx: int) -> str:
    """Навигация главы: предыдущая — ссылкой (у первой — оглавление), следующая —
    ссылкой, если опубликована, иначе приглушённой надписью; у последней — оглавление."""
    if idx > 0:
        prev = hist[idx - 1]
        left = f'<a href="{prev["id"]}.html">← {short_title(prev)}</a>'
    else:
        left = '<a href="../history.html">← Оглавление истории</a>'
    if idx + 1 < len(hist):
        nxt = hist[idx + 1]
        label = "Следующая глава"
        if nxt.get("published"):
            right = f'<a href="{nxt["id"]}.html">{short_title(nxt)} →</a>'
        else:
            right = f'<a href="#" {DISABLED}>{short_title(nxt)} →</a>'
    else:
        label = "Раздел пройден"
        right = '<a href="../history.html">К оглавлению →</a>'
    return f"""    <nav class="nav-footer">
      {left}
      <div style="text-align:right">
        <span class="next-label">{label}</span>
        {right}
      </div>
    </nav>"""


def relink(hist: list[dict]) -> list[str]:
    """Перешить nav-footer на всех опубликованных главах. Возвращает изменённые id."""
    changed = []
    for idx, ch in enumerate(hist):
        page = PAGES / f"{ch['id']}.html"
        if not ch.get("published") or not page.exists():
            continue
        html = page.read_text(encoding="utf-8")
        new = NAV_RE.sub(lambda _: nav_html(hist, idx), html, count=1)
        if new != html:
            page.write_text(new, encoding="utf-8")
            changed.append(ch["id"])
    return changed


def build(cid: str, hist: list[dict]) -> None:
    meta, body = parse_draft((DRAFTS / f"{cid}.md").read_text(encoding="utf-8"), cid)
    idx = next((i for i, c in enumerate(hist) if c["id"] == cid), None)
    if idx is None:
        raise DraftError(f"{cid}: главы нет в data/history.json (канон — docs/history/INDEX.md)")
    ch = hist[idx]
    url = f"{BASE}history/{cid}.html"
    body_html, lede, sections = render_body(body, meta["sections"], cid)

    # стили — из шаблона origins (читаем до записи: origins тоже собирается этим скриптом)
    oh = (PAGES / "origins.html").read_text(encoding="utf-8")
    style = oh[oh.index("<style>"):oh.index("</style>") + len("</style>")]
    if ".sources" not in style:
        style = style.replace("</style>", SOURCES_CSS)

    org = {"@type": "Organization", "@id": BASE + "#org", "name": "Культура хоккея", "url": BASE,
           "logo": BASE + "logo.png",
           "sameAs": ["https://t.me/lifeinovertime", "https://github.com/altitushkin/hockey-platform"]}
    site = {"@type": "WebSite", "@id": BASE + "#website", "name": "Культура хоккея", "url": BASE,
            "inLanguage": "ru", "publisher": {"@id": BASE + "#org"}}
    art = {"@type": "Article", "headline": ch["title"], "description": meta["article_desc"],
           "inLanguage": "ru", "datePublished": iso(meta["published"]), "dateModified": iso(meta["modified"]),
           "image": BASE + "logo.png", "author": {"@id": BASE + "#org"}, "publisher": {"@id": BASE + "#org"},
           "isPartOf": {"@id": BASE + "#website"}, "mainEntityOfPage": url}
    crumb = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Главная", "item": BASE},
        {"@type": "ListItem", "position": 2, "name": "История хоккея", "item": BASE + "history.html"},
        {"@type": "ListItem", "position": 3, "name": meta["breadcrumb"], "item": url}]}
    ldjson = json.dumps({"@context": "https://schema.org", "@graph": [org, site, art, crumb]},
                        ensure_ascii=False, indent=2)

    page_title = meta.get("page_title") or f"{meta['breadcrumb']} · Культура хоккея"
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(page_title)}</title>
<meta name="description" content="{esc(meta["meta_desc"])}">
<link rel="canonical" href="{url}">
<!-- Open Graph / Twitter -->
<meta property="og:type" content="article">
<meta property="og:site_name" content="Культура хоккея">
<meta property="og:locale" content="ru_RU">
<meta property="og:title" content="{esc(meta["og_title"])}">
<meta property="og:description" content="{esc(meta["og_desc"])}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE}logo.png">
<meta property="article:published_time" content="{iso(meta["published"])}">
<meta property="article:modified_time" content="{iso(meta["modified"])}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(meta["og_title"])}">
<meta name="twitter:description" content="{esc(meta["og_desc"])}">
<meta name="twitter:image" content="{BASE}logo.png">
<!-- JSON-LD -->
<script type="application/ld+json">
{ldjson}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet">
<link rel="stylesheet" href="../style.css">
{style}
</head>
<body>

<div class="wrap">

{SITE_HEADER}

  <div class="article-wrap">

    <div class="breadcrumb">
      <a href="../index.html">Главная</a>
      <span>›</span>
      <a href="../history.html">История</a>
      <span>›</span>
      {esc(meta["breadcrumb"])}
    </div>

    <header class="article-header">
      <span class="chapter-label">Глава {ch["n"]} · История хоккея</span>
      <h1>{esc(ch["title"])}</h1>
      <p class="subtitle">{inline(meta["subtitle"])}</p>
      <p class="article-date">Обновлено: <time datetime="{meta["modified"]}">{human_date(meta["modified"])}</time></p>
    </header>

    <div class="article-body">

{body_html}

    </div>

{nav_html(hist, idx)}

  </div>

{SITE_FOOTER}

</div>

</body>
</html>
"""
    (PAGES / f"{cid}.html").write_text(html, encoding="utf-8")

    ch.update(url=url, summary=lede, sections=sections, published=True)
    if meta.get("keywords"):
        ch["keywords"] = meta["keywords"]
    print(f"OK {cid}.html: sections={[s['id'] for s in sections]}; Article {iso(meta['published'])}"
          f" / {iso(meta['modified'])}")


def save_history(hist: list[dict]) -> None:
    """Пишем оба зеркала из одного списка — паритет data/ ↔ docs/data/ сохраняется."""
    text = json.dumps(hist, ensure_ascii=False, indent=2) + "\n"
    for rel in HISTORY_FILES:
        (ROOT / rel).write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Сборка глав истории из docs/history/drafts/<id>.md")
    ap.add_argument("ids", nargs="*", help="id глав из data/history.json")
    ap.add_argument("--all", action="store_true", help="пересобрать все главы, у которых есть черновик")
    ap.add_argument("--relink", action="store_true", help="только перешить навигацию между главами")
    args = ap.parse_args()

    hist = load_history()
    ids = [c["id"] for c in hist if (DRAFTS / f"{c['id']}.md").exists()] if args.all else args.ids
    if not ids and not args.relink:
        ap.error("укажи id главы, --all или --relink")
    try:
        for cid in ids:
            build(cid, hist)
    except DraftError as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        return 1
    if ids:
        save_history(hist)
    changed = relink(hist)
    print(f"Навигация перешита: {changed or 'без изменений'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
