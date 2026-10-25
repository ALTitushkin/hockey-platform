# CLAUDE.md — Hockey Dictionary Platform

> Этот файл читается Claude Code в начале каждой сессии.
> Обновляй его при каждом значимом изменении архитектуры или решений.
> Последнее обновление: 25.10.2026 · v0.16+

---

## Что это за проект

Хоккейная образовательная платформа. Начинается со словаря англ→рус хоккейных терминов.

**Ядро ценности:** момент «ага» — когда пользователь утыкается в английский термин и мгновенно получает понятное объяснение на русском. Не перевод, а понимание.

**Целевые пользователи (спринт 1):** русскоязычные хоккейные фанаты и начинающие тренеры/игроки, которые работают с англоязычными материалами и таблицами статистики.

---

## Принципы, которые не нарушаем

1. **Одно ядро — много обёрток.** Данные (JSON) отдельно от интерфейса. Поменять UI — не значит переписывать базу.
2. **AI/человек граница чёткая.** В базу идут только проверяемые термины. Сленг (рыбачок, поплавок) — в отдельный файл `expert_review.json` со статусом `unverified`. Никогда не выдавать догадку за факт.
3. **Каждый этап рабочий сам по себе.** Если остановились — предыдущий этап всё равно работает.
4. **Документация обновляется вместе с кодом.** Устаревший CLAUDE.md хуже отсутствующего.

---

## Структура репо

```
hockey-platform/
├── CLAUDE.md                  # этот файл — читать первым
├── README.md                  # публичное описание проекта
├── CHANGELOG.md               # лог изменений по версиям
│
├── data/                      # ЯДРО — не зависит от UI (зеркало в docs/data/ для сайта)
│   ├── terms.json             # база терминов (источник правды)
│   ├── expert_review.json     # сленг на выверку, статус unverified
│   ├── clusters.json          # реестр кластеров (группы терминов: Броски, Большинство)
│   ├── history.json           # главы истории: sections (якоря) + published; мост из бота
│   ├── quick_answers.json     # курируемые быстрые ответы для гибрид-движка главной
│   ├── learning.json          # учебные маршруты раздела «Обучение» (шаги → термины/схемы/главы/самопроверка)
│   ├── calendar.json          # рубрика бота «В этот день» (MM-DD → события); только data/, не зеркалится
│   ├── parents.json           # гайд «Родителям»: короткий слой + сравнение + search (поиск сайта и бота)
│   └── schema.md              # описание структуры всех реестров
│
├── web/                       # веб-интерфейс (спринт 1-2)
│   ├── index.html
│   ├── style.css
│   └── app.js
│
├── bot/                       # Telegram-бот (спринт 2)
│   ├── bot.py                 # хендлеры + polling + inline + рубрика «В этот день»
│   ├── search.py              # поиск по базе + мост в историю, без Telegram-зависимостей
│   ├── calendar_feature.py    # рубрика «В этот день»: parse_date/события/карточка (имя ≠ calendar.py — не затеняем stdlib)
│   ├── test_search.py         # тесты поиска (без токена)
│   ├── test_calendar.py       # тесты календаря (без токена)
│   └── README.md              # как запустить локально + памятка по inline/календарю
│
├── tools/                     # утилиты
│   ├── add_term.py            # CLI добавления термина (пишет в оба terms.json)
│   ├── validate_data.py       # проверка целостности реестров + паритета зеркал
│   ├── validate_calendar.py   # проверка calendar.json + покрытие; --sync — батч исследователя → data/
│   ├── build_chapter.py       # сборка главы истории из черновика с frontmatter
│   ├── build_seo.py           # sitemap.xml + DefinedTerm в dictionary.html
│   ├── build_diagrams.py      # генератор тактических SVG-схем (docs/diagrams/)
│   └── calendar-build/        # кухня исследователя календаря (батч hockey_calendar.json, ruff exclude)
│
├── deploy/                    # прод бота: deploy.sh (healthcheck), watchdog.sh (алерт), README (runbook)
├── Dockerfile, docker-compose.yml  # контейнер бота на app-VPS
│
├── docs/                      # САЙТ (GitHub Pages раздаёт отсюда) — НЕ документация
│   ├── index.html / dictionary.html / history.html / learn.html / style.css / logo.png
│   ├── robots.txt / sitemap.xml / .nojekyll
│   ├── data/                  # зеркало data/ для сайта
│   ├── assets/ , diagrams/    # вордмарки, SVG-схемы
│   └── history/               # HTML глав + INDEX.md (канон) + drafts/ (черновики)
│
├── project/                   # ПРОЕКТНАЯ ДОКУМЕНТАЦИЯ — старт: project/README.md
│   ├── README.md              # навигация по всей доке
│   ├── planning/              # ТЗ спринтов + results/ (итоги)
│   ├── design/                # концепт, дизайн-брифы, вордмарк-спека
│   ├── content/               # гайд наполнения, рубрикатор, анонс канала
│   ├── process/               # ops_notes (грабли/VPS/ритуалы), team_process, architecture
│   │   └── handoff/               # брифы PM→дев/исследователь по трекам
│   # стандарты процесса: project/process/documentation-standard.md
│
└── .gitignore
```

