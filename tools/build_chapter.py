#!/usr/bin/env python3
"""Сборка HTML-страницы главы истории из принятого markdown-черновика.

    python tools/build_chapter.py

Берёт черновик `docs/history/drafts/<id>.md`, верстает страницу по шаблону
`docs/history/origins.html` (шапка/стили/подвал переиспользуются), проставляет
JSON-LD (Article + BreadcrumbList) и обновляет `data/history.json` +
`docs/data/history.json` (published/url/summary/sections). Затем запусти
`python tools/build_seo.py`, чтобы глава попала в sitemap.

Под новую главу меняется только блок CONFIG ниже + наличие черновика.
Читает только docs/ и data/; бот (bot/**) не задевается.

⚠️ Формат дат: в Article (datePublished/dateModified) и в og:article:*_time —
полный ISO 8601 с поясом Europe/Moscow (см. iso()). Видимая дата «Обновлено»
остаётся date-only в атрибуте <time datetime>. Так Rich Results не ругается.
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://altitushkin.github.io/hockey-platform/"

# ─────────────────────────── CONFIG (под текущую главу) ───────────────────────────
CONFIG = {
    "id": "soviet-origins",
    "date": "2026-06-20",                       # дата публикации/обновления (date-only)
    "h1": "С чистого льда",
    "subtitle": "Как Советский Союз построил хоккей с нуля",
    "chapter_label": "Глава 3 · История хоккея",
    "breadcrumb_name": "С чистого льда",
    "og_title": "С чистого льда: как СССР построил хоккей с нуля",
    "og_desc": "Как СССР за девять лет построил хоккей с нуля и в 1954-м разгромил Канаду 7:2. Бобров, Тарасов, Чернышёв и «русский стиль».",
    "meta_desc": "Рождение советского хоккея: от бенди к шайбе, «русский стиль» (пас вместо силы), дебют в Стокгольме-1954 (7:2 над Канадой) и золото Кортины-1956. Глава 3 истории хоккея.",
    "article_desc": "Как СССР построил хоккей с нуля за девять лет: корни в бенди, «русский стиль», дебютная победа над Канадой 7:2 в Стокгольме-1954, олимпийское золото Кортины-1956.",
    "page_title": "С чистого льда · Культура хоккея",
    "section_slugs": ["country-without-hockey","russkiy-stil","bobrov-tarasov-chernyshev",
                      "stockholm-1954","cortina-1956","how-so-fast"],
    "prev": ("golden-age-canada.html", "← Золотой век Канады"),
    "next_label": "Тарасов и большая система →",          # следующая глава — пока задизейблена
    "typo_fixes": [],
}
# ──────────────────────────────────────────────────────────────────────────────────

def iso(d: str) -> str:
    """date-only → полный ISO 8601, полдень по Москве (Europe/Moscow, +03:00)."""
    return f"{d}T12:00:00+03:00"

MONTHS_RU = {1:"января",2:"февраля",3:"марта",4:"апреля",5:"мая",6:"июня",
            7:"июля",8:"августа",9:"сентября",10:"октября",11:"ноября",12:"декабря"}
def human_date(d):
    y,m,dd = d.split("-")
    return f"{int(dd)} {MONTHS_RU[int(m)]} {y}"

def esc(t): return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def inline(t):
    t = esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    return t

def main():
    cid = CONFIG["id"]; date = CONFIG["date"]
    url = f"{BASE}history/{cid}.html"
    draft = (ROOT/f"docs/history/drafts/{cid}.md").read_text(encoding="utf-8")
    for a,b in CONFIG["typo_fixes"]:
        draft = draft.replace(a,b)

    # title из history.json (канон)
    hist = json.loads((ROOT/"data/history.json").read_text(encoding="utf-8"))
    ch = next(c for c in hist if c["id"]==cid)
    full_title = ch["title"]

    # переиспользуем <style>+шапку+подвал из origins
    oh = (ROOT/"docs/history/origins.html").read_text(encoding="utf-8")
    style_block = oh[oh.index("<style>"):oh.index("</style>")+len("</style>")]
    if ".sources" not in style_block:
        style_block = style_block.replace("</style>", """  .sources { list-style: none; margin: 8px 0 0; padding: 0; }
  .sources li { font-size: 14px; line-height: 1.5; margin-bottom: 10px; padding-left: 16px; position: relative; color: var(--ink-soft); }
  .sources li::before { content: "→"; position: absolute; left: 0; color: var(--steel); }
  .sources a { color: var(--steel); }
