from __future__ import annotations

import json
import re

from ..schemas import DiagnosisResult


class DiagnosisParseError(ValueError):
    pass


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_json_blob(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise DiagnosisParseError("CLI produced empty output")

    fence = _FENCE_RE.search(stripped)
    if fence:
        return fence.group(1).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise DiagnosisParseError("No JSON object found in CLI output")
    return stripped[start : end + 1]


def parse_diagnosis_result(stdout: str) -> DiagnosisResult:
    try:
        payload = json.loads(_extract_json_blob(stdout))
    except json.JSONDecodeError as exc:
        raise DiagnosisParseError(f"Invalid JSON from CLI: {exc}") from exc
    return DiagnosisResult.model_validate(payload)