# Хэндофф · Sprint 6 · Трек 1 — SEO/AI-SEO фундамент → DEV-чат

> **От:** PM · **Кому:** чат-разработчик (Cowork) · **Дата:** 19.06.2026
> **Скоуп:** только Трек 1. Главу истории НЕ пишем (это чат-исследователь, Трек 2).
> Вставь этот файл в dev-чат как ТЗ. Полное ТЗ спринта — `project/planning/sprint_6.md`.

## Контекст (одна фраза)
Платформа «Культура хоккея» должна стать находимой в поиске и цитируемой в AI-выдаче (GEO). Сейчас на страницах нет canonical/OG, нет sitemap/robots, нет JSON-LD.

## База
- Прод-URL (GitHub Pages, source = `docs/`): `https://altitushkin.github.io/hockey-platform/`
- Страницы: `index.html` (хаб) · `dictionary.html` · `history.html` · `history/origins.html` (опубликованная глава)
- Данные (источник правды + зеркало `docs/data/`): `terms.json` (49), `history.json` (9 глав, опубликована только `origins`), `clusters.json`, `quick_answers.json`

## Задачи

### A. Технический SEO (на всех 4 страницах)
- Уникальные `<title>` и `<meta name="description">` уже есть — проверить и оставить.
- Добавить `<link rel="canonical">` с абсолютным URL страницы.
- Open Graph (`og:title/description/type/url/image`) + Twitter Card (`summary_large_image`). Картинка — `logo.png`/вордмарк, абсолютным URL.
- Один `<h1>` на страницу, осмысленная иерархия заголовков (проверить словарь/индекс истории).

### B. robots.txt + sitemap.xml (в `docs/`, корень Pages)
- `robots.txt`: разрешить AI-краулеров — **GPTBot, ClaudeBot, PerplexityBot, Google-Extended** (+ Bingbot/обычные); строка `Sitemap:` с абсолютным URL.
- `sitemap.xml`: генерировать из реестров (страницы + только `published:true` главы из `history.json`). Желательно отдельный генератор в `tools/` (по образцу `validate_data.py`), чтобы пересобирать. `lastmod` ставить.

### C. JSON-LD (валидно в Rich Results Test, schema = видимому тексту)
- `WebSite` + `Organization` — на всех страницах (имя «Культура хоккея», `logo`, `sameAs`: канал + GitHub).
- `DefinedTermSet` + `DefinedTerm` — в словаре. **Статически** из `terms.json` (краулеры/LLM не исполняют JS — встроить разметку в HTML, не через fetch).
- `Article` — на `origins.html` (`headline/author/publisher/datePublished/dateModified/inLanguage/mainEntityOfPage`). Шаблон переиспользуем для будущих глав.
- `BreadcrumbList` — навигация (Главная → Раздел → Страница).

### D. GEO-гигиена
- Видимый `dateModified` на главе (origins) и ключевых страницах.
- Заметка в `CLAUDE.md`/контент-гайде: писать машиночитаемо, факты с источниками, самодостаточные секции с якорями-id.

## Чего НЕ делать / границы
- Не трогать живую логику словаря/истории так, чтобы сломать рендер (`app.js` удалён ранее — данные читаются страницами напрямую).
- Не менять схему данных и не расходить `data/` ↔ `docs/data/` (validate_data.py должен оставаться зелёным).
- Не писать контент главы 2 — ждём markdown от исследователя (Трек 2).
- FAQ-rich НЕ закладываем (Google убрал в 05.2026) — Q&A держим ради цитируемости LLM, не ради звёздочек.

## Грабли (учесть)
- После любого деплоя/правок проверять прод, а не только локально.
- Schema обязана совпадать с видимым контентом — иначе Rich Results ругается.

## Definition of Done (Трек 1)
- [ ] У каждой страницы уникальные title/description, canonical, OG/Twitter-превью.
- [ ] `robots.txt` (AI-краулеры разрешены) + `sitemap.xml` на проде.
- [ ] JSON-LD: WebSite/Organization везде, DefinedTerm в словаре, Article на origins, BreadcrumbList — валидны в Rich Results Test.
- [ ] Видимый `dateModified` на главе.
- [ ] CLAUDE.md + CHANGELOG (v0.9) обновлены.
- [ ] Передать PM: ссылку на прод + скрин/лог прохождения Rich Results Test.
