"""LLM через локальный Claude Code (`claude -p`) с авторизацией по подписке — без API-ключа.

Только для разработки и тестов на собственном компьютере владельца подписки: подписка Claude рассчитана
на личное использование. Для публичного сайта с внешними пользователями — LLM_PROVIDER=anthropic и API-ключ.

Гарантии:
* ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL не передаются дочернему процессу —
  иначе `claude` пошёл бы в платный API (или в чужой прокси), а не в подписку;
* служебные переменные чужой сессии Claude Code (CLAUDE_CODE_*, CLAUDECODE …) тоже не передаются;
* промпт идёт через stdin (нет ограничений длины argv и подстановки в shell);
* `claude` запускается в пустом временном каталоге и без инструментов — модель только отвечает текстом;
* таймаут убивает процесс; ошибки — типизированные исключения ClaudeCodeError.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from app.core.config import get_settings

log = logging.getLogger(__name__)

# Переменные, из-за которых запрос ушёл бы мимо подписки.
BLOCKED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
# Служебные переменные сессии Claude Code, из которой может быть запущен наш API (desktop-приложение, IDE).
BLOCKED_PREFIX = "CLAUDE"
ALLOWED_CLAUDE_VARS = {"CLAUDE_CONFIG_DIR"}  # свой каталог настроек/входа — передаём
NO_TOOLS = ["Bash", "Edit", "Write", "Read", "Glob", "Grep", "NotebookEdit", "WebFetch", "WebSearch", "Task",
            "TodoWrite"]

_sem: asyncio.Semaphore | None = None


class ClaudeCodeError(RuntimeError):
    """Базовая ошибка вызова Claude Code."""


class ClaudeCodeUnavailable(ClaudeCodeError):
    """`claude` не установлен или не найден."""


class ClaudeCodeTimeout(ClaudeCodeError):
    pass


class ClaudeCodeFailed(ClaudeCodeError):
    """Процесс завершился с ошибкой, вернул is_error или непонятный вывод."""


@dataclass
class LLMResult:
    text: str
    cost_usd: float | None = None
    duration_ms: float | None = None
    session_id: str | None = None
    raw: dict | None = None


def find_claude() -> str | None:
    s = get_settings()
    if s.claude_bin:
        return s.claude_bin if os.path.isfile(s.claude_bin) and os.access(s.claude_bin, os.X_OK) else None
    found = shutil.which("claude")
    if found:
        return found
    for p in ("~/.claude/local/claude", "~/.local/bin/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        p = os.path.expanduser(p)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def subscription_warnings() -> list[str]:
    """Что могло бы увести запросы в платный API. Пустой список — всё чисто."""
    warn = [f"{k} задана в окружении API — дочернему `claude` она не передаётся" for k in BLOCKED_ENV if os.environ.get(k)]
    if get_settings().anthropic_api_key:
        warn.append("ANTHROPIC_API_KEY задан в .env — при LLM_PROVIDER=claude_code он игнорируется")
    return warn


def child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in BLOCKED_ENV and (not k.startswith(BLOCKED_PREFIX) or k in ALLOWED_CLAUDE_VARS)}
    env["NO_COLOR"] = "1"
    return env


def build_args(binary: str, system: str | None, model: str | None) -> list[str]:
    args = [binary, "-p", "--output-format", "json", "--max-turns", "1", "--disallowedTools", *NO_TOOLS]
    if model:
        args += ["--model", model]
    if system:
        args += ["--system-prompt", system]
    return args


def parse_output(stdout: str) -> LLMResult:
    """Разбор `--output-format json`: {"type":"result","is_error":false,"result":"…", …}."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise ClaudeCodeFailed(f"не JSON на выходе claude: {stdout[:200]!r}") from e
    if isinstance(data, list):  # некоторые версии выводят массив событий — берём итоговое
        data = next((x for x in reversed(data) if isinstance(x, dict) and x.get("type") == "result"), {})
    if not isinstance(data, dict) or "result" not in data:
        raise ClaudeCodeFailed(f"в ответе нет поля result: {str(data)[:200]}")
    if data.get("is_error") or data.get("subtype", "success") != "success":
        result = str(data.get("result") or "")
        hint = " — выполните вход: claude, затем /login" if "logged in" in result.lower() else ""
        raise ClaudeCodeFailed(f"claude вернул ошибку ({data.get('subtype')}): {result[:300]}{hint}")
    return LLMResult(text=str(data["result"]), cost_usd=data.get("total_cost_usd"),
                     duration_ms=data.get("duration_ms"), session_id=data.get("session_id"), raw=data)


def _prepare(system: str | None, model: str | None) -> tuple[list[str], dict[str, str]]:
    binary = find_claude()
    if not binary:
        raise ClaudeCodeUnavailable("`claude` не найден: установите Claude Code и выполните вход (claude → /login), "
                                    "или укажите путь в CLAUDE_BIN")
    for w in subscription_warnings():
        log.warning(w)
    s = get_settings()
    return build_args(binary, system, model or s.claude_model or None), child_env()


def ask_llm(prompt: str, *, system: str | None = None, timeout: float | None = None,
            model: str | None = None) -> str:
    """Синхронно: промпт → текст ответа. Бросает ClaudeCodeError (Unavailable / Timeout / Failed)."""
    return ask_llm_full(prompt, system=system, timeout=timeout, model=model).text


def ask_llm_full(prompt: str, *, system: str | None = None, timeout: float | None = None,
                 model: str | None = None) -> LLMResult:
    args, env = _prepare(system, model)
    timeout = timeout or get_settings().claude_timeout
    with tempfile.TemporaryDirectory(prefix="zhkh24-llm-") as cwd:
        try:
            proc = subprocess.run(args, input=prompt, capture_output=True, text=True, timeout=timeout,
                                  env=env, cwd=cwd, check=False)
        except subprocess.TimeoutExpired as e:
            raise ClaudeCodeTimeout(f"claude не ответил за {timeout:.0f} с") from e
        except OSError as e:
            raise ClaudeCodeUnavailable(f"не удалось запустить claude: {e}") from e
    if proc.returncode != 0 and not proc.stdout.strip():
        raise ClaudeCodeFailed(f"claude завершился с кодом {proc.returncode}: {proc.stderr.strip()[-500:]}")
    return parse_output(proc.stdout)


async def ask_llm_async(prompt: str, *, system: str | None = None, timeout: float | None = None,
                        model: str | None = None) -> LLMResult:
    """Асинхронный вариант для FastAPI. Одновременно — не больше CLAUDE_MAX_PARALLEL процессов."""
    global _sem
    s = get_settings()
    if _sem is None:
        _sem = asyncio.Semaphore(max(1, s.claude_max_parallel))
    args, env = _prepare(system, model)
    timeout = timeout or s.claude_timeout
    async with _sem:
        with tempfile.TemporaryDirectory(prefix="zhkh24-llm-") as cwd:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, env=env, cwd=cwd)
            except OSError as e:
                raise ClaudeCodeUnavailable(f"не удалось запустить claude: {e}") from e
            try:
                out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout)
            except asyncio.TimeoutError as e:
                proc.kill()
                await proc.wait()
                raise ClaudeCodeTimeout(f"claude не ответил за {timeout:.0f} с") from e
    stdout = out.decode(errors="replace")
    if proc.returncode != 0 and not stdout.strip():
        raise ClaudeCodeFailed(f"claude завершился с кодом {proc.returncode}: {err.decode(errors='replace').strip()[-500:]}")
    return parse_output(stdout)
