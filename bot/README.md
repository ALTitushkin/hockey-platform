# Telegram-бот хоккейного словаря

Поиск по той же базе `data/terms.json`, что и сайт. Пришли боту «xG», «корси» или «forecheck» — получишь карточку термина.

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

- `bot.py` — Telegram-логика (хендлеры, polling)
- `search.py` — поиск по базе, чистая логика без Telegram
- `test_search.py` — тесты поиска
- `.env` — токен (в git не попадает)

## Важно

Токен никогда не коммитим. `.env` уже в `.gitignore`.
