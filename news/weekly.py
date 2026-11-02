"""Weekly RUS/BLR regular-season recap, aggregated by NHL. No model calls."""

import html
import re
from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from urllib.parse import urlencode

from news import nhl
from news.digest import MONTHS, plural, save_pct


def period(monday: str) -> tuple[str, str]:
    day = date.fromisoformat(monday)
    if day.weekday() != 0:
        raise ValueError("Недельный выпуск датируется понедельником")
    return (day - timedelta(days=7)).isoformat(), (day - timedelta(days=1)).isoformat()


def collect(monday: str, players: dict, fetch: Callable[[str], dict] = nhl.fetch_json) -> dict:
    """Two summary requests; reject truncated, duplicate or inconsistent aggregates."""
    start, end = period(monday)
    query = urlencode({"isAggregate": "true", "isGame": "true", "start": 0, "limit": -1,
                       "cayenneExp": f'gameTypeId=2 and gameDate>="{start}" and gameDate<="{end}"'})
    result = {"start": start, "end": end, "sources": [], "skaters": [], "goalies": []}
    for kind, key in (("skater", "skaters"), ("goalie", "goalies")):
        url = f"{nhl.STATS}/{kind}/summary?{query}"
        response = fetch(url)
        rows = response.get("data")
        if not isinstance(rows, list) or type(response.get("total")) is not int or response["total"] != len(rows):
            raise RuntimeError(f"Недельная статистика {kind}: неполный ответ")
        seen = set()
        for row in rows:
            pid = row.get("playerId")
            if type(pid) is not int or pid <= 0 or pid in seen:
                raise RuntimeError(f"Недельная статистика {kind}: неверный/повторный NHL ID")
            seen.add(pid)
            if str(pid) not in players:
                continue
            fields = ("gamesPlayed", "goals", "assists", "points", "plusMinus") if kind == "skater" else (
                "gamesPlayed", "wins", "shutouts", "saves", "shotsAgainst")
            if any(type(row.get(f)) is not int or (f != "plusMinus" and row[f] < 0) for f in fields):
                raise RuntimeError(f"Недельная статистика {kind}: неверные числа для {pid}")
            if row["gamesPlayed"] > 7:
                raise RuntimeError("Недельная статистика: ответ не похож на недельный")
            if kind == "skater" and row["points"] != row["goals"] + row["assists"]:
                raise RuntimeError(f"Недельная статистика: очки не сходятся для {pid}")
            if kind == "goalie" and (row["wins"] > row["gamesPlayed"] or row["shutouts"] > row["gamesPlayed"]
                                     or row["saves"] > row["shotsAgainst"]):
                raise RuntimeError(f"Недельная статистика: результаты вратаря не сходятся для {pid}")
            if not row["gamesPlayed"] and any(row[f] for f in fields if f != "gamesPlayed"):
                raise RuntimeError(f"Недельная статистика: есть результат без сыгранных матчей для {pid}")
            if not row["gamesPlayed"]:
                continue
            if not players[str(pid)].get("ru") or not players[str(pid)].get("surname"):
                raise RuntimeError(f"Недельная статистика: нет русского имени для NHL ID {pid}")
            result[key].append({"pid": pid, **{f: row[f] for f in fields}})
        result["sources"].append(url)
    return result


