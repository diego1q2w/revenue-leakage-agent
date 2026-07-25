"""Agent layer tests — tool surface, turn discipline, and the write gate."""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from backend.app.agent.service import AgentService, _extract_text
from backend.app.agent.tools import ALL_TOOLS
from backend.app.config import get_settings

EXPECTED_TOOLS = {
    "load_plan",
    "query_invoices",
    "fx_convert",
    "propose_make_good_invoice",
    "propose_credit_memo",
    "propose_plan_amendment",
    "apply_action",
    "rollback_action",
}


def test_tool_surface_is_the_expected_eight():
    """Exactly the eight designed tools are registered — no more, no fewer."""
    assert {t.name for t in ALL_TOOLS} == EXPECTED_TOOLS


def _ledger_rows(path) -> list:
    """Ledger contents, treating a not-yet-created file as empty."""
    return json.loads(path.read_text()) if path.exists() else []


def _last_assistant_text(messages) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            text = _extract_text(message)
            if text.strip():
                return text
    pytest.fail("Graph finished without an assistant text reply")


@pytest.mark.integration
def test_agent_detects_missing_invoice():
    """Agent flags a missing billing period for a monthly plan."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    from backend.app.agent.graph import build_graph

    graph = build_graph(settings)
    config = {"configurable": {"thread_id": "test-missing-invoice"}}

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(content="Any revenue leakage issues with plan C-1001?")
            ]
        },
        config,
    )

    reply = _last_assistant_text(result["messages"]).lower()
    # C-1001 is monthly $8k USD; September 2025 was never invoiced.
    assert "september" in reply or "sep " in reply or "sep." in reply
    assert any(token in reply for token in ("8000", "8,000", "8 000"))
    assert any(
        word in reply
        for word in ("missing", "leakage", "gap", "not invoiced", "never invoiced")
    )


@pytest.mark.integration
def test_agent_answers_currency_followup_without_proposing():
    """Follow-up questions reuse checkpointer context; no write-path tools."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    async def run() -> dict:
        service = AgentService(settings)
        await service.chat("test-currency-followup", "Any revenue leakage issues with plan C-1001?")
        return await service.chat("test-currency-followup", "What currency is that plan in?")

    result = asyncio.run(run())
    assert result["type"] == "message"
    assert "usd" in result["text"].lower()
    assert "would you like me to apply" not in result["text"].lower()


@pytest.mark.integration
def test_investigation_turn_reports_without_proposing(tmp_sandbox):
    """Finding leakage and drafting its fix are separate turns.

    The opening question must come back as prose findings, not as a parked
    approval_request — the user decides whether to act on them.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    async def run() -> dict:
        service = AgentService(settings)
        return await service.chat(
            "test-investigate-only", "Any revenue leakage issues with plan C-1001?"
        )

    result = asyncio.run(run())
    assert result["type"] == "message", "investigation turn must not park at the gate"
    assert "proposal" not in result
    # Nothing drafted, nothing written.
    assert _ledger_rows(tmp_sandbox / "proposals.json") == []


@pytest.mark.integration
def test_fix_request_turn_parks_at_the_write_gate(tmp_sandbox):
    """Asking for the fix is what produces the proposal and the approval card."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    async def run() -> dict:
        service = AgentService(settings)
        await service.chat("test-fix-request", "Any revenue leakage issues with plan C-1001?")
        return await service.chat("test-fix-request", "Yes, please fix it.")

    result = asyncio.run(run())
    assert result["type"] == "approval_request"
    assert result["proposal"]["action_type"] == "make_good_invoice"
    # Still a draft — the gate has not been passed.
    assert _ledger_rows(tmp_sandbox / "invoices.json") == []


@pytest.mark.integration
def test_checkpointer_isolates_threads():
    """Different thread_ids do not share conversation state."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")

    async def run() -> dict:
        service = AgentService(settings)
        await service.chat("thread-a", "Any revenue leakage on C-1001?")
        return await service.chat("thread-b", "What currency is that plan in?")

    result = asyncio.run(run())
    assert result["type"] == "message"
    assert "would you like me to apply" not in result["text"].lower()


def test_apply_requires_prior_proposal(tmp_sandbox):
    """apply_action refuses proposal_ids that were never proposed."""
    from backend.app.agent.tools import apply_action

    result = apply_action.invoke({"proposal_id": "PR-never-created"})
    assert "error" in result
