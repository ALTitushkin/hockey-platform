# Новостник «Культура хоккея»: контейнер сервиса (утренний сбор + кнопки владельцу, long polling).
# Образ собирает CI и кладёт в GHCR (ghcr.io/altitushkin/hockey-news:<sha>); сервер только тянет
# готовый образ — стандарт «Инфра и масштабирование»: сборка на общем VPS даёт пики памяти рядом
# с соседями. Контейнер read-only, без root и capabilities (docker-compose.yml, сервис news).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DISABLE_AUTOUPDATER=1

# Зависимости раньше кода: слой не инвалидируется каждым коммитом.
COPY news/requirements.txt /app/news/requirements.txt
RUN pip install --no-cache-dir -r /app/news/requirements.txt

# Claude Code CLI — первый провайдер вводной фразы. Версия закреплена, автообновление выключено:
# в read-only контейнере обновляться ему некуда. Бинарник — в /usr/local/bin, потому что домашний
# каталог в рантайме — tmpfs. Вход — CLAUDE_CODE_OAUTH_TOKEN в news/.env (`claude setup-token`).
# Нет токена — цепочка уступает шаблону, пост выходит без вводной.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://claude.ai/install.sh | bash -s 2.1.310 \
    && cp -L /root/.local/bin/claude /usr/local/bin/claude \
    && rm -rf /root/.local /root/.claude* \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# UID 1000 — как у бота: том ./news-runtime на хосте принадлежит deploy (UID 1000).
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin app

WORKDIR /app
# Код — от root и только на чтение; пишет сервис только в news/out (том) и $HOME (tmpfs).
COPY news/ news/

USER app
CMD ["python", "-m", "news.run", "serve"]
