"""Русские имена игроков всей НХЛ — для поста «Ночь в НХЛ».

Источник — Wikidata (CC0): у элемента игрока есть «NHL.com player ID» (P3522) и русская метка,
которую пишут редакторы ru.wikipedia. Наш реестр (data/players.json) сильнее: для россиян и
белорусов написание сверено вручную. Нет русского имени — игрока в посте нет: транслитерацию
не выдумываем, лучше промолчать, чем написать «Макдэвид» тремя способами.

    python -m news.run sync-names   # обновить news/data/names_ru.json
"""

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from news.nhl import UA

FILE = Path(__file__).parent / "data" / "names_ru.json"
SPARQL = "https://query.wikidata.org/sparql"
QUERY = 'SELECT ?id ?ru WHERE { ?p wdt:P3522 ?id . ?p rdfs:label ?ru FILTER(LANG(?ru)="ru") }'


def fetch_wikidata() -> dict[str, str]:
    url = f"{SPARQL}?{urllib.parse.urlencode({'query': QUERY})}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        rows = json.load(r)["results"]["bindings"]
    return {b["id"]["value"]: b["ru"]["value"] for b in rows if b["id"]["value"].isdigit()}


PATRONYMIC = re.compile(r"(вич|вна|ична|инична)$")
PARTICLES = {"Ван", "Вэн", "Де", "Ди", "Дю", "Ла", "Ле", "Фон", "Дер", "Дел", "Делла"}


def parse_label(label: str) -> tuple[str, str] | None:
    """Метка Wikidata → (имя, фамилия). Форматы на ru.wikipedia разные:
    «Кучеров, Никита Игоревич (хоккеист)», «Александр Валерьевич Радулов», «Немчинов Сергей Львович»,
    «Энтони Джеймс Эспозито», «Майк Ван Рин». Латиница или одно слово — None: такое не публикуем."""
    label = re.sub(r"\s*\(.*?\)", "", label).strip()
    if not label or re.search(r"[A-Za-z]", label):
        return None
    if "," in label:
        surname, rest = (x.strip() for x in label.split(",", 1))
        return (rest.split()[0], surname) if rest else None
    words = label.split()
    if len(words) < 2:
        return None
    if len(words) > 2 and PATRONYMIC.search(words[-1]):  # «Фамилия Имя Отчество»
        return words[1], words[0]
    if len(words) > 2 and words[-2] in PARTICLES:  # «Майк Ван Рин»
        return words[0], f"{words[-2]} {words[-1]}"
    return words[0], words[-1]  # «Имя [Отчество|второе имя] Фамилия»


def sync() -> int:
    names = {pid: f"{p[0]} {p[1]}" for pid, ru in fetch_wikidata().items() if (p := parse_label(ru))}
    FILE.write_text(json.dumps(dict(sorted(names.items(), key=lambda kv: int(kv[0]))), ensure_ascii=False,
                               indent=0) + "\n", encoding="utf-8")
    return len(names)


def league_players(pids: set[int], ours: dict) -> dict:
    """Записи в формате реестра (ru, surname) для игроков ночи: сначала наш реестр, потом Wikidata."""
    wiki = json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {}
    out = {}
    for pid in pids:
        rec = ours.get(str(pid))
        if rec and rec.get("ru"):
            out[str(pid)] = rec
        elif str(pid) in wiki:
            first, _, surname = wiki[str(pid)].partition(" ")
            out[str(pid)] = {"ru": f"{first} {surname}", "surname": surname, "status": "wikidata"}
    return out
