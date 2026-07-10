from __future__ import annotations

import json
import re

from ..schemas import DiagnosisResult


class DiagnosisParseError(ValueError):
    pass


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _loads_first_object(text: str) -> object:
    """Parse the first JSON value; tolerate trailing garbage."""
    stripped = text.strip()
    if not stripped:
        raise DiagnosisParseError("CLI produced empty output")

    fence = _FENCE_RE.search(stripped)
    if fence:
        stripped = fence.group(1).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char not in "{[":
            continue
        try:
            obj, _end = decoder.raw_decode(stripped, index)
            return obj
        except json.JSONDecodeError:
            continue
    raise DiagnosisParseError("No JSON object found in CLI output")


def parse_diagnosis_result(stdout: str) -> DiagnosisResult:
    try:
        payload = _loads_first_object(stdout)
    except json.JSONDecodeError as exc:
        raise DiagnosisParseError(f"Invalid JSON from CLI: {exc}") from exc
    if isinstance(payload, dict) and "verdict" not in payload and isinstance(payload.get("text"), str):
        # Grok headless envelope slipped through the wrapper
        try:
            payload = _loads_first_object(payload["text"])
        except DiagnosisParseError:
            pass
    if not isinstance(payload, dict):
        raise DiagnosisParseError("CLI JSON is not an object")
    return DiagnosisResult.model_validate(payload)