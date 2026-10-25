"""Реестр «наших» живёт: кого-то подписали, кого-то обменяли, кто-то уехал из НХЛ.

Базовый реестр — news/data/players.json (в репо, написание сверено). Изменения сервер пишет
поверх него в out/registry.json: образ только для чтения, а реестр меняется между выкатами.
Запись не удаляем никогда: уехавшему ставим team=None («вне НХЛ») — вернётся, имя уже есть.

Откуда узнаём:
1. Раз в день (NEWS_REGISTRY_AT, 08:00 МСК) — `audit`: составы 32 клубов (страна рождения RUS/BLR)
   + статистика сезона (гражданство RUS/BLR, ловит родившихся не в России). Кто выпал из составов —
   карточка игрока: сменился клуб или клуба НХЛ нет. Состав клуба отстаёт от подписания
   (Никишин 25.10.2026: в карточке CAR, в составе ещё нет) — поэтому есть п.2.
2. Сразу из инфоповода — `from_story`: подписание, обмен, вызов игрока с родиной RUS/BLR, которого нет.
Новый наш получает имя из Wikidata (status=wikidata). Имени нет — в посты не попадает, владелец
присылает его командой `/name <id> Имя Фамилия` (status=confirmed).
"""

import json
import re
from collections.abc import Callable
from pathlib import Path

from news import publish
from news.nhl import WEB

BASE = Path(__file__).parent / "data" / "players.json"
OVERLAY_NAME = "registry.json"
COUNTRIES = {"RUS", "BLR"}

Fetch = Callable[[str], dict]


def overlay_path() -> Path:
    return publish.OUT / OVERLAY_NAME  # OUT подменяют тесты — путь считаем при вызове


def load() -> dict:
    """Базовый реестр с наложенными изменениями сервера, в формате players.json."""
    reg = json.loads(BASE.read_text(encoding="utf-8"))
    try:
        over = json.loads(overlay_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        over = {}
    for pid, rec in over.get("players", {}).items():
        reg["players"][pid] = {**reg["players"].get(pid, {}), **rec}
    return reg


def save_change(pid: str, rec: dict) -> None:
    path = overlay_path()
    try:
        over = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        over = {"players": {}}
    over["players"][pid] = {**over["players"].get(pid, {}), **rec}
    publish.OUT.mkdir(exist_ok=True)
    path.write_text(json.dumps(over, ensure_ascii=False, indent=1), encoding="utf-8")


def name_record(pid: str, wiki: dict[str, str]) -> dict:
    ru = wiki.get(pid)
    if not ru:
        return {"ru": None, "surname": None, "status": "new"}
    first, _, surname = ru.partition(" ")
    return {"ru": ru, "surname": surname, "status": "wikidata"}


def rosters(fetch: Fetch, teams: list[str]) -> dict[str, dict]:
    """{pid: {en, team, country}} наших в текущих составах. Клуб не ответил — пропускаем его."""
    out = {}
    for team in teams:
        try:
            data = fetch(f"{WEB}/roster/{team}/current")
        except RuntimeError:
            continue
        for group in ("forwards", "defensemen", "goalies"):
            for p in data.get(group, []):
                if p.get("birthCountry") in COUNTRIES:
                    out[str(p["id"])] = {"en": f"{p['firstName']['default']} {p['lastName']['default']}",
                                         "team": team, "country": p["birthCountry"]}
    return out


def audit(fetch: Fetch, teams: list[str], nationals: Callable[[], list[dict]], wiki: dict[str, str],
          today: str) -> list[str]:
    """Сверка реестра с составами → строки для владельца (что изменилось). Пусто — всё сходится."""
    reg = load()["players"]
    found = rosters(fetch, teams)
    if not found:  # API не ответил целиком — по пустоте никого «вне НХЛ» не объявляем
        return []
    try:
        for p in nationals():
            found.setdefault(str(p["pid"]), {"en": p["name"], "team": p["team"], "country": p["country"]})
    except RuntimeError:
        pass
    report = []
    for pid, info in sorted(found.items()):
        rec = reg.get(pid)
        if rec is None:
            new = {**name_record(pid, wiki), "en": info["en"], "country": info["country"], "team": info["team"],
                   "added": today}
            save_change(pid, new)
            report.append(f"➕ {new['ru'] or info['en']} ({info['team']})"
                          + ("" if new["ru"] else f" — нет русского имени: /name {pid} Имя Фамилия"))
        elif rec.get("team") != info["team"]:
            if "team" in rec:  # первый проход только запоминает клубы
                report.append(f"🔁 {rec.get('ru') or info['en']}: {rec.get('team') or 'вне НХЛ'} → {info['team']}")
            save_change(pid, {"team": info["team"]})
    for pid, rec in sorted(reg.items()):
        if pid in found or rec.get("team", "?") is None:
            continue
        try:  # выпал из составов: фарм, обмен в процессе, расторжение — решает карточка игрока
            team = fetch(f"{WEB}/player/{pid}/landing").get("currentTeamAbbrev")
        except RuntimeError:
            continue
        if team != rec.get("team", "?"):  # «?» — клуб ещё не записывали: None тогда значит «уехал»
            if team is None:
                report.append(f"➖ {rec.get('ru') or pid}: вне НХЛ (был {rec.get('team') or 'без клуба'})")
            elif "team" in rec:
                report.append(f"🔁 {rec.get('ru') or pid}: {rec.get('team') or 'вне НХЛ'} → {team}")
            save_change(pid, {"team": team})
    return report


def from_story(pids: set[int], fetch: Fetch, wiki: dict[str, str], today: str) -> tuple[list[str], dict]:
    """Герои инфоповода, которых нет в реестре: родина RUS/BLR → добавить сразу (1 запрос на героя).
    → (строки владельцу, новые записи {pid: запись})."""
    reg = load()["players"]
    added, records = [], {}
    for pid in sorted(str(p) for p in pids):
        if pid in reg:
            continue
        try:
            d = fetch(f"{WEB}/player/{pid}/landing")
        except RuntimeError:
            continue
        if d.get("birthCountry") not in COUNTRIES:
            continue
        en = f"{d.get('firstName', {}).get('default', '')} {d.get('lastName', {}).get('default', '')}".strip()
        new = {**name_record(pid, wiki), "en": en, "country": d["birthCountry"],
               "team": d.get("currentTeamAbbrev"), "added": today}
        save_change(pid, new)
        records[pid] = new
        added.append(f"➕ {new['ru'] or en} ({new['team'] or 'вне НХЛ'}) — из инфоповода"
                     + ("" if new["ru"] else f" — нет русского имени: /name {pid} Имя Фамилия"))
    return added, records


NAME_CMD = re.compile(r"^/name\s+(\d{7})\s+([А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+)+)\s*$")


def owner_command(text: str) -> str | None:
    """`/name 8482100 Александр Никишин` → ответ владельцу. Не та команда — None."""
    if not text.startswith("/name"):
        return None
    m = NAME_CMD.match(text.strip())
    if not m:
        return "Формат: /name <id НХЛ из 7 цифр> Имя Фамилия — по-русски, например /name 8482100 Александр Никишин"
    pid, ru = m.groups()
    save_change(pid, {"ru": ru, "surname": ru.split()[-1], "status": "confirmed"})
    return f"✅ Записал: {pid} — {ru}. В постах с этого момента."
