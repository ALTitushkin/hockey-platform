"""События ночи: что на самом деле главное, а не просто «больше всех очков».

Рекорд клуба, юбилей карьеры, первый гол в НХЛ, победный гол, хет-трик, сухой матч.
Каждое событие — вес (что важнее), короткая фраза без фамилии и числа из данных для гарда.

Сеть и логика разделены: `context()` ходит в НХЛ API, `detect()` — чистая функция, её
проверяют тесты. До/после считаем так: итог карьеры после матча минус этот матч. Если в
профиле игрока этот матч ещё не учтён (API обновился не до конца), карьерные события
для него не выдаём — лучше промолчать, чем объявить «первый гол» ветерану.
"""

import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from news.competition import Scope, from_data
from news.digest import plural
from news.nhl import STATS, WEB, GameReport, fetch_json

# Рекорд клуба считаем только от порога: у молодых франшиз (Юта, Сиэтл) «рекорд» — пара десятков очков.
RECORD_MIN = {"points": 300, "goals": 150, "assists": 200}
RECORD_WORD = {"points": ("лучший бомбардир в истории клуба", "очко", "очка", "очков"),
               "goals": ("лучший снайпер в истории клуба", "гол", "гола", "голов"),
               "assists": ("лучший ассистент в истории клуба", "передача", "передачи", "передач")}


@dataclass
class Event:
    pid: int
    weight: int
    text: str
    numbers: set[int] = field(default_factory=set)


def _milestones(before: int, after: int, marks: list[int]) -> list[int]:
    return [m for m in marks if before < m <= after]


GOAL_MARKS = [100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950]
POINT_MARKS = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200, 1300, 1400, 1500]
GAME_MARKS = [500, 1000, 1500]


def deciding_goal(scoring: list[dict], winner: str, loser_score: int) -> tuple[int | None, bool]:
    """→ (кто забил победный, в овертайме ли). Победный — гол победителя номер «счёт проигравшего + 1»."""
    n = 0
    for period in scoring:
        kind = period["periodDescriptor"]["periodType"]
        if kind == "SO":
            return None, False
        for g in period["goals"]:
            team = g["teamAbbrev"]["default"] if isinstance(g["teamAbbrev"], dict) else g["teamAbbrev"]
            if team == winner:
                n += 1
                if n == loser_score + 1:
                    return g["playerId"], kind == "OT"
    return None, False


def detect(reports: list[GameReport], ctx: dict) -> list[Event]:
    events = []
    for r in reports:
        game = ctx.get("games", {}).get(r.game_id, {})
        winner = r.home if r.home_score > r.away_score else r.away
        scorer, in_ot = deciding_goal(game.get("scoring", []), winner, min(r.home_score, r.away_score))
        for s in r.skaters:
            p = ctx.get("players", {}).get(s.pid)
            if p and p.get("this_game") and p.get("scope_confirmed", p.get("regular")):
                career_start = len(events)
                c = p["career"]
                g0, p0, a0 = c["goals"] - s.goals, c["points"] - s.points, c["assists"] - s.assists
                for stat, tonight, before in (("points", s.points, p0), ("goals", s.goals, g0),
                                              ("assists", s.assists, a0)):
                    top = p.get("franchise", {}).get(stat)  # [(pid, итог за клуб), ...] — двое лучших
                    if not tonight or not top or top[0][0] != s.pid or top[0][1] < RECORD_MIN[stat]:
                        continue
                    n, rival = top[0][1], (top[1][1] if len(top) > 1 else 0)
                    if n - tonight <= rival < n:  # до матча не был единоличным лидером, теперь — да
                        word, *forms = RECORD_WORD[stat]
                        events.append(Event(s.pid, 100 if stat != "assists" else 90,
                                            f"{word}: {n} {plural(n, tuple(forms))}", {n}))
                if s.goals and g0 == 0:
                    events.append(Event(s.pid, 70, "первые голы в НХЛ" if s.goals > 1 else "первый гол в НХЛ"))
                elif s.points and p0 == 0:
                    events.append(Event(s.pid, 60, "первое очко в НХЛ"))
                for m in _milestones(g0, c["goals"], GOAL_MARKS):
                    events.append(Event(s.pid, 85 if m >= 500 else 75, f"{m}-й гол в НХЛ", {m}))
                for m in _milestones(p0, c["points"], POINT_MARKS):
                    events.append(Event(s.pid, 85 if m >= 1000 else 65, f"{m}-е очко в НХЛ", {m}))
                for m in _milestones(c["games"] - 1, c["games"], GAME_MARKS):
                    events.append(Event(s.pid, 50, f"{m}-й матч в НХЛ", {m}))
                if p.get("scope", {}).get("phase") == "playoffs":
                    for event in events[career_start:]:
                        event.text = event.text.replace("в НХЛ", "в плей-офф НХЛ")
            if s.goals >= 3:
                events.append(Event(s.pid, 55, "хет-трик" if s.goals == 3 else f"{s.goals} гола за матч", {s.goals}))
            elif s.points >= 4:
                events.append(Event(s.pid, 45, f"{s.points} очка за матч" if s.points == 4 else
                                    f"{s.points} очков за матч", {s.points}))
            if s.pid == scorer:
                text = "победный гол в овертайме" if in_ot else "победный гол"
                events.append(Event(s.pid, 60 if in_ot else 40, text))
        for g in r.goalies:
            against = r.away_score if g.team == r.home else r.home_score
            if against == 0 and g.saves == g.shots and g.decision == "W":
                events.append(Event(g.pid, 50, "сухой матч"))
    return events


