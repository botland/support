from __future__ import annotations

import os
from pathlib import Path


def default_knowledge_root() -> Path:
    env = os.environ.get("GUIDE_KNOWLEDGE_ROOT", "").strip()
    if env:
        return Path(env)
    # Repo layout: appliance-support/knowledge/product-guide
    return Path(__file__).resolve().parents[2] / "knowledge" / "product-guide"


def default_prompt_path() -> Path:
    env = os.environ.get("GUIDE_PROMPT_PATH", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "prompts" / "product-guide.txt"


def load_guide_prompt_template() -> str:
    path = default_prompt_path()
    return path.read_text(encoding="utf-8")


def format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior messages)"
    lines: list[str] = []
    for item in history:
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def render_guide_prompt(
    *,
    template: str,
    user_message: str,
    history: list[dict],
    locale: str = "en",
) -> str:
    return (
        template.replace("{locale}", locale or "en")
        .replace("{history}", format_history(history))
        .replace("{user_message}", user_message)
    )


def knowledge_index(knowledge_root: Path | None = None) -> str:
    root = knowledge_root or default_knowledge_root()
    if not root.is_dir():
        return ""
    parts: list[str] = []
    for path in sorted(root.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        parts.append(f"### {path.name}\n{text.strip()}\n")
    return "\n".join(parts)
