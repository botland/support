from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..schemas import DiagnosisResult, DiagnosticBundle


class AICliAdapter(Protocol):
    async def diagnose(
        self,
        *,
        bundle: DiagnosticBundle,
        code_roots: list[Path],
        prompt_template: str,
    ) -> DiagnosisResult: ...