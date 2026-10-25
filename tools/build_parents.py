"""Сборка страницы «Родителям» (docs/parents.html) из двух источников.

- data/parents.json — структурированный слой: короткие карточки возрастов, сравнение
  Россия / Канада / США, вопросы школе с хорошим и тревожным ответом, источники. Его же читает бот.
- docs/parents/drafts/parents_guide.md — подробный текст по разделам `## Заголовок {#id}`.
  Раздел `dlya-priemki` на сайт не попадает (только в превью).

    python tools/build_parents.py                      # → docs/parents.html
    python tools/build_parents.py --preview out.html   # приватное превью с черновыми пометками

Пока в data/parents.json `_meta.published: false`, страница помечена noindex и не стоит в sitemap.
Только стандартная библиотека — как build_chapter.py.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "parents.json"
DRAFT = ROOT / "docs" / "parents" / "drafts" / "parents_guide.md"
OUT = ROOT / "docs" / "parents.html"
SITE = "https://altitushkin.github.io/hockey-platform/"
VERDICT = {"same": "Сходятся", "close": "Близки", "partial": "Частично", "differ": "Расходятся"}


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


# ---------- маленький markdown: ровно то, что есть в гайде ----------

def inline(s: str) -> str:
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)

    def link(m):
        url = html.unescape(m.group(2))
        ext = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
        return f'<a href="{esc(url)}"{ext}>{m.group(1)}</a>'
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)


def render_md(md: str) -> str:
    out, lines, i = [], md.strip().splitlines(), 0
    while i < len(lines):
        ln = lines[i].rstrip()
        if not ln.strip() or ln.strip() == "---":
            i += 1
        elif ln.startswith("### "):
            out.append(f"<h3>{inline(ln[4:])}</h3>")
            i += 1
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f'<div class="tbl"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
        elif ln.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip("> ").rstrip())
                i += 1
            out.append(f"<blockquote><p>{inline(' '.join(buf))}</p></blockquote>")
        elif re.match(r"^(- |\d+\. )", ln):
            tag = "ol" if ln[0].isdigit() else "ul"
            items = []
            while i < len(lines) and re.match(r"^(- |\d+\. )", lines[i]):
                items.append(re.sub(r"^(- |\d+\. )", "", lines[i].rstrip()))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(t)}</li>" for t in items) + f"</{tag}>")
        else:
            buf = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||> |- |\d+\. |---)", lines[i]):
                buf.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out)


def sections(md: str) -> list[tuple[str, str, str]]:
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)
    parts = re.split(r"^## (.+?) \{#([\w-]+)\}\s*$", md, flags=re.M)
    return [(parts[i + 1], parts[i], parts[i + 2]) for i in range(1, len(parts), 3)]


# ---------- блоки из data/parents.json ----------

def src_links(ids: list[str], S: dict) -> str:
    if not ids:
        return ""
    links = ", ".join(f'<a href="{esc(S[i]["url"])}" target="_blank" rel="noopener">{esc(S[i]["title"])}</a>'
                      for i in ids)
    return f'<p class="src">Источники: {links}</p>'


def block_short(d: dict) -> str:
    cards = []
    for a in d["ages"]:
        norm = f'<li><b>Ориентир:</b> {esc(a["norm"])}</li>' if a["norm"] else ""
        cards.append(
            f'<article class="age" id="k-{a["id"]}"><h3>{esc(a["title"])}</h3><ul>'
            f'<li><b>Делать:</b> {esc(a["do"])}</li><li><b>Не делать:</b> {esc(a["dont"])}</li>{norm}</ul>'
            f'<a class="more" href="#{a["id"]}">Подробно →</a></article>')
    doctor = "".join(f"<li>{esc(x)}</li>" for x in d["doctor"])
    top = "".join(f'<li><b>{esc(q["q"])}</b><span class="good">Хороший ответ: {esc(q["good"])}</span></li>'
                  for q in d["questions"] if q.get("top"))
    return (f'<p class="thesis">{esc(d["thesis"])} <a href="#glavnoe">Почему так →</a></p>'
            f'<div class="ages">{"".join(cards)}</div>'
            f'<div class="aside-row"><section class="note note--alarm"><h3>К врачу, если</h3>'
            f'<ul>{doctor}</ul></section>'
            f'<section class="note"><h3>Не взяли в 7–9 лет?</h3><p>Это почти ничего не говорит о будущем: ранний '
            f'отбор выбирает тех, кто раньше вырос и родился в начале года. <a href="#otbor-mesyac-rozhdeniya">'
            f'Подробно →</a></p></section></div>'
            f'<section class="note"><h3>5 вопросов школе</h3><ol class="top-q">{top}</ol>'
            f'<a class="more" href="#voprosy">Все 12 с тревожными ответами →</a></section>')


def block_compare(d: dict) -> str:
    S, C = d["sources"], d["compare"]
    labels = {a["id"]: a["label"] for a in d["ages"]}
    countries = C["countries"]
    chips = "".join(f'<button class="chip" type="button" role="tab" data-age="{c["age"]}" '
                    f'aria-selected="{"true" if n == 0 else "false"}">{esc(labels[c["age"]])}</button>'
                    for n, c in enumerate(C["by_age"]))
    panels = []
    for c in C["by_age"]:
        head = "".join(f'<div class="cmp__h" data-c="{k["id"]}">{esc(k["label"])}<small>{esc(k["note"])}</small></div>'
                       for k in countries)
        rows = "".join(
            f'<div class="cmp__t">{esc(r["topic"])}</div>'
            + "".join(f'<div class="cmp__v{" cmp__v--empty" if r[k["id"]] == "—" else ""}" data-c="{k["id"]}">'
                      f'<span class="cmp__lbl">{esc(k["label"])}</span>{esc(r[k["id"]])}</div>' for k in countries)
            for r in c["rows"])
        src = "".join(src_links(c["src"][k["id"]], S).replace('<p class="src">Источники:',
                      f'<p class="src"><b>{esc(k["label"])}:</b>') for k in countries if c["src"].get(k["id"]))
        panels.append(
            f'<div class="cmp__panel" data-age="{c["age"]}" role="tabpanel">'
            f'<p class="verdict"><span class="pill pill--{c["verdict"]}">{VERDICT[c["verdict"]]}</span>'
            f'{esc(c["verdict_text"])}</p>'
            f'<div class="cmp"><div class="cmp__corner"></div>{head}{rows}</div>{src}</div>')
    filt = "".join(f'<button class="chip chip--sm" type="button" data-v="{k}" aria-pressed="false">{v}</button>'
                   for k, v in VERDICT.items() if any(t["verdict"] == k for t in C["by_topic"]))
    topics = "".join(
        f'<article class="topic" data-v="{t["verdict"]}"><header><h4>{esc(t["topic"])}</h4>'
        f'<span class="pill pill--{t["verdict"]}">{VERDICT[t["verdict"]]}</span></header>'
        f'<dl><dt>Россия</dt><dd>{esc(t["ru"])}</dd><dt>Канада и США</dt><dd>{esc(t["west"])}</dd></dl>'
        + (f'<p class="topic__note">{esc(t["note"])}</p>' if t.get("note") else "")
        + src_links(t["src"], S) + "</article>"
        for t in C["by_topic"])
    return (f'<div class="views" role="tablist"><button class="view" type="button" data-view="age" '
            f'aria-selected="true">По возрасту</button><button class="view" type="button" data-view="topic" '
            f'aria-selected="false">По темам</button></div>'
            f'<div class="view-panel" data-view="age"><div class="chips" role="tablist">{chips}</div>'
            f'{"".join(panels)}</div>'
            f'<div class="view-panel" data-view="topic"><div class="chips"><span class="chips__lbl">Показать:</span>'
            f'<button class="chip chip--sm" type="button" data-v="all" aria-pressed="true">Все</button>{filt}</div>'
            f'<div class="topics">{topics}</div></div>')


def block_questions(d: dict) -> str:
    S = d["sources"]
    items = "".join(
        f'<details class="q"><summary><span class="q__n">{n}</span>{esc(q["q"])}</summary>'
        f'<div class="q__body"><p class="good"><b>Хороший ответ.</b> {esc(q["good"])}</p>'
        f'<p class="alarm"><b>Тревожный ответ.</b> {esc(q["alarm"])}</p>{src_links(q["src"], S)}</div></details>'
        for n, q in enumerate(d["questions"], 1))
    return (f'<p class="lead-s">Задайте их на первой встрече. Под каждым — какой ответ успокаивает, '
            f'а какой стоит насторожить.</p><div class="qs">{items}</div>')


def build_body(d: dict, md: str) -> tuple[str, str]:
    """→ (основной HTML, блок «Для приёмки» — только для превью)."""
    detail, review = [], ""
    for sid, title, body in sections(md):
        if sid == "dlya-priemki":
            review = render_md(body)
            continue
        if sid == "rossiya-kanada-ssha":  # сравнение — интерактивным блоком ниже, таблица из md не нужна
            continue
        if sid == "vybor-shkoly":  # вопросы — блоком с ответами
            continue
        detail.append(f'<details class="sec" id="{sid}"><summary>{esc(title)}</summary>'
                      f'<div class="sec__body">{render_md(body)}</div></details>')
    main = (f'<section class="short" aria-label="Коротко">{block_short(d)}</section>'
            f'<section class="block" id="sravnenie"><h2>Россия, Канада и США</h2>'
            f'<p class="lead-s">Как три системы подготовки отвечают на одни и те же вопросы.</p>'
            f'{block_compare(d)}</section>'
            f'<section class="block" id="voprosy"><h2>Вопросы школе и тренеру</h2>{block_questions(d)}</section>'
            f'<section class="block" id="podrobno"><div class="block__head"><h2>Подробно</h2>'
            f'<button class="toggle" id="toggle-all" type="button">Раскрыть всё</button></div>'
            f'<div class="secs">{"".join(detail)}</div></section>')
    return main, review


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", help="путь превью-файла вместо docs/parents.html")
    args = ap.parse_args()
    d = json.loads(DATA.read_text(encoding="utf-8"))
    md = DRAFT.read_text(encoding="utf-8")
    body, review = build_body(d, md)
    tpl = (ROOT / "docs" / "parents" / ("preview.tpl.html" if args.preview else "page.tpl.html"))
    tpl = tpl.read_text(encoding="utf-8")
    page = (tpl.replace("{{BODY}}", body).replace("{{REVIEW}}", review)
            .replace("{{DISCLAIMER}}", esc(d["disclaimer"])).replace("{{ASOF}}", esc(d["_meta"]["data_as_of"]))
            .replace("{{ROBOTS}}", "" if d["_meta"]["published"] else '<meta name="robots" content="noindex">')
            .replace("{{CSS}}", (ROOT / "docs" / "parents" / "parents.css").read_text(encoding="utf-8"))
            .replace("{{JS}}", (ROOT / "docs" / "parents" / "parents.js").read_text(encoding="utf-8")))
    out = Path(args.preview) if args.preview else OUT
    out.write_text(page, encoding="utf-8")
    print(f"{out}: {len(page) // 1024} КБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
