"""Публикация выпуска: черновик → владельцу в личку → в каналы только по команде владельца.

Шаги:
- `night --review` сохраняет черновик (news/out/<дата>_night.json) и шлёт его владельцу в личку бота;
- `publish --date <дата>` отправляет сохранённый черновик в Telegram-канал и в MAX (если настроен).
  Если гард нашёл проблемы, черновик не публикуется. Повторная публикация той же даты тоже не проходит.

Секреты — в news/.env (в git не попадает): NEWS_BOT_TOKEN, NEWS_CHANNEL, OWNER_CHAT_ID,
MAX_BOT_TOKEN, MAX_CHAT_ID. Переменные окружения сильнее файла — так на сервере их задаёт compose.
API MAX (platform-api2.max.ru, POST /messages) написан по документации и живьём ещё не проверен.
"""

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).parent
ENV = ROOT / ".env"
OUT = ROOT / "out"
TG_API = "https://api.telegram.org"
MAX_API = "https://platform-api2.max.ru"
CAPTION_LIMIT = 1024
TITLES = {"night": "«Ночь наших»", "league": "«Ночь в НХЛ»", "tonight": "«Сегодня ночью»"}

Post = Callable[..., dict]


def load_env(path: Path = ENV) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if value.strip():
                os.environ.setdefault(key.strip(), value.strip())


def http_post(url: str, body: dict, headers: dict, files: dict | None = None) -> dict:
    """POST JSON или, если есть files ({поле: путь}), multipart/form-data — так Telegram принимает картинку."""
    if files:
        boundary = uuid.uuid4().hex
        parts = []
        for key, value in body.items():
            value = value if isinstance(value, str) else json.dumps(value)
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        for key, path in files.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; filename="{Path(path).name}"'
                         f'\r\nContent-Type: image/png\r\n\r\n'.encode() + Path(path).read_bytes() + b"\r\n")
        data, ctype = b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"
    else:
        data, ctype = json.dumps(body).encode(), "application/json"
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": ctype, **headers})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error_code": e.code, "description": e.read().decode(errors="replace")[:300]}
    except (OSError, ValueError) as e:  # обрыв, таймаут, битый JSON — сервис не падает, а пробует снова
        return {"ok": False, "description": f"сеть: {type(e).__name__}"}


def visible_len(text: str) -> int:
    """Длина так, как её считает Telegram: после разбора HTML-разметки."""
    return len(html.unescape(re.sub(r"<[^>]+>", "", text)))


