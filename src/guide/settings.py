from __future__ import annotations

import os
from functools import lru_cache


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


@lru_cache(maxsize=1)
def guide_settings() -> dict:
    """All guide limits/toggles from env (cached for process life)."""
    return {
        "max_message_chars": _int("GUIDE_MAX_MESSAGE_CHARS", 2000),
        "max_history_turns": _int("GUIDE_MAX_HISTORY_TURNS", 12),
        "session_ttl_hours": _int("GUIDE_SESSION_TTL_HOURS", 24),
        "max_messages_per_session": _int("GUIDE_MAX_MESSAGES_PER_SESSION", 40),
        "rate_limit_per_hour": _int("GUIDE_RATE_LIMIT_PER_HOUR", 20),
        "service_token": os.environ.get("GUIDE_SERVICE_TOKEN", "").strip(),
        "knowledge_root": os.environ.get(
            "GUIDE_KNOWLEDGE_ROOT",
            "",
        ).strip(),
        "prompt_path": os.environ.get("GUIDE_PROMPT_PATH", "").strip(),
        "stream_chunk_chars": _int("GUIDE_STREAM_CHUNK_CHARS", 48),
        "require_token": _truthy("GUIDE_REQUIRE_TOKEN", "false"),
    }


def clear_guide_settings_cache() -> None:
    guide_settings.cache_clear()
