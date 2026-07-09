from __future__ import annotations

import os

from .postgres import PostgresBillingAdapter
from .stub import StubBillingAdapter


def get_billing_adapter():
    name = os.environ.get("BILLING_ADAPTER", "stub").lower()
    if name == "stub":
        return StubBillingAdapter()
    if name == "postgres":
        return PostgresBillingAdapter()
    raise ValueError(f"Unknown BILLING_ADAPTER: {name}")