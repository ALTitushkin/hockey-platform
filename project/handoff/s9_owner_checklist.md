# Чек-лист владельца · Sprint 9

> **Кому:** Саша · **Дата:** 02.08.2026
> Всё, что нельзя сделать за тебя: BotFather, ssh, GitHub Secrets, коммиты, приёмка.
> Порядок сверху вниз. Не перепрыгивать — шаги 8–10 в неправильном порядке ломают прод.

---

## БЛОК 0 · Прямо сейчас (~10 минут)

### Шаг 1 — закоммитить документы спринта

PowerShell, команды по одной (`&&` в PS не работает):

```
cd D:\MyFolder\Projects\hockey-platform
git add project/planning/sprint_8.md project/planning/sprint_9.md project/planning/results/sprint_8_results.md project/handoff/s9_dev_migration.md project/handoff/s9_research_canada-cup.md project/handoff/s9_owner_checklist.md
git commit -m "docs(pm): S8 закрыт красным; S9 — переезд бота на app-VPS; брифы дева и исследователя"
git push
```

Бота это не передеплоит — CI фильтрует пути, `project/**` не в фильтре.

### Шаг 2 — запустить диагностику

Двойной клик по `D:\MyFolder\ops\hockey-bot-diag.cmd` (или из cmd). Скрипт ничего не меняет, только читает. Отчёт ляжет рядом: `ops\hockey-bot-diag.log`.

### Шаг 3 — прислать отчёт в чат

Открыть `.log`, скопировать целиком, вставить сюда. Токен там не печатается — только его длина и ответ Telegram.

---

## БЛОК 1 · Оживить бота

Дальше — по тому, что покажет отчёт. Найди в нём блок `### token check via getMe`.

### Ветка A — `"ok":false ... 401 Unauthorized` → токен отозван

Самый вероятный случай.

**4A.1.** В Telegram: `@BotFather` → `/mybots` → `@hockey_platform_bot` → `API Token`. Если токена нет или он не работает — `Revoke current token`, получить новый. Скопировать целиком.

**4A.2.** Прописать на сервере:

```
ssh root@185.39.19.83
nano /opt/hockey-platform/bot/.env
```

В файле строка должна быть **целиком**, без пробелов вокруг `=` и без комментария в конце строки:

```
BOT_TOKEN=1234567890:AA...
```

Сохранить: `Ctrl+O`, `Enter`, `Ctrl+X`.

**4A.3.** Рестарт и проверка:

```
systemctl restart hockey-bot
journalctl -u hockey-bot -n 20 --no-pager
```

Ищем строку **«Бот запущен»**. Если её нет — не рестартить по кругу, а прислать вывод сюда.

**4A.4.** Проверить в Telegram: `/start`, любой термин, `/today`.

**4A.5.** Новый токен положить в GitHub Secrets, если он там дублируется (Settings → Secrets and variables → Actions). И записать себе: этот токен через несколько дней поедет на app-VPS.

### Ветка B — сервис не `active` (в отчёте `inactive` / `failed`)

```
ssh root@185.39.19.83
systemctl start hockey-bot
systemctl status hockey-bot --no-pager -l
journalctl -u hockey-bot -n 40 --no-pager
```

Дополнительно посмотри в отчёте блок `### oom and kernel`: если там есть `Killed process` — сервер выжрал память (1 ГБ на бота + VPN + GitSync). Это ровно тот аргумент, из-за которого мы переезжаем. Вывод — в чат.

### Ветка C — сервис `active`, но в логах нет «Бот запущен»

Известная грабля: процесс стартует и тихо выходит.

```
ssh root@185.39.19.83
/opt/hockey-platform/bot/venv/bin/pip show python-telegram-bot | head -3
```

Версия должна быть `21.x`. Если `22.x` — это причина, чиним пином. Вывод — в чат.

### Ветка D — DNS не резолвится ✅ ЭТО НАШ СЛУЧАЙ (подтверждено 02.08, 20:56)

**Что показал отчёт:**
- `httpx.ConnectError: [Errno -3] Temporary failure in name resolution` — бот не может преобразовать `api.telegram.org` в IP. Падает на `get_me()` при старте, systemd поднимает его каждые 10 секунд, и он падает снова: `activating (auto-restart)`.
- `curl` из той же сессии тоже не ответил ничего — **ломается весь сервер, а не бот**.
- Токен цел: `.env` на месте, права `600`, длина 46 — норма. `getMe` пустой не потому, что 401, а потому что до Telegram не дошли.
- Памяти хватает (218 МБ свободно + 1 ГБ swap), диска 14 ГБ, OOM-killer молчит.

