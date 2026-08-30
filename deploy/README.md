# Деплой и восстановление хоккей-бота

> [!done] 30.08.2026 — переезд выполнен, документ описывает фактическое состояние
> Бот живёт на **app-VPS** в контейнере `hockey-bot`. Старый systemd-стенд на `185.39.19.83` остановлен, `disabled`, юнит-файл и `.env` удалены — отката нет и не нужно.
>
> Проверено по факту, а не по намерению: healthcheck-строка `Бот запущен v0.7 (@hockey_platform_bot), терминов: 62, глав истории: 9, дней календаря: 127`; ни одного `409 Conflict`; `getWebhookInfo` → `pending_update_count: 0` (апдейты забираются, polling идёт); токена в логах контейнера нет; `.env` — `600 deploy:deploy`, без инлайн-комментариев; том `runtime/` под UID 1000. Живой ответ бота в Telegram подтверждён.
>
> Порядок был именно такой: **сначала погашен старый инстанс, потом поднят новый.** Обратный порядок дал бы 409 Conflict — два потребителя `getUpdates` на один токен, и ломается это тихо.
>
> Логи спроса со старого стенда сняты в `runtime-archive-old-vps/` (2 строки — подтверждают вывод гейта логов S8 о том, что спроса нет).
>
> ⚠️ **Остался ручной шаг:** repo variable `DEPLOY_ENABLED` всё ещё `false`. Пока он такой, пуш в `main` прогонит тесты, но **не выкатит код** — прод останется на коммите первого разворота. Переключить в `true` в Settings → Secrets and variables → Actions → Variables.

> Бот живёт на **app-VPS** (`88.218.250.212`) в Docker, пользователь `deploy`, каталог `/opt/hockey-platform`.
> Long polling — домен, TLS и Caddy не нужны.
> Старый стенд: личный VPS `185.39.19.83`, systemd-юнит (`hockey-bot.service` — архив, см. низ файла).

## Как работает деплой

Push в `main` с изменениями в `bot/**`, `data/**`, `Dockerfile`, `docker-compose.yml`, `deploy/**` →
GitHub Actions: job `test` (ruff → `validate_data.py` → `test_search.py` + `test_calendar.py`) →
job `deploy` (только если repo variable `DEPLOY_ENABLED=true`) → SSH → `bash deploy/deploy.sh`.

`deploy.sh` делает `git pull --ff-only`, `docker compose up -d --build`, ждёт 8 секунд и проверяет, что бот действительно поднялся. Проверка ветвится по факту пересоздания контейнера: пересоздан — требуется свежая строка «Бот запущен» в логах; тот же самый (образ не изменился) — достаточно `running` без цикла рестартов. Не сошлось — `exit 1`, workflow краснеет.

**Healthcheck живёт в скрипте, а не в workflow** — поэтому ручной деплой защищён тем же гейтом.

### Доступы CI (Settings → Secrets and variables → Actions)

| Имя | Тип | Значение |
|---|---|---|
| `VPS_HOST` | secret | `88.218.250.212` |
| `VPS_USER` | secret | `deploy` |
| `VPS_SSH_KEY` | secret | приватный ключ пары `github-actions-hockey` |
| `DEPLOY_ENABLED` | variable | `true` включает выкат |

Ключ **свой на этот репозиторий** — в `authorized_keys` юзера `deploy` он подписан `github-actions-hockey`, рядом лежат отдельные `prizedrawing-ci` и `investmanager-ci`. Общий CI-ключ на три проекта не заводим: утечка секрета одного репозитория дала бы деплой во все.

> ⚠️ **Грабля 30.08.2026, стоила отдельного разбора.** Секреты в этом репозитории остались от Sprint 3, когда бот деплоился на личный сервер `185.39.19.83`. Workflow переписали под app-VPS 04.08, а секреты — нет. Не заметили, потому что `DEPLOY_ENABLED` стоял `false` и шаг `deploy` **ни разу не выполнялся**: 34 зелёных прогона подряд означали только пройденные тесты.
> **Урок:** «зелёный CI» и «рабочий деплой» — разные утверждения, если деплой под флагом. Флаг, выключенный «на время переезда», делает половину пайплайна непроверяемой; включать его надо в тот же заход, что и переезд, а не «потом».
> Значения секретов GitHub обратно не отдаёт — диагностировать можно только перезаписью.

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

`hockey-bot.service` — юнит для личного VPS. Окно отката (до 09.08.2026) **истекло, а переезд к тому моменту не состоялся** — бот по-прежнему работает на старом стенде. Дата в этом абзаце провисела просроченной до 30.08.2026; держать «окно» без даты пересмотра — тот же класс ошибки, что конфиг, которого нет в репо.

⚠️ **Отката больше нет: сервер `185.39.19.83` гасят.** Он заблокирован из России с 19.08.2026, VPN с него переехал, и хоккей-бот — единственное, что удерживает машину включённой. Значит переключение делается в один заход, без запасной площадки:

```
# 1. Погасить старый инстанс ПЕРВЫМ (иначе 409 Conflict)
ssh root@185.39.19.83            # нужен туннель, IP заблокирован из РФ
systemctl stop hockey-bot
systemctl disable hockey-bot
ps aux | grep bot.py             # должна остаться только строка grep

# 2. Тем же заходом забрать логи спроса — они существуют только здесь
cat /opt/hockey-platform/bot/queries.log
cat /opt/hockey-platform/bot/missing_queries.log

# 3. Убрать установку
rm /opt/hockey-platform/bot/.env
rm /etc/systemd/system/hockey-bot.service
systemctl daemon-reload
```

Дальше — подъём на app-VPS по разделу «Поднять с нуля» выше и `DEPLOY_ENABLED=true`.
