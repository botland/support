from __future__ import annotations

import time

from .settings import guide_settings

_message_counts: dict[str, list[float]] = {}


def clear_rate_limits() -> None:
    _message_counts.clear()


def rate_limit_ok(client_key: str) -> bool:
    """Sliding 1-hour window per client key. Limit from GUIDE_RATE_LIMIT_PER_HOUR."""
    limit = guide_settings()["rate_limit_per_hour"]
    now = time.time()
    window = _message_counts.setdefault(client_key, [])
    window[:] = [ts for ts in window if now - ts < 3600]
    if len(window) >= limit:
        return False
    window.append(now)
    return True
