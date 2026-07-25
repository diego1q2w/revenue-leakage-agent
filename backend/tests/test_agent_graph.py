"""Agent-graph tests: routing, the structural write gate, and its replay
semantics. No LLM involved — the graph under test is the tools node compiled
with a checkpointer, driven by hand-built assistant messages."""

import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from backend.app.agent.graph import (
    APPROVAL_QUESTION,
    flatten_proposal,
    is_affirmative,
    route_after_agent,
    tools_node,
)
from backend.app.agent.state import AgentState
from backend.app.data.proposals import ProposalStore


def _ai_call(name: str, args: dict, call_id: str = "call-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def _tools_only_graph():
    graph = StateGraph(AgentState)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("tools")
    graph.add_edge("tools", END)
    return graph.compile(checkpointer=MemorySaver())


def _make_proposal(sandbox_dir) -> str:
    draft = ProposalStore(sandbox_dir).create(
        action_type="make_good_invoice",
        payload={"plan_id": "C-1001", "amount": 8000},
        reason="Missing September 2025 billing",
    )
    return draft.proposal_id


# --------------------------------------------------------------------------
# Consent check — dumb and deterministic
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["yes, apply it", "Yes, apply it.", "YES, APPLY IT", "  yes , apply it  "],
)
def test_is_affirmative_accepts_exact_phrase_only(text):
    assert is_affirmative(text)


@pytest.mark.parametrize(
    "text",
    ["yes", "ok", "go ahead", "approve", "do it", "y", "no", "No, don't.", "wait", "", "maybe"],
)
def test_is_affirmative_declines_everything_else(text):
    assert not is_affirmative(text)


def test_bare_yes_does_not_apply(tmp_sandbox):
    proposal_id = _make_proposal(tmp_sandbox)
    graph = _tools_only_graph()
    config = {"configurable": {"thread_id": "t-bare-yes"}}

    graph.invoke({"messages": [_ai_call("apply_action", {"proposal_id": proposal_id})]}, config)
    result = graph.invoke(Command(resume="yes"), config)

    tool_result = json.loads(result["messages"][-1].content)
    assert tool_result["declined"] is True
    assert result.get("pending_proposal") is None
    ledger = tmp_sandbox / "invoices.json"
    assert not ledger.exists() or json.loads(ledger.read_text()) == []


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------


def test_route_to_tools_when_model_requests_them():
    state = {"messages": [_ai_call("load_plan", {"plan_id": "C-1001"})]}
    assert route_after_agent(state) == "tools"


def test_route_to_end_when_model_answers_in_prose():
    state = {"messages": [AIMessage(content="October is missing — $8,000 missed revenue.")]}
    assert route_after_agent(state) == END


# --------------------------------------------------------------------------
# Proposals populate the single pending slot
# --------------------------------------------------------------------------


def test_propose_sets_pending_proposal(tmp_sandbox):
    state = {
        "messages": [
            _ai_call(
                "propose_make_good_invoice",
                {"plan_id": "C-1001", "amount": 8000, "reason": "Missing September"},
            )
        ],
        "pending_proposal": None,
    }
    updates = tools_node(state)
    pending = updates["pending_proposal"]
    assert pending is not None and pending["action_type"] == "make_good_invoice"
    result = json.loads(updates["messages"][0].content)
    assert result["proposal_id"] == pending["proposal_id"]


def test_flatten_proposal_merges_nested_payload():
    draft = {
        "proposal_id": "PR-001",
        "action_type": "plan_amendment",
        "payload": {"plan_id": "C-1010", "change_set": {"total_value": 130000}},
        "reason": "Upgrade",
    }
    flat = flatten_proposal(draft)
    assert flat["plan_id"] == "C-1010"
    assert flat["total_value"] == 130000
    assert "change_set" not in flat


# --------------------------------------------------------------------------
# The write gate — interrupt before write, resume decides
# --------------------------------------------------------------------------


def test_apply_parks_at_interrupt_and_writes_nothing(tmp_sandbox):
    proposal_id = _make_proposal(tmp_sandbox)
    graph = _tools_only_graph()
    config = {"configurable": {"thread_id": "t-gate"}}

    result = graph.invoke(
        {"messages": [_ai_call("apply_action", {"proposal_id": proposal_id})]}, config
    )

    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert payload["question"] == APPROVAL_QUESTION
    assert payload["proposal"]["plan_id"] == "C-1001"
    assert payload["proposal"]["amount"] == 8000
    # Nothing written while parked — the hard-gate property.
    ledger = tmp_sandbox / "invoices.json"
    assert not ledger.exists() or json.loads(ledger.read_text()) == []


def test_affirmative_resume_executes_the_write(tmp_sandbox):
    proposal_id = _make_proposal(tmp_sandbox)
    graph = _tools_only_graph()
    config = {"configurable": {"thread_id": "t-approve"}}

    graph.invoke({"messages": [_ai_call("apply_action", {"proposal_id": proposal_id})]}, config)
    result = graph.invoke(Command(resume="Yes, apply it."), config)

    tool_result = json.loads(result["messages"][-1].content)
    assert tool_result["action_id"] == "INV-MG-001"
    assert result.get("pending_proposal") is None
    assert result["applied_actions"][0]["action_id"] == "INV-MG-001"
    rows = json.loads((tmp_sandbox / "invoices.json").read_text())
    assert len(rows) == 1


def test_negative_resume_declines_and_sandbox_untouched(tmp_sandbox):
    proposal_id = _make_proposal(tmp_sandbox)
    graph = _tools_only_graph()
    config = {"configurable": {"thread_id": "t-reject"}}

    graph.invoke({"messages": [_ai_call("apply_action", {"proposal_id": proposal_id})]}, config)
    result = graph.invoke(Command(resume="no, don't"), config)

    tool_result = json.loads(result["messages"][-1].content)
    assert tool_result["declined"] is True
    assert result.get("pending_proposal") is None
    assert not result.get("applied_actions")
    ledger = tmp_sandbox / "invoices.json"
    assert not ledger.exists() or json.loads(ledger.read_text()) == []


def test_apply_with_unknown_proposal_errors_without_parking(tmp_sandbox):
    graph = _tools_only_graph()
    config = {"configurable": {"thread_id": "t-unknown"}}

    result = graph.invoke(
        {"messages": [_ai_call("apply_action", {"proposal_id": "PR-999"})]}, config
    )

    assert "__interrupt__" not in result
    tool_result = json.loads(result["messages"][-1].content)
    assert "error" in tool_result
