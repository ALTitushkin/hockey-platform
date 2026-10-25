"""Интриги «Сегодня ночью»: что может случиться у наших в этот вечер — только из чисел api-web.nhle.com.

Источник — `player/<id>/landing` (карьера в регулярке и пять последних матчей), один запрос на игрока,
один раз при сборке поста. Каждая интрига — строка с числами из данных, гард их сверяет.
Ранг: юбилей карьеры важнее серии, серия важнее темпа сезона.
"""

from news.digest import plural
from news.nhl import WEB, fetch_json


def landing(pid: int, fetch=fetch_json) -> dict:
    return fetch(f"{WEB}/player/{pid}/landing")


def next_mark(value: int, step: int) -> int:
    return (value // step + 1) * step


def player_items(pid: int, surname: str, data: dict) -> list[dict]:
    """→ [{"pid", "rank", "text", "numbers"}]; rank меньше — важнее."""
    career = (data.get("careerTotals") or {}).get("regularSeason") or {}
    last = [g for g in data.get("last5Games", []) if g.get("gameTypeId") == 2]  # свежие — первыми
    name = f"<b>{surname}</b>"
    items = []

    def add(rank: int, text: str, *numbers: int) -> None:
        items.append({"pid": pid, "rank": rank, "text": text, "numbers": [str(n) for n in numbers]})

    if data.get("position") == "G":
        wins, shutouts = career.get("wins", 0), career.get("shutouts", 0)
        mark = next_mark(wins, 50)
        if mark - wins == 1:
            add(0, f"🎯 {name} — одна победа до {mark} в НХЛ", mark)
        mark = next_mark(shutouts, 10)
        if mark - shutouts == 1:
            add(0, f"🧱 {name} — один «сухарь» до {mark} в карьере", mark)
        streak = 0
        for g in last:
            if g.get("decision") != "W":
                break
            streak += 1
        if streak >= 3:
            add(1, f"🥅 {name} — {streak} {plural(streak, ('победа', 'победы', 'побед'))} подряд", streak)
        return items

    for key, step, words, limit in (("goals", 50, ("гол", "гола", "голов"), 5),
                                    ("points", 100, ("очко", "очка", "очков"), 5),
                                    ("assists", 100, ("передача", "передачи", "передач"), 3)):
        value = career.get(key, 0)
        mark = next_mark(value, step)
        if value and mark - value <= limit:
            left = mark - value  # 1–2 — может случиться сегодня, 3–5 — сюжет на ближайшие матчи
            add(0 if left <= 2 else 1, f"🎯 {name} — {left} {plural(left, words)} до {mark} в НХЛ", left, mark)
            break  # один юбилей на игрока: строка про очки и голы сразу — уже шум
    games = career.get("gamesPlayed", 0)
    if games and (games + 1) % 100 == 0:
        add(0, f"🎯 {name} может провести {games + 1}-й матч в НХЛ", games + 1)

    points = goals = 0
    for g in last:
        if g.get("points", 0) == 0:
            break
        points += 1
    for g in last:
        if g.get("goals", 0) == 0:
            break
        goals += 1
    if goals >= 3:
        add(1, f"🔥 {name} забивает {goals} {plural(goals, ('матч', 'матча', 'матчей'))} подряд", goals)
    elif points >= 4:
        add(1, f"🔥 {name} набирает очки {points} {plural(points, ('матч', 'матча', 'матчей'))} подряд", points)

    season = (data.get("featuredStats") or {}).get("regularSeason", {}).get("subSeason") or {}
    gp, sg = season.get("gamesPlayed", 0), season.get("goals", 0)
    if gp >= 5 and sg >= gp:
        add(2, f"📊 {name} — {sg} {plural(sg, ('гол', 'гола', 'голов'))} в {gp} "
               f"{plural(gp, ('матче', 'матчах', 'матчах'))} сезона", sg, gp)
    sp = season.get("points", 0)
    if gp and sp:  # кандидат в «лучший из наших в сезоне» — pick возьмёт одного, с максимумом очков
        add(3, f"📊 Лучший из наших в сезоне — {name}: {sp} {plural(sp, ('очко', 'очка', 'очков'))} "
               f"в {gp} {plural(gp, ('матче', 'матчах', 'матчах'))}", sp, gp)
        items[-1]["value"] = sp
    return items


def collect(ours_by_team: dict[str, list[tuple[int, str]]], fetch=fetch_json) -> list[dict]:
    """Интриги всех наших в составах; игрок без ответа API просто без интриги."""
    items = []
    for recs in ours_by_team.values():
        for pid, surname in recs:
            try:
                items += player_items(pid, surname, landing(pid, fetch))
            except RuntimeError:
                continue
    return items


def team_items(playing: set[str], teams: dict, fetch=fetch_json) -> list[dict]:
    """Клубы вечера из таблицы (один запрос): лидер НХЛ, серия от 3 побед или поражений подряд."""
    try:
        table = fetch(f"{WEB}/standings/now").get("standings", [])
    except RuntimeError:
        return []
    items = []
    for row in table:
        abbr = row.get("teamAbbrev", {}).get("default")
        if abbr not in playing or abbr not in teams:
            continue
        name, n, code = teams[abbr], row.get("streakCount", 0), row.get("streakCode")
        base = {"pid": None, "team": abbr, "teams": [name]}
        if row.get("leagueSequence") == 1:
            items.append({**base, "rank": 1, "text": f"👑 {name} — лидер НХЛ", "numbers": []})
        if n >= 3 and code in ("W", "L"):
            words = ("победа", "победы", "побед") if code == "W" else ("поражение", "поражения", "поражений")
            mark = "📈" if code == "W" else "📉"
            items.append({**base, "rank": 1, "text": f"{mark} {name} — {n} {plural(n, words)} подряд",
                          "numbers": [str(n)]})
    return items


def pick(items: list[dict], playing: set[int], limit: int = 5) -> list[dict]:
    """Лучшие интриги вечера: по одной на игрока и на клуб; игрок — только если сегодня в составе.
    «Лучший из наших в сезоне» (rank 3) — один, с максимумом очков, и если у него нет другой интриги."""
    pool = [it for it in items if it.get("pid") is None or it["pid"] in playing]
    out, seen = [], set()
    for it in sorted((it for it in pool if it["rank"] < 3), key=lambda x: x["rank"]):
        key = it["pid"] if it.get("pid") is not None else it["team"]
        if key not in seen:
            out.append(it)
            seen.add(key)
    out = out[:limit - 1]
    best = max((it for it in pool if it["rank"] == 3), key=lambda x: x["value"], default=None)
    if best and best["pid"] not in {it.get("pid") for it in out}:
        out.append(best)
    return out
