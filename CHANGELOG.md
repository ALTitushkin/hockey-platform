# Changelog

## [0.12.0] — 2026-06-28

### Добавлено (Sprint 7 · глава 4 опубликована)
- `docs/history/tarasov-system.html` — глава 4 «Тарасов и большая система» (метод советского хоккея), собрана `tools/build_chapter.py`: 6 разделов с id-якорями (`engineer`, `five-as-one`, `year-round`, `cross-training`, `legends-vs-facts`, `tandem`), 2 fact-box, таймлайн (8 дат), «Источники» (5 ссылок с описаниями), nav-footer (← С чистого льда; summit-1972 задизейблена), видимый `dateModified`
- JSON-LD `Article` (даты `2026-06-28T12:00:00+03:00`) + `BreadcrumbList`
- `data/history.json` и `docs/data/history.json`: `tarasov-system` → `published:true`, `url`, `summary`, `sections[]`; `era`(soviet)/порядок/`kicker` не тронуты
- `sitemap.xml` — 7 URL (4 опубликованные главы)

### Изменено (тулинг)
- `tools/build_chapter.py`: парсер «Источники» принимает описание после ссылки (`[текст](url) — описание`) и рендерит его в карточке источника

## [0.11.3] — 2026-06-28

### Изменено (Sprint 7 · Трек C — дубль названия в ru_slang)
- `data/terms.json` (оба зеркала): убран `ru_slang`, дублирующий само название карточки — Пятак/Слот («пятак») и Тафгай («тафгай») → `null`. Поиск по «пятак»/«слот»/«тафгай» сохранён (через `ru`). Правило: токен `ru_slang`, совпадающий с `ru` или его `/`-вариантом, чистится
- `bot/test_search.py`: пример термина-со-сленгом в тесте подписи переведён на `форчек` (не дубль)

## [0.11.2] — 2026-06-28

### Изменено (Sprint 7 · Трек C — чистка MT-сленга + ясность подписи)
- `data/terms.json` (оба зеркала): вычищены кальки и не-сленг из `ru_slang`:
  - A (кальки, юзер-подтверждено): Шайба («кругляш/таблетка»), Клюшка («палка») → `null`
  - B (не-сленг): РХЛ («НМХЛ» → уже алиас в `abbr`), Проброс/Выход из зоны (дубли термина), Офсайд («вне игры» — перевод) → `null`; Хват — «левый/правый хват» перенесены в `abbr` (поиск), `ru_slang` → `null`
  - C (по решению PM, без эксперта): Чекер («гасильщик» — «такого нет») → `null`; Тафгай (убран «полицейский», оставлен «тафгай»)
- `bot/search.py`: подпись карточки `💬 У нас говорят:` → `💬 Сленг:`; пустой `ru_slang` строку не показывает
- `bot/test_search.py`: кейсы на подпись «Сленг:», скрытие пустого `ru_slang`, и что затронутые термины по-прежнему находятся (через `ru`/`abbr`)

### Не тронуто (ждёт выверки эксперта СКА)
- rebound «добивание, подбор», snap-shot «подщёлкивание»; `expert_review.json` (рыбачок/поплавок/сыр)

## [0.11.1] — 2026-06-28

### Исправлено (приёмка S7 Трек B)
- `bot/search.py`: нечёткие совпадения подключаются только при отсутствии точных/префиксных — запрос «нмхл» больше не тащит ложную карточку «НХЛ» (буквенный ratio 0.857 ≥ порога). Точный/префиксный/typo-поиск не затронуты
- `data/terms.json` (оба зеркала): термину `handedness` добавлены алиасы «левый хват» / «правый хват» (`ru_slang`) — прямой запрос даёт карточку, а не подсказку «• хват»
- `bot/test_search.py`: кейсы на новые термины и анти-ложные совпадения (`нмхл` → только `rhl`)

## [0.11.0] — 2026-06-28

