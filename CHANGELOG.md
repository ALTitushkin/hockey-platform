# Changelog

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
- `data/terms.json` — 20 верифицированных термин