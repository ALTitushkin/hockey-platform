"""Картинка к посту «Ночь наших»: карточка 1080×1350 в стиле «Культуры хоккея».

Своя графика плюс логотипы клубов (news/assets/logos, обновляет `python -m news.logos`) — только
как обозначение клуба. Фото игроков не берём: это чужие снимки. Шрифты Oswald и PT Sans (OFL) — news/assets/fonts.
Цифры берутся из тех же отчётов, что и текст поста, — отдельно гард их не проверяет.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from news import logos
from news.digest import MONTHS, SUFFIX, display_names, plural
from news.nhl import GameReport

FONTS = Path(__file__).parent / "assets" / "fonts"
W = 1080
PAPER, CARD, INK, SOFT, FAINT = "#F1EAD8", "#FAF4E2", "#20242C", "#3C4350", "#7A7763"
BRICK, STEEL, NAVY, LINE = "#9E3B2C", "#44698D", "#1B2433", "#CFC4AA"
PAD = 64


def font(name: str, size: int, weight: str | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight:
        f.set_variation_by_name(weight)
    return f


def fit(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int) -> str:
    if draw.textlength(text, font=f) <= width:
        return text
    while text and draw.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text.rstrip(" ,·") + "…"


def paste_logo(img: Image.Image, abbrev: str, x: int, y: int, box: int, crop: bool = False) -> int:
    """Логотип в квадрат box×box с сохранением пропорций → сколько места занял по ширине. Нет файла — 0.
    crop — срезать прозрачные поля (у PNG из CDN знак занимает около половины холста)."""
    src = logos.path(abbrev)
    if not src.exists():
        return 0
    logo = Image.open(src).convert("RGBA")
    if crop and logo.getchannel("A").getbbox():
        logo = logo.crop(logo.getchannel("A").getbbox())
    scale = box / max(logo.size)  # крупный логотип на карточке инфоповода — увеличиваем, не только ужимаем
    logo = logo.resize((max(1, round(logo.width * scale)), max(1, round(logo.height * scale))), Image.LANCZOS)
    img.paste(logo, (x + (box - logo.width) // 2, y + (box - logo.height) // 2), logo)
    return box


def ours_line(r: GameReport, names: dict[int, str]) -> str:
    parts = [f"{names[s.pid]} {s.goals}+{s.assists}" for s in sorted(r.skaters, key=lambda s: (-s.points, -s.goals))
             if s.points]
    parts += [f"{names[g.pid]} {g.saves}/{g.shots}" for g in r.goalies]
    return " · ".join(parts) or "наши без очков"


def result_word(r: GameReport, team: str) -> str:
    """«победа 6:3» / «поражение 2:3 ОТ» — счёт со стороны клуба игрока."""
    own, opp = (r.home_score, r.away_score) if team == r.home else (r.away_score, r.home_score)
    return f"{'победа' if own > opp else 'поражение'} {own}:{opp}{SUFFIX.get(r.last_period, '')}"


def player_rows(reports: list[GameReport], names: dict[int, str]) -> tuple[list[tuple], list[str]]:
    """«Ночь наших» на карточке: → (строки (клуб, имя, крупно, мелко, выделить), без очков).
    Полевые с очками — по очкам и голам, затем вратари; без очков — одним списком внизу."""
    skaters = sorted(((s, r) for r in reports for s in r.skaters if s.points),
                     key=lambda x: (-x[0].points, -x[0].goals))
    rows = [(s.team, names[s.pid], f"{s.goals}+{s.assists}", result_word(r, s.team), True) for s, r in skaters]
    for g, r in ((g, r) for r in reports for g in r.goalies):
        pct = "100" if g.saves == g.shots else f"{g.saves / g.shots * 100:.1f}".replace(".", ",")
        rows.append((g.team, names[g.pid], f"{g.saves}/{g.shots}", f"{pct}% · {result_word(r, g.team)}", False))
    idle = [names[s.pid] for r in reports for s in r.skaters if not s.points]
    return rows, idle


def stars_line(r: GameReport, names: dict[int, str]) -> str:
    """Строка матча в «Ночи в НХЛ»: двое лучших по очкам (с русским именем) и вратарь на ноль."""
    top = sorted((s for s in r.skaters if s.points and s.pid in names), key=lambda s: (-s.points, -s.goals))[:2]
    parts = [f"{names[s.pid]} {s.goals}+{s.assists}" for s in top]
    for g in r.goalies:
        against = r.away_score if g.team == r.home else r.home_score
        if g.pid in names and against == 0 and g.saves == g.shots:
            parts.append(f"{names[g.pid]} {g.saves}/{g.shots}")
    return " · ".join(parts)


def render_tonight_card(games: list[dict], ours_by_team: dict[str, list[tuple[int, str]]], teams: dict,
                        msk_date: str, tz, path: Path) -> Path:
    """Афиша «Сегодня ночью»: время по Москве крупно слева, клубы с логотипами, под матчем — наши."""
    from datetime import datetime

    _, m, d = (int(x) for x in msk_date.split("-"))
    head_h, hero_h, foot_h = 250, 190, 110
    mono, small = font("PTSans-Bold.ttf", 26), font("PTSans-Regular.ttf", 30)
    tm = font("Oswald.ttf", 44, "Bold")
    probe = ImageDraw.Draw(Image.new("RGB", (W, 10)))
    time_w = int(probe.textlength("00:00", font=tm)) + 28
    # наших в матче бывает пятеро — строка «наши: …» переносится, высота строки матча растёт
    ours_lines = []
    for g in games:
        ours = [name for _, name in ours_by_team.get(g["home"], []) + ours_by_team.get(g["away"], [])]
        text = "наши: " + ", ".join(ours) if ours else "без наших"
        ours_lines.append((wrap(probe, text, small, W - 2 * PAD - time_w, 3), bool(ours)))
    heights = [86 + 38 * len(lines) for lines, _ in ours_lines]
    h = max(1350, head_h + hero_h + sum(heights) + foot_h + 40)
    img = Image.new("RGB", (W, h), PAPER)
    dr = ImageDraw.Draw(img)

    dr.text((PAD, 58), "КУЛЬТУРА ХОККЕЯ  ·  НХЛ", font=mono, fill=FAINT)
    dr.text((PAD, 92), "СЕГОДНЯ НОЧЬЮ", font=font("Oswald.ttf", 104, "Bold"), fill=INK)
    date = f"{d} {MONTHS[m - 1]}".upper()
    df = font("Oswald.ttf", 44, "Medium")
    dr.text((W - PAD - dr.textlength(date, font=df), 40), date, font=df, fill=BRICK)
    for dy in (head_h - 14, head_h - 6):
        dr.line((PAD, dy, W - PAD, dy), fill=INK, width=3)

    top = head_h + 24
    dr.rounded_rectangle((PAD, top, W - PAD, top + hero_h - 40), radius=6, fill=NAVY)
    n_ours = sum(len(ours_by_team.get(g["home"], [])) + len(ours_by_team.get(g["away"], [])) for g in games)
    dr.text((PAD + 36, top + 18), "В ПРОГРАММЕ", font=mono, fill="#C9D3DF")
    dr.text((PAD + 36, top + 46), f"{len(games)} {plural(len(games), ('матч', 'матча', 'матчей'))}",
            font=font("Oswald.ttf", 64, "SemiBold"), fill="#FFFFFF")
    if n_ours:
        label = f"{n_ours} {plural(n_ours, ('наш', 'наших', 'наших'))}"
        sf = font("Oswald.ttf", 64, "SemiBold")
        dr.text((W - PAD - 36 - dr.textlength(label, font=sf), top + 46), label, font=sf, fill="#F2B8A6")

    tf = font("Oswald.ttf", 36, "Medium")
    yy = head_h + hero_h
    for i, g in enumerate(games):
        yy += heights[i - 1] if i else 0
        if i:
            dr.line((PAD, yy - 10, W - PAD, yy - 10), fill=LINE, width=2)
        start = datetime.fromisoformat(g["start"].replace("Z", "+00:00")).astimezone(tz)
        dr.text((PAD, yy), f"{start:%H:%M}", font=tm, fill=BRICK)
        x = PAD + time_w
        for k, abbrev in enumerate((g["home"], g["away"])):
            if k:
                dash = int(dr.textlength(" — ", font=tf))
                dr.text((x, yy + 4), " — ", font=tf, fill=INK)
                x += dash
            used = paste_logo(img, abbrev, x, yy + 6, 54)
            x += used + (12 if used else 0)
            dr.text((x, yy + 4), teams[abbrev], font=tf, fill=INK)
            x += int(dr.textlength(teams[abbrev], font=tf))
        # кто не сыграет — только в подписи: на афише — расписание и наши в составах, без дублей с текстом
        lines, has_ours = ours_lines[i]
        for k, ln in enumerate(lines):
            dr.text((PAD + time_w, yy + 56 + 38 * k), ln, font=small, fill=STEEL if has_ours else FAINT)

    fy = h - foot_h + 20
    dr.line((PAD, fy, W - PAD, fy), fill=INK, width=3)
    dr.text((PAD, fy + 24), "Время московское · данные NHL", font=small, fill=SOFT)
    tag, tg = "Культура хоккея", font("Oswald.ttf", 34, "SemiBold")
    dr.text((W - PAD - dr.textlength(tag, font=tg), fy + 20), tag, font=tg, fill=INK)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    return path


def wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int, lines: int) -> list[str]:
    """Перенос по словам в заданную ширину; не влезло в `lines` строк — последняя с многоточием."""
    out, cur = [], ""
    for word in text.split():
        probe = f"{cur} {word}".strip()
        if draw.textlength(probe, font=f) <= width:
            cur = probe
            continue
        out.append(cur)
        cur = word
    out.append(cur)
    if len(out) > lines:
        out = out[:lines - 1] + [fit(draw, " ".join(out[lines - 1:]), f, width)]
    return [ln for ln in out if ln]


def render_story_card(label: str, teams_abbr: list[str], hero: str | None, ours: bool, headline: str,
                      stats: str | None, teams: dict, msk_date: str, path: Path) -> Path:
    """Инфоповод: вид новости, логотип клуба (у обмена — оба), герой и заголовок; у вратаря — КН и %ОБ.
    Заголовок — тот же, что в посте (прошёл гард), цифры вратаря — из API НХЛ."""
    _, m, d = (int(x) for x in msk_date.split("-"))
    h = 1350
    img = Image.new("RGB", (W, h), PAPER)
    dr = ImageDraw.Draw(img)
    mono, small = font("PTSans-Bold.ttf", 26), font("PTSans-Regular.ttf", 30)

    dr.text((PAD, 58), "КУЛЬТУРА ХОККЕЯ  ·  НХЛ", font=mono, fill=FAINT)
    dr.text((PAD, 92), label, font=font("Oswald.ttf", 104, "Bold"), fill=INK)
    date = f"{d} {MONTHS[m - 1]}".upper()
    df = font("Oswald.ttf", 44, "Medium")
    dr.text((W - PAD - dr.textlength(date, font=df), 150), date, font=df, fill=BRICK)
    for dy in (236, 244):
        dr.line((PAD, dy, W - PAD, dy), fill=INK, width=3)

    # герой и заголовок — на тёмной плашке, как «Главное» в «Ночи наших»; плашка по тексту, у подвала
    inner = W - 2 * PAD - 80
    hf, hl, sf = font("Oswald.ttf", 76, "Bold"), font("Oswald.ttf", 50, "Medium"), font("Oswald.ttf", 38, "Medium")
    hero_lines = wrap(dr, hero.upper(), hf, inner, 2) if hero else []
    head_lines = wrap(dr, headline, hl, inner, 3)
    plate = 40 + (64 if ours else 0) + 88 * len(hero_lines) + (14 if hero_lines else 0) + 62 * len(head_lines) \
        + (66 if stats else 0) + 34
    bottom = h - 150
    y = bottom - plate
    dr.rounded_rectangle((PAD, y, W - PAD, bottom), radius=6, fill=NAVY)
    x, yy = PAD + 40, y + 40
    if ours:
        badge = "НАШ ИГРОК"
        bw = dr.textlength(badge, font=mono) + 32
        dr.rounded_rectangle((x, yy, x + bw, yy + 44), radius=4, fill=BRICK)
        dr.text((x + 16, yy + 7), badge, font=mono, fill="#FFFFFF")
        yy += 64
    for ln in hero_lines:
        dr.text((x, yy - 8), ln, font=hf, fill="#FFFFFF")
        yy += 88
    yy += 14 if hero_lines else 0
    for ln in head_lines:
        dr.text((x, yy), ln, font=hl, fill="#F2B8A6")
        yy += 62
    if stats:
        dr.text((x, yy + 14), stats, font=sf, fill="#C9D3DF")

    # клубы: логотип крупно по центру свободного места, под ним название; у обмена — два клуба и стрелки
    shown = [t for t in teams_abbr if t in teams][:2]
    tf = font("Oswald.ttf", 46, "SemiBold")
    free_top, free_bottom = 250, y - 20
    box = min(300 if len(shown) < 2 else 240, free_bottom - free_top - 110)
    top = free_top + max(0, (free_bottom - free_top - box - 80) // 2)
    slots = [W // 2] if len(shown) < 2 else [W // 4 + 10, 3 * W // 4 - 10]
    for cx, abbrev in zip(slots, shown, strict=False):
        if not paste_logo(img, abbrev, cx - box // 2, top, box, crop=True):
            dr.rounded_rectangle((cx - box // 2, top, cx + box // 2, top + box), radius=8, outline=LINE, width=3)
        name = teams[abbrev]
        dr.text((cx - dr.textlength(name, font=tf) // 2, top + box + 14), name, font=tf, fill=INK)
    if len(shown) == 2:  # ⇄ рисуем сами: в Oswald нет стрелок
        cx, cy, half = W // 2, top + box // 2, 54
        for dy, tip, sign in ((-18, cx + half, 1), (18, cx - half, -1)):
            dr.line((cx - half, cy + dy, cx + half, cy + dy), fill=BRICK, width=8)
            dr.polygon([(tip + sign * 6, cy + dy), (tip - sign * 18, cy + dy - 16), (tip - sign * 18, cy + dy + 16)],
                       fill=BRICK)

    fy = h - 110
    dr.line((PAD, fy, W - PAD, fy), fill=INK, width=3)
    dr.text((PAD, fy + 24), "Источник: NHL.com", font=small, fill=SOFT)
    tag, tg = "Культура хоккея", font("Oswald.ttf", 34, "SemiBold")
    dr.text((W - PAD - dr.textlength(tag, font=tg), fy + 20), tag, font=tg, fill=INK)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    return path


def render_card(reports: list[GameReport], players: dict, teams: dict, msk_date: str, path: Path,
                highlights: list | None = None, league: bool = False) -> Path:
    """league=False — «Ночь наших» (под матчем — наши), True — «Ночь в НХЛ» (под матчем — звёзды матча)."""
    y, m, d = (int(x) for x in msk_date.split("-"))
    if league:  # в players только игроки с русским именем; display_names не должен видеть остальных
        known = [GameReport(r.game_id, r.home, r.away, r.home_score, r.away_score, r.last_period,
                            [s for s in r.skaters if str(s.pid) in players],
                            [g for g in r.goalies if str(g.pid) in players]) for r in reports]
        names = display_names(known, players)
        games = reports
    else:
        names = display_names(reports, players)
        games = []
    head_h, hero_h, foot_h = 250, 230 if highlights else 190, 110
    img = Image.new("RGB", (W, 10), PAPER)
    dr = ImageDraw.Draw(img)
    mono, small = font("PTSans-Bold.ttf", 26), font("PTSans-Regular.ttf", 30)
    # «Ночь в НХЛ» — табло матчей; «Ночь наших» — строка на каждого нашего (табло уже в посте лиги)
    if league:
        row_h = 106 if len(games) <= 10 else 96
        body_h = row_h * len(games)
    else:
        rows, idle = player_rows(reports, names)
        idle_lines = wrap(dr, "Без очков: " + ", ".join(idle), small, W - 2 * PAD, 6) if idle else []
        row_h = 100 if len(rows) <= 8 else 88
        body_h = row_h * len(rows) + (24 + 40 * len(idle_lines) if idle_lines else 0)
    h = max(1350, head_h + hero_h + body_h + foot_h + 40)

    img = Image.new("RGB", (W, h), PAPER)
    dr = ImageDraw.Draw(img)

    # шапка: как программка матча — двойная линейка, надзаголовок, крупное название
    dr.text((PAD, 58), "КУЛЬТУРА ХОККЕЯ  ·  НХЛ", font=mono, fill=FAINT)
    dr.text((PAD, 92), "НОЧЬ В НХЛ" if league else "НОЧЬ НАШИХ", font=font("Oswald.ttf", 104, "Bold"), fill=INK)
    date = f"{d} {MONTHS[m - 1]}".upper()
    df = font("Oswald.ttf", 44, "Medium")
    dr.text((W - PAD - dr.textlength(date, font=df), 150), date, font=df, fill=BRICK)
    for dy in (head_h - 14, head_h - 6):
        dr.line((PAD, dy, W - PAD, dy), fill=INK, width=3)

    # герой ночи — тот же выбор, что в тексте поста
    best = max((s for r in reports for s in r.skaters), key=lambda s: (s.points, s.goals), default=None)
    top = head_h + 24
    dr.rounded_rectangle((PAD, top, W - PAD, top + hero_h - 40), radius=6, fill=NAVY)
    highlights = [h for h in highlights or [] if h[0] in names]
    if highlights:
        pid, evs = highlights[0]
        line = next((s for r in reports for s in r.skaters if s.pid == pid), None) if pid in names else None
        big = str(max(evs[0].numbers)) if evs[0].numbers else (f"{line.goals}+{line.assists}" if line else "")
        phrase = evs[0].text.split(":")[0]
        sf = font("Oswald.ttf", 96, "Bold")
        bw = dr.textlength(big, font=sf)
        dr.text((PAD + 36, top + 18), "ГЛАВНОЕ", font=mono, fill="#C9D3DF")
        dr.text((PAD + 36, top + 44), names[pid].upper(), font=font("Oswald.ttf", 60, "SemiBold"), fill="#FFFFFF")
        dr.text((PAD + 36, top + 118), fit(dr, phrase[0].upper() + phrase[1:], small, int(W - 2 * PAD - bw - 100)),
                font=small, fill="#F2B8A6")
        dr.text((W - PAD - 36 - bw, top + 22), big, font=sf, fill="#F2B8A6")
    elif best and best.points >= 2 and best.pid in names:
        dr.text((PAD + 36, top + 22), "ГЛАВНОЕ", font=mono, fill="#C9D3DF")
        dr.text((PAD + 36, top + 52), names[best.pid].upper(), font=font("Oswald.ttf", 64, "SemiBold"), fill="#FFFFFF")
        score = f"{best.goals}+{best.assists}"
        sf = font("Oswald.ttf", 96, "Bold")
        dr.text((W - PAD - 36 - dr.textlength(score, font=sf), top + 12), score, font=sf, fill="#F2B8A6")
    else:
        word = plural(len(reports), ("матч", "матча", "матчей"))
        dr.text((PAD + 36, top + 50), f"{len(reports)} {word}" + ("" if league else " с нашими"),
                font=font("Oswald.ttf", 56, "SemiBold"), fill="#FFFFFF")

    y0 = head_h + hero_h
    if not league:
        nf, bf = font("Oswald.ttf", 40, "SemiBold"), font("Oswald.ttf", 48, "Bold")
        for i, (abbrev, name, big, sub, strong) in enumerate(rows):
            yy = y0 + i * row_h
            if i:
                dr.line((PAD, yy - 10, W - PAD, yy - 10), fill=LINE, width=2)
            used = paste_logo(img, abbrev, PAD, yy + 4, 60, crop=True)
            x = PAD + (used + 18 if used else 0)
            bw = dr.textlength(big, font=bf)
            dr.text((W - PAD - bw, yy - 2), big, font=bf, fill=BRICK if strong else INK)
            dr.text((x, yy - 4), fit(dr, name, nf, int(W - 2 * PAD - bw - (x - PAD) - 24)), font=nf, fill=INK)
            dr.text((x, yy + 46), fit(dr, sub, small, int(W - PAD - x)), font=small, fill=STEEL)
        yy = y0 + len(rows) * row_h + 14
        for ln in idle_lines:
            dr.text((PAD, yy), ln, font=small, fill=FAINT)
            yy += 40

    # матчи: счёт крупно, ниже — звёзды матча
    tf, sf, of = font("Oswald.ttf", 36, "Medium"), font("Oswald.ttf", 40, "Bold"), small
    for i, r in enumerate(games):
        yy = y0 + i * row_h
        if i:
            dr.line((PAD, yy - 8, W - PAD, yy - 8), fill=LINE, width=2)
        score = f"{r.home_score}:{r.away_score}{SUFFIX.get(r.last_period, '')}"
        sw = dr.textlength(score, font=sf)
        dr.text((W - PAD - sw, yy), score, font=sf, fill=INK)
        x = PAD
        for k, abbrev in enumerate((r.home, r.away)):
            if k:
                x += int(dr.textlength(" — ", font=tf))
                dr.text((x - int(dr.textlength(" — ", font=tf)), yy + 2), " — ", font=tf, fill=INK)
            used = paste_logo(img, abbrev, x, yy + 4, 54)
            x += used + (12 if used else 0)
            name = teams[abbrev]
            dr.text((x, yy + 2), name, font=tf, fill=INK)
            x += int(dr.textlength(name, font=tf))
        line = stars_line(r, names) if league else ours_line(r, names)
        dr.text((PAD, yy + 44), fit(dr, line, of, W - 2 * PAD), font=of,
                fill=FAINT if line == "наши без очков" else STEEL)

    # подвал
    fy = h - foot_h + 20
    dr.line((PAD, fy, W - PAD, fy), fill=INK, width=3)
    dr.text((PAD, fy + 24), "Все матчи ночи · данные NHL" if league else "Россияне и белорусы в НХЛ · данные NHL",
            font=small, fill=SOFT)
    tag = "Культура хоккея"
    tg = font("Oswald.ttf", 34, "SemiBold")
    dr.text((W - PAD - dr.textlength(tag, font=tg), fy + 20), tag, font=tg, fill=INK)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    return path
