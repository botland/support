from __future__ import annotations

import re
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r'"hf_token"\s*:\s*"[^"]+"'),
    re.compile(r'"password"\s*:\s*"[^"]+"'),
    re.compile(r'"secret"\s*:\s*"[^"]+"'),
]

SENSITIVE_KEYS = frozenset(
    {"hf_token", "password", "secret", "api_token", "token", "credentials"}
)


def _scrub_value(key: str, value: Any) -> Any:
    if key in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return scrub_dict(value)
    if isinstance(value, list):
        return [_scrub_value("", item) if not isinstance(item, (dict, list)) else scrub_object(item) for item in value]
    if isinstance(value, str):
        scrubbed = value
        for pattern in SECRET_PATTERNS:
            scrubbed = pattern.sub("[REDACTED]", scrubbed)
        return scrubbed
    return value


def scrub_object(value: Any) -> Any:
    if isinstance(value, dict):
        return scrub_dict(value)
    if isinstance(value, list):
        return [scrub_object(item) for item in value]
    if isinstance(value, str):
        scrubbed = value
        for pattern in SECRET_PATTERNS:
            scrubbed = pattern.sub("[REDACTED]", scrubbed)
        return scrubbed
    return value


def scrub_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: _scrub_value(key, value) for key, value in data.items()}


def contains_secrets(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)