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
- **🔴 DNS на личном VPS не переживает перезагрузку.** 01.08.2026 в 19:48 сервер ребутнулся — и бот замолчал на два дня: `httpx.ConnectError: [Errno -3] Temporary failure in name resolution` на `get_me()` при старте, systemd поднимал его каждые 10 секунд по кругу (`activating (auto-restart)`). Причина: `/etc/resolv.conf` — симлинк на `/run/resolvconf/resolv.conf`, который генерится при загрузке; в источниках `resolvconf` (`resolv.conf.d/base`, `head`, `tail`) не было ни одного `nameserver`, а ни один интерфейс DNS не отдал → файл сгенерился пустым. До ребута конфиг жил с апреля на том, что раздал интерфейс при установке. **Лечение:** `printf '\nnameserver 1.1.1.1\nnameserver 8.8.8.8\n' >> /etc/resolvconf/resolv.conf.d/head && resolvconf -u`. **Правило: не править `/etc/resolv.conf` напрямую** — там симлинк, правки затрутся при следующем `resolvconf -u`. **Урок шире грабли:** конфиг сервера, которого нет в репо, существует только до первой перезагрузки.
- **Маршруты целы ≠ сеть работает.** При диагностике «нет связи» пинговать и IP (`ping 8.8.8.8`), и имя (`ping api.telegram.org`): первое идёт, второе нет → это DNS, а не сеть и не провайдер. `wg show` на этом сервере молчит не из-за поломки — там AmneziaWG (`awg0`), у него своя утилита `awg`.
- **🔴 `basicConfig(level=INFO)` роняет секреты в лог.** Глобальный INFO включается для ВСЕХ библиотек, включая HTTP-клиенты. `httpx` (внутри python-telegram-bot) на INFO печатает полный URL запроса, а токен бота — часть URL Telegram API. Итог: токен светился в `journalctl` в каждой строке каждые 10 секунд (найдено 19.07.2026, токен отозван через BotFather). **Правило: сторонние логгеры глушить явно** — `logging.getLogger("httpx").setLevel(logging.WARNING)` (и `httpcore`). Проверять по факту: `journalctl -u <сервис> -n 30 --no-pager` и глазами искать секреты, а не полагаться на код.

## Ритуал: разбор логов — обязательная часть КАЖДОГО спринта
В начале спринта (до новых задач):
1. На VPS: `cat /opt/hockey-platform/bot/queries.log` и `cat /opt/hockey-platform/bot/missing_queries.log` → вставить в чат.
2. Разобрать miss-запросы: что искали, почему не нашли.
3. Добавить/улучшить термины по спросу (`tools/add_term.py`), не-словарные запросы → в контент/бэклог.
4. Очистить: `> /opt/hockey-platform/bot/queries.log && > /opt/hockey-platform/bot/missing_queries.log`

## Процесс главы истории
1. Исследователь → полный markdown-черновик → `docs/history/drafts/ИМЯ.md` (сдавать ПОЛНЫЙ текст, не резюме).
2. PM → QA (канон `docs/history/INDEX.md`, RU-качество, границы между главами, помечено ли спорное).
3. Дев (Cowork) → вёрстка `docs/history/ИМЯ.html` по конвейеру `python tools/build_chapter.py <id>` (мета — во frontmatter черновика; скрипт сам ставит `published:true`+url+summary+sections+keywords в оба `history.json`, Article+Breadcrumb JSON-LD с ISO-датами +03:00 и перешивает навигацию между главами) → `build_seo.py` (sitemap) → пуш.
4. PM → приёмка на проде (страница, якоря, индекс, Article, sitemap).

## Данные и валидация
- Источник правды — `data/`; зеркало для сайта — `docs/data/`. `tools/validate_data.py` проверяет целостность реестров + паритет зеркал + обязательный `status`.
- Категории терминов: `stat / tactic / rule / position / basics / org`. Кластеры — отдельный реестр `clusters.json`.
- Календарь (`data/calendar.json`) — только в `data/` (фича бот-онли, сайт не читает), паритет не требуется.

## Хэндофф-брифы (архив по спринтам)
`project/handoff/` — брифы PM→дев/исследователь по каждому треку (s6_*, s7_*). Полезно как шаблоны для будущих спринтов.
