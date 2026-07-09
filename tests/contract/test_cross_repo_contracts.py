from __future__ import annotations

import pytest

from src.ai.stub import StubAICliAdapter
from src.schemas import DiagnosticBundle, SoftwareVersions, TopologySummary

from tests.helpers.contracts import load_contract


def _matches_stub_oom_signals(text: str, signals: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(sig in lowered for sig in signals)


def test_oom_markers_contract_stub_signals():
    contract = load_contract("oom-markers.json")
    signals = tuple(contract["stub_oom_signals"])
    matching = [m for m in contract["permanent_messages"] if _matches_stub_oom_signals(m, signals)]
    assert matching, "expected at least one permanent message to match stub OOM signals"


def test_log_tail_limits_contract():
    limits = load_contract("log-tail-limits.json")
    assert limits["maxLines"] == 200
    assert limits["maxBytes"] == 65536


def test_diagnostic_bundle_golden_validates():
    from src.schemas import DiagnosticBundle

    bundle = load_contract("diagnostic-bundle.v1.golden.json")
    parsed = DiagnosticBundle.model_validate(bundle)
    assert parsed.software.support_client_version == "1.0.0"


@pytest.mark.asyncio
async def test_stub_matches_diagnosis_golden_matrix():
    contract = load_contract("diagnosis-results.golden.json")
    adapter = StubAICliAdapter()
    for case in contract["cases"]:
        bundle = DiagnosticBundle(
            appliance_id="contract-test",
            submitted_at="2026-07-07T12:00:00Z",
            software=SoftwareVersions(),
            topology=TopologySummary(
                serving_mode="distributed",
                role="coordinator",
                node_count=1,
                local_node_id="node-1",
            ),
            health=case["health"],
        )
        result = await adapter.diagnose(bundle=bundle, code_roots=[], prompt_template="")
        assert result.verdict == case["expected_verdict"], case["id"]
        assert result.confidence == case["expected_confidence"], case["id"]