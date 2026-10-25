#!/usr/bin/env bash
# Сторож «Культуры хоккея»: раз в 10 минут из systemd-таймера на app-VPS (cron на сервере нет).
# По каждому сервису: контейнер не running ИЛИ его токен не отвечает на getMe → сообщение владельцу.
#
# Алерт шлёт ОТДЕЛЬНЫЙ служебный бот: на боевом токене сторож промолчал бы ровно тогда,
# когда сломан боевой токен, а бот словаря публичный — служебное в него не пишем.
# Настройки — в /opt/hockey-platform/.watchdog.env (в git не попадает, см. .gitignore):
#   WATCHDOG_TOKEN=...   токен служебного бота (@BotFather → /newbot)
#   WATCHDOG_CHAT=...    chat_id владельца
# Боевые токены берутся из тех же файлов, что у контейнеров: .env (бот) и news/.env (новостник).
#
# Анти-спам: пока сервис лежит, повторный алерт не чаще раза в час; при подъёме —
# одно сообщение «снова работает». Флаги — /opt/hockey-platform/.watchdog-down-<контейнер>.
# Установка и проверка: deploy/README.md → «Алерт о падении».
set -uo pipefail

ROOT=/opt/hockey-platform
REPEAT_AFTER=3600

# контейнер | человеческое имя | файл с токеном | переменная токена
SERVICES=(
    "hockey-bot|Бот словаря|$ROOT/.env|BOT_TOKEN"
    "hockey-news|Новостник|$ROOT/news/.env|NEWS_BOT_TOKEN"
)

check() {
    local container="$1" env_file="$2" var="$3"
    local state token resp
    state="$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "нет контейнера")"
    if [ "$state" != "running" ]; then
        echo "контейнер $container: $state"
        return
    fi
    token="$(grep -E "^${var}=" "$env_file" 2>/dev/null | cut -d= -f2-)"
    [ -n "$token" ] || { echo "нет $var в $env_file"; return; }
    # Ответ getMe забираем в переменную, а не в конвейер с grep -q — см. грабли pipefail в deploy.sh.
    resp="$(curl -s -m 15 "https://api.telegram.org/bot${token}/getMe" || true)"
    if [[ "$resp" != *'"ok":true'* ]]; then
        local problem="getMe не ответил ok (${resp:0:80})"
        echo "${problem//$token/***}"  # токен в сообщение и в лог не попадает
    fi
}

main() {
    # shellcheck disable=SC1091
    source "$ROOT/.watchdog.env" || { echo "нет $ROOT/.watchdog.env"; return 1; }
    local entry container name env_file var problem flag now last
    for entry in "${SERVICES[@]}"; do
        IFS='|' read -r container name env_file var <<< "$entry"
        flag="$ROOT/.watchdog-down-$container"  # не в runtime/: тот принадлежит UID 1000 контейнера
        problem="$(check "$container" "$env_file" "$var")"
        if [ -n "$problem" ]; then
            now="$(date +%s)"
            last=0
            [ -f "$flag" ] && last="$(cat "$flag")"
            if [ $((now - last)) -ge $REPEAT_AFTER ]; then
                send "🔴 $name лежит: $problem"
                echo "$now" > "$flag"
            fi
            echo "$container: $problem"
        elif [ -f "$flag" ]; then
            send "🟢 $name снова работает"
            rm -f "$flag"
            echo "$container: восстановился"
        else
            echo "$container: ок"
        fi
    done
}

send() {
    curl -s -m 15 -o /dev/null "https://api.telegram.org/bot${WATCHDOG_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${WATCHDOG_CHAT}" --data-urlencode "text=$1"
}

main "$@"
