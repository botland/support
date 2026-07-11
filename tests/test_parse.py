from __future__ import annotations

import json

import pytest

from src.ai.parse import DiagnosisParseError, parse_diagnosis_result


def test_parse_plain_json():
    raw = """
    {
      "verdict": "likely_bug",
      "summary": "test",
      "confidence": "high",
      "recommended_actions": ["step 1"]
    }
    """
    result = parse_diagnosis_result(raw)
    assert result.verdict == "likely_bug"
    assert result.recommended_actions == ["step 1"]


def test_parse_fenced_json():
    raw = """Here is the result:
```json
{
  "verdict": "operator_actionable",
  "summary": "fix config",
  "confidence": "medium",
  "recommended_actions": ["check nodes"]
}
```
"""
    result = parse_diagnosis_result(raw)
    assert result.verdict == "operator_actionable"


def test_parse_invalid_raises():
    with pytest.raises(DiagnosisParseError):
        parse_diagnosis_result("not json at all")


def test_parse_tolerates_trailing_garbage():
    raw = (
        '{"verdict":"unknown","summary":"s","confidence":"low",'
        '"recommended_actions":[]} trailing prose'
    )
    result = parse_diagnosis_result(raw)
    assert result.verdict == "unknown"


def test_parse_grok_envelope_text():
    raw = (
        '{"text":"{\\"verdict\\":\\"likely_bug\\",\\"summary\\":\\"x\\",'
        '\\"confidence\\":\\"high\\",\\"recommended_actions\\":[\\"a\\"]}",'
        '"stopReason":"end"}'
    )
    result = parse_diagnosis_result(raw)
    assert result.verdict == "likely_bug"


def test_parse_grok_prefers_structured_output_over_intermediate_text():
    """Grok multi-turn: text concatenates placeholders; structuredOutput is final."""
    intermediate = (
        '{"verdict":"insufficient_data","summary":"Investigating…",'
        '"confidence":"low","recommended_actions":["reading"]}'
    )
    final = {
        "verdict": "operator_actionable",
        "summary": "GPU OOM on 8GB card",
        "confidence": "high",
        "recommended_actions": ["use GPTQ", "lower context"],
    }
    raw = json.dumps(
        {
            "text": intermediate + json.dumps(final),
            "stopReason": "EndTurn",
            "structuredOutput": final,
        }
    )
    result = parse_diagnosis_result(raw)
    assert result.verdict == "operator_actionable"
    assert result.confidence == "high"
    assert "GPTQ" in result.recommended_actions[0]


def test_parse_grok_last_concatenated_text_when_no_structured_output():
    first = (
        '{"verdict":"insufficient_data","summary":"start",'
        '"confidence":"low","recommended_actions":["a"]}'
    )
    last = (
        '{"verdict":"likely_bug","summary":"final",'
        '"confidence":"medium","recommended_actions":["b"]}'
    )
    raw = json.dumps({"text": first + last, "stopReason": "EndTurn"})
    result = parse_diagnosis_result(raw)
    assert result.verdict == "likely_bug"
    assert result.summary == "final"