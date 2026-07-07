from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

import yaml

from ..schemas import DiagnosticBundle, SoftwareVersions

logger = logging.getLogger(__name__)

VERSIONS_FILE = Path(__file__).resolve().parents[2] / "code_context" / "versions.yaml"
DEFAULT_REPOS = {
    "inferedge-phase1": "inferedge-phase1",
    "appliance-console": "appliance-console",
}


def _load_versions() -> dict:
    if not VERSIONS_FILE.is_file():
        return {"releases": {}}
    with VERSIONS_FILE.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {"releases": {}}


def _repo_env_key(name: str) -> str:
    return f"CODE_ROOT_{name.upper().replace('-', '_')}"


def _resolve_ref(repo_key: str, version: str, releases: dict) -> str:
    repo_map = releases.get(repo_key, {})
    if version in repo_map:
        return str(repo_map[version])
    if version and version not in ("unknown", "dev", "mock"):
        return version
    return "main"


def _git_checkout(repo_path: Path, ref: str) -> None:
    if not (repo_path / ".git").exists():
        logger.warning("Code root is not a git repo: %s", repo_path)
        return
    subprocess.run(
        ["git", "-C", str(repo_path), "fetch", "--depth", "1", "origin", ref],
        check=False,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        ["git", "-C", str(repo_path), "checkout", "--detach", ref],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fallback = subprocess.run(
            ["git", "-C", str(repo_path), "checkout", "--detach", "main"],
            check=False,
            capture_output=True,
            text=True,
        )
        if fallback.returncode != 0:
            logger.warning("Could not checkout %s in %s: %s", ref, repo_path, result.stderr.strip())


def resolve_code_roots(bundle: DiagnosticBundle) -> list[Path]:
    """Return read-only repository roots for the reported software versions."""
    releases = _load_versions().get("releases", {})
    software: SoftwareVersions = bundle.software
    version_map = {
        "inferedge-phase1": software.controller_version,
        "appliance-console": software.console_version,
    }

    roots: list[Path] = []
    for repo_key, default_dir in DEFAULT_REPOS.items():
        env_key = _repo_env_key(repo_key)
        configured = os.environ.get(env_key, "").strip()
        if configured:
            repo_path = Path(configured)
        else:
            candidate = Path(__file__).resolve().parents[3] / default_dir
            repo_path = candidate if candidate.is_dir() else None
        if repo_path is None or not repo_path.is_dir():
            logger.info("Code root unavailable for %s", repo_key)
            continue

        ref = _resolve_ref(repo_key, version_map.get(repo_key, "dev"), releases)
        try:
            _git_checkout(repo_path, ref)
        except OSError as exc:
            logger.warning("Checkout failed for %s@%s: %s", repo_path, ref, exc)
        roots.append(repo_path)

    return roots