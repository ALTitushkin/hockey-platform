"""Codex CLI через подписку: изолированный пересказ, метрики без текста и секретов."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from news import publish

MODEL = "gpt-6-luna"
CLI_VERSION = "0.166.0"
DISABLED = ("shell_tool", "unified_exec", "apps", "browser_use", "computer_use",
            "image_generation", "view_image", "multi_agent", "remote_plugin", "hooks", "skill_search")
ENV_KEYS = ("PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
            "CODEX_HOME", "SSL_CERT_FILE", "CODEX_CA_CERTIFICATE", "LANG", "LC_ALL")


def state_path() -> Path:
    return publish.OUT / "codex_usage.json"


def read_state() -> dict:
    path = state_path()
    if not path.exists():
        return {"attempts": 0, "runs": []}
    # Повреждение учёта не сбрасывает защиту молча.
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    publish.OUT.mkdir(parents=True, exist_ok=True)
    path = state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def command(exe: str, model: str) -> list[str]:
    instructions = (Path(__file__).parent / "prompts/editor-system.md").resolve().as_posix()
    args = [exe, "exec", "--ignore-user-config", "--ephemeral", "--json", "--skip-git-repo-check",
            "--sandbox", "read-only", "--color", "never", "--model", model,
            "-c", 'model_reasoning_effort="low"', "-c", 'web_search="disabled"',
            "-c", 'forced_login_method="chatgpt"', "-c", 'approval_policy="never"',
            "-c", "project_doc_max_bytes=0", "-c", "skills.max_context_tokens=1",
            "-c", f"model_instructions_file={json.dumps(instructions)}"]
    for feature in DISABLED:
        args += ["--disable", feature]
    return args + ["-"]


def parse_output(raw: str) -> tuple[str | None, dict]:
    text, usage, completed = None, {}, False
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "turn.failed":
            return None, usage
        if event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
            completed = True
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                text = item.get("text")
            elif item.get("type") not in ("reasoning", "plan", "error"):
                return None, usage  # пересказ не должен выполнять инструменты
    return (text if completed else None), usage


def generate(prompt: str) -> str | None:
    """Один вызов; общий cooldown после сбоя защищает лимит от очереди ретраев."""
    if len(prompt) > 20000:
        raise ValueError("источник превышает бюджет 20000 знаков — требуется редакторское ревью")
    exe = os.environ.get("NEWS_CODEX_BIN") or shutil.which("codex")
    if not exe:
        return None
    state, now = read_state(), time.time()
    if now < state.get("cooldown_until", 0):
        return None
    model = os.environ.get("NEWS_CODEX_MODEL", MODEL)
    env = {k: os.environ[k] for k in ENV_KEYS if k in os.environ}
    started = time.monotonic()
    state["attempts"] = state.get("attempts", 0) + 1
    # Запись до запуска: авария процесса не вызывает немедленный шторм повторов.
    state["cooldown_until"] = now + 30 * 60
    save_state(state)
    answer, usage, status = None, {}, "failed"
    try:
        with tempfile.TemporaryDirectory(prefix="hockey-editor-") as cwd:
            result = subprocess.run(command(exe, model), input=prompt, capture_output=True,
                                    text=True, encoding="utf-8", timeout=120, cwd=cwd, env=env)
        if result.returncode == 0:
            answer, usage = parse_output(result.stdout)
            status = "ok" if answer else "invalid_output"
    except (OSError, subprocess.TimeoutExpired):
        status = "timeout_or_launch_error"
    if answer:
        state["cooldown_until"] = 0
    state.setdefault("runs", []).append({"at": now, "model": model, "status": status,
                                         "seconds": round(time.monotonic() - started, 2),
                                         "prompt_chars": len(prompt),
                                         "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest()[:16],
                                         "usage": usage})
    state["runs"] = state["runs"][-500:]
    save_state(state)
    return answer
