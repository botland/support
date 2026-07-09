from __future__ import annotations

import pytest

from src.ai.stub import StubAICliAdapter
from src.schemas import DiagnosticBundle, SoftwareVersions, TopologySummary

from tests.helpers.contracts import load_contract


def _bundle_from_health(health: dict) -> DiagnosticBundle:
    return DiagnosticBundle(
        appliance_id="stub-contract",
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    load_contract("diagnosis-results.golden.json")["cases"],
    ids=lambda c: c["id"],
)
async def test_stub_verdict_matrix(case):
    adapter = StubAICliAdapter()
    result = await adapter.diagnose(
        bundle=_bundle_from_health(case["health"]),
        code_roots=[],
        prompt_template="",
    )
    assert result.verdict == case["expected_verdict"]
    assert result.confidence == case["expected_confidence"]