#!/usr/bin/env bash
# Деплой хоккей-бота на app-VPS. Вызывается из GitHub Actions и руками.
# Healthcheck внутри скрипта, а не в workflow — чтобы ручной деплой был защищён так же.
set -euo pipefail

cd /opt/hockey-platform

echo "==> git pull"
git pull --ff-only origin main

echo "==> сборка и запуск"
docker compose up -d --build

echo "==> healthcheck"
sleep 8
# Грабля: процесс стартует и тихо выходит — статус контейнера это не ловит.
# Проверяем строку запуска в логах, как раньше проверяли journalctl.
if docker compose logs --since 60s bot | grep -q "Бот запущен"; then
  echo "OK: бот запущен"
else
  echo "FAILED: нет строки запуска в логах контейнера"
  docker compose logs --tail 40 bot
  exit 1
fi

echo "==> чистка старых образов"
docker image prune -f >/dev/null