**✅ ИНЦИДЕНТ ЗАКРЫТ 04.08.2026, 08:19 UTC.** Бот в `active (running)`, в логе «Бот запущен v0.7 (@hockey_platform_bot), терминов: 62, глав истории: 9, дней календаря: 127».

**Фактическая причина — перезагрузка сервера 01.08 в 19:48, а не VPN.** Версия про WireGuard оказалась мимо: `awg0` ни при чём. `/etc/resolv.conf` — симлинк на `/run/resolvconf/resolv.conf`, файл генерится при загрузке, а в источниках `resolvconf` не было ни одного `nameserver` (`base` и `tail` по 0 байт, `head` — только шапка с комментариями). До ребута DNS жил с апреля на том, что раздал интерфейс при установке. Первый ребут это стёр.

**Что сработало:** `printf '\nnameserver 1.1.1.1\nnameserver 8.8.8.8\n' >> /etc/resolvconf/resolv.conf.d/head` → `resolvconf -u` → `systemctl restart hockey-bot`. Записано в `ops_notes.md`.

**Диагностическая ценность:** `ping 8.8.8.8` шёл, `ping api.telegram.org` — нет. Это сразу отсекло сеть и провайдера и оставило только DNS.

Ниже — исходные шаги ветки, оставлены как рабочий образец разбора.

**D.1 · Понять, что именно сломано:**

```
ssh root@185.39.19.83
ls -l /etc/resolv.conf
cat /etc/resolv.conf
ping -c 2 8.8.8.8
ping -c 2 api.telegram.org
systemctl status systemd-resolved --no-pager | head -12
ip route
wg show
```

Как читать:

| Что видно | Диагноз |
|---|---|
| `ping 8.8.8.8` идёт, `ping api.telegram.org` — нет | Чистый DNS. Идти в D.2 |
| Не идёт ни то, ни другое | Сломана маршрутизация — копать WireGuard/iptables, D.2 не поможет |
| `resolv.conf` пустой или там только `127.0.0.53`, а `systemd-resolved` мёртв | Лёг локальный резолвер. D.2 |
| В `resolv.conf` адрес из VPN-подсети (`10.x`) | DNS увели в туннель, который не поднялся. D.2 как временная мера, потом чинить конфиг |

**D.2 · Временный фикс — вернуть боту связь:**

```
cp /etc/resolv.conf /root/resolv.conf.bak
rm -f /etc/resolv.conf
printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' > /etc/resolv.conf
getent hosts api.telegram.org
systemctl restart hockey-bot
journalctl -u hockey-bot -n 20 --no-pager
```

`getent` должен вернуть IP. В журнале ищем «Бот запущен». Бэкап в `/root/resolv.conf.bak` — если стало хуже, вернуть `cp /root/resolv.conf.bak /etc/resolv.conf`.

⚠️ Это заплатка. Если `resolv.conf` управляется `systemd-resolved` или `wg-quick`, её могут перезаписать при следующем рестарте — поэтому D.4 обязателен.

**D.3 · Проверить в Telegram:** `/start`, любой термин, `/today`.

**D.4 · Найти настоящую причину** (иначе повторится):
- Что менялось на сервере 01.08 — конфиги WireGuard, `DNS =` в `wg0.conf`, правила iptables, настройки x-ui.
- Вывод `wg show` и `ip route` — в чат, разберём вместе.

**Вывод для спринта.** Это не случайная поломка, а ровно тот риск, из-за которого мы переезжаем: публичный бот лёг от того, что рядом крутили личный VPN. Аргумент S9 подтверждён на практике — вписать в итоги спринта.

### Шаг 5 — записать причину

Когда бот заговорит: одной строкой в `project/process/ops_notes.md`, раздел «Грабли» — что было и как поняли. Это пункт DoD спринта, и это ровно то, что спасёт в следующий раз.

**Стартовый гейт S9 пройден, когда бот отвечает и причина известна.** До этого переезд не начинаем.

---

## БЛОК 2 · Переезд (после того, как бот жив)

Дев-часть (Dockerfile, compose, CI, deploy.sh) делаю я в чате по брифу `s9_dev_migration.md`. Ниже — только твои руки.

### Шаг 6 — выключить автодеплой на время переезда

