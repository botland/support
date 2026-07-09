from __future__ import annotations

import json

import pytest

from src.redact import contains_secrets, scrub_dict, scrub_object

from tests.helpers.contracts import load_contract


@pytest.fixture
def redaction_contract():
    return load_contract("redaction-cases.json")


def test_sensitive_keys_match_contract(redaction_contract):
    from src.redact import SENSITIVE_KEYS

    assert set(redaction_contract["sensitive_keys"]) == set(SENSITIVE_KEYS)


@pytest.mark.parametrize("case", load_contract("redaction-cases.json")["cases"], ids=lambda c: c["id"])
def test_scrub_dict_contract_cases(case):
    if "expected" in case:
        assert scrub_dict(case["input"]) == case["expected"]
        return
    if case.get("support_must_redact"):
        raw = case["input"]["raw"]
        scrubbed = scrub_object(raw)
        assert "[REDACTED]" in scrubbed
        assert contains_secrets(scrubbed) is False


def test_scrub_object_equivalent_for_nested_dict():
    payload = {
        "hf_token": "secret",
        "nested": {"password": "x"},
        "list": [{"token": "y"}],
    }
    assert scrub_dict(payload) == scrub_object(payload)


def test_contains_secrets_detects_unscrubbed_bearer():
    assert contains_secrets('log line Bearer abc.def-ghi token')
    assert not contains_secrets(scrub_dict({"log": "Bearer abc.def-ghi"})["log"])