# 📚 Документация проекта «Культура хоккея»

Точка входа в проектную документацию. Сам **сайт** живёт в `../docs/` (GitHub Pages), **код** — в `../bot/`, `../tools/`, данные — в `../data/`. Здесь — только «как мы это строим».

**Что за проект:** образовательная хоккейная платформа (словарь EN→RU + история + бот). Обзор и архитектура — `../CLAUDE.md`.
**Живой статус проекта** ведётся в Obsidian-дашборде (у Саши). История версий — `../CHANGELOG.md`.

---

## 🗺 Навигация

### 📋 [planning/](planning/) — спринты
ТЗ каждого спринта и итоги. Начни с последнего.
- **[backlog.md](planning/backlog.md) — единый бэклог: сделано, дальше, ждёт владельца (с 25.10.2026 работаем потоком по нему)**
- ТЗ: [sprint_1](planning/sprint_1.md) · [2](planning/sprint_2.md) · [3](planning/sprint_3.md) · [4](planning/sprint_4.md) · [5](planning/sprint_5.md) · [6](planning/sprint_6.md) · [7](planning/sprint_7.md) · [8](planning/sprint_8.md) · [9](planning/sprint_9.md) — все закрыты, новый не открыт
- Ретро/итоги: [planning/results/](planning/results/) (sprint_1, 6, 7, 8, 9)

### 🎨 [design/](design/) — дизайн и концепт
- [ecosystem.md](design/ecosystem.md) — **карта экосистемы бренда (24.10.2026): треки, решения, роли**
- [content_strategy.md](design/content_strategy.md) — **стратегия каналов: два канала по географии, сетка рубрик, ФАРМ**
- [koncept_platforma.md](design/koncept_platforma.md) — концепт платформы
- [design_concept_s5.md](design/design_concept_s5.md) — утверждённый визуальный концепт (идентичность A «Учебник»)
- [design_brief.md](design/design_brief.md) · [design_brief_s5.md](design/design_brief_s5.md) — брифы дизайнеру
- [wordmark_spec.md](design/wordmark_spec.md) — спека вордмарка

### 📝 [content/](content/) — правила контента
- [content_guide.md](content/content_guide.md) — как наполнять базу терминов
- [rubricator_terms.md](content/rubricator_terms.md) — рубрикатор (уровни/профили/категории)
- [channel-announcement.md](content/channel-announcement.md) — черновик анонса бота в канал
- [channel_packaging.md](content/channel_packaging.md) — упаковка канала: аватар, описание, навигация
- Гайд «Родителям»: канон — [`../docs/parents/drafts/parents_guide.md`](../docs/parents/drafts/parents_guide.md), исследование — [research/parents_guide_research.md](content/research/parents_guide_research.md); `content/drafts/parents_guide_*_v1.md` — устаревшие черновики v1
- Канон истории (9 глав — все опубликованы, формат черновика): [`../docs/history/INDEX.md`](../docs/history/INDEX.md) *(лежит рядом с пайплайном сборки глав)*

### ⚙️ [process/](process/) — как работаем
- [ops_notes.md](process/ops_notes.md) — **операционка: грабли, VPS, деплой, ритуал разбора логов, процесс главы**
- [team_process.md](process/team_process.md) — роли и разделение по чатам
- [architecture.md](process/architecture.md) — архитектурные решения и почему
- [documentation-standard.md](process/documentation-standard.md) — **стандарт ведения документации**
- [infra-audit.md](process/infra-audit.md) — аудит CI/VPS/деплоя + приоритеты фиксов
- [requirements-and-scaling.md](process/requirements-and-scaling.md) — **требования и триггеры масштабирования**
- [dev-audit.md](process/dev-audit.md) — аудит кода (bot/tools) + приоритеты

### 🔬 [research/](research/) — исследования
- [llm_options.md](research/llm_options.md) — выбор LLM для новостника · [news_network_research.md](research/news_network_research.md) · [platforms_community_research.md](research/platforms_community_research.md) · [data_products_research.md](research/data_products_research.md)

### 🤝 [handoff/](handoff/) — брифы-передачи
Готовые ТЗ PM → дев/исследователь по трекам спринтов (шаблоны для будущих задач).

---

## 🔗 Быстрые ссылки
- Сайт: https://altitushkin.github.io/hockey-platform/
- Репозиторий: https://github.com/ALTitushkin/hockey-platform
- Контекст для Claude: [`../CLAUDE.md`](../CLAUDE.md)
