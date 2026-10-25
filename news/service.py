"""Сервис новостника: утренний сбор; чистый гард — публикует сам (NEWS_AUTO_PUBLISH=1), иначе кнопки.

    python -m news.run serve

- Каждое утро после NEWS_REVIEW_AT (МСК, по умолчанию 09:30) собирает «Ночь наших» и шлёт владельцу
  в личку бота: пост как он выйдет и кнопки «✅ Опубликовать» / «✖️ Отклонить».
  Если в ночи ещё идут матчи, ждёт и пробует снова каждые RETRY минут, но не дольше NEWS_DEADLINE
  (по умолчанию 12:00): в дедлайн собирает с тем, что закончилось.
- Кнопки принимает только от OWNER_CHAT_ID. Нажатие от кого-то ещё игнорируется.
- Публикует тот же `publish.publish`, что и команда: гард, отказ и дубль проверяются там.

Опрос Telegram — long polling (getUpdates). Этим токеном больше никто не опрашивает, иначе 409.
"""

import json
import os
import time
from collections.abc import Callable
from datetime import datetime
from datetime import time as dtime
from zoneinfo import ZoneInfo

from news import publish

MSK = ZoneInfo("Europe/Moscow")
RETRY = 15 * 60
STATE = publish.OUT / "service_state.json"


def parse_hhmm(value: str, default: str) -> dtime:
    h, m = (int(x) for x in (value or default).split(":"))
    return dtime(h, m)


def handle_update(update: dict, owner: str, post: publish.Post = publish.http_post) -> str | None:
    """Одно обновление Telegram → что сделали (для лога). Чистая логика, сеть — через post."""
    cb = update.get("callback_query")
    if not cb:
        return None
    if str(cb.get("from", {}).get("id")) != str(owner):
        publish.tg_call("answerCallbackQuery", {"callback_query_id": cb["id"]}, post)
        return f"чужое нажатие от {cb.get('from', {}).get('id')} — игнор"
    action, _, msk = cb.get("data", "").partition(":")
    msg = cb.get("message", {})
    if action == "pub":
        ok, report = publish.publish(msk, ["tg", "max"], post)
        note = ("✅ Опубликовано" if ok else "⚠️ Не всё ушло") + "\n" + "\n".join(report)
    elif action == "rej":
        publish.reject(msk)
        note = "✖️ Отклонено — в канал не пойдёт"
    else:
        return f"неизвестная кнопка {cb.get('data')}"
    publish.tg_call("answerCallbackQuery", {"callback_query_id": cb["id"], "text": note.split("\n")[0]}, post)
    # кнопки убираем, чтобы не нажать второй раз; итог — в том же сообщении
    publish.tg_call("editMessageText", {"chat_id": msg.get("chat", {}).get("id"), "message_id": msg.get("message_id"),
                                        "text": note, "reply_markup": {"inline_keyboard": []}}, post)
    return f"{action} {msk}: {note.splitlines()[0]}"


def due(now: datetime, state: dict, review_at: dtime, deadline: dtime) -> str | None:
    """→ дата выпуска, если пора собирать, иначе None. Один выпуск в день."""
    today = now.date().isoformat()
    if state.get("built") == today or now.time() < review_at:
        return None
    if state.get("next_try") and now.timestamp() < state["next_try"] and now.time() < deadline:
        return None
    return today


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    publish.OUT.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state), encoding="utf-8")


def run_forever(build: Callable[[str, bool], str]) -> None:
    """build(дата, последняя_попытка) → "ok" | "nogames" | "pending" (матчи ещё идут)."""
    owner = os.environ["OWNER_CHAT_ID"]
    review_at = parse_hhmm(os.environ.get("NEWS_REVIEW_AT", ""), "09:30")
    deadline = parse_hhmm(os.environ.get("NEWS_DEADLINE", ""), "12:00")
    offset = None
    print(f"новостник: сбор после {review_at:%H:%M} МСК, дедлайн {deadline:%H:%M}, владелец {owner}", flush=True)
    while True:
        state, now = load_state(), datetime.now(MSK)
        msk = due(now, state, review_at, deadline)
        if msk:
            try:
                result = build(msk, now.time() >= deadline)
            except Exception as e:  # сеть/API: не роняем сервис, пробуем позже
                result = f"ошибка {type(e).__name__}: {e}"
            print(f"{now:%Y-%m-%d %H:%M} сборка {msk}: {result}", flush=True)
            if result in ("ok", "nogames"):
                state = {"built": msk}
            else:
                state["next_try"] = now.timestamp() + RETRY
            save_state(state)
        body = {"timeout": 50, "allowed_updates": ["callback_query"]}
        if offset is not None:
            body["offset"] = offset
        r = publish.tg_call("getUpdates", body)
        for upd in r.get("result", []):
            offset = upd["update_id"] + 1
            line = handle_update(upd, owner)
            if line:
                print(f"{datetime.now(MSK):%H:%M} {line}", flush=True)
        if not r.get("ok"):
            print(f"getUpdates: {r.get('description')}", flush=True)
            time.sleep(10)
