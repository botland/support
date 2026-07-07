from __future__ import annotations

from .billing.registry import get_billing_adapter
from .schemas import EntitlementResponse


async def check_entitlement(appliance_id: str) -> EntitlementResponse:
    adapter = get_billing_adapter()
    return await adapter.check_entitlement(appliance_id)