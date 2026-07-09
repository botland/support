from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.ai.stub import StubAICliAdapter
from src.schemas import DiagnosticBundle, SoftwareVersions, TopologySummary

from tests.helpers.contracts import load_contract

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ai_diagnose_stub.py"


def _bundle_from_health(health: dict) -> DiagnosticBundle:
    return DiagnosticBundle(
        appliance_id="script-parity",
        submitted_at="2026-07-07T12:00:00Z",
        software=SoftwareVersions(),
        topology=TopologySummary(
            serving_mode="distributed",
            role="coordinator",
            node_count=1,
            local_node_id="node-1",
        ),
        health=health,
    )


def _run_script_prompt(prompt: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=prompt,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


@pytest.mark.asyncio
async def test_script_matches_stub_on_oom_case():
    case = next(c for c in load_contract("diagnosis-results.golden.json")["cases"] if c["id"] == "oom_last_error")
    bundle = _bundle_from_health(case["health"])
    stub = await StubAICliAdapter().diagnose(bundle=bundle, code_roots=[], prompt_template="")
    script = _run_script_prompt(f"health {bundle.health}")
    assert script["verdict"] == stub.verdict


@pytest.mark.asyncio
async def test_script_matches_stub_on_degraded_exit_case():
    case = next(c for c in load_contract("diagnosis-results.golden.json")["cases"] if c["id"] == "degraded_exit_code")
    bundle = _bundle_from_health(case["health"])
    stub = await StubAICliAdapter().diagnose(bundle=bundle, code_roots=[], prompt_template="")
    script = _run_script_prompt(
        f"state={bundle.health['state']} exit_code={bundle.health['actual']['exit_code']} degraded"
    )
    assert script["verdict"] == stub.verdict