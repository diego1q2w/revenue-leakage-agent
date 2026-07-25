"""API integration tests — chat contract and sandbox endpoints."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app.agent.graph import APPROVAL_QUESTION
from backend.app.agent.service import get_agent_service
from backend.app.data.proposals import ProposalStore
from backend.app.data.sandbox import SandboxLedger
from backend.app.main import create_app


class _FakeAgentService:
    async def chat(self, thread_id: str, message: str) -> dict:
        if message == "trigger-approval":
            return {
                "type": "approval_request",
                "text": APPROVAL_QUESTION,
                "proposal": {
                    "action_type": "make_good_invoice",
                    "plan_id": "C-1001",
                    "amount": 8000,
                    "reason": "Missing September 2025 billing",
                    "proposal_id": "PR-001",
                },
            }
        return {"type": "message", "text": f"Echo: {message}"}

    async def history(self, thread_id: str) -> list[dict]:
        return [{"role": "human", "content": "hello"}]


@pytest.fixture
def api_client():
    app = create_app()
    app.dependency_overrides[get_agent_service] = lambda: _FakeAgentService()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_chat_returns_message_shape(api_client):
    response = api_client.post(
        "/chat", json={"thread_id": "t-1", "message": "any revenue leakage on C-1001?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"type": "message", "text": "Echo: any revenue leakage on C-1001?"}


def test_chat_returns_approval_request_shape(api_client):
    response = api_client.post(
        "/chat", json={"thread_id": "t-2", "message": "trigger-approval"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "approval_request"
    assert body["text"] == APPROVAL_QUESTION
    assert body["proposal"]["action_type"] == "make_good_invoice"
    assert body["proposal"]["plan_id"] == "C-1001"


def test_chat_history_returns_thread_messages(api_client):
    response = api_client.get("/chat/t-3/history")
    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == "t-3"
    assert body["messages"] == [{"role": "human", "content": "hello"}]


def test_sandbox_state_reflects_ledgers(tmp_sandbox, client):
    ledger = SandboxLedger(tmp_sandbox)
    draft = ProposalStore(tmp_sandbox).create(
        action_type="make_good_invoice",
        payload={"plan_id": "C-1001", "amount": 8000},
        reason="Missing September",
    )
    ledger.apply(draft)

    response = client.get("/api/sandbox")
    assert response.status_code == 200
    body = response.json()
    assert len(body["invoices"]) == 1
    assert body["invoices"][0]["action_id"] == "INV-MG-001"
    assert body["credit_memos"] == []
    assert body["plan_amendments"] == []


def test_sandbox_audit_log_returns_entries(tmp_sandbox, client):
    ledger = SandboxLedger(tmp_sandbox)
    draft = ProposalStore(tmp_sandbox).create(
        action_type="credit_memo",
        payload={"invoice_id": "I-9123", "amount": 2000},
        reason="Overbilled",
    )
    ledger.apply(draft)

    response = client.get("/api/sandbox/audit-log")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["event"] == "applied"
    assert entries[0]["action_id"] == "CM-001"


def test_sandbox_reset_clears_ledgers(tmp_sandbox, client):
    ledger = SandboxLedger(tmp_sandbox)
    draft = ProposalStore(tmp_sandbox).create(
        action_type="make_good_invoice",
        payload={"plan_id": "C-1001", "amount": 8000},
        reason="Missing September",
    )
    ledger.apply(draft)
    assert json.loads((tmp_sandbox / "invoices.json").read_text())

    response = client.post("/api/sandbox/reset")
    assert response.status_code == 200
    assert response.json() == {"status": "reset"}
    assert client.get("/api/sandbox").json()["invoices"] == []
    assert client.get("/api/sandbox/audit-log").json()["entries"] == []