def headline(events: list[Event], limit: int = 3) -> list[tuple[int, list[Event]]]:
    """Игроки с событиями — по весу главного события, у каждого события по весу."""
    by: dict[int, list[Event]] = {}
    for e in events:
        by.setdefault(e.pid, []).append(e)
    ranked = sorted(by.items(), key=lambda kv: -max(e.weight for e in kv[1]))
    return [(pid, sorted(evs, key=lambda e: -e.weight)) for pid, evs in ranked[:limit]]


def streak_totals(rows: list[dict]) -> tuple[str, set[int]]:
    """Return a caption suffix and its guard numbers for exactly the streak games."""
    if not rows or any(type(r.get("plusMinus")) is not int
                       or type(r.get("goals")) is not int or type(r.get("points")) is not int
                       or not 0 <= r["goals"] <= r["points"] for r in rows):
        return "", set()
    goals = sum(r["goals"] for r in rows)
    assists = sum(r["points"] - r["goals"] for r in rows)
    plus_minus = sum(r["plusMinus"] for r in rows)
    return f" ({goals}+{assists},{plus_minus:+d})", {goals, assists, abs(plus_minus)}


def scoring_streaks(reports: list[GameReport], candidates: set[int],
                    fetch: Callable[[str], dict] = fetch_json) -> list[Event]:
    """Серии регулярного чемпионата: только если полный журнал содержит и текущий матч, и прошлые игры."""
    lines = {s.pid: s for report in reports for s in report.skaters if s.pid in candidates}
    events = []
    for pid, line in lines.items():
        report = next(r for r in reports if any(s.pid == pid for s in r.skaters))
        scope_data = report.scope
        if not scope_data or scope_data.get("phase") != "regular":
            continue
        if scope_data.get("competition") != "nhl":
            continue
        try:
            payload = fetch(f"{WEB}/player/{pid}/game-log/now")
        except RuntimeError:
            break  # endpoint недоступен — не повторяем сетевые ретраи для всех оставшихся игроков
        if not isinstance(payload, dict) or payload.get("gameTypeId") != 2:
            continue
        rows = payload.get("gameLog")
        if not isinstance(rows, list) or not rows:
            continue
        if any(not isinstance(row, dict) or type(row.get("gameId")) is not int
               or not isinstance(row.get("gameDate"), str)
               or any(type(row.get(k)) is not int or row[k] < 0 for k in ("goals", "points"))
               for row in rows):
            continue
        try:
            for row in rows:
                date.fromisoformat(row["gameDate"])
        except ValueError:
            continue
        ordered = sorted(rows, key=lambda row: (row["gameDate"], row["gameId"]), reverse=True)
        if len({row["gameId"] for row in ordered}) != len(ordered):
            continue
        current = next((i for i, row in enumerate(ordered) if row["gameId"] == report.game_id), None)
        if current is None or (ordered[current]["goals"], ordered[current]["points"]) != (line.goals, line.points):
            continue  # журнал ещё не обновился или не соответствует box score
        for key, current_value, label, minimum, weight in (
                ("points", line.points, "результативную", 4, 75),
                ("goals", line.goals, "голевую", 3, 70)):
            prior = 0
            for row in ordered[current + 1:]:
                if row[key] == 0:
                    break
                prior += 1
            if current_value and prior >= minimum:
                length = prior + 1
                count = plural(length, ("матча", "матчей", "матчей"))
                suffix, numbers = streak_totals(ordered[current:current + length])
                events.append(Event(pid, weight, f"продлил {label} серию до {length} {count}{suffix}",
                                    numbers | {length}))
            elif not current_value and prior >= minimum + 1:
                count = plural(prior, ("матча", "матчей", "матчей"))
                suffix, numbers = streak_totals(ordered[current + 1:current + 1 + prior])
                events.append(Event(pid, weight, f"прервал {label} серию из {prior} {count}{suffix}",
                                    numbers | {prior}))
    return events


