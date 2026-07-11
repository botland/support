from __future__ import annotations

import json
import re

from ..schemas import DiagnosisResult


class DiagnosisParseError(ValueError):
    pass


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_REQUIRED = ("verdict", "summary", "confidence", "recommended_actions")


def _iter_json_values(text: str):
    """Yield successive JSON values (supports concatenated objects)."""
    stripped = text.strip()
    if not stripped:
        return
    decoder = json.JSONDecoder()
    index = 0
    length = len(stripped)
    while index < length:
        while index < length and stripped[index] not in "{[":
            index += 1
        if index >= length:
            break
        try:
            obj, end = decoder.raw_decode(stripped, index)
            yield obj
            index = end
        except json.JSONDecodeError:
            index += 1


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

    for obj in _iter_json_values(stripped):
        return obj
    raise DiagnosisParseError("No JSON object found in CLI output")


def _is_diagnosis(obj: object) -> bool:
    return isinstance(obj, dict) and all(key in obj for key in _REQUIRED)


def _diagnoses_from_text(text: object) -> list[dict]:
    if isinstance(text, dict) and _is_diagnosis(text):
        return [text]
    if not isinstance(text, str):
        return []
    found = [obj for obj in _iter_json_values(text) if _is_diagnosis(obj)]
    if found:
        return found
    fence = _FENCE_RE.search(text)
    if fence:
        return [obj for obj in _iter_json_values(fence.group(1)) if _is_diagnosis(obj)]
    return []


def _extract_diagnosis_dict(payload: object) -> dict | None:
    """Pull DiagnosisResult from a plain object or Grok headless envelope."""
    if not isinstance(payload, dict):
        return None
    # Prefer final schema-validated object from Grok headless
    structured = payload.get("structuredOutput")
    if _is_diagnosis(structured):
        return structured  # type: ignore[return-value]
    if _is_diagnosis(payload):
        return payload
    if "text" in payload:
        candidates = _diagnoses_from_text(payload["text"])
        if candidates:
            return candidates[-1]
    for key in ("result", "data", "output"):
        nested = payload.get(key)
        if _is_diagnosis(nested):
            return nested  # type: ignore[return-value]
        if isinstance(nested, dict):
            extracted = _extract_diagnosis_dict(nested)
            if extracted is not None:
                return extracted
    return None


def parse_diagnosis_result(stdout: str) -> DiagnosisResult:
    try:
        payload = _loads_first_object(stdout)
    except json.JSONDecodeError as exc:
        raise DiagnosisParseError(f"Invalid JSON from CLI: {exc}") from exc

    extracted = _extract_diagnosis_dict(payload)
    if extracted is None and isinstance(payload, dict) is False:
        raise DiagnosisParseError("CLI JSON is not an object")
    if extracted is None:
        # Concatenated DiagnosisResult objects without envelope
        candidates = _diagnoses_from_text(stdout)
        extracted = candidates[-1] if candidates else None
    if extracted is None:
        raise DiagnosisParseError("CLI JSON is not a DiagnosisResult object")
    return DiagnosisResult.model_validate(extracted)
