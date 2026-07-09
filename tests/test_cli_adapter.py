from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.ai.cli import (
    SubprocessCLIAdapter,
    expand_command_placeholders,
    write_diagnosis_artifacts,
)
from src.ai.errors import CLIPermanentError
from src.code_context.manager import REPO_BACKEND, REPO_CONSOLE
from src.schemas import DiagnosticBundle, SoftwareVersions, TopologySummary

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ai_diagnose_stub.py"


def _bundle() -> DiagnosticBundle:
    return DiagnosticBundle(
        appliance_id="forge-demo-001",
        submitted_at="2026-07-07T12:00:00Z",
        software=SoftwareVersions(),
        topology=TopologySummary(
            serving_mode="distributed",
            role="coordinator",
            node_count=1,
            local_node_id="node-1",
        ),
        health={
            "state": "DEGRADED",
            "last_error": "CUDA out of memory",
            "actual": {"exit_code": 1},
        },
        user_note="Model won't load",
    )


@pytest.mark.asyncio
async def test_cli_adapter_invokes_stub_script(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_CLI_COMMAND", f"{sys.executable} {SCRIPT}")
    monkeypatch.setenv("AI_CLI_TIMEOUT_SEC", "30")
    monkeypatch.setenv("CODE_WORKTREE_ROOT", str(tmp_path / "wt"))

    adapter = SubprocessCLIAdapter()
    result = await adapter.diagnose(
        bundle=_bundle(),
        code_roots=[],
        prompt_template="OOM in bundle\n{user_note}",
        ticket_id="ticket-stub-1",
    )
    assert result.verdict == "operator_actionable"
    assert result.recommended_actions
    ai_dir = tmp_path / "wt" / "ticket-stub-1" / "_ai"
    assert (ai_dir / "prompt.txt").is_file()
    assert (ai_dir / "bundle.json").is_file()
    assert (ai_dir / "cli_stdout.txt").is_file()


@pytest.mark.asyncio
async def test_cli_adapter_sets_cwd_to_backend_worktree(monkeypatch, tmp_path):
    console = tmp_path / REPO_CONSOLE
    backend = tmp_path / REPO_BACKEND
    console.mkdir()
    backend.mkdir()
    (backend / "marker.txt").write_text("backend-root\n", encoding="utf-8")

    # Print cwd and AI_CODE_ROOT for assertions
    code = (
        "import os, json; "
        "print(json.dumps({"
        "'verdict':'unknown','summary':os.getcwd(),"
        "'confidence':'low','recommended_actions':[os.environ.get('AI_CODE_ROOT','')]"
        "}))"
    )
    monkeypatch.setenv("AI_CLI_COMMAND", f"{sys.executable} -c {json.dumps(code)}")
    monkeypatch.setenv("AI_CLI_CWD", "code_root")
    monkeypatch.setenv("AI_CLI_PRIMARY_ROOT", "backend")
    monkeypatch.setenv("CODE_WORKTREE_ROOT", str(tmp_path / "wt"))

    adapter = SubprocessCLIAdapter()
    result = await adapter.diagnose(
        bundle=_bundle(),
        code_roots=[console, backend],
        prompt_template="x",
        ticket_id="ticket-cwd",
    )
    assert Path(result.summary).resolve() == backend.resolve()
    assert Path(result.recommended_actions[0]).resolve() == backend.resolve()


@pytest.mark.asyncio
async def test_cli_adapter_requires_command(monkeypatch):
    monkeypatch.delenv("AI_CLI_COMMAND", raising=False)
    with pytest.raises(CLIPermanentError):
        SubprocessCLIAdapter()


@pytest.mark.asyncio
async def test_cli_adapter_invalid_json_is_permanent(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_CLI_COMMAND", f"{sys.executable} -c 'print(\"not-json\")'")
    monkeypatch.setenv("CODE_WORKTREE_ROOT", str(tmp_path / "wt"))
    adapter = SubprocessCLIAdapter()
    with pytest.raises(CLIPermanentError):
        await adapter.diagnose(
            bundle=_bundle(),
            code_roots=[],
            prompt_template="test",
            ticket_id="ticket-bad-json",
        )


@pytest.mark.asyncio
async def test_cli_adapter_accepts_inline_json_command(monkeypatch, tmp_path):
    payload = {
        "verdict": "unknown",
        "summary": "inline",
        "confidence": "low",
        "recommended_actions": ["wait"],
    }
    code = f"import json; print(json.dumps({payload!r}))"
    monkeypatch.setenv("AI_CLI_COMMAND", f"{sys.executable} -c {json.dumps(code)}")
    monkeypatch.setenv("CODE_WORKTREE_ROOT", str(tmp_path / "wt"))
    adapter = SubprocessCLIAdapter()
    result = await adapter.diagnose(
        bundle=_bundle(),
        code_roots=[],
        prompt_template="x",
        ticket_id="ticket-inline",
    )
    assert result.verdict == "unknown"


def test_expand_command_placeholders():
    cmd = expand_command_placeholders(
        ["tool", "--prompt", "{prompt_file}", "--root", "{code_root}", "{ticket_id}"],
        prompt_file="/t/_ai/prompt.txt",
        bundle_file="/t/_ai/bundle.json",
        code_root="/t/appliance-backend",
        code_roots="/t/console:/t/backend",
        ticket_id="abc",
    )
    assert cmd == ["tool", "--prompt", "/t/_ai/prompt.txt", "--root", "/t/appliance-backend", "abc"]


def test_write_diagnosis_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("CODE_WORKTREE_ROOT", str(tmp_path))
    bundle = _bundle()
    ai_dir, prompt_path, bundle_path = write_diagnosis_artifacts(
        ticket_id="tid-1",
        bundle=bundle,
        prompt="hello prompt",
        code_roots=[tmp_path / "a", tmp_path / "b"],
    )
    assert ai_dir == tmp_path / "tid-1" / "_ai"
    assert prompt_path.read_text(encoding="utf-8") == "hello prompt"
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert data["appliance_id"] == "forge-demo-001"
    assert "a" in (ai_dir / "code_roots.txt").read_text(encoding="utf-8")
