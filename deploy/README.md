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
> `DEPLOY_ENABLED=true` с 30.08.2026 — пуш в `main` выкатывает код сам (сверено 17.10.2026: последний прогон — `test` ✅, `deploy` ✅).

> Бот живёт на **app-VPS** (`88.218.250.212`) в Docker, пользователь `deploy`, каталог `/opt/hockey-platform`.
> Long polling — домен, TLS и Caddy не нужны.
> Старый стенд на личном VPS `185.39.19.83` (systemd) снесён 30.08.2026, юнит удалён из репо 17.10.2026.

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

> Деплой упал — в логе GitHub Actions только причина: строки самого бота («Не читается реестр…», «Бот запущен…») и **имена** классов исключений, без их текста. Репозиторий публичный, лог Actions виден всем, а трейсбек может нести чужое сообщение или данные запроса. Полные логи — на сервере: `docker compose logs --tail 100 bot`.

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

## Алерт о падении

`deploy/watchdog.sh` раз в 10 минут проверяет два сервиса: `hockey-bot` (бот словаря, токен `BOT_TOKEN` из `.env`) и `hockey-news` (новостник, `NEWS_BOT_TOKEN` из `news/.env`). Для каждого: контейнер в состоянии `running` и токен отвечает на `getMe`. Если нет — сообщение владельцу от **отдельного служебного бота** (алерт на боевом токене промолчал бы ровно тогда, когда сломан боевой токен; бот словаря публичный — служебное в него не пишем). Пока сервис лежит, повтор — не чаще раза в час; когда поднялся — одно «🟢 снова работает». Флаги — `.watchdog-down-<контейнер>`.

Служебный бот только отправляет: входящие он не читает, сообщения шлёт одному `WATCHDOG_CHAT`. Кто-то другой может нажать у него /start, но ничего не получит.

Включение — один раз:

```
# 1. @BotFather → /newbot → служебный бот, взять токен. Написать ему /start.
#    Токен в чат с агентом НЕ вставлять — сразу в файл на сервере, из своего терминала.

# 2. На app-VPS под deploy:
cd /opt/hockey-platform
printf 'WATCHDOG_TOKEN=%s\nWATCHDOG_CHAT=%s\n' '<токен>' '<chat_id>' > .watchdog.env
chmod 600 .watchdog.env
bash deploy/watchdog.sh        # обе строки «ок»

# 3. Таймер (cron на сервере нет):
sudo cp deploy/hockey-watchdog.service deploy/hockey-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now hockey-watchdog.timer
systemctl list-timers hockey-watchdog.timer

# 4. Проверка по-настоящему — непроверенный алерт не считается сделанным:
docker stop hockey-news; sudo systemctl start hockey-watchdog.service   # → 🔴
docker start hockey-news; sudo systemctl start hockey-watchdog.service  # → 🟢
```

Откат: `sudo systemctl disable --now hockey-watchdog.timer` и удалить оба юнита из `/etc/systemd/system/`.

Сторож живёт на том же сервере и о падении самого VPS не сообщит — это фаза 2: внешний «пульс» (healthchecks.io), см. `project/planning/backlog.md`.

`.watchdog.env` и флаги `.watchdog-down-*` — в `.gitignore`, `git pull` их не трогает.
