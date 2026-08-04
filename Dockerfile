# Хоккей-бот: контейнер рантайма (Telegram long polling).
# Слои: сначала зависимости (кэшируются, пока requirements.txt не менялся), потом код.
# Структура внутри образа повторяет репо: /app/bot + /app/data — search.py и
# calendar_feature.py ищут данные как ../data относительно себя, ломать нельзя.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Непривилегированный пользователь. UID/GID 1000 намеренно совпадает с дефолтным
# логин-юзером Ubuntu на VPS: bind-mount ./runtime наследует ownership хоста,
# и контейнер пишет логи спроса без chown и без root.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin app

WORKDIR /app

# --- слой зависимостей (кэш) ---
COPY bot/requirements.txt ./bot/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r bot/requirements.txt

# --- слой кода и данных ---
COPY bot/ ./bot/
COPY data/ ./data/

# Логи спроса живут в томе, не в образе.
RUN mkdir -p /app/runtime && chown -R 1000:1000 /app/runtime
ENV RUNTIME_DIR=/app/runtime

USER app
WORKDIR /app/bot
CMD ["python", "bot.py"]
