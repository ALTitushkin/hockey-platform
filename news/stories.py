"""⚡ Инфоповоды: обмены, контракты, крупные травмы по всей НХЛ + вызовы и отправки наших.

Источник — лента новостей NHL.com (forge-dapi, без ключа, тот же JSON, что у сайта).
Тег `transactions` в ленте неполный (подписание Раймера 25.10.2026 шло без него), поэтому читаем
общую ленту и сами решаем по заголовку, что это за новость.

Бюджет запросов: одна лента раз в NEWS_STORIES_MIN минут; полный текст — только у отобранной новости,
один раз. Каждую новость обрабатываем один раз (стейт — out/stories_state.json).

Пересказ пишет модель (цепочка llm.ask), имена и клубы — только из данных: игроки отмечены
в тексте NHL ID, русские имена — наш реестр, потом Wikidata. Гард сверяет каждое число с текстом
источника. Связь событий («подписали, потому что травмирован Шестёркин») — только если она есть в тексте.
"""

import html
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from news import guard, publish
from news.card import render_story_card
from news.digest import MONTHS, plural
from news.nhl import WEB

FEED = "https://forge-dapi.d3.nhle.com/v2/content/en-us/stories?$limit=40"
STATE = publish.OUT / "stories_state.json"
PROMPT = Path(__file__).parent / "prompts" / "story.md"
KEEP = timedelta(days=3)
# Пресс-релиз клуба выходит раньше, через 20–30 минут NHL.com пишет свой текст — с контекстом
# (у Раймера — травма Шестёркина). Релиз клуба ждёт столько, чтобы взять текст NHL.com.
HOLD_TEAM = timedelta(minutes=60)
REPORT_REPEAT = timedelta(days=3)
Fetch = Callable[[str], dict]

SKIP_TAGS = {"game-recap", "game-preview", "postgame", "pregame", "game-coverage", "feature", "player-feature",
             "column", "nhl-history", "blog", "nhl-insider", "fantasy", "betting", "video"}
# 27.10.2026 трекер подписаний драфта вышел постом «часть игроков подписала контракты» — пустышка
EVERGREEN = {"tracker", "rankings"}

# вид → (эмодзи заголовка, хэштег рубрики, только про наших)
KINDS = {
    "trade": ("🔁", "#Обмены", False),
    "signing": ("✍️", "#Контракты", False),
    "injury": ("🚑", "#Травмы", False),
    "injury_minor": ("🚑", "#Травмы", True),
    "claim": ("📋", "#Вейверы", True),
    "return": ("✅", "#Возвращения", True),
    "recall": ("⬆️", "#Вызовы", True),
    "assign": ("⬇️", "#Вызовы", True),
}
# виды, где герой может оказаться новым нашим (подписали, обменяли, вызвали) — проверяем родину
DISCOVER = {"signing", "trade", "claim", "recall", "assign", "return"}
LABELS = {"trade": "ОБМЕН", "signing": "КОНТРАКТ", "injury": "ТРАВМА", "injury_minor": "ТРАВМА",
          "claim": "ВЕЙВЕРЫ", "return": "ВОЗВРАЩЕНИЕ", "recall": "ВЫЗОВ", "assign": "В ФАРМ"}
