from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SoftwareVersions(BaseModel):
    console_version: str = "unknown"
    controller_version: str = "unknown"
    support_client_version: str = "1.0.0"


class TopologySummary(BaseModel):
    serving_mode: str
    role: str
    node_count: int
    local_node_id: str


class DiagnosticBundle(BaseModel):
    bundle_version: Literal[1] = 1
    appliance_id: str
    submitted_at: str
    software: SoftwareVersions
    topology: TopologySummary
    health: dict[str, Any]
    events: list[dict[str, Any]] = Field(default_factory=list)
    deployments_summary: list[dict[str, Any]] = Field(default_factory=list)
    nodes_summary: list[dict[str, Any]] = Field(default_factory=list)
    user_note: str = ""
    attachments: dict[str, Any] = Field(default_factory=dict)


class DiagnosisResult(BaseModel):
    verdict: Literal["likely_bug", "operator_actionable", "insufficient_data", "unknown"]
    summary: str
    confidence: Literal["low", "medium", "high"]
    recommended_actions: list[str]
    engineering_notes: str | None = None
    evidence: list[str] = Field(default_factory=list)


class EntitlementResponse(BaseModel):
    entitled: bool
    tier: str | None = None
    message: str | None = None


class TicketCreateResponse(BaseModel):
    ticket_id: str
    status: str


class TicketStatusResponse(BaseModel):
    ticket_id: str
    status: str
    diagnosis: DiagnosisResult | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    github_issue_url: str | None = None


class TicketSummary(BaseModel):
    ticket_id: str
    status: str
    created_at: str
    updated_at: str
    verdict: str | None = None
    summary: str | None = None
    confidence: str | None = None
    github_issue_url: str | None = None


class TicketListResponse(BaseModel):
    appliance_id: str
    tickets: list[TicketSummary]