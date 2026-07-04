# Операционные заметки (dev/process)

> Рабочий слой для разработки — то, что нужно Claude/деву по ходу. Не для витрины.
> Пользовательский статус-обзор — в Obsidian-дашборде. Детали спринтов — в `sprint_N.md` / `sprint_N_results.md`.

## Инфраструктура
- **Сайт:** https://altitushkin.github.io/hockey-platform/ (GitHub Pages из папки `docs/`)
- **Репо:** https://github.com/ALTitushkin/hockey-platform
- **Бот:** @hockey_platform_bot (Telegram), python-telegram-bot
- **VPS:** британский; общий с x-ui (VPN) и nginx (опросник), ~230 МБ свободно. Бот — systemd-юнит `hockey-bot` (автостарт, рестарт при падении).
- **Деплой:** push в `main` → GitHub Actions → SSH → рестарт бота. Workflow фильтрует пути: срабатывает только на `bot/**`, `data/**`, `.github/**`. Правки `docs/`/`tools/`/корневых `.md` бот НЕ передеплоивают (Pages обновляется сам).

## Грабли (проверено болью)
- **PTB запинен `<22`** — версия 22.x ломает `run_polling` (процесс стартует и тихо выходит). Не обновлять.
- **После деплоя проверять `journalctl`** на строку «Бот запущен …», а не только `is-active` (был кейс обрезанного `bot.py` без `main()` — `py_compile` это не ловит).
- **`.env`:** нужна строка `BOT_TOKEN=...` целиком, голый токен не парсится.
- **AdGuard** с фильтрацией HTTPS подменяет сертификат Telegram → `CERTIFICATE_VERIFY_FAILED`. Решение: AdGuard → Сеть → Фильтруемые приложения → отключить для `python.exe`.
- **`.git`-локи на подключённом диске (Cowork):** коммиты из песочницы падают на `HEAD.lock`/`index.lock` (нет прав на `.git`). Договорённость: PM готовит файлы, **коммитит пользователь** на своей стороне. В PowerShell `&&` не работает — команды по одной или через `;`.
- **Модуль календаря — `bot/calendar_feature.py`** (не `calendar.py`), чтобы не конфликтовать со стандартной библиотекой Python.
- **Поиск:** нечёткое совпадение включать только при пустых exact/prefix — иначе «нмхл» тащит «нхл».

## Ритуал: разбор логов — обязательная часть КАЖДОГО спринта
В начале спринта (до новых задач):
1. На VPS: `cat /opt/hockey-platform/bot/queries.log` и `cat /opt/hockey-platform/bot/missing_queries.log` → вставить в чат.
2. Разобрать miss-запросы: что искали, почему не нашли.
3. Добавить/улучшить термины по спросу (`tools/add_term.py`), не-словарные запросы → в контент/бэклог.
4. Очистить: `> /opt/hockey-platform/bot/queries.log && > /opt/hockey-platform/bot/missing_queries.log`

## Процесс главы истории
1. Исследователь → полный markdown-черновик → `docs/history/drafts/ИМЯ.md` (сдавать ПОЛНЫЙ текст, не резюме).
2. PM → QA (канон `docs/history/INDEX.md`, RU-качество, границы между главами, помечено ли спорное).
3. Дев (Cowork) → вёрстка `docs/history/ИМЯ.html` по конвейеру `tools/build_chapter.py` (меняется блок CONFIG) → `published:true`+url+summary+sections в `history.json` (оба зеркала) → Article+Breadcrumb JSON-LD (ISO-даты +03:00) → `build_seo.py` (sitemap) → пуш.
4. PM → приёмка на проде (страница, якоря, индекс, Article, sitemap).

## Данные и валидация
- Источник правды — `data/`; зеркало для сайта — `docs/data/`. `tools/validate_data.py` проверяет целостность реестров + паритет зеркал + обязательный `status`.
- Категории терминов: `stat / tactic / rule / position / basics / org`. Кластеры — отдельный реестр `clusters.json`.
- Календарь (`data/calendar.json`) — только в `data/` (фича бот-онли, сайт не читает), паритет не требуется.

## Хэндофф-брифы (архив по спринтам)
`project/handoff/` — брифы PM→дев/исследователь по каждому треку (s6_*, s7_*). Полезно как шаблоны для будущих спринтов.
