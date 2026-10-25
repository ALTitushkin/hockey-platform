"""Сервис новостника: утренний сбор; чистый гард — публикует сам (NEWS_AUTO_PUBLISH=1), иначе кнопки.

    python -m news.run serve

- Каждое утро собирает рубрики по своему времени (МСК): «Ночь в НХЛ» после NEWS_LEAGUE_AT (09:00),
  «Ночь наших» после NEWS_REVIEW_AT (09:30). Чистый гард — пост уходит сам, владельцу отчёт;
  иначе — владельцу в личку пост и кнопки «✅ Опубликовать» / «✖️ Отклонить».
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
    # «pub:<рубрика>:<дата>»; у старых кнопок «pub:<дата>» — это «Ночь наших»
    action, *rest = cb.get("data", "").split(":")
    kind, msk = rest if len(rest) == 2 else ["night", *rest[:1]]
    msg = cb.get("message", {})
    if action == "pub":
        ok, report = publish.publish(msk, ["tg", "max"], post, kind)
        note = ("✅ Опубликовано" if ok else "⚠️ Не всё ушло") + "\n" + "\n".join(report)
    elif action == "rej":
        publish.reject(msk, kind)
        note = "✖️ Отклонено — в канал не пойдёт"
    else:
        return f"неизвестная кнопка {cb.get('data')}"
    publish.tg_call("answerCallbackQuery", {"callback_query_id": cb["id"], "text": note.split("\n")[0]}, post)
    # кнопки убираем, чтобы не нажать второй раз; итог — в том же сообщении
    publish.tg_call("editMessageText", {"chat_id": msg.get("chat", {}).get("id"), "message_id": msg.get("message_id"),
                                        "text": note, "reply_markup": {"inline_keyboard": []}}, post)
    return f"{action} {kind} {msk}: {note.splitlines()[0]}"


def due(now: datetime, state: dict, review_at: dtime, deadline: dtime) -> str | None:
    """→ дата выпуска, если пора собирать, иначе None. Один выпуск в день."""
    today = now.date().isoformat()
    if state.get("built") == today or now.time() < review_at:
        return None
    if state.get("next_try") and now.timestamp() < state["next_try"] and now.time() < deadline:
        return None
    return today


def load_state() -> dict:
    """{рубрика: {"built": дата, "next_try": ts}}. Старый формат (одна рубрика) — это «Ночь наших»."""
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {"night": state} if "built" in state or "next_try" in state else state


def save_state(state: dict) -> None:
    publish.OUT.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state), encoding="utf-8")


Build = Callable[[str, bool], str]


def run_forever(jobs: list[tuple[str, str, str, Build]],
                ticks: list[tuple[int, Callable[[datetime], list[str]]]] = (),
                chat: Callable[[dict], str | None] | None = None) -> None:
    """jobs: (рубрика, переменная со временем, время по умолчанию, build).
    build(дата, последняя_попытка) → "ok" | "nogames" | "pending" (матчи ещё идут).
    ticks: (раз в сколько секунд, fn(сейчас) → строки для лога) — перепроверки вышедших постов.
    chat: обработчик сообщений и реакций чата обсуждений (уровни); None — бот слушает только кнопки."""
    owner = os.environ["OWNER_CHAT_ID"]
    deadline = parse_hhmm(os.environ.get("NEWS_DEADLINE", ""), "12:00")
    plan = [(kind, parse_hhmm(os.environ.get(var, ""), default), build) for kind, var, default, build in jobs]
    offset, last_tick = None, [0.0] * len(ticks)
    times = ", ".join(f"{kind} {at:%H:%M}" for kind, at, _ in plan)
    print(f"новостник: сбор после {times} МСК, дедлайн {deadline:%H:%M}, владелец {owner}", flush=True)
    while True:
        state, now = load_state(), datetime.now(MSK)
        for kind, at, build in plan:
            job = state.get(kind, {})
            msk = due(now, job, at, deadline)
            if not msk:
                continue
            try:
                result = build(msk, now.time() >= deadline)
            except Exception as e:  # сеть/API: не роняем сервис, пробуем позже
                result = f"ошибка {type(e).__name__}: {e}"
            print(f"{now:%Y-%m-%d %H:%M} сборка {kind} {msk}: {result}", flush=True)
            done = result in ("ok", "nogames")
            state[kind] = {"built": msk} if done else {**job, "next_try": now.timestamp() + RETRY}
            save_state(state)
        for i, (every, fn) in enumerate(ticks):
            if now.timestamp() - last_tick[i] < every:
                continue
            last_tick[i] = now.timestamp()
            try:
                lines = fn(now)
            except Exception as e:  # сеть/API: перепроверка подождёт следующего раза
                lines = [f"перепроверка: ошибка {type(e).__name__}: {e}"]
            for line in lines:
                print(f"{now:%Y-%m-%d %H:%M} {line}", flush=True)
        # message_reaction по умолчанию не приходит — только если указать явно
        kinds = ["callback_query"] + (["message", "message_reaction"] if chat else [])
        body = {"timeout": 50, "allowed_updates": kinds}
        if offset is not None:
            body["offset"] = offset
        r = publish.tg_call("getUpdates", body)
        for upd in r.get("result", []):
            offset = upd["update_id"] + 1
            line = handle_update(upd, owner)
            if chat and not line:
                try:
                    line = chat(upd)
                except Exception as e:  # уровни — не повод ронять публикации
                    line = f"уровни: ошибка {type(e).__name__}: {e}"
            if line:
                print(f"{datetime.now(MSK):%H:%M} {line}", flush=True)
        if not r.get("ok"):
            print(f"getUpdates: {r.get('description')}", flush=True)
            time.sleep(10)
