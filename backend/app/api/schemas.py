"""Pydantic request/response schemas for the API layer.

The chat shapes implement the FROZEN frontend contract:
POST /chat {thread_id, message} -> {"type": "message", ...} |
{"type": "approval_request", ..., "proposal": {flat key/value object}}.
"""

from typing import Any, Literal

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Incoming chat message from the UI."""

    thread_id: str
    message: str


class MessageReply(BaseModel):
    """Plain assistant reply."""

    type: Literal["message"] = "message"
    text: str


class ApprovalRequestReply(BaseModel):
    """The write gate is parked: confirmation question plus the exact
    proposal payload the user is being asked to authorize."""

    type: Literal["approval_request"] = "approval_request"
    text: str
    proposal: dict[str, Any]


class ChatHistoryResponse(BaseModel):
    """Full human/assistant history for a thread."""

    thread_id: str
    messages: list[dict[str, Any]]


class SandboxStateResponse(BaseModel):
    """Current contents of the writable sandbox ledgers."""

    invoices: list[dict[str, Any]]
    credit_memos: list[dict[str, Any]]
    plan_amendments: list[dict[str, Any]]


class AuditLogResponse(BaseModel):
    """Audit trail of applied/rolled-back actions."""

    entries: list[dict[str, Any]]
