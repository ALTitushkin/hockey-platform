# Changelog

## [0.6.0] — 2026-06-13

### Добавлено
- База: +10 терминов из разбора лога запросов (wrist-shot, slap-shot, snap-shot, zone-defense, umbrella, box-out, neutral-zone, cross-check, delayed-penalty, empty-net) → 49 verified
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
