from __future__ import annotations

import os

from .cli import SubprocessCLIAdapter
from .errors import CLIPermanentError
from .stub import StubAICliAdapter


def get_adapter():
    name = os.environ.get("AI_CLI_ADAPTER", "stub").lower()
    if name == "stub":
        return StubAICliAdapter()
    if name == "cli":
        return SubprocessCLIAdapter()
    raise CLIPermanentError(f"Unknown AI_CLI_ADAPTER: {name}")