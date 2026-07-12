from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

import yaml

from ..schemas import DiagnosticBundle
from .errors import CodeContextError

logger = logging.getLogger(__name__)

VERSIONS_FILE = Path(__file__).resolve().parents[2] / "code_context" / "versions.yaml"

# Stable product keys (directory names under the ticket worktree).
REPO_CONSOLE = "appliance-console"
REPO_BACKEND = "appliance-backend"

REPO_ENV_KEYS = {
    REPO_CONSOLE: "CODE_ROOT_APPLIANCE_CONSOLE",
    REPO_BACKEND: "CODE_ROOT_APPLIANCE_BACKEND",
}

# Bundle field that stamps the build ref for each product repo.
REPO_VERSION_ATTR = {
    REPO_CONSOLE: "console_version",
    REPO_BACKEND: "controller_version",
}

INVALID_VERSION_PLACEHOLDERS = frozenset({"", "unknown", "dev", "mock"})


def _worktree_root() -> Path:
    raw = os.environ.get("CODE_WORKTREE_ROOT", "").strip()
    if raw:
        return Path(raw)
    return Path(os.environ.get("SUPPORT_DATA_DIR", "/data")).resolve() / "code_worktrees"


def _load_versions() -> dict:
    if not VERSIONS_FILE.is_file():
        return {"releases": {}}
    with VERSIONS_FILE.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {"releases": {}}


def _source_repo(repo_key: str) -> Path:
    env_key = REPO_ENV_KEYS[repo_key]
    configured = os.environ.get(env_key, "").strip()
    if not configured:
        raise CodeContextError(
            f"Source clone not configured for {repo_key}",
            reason="source_not_configured",
            repo_key=repo_key,
            detail=f"Set {env_key} to a git checkout of the product repository.",
        )
    path = Path(configured)
    if not path.is_dir():
        raise CodeContextError(
            f"Source clone path missing for {repo_key}",
            reason="source_missing",
            repo_key=repo_key,
            detail=f"{env_key}={path} is not a directory",
        )
    if not (path / ".git").exists():
        raise CodeContextError(
            f"Source path is not a git repository for {repo_key}",
            reason="source_not_git",
            repo_key=repo_key,
            detail=str(path),
        )
    return path


def ticket_dir(ticket_id: str) -> Path:
    """Per-ticket isolation root: worktrees + AI artifacts live under this path."""
    return _worktree_root() / ticket_id


def ticket_ai_dir(ticket_id: str) -> Path:
    """Dynamic artifact dir for prompt/bundle/CLI logs: `{ticket_id}/_ai/`."""
    return ticket_dir(ticket_id) / "_ai"


def _ticket_dir(ticket_id: str) -> Path:
    return ticket_dir(ticket_id)


def _ticket_repo_path(ticket_id: str, repo_key: str) -> Path:
    return ticket_dir(ticket_id) / repo_key


