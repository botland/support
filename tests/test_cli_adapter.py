from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.ai.cli import SubprocessCLIAdapter
from src.ai.errors import CLIPermanentError
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
async def test_cli_adapter_invokes_stub_script(monkeypatch):
    monkeypatch.setenv("AI_CLI_COMMAND", f"{sys.executable} {SCRIPT}")
    monkeypatch.setenv("AI_CLI_TIMEOUT_SEC", "30")

    adapter = SubprocessCLIAdapter()
    result = await adapter.diagnose(
        bundle=_bundle(),
        code_roots=[],
        prompt_template="OOM in bundle\n{user_note}",
    )
    assert result.verdict == "operator_actionable"
    assert result.recommended_actions


@pytest.mark.asyncio
async def test_cli_adapter_requires_command(monkeypatch):
    monkeypatch.delenv("AI_CLI_COMMAND", raising=False)
    with pytest.raises(CLIPermanentError):
        SubprocessCLIAdapter()


@pytest.mark.asyncio
async def test_cli_adapter_invalid_json_is_permanent(monkeypatch):
    monkeypatch.setenv("AI_CLI_COMMAND", f"{sys.executable} -c 'print(\"not-json\")'")
    adapter = SubprocessCLIAdapter()
    with pytest.raises(CLIPermanentError):
        await adapter.diagnose(bundle=_bundle(), code_roots=[], prompt_template="test")


@pytest.mark.asyncio
async def test_cli_adapter_accepts_inline_json_command(monkeypatch):
    payload = {
        "verdict": "unknown",
        "summary": "inline",
        "confidence": "low",
        "recommended_actions": ["wait"],
    }
    code = f"import json; print(json.dumps({payload!r}))"
    monkeypatch.setenv("AI_CLI_COMMAND", f"{sys.executable} -c {json.dumps(code)}")
    adapter = SubprocessCLIAdapter()
    result = await adapter.diagnose(bundle=_bundle(), code_roots=[], prompt_template="x")
    assert result.verdict == "unknown"