# порядок важен: «activate … from injured reserve» — возвращение, а не травма
RULES = [
    ("return", r"\bactivat\w*|\boff (ir|injured)|\breturns? from\b|\b(could|will|to|nears?) return\b"),
    ("trade", r"\bacquir\w*|\btraded?\b.*\bto\b|\btrades\b|\bdeal\b.*\bfor\b"),
    ("signing", r"\bsigns?\b|\bsigned\b|\bre-sign\w*|agrees? to terms|\bextension\b|\bcontract\b"),
    ("injury", r"season-ending|\bsurgery\b|week-to-week|month-to-month|\bout (indefinitely|for the season|\d+)"
               r"|\bltir\b|long-term injured"),
    ("injury_minor", r"\binjur\w*|\bto ir\b|\bon ir\b|\bplaced on\b"),
    ("claim", r"\bclaim(s|ed)?\b.*\bwaivers\b|\bclaims? (forward|defenseman|goalie|goaltender|f|d|g)\b"
              r"|\bclaimed\b|\bwaivers\b"),  # не «staking his claim»
    ("recall", r"\brecall\w*|\bcall(s|ed)? up\b"),
    ("assign", r"\bassign\w*|\bloan\w*|\bre-assign\w*|\bsen[dt]s?\b.*\bto\b"),
]
# англ. название в тексте → код клуба (для гарда: клубы в пересказе — только те, что есть в источнике).
# «New York» не берём: у Нью-Йорка два клуба, различаем по прозвищу.
TEAM_EN = {
    "ANA": ("Anaheim", "Ducks"), "BOS": ("Boston", "Bruins"), "BUF": ("Buffalo", "Sabres"),
    "CGY": ("Calgary", "Flames"), "CAR": ("Carolina", "Hurricanes"), "CHI": ("Chicago", "Blackhawks"),
    "COL": ("Colorado", "Avalanche"), "CBJ": ("Columbus", "Blue Jackets"), "DAL": ("Dallas", "Stars"),
    "DET": ("Detroit", "Red Wings"), "EDM": ("Edmonton", "Oilers"), "FLA": ("Florida", "Panthers"),
    "LAK": ("Los Angeles", "Kings"), "MIN": ("Minnesota", "Wild"), "MTL": ("Montreal", "Canadiens"),
    "NSH": ("Nashville", "Predators"), "NJD": ("New Jersey", "Devils"), "NYI": ("", "Islanders"),
    "NYR": ("", "Rangers"), "OTT": ("Ottawa", "Senators"), "PHI": ("Philadelphia", "Flyers"),
    "PIT": ("Pittsburgh", "Penguins"), "SJS": ("San Jose", "Sharks"), "SEA": ("Seattle", "Kraken"),
    "STL": ("St. Louis", "Blues"), "TBL": ("Tampa Bay", "Lightning"), "TOR": ("Toronto", "Maple Leafs"),
    "UTA": ("Utah", "Mammoth"), "VAN": ("Vancouver", "Canucks"), "VGK": ("Vegas", "Golden Knights"),
    "WSH": ("Washington", "Capitals"), "WPG": ("Winnipeg", "Jets"),
}
# NHL.com пишет числа до десяти словами («eight points», «one-year») — модель пишет их цифрами
NUMBER_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                           "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
                                           .split())}
# слова с большой буквы, которые законно стоят в пересказе (кроме имён и клубов из данных)
VOCAB = {"НХЛ", "АХЛ", "КХЛ", "ECHL", "Кубок", "Стэнли", "Россия", "России", "Канада", "Канады", "США",
         "Олимпиада", "Олимпиады", "Драфт", "Хартфорд", "Хершей"} | set(MONTHS)


@dataclass
class Story:
    eid: str
    slug: str
    headline: str
    summary: str
    date: datetime
    kind: str
    pids: set[int]
    teams: set[str]
    nhl: bool  # текст редакции NHL.com, а не пресс-релиз клуба
    url: str = ""
    text: str = ""
    mentioned: set[int] = field(default_factory=set)
    en: dict[int, str] = field(default_factory=dict)  # упомянутые: имя латиницей из ссылки в тексте

    @property
    def link(self) -> str:
        return f"https://www.nhl.com/news/{self.slug}"


def kind_of(headline: str, summary: str = "") -> str | None:
    """Вид новости по заголовку; summary — запасной вариант, когда заголовок без глагола («Hellebuyck to Devils»)."""
    for text in (headline, summary):
        low = text.lower()
        for kind, rule in RULES:
            if re.search(rule, low):
                return kind
    return None


def parse_item(it: dict) -> Story | None:
    slugs = {t.get("slug", "") for t in it.get("tags", [])}
    # колонки клубных «инсайдеров» (lak-insider…) — мнения и разборы, а не событие
    if slugs & SKIP_TAGS or any(s.endswith(("-insider", "day-to-day")) for s in slugs):
        return None
    # сводные страницы, которые редакция дописывает месяцами («…signings tracker»): дата свежая, новости нет
    if set(it.get("slug", "").split("-")) & EVERGREEN:
        return None
    kind = kind_of(it.get("headline") or "", (it.get("summary") or "")[:200])
    if not kind:
        return None
    pids = {int(s.split("-")[1]) for s in slugs if re.fullmatch(r"playerid-\d+", s)}
    teams = {t["extraData"]["abbreviation"] for t in it.get("tags", [])
             if t.get("slug", "").startswith("teamid-") and t.get("extraData", {}).get("abbreviation")}
    when = datetime.fromisoformat(it["contentDate"].replace("Z", "+00:00"))
    return Story(it["_entityId"], it["slug"], (it.get("headline") or "").strip(), it.get("summary") or "", when,
                 kind, pids, teams, "nhl-created" in slugs, it.get("selfUrl", ""))


