#!/usr/bin/env bash
# Сторож хоккей-бота: раз в 10 минут из cron на app-VPS.
# Контейнер не running ИЛИ боевой токен не отвечает на getMe → сообщение владельцу.
#
# Алерт шлёт ОТДЕЛЬНЫЙ служебный бот: на боевом токене сторож промолчал бы ровно
# тогда, когда сломан боевой токен. Настройки — в /opt/hockey-platform/.watchdog.env
# (в git не попадает, см. .gitignore):
#   WATCHDOG_TOKEN=...   токен служебного бота (@BotFather → /newbot)
#   WATCHDOG_CHAT=...    chat_id владельца (@userinfobot)
# Боевой BOT_TOKEN берётся из .env рядом с compose — тот же файл, что у контейнера.
#
# Анти-спам: пока бот лежит, повторный алерт не чаще раза в час; при подъёме —
# одно сообщение «восстановился». Состояние — в файле-флаге /opt/hockey-platform/.watchdog-down.
# Установка и проверка: deploy/README.md → «Алерт о падении».
set -uo pipefail

main() {
    local root=/opt/hockey-platform
    local flag="$root/.watchdog-down"   # не в runtime/: тот принадлежит UID 1000 контейнера, cron идёт от deploy
    local repeat_after=3600

    # shellcheck disable=SC1091
    source "$root/.watchdog.env" || { echo "нет $root/.watchdog.env"; return 1; }
    local bot_token
    bot_token="$(grep -E '^BOT_TOKEN=' "$root/.env" | cut -d= -f2-)"

    local problem=""
    local state
    state="$(docker inspect -f '{{.State.Status}}' hockey-bot 2>/dev/null || echo "нет контейнера")"
    if [ "$state" != "running" ]; then
        problem="контейнер hockey-bot: $state"
    else
        # Ответ getMe забираем в переменную, а не в конвейер с grep -q — см. грабли pipefail в deploy.sh.
        local resp
        resp="$(curl -s -m 15 "https://api.telegram.org/bot${bot_token}/getMe" || true)"
        if [[ "$resp" != *'"ok":true'* ]]; then
            # Токен в сообщение и в лог не попадает — только описание ответа.
            problem="getMe не ответил ok (${resp:0:80})"
            problem="${problem//$bot_token/***}"
        fi
    fi

    if [ -n "$problem" ]; then
        local now last=0
        now="$(date +%s)"
        [ -f "$flag" ] && last="$(cat "$flag")"
        if [ $((now - last)) -ge $repeat_after ]; then
            send "🔴 Хоккей-бот лежит: $problem"
            echo "$now" > "$flag"
        fi
    elif [ -f "$flag" ]; then
        send "🟢 Хоккей-бот снова отвечает"
        rm -f "$flag"
    fi
}

send() {
    curl -s -m 15 -o /dev/null "https://api.telegram.org/bot${WATCHDOG_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${WATCHDOG_CHAT}" --data-urlencode "text=$1"
}

main "$@"
