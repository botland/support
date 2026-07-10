from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.code_context.errors import CodeContextError
from src.code_context.manager import (
    REPO_BACKEND,
    REPO_CONSOLE,
    _resolve_ref,
    _safe_directory_flags,
    prepare_code_roots,
    release_code_roots,
)
from src.schemas import DiagnosticBundle


@pytest.fixture
def sample_bundle() -> DiagnosticBundle:
    raw = json.loads((Path(__file__).parent / "fixtures" / "sample-bundle.json").read_text())
    return DiagnosticBundle.model_validate(raw)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(path: Path, first_message: str = "init") -> str:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "README.md").write_text(f"{first_message}\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", first_message)
    return _git(path, "rev-parse", "HEAD")


def test_resolve_ref_rejects_placeholders():
    with pytest.raises(CodeContextError) as exc:
        _resolve_ref(REPO_BACKEND, "dev", {})
    assert exc.value.reason == "invalid_version"

    with pytest.raises(CodeContextError):
        _resolve_ref(REPO_CONSOLE, "unknown", {})

    with pytest.raises(CodeContextError):
        _resolve_ref(REPO_CONSOLE, "", {})


def test_resolve_ref_uses_alias_and_passthrough_sha():
    releases = {REPO_CONSOLE: {"1.0.0": "abc123def"}}
    assert _resolve_ref(REPO_CONSOLE, "1.0.0", releases) == "abc123def"
    assert _resolve_ref(REPO_BACKEND, "deadbeefcafebabe", {}) == "deadbeefcafebabe"


def test_prepare_and_release_isolated_worktrees(tmp_path, monkeypatch, sample_bundle):
    console_src = tmp_path / "console-src"
    backend_src = tmp_path / "backend-src"
    work_root = tmp_path / "worktrees"

    sha_console_a = _init_repo(console_src, "console-a")
    (console_src / "README.md").write_text("console-b\n", encoding="utf-8")
    _git(console_src, "add", "README.md")
    _git(console_src, "commit", "-m", "console-b")
    sha_console_b = _git(console_src, "rev-parse", "HEAD")

    sha_backend_a = _init_repo(backend_src, "backend-a")
    (backend_src / "README.md").write_text("backend-b\n", encoding="utf-8")
    _git(backend_src, "add", "README.md")
    _git(backend_src, "commit", "-m", "backend-b")
    sha_backend_b = _git(backend_src, "rev-parse", "HEAD")

    source_console_head = _git(console_src, "rev-parse", "HEAD")
    source_backend_head = _git(backend_src, "rev-parse", "HEAD")

    monkeypatch.setenv("CODE_ROOT_APPLIANCE_CONSOLE", str(console_src))
    monkeypatch.setenv("CODE_ROOT_APPLIANCE_BACKEND", str(backend_src))
    monkeypatch.setenv("CODE_WORKTREE_ROOT", str(work_root))

    bundle_a = sample_bundle.model_copy(deep=True)
    bundle_a.software.console_version = sha_console_a
    bundle_a.software.controller_version = sha_backend_a

    bundle_b = sample_bundle.model_copy(deep=True)
    bundle_b.software.console_version = sha_console_b
    bundle_b.software.controller_version = sha_backend_b

    roots_a = prepare_code_roots("ticket-a", bundle_a)
    roots_b = prepare_code_roots("ticket-b", bundle_b)

    assert len(roots_a) == 2
    assert len(roots_b) == 2
    assert roots_a[0].name == REPO_CONSOLE
    assert roots_a[1].name == REPO_BACKEND

    assert _git(roots_a[0], "rev-parse", "HEAD") == sha_console_a
    assert _git(roots_a[1], "rev-parse", "HEAD") == sha_backend_a
    assert _git(roots_b[0], "rev-parse", "HEAD") == sha_console_b
    assert _git(roots_b[1], "rev-parse", "HEAD") == sha_backend_b

    # Source clones are not moved for diagnosis.
    assert _git(console_src, "rev-parse", "HEAD") == source_console_head
    assert _git(backend_src, "rev-parse", "HEAD") == source_backend_head

    release_code_roots("ticket-a")
    release_code_roots("ticket-b")
    assert not (work_root / "ticket-a").exists()
    assert not (work_root / "ticket-b").exists()


def test_prepare_rejects_dev_versions(tmp_path, monkeypatch, sample_bundle):
    console_src = tmp_path / "console-src"
    backend_src = tmp_path / "backend-src"
    _init_repo(console_src)
    _init_repo(backend_src)
    monkeypatch.setenv("CODE_ROOT_APPLIANCE_CONSOLE", str(console_src))
    monkeypatch.setenv("CODE_ROOT_APPLIANCE_BACKEND", str(backend_src))
    monkeypatch.setenv("CODE_WORKTREE_ROOT", str(tmp_path / "worktrees"))

    with pytest.raises(CodeContextError) as exc:
        prepare_code_roots("ticket-dev", sample_bundle)
    assert exc.value.reason == "invalid_version"


def test_prepare_tag_checkout(tmp_path, monkeypatch, sample_bundle):
    console_src = tmp_path / "console-src"
    backend_src = tmp_path / "backend-src"
    sha_console = _init_repo(console_src, "console")
    sha_backend = _init_repo(backend_src, "backend")
    _git(console_src, "tag", "v1.2.3")
    _git(backend_src, "tag", "v1.2.3")

    monkeypatch.setenv("CODE_ROOT_APPLIANCE_CONSOLE", str(console_src))
    monkeypatch.setenv("CODE_ROOT_APPLIANCE_BACKEND", str(backend_src))
    monkeypatch.setenv("CODE_WORKTREE_ROOT", str(tmp_path / "worktrees"))

    bundle = sample_bundle.model_copy(deep=True)
    bundle.software.console_version = "v1.2.3"
    bundle.software.controller_version = "v1.2.3"

    roots = prepare_code_roots("ticket-tag", bundle)
    assert _git(roots[0], "rev-parse", "HEAD") == sha_console
    assert _git(roots[1], "rev-parse", "HEAD") == sha_backend
    release_code_roots("ticket-tag")


def test_safe_directory_flags_include_submodule_parent(tmp_path):
    submodule = tmp_path / "console"
    submodule.mkdir()
    parent = tmp_path / "monorepo"
    parent.mkdir()
    (parent / ".git" / "modules" / "console").mkdir(parents=True)
    (submodule / ".git").write_text("gitdir: ../monorepo/.git/modules/console\n", encoding="utf-8")

    flags = _safe_directory_flags(submodule)
    joined = " ".join(flags)
    assert f"safe.directory={submodule.resolve()}" in joined
    assert f"safe.directory={(parent / '.git' / 'modules' / 'console').resolve()}" in joined
    assert f"safe.directory={parent.resolve()}" in joined


def test_missing_source_raises(tmp_path, monkeypatch, sample_bundle):
    monkeypatch.delenv("CODE_ROOT_APPLIANCE_CONSOLE", raising=False)
    monkeypatch.delenv("CODE_ROOT_APPLIANCE_BACKEND", raising=False)
    monkeypatch.setenv("CODE_WORKTREE_ROOT", str(tmp_path / "worktrees"))

    bundle = sample_bundle.model_copy(deep=True)
    bundle.software.console_version = "abc123"
    bundle.software.controller_version = "abc123"

    with pytest.raises(CodeContextError) as exc:
        prepare_code_roots("ticket-missing", bundle)
    assert exc.value.reason == "source_not_configured"
