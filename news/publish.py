"""Публикация выпуска: черновик → владельцу в личку → в каналы только по команде владельца.

Шаги:
- `night --review` сохраняет черновик (news/out/<дата>_night.json) и шлёт его владельцу в личку бота;
- `publish --date <дата>` отправляет сохранённый черновик в Telegram-канал и в MAX (если настроен).
  Если гард нашёл проблемы, черновик не публикуется. Повторная публикация той же даты тоже не проходит.

Секреты — в news/.env (в git не попадает): NEWS_BOT_TOKEN, NEWS_CHANNEL, OWNER_CHAT_ID,
MAX_BOT_TOKEN, MAX_CHAT_ID. Переменные окружения сильнее файла — так на сервере их задаёт compose.
API MAX (platform-api2.max.ru, POST /messages) написан по документации и живьём ещё не проверен.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).parent
ENV = ROOT / ".env"
OUT = ROOT / "out"
TG_API = "https://api.telegram.org"
MAX_API = "https://platform-api2.max.ru"

Post = Callable[[str, dict, dict], dict]


def load_env(path: Path = ENV) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if value.strip():
                os.environ.setdefault(key.strip(), value.strip())


def http_post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error_code": e.code, "description": e.read().decode(errors="replace")[:300]}


def tg_send(chat: str, text: str, post: Post = http_post) -> tuple[bool, str]:
    token = os.environ.get("NEWS_BOT_TOKEN")
    if not token or not chat:
        return False, "не настроен NEWS_BOT_TOKEN или чат"
    r = post(f"{TG_API}/bot{token}/sendMessage",
             {"chat_id": chat, "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}, {})
    return bool(r.get("ok")), r.get("description", "") if not r.get("ok") else f"message_id {r['result']['message_id']}"


def max_send(text: str, post: Post = http_post) -> tuple[bool, str]:
    token, chat = os.environ.get("MAX_BOT_TOKEN"), os.environ.get("MAX_CHAT_ID")
    if not token or not chat:
        return False, "MAX не настроен"
    r = post(f"{MAX_API}/messages?{urllib.parse.urlencode({'chat_id': chat})}",
             {"text": text, "format": "html"}, {"Authorization": token})
    ok = "message" in r
    return ok, "отправлено" if ok else str(r.get("message") or r.get("description") or r)[:300]


def draft_path(msk: str) -> Path:
    return OUT / f"{msk}_night.json"


def save_draft(msk: str, text: str, issues: list[str], variant: str) -> Path:
    OUT.mkdir(exist_ok=True)
    path = draft_path(msk)
    # пересборка черновика не сбрасывает отметки о публикации — иначе дата ушла бы в канал дважды
    done = json.loads(path.read_text(encoding="utf-8"))["published"] if path.exists() else []
    path.write_text(json.dumps({"date": msk, "text": text, "issues": issues, "variant": variant,
                                "published": done}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def review(msk: str, post: Post = http_post) -> tuple[bool, str]:
    d = json.loads(draft_path(msk).read_text(encoding="utf-8"))
    guard_line = "гард: чисто" if not d["issues"] else "⚠️ гард: " + "; ".join(d["issues"])
    head = (f"📝 <b>Черновик на проверку</b> · {msk}\n{d['variant']} · {guard_line}\n"
            f"Опубликовать: <code>python -m news.run publish --date {msk}</code>")
    ok, info = tg_send(os.environ.get("OWNER_CHAT_ID", ""), head, post)
    if ok:
        ok, info = tg_send(os.environ.get("OWNER_CHAT_ID", ""), d["text"], post)
    return ok, info


def publish(msk: str, targets: list[str], post: Post = http_post) -> tuple[bool, list[str]]:
    """→ (всё ушло, строки отчёта). Ничего не шлёт, если черновика нет, гард не чист или дата уже вышла."""
    path = draft_path(msk)
    if not path.exists():
        return False, [f"нет черновика {path.name} — сначала night --review"]
    d = json.loads(path.read_text(encoding="utf-8"))
    if d["issues"]:
        return False, ["гард не чист — не публикую: " + "; ".join(d["issues"])]
    report, all_ok = [], True
    for target in targets:
        if target in d["published"]:
            report.append(f"{target}: уже опубликовано, пропускаю")
            continue
        ok, info = tg_send(os.environ.get("NEWS_CHANNEL", ""), d["text"], post) if target == "tg" \
            else max_send(d["text"], post)
        report.append(f"{target}: {'ок' if ok else 'ошибка'} — {info}")
        if ok:
            d["published"].append(target)
        all_ok &= ok
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return all_ok, report
