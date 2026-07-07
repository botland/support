from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.code_context.manager import _resolve_ref, resolve_code_roots
from src.schemas import DiagnosticBundle


@pytest.fixture
def sample_bundle() -> DiagnosticBundle:
    raw = json.loads((Path(__file__).parent / "fixtures" / "sample-bundle.json").read_text())
    return DiagnosticBundle.model_validate(raw)


def test_resolve_ref_unknown_falls_back_to_main():
    assert _resolve_ref("inferedge-phase1", "unknown-sha", {}) == "unknown-sha"
    assert _resolve_ref("inferedge-phase1", "dev", {}) == "main"


def test_resolve_code_roots_uses_monorepo_paths(sample_bundle, monkeypatch):
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("CODE_ROOT_INFEREDGE_PHASE1", str(repo_root / "inferedge-phase1"))
    monkeypatch.setenv("CODE_ROOT_APPLIANCE_CONSOLE", str(repo_root / "appliance-console"))

    roots = resolve_code_roots(sample_bundle)
    assert len(roots) == 2
    assert any(path.name == "inferedge-phase1" for path in roots)
    assert any(path.name == "appliance-console" for path in roots)