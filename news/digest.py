"""Шаблон поста «Ночь наших»: утренний дайджест по матчам НХЛ с участием россиян и белорусов.

Текст собирается только из данных. Фамилии — только из реестра, в именительном падеже
(склонять фамилии шаблоном — верный способ ошибиться). Рядом с текстом возвращаются
факты — по ним `guard.py` проверяет и этот текст, и любую его переписанную версию.
"""

from collections import Counter

from news.nhl import GameReport

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]
SUFFIX = {"OT": " ОТ", "SO": " Б"}
DECISION = {"W": "победа", "L": "поражение", "O": "поражение в овертайме"}
DECISION_SO = {"O": "поражение по буллитам"}


def plural(n: int, forms: tuple[str, str, str]) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def display_names(reports: list[GameReport], players: dict) -> dict[int, str]:
    """Фамилия, а при совпадении фамилий в одном посте — с инициалом (братья Протасы)."""
    pids = [ln.pid for r in reports for ln in r.skaters + r.goalies]
    counts = Counter(players[str(p)]["surname"] for p in set(pids))
    names = {}
    for p in pids:
        rec = players[str(p)]
        names[p] = f"{rec['ru'][0]}. {rec['surname']}" if counts[rec["surname"]] > 1 else rec["surname"]
    return names


def render_night(reports: list[GameReport], players: dict, teams: dict, msk_date: str) -> tuple[str, dict]:
    """→ (HTML-текст для Telegram, факты для гарда). Пустой список матчей → пустой текст."""
    y, m, d = (int(x) for x in msk_date.split("-"))
    facts = {"numbers": {d}, "pids": set(), "teams": set()}
    if not reports:
        return "", facts

    names = display_names(reports, players)
    lines = [f"🌙 <b>Ночь наших</b> · {d} {MONTHS[m - 1]}", ""]

    best = max((s for r in reports for s in r.skaters), key=lambda s: (s.points, s.goals), default=None)
    if best and best.points >= 2:
        lines.append(f"⭐ Главное: {names[best.pid]} — {best.points} {plural(best.points, ('очко', 'очка', 'очков'))}"
                     f" ({best.goals}+{best.assists})")
        lines.append("")
        facts["numbers"] |= {best.points}

    for r in reports:
        home, away = teams[r.home], teams[r.away]
        facts["teams"] |= {home, away}
        facts["numbers"] |= {r.home_score, r.away_score}
        lines.append(f"<b>{home} — {away} {r.home_score}:{r.away_score}{SUFFIX.get(r.last_period, '')}</b>")
        for s in sorted(r.skaters, key=lambda s: (-s.points, -s.goals)):
            facts["pids"].add(s.pid)
            facts["numbers"] |= {s.goals, s.assists, s.sog}
            score = f"{s.goals}+{s.assists}" if s.points else "без очков"
            shots = f", {s.sog} {plural(s.sog, ('бросок', 'броска', 'бросков'))}" if s.sog else ""
            lines.append(f"• {names[s.pid]} ({teams[s.team]}) — {score}{shots}")
        for g in r.goalies:
            facts["pids"].add(g.pid)
            facts["numbers"] |= {g.saves, g.shots}
            word = (DECISION_SO if r.last_period == "SO" else {}).get(g.decision) or DECISION.get(g.decision)
            result = f", {word}" if word else ""
            lines.append(f"• {names[g.pid]} ({teams[g.team]}) — {g.saves} "
                         f"{plural(g.saves, ('сейв', 'сейва', 'сейвов'))} из {g.shots}{result}")
        lines.append("")

    lines.append("Матчи прошли ночью по московскому времени.")
    return "\n".join(lines).strip(), facts


def with_lead(text: str, lead: str) -> str:
    """Вставить вводную фразу сразу после заголовка; сам блок статистики не трогаем."""
    title, _, body = text.partition("\n\n")
    return f"{title}\n\n{lead}\n\n{body}"