def _safe_directory_flags(source: Path) -> list[str]:
    """Trust mounted host clones when git runs as a different user (e.g. Docker root)."""
    flags: list[str] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            flags.extend(["-c", f"safe.directory={resolved}"])

    add(source)
    git_meta = source / ".git"
    if git_meta.is_file():
        line = git_meta.read_text(encoding="utf-8", errors="replace").strip()
        if line.startswith("gitdir:"):
            gitdir = Path(line.split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = (source / gitdir).resolve()
            add(gitdir)
            # Submodule object DB lives under the parent repo's .git/modules/…
            cursor = gitdir
            while cursor.parent != cursor:
                if cursor.name == "modules":
                    add(cursor.parent.parent)
                    break
                cursor = cursor.parent

    return flags


def _run_git(source: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *_safe_directory_flags(source), "-C", str(source), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _resolve_ref(repo_key: str, version: str, releases: dict) -> str:
    """Map optional release aliases; otherwise return the version as a git ref.

    Does not accept placeholders such as dev/unknown/mock.
    """
    cleaned = (version or "").strip()
    if not cleaned or cleaned.lower() in INVALID_VERSION_PLACEHOLDERS:
        raise CodeContextError(
            f"Invalid software version for {repo_key}: {version!r}",
            reason="invalid_version",
            repo_key=repo_key,
            ref=version,
            detail="Appliance builds must stamp a git SHA or tag (not dev/unknown/mock).",
        )

    repo_map = releases.get(repo_key, {}) or {}
    if cleaned in repo_map:
        mapped = str(repo_map[cleaned]).strip()
        if not mapped or mapped.lower() in INVALID_VERSION_PLACEHOLDERS:
            raise CodeContextError(
                f"versions.yaml alias for {repo_key}/{cleaned} is invalid",
                reason="invalid_alias",
                repo_key=repo_key,
                ref=cleaned,
                detail=mapped,
            )
        return mapped
    return cleaned


def _try_rev_parse(source: Path, ref: str) -> str | None:
    result = _run_git(source, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def _looks_like_git_sha(ref: str) -> bool:
    """True for full or abbreviated hex SHAs (7–40 chars)."""
    if not 7 <= len(ref) <= 40:
        return False
    return all(c in "0123456789abcdefABCDEF" for c in ref)


def _ensure_ref(source: Path, repo_key: str, ref: str) -> str:
    """Fetch ref if needed and return the canonical commit SHA."""
    sha = _try_rev_parse(source, ref)
    if sha:
        return sha

    fetch_attempts: list[tuple[str, ...]] = []
    if _looks_like_git_sha(ref):
        # Prefer object fetch so any published commit works (any branch / prod).
        fetch_attempts.append(("fetch", "--no-tags", "origin", ref))
    fetch_attempts.extend(
        (
            ("fetch", "--no-tags", "origin", ref),
            ("fetch", "origin", f"refs/tags/{ref}:refs/tags/{ref}"),
            ("fetch", "origin", f"+refs/heads/{ref}:refs/remotes/origin/{ref}"),
        )
    )
    # Deduplicate while preserving order
    seen: set[tuple[str, ...]] = set()
    unique_attempts: list[tuple[str, ...]] = []
    for args in fetch_attempts:
        if args not in seen:
            seen.add(args)
            unique_attempts.append(args)

    fetch_errors: list[str] = []
    for args in unique_attempts:
        fetch = _run_git(source, *args)
        if fetch.returncode != 0:
            snippet = (fetch.stderr or fetch.stdout or "").strip()
            if snippet:
                fetch_errors.append(snippet[-400:])
            continue
        sha = _try_rev_parse(source, ref) or _try_rev_parse(source, f"origin/{ref}")
        if sha:
            return sha

    if fetch_errors:
        raise CodeContextError(
            f"Could not fetch ref {ref!r} for {repo_key}",
            reason="fetch_failed",
            repo_key=repo_key,
            ref=ref,
            detail=" | ".join(fetch_errors)[-800:],
        )
    raise CodeContextError(
        f"Unknown git ref {ref!r} for {repo_key}",
        reason="unknown_ref",
        repo_key=repo_key,
        ref=ref,
        detail="rev-parse failed after fetch attempts",
    )


def _remove_worktree(source: Path, dest: Path) -> None:
    if dest.exists():
        removed = _run_git(source, "worktree", "remove", "--force", str(dest))
        if removed.returncode != 0 and dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
            _run_git(source, "worktree", "prune")
    else:
        _run_git(source, "worktree", "prune")


def _add_worktree(source: Path, dest: Path, sha: str, repo_key: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        _remove_worktree(source, dest)

    result = _run_git(source, "worktree", "add", "--detach", str(dest), sha)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-800:]
        raise CodeContextError(
            f"Failed to create worktree for {repo_key} at {sha[:12]}",
            reason="worktree_failed",
            repo_key=repo_key,
            ref=sha,
            detail=detail or "git worktree add failed",
        )


def prepare_code_roots(ticket_id: str, bundle: DiagnosticBundle) -> list[Path]:
    """Create per-ticket worktrees at exact bundle SHAs/tags.

    Raises CodeContextError if any required ref is invalid or cannot be checked out.
    Partial worktrees are left for the caller to release via release_code_roots.
    """
    if not ticket_id or not ticket_id.strip():
        raise CodeContextError(
            "ticket_id is required for code context isolation",
            reason="missing_ticket_id",
        )

    releases = _load_versions().get("releases", {}) or {}
    software = bundle.software
    roots: list[Path] = []

    for repo_key in (REPO_CONSOLE, REPO_BACKEND):
        version_attr = REPO_VERSION_ATTR[repo_key]
        version = getattr(software, version_attr, "")
        ref = _resolve_ref(repo_key, version, releases)
        source = _source_repo(repo_key)
        sha = _ensure_ref(source, repo_key, ref)
        dest = _ticket_repo_path(ticket_id, repo_key)
        _add_worktree(source, dest, sha, repo_key)
        logger.info(
            "Code context worktree ready ticket=%s repo=%s ref=%s sha=%s path=%s",
            ticket_id,
            repo_key,
            ref,
            sha[:12],
            dest,
        )
        roots.append(dest)

    return roots


def release_code_roots(ticket_id: str) -> None:
    """Remove worktrees under CODE_WORKTREE_ROOT/ticket_id (idempotent)."""
    if not ticket_id or not ticket_id.strip():
        return

    ticket_path = _ticket_dir(ticket_id)
    for repo_key in (REPO_CONSOLE, REPO_BACKEND):
        dest = _ticket_repo_path(ticket_id, repo_key)
        env_key = REPO_ENV_KEYS[repo_key]
        configured = os.environ.get(env_key, "").strip()
        if configured and Path(configured).is_dir():
            try:
                _remove_worktree(Path(configured), dest)
            except OSError as exc:
                logger.warning("Worktree remove failed for %s: %s", dest, exc)
        elif dest.exists():
            shutil.rmtree(dest, ignore_errors=True)

    if ticket_path.exists():
        shutil.rmtree(ticket_path, ignore_errors=True)
        logger.info("Released code context for ticket %s", ticket_id)
