# Культура хоккея

Образовательная хоккейная платформа: от англо-русского словаря терминов до базы знаний по истории и тактике. Для тех, кто работает с английскими материалами, статистикой и разборами — и хочет понимать игру глубже.

**Живой сайт:** https://altitushkin.github.io/hockey-platform/
**Телеграм-бот:** [@hockey_platform_bot](https://t.me/hockey_platform_bot) · при поддержке канала [«Хоккейный Овертайм»](https://t.me/lifeinovertime)

---

## Что внутри

- **Словарь** — 62 проверенных термина (статистика, тактика, правила, позиции, базовое, лиги), три оси фильтров (уровень × профиль × категория), кластеры и нечёткий поиск.
- **История хоккея** — лонгриды-главы (сейчас 4: Истоки → Золотой век Канады → С чистого льда → Тарасов), с fact-box'ами, таймлайнами и якорями на разделы.
- **Бот** — поиск термина текстом и inline (`@bot термин` в любом чате), мост в историю, рубрика «📅 В этот день в истории хоккея».

## Как устроено

- **Данные отдельно от интерфейса.** Источник правды — `data/*.json` (термины, история, календарь, кластеры), зеркало для сайта — `docs/data/`.
- **Неподтверждённый сленг** — в `data/expert_review.json` со статусом `unverified`, не смешивается с фактами.
- **Сайт** — статический HTML/CSS/JS на GitHub Pages (папка `docs/`), без серверов и фреймворков. SEO/AI-SEO: JSON-LD, sitemap, robots с доступом AI-краулеров.
- **Бот** — Python (python-telegram-bot) на VPS под systemd; поисковая логика (`bot/search.py`, `bot/calendar_feature.py`) изолирована от Telegram и покрыта тестами.
- **CI/CD** — push в `main` → GitHub Actions: тесты + валидация данных **гейтят** деплой бота на VPS (с healthcheck по логу запуска).

## Структура репозитория

```
docs/       — сайт (GitHub Pages): HTML/CSS, data/ (зеркало), history/ (главы)
data/       — источник правды: terms/history/calendar/clusters/quick_answers (+ schema)
bot/        — Telegram-бот + тесты (search.py, calendar_feature.py, bot.py)
tools/      — утилиты: add_term.py, validate_data.py, build_seo.py, build_chapter.py
project/    — проектная документация (старт: project/README.md)
CLAUDE.md   — контекст и архитектура · CHANGELOG.md — история версий
```

## Запуск локально

Сайт:
```bash
cd docs
python -m http.server 8000    # http://localhost:8000  (file:// не годится: используется fetch())
```

Бот:
```bash
BOT_TOKEN=<токен> python bot/bot.py     # или положить токен в bot/.env (BOT_TOKEN=...)
```

## Добавить термин

Через CLI (валидирует и пишет в оба `terms.json`):
```bash
python tools/add_term.py
```
Неподтверждённый сленг -> `data/expert_review.json` (`status: unverified`). Схема полей — `data/schema.md`.

---

Документация проекта — [`project/README.md`](project/README.md). Контекст и архитектурные решения — [`CLAUDE.md`](CLAUDE.md).
