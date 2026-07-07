from __future__ import annotations

import json
import os
from pathlib import Path

from ..schemas import DiagnosticBundle

DEFAULT_PROMPT_FILE = (
    Path(__file__).resolve().parents[2] / "prompts" / "diagnose.txt"
)


def load_prompt_template() -> str:
    override = os.environ.get("AI_PROMPT_TEMPLATE_PATH", "").strip()
    path = Path(override) if override else DEFAULT_PROMPT_FILE
    if not path.is_file():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(
    *,
    template: str,
    bundle: DiagnosticBundle,
    code_roots: list[Path],
) -> str:
    roots = "\n".join(f"- {root}" for root in code_roots) if code_roots else "- (none available)"
    bundle_json = json.dumps(bundle.model_dump(), indent=2, sort_keys=True)
    user_note = bundle.user_note.strip() or "(none)"
    return (
        template.replace("{bundle_json}", bundle_json)
        .replace("{code_roots}", roots)
        .replace("{user_note}", user_note)
    )