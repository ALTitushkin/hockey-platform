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

## Лог ненайденных запросов

Всё, что бот не нашёл, копится в `bot/missing_queries.log` (дата + запрос).
Раз в пару недель: `sort missing_queries.log | cut -f2 | sort | uniq -c | sort -rn` — готовый список, чего не хватает в базе.

## Важно

Токен никогда не коммитим. `.env` уже в `.gitignore`. После засветки токена — `/revoke` в @BotFather.
