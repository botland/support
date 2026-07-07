from __future__ import annotations

import os

from .stub import StubBillingAdapter


def get_billing_adapter():
    name = os.environ.get("BILLING_ADAPTER", "stub").lower()
    if name == "stub":
        return StubBillingAdapter()
    raise ValueError(f"Unknown BILLING_ADAPTER: {name}")