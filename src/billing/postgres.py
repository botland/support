from __future__ import annotations

import os
from datetime import datetime, timezone

from ..schemas import EntitlementResponse

try:
    import asyncpg
except ImportError:  # pragma: no cover - optional until postgres adapter is used
    asyncpg = None  # type: ignore[assignment]


class PostgresBillingAdapter:
    """Reads entitlement from the shared nocloud Postgres database."""

    def __init__(self) -> None:
        # Prefer ENTITLEMENT_DATABASE_URL so support app DB stays separate.
        self.database_url = (
            os.environ.get("ENTITLEMENT_DATABASE_URL", "").strip()
            or os.environ.get("DATABASE_URL", "").strip()
        )
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if asyncpg is None:
            raise RuntimeError("asyncpg is required when BILLING_ADAPTER=postgres")
        if not self.database_url:
            raise RuntimeError(
                "ENTITLEMENT_DATABASE_URL (or DATABASE_URL) is required when BILLING_ADAPTER=postgres"
            )
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=4)
        return self._pool

    async def check_entitlement(self, appliance_id: str) -> EntitlementResponse:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT ss.status, ss.trial_ends_at
                FROM appliances a
                JOIN service_subscriptions ss ON ss.customer_id = a.customer_id
                WHERE a.appliance_id = $1
                  AND ss.service_key = 'aiAssistedSupport'
                  AND ss.status IN ('active', 'trialing')
                LIMIT 1
                """,
                appliance_id,
            )

        if not row:
            appliance_exists = await self._appliance_exists(appliance_id)
            if not appliance_exists:
                return EntitlementResponse(
                    entitled=False,
                    message="Unknown appliance. Hardware must be provisioned after full payment.",
                )
            return EntitlementResponse(
                entitled=False,
                message="AI-assisted support is not active for this customer.",
            )

        if row["status"] == "trialing" and row["trial_ends_at"] is not None:
            trial_end = row["trial_ends_at"]
            if isinstance(trial_end, datetime):
                now = datetime.now(timezone.utc)
                if trial_end.tzinfo is None:
                    trial_end = trial_end.replace(tzinfo=timezone.utc)
                if trial_end < now:
                    return EntitlementResponse(
                        entitled=False,
                        message="AI-assisted support trial has ended.",
                    )

        return EntitlementResponse(entitled=True, tier="paid")

    async def _appliance_exists(self, appliance_id: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT 1 FROM appliances WHERE appliance_id = $1",
                appliance_id,
            )
        return val is not None