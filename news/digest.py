"""Шаблоны утренних постов: «Ночь наших» (россияне и белорусы в НХЛ) и «Ночь в НХЛ» (вся лига).

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


def save_pct(saves: int, shots: int, facts: dict) -> str:
    """%ОБ за матч: «93,9%», сухой матч — «100%». Числа процента — в факты для гарда."""
    pct = "100" if saves == shots else f"{saves / shots * 100:.1f}".replace(".", ",")
    facts["numbers"] |= {int(x) for x in pct.split(",")}
    return f"{pct}%"


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
                 highlights: list | None = None) -> tuple[str, dict]:
    """→ (HTML-текст для Telegram, факты для гарда). Пустой список матчей → пустой текст.

    highlights — `events.headline(...)`: [(pid, [Event, ...]), ...]. Есть события — блок «Главное»
    строится из них (рекорд важнее двух очков); нет — главный тот, у кого больше очков.
    Это полный текст по матчам: его читает модель для вводной фразы, он же — запасной пост без
    картинки. В канал с карточкой идёт `render_caption`.
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
        rows = []
        for s in sorted(r.skaters, key=lambda s: (-s.points, -s.goals)):
            facts["pids"].add(s.pid)
            facts["numbers"] |= {s.goals, s.assists, s.sog}
            if s.points:
                rows.append(f"🏒 {names[s.pid]} — <b>{s.goals}+{s.assists}</b>")
            else:
                idle_players.append(names[s.pid])
        for g in r.goalies:
            facts["pids"].add(g.pid)
            facts["numbers"] |= {g.saves, g.shots}
            word = (DECISION_SO if r.last_period == "SO" else {}).get(g.decision) or DECISION.get(g.decision)
            against = r.away_score if g.team == r.home else r.home_score
            result = (f", {word}" if word else "") + (", на ноль" if against == 0 and g.saves == g.shots else "")
            rows.append(f"🥅 {names[g.pid]} — {g.saves} {plural(g.saves, ('сейв', 'сейва', 'сейвов'))} "
                        f"из {g.shots} ({save_pct(g.saves, g.shots, facts)}){result}")
        if rows:
            lines += [f"<b>{head}</b>", *rows, ""]
        else:
            idle_games.append(head)

    idle = []
    if idle_players:
        idle.append("Без очков: " + ", ".join(idle_players))
    if idle_games:
        idle.append("Ещё матчи: " + "; ".join(idle_games))
    if idle:
        lines.append("<blockquote expandable>" + "\n".join(idle) + "</blockquote>")
    return "\n".join(lines).strip(), facts


ICONS = [("в истории клуба", "🏆"), ("-й гол в НХЛ", "🎯"), ("-е очко в НХЛ", "🎯"), ("-й матч", "🎖"),
         ("перв", "✨"), ("победный", "🚨"), ("хет-трик", "🎩"), ("гола за матч", "🎩"), ("за матч", "💥"),
         ("сухой матч", "🧱")]


def icon(text: str) -> str:
    return next((e for key, e in ICONS if key in text), "⭐")


def render_caption(reports: list[GameReport], players: dict, teams: dict, msk_date: str,
                   highlights: list | None = None, lead: str | None = None,
                   with_teams: bool = True) -> tuple[str, dict]:
    """Подпись к карточке: как у больших спортивных каналов — заголовок-новость, абзац, блоки через
    пустую строку, одна метка на строку, подпись рубрики в конце. Счёт всех матчей — на картинке,
    в тексте — сюжет и очки наших. with_teams=False — запасной вариант, если не влезает в 1024 знака.
    """
    _, m, d = (int(x) for x in msk_date.split("-"))
    facts = {"numbers": {d}, "pids": set(), "teams": set()}
    if not reports:
        return "", facts
    names = display_names(reports, players)
    team_of = {s.pid: teams[s.team] for r in reports for s in r.skaters} | \
              {g.pid: teams[g.team] for r in reports for g in r.goalies}
    for r in reports:
        facts["teams"] |= {teams[r.home], teams[r.away]}
        facts["numbers"] |= {r.home_score, r.away_score}

    blocks = []
    rest = list(highlights or [])
    if rest:
        pid, evs = rest[0]
        top = evs[0]
        facts["numbers"] |= top.numbers
        blocks.append(f"{icon(top.text)} <b>{names[pid]} — {top.text}</b>")
        others = [(pid, evs[1:])] if evs[1:] else []
        rest = others + rest[1:]
    else:
        blocks.append(f"🌙 <b>Ночь наших · {d} {MONTHS[m - 1]}</b>")
    if lead:
        blocks.append(lead)
    if rest:
        lines = ["⭐ <b>Ещё главное</b>"]
        for pid, evs in rest:
            for e in evs:
                facts["numbers"] |= e.numbers
            lines.append(f"{icon(evs[0].text)} {names[pid]} — {', '.join(e.text for e in evs)}")
        blocks.append("\n".join(lines))

    # Без меток в строках: опора для глаза — фамилия жирным; группы «2+ очка» и «1 очко» — через
    # пустую строку. Так строки не сливаются и пост не пестрит (выбор владельца 25.10.2026).
    def club(pid: int) -> str:
        return f" · {team_of[pid]}" if with_teams else ""

    scorers = sorted((s for r in reports for s in r.skaters), key=lambda s: (-s.points, -s.goals))
    groups: dict[bool, list[str]] = {True: [], False: []}
    idle = []
    for s in scorers:
        facts["pids"].add(s.pid)
        facts["numbers"] |= {s.goals, s.assists, s.sog}
        if s.points:
            groups[s.points >= 2].append(f"<b>{names[s.pid]}</b> {s.goals}+{s.assists}{club(s.pid)}")
        else:
            idle.append(names[s.pid])
    keepers = []
    for r in reports:
        for g in r.goalies:
            facts["pids"].add(g.pid)
            facts["numbers"] |= {g.saves, g.shots}
            word = (DECISION_SO if r.last_period == "SO" else {}).get(g.decision) or DECISION.get(g.decision)
            result = f", {word}" if word else ""
            keepers.append(f"🥅 <b>{names[g.pid]}</b> {g.saves} из {g.shots} ({save_pct(g.saves, g.shots, facts)})"
                           f"{club(g.pid)}{result}")
    parts = ["\n".join(x) for x in (groups[True], groups[False], keepers) if x]
    if parts:
        blocks.append("📊 <b>Очки наших</b>\n" + "\n\n".join(parts))
    if idle:
        blocks.append("<blockquote expandable>Без очков: " + ", ".join(idle) + "</blockquote>")
    blocks.append(f"🌙 #НочьНаших · {d} {MONTHS[m - 1]}")
    return "\n\n".join(blocks), facts