def tg_send(chat: str, text: str, post: Post = http_post, photo: str | None = None) -> tuple[bool, str]:
    """Текст или картинка с подписью. Не влезает в подпись — картинка, следом текст отдельным сообщением."""
    token = os.environ.get("NEWS_BOT_TOKEN")
    if not token or not chat:
        return False, "не настроен NEWS_BOT_TOKEN или чат"
    api, ids = f"{TG_API}/bot{token}", []
    msg = {"chat_id": chat, "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
    if photo and Path(photo).exists():
        fits = visible_len(text) <= CAPTION_LIMIT
        body = {"chat_id": chat, **({"caption": text, "parse_mode": "HTML"} if fits else {})}
        r = post(f"{api}/sendPhoto", body, {}, files={"photo": photo})
        if not r.get("ok"):
            return False, r.get("description", "")
        ids.append(r["result"]["message_id"])
        if fits:
            return True, f"картинка с подписью, message_id {ids[0]}"
    r = post(f"{api}/sendMessage", msg, {})
    if not r.get("ok"):
        return False, r.get("description", "")
    ids.append(r["result"]["message_id"])
    return True, ("картинка + текст, " if len(ids) > 1 else "") + f"message_id {', '.join(map(str, ids))}"


def max_send(text: str, post: Post = http_post) -> tuple[bool, str]:
    token, chat = os.environ.get("MAX_BOT_TOKEN"), os.environ.get("MAX_CHAT_ID")
    if not token or not chat:
        return False, "MAX не настроен"
    r = post(f"{MAX_API}/messages?{urllib.parse.urlencode({'chat_id': chat})}",
             {"text": text, "format": "html"}, {"Authorization": token})
    ok = "message" in r
    return ok, "отправлено" if ok else str(r.get("message") or r.get("description") or r)[:300]


def draft_path(msk: str, kind: str = "night") -> Path:
    """kind — рубрика: night («Ночь наших»), league («Ночь в НХЛ»)."""
    return OUT / f"{msk}_{kind}.json"


def save_draft(msk: str, text: str, issues: list[str], variant: str, card: str | None = None,
               kind: str = "night", data: dict | None = None) -> Path:
    """data — исходные данные поста для перепроверки после выхода («Сегодня ночью»: матчи и составы)."""
    OUT.mkdir(exist_ok=True)
    path = draft_path(msk, kind)
    # пересборка черновика не сбрасывает отметки о публикации — иначе дата ушла бы в канал дважды
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    d = {"date": msk, "text": text, "issues": issues, "variant": variant, "card": card,
         "published": old.get("published", []), "messages": old.get("messages", {})}
    if data is not None:
        d["data"] = data
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def edit_photo(chat: str, message_id: int, text: str, photo: str, post: Post = http_post) -> tuple[bool, str]:
    """Заменить картинку и подпись вышедшего поста (editMessageMedia)."""
    media = {"type": "photo", "media": "attach://photo", "caption": text, "parse_mode": "HTML"}
    r = post(f"{TG_API}/bot{os.environ.get('NEWS_BOT_TOKEN', '')}/editMessageMedia",
             {"chat_id": chat, "message_id": message_id, "media": media}, {}, files={"photo": photo})
    return bool(r.get("ok")), r.get("description", "ок")


def tg_call(method: str, body: dict, post: Post = http_post) -> dict:
    """Любой метод Bot API от имени бота новостника."""
    return post(f"{TG_API}/bot{os.environ.get('NEWS_BOT_TOKEN', '')}/{method}", body, {})


def control_text(d: dict, kind: str = "night") -> str:
    guard_line = "гард: чисто" if not d["issues"] else "⚠️ гард: " + html.escape("; ".join(d["issues"]))
    return f"📝 <b>Черновик {TITLES.get(kind, kind)} {d['date']}</b> выше\n{d['variant']} · {guard_line}"


def review(msk: str, post: Post = http_post, kind: str = "night") -> tuple[bool, str]:
    """Черновик владельцу: сам пост как он выйдет, следом — сообщение с кнопками.
    Гард не чист — кнопки «Опубликовать» нет: такой пост не уходит ни кнопкой, ни командой."""
    d = json.loads(draft_path(msk, kind).read_text(encoding="utf-8"))
    owner = os.environ.get("OWNER_CHAT_ID", "")
    ok, info = tg_send(owner, d["text"], post, d.get("card"))
    if not ok:
        return ok, info
    buttons = [{"text": "✖️ Отклонить", "callback_data": f"rej:{kind}:{msk}"}]
    if not d["issues"]:
        buttons.insert(0, {"text": "✅ Опубликовать", "callback_data": f"pub:{kind}:{msk}"})
    r = tg_call("sendMessage", {"chat_id": owner, "text": control_text(d, kind), "parse_mode": "HTML",
                                "reply_markup": {"inline_keyboard": [buttons]}}, post)
    return bool(r.get("ok")), info if r.get("ok") else r.get("description", "")


def auto_publish(msk: str, post: Post = http_post, kind: str = "night") -> tuple[bool, str]:
    """Автопубликация (NEWS_AUTO_PUBLISH=1): чистый черновик сразу в каналы, владельцу — отчёт.
    Те же проверки, что у кнопки: гард, отказ, дубль — внутри publish()."""
    ok, report = publish(msk, ["tg", "max"], post, kind)
    title = f"{TITLES.get(kind, kind)} {msk}"
    if not any(": ок —" in line for line in report):  # ничего нового не ушло: уже было в канале или ошибка
        if ok:
            return ok, "; ".join(report)  # повтор той же даты — владельцу писать не о чем
        note = f"⚠️ <b>{title}</b>: автопубликация не прошла"
    else:
        note = f"🤖 <b>{title}</b> вышло автоматически" if ok else f"⚠️ <b>{title}</b>: ушло не везде"
    note += "\n" + html.escape("\n".join(report))
    tg_call("sendMessage", {"chat_id": os.environ.get("OWNER_CHAT_ID", ""), "text": note, "parse_mode": "HTML"}, post)
    return ok, "; ".join(report)


def reject(msk: str, kind: str = "night") -> None:
    path = draft_path(msk, kind)
    d = json.loads(path.read_text(encoding="utf-8"))
    d["rejected"] = True
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def publish(msk: str, targets: list[str], post: Post = http_post, kind: str = "night") -> tuple[bool, list[str]]:
    """→ (всё ушло, строки отчёта). Ничего не шлёт, если черновика нет, гард не чист или дата уже вышла."""
    path = draft_path(msk, kind)
    if not path.exists():
        return False, [f"нет черновика {path.name} — сначала night --review"]
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("rejected"):
        return False, ["черновик отклонён владельцем — не публикую"]
    if d["issues"]:
        return False, ["гард не чист — не публикую: " + "; ".join(d["issues"])]
    report, all_ok = [], True
    for target in targets:
        if target in d["published"]:
            report.append(f"{target}: уже опубликовано, пропускаю")
            continue
        if target == "max" and not (os.environ.get("MAX_BOT_TOKEN") and os.environ.get("MAX_CHAT_ID")):
            report.append("max: не подключён, пропускаю")  # не ошибка: канал ещё не заведён
            continue
        ok, info = tg_send(os.environ.get("NEWS_CHANNEL", ""), d["text"], post, d.get("card")) if target == "tg" \
            else max_send(d["text"], post)
        report.append(f"{target}: {'ок' if ok else 'ошибка'} — {info}")
        if ok:
            d["published"].append(target)
            if target == "tg":  # для правки поста потом (перепроверка состава)
                d.setdefault("messages", {})["tg"] = [int(x) for x in re.findall(r"\d+", info.split("message_id")[-1])]
        all_ok &= ok
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return all_ok, report
