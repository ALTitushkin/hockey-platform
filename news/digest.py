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


def render_night(reports: list[GameReport], players: dict, teams: dict, msk_date: str,
                 highlights: list | None = None, compact: bool = False) -> tuple[str, dict]:
    """→ (HTML-текст для Telegram, факты для гарда). Пустой список матчей → пустой текст.

    highlights — `events.headline(...)`: [(pid, [Event, ...]), ...]. Есть события — блок «Главное»
    строится из них (рекорд важнее двух очков); нет — главный тот, у кого больше очков.
    compact — для тяжёлых ночей, когда пост не влезает в подпись к картинке: наши в матче
    одной строкой, матчи без наших очков — только на картинке.
    """
    y, m, d = (int(x) for x in msk_date.split("-"))
    facts = {"numbers": {d}, "pids": set(), "teams": set()}
    if not reports:
        return "", facts

    names = display_names(reports, players)
    lines = [f"🌙 <b>Ночь наших</b> · {d} {MONTHS[m - 1]}", ""]

    best = max((s for r in reports for s in r.skaters), key=lambda s: (s.points, s.goals), default=None)
    if highlights:
        lines.append("⭐ <b>Главное</b>")
        for pid, evs in highlights:
            lines.append(f"<b>{names[pid]}</b> — {', '.join(e.text for e in evs)}")
            for e in evs:
                facts["numbers"] |= e.numbers
        lines.append("")
    elif best and best.points >= 2:
        lines.append(f"⭐ <b>Главное:</b> {names[best.pid]} — {best.points} "
                     f"{plural(best.points, ('очко', 'очка', 'очков'))} ({best.goals}+{best.assists})")
        lines.append("")
        facts["numbers"] |= {best.points}

    # Матч попадает в текст, если у наших есть очки или играл наш вратарь. Остальные — в
    # свёрнутый блок: пост короче (подпись к картинке — до 1024 знаков), но никто не потерян.
    idle_players, idle_games = [], []
    for r in reports:
        home, away = teams[r.home], teams[r.away]
        facts["teams"] |= {home, away}
        facts["numbers"] |= {r.home_score, r.away_score}
        head = f"{home} — {away} {r.home_score}:{r.away_score}{SUFFIX.get(r.last_period, '')}"
        rows, scored = [], []
        for s in sorted(r.skaters, key=lambda s: (-s.points, -s.goals)):
            facts["pids"].add(s.pid)
            facts["numbers"] |= {s.goals, s.assists, s.sog}
            if s.points:
                scored.append(f"{names[s.pid]} <b>{s.goals}+{s.assists}</b>" if compact
                              else f"🏒 {names[s.pid]} — <b>{s.goals}+{s.assists}</b>")
            else:
                idle_players.append(names[s.pid])
        for g in r.goalies:
            facts["pids"].add(g.pid)
            facts["numbers"] |= {g.saves, g.shots}
            word = (DECISION_SO if r.last_period == "SO" else {}).get(g.decision) or DECISION.get(g.decision)
            against = r.away_score if g.team == r.home else r.home_score
            result = (f", {word}" if word else "") + (", на ноль" if against == 0 and g.saves == g.shots else "")
            rows.append(f"🥅 {names[g.pid]} — {g.saves} {plural(g.saves, ('сейв', 'сейва', 'сейвов'))} "
                        f"из {g.shots}{result}")
        rows = (["🏒 " + ", ".join(scored)] if compact and scored else scored) + rows
        if rows:
            lines += [f"<b>{head}</b>", *rows] + ([] if compact else [""])
        else:
            idle_games.append(head)

    idle = []
    if idle_players:
        idle.append("Без очков: " + ", ".join(idle_players))
    if idle_games and not compact:
        idle.append("Ещё матчи: " + "; ".join(idle_games))
    if idle:
        lines += [""] if compact else []
        lines.append("<blockquote expandable>" + "\n".join(idle) + "</blockquote>")
    return "\n".join(lines).strip(), facts


def with_lead(text: str, lead: str) -> str:
    """Вставить вводную фразу цитатой сразу после заголовка; сам блок статистики не трогаем."""
    title, _, body = text.partition("\n\n")
    return f"{title}\n\n<blockquote>{lead}</blockquote>\n\n{body}"