### Добавлено (Sprint 7 · Трек B — пополнение базы из лога спроса)
- 13 терминов (verified, с источником) по решению PM (`s7_pm_decision_base.md`): Хват (handedness), Силовой приём/Хит (body-check, алиасы «хит»/«силовой»), Драфт (draft), Штраф-бокс (penalty-box), Подправление (deflection), Один в один (1-on-1), Типы защитников (defenseman-types) + кластер «Лиги»: НХЛ, КХЛ, МХЛ, ВХЛ, ECHL, РХЛ (бывш. НМХЛ)
- 2 новые категории: `basics` («Базовое / техника») и `org` («Лиги / организации»); кластер `leagues` в `clusters.json` (оба зеркала)
- `tools/add_term.py` пропатчен под схему v2.0: категории `basics/org`, полный набор полей (`profiles/cluster/see_also/anchor/source/added/status`), пакетный режим `--batch`

### Исправлено / полировка
- `tools/validate_data.py`: проверка обязательного `status` ∈ {verified, unverified}
- `data/terms.json` (оба зеркала): проставлен `status: verified` 4 старым записям (`puck`/`hockey-stick`/`forward`/`checker`) — были без поля
- `bot/bot.py`: счётчик терминов по файлам (вариант 1) → «терминов: 62 (+3 на выверке)», устойчиво к отсутствию `status`
- `bot/search.py`: метки новых категорий `basics`/`org` в карточке (иначе показывало сырой ключ)
- `bot/calendar_feature.py`: `parse_date` распознаёт «сегодня/завтра/вчера» (Europe/Moscow) — полировка Трека A
- `CLAUDE.md`: категории `basics/org` в схеме термина
- `docs/dictionary.html`: статический `DefinedTerm`-блок (SEO, S6) пересобран `build_seo.py` под выросшую базу (49 → 62 термина); `sitemap.xml` lastmod обновлён

### Отложено (бэклог S8)
- «Подкидка» (формат не уточнён); мягкая обработка несуществующих дат («56 мая»)
- Решение PM по НМХЛ→РХЛ: лига официально преобразована в РХЛ (17.04.2026) — карточка ведёт именем **РХЛ**, «НМХЛ» заведён алиасом (`abbr` + `ru_slang`); оба запроса находят карточку

## [0.10.0] — 2026-06-28

### Добавлено (Sprint 7 · Трек A — бот «📅 В этот день»)
- Историческая рубрика в боте на курируемом календаре. `data/calendar.json` (ключ `MM-DD` → массив событий; 101 дата, 119 событий). Только в `data/` — фича бот-онли, сайт календарь не читает, паритет-проверка не нужна (validate не трогаем)
- `bot/calendar_feature.py` (чистая логика, без Telegram; имя ≠ `calendar.py`, чтобы не затенять stdlib): `load_calendar()` с валидацией, `events_for_date()` (сорт по году), `parse_date()` (день-первым: «14 марта»/«2 янв»/«02.01»/«14-03»/«14/03», игнор регистра/ё/слов-обёрток), `format_day_card()` (HTML), `today_mmdd()` (Europe/Moscow, фикс `+03:00`), `random_day()`
- `bot/bot.py`: кнопка «📅 В этот день» в `/start` (`callback_data=onthisday:today`) + `CallbackQueryHandler`; команды `/today` и `/day <дата>`; кнопка «📅 Случайный день». В `handle_query` дата распознаётся `parse_date()` **до** словаря и не пишется в `missing_queries.log`. Антиколлизия: датой считается только явный паттерн (число+месяц-слово или строка целиком `DD.MM`/`DD-DD`); одиночные слова/числа → словарь
- Карточка: «📅 <b>14 марта</b> в истории хоккея», по событию `<b>{год}</b> — {текст}` + метка `cat` (эмодзи), при `video` → «🎥 Смотреть момент»; пустая дата → дружелюбная заглушка (не падение)
- `bot/test_calendar.py` (без токена): `parse_date` на валидных/мусорных/одиночных, `events_for_date` + сортировка, пустая дата, формат карточки
- Лог запуска бота → `v0.7`, «терминов: 49 (+3 на выверке), глав истории: 9, дней календаря: 101» (заодно кэрриовер-фикс `52` → `49 (+3)`)
- `bot/README.md` и `CLAUDE.md`: команды, формат `calendar.json`, таймзона

