"""Уровни «хоккейная карьера» в чате обсуждений канала: баллы за активность → тег участника.

Баллы: +1 за сообщение (не больше DAILY_MESSAGES в сутки), +2 за реакцию другого участника на твоё
сообщение (одна реакция от человека на сообщение, свои не считаются). Снятая реакция баллы не отнимает.
Тег ставит `setChatMemberTag` (Bot API 9.5): до 16 символов, эмодзи в теге запрещены — эмодзи только
в поздравлении. «Легенда» — с 1000 баллов, высшая ступень.

Хранится только user_id → баллы (`levels.json` в news/out). Кто автор сообщения — память процесса
на последние MSG_MEMORY сообщений: после рестарта реакции на старые сообщения просто не считаются.
"""

import json
from collections import OrderedDict
from datetime import date

from news import publish
from news.digest import plural

FILE = publish.OUT / "levels.json"
# Путь игрока за океаном: проспект (задрафтован) → фарм-клуб (AHL) → дебют в НХЛ → … → легенда.
# Пороги снижены по просьбе владельца 25.10.2026: «50 комментов и всего лишь дебютант — сложно».
LEVELS = [(3, "Проспект", "🌱"), (10, "Фарм", "🌾"), (25, "Дебютант", "🏒"), (60, "Основа", "⭐"),
          (150, "Ассистент", "🅰️"), (400, "Капитан", "©️"), (1000, "Легенда", "🏆")]
DAILY_MESSAGES = 10
MSG_MEMORY = 5000


def level(points: int) -> tuple[int, str, str] | None:
    """Уровень по баллам; до первого порога — без тега (просмотровый лагерь)."""
    got = None
    for row in LEVELS:
        if points >= row[0]:
            got = row
    return got


class Levels:
    def __init__(self, chat_id: int, call=publish.tg_call, path=FILE, skip: set[int] = frozenset()):
        # skip — владелец: у него должность в клиенте («Главный тренер»), тег бот ему не ставит
        self.chat, self.call, self.path, self.skip = chat_id, call, path, set(skip)
        self.points: dict[str, int] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.authors: OrderedDict[int, dict] = OrderedDict()  # message_id → автор (id, имя)
        self.voted: set[tuple[int, int]] = set()  # (message_id, кто поставил) — одна реакция = один раз
        self.today, self.sent = date.today(), {}

    def save(self) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(self.points), encoding="utf-8")

    def add(self, user: dict, n: int) -> str | None:
        uid = str(user["id"])
        before = self.points.get(uid, 0)
        self.points[uid] = before + n
        self.save()
        new = level(self.points[uid])
        if new and new != level(before):
            self.call("setChatMemberTag", {"chat_id": self.chat, "user_id": user["id"], "tag": new[1]})
            name = user.get("first_name") or "Участник"
            self.call("sendMessage", {"chat_id": self.chat, "text": f"{new[2]} {name} — теперь «{new[1]}»"})
            return f"уровень: {uid} → {new[1]}"
        return None

    def on_message(self, msg: dict) -> str | None:
        """Сообщение в чате. Автопересылка из канала, сообщения от имени канала и ботов — мимо."""
        user = msg.get("from") or {}
        if msg["chat"]["id"] != self.chat or msg.get("is_automatic_forward") or msg.get("sender_chat") \
                or not user or user.get("is_bot") or user["id"] in self.skip:
            return None
        self.authors[msg["message_id"]] = {"id": user["id"], "first_name": user.get("first_name", "")}
        if len(self.authors) > MSG_MEMORY:
            self.authors.popitem(last=False)
        if date.today() != self.today:
            self.today, self.sent = date.today(), {}
        self.sent[user["id"]] = self.sent.get(user["id"], 0) + 1
        if self.sent[user["id"]] > DAILY_MESSAGES:
            return None
        return self.add(user, 1)

    def on_reaction(self, upd: dict) -> str | None:
        """message_reaction: засчитываем, если реакция появилась впервые и не на своё сообщение."""
        user = upd.get("user")
        author = self.authors.get(upd["message_id"])
        if upd["chat"]["id"] != self.chat or not user or not author or author["id"] == user["id"]:
            return None
        key = (upd["message_id"], user["id"])
        if not upd.get("new_reaction") or upd.get("old_reaction") or key in self.voted:
            return None
        self.voted.add(key)
        return self.add(author, 2)

    def me(self, msg: dict) -> str:
        """Ответ на /level: баллы и сколько до следующего уровня."""
        pts = self.points.get(str(msg["from"]["id"]), 0)
        cur = level(pts)
        nxt = next((row for row in LEVELS if row[0] > pts), None)
        head = f"{cur[2]} «{cur[1]}»" if cur else "🧊 Просмотровый лагерь"
        tail = f"до «{nxt[1]}» — {nxt[0] - pts}" if nxt else "выше некуда"
        return f"{head} · {pts} {plural(pts, ('балл', 'балла', 'баллов'))} · {tail}"


    def on_update(self, upd: dict) -> str | None:
        """Обновление из getUpdates: сообщение, /level или реакция. Остальное — не наше."""
        msg = upd.get("message")
        if msg and msg.get("chat", {}).get("id") == self.chat:
            if (msg.get("text") or "").split("@")[0].strip() == "/level" and msg.get("from"):
                self.call("sendMessage", {"chat_id": self.chat, "text": self.me(msg),
                                          "reply_parameters": {"message_id": msg["message_id"]}})
                return None
            return self.on_message(msg)
        if upd.get("message_reaction"):
            return self.on_reaction(upd["message_reaction"])
        return None
