from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .entitlement import check_entitlement
from .jobs.diagnose import run_diagnosis
from .redact import contains_secrets, scrub_dict
from .schemas import (
    DiagnosticBundle,
    EntitlementResponse,
    TicketCreateResponse,
    TicketListResponse,
    TicketStatusResponse,
)
from . import tickets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

RATE_LIMIT_PER_HOUR = int(os.environ.get("SUPPORT_RATE_LIMIT_PER_HOUR", "10"))
_ticket_counts: dict[str, list[float]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await tickets.init_db()
    logger.info("Appliance support service started")
    yield


app = FastAPI(title="Appliance Support", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/entitlement/{appliance_id}", response_model=EntitlementResponse)
async def get_entitlement(appliance_id: str) -> EntitlementResponse:
    return await check_entitlement(appliance_id)


def _rate_limit_ok(appliance_id: str) -> bool:
    import time

    now = time.time()
    window = _ticket_counts.setdefault(appliance_id, [])
    window[:] = [ts for ts in window if now - ts < 3600]
    if len(window) >= RATE_LIMIT_PER_HOUR:
        return False
    window.append(now)
    return True


@app.post("/v1/tickets", response_model=TicketCreateResponse, status_code=202)
async def create_ticket(
    bundle: DiagnosticBundle,
    background_tasks: BackgroundTasks,
) -> TicketCreateResponse | JSONResponse:
    entitlement = await check_entitlement(bundle.appliance_id)
    if not entitlement.entitled:
        return JSONResponse(
            status_code=403,
            content={
                "error": "subscription_required",
                "message": entitlement.message or "Support subscription required.",
            },
        )

    if not _rate_limit_ok(bundle.appliance_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for this appliance")

    scrubbed = scrub_dict(bundle.model_dump())
    raw = json.dumps(scrubbed)
    if contains_secrets(raw):
        raise HTTPException(status_code=400, detail="Bundle contains sensitive data")

    clean_bundle = DiagnosticBundle.model_validate(scrubbed)
    ticket_id = await tickets.create_ticket(clean_bundle)
    background_tasks.add_task(run_diagnosis, ticket_id, clean_bundle)
    return TicketCreateResponse(ticket_id=ticket_id, status="queued")


@app.get("/v1/tickets", response_model=TicketListResponse)
async def list_tickets(appliance_id: str) -> TicketListResponse | JSONResponse:
    entitlement = await check_entitlement(appliance_id)
    if not entitlement.entitled:
        return JSONResponse(
            status_code=403,
            content={
                "error": "subscription_required",
                "message": entitlement.message or "Support subscription required.",
            },
        )
    items = await tickets.list_tickets_for_appliance(appliance_id)
    return TicketListResponse(appliance_id=appliance_id, tickets=items)


@app.get("/v1/tickets/{ticket_id}", response_model=TicketStatusResponse)
async def get_ticket(ticket_id: str) -> TicketStatusResponse:
    ticket = await tickets.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@app.get("/v1/tickets/{ticket_id}/diagnosis", response_model=TicketStatusResponse)
async def get_ticket_diagnosis(ticket_id: str) -> TicketStatusResponse:
    ticket = await tickets.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status != "complete":
        raise HTTPException(status_code=409, detail=f"Ticket status is {ticket.status}")
    return ticket