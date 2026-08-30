#!/usr/bin/env bash
# Деплой хоккей-бота на app-VPS. Вызывается из GitHub Actions и руками.
# Healthcheck внутри скрипта, а не в workflow — чтобы ручной деплой был защищён так же.
#
# ⚠️ Всё тело — внутри main(), и это не стиль, а необходимость.
# Скрипт делает `git pull`, который может переписать ЕГО ЖЕ файл во время работы.
# Bash читает скрипт порциями по мере исполнения: если файл изменился под ним,
# он продолжит с прежнего байтового смещения в уже другом тексте и выполнит мусор.
# Пока deploy.sh не менялся, это не стреляло. Обёртка в функцию заставляет bash
# разобрать тело целиком до первой команды, поэтому подмена файла безопасна.
set -euo pipefail

main() {
    cd /opt/hockey-platform

    echo "==> git pull"
    git pull --ff-only origin main

    echo "==> сборка и запуск"
    # Запоминаем контейнер ДО запуска: по смене id понятно, пересоздавался он или нет.
    # Без этого healthcheck ниже врёт — см. комментарий к нему.
    local before_id after_id state restarts
    before_id="$(docker compose ps -q bot 2>/dev/null || true)"
    docker compose up -d --build
    after_id="$(docker compose ps -q bot 2>/dev/null || true)"

    echo "==> healthcheck"
    sleep 8
    # Грабля 1: процесс стартует и тихо выходит — статус контейнера это не ловит.
    # Поэтому при рестарте требуем свежую строку запуска в логах.
    #
    # Грабля 2 (30.08.2026): деплой, не меняющий образ, контейнер НЕ пересоздаёт.
    # Dockerfile кладёт внутрь только bot/ и data/, а *.md и deploy/ исключены
    # .dockerignore — значит пуш в deploy/** или .github/** даёт идентичный образ.
    # Прежняя версия искала "Бот запущен" за последние 60 секунд безусловно и красила
    # такой деплой в красный при живом боте. Теперь ветвимся по факту пересоздания.
    if [ -z "$after_id" ]; then
        echo "FAILED: контейнер bot не запущен"
        docker compose ps
        return 1
    fi

    state="$(docker inspect -f '{{.State.Status}}' "$after_id")"
    restarts="$(docker inspect -f '{{.RestartCount}}' "$after_id")"

    if [ "$before_id" != "$after_id" ]; then
        # Контейнер пересоздан — обязана появиться свежая строка запуска.
        #
        # Грабля 3 (30.08.2026): здесь стояло `docker compose logs ... | grep -q`.
        # При `set -o pipefail` это ломается ровно тогда, когда всё хорошо:
        # `grep -q` выходит по первому совпадению и закрывает канал, `docker compose
        # logs` получает SIGPIPE и падает с ненулевым кодом, pipefail берёт его как
        # статус конвейера. То есть проверка проваливалась ИМЕННО ПОТОМУ, что строка
        # нашлась. Тот же класс, что молчаливое падение из-за `head` в конвейере
        # (разбор переезда VPN, 22.08). Лечение — не строить конвейер: забираем
        # вывод в переменную и сопоставляем с образцом средствами самого bash.
        local fresh_logs
        fresh_logs="$(docker compose logs --since 60s bot 2>&1 || true)"
        if [[ "$fresh_logs" == *"Бот запущен"* ]]; then
            echo "OK: бот перезапущен с новым образом"
        else
            echo "FAILED: контейнер пересоздан, но строки запуска в логах нет"
            docker compose logs --tail 40 bot
            return 1
        fi
    else
        # Образ не изменился, контейнер тот же. Проверяем, что он жив и не в цикле
        # рестартов — «не перезапускался» не должно означать «не проверяли».
        if [ "$state" = "running" ]; then
            echo "OK: образ не изменился, контейнер работает (status=$state, restarts=$restarts)"
        else
            echo "FAILED: контейнер не в состоянии running (status=$state, restarts=$restarts)"
            docker compose logs --tail 40 bot
            return 1
        fi
    fi

    echo "==> чистка старых образов"
    docker image prune -f >/dev/null
}

main "$@"