</style>""")

    SITE_HEADER = '''  <header class="site-header">
    <div class="rules"></div>
    <div class="logo">
      <a href="../index.html">
        <img class="logo-img" src="../logo.png" alt="Хоккейный словарь" width="68" height="68">
      </a>
    </div>
    <p class="site-name">Хоккейный словарь</p>
    <p class="tagline">Исторический раздел</p>
    <p class="channel">приложение к каналу «Хоккейный Овертайм»</p>
  </header>'''
    SITE_FOOTER = '''  <footer class="site-footer">
    <a href="https://t.me/lifeinovertime" rel="noopener">Telegram · Хоккейный Овертайм</a><br>
    <a href="https://github.com/altitushkin/hockey-platform" rel="noopener">GitHub · hockey-platform</a>
  </footer>'''

    # разбор черновика
    blocks=[]; cur=[]
    for ln in draft.split("\n"):
        if ln.strip()=="":
            if cur: blocks.append("\n".join(cur)); cur=[]
        else: cur.append(ln)
    if cur: blocks.append("\n".join(cur))

    slug_it=iter(CONFIG["section_slugs"]); sections_meta=[]; body=[]; lede=None
    i=0; n=len(blocks)
    while i<n:
        b=blocks[i]
        if b.startswith("# "): i+=1; continue
        if b.startswith("## Краткое резюме"): lede=blocks[i+1]; i+=2; continue
        if b.startswith("## Таймлайн"):
            items=[]
            for ln in blocks[i+1].split("\n"):
                ln=re.sub(r"^\s*-\s*","",ln).strip()
                m=re.match(r"\*\*(.+?)\*\*\s*—\s*(.*)", ln)
                if m: items.append((m.group(1),m.group(2)))
            rows="".join(f'\n        <div class="timeline-item">\n          <div class="year">{esc(y)}</div>\n          <p>{inline(t)}</p>\n        </div>' for y,t in items)
            body.append(f'      <h2 id="timeline">Таймлайн</h2>\n      <div class="timeline">{rows}\n      </div>'); i+=2; continue
        if b.startswith("## Источники"):
            lis=[]
            for ln in blocks[i+1].split("\n"):
                m=re.match(r"^\s*-\s*\[(.+?)\]\((.+?)\)\s*$", ln)
                if m: lis.append(f'\n        <li><a href="{m.group(2)}" rel="noopener" target="_blank">{esc(m.group(1))}</a></li>')
            body.append(f'      <h2 id="sources">Источники</h2>\n      <ul class="sources">{"".join(lis)}\n      </ul>'); i+=2; continue
        if b.startswith("### Fact-box:"):
            label=b.split(":",1)[1].strip()
            body.append(f'      <div class="fact-box">\n        <span class="fact-label">{inline(label)}</span>\n        {inline(blocks[i+1])}\n      </div>'); i+=2; continue
        if b.startswith("## "):
            title=b[3:].strip(); slug=next(slug_it)
            sections_meta.append({"id":slug,"title":title})
            body.append(f'      <h2 id="{slug}">{inline(title)}</h2>'); i+=1; continue
        body.append(f"      <p>{inline(b)}</p>"); i+=1

    intro=f"      <p>{inline(lede)}</p>" if lede else ""
    body_html="\n\n".join(([intro] if intro else [])+body)

    ORG={"@type":"Organization","@id":BASE+"#org","name":"Культура хоккея","url":BASE,
         "logo":BASE+"logo.png","sameAs":["https://t.me/lifeinovertime","https://github.com/altitushkin/hockey-platform"]}
    SITE={"@type":"WebSite","@id":BASE+"#website","name":"Культура хоккея","url":BASE,
          "inLanguage":"ru","publisher":{"@id":BASE+"#org"}}
    ART={"@type":"Article","headline":full_title,"description":CONFIG["article_desc"],
         "inLanguage":"ru","datePublished":iso(date),"dateModified":iso(date),"image":BASE+"logo.png",
         "author":{"@id":BASE+"#org"},"publisher":{"@id":BASE+"#org"},
         "isPartOf":{"@id":BASE+"#website"},"mainEntityOfPage":url}
    CRUMB={"@type":"BreadcrumbList","itemListElement":[
        {"@type":"ListItem","position":1,"name":"Главная","item":BASE},
        {"@type":"ListItem","position":2,"name":"История хоккея","item":BASE+"history.html"},
        {"@type":"ListItem","position":3,"name":CONFIG["breadcrumb_name"],"item":url}]}
    ldjson=json.dumps({"@context":"https://schema.org","@graph":[ORG,SITE,ART,CRUMB]},ensure_ascii=False,indent=2)

    prev_href,prev_text=CONFIG["prev"]
    html=f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{CONFIG["page_title"]}</title>
<meta name="description" content="{CONFIG["meta_desc"]}">
<link rel="canonical" href="{url}">
<!-- Open Graph / Twitter -->
<meta property="og:type" content="article">
<meta property="og:site_name" content="Культура хоккея">
<meta property="og:locale" content="ru_RU">
<meta property="og:title" content="{CONFIG["og_title"]}">
<meta property="og:description" content="{CONFIG["og_desc"]}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE}logo.png">
<meta property="article:published_time" content="{iso(date)}">
<meta property="article:modified_time" content="{iso(date)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{CONFIG["og_title"]}">
<meta name="twitter:description" content="{CONFIG["og_desc"]}">
<meta name="twitter:image" content="{BASE}logo.png">
<!-- JSON-LD -->
<script type="application/ld+json">
{ldjson}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&family=PT+Serif:ital,wght@0,400;0,700;1,400;1,700&family=PT+Mono&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../style.css">
{style_block}
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
      {CONFIG["breadcrumb_name"]}
    </div>

    <header class="article-header">
      <span class="chapter-label">{CONFIG["chapter_label"]}</span>
      <h1>{CONFIG["h1"]}</h1>
      <p class="subtitle">{CONFIG["subtitle"]}</p>
      <p class="article-date">Обновлено: <time datetime="{date}">{human_date(date)}</time></p>
    </header>

    <div class="article-body">

{body_html}

    </div>

    <nav class="nav-footer">
      <a href="{prev_href}">{prev_text}</a>
      <div style="text-align:right">
        <span class="next-label">Следующая глава</span>
        <a href="#" style="opacity:0.45;pointer-events:none;cursor:default">{CONFIG["next_label"]}</a>
      </div>
    </nav>

  </div>

{SITE_FOOTER}

</div>

</body>
</html>
'''
    (ROOT/f"docs/history/{cid}.html").write_text(html, encoding="utf-8")

    # history.json (оба зеркала)
    for rel in ["data/history.json","docs/data/history.json"]:
        p=ROOT/rel; data=json.loads(p.read_text(encoding="utf-8"))
        for c in data:
            if c["id"]==cid:
                c["url"]=url; c["summary"]=lede; c["sections"]=sections_meta; c["published"]=True
        p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    print(f"OK {cid}.html: sections={[s['id'] for s in sections_meta]}; Article dates ISO {iso(date)}")

if __name__ == "__main__":
    main()
