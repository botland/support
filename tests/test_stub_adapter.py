from __future__ import annotations

import pytest

from src.ai.stub import StubAICliAdapter
from src.schemas import DiagnosticBundle, SoftwareVersions, TopologySummary


@pytest.mark.asyncio
async def test_stub_oom_operator_actionable():
    bundle = DiagnosticBundle(
        appliance_id="x",
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
            "actual": {"exit_code": 1, "log_snippet": ""},
        },
    )
    result = await StubAICliAdapter().diagnose(bundle=bundle, code_roots=[], prompt_template="")
    assert result.verdict == "operator_actionable"
    assert result.confidence == "high"