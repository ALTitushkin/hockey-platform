# Новостник «Культура хоккея»: контейнер сервиса (утренний сбор + кнопки владельцу, long polling).
# Образ собирает CI и кладёт в GHCR (ghcr.io/altitushkin/hockey-news:<sha>); сервер только тянет
# готовый образ — стандарт «Инфра и масштабирование»: сборка на общем VPS даёт пики памяти рядом
# с соседями. Контейнер read-only, без root и capabilities (docker-compose.yml, сервис news).
FROM node:22-bookworm-slim AS codex
RUN npm install --prefix /opt/codex --ignore-scripts --no-audit --no-fund @openai/codex@0.166.0 \
    && find /opt/codex/node_modules/@openai -path '*/bin/codex' -type f -exec cp {} /usr/local/bin/codex \;

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CODEX_HOME=/home/app/.codex

# Зависимости раньше кода: слой не инвалидируется каждым коммитом.
COPY news/requirements.txt /app/news/requirements.txt
RUN pip install --no-cache-dir -r /app/news/requirements.txt

# Только native CLI: Node/npm и Claude отсутствуют в конечном образе.
COPY --from=codex /usr/local/bin/codex /usr/local/bin/codex

# UID 1000 — как у бота: том ./news-runtime на хосте принадлежит deploy (UID 1000).
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin app

WORKDIR /app
# Код — от root и только на чтение; пишет сервис только в news/out (том) и $HOME (tmpfs).
COPY news/ news/

USER app
CMD ["python", "-m", "news.run", "serve"]
