from __future__ import annotations

import os

from .errors import CLIPermanentError
from .guide_cli import SubprocessGuideAdapter
from .guide_stub import StubGuideAdapter


def get_guide_adapter():
    name = os.environ.get("GUIDE_AI_ADAPTER", "stub").strip().lower()
    if name == "stub":
        return StubGuideAdapter()
    if name == "cli":
        return SubprocessGuideAdapter()
    raise CLIPermanentError(f"Unknown GUIDE_AI_ADAPTER: {name}")
