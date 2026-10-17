#!/usr/bin/env python3
"""Генератор тактических SVG-схем словаря (запуск из корня репо):

    python tools/build_diagrams.py            # пересобрать все схемы в docs/diagrams/
    python tools/build_diagrams.py icing      # только одну

Стиль — как у первых ручных схем (forecheck/powerplay/slot): кремовый фон, голубой
лёд, PT Mono / Oswald, красные — атакующие, синие — обороняющиеся. Схема описывается
координатами игроков и стрелок поверх общей разметки катка, поэтому её можно поправить
без ручной вёрстки SVG. Ручные схемы forecheck/powerplay/slot генератор не трогает.

Подключение к термину: в terms.json `visual: "diagrams/<имя>.svg"`, `visual_type: "scheme"`,
`visual_caption` — подпись. Наличие файла проверяет validate_data.py.
"""
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs/diagrams"

INK, PAPER, ICE = "#2A2A24", "#F1EAD9", "#EAF2F8"
NAVY, BLUE, RED, GOLD = "#233048", "#4A6E92", "#A14A33", "#B08234"
COLORS = {"a": RED, "d": BLUE, "g": NAVY}
TOP, BOTTOM, MID = 38, 283, 160.5


class Svg:
    def __init__(self, title: str, subtitle: str = ""):
        self.parts: list[str] = []
        self.markers: set[str] = set()
        self.title, self.subtitle = title, subtitle

    def add(self, s: str) -> None:
        self.parts.append(s)

    # ── разметка катка ──
    def half_rink(self, side: str = "right") -> None:
        """Зона у ворот: right — атакуем вправо (ворота справа), left — своя зона слева."""
        self.add(f'<rect x="20" y="{TOP}" width="380" height="{BOTTOM - TOP}" rx="18" fill="{ICE}" '
                 f'stroke="{INK}" stroke-width="1.5"/>')
        if side == "right":
            blue, goal, dots, slot_x = 168, 360, 310, 290
            self.goal(goal, "right")
        else:
            blue, goal, dots, slot_x = 252, 60, 110, 60
            self.goal(goal, "left")
        self.add(f'<line x1="{blue}" y1="{TOP}" x2="{blue}" y2="{BOTTOM}" stroke="{BLUE}" stroke-width="2.5"/>')
        self.add(f'<text x="{blue + (-10 if side == "right" else 4)}" y="52" font-size="8" fill="{BLUE}" '
                 f'font-weight="700" text-anchor="{"end" if side == "right" else "start"}">СИНЯЯ</text>')
        self.add(f'<line x1="{goal}" y1="{TOP}" x2="{goal}" y2="{BOTTOM}" stroke="{RED}" stroke-width="1.5" '
                 f'stroke-dasharray="4,3"/>')
        for y in (115, 206):
            self.add(f'<circle cx="{dots}" cy="{y}" r="22" fill="none" stroke="{RED}" stroke-width="0.8" '
                     f'opacity="0.5"/>')
            self.add(f'<circle cx="{dots}" cy="{y}" r="3" fill="{RED}"/>')
        self.add(f'<rect x="{slot_x}" y="122" width="70" height="77" rx="4" fill="{GOLD}" opacity="0.10" '
                 f'stroke="{GOLD}" stroke-width="0.8" stroke-dasharray="3,3"/>')

    def full_rink(self) -> None:
        self.add(f'<rect x="20" y="{TOP}" width="380" height="{BOTTOM - TOP}" rx="18" fill="{ICE}" '
                 f'stroke="{INK}" stroke-width="1.5"/>')
        for x in (162, 258):
            self.add(f'<line x1="{x}" y1="{TOP}" x2="{x}" y2="{BOTTOM}" stroke="{BLUE}" stroke-width="2.5"/>')
        self.add(f'<line x1="210" y1="{TOP}" x2="210" y2="{BOTTOM}" stroke="{RED}" stroke-width="2.5"/>')
        self.add(f'<circle cx="210" cy="{MID}" r="22" fill="none" stroke="{BLUE}" stroke-width="0.8" opacity="0.6"/>')
        for x in (41, 379):
            self.add(f'<line x1="{x}" y1="{TOP + 8}" x2="{x}" y2="{BOTTOM - 8}" stroke="{RED}" stroke-width="1.2" '
                     f'stroke-dasharray="4,3"/>')
        self.goal(41, "left")
        self.goal(379, "right")
        for x in (80, 340):
            for y in (110, 211):
                self.add(f'<circle cx="{x}" cy="{y}" r="2.5" fill="{RED}"/>')

    def goal(self, x: float, side: str) -> None:
        gx = x if side == "right" else x - 14
        self.add(f'<rect x="{gx}" y="148" width="14" height="25" rx="2" fill="{NAVY}" fill-opacity="0.15" '
                 f'stroke="{NAVY}" stroke-width="1.8"/>')

    def shade(self, x: float, y: float, w: float, h: float, label: str = "") -> None:
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{GOLD}" opacity="0.13"/>')
        if label:
            self.add(f'<text x="{x + w / 2}" y="{y + 12}" text-anchor="middle" font-size="7.5" fill="{GOLD}" '
                     f'font-weight="700">{label}</text>')

    # ── фигуры ──
    def player(self, x: float, y: float, label: str, team: str = "a") -> None:
        self.add(f'<circle cx="{x}" cy="{y}" r="11" fill="{COLORS[team]}" opacity="0.92"/>')
        self.add(f'<text x="{x}" y="{y + 3.2}" text-anchor="middle" font-size="8.5" fill="{PAPER}" '
                 f'font-weight="700">{label}</text>')

    def puck(self, x: float, y: float) -> None:
        self.add(f'<circle cx="{x}" cy="{y}" r="4.5" fill="{INK}"/>')

    def arrow(self, x1, y1, x2, y2, color: str = RED, kind: str = "move", bend: float = 0) -> None:
        """kind: move — сплошная (движение с шайбой/без), pass — пунктир (передача/бросок),
        puck — точки (шайба без владельца). bend — изгиб дуги в пикселях."""
        self.markers.add(color)
        dash = {"move": "", "pass": ' stroke-dasharray="5,3"', "puck": ' stroke-dasharray="1.5,3"'}[kind]
        if bend:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            dx, dy = x2 - x1, y2 - y1
            length = (dx * dx + dy * dy) ** 0.5 or 1
            cx, cy = mx - dy / length * bend, my + dx / length * bend
            d = f"M{x1},{y1} Q{cx:.1f},{cy:.1f} {x2},{y2}"
        else:
            d = f"M{x1},{y1} L{x2},{y2}"
        self.add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6"{dash} '
                 f'marker-end="url(#arr-{color[1:]})"/>')

    def label(self, x: float, y: float, text: str, color: str = INK, size: float = 8, anchor: str = "middle",
              bold: bool = True) -> None:
        w = ' font-weight="700"' if bold else ""
        self.add(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" fill="{color}"{w}>{text}</text>')

    def legend(self, items: list[tuple[str, str]]) -> None:
        """items: (team|'puck', подпись) — ряд под площадкой."""
        x = 26
        for kind, text in items:
            if kind == "puck":
                self.add(f'<circle cx="{x + 6}" cy="290" r="4" fill="{INK}"/>')
            else:
                self.add(f'<circle cx="{x + 6}" cy="290" r="5.5" fill="{COLORS[kind]}" opacity="0.92"/>')
            self.add(f'<text x="{x + 15}" y="293" font-size="8" fill="{INK}">{text}</text>')
            x += 22 + len(text) * 4.9

    def render(self) -> str:
        defs = "".join(f'<marker id="arr-{c[1:]}" markerWidth="7" markerHeight="7" refX="5" refY="3.5" '
                       f'orient="auto"><path d="M0,0 L0,7 L7,3.5 z" fill="{c}"/></marker>'
                       for c in sorted(self.markers))
        sub = (f'\n  <text x="210" y="33" text-anchor="middle" font-size="7.5" fill="{INK}" opacity="0.75">'
               f'{self.subtitle}</text>') if self.subtitle else ""
        body = "\n  ".join(self.parts)
        title = (f'<text x="210" y="18" text-anchor="middle" font-family="\'Oswald\', sans-serif" font-size="13" '
                 f'font-weight="700" fill="{NAVY}" letter-spacing="2">{self.title}</text>')
        return f'''<svg viewBox="0 0 420 302" xmlns="http://www.w3.org/2000/svg" font-family="'PT Mono', monospace">
  <rect width="420" height="302" fill="{PAPER}"/>
  {title}{sub}
  <defs>{defs}</defs>
  {body}
</svg>
'''


# ─────────────────────────────── схемы ───────────────────────────────

def neutral_zone_trap() -> Svg:
    s = Svg("NEUTRAL ZONE TRAP · ЛОВУШКА 1-2-2", "один давит в чужой зоне, четверо перекрывают середину")
    s.full_rink()
    s.shade(162, TOP, 96, BOTTOM - TOP)
    s.label(210, 52, "НЕЙТРАЛЬНАЯ ЗОНА", GOLD, 7.5)
    s.player(52, 196, "D", "a")
    s.puck(64, 190)
    s.arrow(64, 196, 120, 236, RED, "move", bend=-8)
    s.player(135, 92, "F", "a")
    s.player(140, 228, "F", "a")
    s.player(110, 178, "F1", "d")
    s.arrow(110, 189, 112, 226, BLUE, "move")
    s.player(222, 92, "F2", "d")
    s.player(222, 228, "F3", "d")
    s.arrow(222, 217, 196, 236, BLUE, "move")
    s.player(282, 125, "D", "d")
    s.player(282, 196, "D", "d")
    s.label(110, 160, "гонит к борту", BLUE, 7)
    s.label(300, 262, "ловят пас по борту", BLUE, 7)
    s.legend([("d", "Ловушка (обороняются)"), ("a", "Выходят из зоны"), ("puck", "Шайба")])
    return s


def umbrella() -> Svg:
    s = Svg("UMBRELLA · ЗОНТИК", "большинство 5 на 4: трое дугой наверху, двое у ворот")
    s.half_rink("right")
    s.player(192, 160, "D", "a")
    s.player(232, 82, "F", "a")
    s.player(232, 238, "F", "a")
    s.player(340, 132, "F", "a")
    s.player(332, 205, "F", "a")
    s.puck(204, 152)
    s.arrow(200, 150, 222, 92, RED, "pass", bend=6)
    s.arrow(200, 170, 222, 228, RED, "pass", bend=-6)
    s.arrow(205, 160, 355, 158, RED, "pass")
    s.label(295, 152, "бросок от точки", RED, 7)
    for x, y in ((290, 110), (290, 210), (250, 135), (250, 185)):
        s.player(x, y, "PK", "d")
    s.player(368, 160, "G", "g")
    s.legend([("a", "В большинстве"), ("d", "В меньшинстве (ромб)"), ("g", "Вратарь"), ("puck", "Шайба")])
    return s


def odd_man_rush() -> Svg:
    s = Svg("ODD-MAN RUSH · ВЫХОД 2 В 1", "защитник закрывает передачу, вратарь берёт бросок")
    s.half_rink("right")
    s.player(200, 105, "F", "a")
    s.puck(212, 112)
    s.player(205, 222, "F", "a")
    s.arrow(212, 105, 300, 118, RED, "move")
    s.arrow(216, 222, 305, 205, RED, "move")
    s.arrow(300, 125, 305, 198, RED, "pass")
    s.label(318, 166, "пас?", RED, 7)
    s.player(268, 166, "D", "d")
    s.arrow(275, 158, 290, 140, BLUE, "move")
    s.label(250, 186, "держит середину", BLUE, 7)
    s.player(352, 152, "G", "g")
    s.label(330, 98, "бросок?", RED, 7)
    s.legend([("a", "Атакующие"), ("d", "Защитник"), ("g", "Вратарь"), ("puck", "Шайба")])
    return s


def breakout() -> Svg:
    s = Svg("BREAKOUT · ВЫХОД ИЗ ЗОНЫ", "защитник за воротами → крайний у борта → центр в разгоне")
    s.half_rink("left")
    s.player(36, 190, "D", "a")
    s.puck(48, 196)
    s.player(95, 240, "D", "a")
    s.player(150, 262, "W", "a")
    s.player(150, 58, "W", "a")
    s.player(120, 160, "C", "a")
    s.arrow(48, 200, 140, 258, RED, "pass", bend=10)
    s.arrow(160, 256, 210, 205, RED, "pass")
    s.arrow(128, 168, 212, 196, RED, "move", bend=-12)
    s.arrow(212, 196, 290, 196, RED, "move")
    s.arrow(160, 58, 285, 70, RED, "move")
    s.label(250, 214, "центр подхватывает", RED, 7)
    s.player(230, 120, "F", "d")
    s.player(205, 260, "F", "d")
    s.legend([("a", "Выходят из своей зоны"), ("d", "Форчек соперника"), ("puck", "Шайба")])
    return s


def offside() -> Svg:
    s = Svg("OFFSIDE · ОФСАЙД", "в зону атаки шайба должна войти раньше игрока")
    s.half_rink("right")
    s.add(f'<line x1="20" y1="{MID}" x2="400" y2="{MID}" stroke="{INK}" stroke-width="0.6" '
          f'stroke-dasharray="2,3" opacity="0.4"/>')
    s.player(190, 98, "F", "a")
    s.puck(150, 104)
    s.arrow(130, 104, 146, 104, RED, "move")
    s.label(285, 92, "ОФСАЙД", RED, 10)
    s.label(285, 106, "игрок пересёк синюю раньше шайбы", INK, 7, bold=False)
    s.puck(188, 222)
    s.player(150, 222, "F", "a")
    s.arrow(162, 222, 180, 222, RED, "move")
    s.label(260, 216, "ЧИСТО", BLUE, 10)
    s.label(260, 230, "шайба в зоне — игрок может входить", INK, 7, bold=False)
    s.label(168, 276, "решает положение коньков, а не клюшки", BLUE, 7)
    s.legend([("a", "Атакующий"), ("puck", "Шайба")])
    return s


def icing() -> Svg:
    s = Svg("ICING · ПРОБРОС", "шайба из своей половины пересекла чужую линию ворот без касания")
    s.full_rink()
    s.player(118, 205, "D", "a")
    s.puck(130, 200)
    s.arrow(132, 198, 393, 110, INK, "puck", bend=-10)
    s.label(214, 56, "КРАСНАЯ", RED, 7, anchor="start")
    s.label(379, 56, "ЛИНИЯ ВОРОТ", RED, 7, anchor="end")
    s.add(f'<circle cx="80" cy="211" r="8" fill="none" stroke="{RED}" stroke-width="1.4"/>')
    s.label(80, 236, "вбрасывание здесь", RED, 7)
    s.label(322, 222, "игра остановлена, смены нет", INK, 7, bold=False)
    s.label(322, 234, "у нарушителя (кроме меньшинства)", INK, 7, bold=False)
    s.legend([("a", "Пробросил"), ("puck", "Путь шайбы")])
    return s


def cycle() -> Svg:
    s = Svg("CYCLE · КАРУСЕЛЬ", "шайбу катают по борту, игроки меняются местами")
    s.half_rink("right")
    s.player(368, 255, "1", "a")
    s.puck(352, 266)
    s.arrow(368, 244, 330, 200, RED, "move", bend=-12)
    s.player(298, 252, "2", "a")
    s.arrow(309, 256, 340, 268, RED, "move")
    s.player(268, 205, "3", "a")
    s.arrow(274, 215, 290, 240, RED, "move")
    s.player(300, 165, "D", "d")
    s.player(366, 160, "G", "g")
    s.label(220, 252, "1 оставляет шайбу у борта", RED, 7)
    s.label(220, 264, "2 подхватывает, 3 встаёт на место 2", RED, 7)
    s.legend([("a", "Атакующие"), ("d", "Обороняющиеся"), ("g", "Вратарь"), ("puck", "Шайба")])
    return s


def zone_entry() -> Svg:
    s = Svg("ZONE ENTRY · ВХОД В ЗОНУ", "три способа пересечь синюю линию")
    s.half_rink("right")
    s.player(120, 82, "F", "a")
    s.arrow(132, 84, 236, 92, RED, "move")
    s.label(300, 70, "С КОНТРОЛЕМ", RED, 8)
    s.label(300, 80, "больше всего моментов", INK, 7, bold=False)
    s.player(125, 160, "F", "a")
    s.arrow(136, 160, 205, 150, RED, "pass")
    s.player(215, 148, "F", "a")
    s.label(270, 146, "ПАСОМ", RED, 8)
    s.player(120, 236, "F", "a")
    s.arrow(132, 240, 380, 270, INK, "puck", bend=-8)
    s.label(270, 212, "ЗАБРОСОМ", RED, 8)
    s.label(270, 224, "шайбу ещё надо выиграть", INK, 7, bold=False)
    s.legend([("a", "Атакующие"), ("puck", "Шайба без владельца")])
    return s


def screen() -> Svg:
    s = Svg("SCREEN · ЗАСЛОН", "нападающий перед воротами закрывает вратарю обзор")
    s.half_rink("right")
    s.add(f'<polygon points="352,160 192,140 192,180" fill="{INK}" opacity="0.07"/>')
    s.player(185, 160, "D", "a")
    s.puck(198, 166)
    s.arrow(200, 166, 355, 164, RED, "pass")
    s.player(330, 160, "F", "a")
    s.player(355, 150, "G", "g")
    s.label(240, 128, "линия обзора вратаря", INK, 7, bold=False)
    s.label(300, 146, "заслон", RED, 8)
    s.player(318, 205, "D", "d")
    s.arrow(318, 194, 324, 176, BLUE, "move")
    s.label(290, 226, "защитник выталкивает с пятака", BLUE, 7)
    s.legend([("a", "Атакующие"), ("d", "Защитник"), ("g", "Вратарь"), ("puck", "Шайба")])
    return s


DIAGRAMS = {
    "neutral-zone-trap": neutral_zone_trap,
    "umbrella": umbrella,
    "odd-man-rush": odd_man_rush,
    "breakout": breakout,
    "offside": offside,
    "icing": icing,
    "cycle": cycle,
    "zone-entry": zone_entry,
    "screen": screen,
}


def main() -> int:
    names = sys.argv[1:] or list(DIAGRAMS)
    for name in names:
        if name not in DIAGRAMS:
            print(f"нет схемы '{name}'; есть: {', '.join(DIAGRAMS)}", file=sys.stderr)
            return 1
        (OUT / f"{name}.svg").write_text(DIAGRAMS[name]().render(), encoding="utf-8")
        print(f"OK diagrams/{name}.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
