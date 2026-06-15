# Changelog

## [0.8.0] — 2026-06-14

### Добавлено (Слой B · вёрстка под концепт S5, направление A «Учебник»)
- IA Шаг 1: новый лёгкий `docs/index.html` — ответ-вход (гибрид: `quick_answers.json` сверху + Fuse.js fallback по терминам и главам истории) + 4 карточки-входа; счётчики (терминов/глав) тянутся из данных, не хардкод
- `docs/dictionary.html` — словарь (стиль A) на `terms.json` + `clusters.json`: три независимые оси фильтров (Уровень/Профиль/Категория), вид «Кластеры ⇄ A→Z», «Вне кластеров» для терминов без группы, карточки с `see_also`/`anchor`/слотом визуала (схема/видео), мобильный drawer «Фильтры (N)»
- `docs/history.html` — индекс глав из `history.json`: группировка по эрам, `published` → метка «Скоро», ссылки на страницы глав; deep-link на разделы (`origins.html#<section-id>`)
- `history.json`: индекс истории показывает только сверенную главу `origins`. Роадмап глав 2–9 **придержан** (PM): `history.json` разошёлся с `docs/history/INDEX.md` — публиковать несверенный список нельзя, вернём после сверки с research-чатом
- `docs/assets/wordmark-{stacked,inline,mono}.svg` — вордмарк «КУЛЬТУРА ХОККЕЯ» как SVG (У без дескендера по `wordmark_spec.md`, графит+стальной), вставлен в шапку главной
- Микрокопия слотов: «Обучение»/«Сообщество» → «Раздел в разработке» (заглушки «скоро»)
- Партнёр-ссылка «при поддержке канала» — в шапке (кликабельна) и в подвале

### Изменено
- `docs/history/origins.html`: ссылки «Словарь» → `dictionary.html` (после переезда index→хаб)
- `tools/validate_data.py`: url обязателен только у опубликованных глав (заглушки — `url:null`)

### Примечания / TODO
- Кластеры: реестр пока 2 группы (shots/power-play) → словарь показывает их + «Вне кластеров». Расширение таксономии (дизайнер предложил ~9 групп) — отдельная задача данных/PM
- Профиль-ось: чипы строятся из данных; `profiles` пустые до разметки контент-чатом → ось показывает «размечается, позже»
- Вордмарк — геометрический v1 по правилу базовой линии; PNG для бота/превью отрендерить после утверждения (в песочнице нет растеризатора). Точные контуры Oswald — опциональный следующий проход
- Удалён осиротевший `docs/app.js` (программка-словарь заменена `dictionary.html`); `style.css` оставлен — его читает `origins.html`

## [0.7.0] — 2026-06-14

### Добавлено (Слой данных под концепт S5, Трек B-A)
- `data/clusters.json` — реестр кластеров терминов (решение: отдельный реестр, не «термины-контейнеры»); сидинг: Броски, Большинство
- `data/quick_answers.json` — курируемые быстрые ответы для гибрид-движка главной (вопрос → саммари → якорь)
- `terms.json`: новые поля `profiles[]` (ось Профиль — заполнит контент-чат), `cluster`, `see_also[]`, `anchor`; сидинг кластеров (shots/power-play) и `see_also`
- `history.json`: `sections[{id,title}]` (якоря разделов) + `published`; id-якоря добавлены к h2 в `docs/history/origins.html`
- Визуал расширен под видео: `visual="youtube:ID"` + `visual_timecode`/`visual_caption`/`visual_attribution` (контракт в `schema.md`)
- `tools/validate_data.py` — проверка ссылочной целостности реестров и паритета `data/` ↔ `docs/data/`
- `data/schema.md` v2.0 + `docs/data/` зеркала всех реестров; `CLAUDE.md` — модель данных S5

### Примечания
- Уровень: ключи `novice/fan/geek` не трогаем; карта меток `База/Средний/Продвинутый` — в UI
- Живой сайт не затронут: `app.js` читает только `diagram`/`level`, новые поля игнорирует
- Вёрстка (Слой B: index→dictionary, новый ответ-вход) — после HTML из Claude Design

## [0.6.0] — 2026-06-13