---

## Схема термина (terms.json)

Каждый термин — объект со следующими полями:

```json
{
  "id": "corsi",
  "en": "Corsi",
  "ru": "Корси",
  "category": "stat",
  "abbr": ["CF", "CA", "CF%"],
  "definition": "Считает все попытки броска: в створ, мимо и заблокированные...",
  "ru_slang": null,
  "visual": null,
  "visual_type": null,
  "source": "naturalstattrick.com",
  "status": "verified",
  "added": "2026-06-06",
  "notes": ""
}
```

**Поля:**
- `id` — уникальный slug (латиница, строчные, через дефис)
- `en` — английское название (каноническое)
- `ru` — русский перевод/транслитерация
- `category` — `stat` | `tactic` | `position` | `rule` | `basics` (Базовое/техника) | `org` (Лиги/организации)
- `abbr` — массив сокращений (пусто `[]` если нет)
- `definition` — объяснение по-человечески, без академизма
- `ru_slang` — русский разговорный эквивалент (`null` если нет)
- `visual` — ссылка или описание визуала (`null` если нет)
- `visual_type` — `scheme` | `video` | `gif` | `null`
- `source` — источник/проверка
- `status` — `verified` | `unverified`
- `added` — дата добавления ISO
- `notes` — служебные заметки, видны только в данных

---

## Веб / IA (S5, Шаг 1 концепта `project/design/design_concept_s5.md`)

Главная перестала быть словарём. Структура страниц (направление A «Учебник», все self-contained, данные через `fetch ./data/*.json`):
- `docs/index.html` — **хаб/ответ-вход**: гибрид-движок (курируемые `quick_answers.json` сверху + Fuse.js fallback по `terms.json` и keywords `history.json`) + 4 карточки-входа (Словарь/История/Обучение/Сообщество·слот). Счётчики из данных.
- `docs/dictionary.html` — **словарь**: `terms.json` + `clusters.json`; три оси фильтров (Уровень/Профиль/Категория), кластеры ⇄ плоский A→Z, карточки с see_also/anchor/визуал-слотом, мобильный drawer.
- `docs/history.html` — **индекс истории** из `history.json` (эры + `published`→«скоро»); главы — отдельные страницы `docs/history/<id>.html` с id-якорями. `history.json` синхронизирован с каноном `docs/history/INDEX.md` (9 глав; `id`/`title`/`era`/порядок — зона research-чата, дев не меняет). Опубликованы все 9 глав — раздел закрыт 17.10.2026.
- `docs/learn.html` — **обучение**: маршруты из `learning.json` (шаг = объяснение + мини-карточки терминов со схемами + ссылка в главу + вопрос самопроверки), deep-link `#<маршрут>[-<шаг>]`, прогресс — `localStorage` (удобство, не данные).
- `docs/parents.html` — **родителям** (с 25.10.2026): собирается `python tools/build_parents.py` из `data/parents.json` + `docs/parents/drafts/parents_guide.md` (сборка пишет и зеркало `docs/data/parents.json`, проверяет якоря поиска). Блоки `<!-- hold:doctor -->…<!-- /hold -->` на сайт не идут — ждут ревью спортивного врача; `_meta.hold_doctor` прячет «К врачу, если». Превью со всем текстом — `--preview <путь>`. Поиск: `search[]` → `parentsMatch` на главной и `find_parents_section` в боте (одна логика: слова фразы по грубой основе)

