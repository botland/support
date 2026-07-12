from __future__ import annotations

import json
import re
from typing import Any


class GuideParseError(Exception):
    pass


_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_content(obj: Any) -> str | None:
    if isinstance(obj, dict):
        if isinstance(obj.get("content"), str) and obj["content"].strip():
            return obj["content"].strip()
        # Grok envelope
        so = obj.get("structuredOutput") or obj.get("structured_output")
        if isinstance(so, dict) and isinstance(so.get("content"), str):
            return so["content"].strip()
        if isinstance(so, str) and so.strip():
            try:
                inner = json.loads(so)
                if isinstance(inner, dict) and isinstance(inner.get("content"), str):
                    return inner["content"].strip()
            except json.JSONDecodeError:
                pass
        text = obj.get("text")
        if isinstance(text, str) and text.strip():
            # try parse nested JSON from text
            nested = _find_content_in_text(text)
            if nested:
                return nested
            # plain assistant text as last resort when not schema-shaped
            if not text.lstrip().startswith("{"):
                return text.strip()
    return None


def _find_content_in_text(s: str) -> str | None:
    s = s.strip()
    if not s:
        return None
    # fenced
    for match in _FENCE.finditer(s):
        try:
            obj = json.loads(match.group(1).strip())
            content = _extract_content(obj)
            if content:
                return content
        except json.JSONDecodeError:
            continue
    # whole string JSON
    try:
        obj = json.loads(s)
        content = _extract_content(obj)
        if content:
            return content
    except json.JSONDecodeError:
        pass
    # scan for objects with "content"
    decoder = json.JSONDecoder()
    idx = 0
    last: str | None = None
    while idx < len(s):
        start = s.find("{", idx)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(s, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        content = _extract_content(obj)
        if content:
            last = content
        idx = end
    return last


def parse_guide_reply(stdout: str) -> str:
    content = _find_content_in_text(stdout)
    if content:
        return content
    stripped = (stdout or "").strip()
    if stripped and not stripped.lstrip().startswith("{"):
        return stripped
    raise GuideParseError("Could not parse guide reply from CLI output")
