"""Sandbox inspection endpoints — ledgers and audit log."""

from fastapi import APIRouter

from backend.app.api.schemas import AuditLogResponse, SandboxStateResponse
from backend.app.data.runtime import get_runtime

router = APIRouter(tags=["sandbox"])


@router.get("/sandbox", response_model=SandboxStateResponse)
async def sandbox_state() -> SandboxStateResponse:
    """Return the current contents of the writable sandbox ledgers."""
    state = get_runtime().sandbox.state()
    return SandboxStateResponse(**state)


@router.get("/sandbox/audit-log", response_model=AuditLogResponse)
async def audit_log() -> AuditLogResponse:
    """Return the audit trail of applied and rolled-back actions."""
    entries = [entry.model_dump() for entry in get_runtime().sandbox.audit_log()]
    return AuditLogResponse(entries=entries)


@router.post("/sandbox/reset")
async def reset_sandbox() -> dict[str, str]:
    """Reset all sandbox ledgers to their empty state."""
    get_runtime().sandbox.reset()
    return {"status": "reset"}