## Новостник (`news/`, с 25.10.2026)

Отдельный сервис: канал @hockey_culture (наши в НХЛ) + чат обсуждений, бот @hockey_culture_news_bot. Контейнер `hockey-news` (GHCR, профиль compose `news`), состояние — `news-runtime/` на сервере. Рубрики: «Ночь в НХЛ» 09:00, «Ночь наших» 09:30, «Сегодня ночью» 18:00 (МСК), автопубликация при чистом гарде (`news/guard.py`), уровни в чате (`news/levels.py`). «⚡ Инфоповоды» (`news/stories.py`, с 26.10.2026): лента NHL.com раз в 15 минут → обмены, контракты, крупные травмы по всей лиге + вызовы/отправки наших; пересказ — модель (`prompts/story.md`), имена — реестр/Wikidata по NHL ID из текста, гард сверяет числа с источником. У вратарей (герой новости и наши из текста) — строка КН и %ОБ из API НХЛ, шаблоном. Картинка — `card.render_story_card` (логотипы клубов, герой, заголовок). Автопубликация `NEWS_STORIES_AUTO=1` (с 26.10.2026); пост с «👀 проверь» — владельцу с кнопками; ручной прогон — `python -m news.run stories --since <часы>`. Тесты: `python -m news.test_news`. Грабли и решения — `project/process/ops_notes.md` (раздел «Новостник»), стратегия — `project/design/content_strategy.md`. Формат состояния на сервере меняем только при остановленном контейнере. Реестр наших — `news/registry.py`: база `data/players.json` + изменения сервера в `news-runtime/registry.json` (утренняя сверка с составами в 08:00, новые из инфоповодов, `/name` от владельца); `run.load()` отдаёт уже слитый реестр. Перенести накопленное в репо — `python -m news.run sync-registry` на сервере и забрать файл.
- Схемы словаря: SVG в `docs/diagrams/`, новые — `python tools/build_diagrams.py` (ручные `forecheck/powerplay/slot` генератор не трогает). Термин ссылается полями `visual/visual_type:"scheme"/visual_caption`; словарь и «Обучение» показывают схему картинкой, бот — ссылкой.
- `docs/assets/wordmark-*.svg` — SVG-вордмарк (не live-текст; У без дескендера, `project/design/wordmark_spec.md`).

Карта меток уровня в UI: `novice→База`, `fan→Средний`, `geek→Продвинутый` (ключи в данных не меняем).
Целостность данных перед коммитом: `python tools/validate_data.py`.

---

## Модель данных платформы (S5, концепт `project/design/design_concept_s5.md`)

Три ортогональные оси таксономии термина: **Категория** (`category`, 1 знач.), **Уровень**
(`level`, упорядочен) и **Профиль** (`profiles[]`, мультизначение — заполняет контент-чат).

Новые поля термина: `profiles[]`, `cluster` (slug из `clusters.json` или null),
`see_also[]` (id смежных), `anchor` (`{target, anchor_id, label}`|null — связь с главой истории).
Визуал расширен под видео: `visual="youtube:ID"` + `visual_timecode`/`visual_attribution`.
Полная схема — `data/schema.md`.

**Уровень — ключи vs метки:** в данных оставляем `novice/fan/geek`; в UI карта меток
`База/Средний/Продвинутый`. Переименование ключей — опционально.

**Кластеры — отдельный реестр (`clusters.json`), не «термины-контейнеры».** Группа — не термин
(нет определения/уровня), поэтому не в `terms.json`. Термин ссылается на кластер полем `cluster`;
если кластер совпадает с термином (Большинство = `power-play`) — связь через `term_id` реестра.