def render_league(reports: list[GameReport], players: dict, teams: dict, msk_date: str,
                  highlights: list | None = None, stars: int = 5) -> tuple[str, dict]:
    """«Ночь в НХЛ»: вся лига. Счёт всех матчей — на карточке, в подписи — события ночи и звёзды по очкам.
    players — только игроки с русским именем (names.league_players): кого нет, того нет и в посте."""
    _, m, d = (int(x) for x in msk_date.split("-"))
    facts = {"numbers": {d}, "pids": set(), "teams": set()}
    if not reports:
        return "", facts
    skaters = [s for r in reports for s in r.skaters if str(s.pid) in players]
    goalies = [g for r in reports for g in r.goalies if str(g.pid) in players]
    names = display_names([GameReport(0, "", "", 0, 0, "REG", skaters, goalies)], players)
    team_of = {ln.pid: teams[ln.team] for ln in skaters + goalies}
    for r in reports:
        facts["teams"] |= {teams[r.home], teams[r.away]}
        facts["numbers"] |= {r.home_score, r.away_score}

    blocks, rest = [], [(pid, evs) for pid, evs in highlights or [] if str(pid) in players]
    if rest:
        pid, evs = rest.pop(0)
        facts["pids"].add(pid)
        facts["numbers"] |= evs[0].numbers
        blocks.append(f"{icon(evs[0].text)} <b>{names[pid]} — {evs[0].text}</b> · {team_of[pid]}")
        if evs[1:]:
            rest.insert(0, (pid, evs[1:]))
    else:
        blocks.append(f"🏒 <b>Ночь в НХЛ · {d} {MONTHS[m - 1]}</b>")
    if rest:
        lines = ["⭐ <b>Ещё главное</b>"]
        for pid, evs in rest:
            facts["pids"].add(pid)
            for e in evs:
                facts["numbers"] |= e.numbers
            lines.append(f"{icon(evs[0].text)} {names[pid]} — {', '.join(e.text for e in evs)} · {team_of[pid]}")
        blocks.append("\n".join(lines))

    # звёзды ночи: больше всех очков, от двух; ничья по очкам — больше голов
    top = sorted((s for s in skaters if s.points >= 2), key=lambda s: (-s.points, -s.goals))
    if top[:stars]:
        rows = []
        for s in top[:stars]:
            facts["pids"].add(s.pid)
            facts["numbers"] |= {s.goals, s.assists}
            rows.append(f"<b>{names[s.pid]}</b> {s.goals}+{s.assists} · {team_of[s.pid]}")
        blocks.append("📊 <b>Звёзды ночи</b>\n" + "\n".join(rows))
    blocks.append(f"🏒 #НочьВНХЛ · {d} {MONTHS[m - 1]}")
    return "\n\n".join(blocks), facts


NOT_PLAYED = "не играл прошлый матч"


