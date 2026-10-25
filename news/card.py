"""Картинка к посту «Ночь наших»: карточка 1080×1350 в стиле «Культуры хоккея».

Своя графика плюс логотипы клубов (news/assets/logos, обновляет `python -m news.logos`) — только
как обозначение клуба. Фото игроков не берём: это чужие снимки. Шрифты Oswald и PT Sans (OFL) — news/assets/fonts.
Цифры берутся из тех же отчётов, что и текст поста, — отдельно гард их не проверяет.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from news import logos
from news.digest import MONTHS, SUFFIX, display_names
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


def paste_logo(img: Image.Image, abbrev: str, x: int, y: int, box: int) -> int:
    """Логотип в квадрат box×box с сохранением пропорций → сколько места занял по ширине. Нет файла — 0."""
    src = logos.path(abbrev)
    if not src.exists():
        return 0
    logo = Image.open(src).convert("RGBA")
    logo.thumbnail((box, box), Image.LANCZOS)
    img.paste(logo, (x + (box - logo.width) // 2, y + (box - logo.height) // 2), logo)
    return box


def ours_line(r: GameReport, names: dict[int, str]) -> str:
    parts = [f"{names[s.pid]} {s.goals}+{s.assists}" for s in sorted(r.skaters, key=lambda s: (-s.points, -s.goals))
             if s.points]
    parts += [f"{names[g.pid]} {g.saves}/{g.shots}" for g in r.goalies]
    return " · ".join(parts) or "наши без очков"


def render_card(reports: list[GameReport], players: dict, teams: dict, msk_date: str, path: Path,
                highlights: list | None = None) -> Path:
    y, m, d = (int(x) for x in msk_date.split("-"))
    names = display_names(reports, players)
    games = sorted(reports, key=lambda r: -sum(s.points for s in r.skaters) - len(r.goalies))
    row_h = 106 if len(games) <= 10 else 96
    head_h, hero_h, foot_h = 250, 230 if highlights else 190, 110
    h = max(1350, head_h + hero_h + row_h * len(games) + foot_h + 40)

    img = Image.new("RGB", (W, h), PAPER)
    dr = ImageDraw.Draw(img)
    mono, small = font("PTSans-Bold.ttf", 26), font("PTSans-Regular.ttf", 30)

    # шапка: как программка матча — двойная линейка, надзаголовок, крупное название
    dr.text((PAD, 58), "КУЛЬТУРА ХОККЕЯ  ·  НХЛ", font=mono, fill=FAINT)
    dr.text((PAD, 92), "НОЧЬ НАШИХ", font=font("Oswald.ttf", 104, "Bold"), fill=INK)
    date = f"{d} {MONTHS[m - 1]}".upper()
    df = font("Oswald.ttf", 44, "Medium")
    dr.text((W - PAD - dr.textlength(date, font=df), 150), date, font=df, fill=BRICK)
    for dy in (head_h - 14, head_h - 6):
        dr.line((PAD, dy, W - PAD, dy), fill=INK, width=3)

    # герой ночи — тот же выбор, что в тексте поста
    best = max((s for r in reports for s in r.skaters), key=lambda s: (s.points, s.goals), default=None)
    top = head_h + 24
    dr.rounded_rectangle((PAD, top, W - PAD, top + hero_h - 40), radius=6, fill=NAVY)
    if highlights:
        pid, evs = highlights[0]
        line = next((s for r in reports for s in r.skaters if s.pid == pid), None)
        big = str(max(evs[0].numbers)) if evs[0].numbers else (f"{line.goals}+{line.assists}" if line else "")
        phrase = evs[0].text.split(":")[0]
        sf = font("Oswald.ttf", 96, "Bold")
        bw = dr.textlength(big, font=sf)
        dr.text((PAD + 36, top + 18), "ГЛАВНОЕ", font=mono, fill="#C9D3DF")
        dr.text((PAD + 36, top + 44), names[pid].upper(), font=font("Oswald.ttf", 60, "SemiBold"), fill="#FFFFFF")
        dr.text((PAD + 36, top + 118), fit(dr, phrase[0].upper() + phrase[1:], small, int(W - 2 * PAD - bw - 100)),
                font=small, fill="#F2B8A6")
        dr.text((W - PAD - 36 - bw, top + 22), big, font=sf, fill="#F2B8A6")
    elif best and best.points >= 2:
        dr.text((PAD + 36, top + 22), "ГЛАВНОЕ", font=mono, fill="#C9D3DF")
        dr.text((PAD + 36, top + 52), names[best.pid].upper(), font=font("Oswald.ttf", 64, "SemiBold"), fill="#FFFFFF")
        score = f"{best.goals}+{best.assists}"
        sf = font("Oswald.ttf", 96, "Bold")
        dr.text((W - PAD - 36 - dr.textlength(score, font=sf), top + 12), score, font=sf, fill="#F2B8A6")
    else:
        dr.text((PAD + 36, top + 50), f"{len(reports)} матчей с нашими", font=font("Oswald.ttf", 56, "SemiBold"),
                fill="#FFFFFF")

    # матчи: счёт крупно, ниже — наши с очками
    y0 = head_h + hero_h
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
        line = ours_line(r, names)
        dr.text((PAD, yy + 44), fit(dr, line, of, W - 2 * PAD), font=of,
                fill=FAINT if line == "наши без очков" else STEEL)

    # подвал
    fy = h - foot_h + 20
    dr.line((PAD, fy, W - PAD, fy), fill=INK, width=3)
    dr.text((PAD, fy + 24), "Россияне и белорусы в НХЛ · данные NHL", font=small, fill=SOFT)
    tag = "Культура хоккея"
    tg = font("Oswald.ttf", 34, "SemiBold")
    dr.text((W - PAD - dr.textlength(tag, font=tg), fy + 20), tag, font=tg, fill=INK)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    return path