**Реестры под сайт:** `quick_answers.json` (вопрос→саммари→якорь, гибрид-движок главной),
`history.json.sections` (якоря разделов глав = цели deep-link). Целостность всех ссылок —
`python tools/validate_data.py` (часть прогона перед коммитом).

⚠️ **Граница ролей:** дев заводит поля и структурные связи (`cluster/see_also`); разметку
`profiles` по рубрикатору делает контент-чат; тексты истории и `sections`-контент — контент/research.

---

## SEO / AI-SEO (GEO) — фундамент видимости (S6, Трек 1)

Цель: платформу можно **найти** в поиске и **процитировать** в AI-выдаче
(ChatGPT, Claude, Perplexity, Google AI Overviews).

**На всех 4 страницах** (`index`/`dictionary`/`history`/`history/origins`): уникальные
`title`/`description`, `<link rel="canonical">` (абс. URL; у главной — корень без `index.html`),
Open Graph + Twitter Card (`summary_large_image`, картинка `logo.png` абс. URL), один `<h1>`.
JSON-LD `Organization` + `WebSite` встроены статически в `<head>` каждой страницы
(имя «Культура хоккея», `@id`-граф переиспользуется).

**Разметка по страницам:** `BreadcrumbList` — на словаре/истории/главе; `DefinedTermSet`
+ `DefinedTerm` (62) — в словаре, **статически** (краулеры/LLM не исполняют JS);
`Article` — на главах истории (+ видимый `dateModified`). Schema обязана совпадать с
видимым текстом.

**Формат дат `Article`:** `datePublished`/`dateModified` и `og:article:*_time` —
полный ISO 8601 с поясом Europe/Moscow (`2026-06-19T12:00:00+03:00`), иначе Rich
Results выдаёт warning «date without time». Видимый `<time datetime>` — date-only.
Главы истории собираются `python tools/build_chapter.py <id>` (или `--all`) из
markdown-черновика `docs/history/drafts/<id>.md` по шаблону `origins.html`. Мета главы
(даты `published`/`modified`, subtitle, og/meta-описания, `sections`, `keywords` для бота) —
во frontmatter черновика, скрипт не правится. Навигация «← / →» между главами
перешивается автоматически. Затем `build_seo.py` для sitemap.

**`docs/robots.txt`** разрешает AI-краулеров (GPTBot, ClaudeBot, PerplexityBot,
Google-Extended, Applebot-Extended, OAI-SearchBot и др.) + обычные; строка `Sitemap:`.
**`docs/sitemap.xml`** — страницы + только `published:true` главы.

**Регенерация:** `python tools/build_seo.py` пересобирает `sitemap.xml` и инжектит
блок `DefinedTerm` в `dictionary.html` между маркерами `SEO:DEFINEDTERMS`. Читает
только `data/` — паритет `data/ ↔ docs/data/` и `validate_data.py` не задеты.
Запускать после изменений в `terms.json` или `history.json` (новые published-главы).

**Поисковики (18.10.2026):** Google Search Console — ресурс «Префикс URL»
`…/hockey-platform/`, тег `google-site-verification` в `docs/index.html`, sitemap отправлен.
Яндекс.Вебмастер подпапку github.io не подтверждает (файл ищет в корне домена) —
вместо него **IndexNow**: ключ `docs/<KEY>.txt`, отправка `python tools/indexnow.py`
(все URL из sitemap или перечисленные). Запускать после пуша значимых правок сайта.

⚠️ **FAQ-rich не закладываем** (Google убрал FAQ-сниппеты в 05.2026) — Q&A-структуру
держим ради цитируемости LLM, не ради звёздочек в выдаче.

### GEO-гигиена контента (правило для контент/research-чатов)

Чтобы нас цитировали AI-движки: писать **машиночитаемо** и естественно (без
артефактов машинного перевода); **факты — с источниками**; **самодостаточные
секции** с `id`-якорями (каждая отвечает на конкретный вопрос — это цель deep-link
и единица цитирования); держать **свежесть** (видимый `dateModified` на главах).
Новую главу дев верстает по шаблону `origins.html`: ставит `published:true` +
`url` в `history.json`, вешает `Article`-разметку, прогоняет `build_seo.py`
(глава попадёт в sitemap), проверяет в Rich Results Test.