GitHub → репо `hockey-platform` → Settings → Secrets and variables → Actions → вкладка **Variables** → создать `DEPLOY_ENABLED` = `false`.

Зачем: пока идёт переезд, случайный пуш не должен поднять второй экземпляр бота. Два бота на одном токене = Telegram 409, прод ломается тихо.

### Шаг 7 — забрать логи спроса со старого сервера

**До** любых остановок и сносов:

```
ssh root@185.39.19.83
cat /opt/hockey-platform/bot/queries.log
cat /opt/hockey-platform/bot/missing_queries.log
```

Скопировать оба вывода в чат (или в файл у себя). Это единственные данные о живых пользователях, второй копии нет.

### Шаг 8 — остановить старого бота

```
ssh root@185.39.19.83
systemctl stop hockey-bot
systemctl disable hockey-bot
ps aux | grep bot.py
```

Последняя команда должна показать только саму строку `grep`. Если видно `python bot.py` — процесс жив, дальше не идти.

**`.env` пока не удалять** — это окно отката.

### Шаг 9 — поднять на app-VPS

Только после шага 8. Команды дам точные, когда будут готовы Dockerfile и compose. Ориентировочно:

```
ssh deploy@88.218.250.212
cd /opt/hockey-platform
nano .env        (BOT_TOKEN=...)
docker compose up -d --build
docker compose logs --tail 30 bot
```

В логах — «Бот запущен». И **глазами проверить, что в логах нет токена** — та самая грабля 19.07.

### Шаг 10 — приёмка в Telegram

Живыми командами, не «наверное работает»: `/start` → поиск термина → `/today` → `/day 15.09` → несуществующая дата.

### Шаг 11 — включить автодеплой

GitHub → Variables → `DEPLOY_ENABLED` = `true`. Затем любой мелкий пуш в `bot/` → смотрим, что Actions зелёные и healthcheck прошёл.

### Шаг 12 — GitHub Secrets на новый хост

Settings → Secrets and variables → Actions → Secrets:

- `VPS_HOST` → `88.218.250.212`
- `VPS_USER` → `deploy`
- `VPS_SSH_KEY` → приватный ключ деплой-пользователя app-VPS (тот же, что у PrizeDrawing, если он общий)

Делать **до** шага 11.

### Шаг 13 — служебный бот для алертов

`@BotFather` → `/newbot` → имя вида `hockey_watchdog_bot`. Токен — на app-VPS, в отдельную переменную. Отдельный бот нужен потому, что алерт на боевом токене промолчит ровно тогда, когда сломан боевой токен.

Ещё понадобится твой `chat_id` — напиши `@userinfobot`, он его пришлёт.

### Шаг 14 — проверить алерт по-настоящему

```
ssh deploy@88.218.250.212
docker stop hockey-bot
```

Ждём до 10 минут — должно прийти сообщение. Потом:

```
docker start hockey-bot
```

Не проверенный алерт не считается сделанным.

### Шаг 15 — зачистка личного сервера (не раньше 09.08)

Окно отката — 7 дней. После него:

```
ssh root@185.39.19.83
rm /opt/hockey-platform/bot/.env
rm /etc/systemd/system/hockey-bot.service
systemctl daemon-reload
```

Каталог `/opt/hockey-platform` — по желанию, места он ест мало.

---

## БЛОК 3 · Фоном, когда есть настроение

- **Глава 6 «Кубки Канады»** — отдать бриф `s9_research_canada-cup.md` чату-исследователю. От спринта не зависит, сдаётся когда сдаётся.
- **Наполнение календаря** — 127/366, очередь по дырам: ноябрь (4/30) → октябрь (6/31) → июль (7/31).
- **Мелкий хвост:** `tools/calendar-build/` до сих пор не в git. Либо `git add`, либо в `.gitignore` — реши одной строкой.

---

## Куда смотреть, если что-то пошло не так

| Симптом | Причина, скорее всего |
|---|---|
| Бот отвечает через раз, дублирует ответы | Два инстанса живы одновременно → 409. Вернуться к шагу 8 |
| Контейнер стартует и сразу падает | `.env`: нет строки целиком, или инлайн-комментарий в значении |
| Actions зелёные, а изменений в боте нет | `DEPLOY_ENABLED` ещё `false`, или пуш не попал в path-фильтр |
| В логах виден токен | Потерян `logging.getLogger("httpx").setLevel(WARNING)` при переезде |
