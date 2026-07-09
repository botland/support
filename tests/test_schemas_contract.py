from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.schemas import DiagnosisResult, DiagnosticBundle

from tests.helpers.contracts import contracts_root, load_contract


def test_golden_bundle_validates_with_pydantic():
    bundle = load_contract("diagnostic-bundle.v1.golden.json")
    DiagnosticBundle.model_validate(bundle)


def test_golden_bundle_matches_local_fixture():
    local = json.loads(
        (Path(__file__).parent / "fixtures" / "sample-bundle.json").read_text(encoding="utf-8")
    )
    golden = load_contract("diagnostic-bundle.v1.golden.json")
    assert local["appliance_id"] == golden["appliance_id"]
    assert local["bundle_version"] == golden["bundle_version"]


@pytest.mark.parametrize(
    "case",
    load_contract("diagnosis-results.golden.json")["cases"],
    ids=lambda c: c["id"],
)
def test_diagnosis_result_literals_accept_golden_verdicts(case):
    DiagnosisResult(
        verdict=case["expected_verdict"],
        summary="contract",
        confidence=case["expected_confidence"],
        recommended_actions=["a"],
    )


def test_json_schema_files_exist():
    root = Path(__file__).resolve().parents[1] / "schemas"
    assert (root / "diagnostic-bundle.v1.json").is_file()
    assert (root / "diagnosis-result.v1.json").is_file()


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("jsonschema"),
    reason="jsonschema optional dev dependency",
)
def test_golden_bundle_validates_against_json_schema():
    import jsonschema

    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "diagnostic-bundle.v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    bundle = load_contract("diagnostic-bundle.v1.golden.json")
    jsonschema.validate(bundle, schema)