def body_text(full: dict) -> tuple[str, dict[int, str]]:
    """Полный текст новости без разметки + упомянутые игроки (теги forge-entity с NHL ID):
    {pid: имя латиницей из slug} — «jared-mccann-8477955» → «Jared Mccann»."""
    md = "\n\n".join(p.get("content", "") for p in full.get("parts", []) if p.get("type") == "markdown")
    mentioned = {int(pid): name.replace("-", " ").title()
                 for name, pid in re.findall(r'slug="([^"]*?)-(\d{7})" code="player"', md)}
    plain = re.sub(r"<[^>]+>", "", md)
    plain = re.sub(r"[ \t]+", " ", html.unescape(plain)).strip()
    return plain, mentioned


def teams_in(text: str) -> set[str]:
    return {abbr for abbr, (city, nick) in TEAM_EN.items()
            if re.search(rf"\b{re.escape(nick)}\b", text) or (city and re.search(rf"\b{re.escape(city)}\b", text))}


def same_event(a: Story, b: Story) -> bool:
    """Релиз клуба и текст NHL.com об одном и том же: тот же вид и общий игрок, или общий клуб и слово заголовка."""
    if a.kind != b.kind:
        return False
    if a.pids & b.pids:
        return True
    words = lambda s: {w for w in re.findall(r"\b[A-Z][a-z]{3,}\b", s.headline)} - {  # noqa: E731
        n for _, nick in TEAM_EN.values() for n in nick.split()} - {"With", "From", "Terms", "Agree", "Signs"}
    return bool(a.teams & b.teams and words(a) & words(b))


# Травма со списком травмированных и возвращение в строй — по всей лиге, но только заметных игроков:
# 26–27.10.2026 с правилом «только наши» за двое суток не вышло ни одного инфоповода (мимо прошли
# Зуккарелло на IR и возвращение Холла). Сводку травм редакции NHL.com берём всегда: там уже отобрано.
WIDER = {"injury_minor", "return"}
CAREER_POINTS, SEASON_POINTS, GOALIE_GAMES = 300, 40, 30


def wider(s: Story, notable: Callable[[int], bool] | None) -> bool:
    if s.kind not in WIDER:
        return False
    if s.nhl and "status report" in s.headline.lower():
        return True
    return bool(notable) and any(notable(p) for p in s.pids)


def is_notable(landing: dict) -> bool:
    """Заметный игрок по карточке НХЛ: карьера, прошлый/текущий сезон; у вратаря — матчи сезона."""
    reg = landing.get("featuredStats", {}).get("regularSeason", {})
    season, career = reg.get("subSeason") or {}, reg.get("career") or {}
    if landing.get("position") == "G":
        return season.get("gamesPlayed", 0) >= GOALIE_GAMES or career.get("gamesPlayed", 0) >= 200
    return career.get("points", 0) >= CAREER_POINTS or season.get("points", 0) >= SEASON_POINTS


def select(items: list[Story], state: dict, now: datetime, ours: set[int], ours_en: dict[str, int],
           notable: Callable[[int], bool] | None = None) -> list[Story]:
    """Новые новости, которые пора обработать: не виденные, важные (или про наших), без дублей события.
    notable(NHL ID) — заметен ли игрок (для травм и возвращений не наших)."""
    out = []
    since = datetime.fromisoformat(state["since"])
    for s in sorted(items, key=lambda s: s.date):
        if s.eid in state["seen"] or s.date < since:
            continue
        for name, pid in ours_en.items():  # клуб не отметил игрока тегом — ищем нашего по имени
            if name in s.headline or name in s.summary:
                s.pids.add(pid)
        if KINDS[s.kind][2] and not s.pids & ours and not wider(s, notable):
            state["seen"][s.eid] = now.isoformat()  # мелкое движение не нашего — пропускаем навсегда
            continue
        if not s.nhl and now - s.date < HOLD_TEAM and not any(same_event(s, o) for o in items if o.nhl):
            continue  # релиз клуба ждёт текст NHL.com — решим на следующем проходе
        twins = [o for o in items if o is not s and same_event(s, o)]
        if any(o.eid in state["seen"] for o in twins) or any(same_event(s, o) for o in out):
            state["seen"][s.eid] = now.isoformat()  # то же событие уже вышло — дубль
            continue
        if not s.nhl and any(o.nhl for o in twins):
            continue  # возьмём текст NHL.com, когда до него дойдёт очередь
        if report_repeat(s, state, now):
            state["seen"][s.eid] = now.isoformat()
            continue
        out.append(s)
    return out


