from __future__ import annotations


class CLIAdapterError(RuntimeError):
    """Base error for external CLI adapter failures."""


class CLITransientError(CLIAdapterError):
    """Retryable CLI failure (timeout, empty output, non-zero exit on transient)."""


class CLIPermanentError(CLIAdapterError):
    """Non-retryable CLI failure (misconfiguration, invalid JSON schema)."""