def context(reports: list[GameReport], fetch: Callable[[str], dict] = fetch_json,
            games: dict | None = None, scope: Scope | None = None) -> dict:
    """Всё, что нужно detect(): ход матча, карьера наших с очками, лидеры франшизы."""
    ctx: dict = {"games": dict(games or {}), "players": {}}
    franchise = {t["triCode"]: t["franchiseId"] for t in fetch(f"{STATS}/team").get("data", [])}
    for r in reports:
        if games is None:
            ctx["games"][r.game_id] = {"scoring": fetch(f"{WEB}/gamecenter/{r.game_id}/landing")
                                       .get("summary", {}).get("scoring", [])}
        for s in r.skaters:
            if not s.points:
                continue  # без очков ни рекорда, ни юбилея по голам/очкам
            actual = from_data(r.scope) if r.scope else scope
            if actual is None or actual.profile.career_key is None:
                continue
            if scope and actual != scope:
                continue
            land = fetch(f"{WEB}/player/{s.pid}/landing")
            last = (land.get("last5Games") or [{}])[0]
            c = land.get("careerTotals", {}).get(actual.profile.career_key, {})
            if any(type(c.get(k)) is not int or c[k] < 0 for k in ("goals", "assists", "points", "gamesPlayed")):
                continue
            p = {"this_game": last.get("gameId") == r.game_id,
                 "regular": actual.phase == "regular" and last.get("gameTypeId") == actual.profile.game_type,
                 "scope_confirmed": last.get("gameTypeId") == actual.profile.game_type,
                 "scope": actual.data(),
                 "career": {"goals": c["goals"], "assists": c["assists"],
                            "points": c["points"], "games": c["gamesPlayed"]},
                 "franchise": {}}
            fid = franchise.get(s.team)
            if fid and p["this_game"] and p["regular"]:
                for stat in ("points", "goals", "assists"):
                    if p["career"][stat] < RECORD_MIN[stat]:
                        continue
                    sort = urllib.parse.quote(f'[{{"property":"{stat}","direction":"DESC"}}]')
                    exp = urllib.parse.quote(f"franchiseId={fid} and gameTypeId={actual.profile.game_type}")
                    rows = fetch(f"{STATS}/skater/summary?isAggregate=true&isGame=false&limit=2"
                                 f"&sort={sort}&cayenneExp={exp}").get("data", [])
                    p["franchise"][stat] = [(row["playerId"], row[stat]) for row in rows]
            ctx["players"][s.pid] = p
    return ctx
