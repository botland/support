from __future__ import annotations


class CodeContextError(Exception):
    """Raised when per-ticket code context cannot be prepared for the reported versions."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        repo_key: str | None = None,
        ref: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.repo_key = repo_key
        self.ref = ref
        self.detail = detail
