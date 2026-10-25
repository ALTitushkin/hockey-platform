"""Логотипы клубов НХЛ для карточки: скачать один раз и хранить в репо (news/assets/logos/*.png).

    python -m news.logos            # докачать недостающие
    python -m news.logos --force    # перекачать все (клуб сменил логотип)

Источник — SVG из CDN НХЛ (assets.nhle.com), рендер в PNG через resvg-py: он нужен только
здесь, на машине, где обновляют логотипы. Рантайм новостника читает готовые PNG — лишней
зависимости на сервере нет. Логотипы — товарные знаки НХЛ и клубов; используем только для
обозначения клуба в новостной карточке, без искажений и не как свой знак.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
DIR = ROOT / "assets" / "logos"
URL = "https://assets.nhle.com/logos/nhl/svg/{}_light.svg"
SIZE = 640  # карточка инфоповода ставит логотип ~300 px после обрезки полей — 160 давало мыло


def path(abbrev: str) -> Path:
    return DIR / f"{abbrev}.png"


def sync(force: bool = False) -> list[str]:
    import resvg_py  # только для обновления логотипов

    DIR.mkdir(parents=True, exist_ok=True)
    teams = json.loads((ROOT / "data" / "teams.json").read_text(encoding="utf-8"))
    done = []
    for abbrev in teams:
        if path(abbrev).exists() and not force:
            continue
        req = urllib.request.Request(URL.format(abbrev), headers={"User-Agent": "KulturaHokkeyaNews/0.1"})
        svg = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
        path(abbrev).write_bytes(bytes(resvg_py.svg_to_bytes(svg_string=svg, width=SIZE)))
        done.append(abbrev)
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="news.logos")
    ap.add_argument("--force", action="store_true")
    got = sync(ap.parse_args().force)
    print(f"скачано: {', '.join(got) if got else 'ничего — все логотипы на месте'}")
    sys.exit(0)