### Примечания
- `conf`-политика S7: показываем все события (включая `med`) — фильтр по `conf` в бэклоге
- Не входит (бэклог S8+): авто-синк `calendar.json`, scheduled task «саммари дня», inline-режим для дат, фильтры по `conf`/`reg`. Наполнение календаря и `video` — поток исследователя
- `test_calendar.py` + `test_search.py` зелёные; PTB-пин `<22` не трогали

## [0.9.3] — 2026-06-20

### Добавлено (Sprint 6 · Трек 2 — глава 3 опубликована)
- `docs/history/soviet-origins.html` — глава 3 «С чистого льда» (рождение советского хоккея), свёрстана `tools/build_chapter.py`: 6 разделов с id-якорями (`country-without-hockey`, `russkiy-stil`, `bobrov-tarasov-chernyshev`, `stockholm-1954`, `cortina-1956`, `how-so-fast`), 3 fact-box, таймлайн (4 даты), «Источники» (8 ссылок), nav-footer (← Золотой век Канады; tarasov-system задизейблена), видимый `dateModified`
- JSON-LD `Article` (`datePublished`/`dateModified` = `2026-06-20T12:00:00+03:00`, сразу ISO) + `BreadcrumbList`
- `data/history.json` и `docs/data/history.json`: `soviet-origins` → `published:true`, `url`, `summary` (из «Краткого резюме»), `sections[]`; порядок/era(`soviet`)/kicker не тронуты
- `sitemap.xml` — 6 URL (3 опубликованные главы)

### Исправлено (Трек D — deep-link-якоря)
- `docs/style.css` (главы) и `docs/dictionary.html` (липкая шапка): `scroll-margin-top: 80px` заголовкам с id и карточкам `.term`, `scroll-behavior: smooth` — якорь больше не прячется под верхним отступом/липкой шапкой. Проверено на `#russkiy-stil` и `#rocket-richard`
- Даты Article на `origins`/`golden-age` уже в полном ISO с TZ (из v0.9.2) — 4 warning Rich Results сняты ещё там

### Примечания
- Текст главы принят контентом и не переписывался (builder распарсил готовый markdown)
- `validate_data.py` зелёный; `data/ ↔ docs/data/` идентичны

## [0.9.2] — 2026-06-19

### Исправлено (Rich Results · даты Article)
- `Article` JSON-LD на `origins.html` и `golden-age-canada.html`: `datePublished`/`dateModified` переведены в полный ISO 8601 с поясом Europe/Moscow (`…T12:00:00+03:00`) — убирает warning Rich Results про «date without time». Заодно так же нормализованы `og:article:*_time`. Видимая дата «Обновлено: …» не менялась (остаётся date-only в `<time datetime>`)
- `tools/build_chapter.py` — вынесен в репо как переиспользуемый сборщик главы из markdown-черновика (по шаблону `origins.html`): формат ISO-дат заложен в `iso()`, видимая дата — через `human_date()`. Будущие главы сразу с чистыми датами; под новую главу меняется только блок `CONFIG`
- Только `docs/` + `tools/` — `data/`/`bot/` не тронуты, автодеплой бота не триггерится

## [0.9.1] — 2026-06-19

### Добавлено (Sprint 6 · Трек 2 — глава 2 опубликована)
- `docs/history/golden-age-canada.html` — глава 2 «Золотой век Канады: первые суперзвёзды и Большая шестёрка», свёрстана по шаблону `origins.html`: breadcrumb (Главная › История › Золотой век Канады), chapter-label «Глава 2», 6 разделов h2 с id-якорями (`original-six`, `montreal-vs-toronto`, `howie-morenz`, `rocket-richard`, `richard-riot-1955`, `gordie-howe`), 3 fact-box, таймлайн (7 дат), блок «Источники» (9 ссылок), nav-footer (← origins; soviet-origins задизейблена), видимый `dateModified`
- JSON-LD на главе: `Article` (`datePublished`/`dateModified` = 2026-06-19, `author`/`publisher` = Организация с `logo`, `inLanguage`=ru, `mainEntityOfPage`) + `BreadcrumbList`
- `data/history.json` и `docs/data/history.json`: `golden-age-canada` → `published:true`, `url`, `summary` (из «Краткого резюме»), `sections[]` по 6 якорям; порядок/era/kicker не тронуты
- `sitemap.xml` пересобран `build_seo.py` — теперь 5 URL (2 опубликованные главы)

