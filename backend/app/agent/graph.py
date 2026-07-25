"""LangGraph graph assembly for the Revenue Leakage Agent.

ReAct-style tool-calling agent: one LLM node bound to all eight tools, looping
agent <-> tools until the model answers in prose. The LLM is the router; the
only structural piece — because it must be a hard guarantee, not a prompt — is
the write gate around apply_action.

The write gate: consent happens at two layers. Conversationally the model
proposes and asks; structurally, `interrupt()` inside the apply path stops
execution BEFORE the sandbox write regardless of why the tool was called,
surfaces the exact payload to the UI, and only an out-of-band resume — a thing
the UI does, that the LLM cannot fake — lets the write happen. The model
calling apply is a request; the human resume is the authorization. Worst case
of a model error is a spurious confirmation question, never a spurious write.
"""

import json
import re
from typing import Any, Callable, Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from backend.app.agent.prompts import SYSTEM_PROMPT
from backend.app.agent.state import AgentState
from backend.app.agent.tools import ALL_TOOLS, _runtime
from backend.app.agent.trace import (
    log_agent_step,
    log_gate_decision,
    log_gate_parked,
    log_route,
    log_tool_step,
)
from backend.app.config import Settings

_TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}
_PROPOSE_TOOL_NAMES = {
    "propose_make_good_invoice",
    "propose_credit_memo",
    "propose_plan_amendment",
}

APPROVAL_PHRASE = "yes, apply it"
APPROVAL_QUESTION = (
    "Would you like me to apply this to the sandbox? "
    f'Type exactly "{APPROVAL_PHRASE}" to confirm — anything else declines.'
)


def _normalize_gate_text(text: str) -> str:
    lowered = str(text).strip().lower()
    lowered = re.sub(r"[^\w\s]", "", lowered)
    return " ".join(lowered.split())


_APPROVAL_PHRASE_NORMALIZED = _normalize_gate_text(APPROVAL_PHRASE)


def is_affirmative(text: str) -> bool:
    """Only the phrase 'yes, apply it' applies (spacing/punctuation insensitive)."""
    return _normalize_gate_text(text) == _APPROVAL_PHRASE_NORMALIZED


def flatten_proposal(draft: dict[str, Any]) -> dict[str, Any]:
    """Flatten an ActionDraft dump into the flat key/value object the UI
    renders as generic rows (nested payloads like change_set are merged up)."""
    flat: dict[str, Any] = {"action_type": draft.get("action_type")}
    for key, value in (draft.get("payload") or {}).items():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    flat["reason"] = draft.get("reason")
    flat["proposal_id"] = draft.get("proposal_id")
    return flat


def _gated_apply(args: dict[str, Any]) -> dict[str, Any]:
    """Execute apply_action behind the structural write gate.

    Replay semantics: this function runs twice (pause, then resume), so there
    are NO side effects above the interrupt() line — only the read that builds
    the payload the human sees. The write happens strictly after it.
    """
    proposal_id = args.get("proposal_id", "")
    draft = _runtime().proposals.get(proposal_id)
    if draft is None:
        return {"error": f"No proposal with id '{proposal_id}'. Propose an action first."}

    # HARD GATE — execution stops here, checkpointed mid-node, nothing written.
    # Only an out-of-band resume (Command(resume=...)) returns a value.
    proposal = flatten_proposal(draft.model_dump())
    decision = interrupt(
        {
            "question": APPROVAL_QUESTION,
            "proposal": proposal,
        }
    )

    approved = is_affirmative(str(decision))
    log_gate_decision(str(decision), applied=approved)
    if not approved:
        return {
            "declined": True,
            "message": (
                "The user did not approve this proposal; nothing was written to "
                f"the sandbox. Only the exact phrase {APPROVAL_PHRASE!r} applies — "
                f"their reply was: {str(decision)!r}. Acknowledge, answer any "
                "question in their reply if needed, and continue. Re-propose only "
                "if they explicitly ask for a fix."
            ),
        }

    # Write strictly after the interrupt.
    return _TOOLS_BY_NAME["apply_action"].invoke({"proposal_id": proposal_id})


def tools_node(state: AgentState) -> dict[str, Any]:
    """Execute the tool calls requested by the last assistant message.

    apply_action calls are processed FIRST so the interrupt is hit before any
    other side effect in the batch — on resume the node re-executes from the
    top, and this ordering guarantees nothing ran (and nothing replays) ahead
    of the gate.
    """
    last = state["messages"][-1]
    calls = sorted(last.tool_calls, key=lambda call: call["name"] != "apply_action")
    step = sum(1 for m in state["messages"] if isinstance(m, ToolMessage)) + 1

    pending = state.get("pending_proposal")
    tool_messages: list[ToolMessage] = []
    applied_entries: list[dict[str, Any]] = []

    for call in calls:
        name, args, call_id = call["name"], call["args"], call["id"]

        if name == "apply_action":
            result = _gated_apply(args)
            log_tool_step(step, name, args, result)
            if isinstance(result, dict) and "action_id" in result:
                draft = result.get("draft", {})
                payload = draft.get("payload", {})
                applied_entries.append(
                    {
                        "action_id": result["action_id"],
                        "type": draft.get("action_type"),
                        "target": payload.get("plan_id") or payload.get("invoice_id"),
                        "amount": payload.get("amount"),
                        "reason": draft.get("reason"),
                        "ts": result.get("applied_at"),
                    }
                )
                pending = None
            elif isinstance(result, dict) and result.get("declined"):
                pending = None
        else:
            result = _TOOLS_BY_NAME[name].invoke(args)
            log_tool_step(step, name, args, result)
            if name in _PROPOSE_TOOL_NAMES and isinstance(result, dict) and "proposal_id" in result:
                pending = result  # single slot: a new proposal replaces any stale one

        tool_messages.append(
            ToolMessage(content=json.dumps(result, default=str), name=name, tool_call_id=call_id)
        )

    updates: dict[str, Any] = {"messages": tool_messages, "pending_proposal": pending}
    if applied_entries:
        updates["applied_actions"] = applied_entries
    return updates


def route_after_agent(state: AgentState) -> Literal["tools", "__end__"]:
    """No tool calls -> the prose is the answer, end the turn."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        log_route("tools")
        return "tools"
    log_route("end")
    return END


def build_llm(settings: Settings) -> ChatAnthropic:
    """Construct the Claude Sonnet 5 chat model."""
    return ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key or None,
        max_tokens=8192,
    )


def _make_agent_node(llm_with_tools: Any) -> Callable[[AgentState], dict[str, Any]]:
    def agent_node(state: AgentState) -> dict[str, Any]:
        step = sum(1 for m in state["messages"] if isinstance(m, AIMessage)) + 1
        response = llm_with_tools.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        )
        log_agent_step(step, response)
        return {"messages": [response]}

    return agent_node


def build_checkpointer() -> MemorySaver:
    """Checkpointer persisting per-thread state — conversation memory and
    interrupt/resume both hang off this."""
    return MemorySaver()


def build_graph(
    settings: Settings, checkpointer: MemorySaver | None = None
) -> CompiledStateGraph:
    """Assemble and compile the two-node ReAct graph."""
    llm_with_tools = build_llm(settings).bind_tools(ALL_TOOLS)

    graph = StateGraph(AgentState)
    graph.add_node("agent", _make_agent_node(llm_with_tools))
    graph.add_node("tools", tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer or build_checkpointer())
