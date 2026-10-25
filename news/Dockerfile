# Новостник «Культура хоккея»: контейнер сервиса (утренний сбор + кнопки владельцу, long polling).
# Отдельный образ от бота: свои зависимости (Pillow, Claude Code CLI) и свой токен.
# Собирается из корня репо: docker compose --profile news build news
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# UID 1000 — как у бота: том ./news-runtime на хосте принадлежит deploy (UID 1000).
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY news/requirements.txt news/requirements.txt
RUN pip install --no-cache-dir -r news/requirements.txt

# Claude Code CLI — первый провайдер вводной фразы. Версия закреплена; вход —
# CLAUDE_CODE_OAUTH_TOKEN в news/.env (`claude setup-token` у владельца). Нет токена —
# цепочка уступает шаблону, пост выходит без вводной.
USER app
RUN curl -fsSL https://claude.ai/install.sh | bash -s 2.1.310
ENV PATH=/home/app/.local/bin:$PATH

COPY --chown=app:app news/ news/
RUN mkdir -p news/out

CMD ["python", "-m", "news.run", "serve"]