### Примечания
- Текст главы принят контентом и не переписывался; вёрстка распарсила готовый markdown. Минор-правка по ТЗ: «Монреального форума» → «Монреальского форума» (2×)
- `validate_data.py` зелёный; `data/ ↔ docs/data/` идентичны

## [0.9.0] — 2026-06-19

### Добавлено (Sprint 6 · Трек 1 — SEO / AI-SEO фундамент)
- Технический SEO на всех 4 страницах (`index`/`dictionary`/`history`/`history/origins`): `<link rel="canonical">` (абс. URL; у главной — корень), Open Graph + Twitter Card (`summary_large_image`, картинка `logo.png`), приведена иерархия заголовков к одному `<h1>` на страницу
- `<h1>` на главной (был только SVG-вордмарк) — visually-hidden, для семантики/SEO
- JSON-LD `Organization` + `WebSite` — статически в `<head>` каждой страницы (имя «Культура хоккея», `logo`, `sameAs`: канал + GitHub)
- JSON-LD `BreadcrumbList` — на словаре, индексе истории и главе
- JSON-LD `DefinedTermSet` + 49 `DefinedTerm` — в `dictionary.html` **статически** (не через fetch: краулеры/LLM не исполняют JS); `name`=рус, `alternateName`=англ+сокращения, `description`=определение
- JSON-LD `Article` на `origins.html` (`headline`/`author`/`publisher`/`datePublished`/`dateModified`/`inLanguage`/`mainEntityOfPage`) + видимый `dateModified` («Обновлено: 13 июня 2026»)
- `docs/robots.txt` — разрешены AI-краулеры (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, Applebot-Extended, OAI-SearchBot) + обычные; строка `Sitemap:`
- `docs/sitemap.xml` — страницы + только `published:true` главы (сейчас `origins`), с `lastmod`
- `tools/build_seo.py` — генератор: пересобирает `sitemap.xml` и инжектит `DefinedTerm` в словарь между маркерами `SEO:DEFINEDTERMS`. Читает только `data/`, без зависимостей (по образцу `validate_data.py`)
- `CLAUDE.md`: раздел «SEO / AI-SEO (GEO)» + правило GEO-гигиены контента для контент/research-чатов

### Изменено
- `origins.html`: дублирующий `<h1>Хоккейный словарь</h1>` в шапке-бренде понижен до `<p class="site-name">` (единственный `<h1>` = заголовок главы)

### Примечания
- Schema везде совпадает с видимым текстом; все блоки JSON-LD проходят `json.loads`. Финальная валидация — Rich Results Test по прод-URL после деплоя
- FAQ-rich намеренно не закладывали (Google убрал FAQ-сниппеты 05.2026) — Q&A держим ради цитируемости LLM
- `data/ ↔ docs/data/` не трогали; `validate_data.py` зелёный
- Трек 2 (глава «Золотой век Канады») — отдельно, чат-исследователь; дев верстает по готовому markdown

## [0.8.0] — 2026-06-14

### Добавлено (Слой B · вёрстка под концепт S5, направление A «Учебник»)
- IA Шаг 1: новый лёгкий `docs/index.html` — ответ-вход (гибрид: `quick_answers.json` сверху + Fuse.js fallback по терминам и главам истории) + 4 карточки-входа; счётчики (терминов/глав) тянутся из данных, не хардкод
- `docs/dictionary.html` — словарь (стиль A) на `terms.json` + `clusters.json`: три независимые оси фильтров (Уровень/Профиль/Категория), вид «Кластеры ⇄ A→Z», «Вне кластеров» для терминов без группы, карточки с `see_also`/`anchor`/слотом визуала (схема/видео), мобильный drawer «Фильтры (N)»
- `docs/history.html` — индекс глав из `history.json`: группировка по эрам, `published` → метка «Скоро», ссылки на страницы глав; deep-link на разделы (`origins.html#<section-id>`)
- `history.json`: синхронизирован с каноном `docs/history/INDEX.md` (v0.2) — 9 глав, `id`/`title`/`era`/порядок/`kicker` из файла; опубликована глава 1 `origins`, главы 2–9 — `published:false` (тизеры из канон-описаний, текст пишет research-чат)
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