def report_keys(s: Story) -> set[str]:
    """Герои заголовка сводки травм: «NHL Status Report: Hall could return for Hurricanes» → {"Hall"}."""
    if not (s.nhl and "status report" in s.headline.lower()):
        return set()
    tail = s.headline.split(":", 1)[-1]
    nicks = {n for _, nick in TEAM_EN.values() for n in nick.split()}
    return set(re.findall(r"\b[A-Z][a-z]{2,}\b", tail)) - nicks - {"NHL", "Status", "Report", "The"}


def report_repeat(s: Story, state: dict, now: datetime) -> bool:
    """Сводка травм выходит каждый день и может неделю вести одного героя (Холл 26 и 27.10.2026) —
    тот же герой в заголовке за 3 дня = повтор. Новых героев запоминаем."""
    keys = report_keys(s)
    heads = state.setdefault("report_heads", {})
    for k, t in list(heads.items()):
        if now - datetime.fromisoformat(t) > REPORT_REPEAT:
            del heads[k]
    if keys & heads.keys():
        return True
    heads.update({k: now.isoformat() for k in keys})
    return False


def load_state(now: datetime) -> dict:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # первый запуск: старьё из ленты не публикуем, начинаем с последних 6 часов
        state = {"since": (now - timedelta(hours=6)).isoformat(), "seen": {}}
    state["seen"] = {k: v for k, v in state["seen"].items() if now - datetime.fromisoformat(v) < KEEP}
    return state


def save_state(state: dict) -> None:
    publish.OUT.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def prompt_for(s: Story, names: dict, teams_ru: dict, ours: set[int]) -> str:
    people = "\n".join(f"- {names[str(p)]['ru']}" for p in sorted(s.mentioned | s.pids) if str(p) in names)
    clubs = "\n".join(f"- {teams_ru[t]}" for t in sorted(s.teams) if t in teams_ru)
    our = ", ".join(names[str(p)]["ru"] for p in sorted((s.mentioned | s.pids) & ours) if str(p) in names)
    return (PROMPT.read_text(encoding="utf-8").replace("{headline}", s.headline).replace("{text}", s.text[:5000])
            .replace("{people}", people or "- (нет)").replace("{clubs}", clubs or "- (нет)")
            .replace("{ours}", our or "нет"))


def clean(text: str | None) -> str | None:
    """Ответ модели → «заголовок\\n\\nтекст»: без служебных подписей, markdown и кавычек вокруг."""
    lines = [ln.strip().strip("*#").strip() for ln in (text or "").strip().splitlines()]
    lines = [ln for ln in lines if ln and not re.match(r"^(заголовок|текст)\s*:?$", ln, re.IGNORECASE)]
    if len(lines) < 2:
        return None
    head = re.sub(r"^заголовок\s*:\s*", "", lines[0], flags=re.IGNORECASE).strip("«»\"' ")
    return head + "\n\n" + " ".join(re.sub(r"^текст\s*:\s*", "", ln, flags=re.IGNORECASE) for ln in lines[1:])


def check(text: str, s: Story, names: dict, registry: dict, teams_ru: dict,
          ours: set[int]) -> tuple[list[str], list[str]]:
    """→ (замечания гарда — пост не уходит, «проверь глазами» — уходит только кнопкой владельца)."""
    source = f"{s.headline}\n{s.summary}\n{s.text}"
    in_story = s.teams | teams_in(source)
    spelled = {str(n) for w, n in NUMBER_WORDS.items() if re.search(rf"\b{w}\b", source, re.IGNORECASE)}
    facts = {"numbers": set(re.findall(r"\d+", source)) | spelled,
             "pids": {p for p in (s.mentioned | s.pids) & ours if str(p) in registry},
             "teams": {teams_ru[t] for t in in_story if t in teams_ru}}
    issues = guard.check(text, facts, registry, teams_ru)
    if re.search(r"[A-Za-z]{2,}", re.sub(r"\bECHL\b", "", text)):
        issues.append("латиница в тексте")
    for pid in s.pids:  # герой новости назван, и его имя — из данных
        rec = names.get(str(pid))
        if not rec:
            issues.append(f"нет русского имени для игрока {pid}")
        elif not guard.mentions(text, rec["surname"]):
            issues.append(f"не назван герой новости: {rec['ru']}")
    known = set(VOCAB)
    for rec in names.values():
        known |= set(rec["ru"].split())
    known |= {w for t in teams_ru.values() for w in t.split()}
    words = re.findall(r"(?<![.!?\n]\s)(?<!^)\b[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?", text)
    unknown = sorted({w for w in words if not any(guard.stem(k) and w.startswith(guard.stem(k)) for k in known)})
    notes = [f"незнакомые слова с большой буквы: {', '.join(unknown)}"] if unknown else []
    return issues, notes


