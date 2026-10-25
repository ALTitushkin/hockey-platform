"""Сменный слой модели: вводная фраза к посту от первого провайдера, чья фраза прошла гард.

Статистику модель не пишет: числа словами («два гола») гард сверить не может, поэтому блок
цифр всегда шаблонный, а модель даёт одну живую фразу сверху. Фразу проверяет
`guard.check_lead`; провайдер упал, исчерпал лимит, не настроен или фраза не прошла гард —
берём следующего. Не справился никто — пост уходит без фразы. Канал не молчит из-за модели.

Порядок — переменная NEWS_LLM, через запятую (по умолчанию «claude_cli,gigachat,yandexgpt»):
- claude_cli — Claude Code в headless-режиме (`claude -p`), подписка. На сервере вход по
  долгоживущему токену: `claude setup-token` → CLAUDE_CODE_OAUTH_TOKEN. Модель — NEWS_CLAUDE_MODEL.
- gigachat  — Сбер, легально в РФ. GIGACHAT_AUTH_KEY (ключ авторизации из кабинета),
  GIGACHAT_SCOPE (по умолчанию GIGACHAT_API_PERS), GIGACHAT_CA_BUNDLE — корневой сертификат
  Минцифры: без него TLS не проверяется, а проверку мы не отключаем.
- yandexgpt — Yandex AI Studio. YANDEX_API_KEY, YANDEX_FOLDER_ID, YANDEX_MODEL (yandexgpt-lite).
Провайдеры gigachat и yandexgpt написаны по документации и ждут ключей: живьём не проверены.
"""

import json
import os
import shutil
import ssl
import subprocess
import time
import urllib.request
import uuid
from collections.abc import Callable

PROMPT = """Ты редактор Telegram-канала «Культура хоккея». Ниже утренний пост о матчах НХЛ
с участием российских и белорусских игроков. Напиши к нему ОДНУ вводную фразу (до 25 слов),
живую, без канцелярита — о главном сюжете ночи.
Жёсткие правила:
- никаких чисел и числительных — ни цифрами, ни словами («два», «дубль», «хет-трик»);
- никаких «впервые», «рекорд», «лучший», «серия», «подряд» — этого нет в данных;
- фамилии и клубы бери ровно как в посте, в той же форме, не склоняй;
- без оценок, слухов, прогнозов, эмодзи и HTML;
- ответь только фразой, без кавычек и пояснений.

Пост:
"""
DEFAULT_CHAIN = "claude_cli,gigachat,yandexgpt"
TIMEOUT = 120


def _clean(text: str | None) -> str | None:
    text = (text or "").strip().strip("«»\"' ")
    return text or None


def _post_json(url: str, body: dict, headers: dict, context: ssl.SSLContext | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=context) as resp:
        return json.load(resp)


def claude_cli(prompt: str) -> str | None:
    exe = shutil.which("claude")
    if not exe:
        return None
    cmd = [exe, "-p", "--output-format", "text", "--tools", "", "--no-session-persistence",
           "--strict-mcp-config", "--setting-sources", ""]
    if os.environ.get("NEWS_CLAUDE_MODEL"):
        cmd += ["--model", os.environ["NEWS_CLAUDE_MODEL"]]
    try:
        res = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    # Исчерпанный лимит подписки = ненулевой код выхода: просто уступаем следующему провайдеру.
    return _clean(res.stdout) if res.returncode == 0 else None


_giga_token: dict = {}


def gigachat(prompt: str) -> str | None:
    key = os.environ.get("GIGACHAT_AUTH_KEY")
    if not key:
        return None
    ctx = ssl.create_default_context(cafile=os.environ.get("GIGACHAT_CA_BUNDLE") or None)
    if _giga_token.get("expires_at", 0) - 60 < time.time():
        req = urllib.request.Request(
            os.environ.get("GIGACHAT_OAUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"),
            data=f"scope={os.environ.get('GIGACHAT_SCOPE', 'GIGACHAT_API_PERS')}".encode(), method="POST",
            headers={"Authorization": f"Basic {key}", "RqUID": str(uuid.uuid4()),
                     "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            tok = json.load(resp)
        _giga_token.update(token=tok["access_token"], expires_at=tok["expires_at"] / 1000)
    data = _post_json(
        os.environ.get("GIGACHAT_API_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"),
        {"model": os.environ.get("GIGACHAT_MODEL", "GigaChat"), "messages": [{"role": "user", "content": prompt}]},
        {"Authorization": f"Bearer {_giga_token['token']}"}, ctx)
    return _clean(data["choices"][0]["message"]["content"])


def yandexgpt(prompt: str) -> str | None:
    key, folder = os.environ.get("YANDEX_API_KEY"), os.environ.get("YANDEX_FOLDER_ID")
    if not (key and folder):
        return None
    model = os.environ.get("YANDEX_MODEL", "yandexgpt-lite")
    data = _post_json(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        {"modelUri": f"gpt://{folder}/{model}/latest",
         "completionOptions": {"stream": False, "temperature": 0.6, "maxTokens": "200"},
         "messages": [{"role": "user", "text": prompt}]},
        {"Authorization": f"Api-Key {key}", "x-folder-id": folder})
    return _clean(data["result"]["alternatives"][0]["message"]["text"])


PROVIDERS: dict[str, Callable[[str], str | None]] = {
    "claude_cli": claude_cli, "gigachat": gigachat, "yandexgpt": yandexgpt,
}


def lead(text: str, accept: Callable[[str], list[str]],
         chain: str | None = None, providers: dict | None = None) -> tuple[str | None, str, list[str]]:
    """→ (фраза или None, кто её дал, журнал попыток). `accept` — гард: пустой список = принято."""
    providers = providers or PROVIDERS
    log = []
    for name in (chain or os.environ.get("NEWS_LLM") or DEFAULT_CHAIN).split(","):
        name = name.strip()
        if name == "none" or not name:
            break
        if name not in providers:
            log.append(f"{name}: неизвестный провайдер")
            continue
        try:
            phrase = providers[name](PROMPT + text)
        except Exception as e:  # сеть, 4xx/5xx, неожиданный ответ — пробуем следующего
            log.append(f"{name}: ошибка {type(e).__name__}: {e}"[:200])
            continue
        if not phrase:
            log.append(f"{name}: не настроен или не ответил")
            continue
        issues = accept(phrase)
        if issues:
            log.append(f"{name}: фраза отклонена гардом ({'; '.join(issues)}): {phrase}")
            continue
        return phrase, name, log
    return None, "шаблон", log
