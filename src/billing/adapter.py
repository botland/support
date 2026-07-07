from __future__ import annotations

from typing import Protocol

from ..schemas import EntitlementResponse


class BillingEntitlementAdapter(Protocol):
    async def check_entitlement(self, appliance_id: str) -> EntitlementResponse: ...