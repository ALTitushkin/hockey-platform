"""Необязательный шаг: Claude Code в headless-режиме (`claude -p`) пишет вводную фразу к посту.

Статистику модель не переписывает: числа словами («два гола») гард сверить не может, поэтому
блок цифр всегда шаблонный, а модель даёт только одну живую фразу сверху. Инструменты
выключены — она ничего не публикует и никуда не ходит. Фраза проходит `guard.check_lead`;
не прошла, CLI не найден или упал — пост уходит без неё. Канал не молчит из-за модели.
На сервере вход по долгоживущему токену: `claude setup-token` → CLAUDE_CODE_OAUTH_TOKEN.
"""

import shutil
import subprocess

RULES = """Ты редактор Telegram-канала «Культура хоккея». Ниже утренний пост о матчах НХЛ
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


def lead(text: str, timeout: int = 120) -> str | None:
    exe = shutil.which("claude")
    if not exe or not text:
        return None
    cmd = [exe, "-p", "--output-format", "text", "--tools", "", "--no-session-persistence",
           "--strict-mcp-config", "--setting-sources", ""]
    try:
        res = subprocess.run(cmd, input=RULES + text, capture_output=True, text=True,
                             encoding="utf-8", timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None
    out = res.stdout.strip()
    return out if res.returncode == 0 and out else None
