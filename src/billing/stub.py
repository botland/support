from __future__ import annotations

import os

from ..schemas import EntitlementResponse


class StubBillingAdapter:
    """Env-driven entitlement stub until the billing database is wired."""

    def __init__(self) -> None:
        self.free_for_all = os.environ.get("SUPPORT_FREE_FOR_ALL", "true").lower() in (
            "1",
            "true",
            "yes",
        )

    def _denied_ids(self) -> set[str]:
        raw = os.environ.get("SUPPORT_DENIED_APPLIANCE_IDS", "")
        return {item.strip() for item in raw.split(",") if item.strip()}

    def _entitled_ids(self) -> set[str]:
        raw = os.environ.get("SUPPORT_ENTITLED_APPLIANCE_IDS", "")
        return {item.strip() for item in raw.split(",") if item.strip()}

    async def check_entitlement(self, appliance_id: str) -> EntitlementResponse:
        if appliance_id in self._denied_ids():
            return EntitlementResponse(
                entitled=False,
                message="Support subscription required for this appliance.",
            )

        explicit = self._entitled_ids()
        if explicit:
            if appliance_id in explicit:
                return EntitlementResponse(entitled=True, tier="paid")
            return EntitlementResponse(
                entitled=False,
                message="Support subscription required for this appliance.",
            )

        if self.free_for_all:
            return EntitlementResponse(entitled=True, tier="free")

        return EntitlementResponse(
            entitled=False,
            message="Support subscription required for this appliance.",
        )