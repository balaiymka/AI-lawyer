"""Обёртка над `claude -p`: настоящие подпроцессы, но вместо claude — поддельный скрипт."""

import json
import stat
import textwrap

import pytest

from app.core.config import get_settings
from app.services.lawyer import generator as gen
from app.services.lawyer.schema import Assessment, LawyerAnswer
from app.services.llm import claude_code as cc

FAKE = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os, sys, time
    prompt = sys.stdin.read()
    mode = os.environ.get("FAKE_MODE", "ok")
    if mode == "sleep":
        time.sleep(5)
    if mode == "crash":
        print("boom", file=sys.stderr); sys.exit(3)
    if mode == "lawyer":
        print(open(os.environ["FAKE_ANSWER"]).read()); sys.exit(0)
    report = {{
        "prompt": prompt,
        "args": sys.argv[1:],
        "leaked": sorted(k for k in os.environ if k.startswith(("ANTHROPIC", "CLAUDE")) and k != "CLAUDE_CONFIG_DIR"),
        "cwd_empty": os.listdir(os.getcwd()) == [],
    }}
    out = {{"type": "result", "subtype": "success", "is_error": mode == "error",
           "result": json.dumps(report), "total_cost_usd": 0.0, "duration_ms": 12}}
    print(json.dumps([{{"type": "system"}}, out]) if mode == "array" else json.dumps(out))
''')


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    path = tmp_path / "claude"
    path.write_text(FAKE.format())
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    s = get_settings()
    monkeypatch.setattr(s, "claude_bin", str(path))
    monkeypatch.setattr(s, "claude_timeout", 10.0)
    monkeypatch.setattr(s, "claude_model", "")
    monkeypatch.setattr(cc, "_sem", None)
    return monkeypatch


def test_prompt_via_stdin_and_no_paid_api_env(fake_claude):
    fake_claude.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    fake_claude.setenv("ANTHROPIC_BASE_URL", "http://proxy")
    fake_claude.setenv("CLAUDE_CODE_SESSION_ID", "outer-session")
    report = json.loads(cc.ask_llm("Привет, «кавычки» и $(rm -rf /)", system="Ты юрист"))
    assert report["prompt"] == "Привет, «кавычки» и $(rm -rf /)"
    assert report["leaked"] == []
    assert report["cwd_empty"] is True
    args = report["args"]
    assert args[:3] == ["-p", "--output-format", "json"]
    assert "--disallowedTools" in args and "Bash" in args
    assert args[args.index("--system-prompt") + 1] == "Ты юрист"
    assert any("ANTHROPIC_API_KEY" in w for w in cc.subscription_warnings())


def test_model_flag_only_when_configured(fake_claude):
    assert "--model" not in json.loads(cc.ask_llm("x"))["args"]
    fake_claude.setattr(get_settings(), "claude_model", "sonnet")
    args = json.loads(cc.ask_llm("x"))["args"]
    assert args[args.index("--model") + 1] == "sonnet"


def test_array_output_is_supported(fake_claude):
    fake_claude.setenv("FAKE_MODE", "array")
    assert json.loads(cc.ask_llm("x"))["prompt"] == "x"


@pytest.mark.parametrize(("mode", "exc"), [("error", cc.ClaudeCodeFailed), ("crash", cc.ClaudeCodeFailed),
                                           ("sleep", cc.ClaudeCodeTimeout)])
def test_errors(fake_claude, mode, exc):
    fake_claude.setenv("FAKE_MODE", mode)
    with pytest.raises(exc):
        cc.ask_llm("x", timeout=1)


def test_missing_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "claude_bin", str(tmp_path / "nope"))
    with pytest.raises(cc.ClaudeCodeUnavailable):
        cc.ask_llm("x")


def test_parse_output_rejects_garbage():
    with pytest.raises(cc.ClaudeCodeFailed):
        cc.parse_output("Error: not logged in")
    with pytest.raises(cc.ClaudeCodeFailed):
        cc.parse_output(json.dumps({"type": "result", "subtype": "error_max_turns", "result": ""}))


async def test_async_timeout_and_success(fake_claude):
    res = await cc.ask_llm_async("async")
    assert json.loads(res.text)["prompt"] == "async" and res.duration_ms == 12
    fake_claude.setenv("FAKE_MODE", "sleep")
    with pytest.raises(cc.ClaudeCodeTimeout):
        await cc.ask_llm_async("x", timeout=1)


async def test_lawyer_answer_through_claude_code(fake_claude, tmp_path):
    answer = LawyerAnswer(summary="Копию протокола выдают за 5 рабочих дней.",
                          assessment=Assessment(position="strong", reasoning="Прямая норма."), disclaimer="—")
    payload = {"type": "result", "subtype": "success", "is_error": False,
               "result": "```json\n" + answer.model_dump_json(exclude={"legal_basis"}) + "\n```"}
    f = tmp_path / "answer.json"
    f.write_text(json.dumps(payload, ensure_ascii=False))
    fake_claude.setenv("FAKE_MODE", "lawyer")
    fake_claude.setenv("FAKE_ANSWER", str(f))
    fake_claude.setattr(get_settings(), "llm_provider", "claude_code")
    assert gen.llm_provider() == "claude_code"
    items = [x async for x in gen.generate_answer("<context/>")]
    final = items[-1]
    assert isinstance(final, gen.Final) and final.mode == "llm"
    assert final.answer.summary.startswith("Копию протокола") and final.usage["via"] == "claude_code"


def test_provider_none_without_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "llm_provider", "claude_code")
    monkeypatch.setattr(get_settings(), "claude_bin", str(tmp_path / "nope"))
    assert gen.llm_provider() == "none" and not gen.llm_available()
