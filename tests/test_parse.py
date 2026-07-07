from __future__ import annotations

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