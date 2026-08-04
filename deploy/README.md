# Деплой и восстановление хоккей-бота

> Бот живёт на **app-VPS** (`88.218.250.212`) в Docker, пользователь `deploy`, каталог `/opt/hockey-platform`.
> Long polling — домен, TLS и Caddy не нужны.
> Старый стенд: личный VPS `185.39.19.83`, systemd-юнит (`hockey-bot.service` — архив, см. низ файла).

## Как работает деплой

Push в `main` с изменениями в `bot/**`, `data/**`, `Dockerfile`, `docker-compose.yml`, `deploy/**` →
GitHub Actions: job `test` (ruff → `validate_data.py` → `test_search.py` + `test_calendar.py`) →
job `deploy` (только если repo variable `DEPLOY_ENABLED=true`) → SSH → `bash deploy/deploy.sh`.

`deploy.sh` делает `git pull --ff-only`, `docker compose up -d --build`, ждёт 8 секунд и грепает логи контейнера на строку «Бот запущен». Нет строки — `exit 1`, workflow краснеет, деплой не считается успешным.

**Healthcheck живёт в скрипте, а не в workflow** — поэтому ручной деплой защищён тем же гейтом.

## ⚠️ Правило одного инстанса

Два потребителя `getUpdates` на один токен → Telegram отдаёт **409 Conflict**, бот начинает «мигать», и ломается это тихо. Перед любым стартом на новом месте убедиться, что старый экземпляр мёртв:

```
ssh root@185.39.19.83
systemctl stop hockey-bot
systemctl disable hockey-bot
ps aux | grep bot.py        # должна остаться только строка самого grep
```

Никаких `replicas`, никакого `docker compose scale`.

## Поднять с нуля на чистом сервере

```
# 1. Код
sudo mkdir -p /opt/hockey-platform
sudo chown 1000:1000 /opt/hockey-platform
git clone https://github.com/ALTitushkin/hockey-platform.git /opt/hockey-platform
cd /opt/hockey-platform

# 2. Каталог логов спроса. UID 1000 = пользователь app внутри контейнера,
#    иначе бот не сможет писать в том.
mkdir -p runtime
chown -R 1000:1000 runtime

# 3. Секреты. Строка BOT_TOKEN=... ЦЕЛИКОМ, без пробелов вокруг «=»,
#    без инлайн-комментария в конце строки.
cat > .env <<'ENV'
BOT_TOKEN=<токен из BotFather>
ENV
chmod 600 .env

# 4. Старт
docker compose up -d --build
docker compose logs --tail 30 bot
```

В логах должна быть строка «Бот запущен v0.7 (@hockey_platform_bot), терминов: …».

**После первого старта посмотреть логи глазами на предмет токена** — грабля 19.07.2026: `httpx` на INFO печатал полный URL Telegram API вместе с токеном. В коде заглушено, но проверять надо по факту, а не по коду.

## Частые операции

| Задача | Команда |
|---|---|
| Логи | `docker compose logs -f bot` |
| Рестарт | `docker compose restart bot` |
| Ручной деплой | `bash /opt/hockey-platform/deploy/deploy.sh` |
| Логи спроса | `cat /opt/hockey-platform/runtime/queries.log` |
| Очистить логи спроса (после разбора) | `> runtime/queries.log && > runtime/missing_queries.log` |
| Остановить | `docker compose down` |

## Отладка

| Симптом | Причина |
|---|---|
| Контейнер стартует и сразу падает | `.env`: нет строки целиком или инлайн-комментарий в значении |
| `Permission denied` на `runtime/` | Каталог не принадлежит UID 1000 → `chown -R 1000:1000 runtime` |
| Бот отвечает через раз, дублирует ответы | Жив второй инстанс → 409 Conflict, см. «Правило одного инстанса» |
| `Temporary failure in name resolution` | DNS хоста. Проверить `ping 8.8.8.8` против `ping api.telegram.org`; см. `project/process/ops_notes.md` |
| Процесс стартует, но команды не работают | PTB запинен `<22`: версия 22.x ломает `run_polling` |
| Actions зелёные, а на проде старый код | `DEPLOY_ENABLED` ещё `false`, или пуш не попал в path-фильтр |

## Данные и бэкап

Бот стейтлесс: реестры (`data/terms.json`, `history.json`, `calendar.json`) лежат в git, отдельного бэкапа не требуют. Единственное, что живёт только на сервере, — логи спроса в `runtime/`; они разовые, разбираются раз в спринт и чистятся.

## Архив: старый systemd-стенд

`hockey-bot.service` — юнит для личного VPS, оставлен до конца окна отката (**до 09.08.2026**), потом удаляется вместе с установкой:

```
ssh root@185.39.19.83
rm /opt/hockey-platform/bot/.env
rm /etc/systemd/system/hockey-bot.service
systemctl daemon-reload
```