def render_tonight(games: list[dict], ours_by_team: dict[str, list[tuple[int, str]]], teams: dict, msk_date: str,
                   tz, out_by_team: dict[str, list[tuple[int, str, str]]] | None = None,
                   items: list[dict] | None = None, hook: tuple[str, list[str]] | None = None) -> tuple[str, dict]:
    """«Сегодня ночью»: расписание и наши — на карточке, в тексте то, чего на ней нет: интриги вечера
    (`intrigue.pick`) и кто из наших не сыграет. games — `nhl.upcoming_games`,
    ours_by_team — {клуб: [(id, фамилия), ...]}, out_by_team — {клуб: [(id, фамилия, причина), ...]}."""
    from datetime import datetime

    out_by_team, items = out_by_team or {}, items or []
    _, m, d = (int(x) for x in msk_date.split("-"))
    facts = {"numbers": {d, len(games)}, "pids": set(), "teams": set()}
    if not games:
        return "", facts
    start_of, team_game = {}, {}
    for g in games:
        start = datetime.fromisoformat(g["start"].replace("Z", "+00:00")).astimezone(tz)
        start_of[id(g)] = (f"{start:%H}", f"{start:%M}")  # гард сверяет строки: «02» и «00» — не числа 2 и 0
        team_game |= {g["home"]: g, g["away"]: g}
    team_of = {pid: t for t, recs in ours_by_team.items() for pid, _ in recs}
    n_ours = sum(len(v) for v in ours_by_team.values())
    word = plural(len(games), ("матч", "матча", "матчей"))
    title = f"📺 <b>Сегодня ночью в НХЛ</b> · {len(games)} {word}"
    if n_ours:
        title += f" · {n_ours} {plural(n_ours, ('наш', 'наших', 'наших'))}"
        facts["numbers"].add(n_ours)
    blocks = [title]

    rows = []
    for it in items:
        hh, mm = start_of[id(team_game[it.get("team") or team_of[it["pid"]]])]
        rows.append(f"{it['text']} · {hh}:{mm}")
        facts["numbers"] |= set(it["numbers"]) | {hh, mm}
        facts["teams"] |= set(it.get("teams", []))
        if it.get("pid") is not None:
            facts["pids"].add(it["pid"])
    if not rows and n_ours:  # интриг нет — хотя бы где смотреть наших
        g = max(games, key=lambda g: len(ours_by_team.get(g["home"], [])) + len(ours_by_team.get(g["away"], [])))
        n = len(ours_by_team.get(g["home"], [])) + len(ours_by_team.get(g["away"], []))
        hh, mm = start_of[id(g)]
        home, away = teams[g["home"]], teams[g["away"]]
        rows.append(f"👀 Больше всего наших — <b>{hh}:{mm}</b> {home} — {away}: {n}")
        facts["numbers"] |= {hh, mm, n}
        facts["teams"] |= {home, away}
    if rows:
        blocks.append("🔥 <b>Интриги вечера</b>\n" + "\n".join(rows))

    skip = [x for v in out_by_team.values() for x in v]
    if skip:
        facts["pids"] |= {pid for pid, _, _ in skip}
        by_why: dict[str, list[str]] = {}
        for _, name, why in skip:
            by_why.setdefault(why, []).append(name)
        # травма — точно не сыграет; не было в прошлом матче — под вопросом (может вернуться в состав)
        sure = [f"{', '.join(names)} — {why}" for why, names in by_why.items() if why != NOT_PLAYED]
        if sure:
            blocks.append("🚑 <b>Не сыграют</b>\n" + "\n".join(sure))
        if NOT_PLAYED in by_why:
            blocks.append(f"❔ <b>Под вопросом</b>\n{', '.join(by_why[NOT_PLAYED])} — {NOT_PLAYED}")
    if hook:
        blocks.append(hook[0])
        facts["teams"] |= set(hook[1])
    blocks.append(f"📺 #СегодняНочью · {d} {MONTHS[m - 1]} · время московское")
    return "\n\n".join(blocks), facts


def tonight_hook(games: list[dict], ours_by_team: dict[str, list[tuple[int, str]]], goalies: set[int],
                 teams: dict) -> tuple[str, list[str]] | None:
    """Вопрос в комментарии — один на день, только в вечернем посте (просьба владельца: «не переборщить»).
    «Кто из наших забьёт» — только если играет наш полевой: иначе вопрос был бы про пустоту.
    → (строка, клубы в ней) или None."""
    if not games:
        return None
    if any(pid not in goalies for recs in ours_by_team.values() for pid, _ in recs):
        return "💬 Кто из наших забьёт сегодня? Пишите в комментариях", []
    g = max(games, key=lambda g: len(ours_by_team.get(g["home"], [])) + len(ours_by_team.get(g["away"], [])))
    home, away = teams[g["home"]], teams[g["away"]]
    return f"💬 Ваш прогноз на матч {home} — {away}? Пишите в комментариях", [home, away]


def with_lead(text: str, lead: str) -> str:
    """Вставить вводную фразу цитатой сразу после заголовка; сам блок статистики не трогаем."""
    title, _, body = text.partition("\n\n")
    return f"{title}\n\n<blockquote>{lead}</blockquote>\n\n{body}"
