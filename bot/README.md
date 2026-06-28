# Telegram-бот хоккейного словаря

Поиск по той же базе `data/terms.json`, что и сайт. Пришли боту «xG», «корси» или «forecheck» — получишь карточку термина. При miss по словарю бот может предложить главу истории (`data/history.json`).

Бот: **@hockey_platform_bot**

## Запуск локально (Windows)

```powershell
cd Projects\hockey-platform\bot
pip install -r requirements.txt

# токен: создай файл .env рядом с bot.py
echo BOT_TOKEN=твой_токен_от_BotFather > .env

python bot.py
```

Остановка — `Ctrl+C`. Бот работает, пока запущен скрипт (polling, без сервера).

## Тесты (токен не нужен)

```powershell
python test_search.py
```

## Файлы

- `bot.py` — Telegram-логика (хендлеры, polling, inline, рубрика «В этот день»)
- `search.py` — поиск по базе + мост в историю, чистая логика без Telegram
- `calendar_feature.py` — рубрика «В этот день»: `parse_date`, `events_for_date`, карточка дня (чистая логика без Telegram; имя не `calendar.py`, чтобы не затенять stdlib)
- `test_search.py` — тесты поиска и `find_history_chapter`
- `test_calendar.py` — тесты `parse_date`/событий/формата
- `.env` — токен (в git не попадает)

Данные: словарь — `../data/terms.json` (+ `expert_review.json`), история — `../data/history.json`, календарь — `../data/calendar.json`.

## Inline-режим

Inline — это когда бота можно вызвать **в любом чате**, не открывая диалог с ним: набираешь `@hockey_platform_bot форчек` прямо в строке сообщения, и Telegram показывает карточки-подсказки. Тыкаешь нужную — она отправляется в текущий чат. Удобно поделиться объяснением термина с собеседником, не выходя из переписки.

### Как включить (один раз, в @BotFather)

1. Открой @BotFather → `/setinline`
2. Выбери @hockey_platform_bot
3. Задай placeholder, например: `термин или тема…`

Без этого шага inline работать не будет, даже если код на месте.

### Как пользоваться

- В любом чате набери `@hockey_platform_bot ` и термин (минимум 2 символа): `@hockey_platform_bot xG`
- Появятся карточки — выбери нужную, она уйдёт в чат.
- Если термина нет в словаре, но запрос похож на историческую тему («история хоккея», «кубок стэнли») — бот предложит карточку со ссылкой на статью.

### Частые грабли

- **Бот не появляется в подсказке** — inline не включён в BotFather (`/setinline`) либо Telegram ещё кэширует: подожди пару минут / перезапусти Telegram.
- **Показывает старые результаты** — у inline-ответов есть `cache_time` (до 5 мин) плюс кэш на стороне Telegram. Для проверки правок меняй текст запроса.
- **«Термин не найден»** — карточек нет ни по словарю, ни по истории; кнопка ведёт открыть бота в личке.

### Поведение в группах (privacy mode)

Чтобы бот не отвечал на каждое сообщение участников в группах, в @BotFather включён **privacy mode**: `/setprivacy` → бот → **Enable**. Тогда в группах бот видит только команды (`/start@bot`), ответы и упоминания себя; inline при этом работает везде (от privacy не зависит).

⚠️ Грабли: новая настройка privacy применяется только к группам, куда бот зашёл **после** изменения. В уже существующих чатах нужно удалить бота и добавить заново.

В коде дополнительно стоит защита: `handle_query` игнорирует сообщения «через бота» (`via_bot`), чтобы бот не реагировал на эхо собственных inline-карточек.

## Рубрика «В этот день в истории хоккея»

Историческая рубрика на курируемом календаре `../data/calendar.json` (ключ `MM-DD` → массив событий). Никаких внешних API/LLM в рантайме — бот просто читает JSON.

Как пользоваться:

- Кнопка **«📅 В этот день»** в `/start` — события на сегодня (таймзона **Europe/Moscow**, фикс. `+03:00`).
- Команда `/today` — то же, что кнопка.
- Команда `/day <дата>` — на произвольную дату: `/day 14 марта` или `/day 14-03`.
- Просто пришли дату текстом: `14 марта`, `2 января`, `02.01`, `14-03`. Бот распознаёт дату **до** словарного поиска и не засоряет `missing_queries.log`.
- Кнопка **«📅 Случайный день»** под карточкой.

Формат входа (`parse_date`): день-первым по русской конвенции (`14.03` = 14 марта). Понимает `DD месяц`, `DD.MM`, `DD-MM`, `DD/MM`, игнорирует регистр/ё и слова-обёртки («что было 2 января»). **Антиколлизия со словарём:** датой считается только явный паттерн (число + месяц-слово, либо строка целиком вида `DD.MM`/`DD-DD`); одиночные слова («март») и числа словарём не перехватываются как даты.

Схема события `calendar.json`:

```json
"03-23": [
  { "year": 1994, "text": "…", "cat": "Рекорд", "reg": "NHL", "conf": "high", "video": "https://…" }
]
```

- `cat`: Рождение / Гибель / Дебют / Рекорд / Матч / Турнир / Переход / Возвращение / Достижение / Организация
- `reg`: RU / NHL / INT / WORLD · `conf`: high / med · `video` (опц.): ссылка на момент → в карточке «🎥 Смотреть момент»
- На этом спринте показываем **все** события (включая `conf:med`) — данные курируемые; фильтр по `conf` — бэклог.
- Наполнение календаря и `video` — поток исследователя; коммит `calendar.json` пока ручной (авто-синк — бэклог).

## Деплой на VPS (спринт 3)

Первичная настройка, один раз:

```bash
# на VPS, под root или sudo
sudo useradd -r -m -d /opt/hockey-platform -s /bin/bash hockey
sudo -u hockey git clone https://github.com/ALTitushkin/hockey-platform /opt/hockey-platform
cd /opt/hockey-platform/bot
sudo -u hockey python3 -m venv venv
sudo -u hockey venv/bin/pip install -r requirements.txt
sudo -u hockey sh -c 'echo "BOT_TOKEN=новый_токен" > .env'
sudo cp ../deploy/hockey-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hockey-bot
journalctl -u hockey-bot -f   # проверить, что поднялся
```

Для автодеплоя (push в main → бот обновился):

1. На VPS: `ssh-keygen -t ed25519 -f deploy_key` (без пароля), публичный ключ → `~hockey/.ssh/authorized_keys`
2. Разреши пользователю hockey рестарт сервиса без пароля:
   `echo "hockey ALL=NOPASSWD: /usr/bin/systemctl restart hockey-bot" | sudo tee /etc/sudoers.d/hockey-bot`
3. В GitHub репо → Settings → Secrets → Actions: `VPS_HOST`, `VPS_USER=hockey`, `VPS_SSH_KEY` (приватный deploy_key)

## Лог запросов

Все запросы пишутся в `bot/queries.log` (дата + hit/miss + текст), ненайденные дублируются в `bot/missing_queries.log`. Раз в спринт логи разбираются (правило проекта) и чистятся.

Готовый список «чего не хватает в базе»:
`sort missing_queries.log | cut -f2 | sort | uniq -c | sort -rn`

## Важно

Токен никогда не коммитим. `.env` уже в `.gitignore`. После засветки токена — `/revoke` в @BotFather.
