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

from news import (
    event_registry,
    fact_packet,
    guard,
    publish,
    source_watch,
    story_provenance,
    story_validation,
    temporal,
    trades,
)
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
    ("signing", r"\bsigns?\b|\bsigned\b|\bre-sign\w*|agrees? to terms|\bextension\b|\bcontract\b"
                r"|\breleas\w*\b.*\b(?:pto|tryout)\b"),
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
NUMBER_WORDS.update({w: i for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth "
    "fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split(), 1)})
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
    # Сезонный список сделок обновляется год: это не отдельный инфоповод.
    if re.fullmatch(r"\d{4}-\d{2}-nhl-trades", it.get("slug", "")):
        return None
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
    """Before full evidence is loaded, only identical document IDs prove equality."""
    return a.eid == b.eid


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
        if now.timestamp() < state.get("retry_after", {}).get(s.eid, 0):
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
        if any(o.eid in state["seen"] for o in twins):
            state["seen"][s.eid] = now.isoformat()  # то же событие уже вышло — дубль
            continue
        if any(same_event(s, o) for o in out):
            continue  # первый текст ещё не доставлен — не закрываем событие заранее
        if not s.nhl and any(o.nhl for o in twins):
            continue  # возьмём текст NHL.com, когда до него дойдёт очередь
        if report_repeat(s, state, now, remember=False):
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


def report_repeat(s: Story, state: dict, now: datetime, remember: bool = True) -> bool:
    """Legacy state is retained, but a player's surname never suppresses an update."""
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
    clubs = "\n".join(f"- {teams_ru[t]}" for t in sorted(s.teams | teams_in(s.text + s.headline)) if t in teams_ru)
    our = ", ".join(names[str(p)]["ru"] for p in sorted((s.mentioned | s.pids) & ours) if str(p) in names)
    editorial = (PROMPT.parent / "editorial.md").read_text(encoding="utf-8")
    return editorial + "\n\n" + (PROMPT.read_text(encoding="utf-8").replace("{headline}", s.headline)
            .replace("{text}", source_excerpt(s, ours))
            .replace("{people}", people or "- (нет)").replace("{clubs}", clubs or "- (нет)")
            .replace("{ours}", our or "нет")) + (
                f"\n\nКонтроль перед ответом: в тексте обязательно назови {our} и сообщи только факт"
                " о каждом из них из источника с сохранением временного контекста. Старую травму"
                " обозначай как продолжающееся отсутствие или укажи дату травмы. Добавь предложение, даже если"
                " основной заголовок про другого игрока. Клубы называй строго по списку выше."
                if our else "") + (trades.prompt(trade_facts(s), names, teams_ru) if s.kind == "trade" else "")


def trade_facts(s: Story) -> trades.Trade:
    return trades.extract(s.headline, s.text, s.en, TEAM_EN)


def health_facts(s: Story) -> dict[str, str]:
    """Only the event headline can bind an injury qualifier to this story's hero.

    Do not borrow diagnoses from other paragraphs/players in status reports.
    """
    if "status report" in s.headline.lower() or s.kind not in {"injury", "injury_minor"}:
        return {}
    for english, region in (("upper", "верхняя"), ("lower", "нижняя")):
        if re.search(rf"\b{english}[- ]body\b", s.headline, re.I):
            return {"region": region}
    return {}


def source_excerpt(s: Story, ours: set[int]) -> str:
    """Начало статьи и полные абзацы про наших/героев: не отрезаем факты, требуемые гардом."""
    paragraphs = s.text.split("\n\n")
    needed = [en for pid, en in s.en.items() if pid in ours or pid in s.pids]
    out, size = [], 0
    for paragraph in paragraphs:
        if size + len(paragraph) <= 5000 or any(en in paragraph for en in needed):
            out.append(paragraph)
            size += len(paragraph)
    return "\n\n".join(out)


def clean(text: str | None) -> str | None:
    """Ответ модели → «заголовок\\n\\nтекст»: без служебных подписей, markdown и кавычек вокруг."""
    if (text or "").strip() == "SKIP: нет нового события":
        return None  # обычный редакторский отказ: уведомление владельцу и повтор, не seen
    lines = [ln.strip().strip("*#").strip() for ln in (text or "").strip().splitlines()]
    lines = [ln for ln in lines if ln and not re.match(r"^(заголовок|текст)\s*:?$", ln, re.IGNORECASE)]
    if len(lines) < 2:
        return None
    head = re.sub(r"^заголовок\s*:\s*", "", lines[0], flags=re.IGNORECASE).strip()
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
    issues.extend(temporal.check(text, s, names))
    quote_depth, bad_quotes = 0, False
    for quote in re.findall("[«»]", text):
        quote_depth += 1 if quote == "«" else -1
        bad_quotes |= quote_depth < 0
    if quote_depth or bad_quotes:
        issues.append("несбалансированные кавычки")
    health = health_facts(s)
    if health and not (health["region"][:4] in text.lower() and "част" in text.lower() and "тел" in text.lower()):
        issues.append("потеряно подтверждённое уточнение травмы из заголовка источника")
    if s.kind == "trade" and re.search(r"обменял[аи]?\b[^\n.!?]*\b(?:у|на)\s", text, re.IGNORECASE):
        issues.append("неясное направление обмена: используйте получил/отдал")
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
    if "status report" in s.headline.lower():
        hero = hero_of(s, names, ours, headline=text.partition("\n\n")[0])
        clubs = focus_teams(s, hero)
        if not clubs:
            notes.append("не установлена однозначная связь героя и клуба в источнике")
        else:
            head_clubs = {t for t, ru in teams_ru.items() if guard.mentions(text.partition("\n\n")[0], ru)}
            if head_clubs and head_clubs != set(clubs):
                issues.append("клуб героя заголовка противоречит разделу источника")
    if s.kind == "trade":
        trade_issues, trade_notes = trades.check(text, trade_facts(s), names, teams_ru)
        issues.extend(trade_issues)
        notes.extend(trade_notes)
    return issues, notes + editorial_notes(text)


def editorial_notes(text: str) -> list[str]:
    """Консервативные сигналы ревью; смысл и правдивость отдельно проверяет редактор."""
    head, _, body = text.partition("\n\n")
    words = lambda s: set(re.findall(r"[а-яё]{4,}", s.lower()))  # noqa: E731
    title_words = words(head)
    first = words(re.split(r"[.!?]", body, maxsplit=1)[0])
    notes = []
    if len(title_words) >= 3 and len(title_words & first) / len(title_words) >= 0.8:
        notes.append("первое предложение повторяет заголовок")
    for phrase in ("не оставит равнодушным", "в мире хоккея", "настоящая сенсация", "время покажет"):
        if phrase in text.lower():
            notes.append(f"редакторский штамп: {phrase}")
    return notes


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


def hero_of(s: Story, names: dict, ours: set[int], headline: str | None = None) -> int | None:
    """Герой карточки: игрок из тегов новости с русским именем, наш — в первую очередь.
    Тегов нет (сводка травм) — упомянутый в тексте, чья фамилия стоит в заголовке."""
    if headline is not None:
        # Карточка иллюстрирует пересказ: сводка может содержать несколько разных новостей.
        known = [p for p in sorted(s.pids | s.mentioned) if str(p) in names
                 and guard.mentions(headline, names[str(p)]["surname"])]
        return min(known, key=lambda p: headline.find(names[str(p)]["surname"]), default=None)
    known = [p for p in sorted(s.pids) if str(p) in names]
    if not known:
        low = s.headline.lower()
        known = [p for p, en in sorted(s.en.items()) if str(p) in names and en.split()[-1].lower() in low]
    return next((p for p in known if p in ours), known[0] if known else None)


def focus_teams(s: Story, hero: int | None) -> list[str]:
    candidates = set()
    for section in re.split(r"(?m)^#{1,6}\s+", s.text)[1:]:
        heading, _, content = section.partition("\n")
        if hero in s.en and s.en[hero].casefold() in content.casefold():
            # В абзаце есть и соперники: клуб героя задан заголовком раздела.
            candidates |= teams_in(heading)
    if not candidates and hero in s.en:
        # Explicit owner relation is usable without section markup; opponents
        # elsewhere in the sentence never become club ownership.
        pattern = (rf"{re.escape(s.en[hero])}\s+of\s+(?:the\s+)?(.{{1,80}}?)"
                   r"(?:\s+(?:is|was|has|will|who)\b|[.,\n]|$)")
        for match in re.finditer(pattern, s.text):
            candidates |= teams_in(match.group(1))
    return sorted(candidates) if len(candidates) == 1 else []


def card(s: Story, body: str, names: dict, ours: set[int], goalies: list[dict], teams_ru: dict,
         msk: str, path: Path, packet: dict | None = None) -> Path:
    if packet:
        spec = fact_packet.card_spec(packet)
        return render_story_card(spec["label"], spec["teams"], spec["hero"], spec["hero_id"] in ours,
                                 spec["headline"], None, teams_ru, msk, path)
    head = body.partition("\n\n")[0]
    hero = hero_of(s, names, ours, headline=head)
    g = next((g for g in goalies if g["pid"] == hero), None)
    stats = f"{g['season']} · {g['games']} · КН {g['gaa']} · %ОБ {g['sv']}" if g else None
    # у обмена — оба клуба; у остального — клуб из тегов (первый по алфавиту: тегов обычно один)
    report = "status report" in s.headline.lower()
    tagged = sorted(t for t in s.teams | teams_in(s.text + s.headline)
                    if t in teams_ru and guard.mentions(body, teams_ru[t]))
    if report:
        tagged = focus_teams(s, hero)
    if not report:
        # A single tagged club can identify a tagged headline hero. A club merely
        # mentioned in the prose can be an opponent, never proof of ownership.
        tagged = focus_teams(s, hero)
        if not tagged and hero in s.pids and len(s.teams) == 1:
            tagged = sorted(s.teams)
    teams = tagged[:1]
    if s.kind == "trade":
        moves = trade_facts(s).moves
        # Never pick clubs alphabetically from unrelated transactions/background.
        teams = [moves[0].source, moves[0].destination] if moves else []
    return render_story_card("СВОДКА НХЛ" if report else LABELS[s.kind], teams,
                             names[str(hero)]["ru"] if hero else None, hero in ours,
                             body.partition("\n\n")[0], stats, teams_ru, msk, path)


def render(s: Story, body: str, msk: str, stats: list[str] = ()) -> str:
    emoji, tag, _ = KINDS[s.kind]
    if "status report" in s.headline.lower():
        emoji, tag = "📰", "#СводкаНХЛ"
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
            deliver: Callable[[str, str], tuple[bool, str]], notify: Callable[[str], None],
            discover: Callable[[set[int]], tuple[list[str], dict]] | None = None,
            refresh_fetch=None) -> list[str]:
    """Один проход: → строки для лога. write(промпт, гард) → (текст, кто написал, журнал),
    deliver(дата, рубрика) → итог отправки владельцу/в канал, notify(текст) — владельцу о сбое,
    discover(NHL ID) → новые наши среди героев подписаний/обменов/вызовов (registry.from_story)."""
    state = load_state(now)
    msk = now.date().isoformat()
    # Сохраняем исходники выбранных новостей: отказ модели может пережить
    # несколько обновлений короткой ленты (40 элементов).
    queued = state.setdefault("pending_items", {})
    raw = list(queued.values()) + fetch(FEED).get("items", [])
    raw, refreshed = source_watch.prepare(
        raw, state, now, parse_item, lambda s: body_text(fetch(s.url)),
        bounded_fetch=(lambda s, timeout: body_text(refresh_fetch(s.url, timeout))) if refresh_fetch else None)
    parsed = {s.eid: (s, it) for it in raw if (s := parse_item(it))}
    items = [s for s, _ in parsed.values()]
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
        if report_repeat(s, state, now, remember=False):
            state["seen"][s.eid] = now.isoformat()
            continue
        kind = f"story-{s.eid[:8]}"
        queued[s.eid] = parsed[s.eid][1]
        save_state(state)
        draft_msk = state.setdefault("draft_dates", {}).get(s.eid, msk)
        # После сбоя доставки повторяем тот же черновик: уже отправленные каналы
        # пропустит publish(), модель и источник повторно не вызываются.
        if publish.draft_path(draft_msk, kind).exists():
            ok, info = deliver(draft_msk, kind)
            log.append(f"инфоповод {s.slug} ({s.kind}): {'ок' if ok else 'ошибка'} — {info}")
            if ok:
                state["seen"][s.eid] = now.isoformat()
                queued.pop(s.eid, None)
                report_repeat(s, state, now)
                save_state(state)
            continue
        try:
            s.text, s.en = refreshed[s.eid] if s.eid in refreshed else body_text(fetch(s.url))
            s.mentioned = set(s.en)
        except RuntimeError as e:
            log.append(f"инфоповод {s.slug}: текст не получен ({e})")
            continue
        names = wiki(s.mentioned | s.pids, registry)
        packet = fact_packet.extract(s, names, teams_ru, TEAM_EN)
        equivalent = story_provenance.equivalent_draft(s, packet, publish.OUT, msk)
        if equivalent:
            previous_path, previous = equivalent
            previous_date, previous_kind = previous_path.stem.split("_", 1)
            if previous.get("published") or previous.get("rejected") or previous.get("editorial_closed"):
                ok, info = True, "прежний редакционный исход сохранён"
            else:
                ok, info = deliver(previous_date, previous_kind)
            log.append(f"инфоповод {s.slug}: прежние факты, существующая задача — {info}")
            if ok:
                source_watch.remember(state, parsed[s.eid][1], s, now)
                state["seen"][s.eid] = now.isoformat()
                queued.pop(s.eid, None)
                save_state(state)
            continue
        notes: list[str] = []
        reference = story_provenance.published_reference(s, publish.OUT, msk)
        events_db = event_registry.Registry(publish.OUT / "event_registry.sqlite3")
        try:
            events_db.sync_archive(publish.OUT)
            extracted = fact_packet.revision(packet) if packet else event_registry.extract(s)
            revision = events_db.bind_reference(extracted, s.text)
            decision = events_db.classify(revision)
            events_db.register(f"{draft_msk}_{kind}.json", s.slug, revision,
                               {"headline": s.headline, "text": s.text[:20000], "en": s.en})
        finally:
            events_db.close()
        if decision["status"] == "duplicate":
            state["seen"][s.eid] = now.isoformat()
            queued.pop(s.eid, None)
            log.append(f"инфоповод {s.slug}: уже опубликована та же версия события")
            save_state(state)
            continue

        def accept(text: str, s=s, names=names, notes=notes) -> list[str]:
            issues, found = check(text, s, names, registry, teams_ru, ours)
            if reference and not (revision.get("references") and decision["status"] in ("new", "update")):
                found.append(f"ссылка на уже опубликованное событие {reference['slug']}: "
                             "нужно подтвердить новые факты, а не повторять событие")
            if decision["status"] == "review":
                found.extend(f"факты события: {reason}" for reason in decision["reasons"])
            notes[:] = found
            return issues

        if packet:
            body = fact_packet.render(packet)
            errors = fact_packet.verify(packet, fact_packet.snapshot(s), body)
            body, source, attempts = (None if errors else body), "fact_template_v1", errors
            notes = [] if decision["status"] != "review" else decision["reasons"]
        else:
            body, source, attempts = write(lambda _p, s=s, names=names: prompt_for(s, names, teams_ru, ours), accept)
            notes.append("свободный пересказ: утверждения требуют редакторского подтверждения")
        if not body:  # новость есть, а поста нет — владелец должен знать
            failures = state.setdefault("failures", {})
            failures[s.eid] = failures.get(s.eid, 0) + 1
            delay = min(6 * 60 * 60, 30 * 60 * 2 ** min(failures[s.eid] - 1, 4))
            state.setdefault("retry_after", {})[s.eid] = now.timestamp() + delay
            why = "; ".join(attempts)[:600] or "модель не ответила"
            notices = state.setdefault("failure_notices", {})
            previous = notices.get(s.eid)
            if not previous or now - datetime.fromisoformat(previous) >= timedelta(hours=6):
                notify(f"⚠️ Инфоповод без поста: {s.headline}\n{s.link}\n{why}")
                notices[s.eid] = now.isoformat()
            log.append(f"инфоповод {s.slug}: пересказ не прошёл гард — {why[:300]}")
            continue
        variant = f"пересказ {source}" + (f" · 👀 проверь: {'; '.join(notes)}" if notes else "")
        goalies = [] if packet else goalie_stats(s, names, ours, fetch)
        try:
            pic = str(card(s, body, names, ours, goalies, teams_ru, msk,
                           publish.OUT / f"{msk}_{kind}.png", packet=packet))
        except Exception as e:  # картинка — украшение: без неё пост всё равно выходит
            pic = None
            log.append(f"инфоповод {s.slug}: карточка не собралась ({type(e).__name__}: {e})")
        data = {"slug": s.slug, "auto": not notes, "event_revision": revision, "event_decision": decision,
                "source_event": {"kind": s.kind, "pids": sorted(s.pids), "teams": sorted(s.teams),
                                 "headline": s.headline, "date": s.date.isoformat(),
                                 "text": s.text[:20000], "text_truncated": len(s.text) > 20000,
                                 "en": s.en, "health": health_facts(s)}}
        data["source_snapshot"] = fact_packet.snapshot(s)
        data["source_snapshot"]["fetched_at"] = now.isoformat()
        if packet:
            data["fact_packet"] = packet
            data["packet_hash"] = fact_packet.key(packet)
            expiry = fact_packet.expires_at(packet)
            if expiry:
                data["expires_at"] = expiry
            if pic:
                data["card_spec"] = fact_packet.card_spec(packet)
                data["card_hash"] = story_validation.image_hash(pic)
        if s.kind == "trade":
            data["trade_facts"] = trade_facts(s).data()
        caption = (fact_packet.caption(packet, data["source_snapshot"], msk) if packet else
                   render(s, body, msk, [goalie_line(g) for g in goalies]))
        publish.save_draft(msk, caption, [], variant, pic,
                           kind=kind, data=data)
        source_watch.remember(state, parsed[s.eid][1], s, now)
        state["draft_dates"][s.eid] = msk
        save_state(state)  # дата черновика переживает сбой доставки и московскую полночь
        ok, info = deliver(msk, kind)
        log.append(f"инфоповод {s.slug} ({s.kind}): {'ок' if ok else 'ошибка'} — {info}")
        if ok:
            state["seen"][s.eid] = now.isoformat()
            queued.pop(s.eid, None)
            report_repeat(s, state, now)
            save_state(state)
    save_state(state)
    return log
