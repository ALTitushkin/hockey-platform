"""Аватар канала «Культура хоккея» — штамп программки (выбор владельца 25.10.2026).

Монограмма «КХ» тушью на бумаге, двойное кирпичное кольцо, подпись «Культура хоккея».
Палитра и шрифт — как у карточек новостника (news/card.py). 1024×1024, Telegram обрезает по кругу.

    python tools/build_avatar.py   # → news/assets/brand/channel_avatar.png
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "news" / "assets" / "fonts"
OUT = ROOT / "news" / "assets" / "brand" / "channel_avatar.png"
S = 1024
PAPER, INK, BRICK = "#F1EAD8", "#20242C", "#9E3B2C"


def oswald(size, weight="Bold"):
    f = ImageFont.truetype(str(FONTS / "Oswald.ttf"), size)
    f.set_variation_by_name(weight)
    return f


def centered(dr, text, f, cx, cy, fill):
    left, top, right, bottom = dr.textbbox((0, 0), text, font=f)
    dr.text((cx - (left + right) / 2, cy - (top + bottom) / 2), text, font=f, fill=fill)


def stamp():
    """Монограмма крупно — она и читается в списке чатов; подпись — для профиля, где аватар большой.
    Подпись держим внутри кольца с запасом: на 812-й строке она касалась внутреннего кольца."""
    img = Image.new("RGB", (S, S), PAPER)
    dr = ImageDraw.Draw(img)
    dr.ellipse((40, 40, S - 40, S - 40), outline=BRICK, width=26)
    dr.ellipse((98, 98, S - 98, S - 98), outline=BRICK, width=8)
    centered(dr, "КХ", oswald(440), S / 2, S / 2 - 40, INK)
    dr.line((320, 710, S - 320, 710), fill=BRICK, width=12)
    centered(dr, "КУЛЬТУРА ХОККЕЯ", oswald(52, "SemiBold"), S / 2, 768, INK)
    return img


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    stamp().save(OUT, optimize=True)
    print(OUT)