def render(data: dict, players: dict) -> tuple[str, dict]:
    """Leaders, remaining skaters and all active goalies; totals are over the full week.

    Save percentage uses aggregate saves/shots, never the mean of game percentages.
    Dates refer to NHL game dates, not the Moscow date of the final whistle.
    """
    skaters = sorted(data["skaters"], key=lambda p: (-p["points"], -p["goals"], p["pid"]))
    goalies = sorted(data["goalies"], key=lambda p: (-p["wins"], -p["saves"], p["pid"]))
    if not skaters and not goalies:
        return "", {"numbers": set(), "pids": set(), "teams": set()}
    facts = {"numbers": set(), "pids": {p["pid"] for p in skaters + goalies}, "teams": set()}

    def name(pid: int) -> str:
        return html.escape(players[str(pid)]["ru"])

    def day(value: str) -> str:
        d = date.fromisoformat(value)
        return f"{d.day} {MONTHS[d.month - 1]}"

    span = f"{day(data['start'])} — {day(data['end'])}"
    if skaters and skaters[0]["points"]:
        leader = skaters[0]
        score = leader["points"]
        headline = f"📊 <b>{name(leader['pid'])} — {score} {plural(score, ('очко', 'очка', 'очков'))} за неделю</b>"
    else:
        headline = f"📊 <b>Неделя наших в НХЛ: {span}</b>"
    parts = [headline, f"{span}. Итоги регулярного чемпионата по датам матчей НХЛ."]
    achievements = data.get("achievements", [])
    if achievements:
        lines = []
        for event in achievements:
            phrase = html.escape(event["text"])
            url = html.escape(event["url"], quote=True)
            lines.append(f"<b>{name(event['pid'])}</b> — <a href=\"{url}\">{phrase}</a>")
            facts["pids"].add(event["pid"])
            facts["numbers"] |= {str(int(n)) for n in re.findall(r"\d+", event["text"])}
        parts.append("🏆 <b>Достижения недели</b>\n" + "\n".join(lines))
    if skaters:
        def line(p: dict, label: str) -> str:
            games = p["gamesPlayed"]
            value = p.get("plusMinus")
            # Old saved weekly data did not contain this field; never invent zero.
            rating = (f"{value:+d}" if value else "0") if type(value) is int else "н/д"
            return (f"<b>{label}</b> — {p['points']} ({p['goals']}+{p['assists']}), "
                    f"{games} {plural(games, ('матч', 'матча', 'матчей'))}; +/− {rating}")

        parts.append("🏒 <b>Очки и полезность (+/−) за неделю</b>\n"
                     + "\n".join(line(p, name(p["pid"])) for p in skaters[:5]))
        if len(skaters) > 5:
            surnames = Counter(players[str(p["pid"])]["surname"] for p in skaters)
            more = []
            for p in skaters[5:]:
                surname = players[str(p["pid"])]["surname"]
                label = name(p["pid"]) if surnames[surname] > 1 else html.escape(surname)
                more.append(line(p, label))
            parts.append("<blockquote expandable>Ещё наши\n" + "\n".join(more) + "</blockquote>")
    if goalies:
        lines = []
        for p in goalies:
            wins, games = p["wins"], p["gamesPlayed"]
            line = (f"<b>{name(p['pid'])}</b> — {wins} {plural(wins, ('победа', 'победы', 'побед'))}, "
                    f"{games} {plural(games, ('матч', 'матча', 'матчей'))}")
            if p["shotsAgainst"]:
                line += f"; отражено {save_pct(p['saves'], p['shotsAgainst'], facts)}"
            else:
                line += "; без бросков по воротам"
            if p["shutouts"]:
                count = p["shutouts"]
                line += f"; {count} {plural(count, ('сухой матч', 'сухих матча', 'сухих матчей'))}"
            lines.append(line)
        parts.append("🥅 <b>Вратари</b>\n" + "\n".join(lines))
    start_year, end_year = date.fromisoformat(data["start"]).year, date.fromisoformat(data["end"]).year
    year = str(start_year) if start_year == end_year else f"{start_year}–{end_year}"
    parts.append(f"📅 #НеделяНаших · {span} {year}")
    text = "\n\n".join(parts)
    # Template numbers are dates and fields already validated above, including derived %.
    facts["numbers"] |= {str(int(n)) for n in re.findall(r"\d+", f"{data['start']} {data['end']}")}
    for row in skaters + goalies:
        facts["numbers"] |= {str(abs(v)) for k, v in row.items() if k != "pid" and type(v) is int}
    return text, facts