def ru_num(x: float, digits: int) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def goalie_stats(s: Story, names: dict, ours: set[int], fetch: Fetch) -> list[dict]:
    """КН и %ОБ вратарей новости — из API НХЛ, не из пересказа: герой новости и наши из текста.
    Сезон — текущий, а если в нём вратарь ещё не играл, последний сыгранный (так отдаёт API)."""
    out = []
    for pid in sorted(s.pids | (s.mentioned & ours)):
        rec = names.get(str(pid))
        if not rec:
            continue
        try:
            d = fetch(f"{WEB}/player/{pid}/landing")
        except RuntimeError:
            continue
        featured = d.get("featuredStats", {})
        st = featured.get("regularSeason", {}).get("subSeason") or {}
        if d.get("position") != "G" or not st.get("gamesPlayed"):
            continue
        season = str(featured.get("season", ""))
        gp = st["gamesPlayed"]
        out.append({"pid": pid, "surname": rec["surname"], "season": f"{season[:4]}/{season[6:]}",
                    "games": f"{gp} {plural(gp, ('матч', 'матча', 'матчей'))}",
                    "gaa": ru_num(st["goalsAgainstAvg"], 2), "sv": ru_num(st["savePctg"] * 100, 1)})
    return out


def goalie_line(g: dict) -> str:
    return f"🥅 <b>{html.escape(g['surname'])}</b> · {g['season']}: {g['games']}, КН {g['gaa']}, %ОБ {g['sv']}"


def hero_of(s: Story, names: dict, ours: set[int]) -> int | None:
    """Герой карточки: игрок из тегов новости с русским именем, наш — в первую очередь.
    Тегов нет (сводка травм) — упомянутый в тексте, чья фамилия стоит в заголовке."""
    known = [p for p in sorted(s.pids) if str(p) in names]
    if not known:
        low = s.headline.lower()
        known = [p for p, en in sorted(s.en.items()) if str(p) in names and en.split()[-1].lower() in low]
    return next((p for p in known if p in ours), known[0] if known else None)


def card(s: Story, body: str, names: dict, ours: set[int], goalies: list[dict], teams_ru: dict,
         msk: str, path: Path) -> Path:
    hero = hero_of(s, names, ours)
    g = next((g for g in goalies if g["pid"] == hero), None)
    stats = f"{g['season']} · {g['games']} · КН {g['gaa']} · %ОБ {g['sv']}" if g else None
    # у обмена — оба клуба; у остального — клуб из тегов (первый по алфавиту: тегов обычно один)
    tagged = sorted(s.teams or teams_in(s.headline))  # нет тегов клуба — клуб из заголовка («…for Kraken»)
    teams = tagged[:2] if s.kind == "trade" else tagged[:1]
    return render_story_card(LABELS[s.kind], teams, names[str(hero)]["ru"] if hero else None, hero in ours,
                             body.partition("\n\n")[0], stats, teams_ru, msk, path)


def render(s: Story, body: str, msk: str, stats: list[str] = ()) -> str:
    emoji, tag, _ = KINDS[s.kind]
    head, _, rest = body.partition("\n\n")
    _, m, d = (int(x) for x in msk.split("-"))
    block = "\n".join(stats) + "\n\n" if stats else ""
    return (f"{emoji} <b>{html.escape(head)}</b>\n\n{html.escape(rest)}\n\n{block}"
            f"🔗 <a href=\"{s.link}\">NHL.com</a>\n⚡ {tag} · {d} {MONTHS[m - 1]}")