---

## Текущий стек

| Слой | Технология | Почему |
|------|-----------|--------|
| База данных | JSON-файл | Нет инфраструктуры на старте, легко читается, легко версионируется в Git |
| Веб (спринт 1) | Vanilla HTML/CSS/JS | Без фреймворков — минимум зависимостей, максимум контроля |
| Поиск (спринт 1) | Fuse.js (CDN) | Нечёткий поиск на клиенте, 0 серверов |
| Хостинг (спринт 1) | GitHub Pages | Бесплатно, деплой из репо |
| Бот (спринт 2) | Python + python-telegram-bot | Простой стек, много примеров |
| Хостинг бота | Docker на app-VPS (с 30.08.2026) | Изоляция от личной инфры, деплой пушем в `main` |

**Когда пересматривать стек:** когда JSON-файл превысит ~500 терминов или появится нужда в серверной фильтрации. До этого — не менять.

---

## Git-конвенции

```
feat: добавлен термин forecheck
fix: исправлено определение PDO
data: наполнение базы (новые термины)
docs: обновлён CLAUDE.md / README
style: правки вёрстки без изменения логики
refactor: переработка без изменения функционала
```

Ветки:
- `main` — стабильная версия (деплой на GitHub Pages)
- `dev` — активная разработка
- `content/...` — ветки для наполнения базы

---

## Что НЕ делаем (явные ограничения)

- Не тащим фреймворки (React, Vue) до появления реальной нужды
- Не выдаём `unverified` термины как факты в UI
- Не переводим чужие материалы дословно и не публикуем — только пересказ/конспект (авторские права)
- Не строим серверный бэкенд до спринта 3+

---

## Контакт и контекст

- Владелец: Александр (Саша), DevOps → технический продакт
- Режим работы: ~2 часа/нед, без дедлайнов
- Канал для теста аудитории: Telegram-канал по хоккею (есть живая аудитория)
- Кандидат в эксперты по сленгу: аналитик из СКА
- Концепция: `project/design/koncept_platforma.md`
- Спринты: последний закрытый — S9 (`project/planning/results/sprint_9_results.md`); новый не открыт. Вся история — `project/planning/`
- Бот: **@hockey_platform_bot** (username не хардкодим — берётся из `bot.username`)
- Карточка термина в боте ведёт на сайт: схема · глава истории (`anchor`) · `dictionary.html#t-<id>`; база URL — `search.SITE_URL`. У unverified-терминов ссылок нет
- Inline-режим: включается в @BotFather (`/setinline`); при miss по словарю inline и текст предлагают главу истории через `find_history_chapter` (`data/history.json`)
- Рубрика «В этот день» (бот v0.7, S7 Трек A): кнопка «📅 В этот день» + `/today` + `/day <дата>`; логика `bot/calendar_feature.py` (`parse_date` день-первым, `events_for_date`, `format_day_card`, TZ Europe/Moscow `+03:00`). Данные `data/calendar.json` (`MM-DD`; `year/text/cat/reg/conf/video?`), **только в `data/`** (сайт не читает, паритета нет). `parse_date` идёт ДО словаря, даты не пишутся в `missing_queries.log`. Наполнение/`video` — поток исследователя в `tools/calendar-build/hockey_calendar.json`; в бота доезжает `python tools/validate_calendar.py --sync` (тот же валидатор гейтит CI). Бот v0.8 понимает «послезавтра/позавчера», на «56 мая» отвечает «нет такой даты», чинит английскую раскладку и пишет покрытие календаря в строку запуска
- Токен бота: в `bot/.env` (локально и на VPS), в git не попадает
- Прод: с 30.08.2026 — Docker-контейнер `hockey-bot` на app-VPS (`88.218.250.212`), автодеплой через GitHub Actions при пуше в `main` (`deploy/`, `.github/workflows/deploy.yml`, флаг `DEPLOY_ENABLED`). Прежний systemd-стенд на личном сервере снесён
- Наполнение базы: от спроса — разбирать `bot/missing_queries.log`