### Добавлено
- База: +10 терминов из разбора лога запросов (wrist-shot, slap-shot, snap-shot, zone-defense, umbrella, box-out, neutral-zone, cross-check, delayed-penalty, empty-net) → 49 verified
- Бот: в меню /start добавлена кнопка-ссылка «📚 История хоккея» (раздел истории на сайте)
- Бот: inline-режим теперь отдаёт **главы истории** при miss по словарю (`@bot история хоккея` → карточка со ссылкой «Читать статью»)
- `data/history.json`: расширены `keywords` главы «Истоки» под реальные формулировки (18 ключей)
- `bot/search.py`: история вынесена в чистый модуль — `load_history()`, `find_history_chapter()` (совпадение по границам слов, защита от ложных срабатываний на короткие/общие слова)
- `bot/test_search.py`: тесты `find_history_chapter` (хиты + анти-ложные срабатывания)
- `bot/README.md`: памятка по inline (что это, включение в BotFather, использование, частые грабли)

### Исправлено
- Бот: в `/start` и `/help` был захардкожен неверный username `@hockey_overtime_bot`; теперь реальный `@hockey_platform_bot` берётся из `bot.username` на старте (`_post_init`), с дефолтом и override через env `BOT_USERNAME`
- Бот: `handle_query` игнорирует сообщения «через бота» (`via_bot`) — бот больше не реагирует на эхо собственных inline-карточек в группах
- Деплой: `python-telegram-bot` запинен `>=21.0,<22` — версия 22.x ломала `run_polling` (процесс стартовал и тихо выходил)
- Бот: запрос, по которому нашлась глава истории, больше не пишется в `missing_queries.log` как miss (логируется как hit)
- Настройка: в @BotFather включён privacy mode, чтобы бот не отвечал на постороннюю переписку в группах (см. `bot/README.md`)

## [0.5.0] — 2026-06-13

### Добавлено
- Бот: inline-режим (`@bot термин` в любом чате) — `handle_inline`, `InlineQueryHandler`, карточки `InlineQueryResultArticle`
- Мост в историю: `find_history_chapter` + `data/history.json` (1 глава «Истоки»), ответ текстом при miss по словарю
- Лог всех запросов `bot/queries.log` (hit/miss)

## [0.3.0] — 2026-06-12

### Добавлено
- База: +14 терминов → 35 verified (icing, offside, позиции C/LW/RW/D/G, deke, breakaway, screen, rebound, one-timer, cycle, breakout, enforcer)
- Бот: лог ненайденных запросов `bot/missing_queries.log` — сырьё для наполнения базы
- `deploy/hockey-bot.service` — systemd-юнит для VPS
- `.github/workflows/deploy.yml` — автодеплой на VPS при пуше в main
- `docs/sprint_3.md` — ТЗ спринта 3
- `bot/README.md`: инструкция настройки VPS и автодеплоя

## [0.2.0] — 2026-06-12

### Добавлено
- `bot/bot.py` — Telegram-бот: поиск термина текстом, /start, /help (python-telegram-bot, polling)
- `bot/search.py` — поисковый модуль поверх `data/terms.json` (точное + нечёткое совпадение, без зависимостей)
- `bot/test_search.py` — тесты поиска, запускаются без токена
- `bot/README.md`, `bot/requirements.txt`
- `docs/sprint_2.md` — ТЗ спринта 2
- `docs/sprint_1_results.md` — итоги спринта 1

### Не сделано (бэклог)
- Хостинг бота (Railway/Render) — после локального теста
- Inline-режим, расширение базы, визуальные схемы

## [0.1.0] — 2026-06-07

### Добавлено
- Базовая структура репо: `data/`, `web/`, `bot/`, `docs/`
- `data/terms.json` — 20 верифицированных терминов (stat: 8, tactic: 7, rule: 2, stat mix: 3)
- `data/expert_review.json` — 3 неподтверждённых сленгизма
- `data/schema.md` — описание схемы данных
- `web/index.html` + `web/style.css` + `web/app.js` — словарь с поиском (Fuse.js) и фильтрами по категориям
- `CLAUDE.md` — контекст для Claude Code
- `README.md` — публичное описание

### Не сделано (следующий спринт)
- GitHub Pages деплой
- Telegram-бот
- Визуальные схемы для тактики (форчек, слот)