def ours_by_name(state: dict, today: str, nationals: Callable[[], list[dict]]) -> dict[str, int]:
    """Английские имена наших → NHL ID: клубы часто не ставят тег игрока на «вызван из АХЛ».
    Обновляем раз в день (4 запроса); источник не ответил — работаем со вчерашним списком."""
    cache = state.get("ours_en", {})
    if cache.get("date") != today:
        try:
            cache = {"date": today, "names": {p["name"]: p["pid"] for p in nationals()}}
        except RuntimeError:
            pass
        state["ours_en"] = cache
    return cache.get("names", {})


def process(now: datetime, fetch: Fetch, registry: dict, teams_ru: dict, wiki: Callable[[set, dict], dict],
            write: Callable[[str], str | None], nationals: Callable[[], list[dict]],
            deliver: Callable[[str, str], str], notify: Callable[[str], None],
            discover: Callable[[set[int]], tuple[list[str], dict]] | None = None) -> list[str]:
    """Один проход: → строки для лога. write(промпт, гард) → (текст, кто написал, журнал),
    deliver(дата, рубрика) → итог отправки владельцу/в канал, notify(текст) — владельцу о сбое,
    discover(NHL ID) → новые наши среди героев подписаний/обменов/вызовов (registry.from_story)."""
    state = load_state(now)
    msk = now.date().isoformat()
    items = [s for it in fetch(FEED).get("items", []) if (s := parse_item(it))]
    log = []
    if discover:  # каждого незнакомого героя проверяем один раз: 1 запрос карточки на игрока
        checked = set(state.get("checked", []))
        fresh = {p for s in items if s.eid not in state["seen"] and s.kind in DISCOVER for p in s.pids}
        fresh -= {int(k) for k in registry} | checked
        if fresh:
            lines, records = discover(fresh)
            state["checked"] = sorted(checked | fresh)[-3000:]
            registry.update({k: v for k, v in records.items() if v.get("ru")})
            for line in lines:
                notify(f"Реестр наших: {line}")
            log += [f"реестр: {line}" for line in lines]
    ours = {int(p) for p, r in registry.items() if r.get("ru")}
    cache = state.setdefault("notable", {})

    def notable(pid: int) -> bool:  # 1 запрос карточки на игрока, ответ помним
        if str(pid) not in cache:
            try:
                cache[str(pid)] = is_notable(fetch(f"{WEB}/player/{pid}/landing"))
            except RuntimeError:
                return False  # не ответил — решим на следующем проходе
        return cache[str(pid)]

    for s in select(items, state, now, ours, ours_by_name(state, msk, nationals), notable):
        state["seen"][s.eid] = now.isoformat()  # до работы: упадёт посередине — повторять не будем
        try:
            s.text, s.en = body_text(fetch(s.url))
            s.mentioned = set(s.en)
        except RuntimeError as e:
            log.append(f"инфоповод {s.slug}: текст не получен ({e})")
            continue
        names = wiki(s.mentioned | s.pids, registry)
        notes: list[str] = []

        def accept(text: str, s=s, names=names, notes=notes) -> list[str]:
            issues, found = check(text, s, names, registry, teams_ru, ours)
            notes[:] = found
            return issues

        body, source, attempts = write(lambda _p, s=s, names=names: prompt_for(s, names, teams_ru, ours), accept)
        kind = f"story-{s.eid[:8]}"
        if not body:  # новость есть, а поста нет — владелец должен знать
            why = "; ".join(attempts)[:600] or "модель не ответила"
            notify(f"⚠️ Инфоповод без поста: {s.headline}\n{s.link}\n{why}")
            log.append(f"инфоповод {s.slug}: пересказ не прошёл гард — {why[:300]}")
            continue
        variant = f"пересказ {source}" + (f" · 👀 проверь: {'; '.join(notes)}" if notes else "")
        goalies = goalie_stats(s, names, ours, fetch)
        try:
            pic = str(card(s, body, names, ours, goalies, teams_ru, msk, publish.OUT / f"{msk}_{kind}.png"))
        except Exception as e:  # картинка — украшение: без неё пост всё равно выходит
            pic = None
            log.append(f"инфоповод {s.slug}: карточка не собралась ({type(e).__name__}: {e})")
        publish.save_draft(msk, render(s, body, msk, [goalie_line(g) for g in goalies]), [], variant, pic,
                           kind=kind, data={"slug": s.slug, "auto": not notes})
        log.append(f"инфоповод {s.slug} ({s.kind}): {deliver(msk, kind)}")
    save_state(state)
    return log
