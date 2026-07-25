"""LangGraph agent state.

Channels are deliberately minimal: cross-turn context (plans fetched, findings,
which plan is under discussion) lives in the message history restored by the
checkpointer — no active_plan_id or findings channels needed.
"""

import operator
from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    """Conversation state carried across graph nodes and turns.

    messages: full conversation including tool results (add_messages reducer
        appends). This is what makes follow-ups work with zero extra machinery.
    pending_proposal: single slot — one proposal in flight at a time, mirroring
        the brief's flow. Set by propose_* tools, cleared when apply resolves
        (approved or declined).
    applied_actions: append-only audit list
        {action_id, type, target, amount, reason, ts}. Powers rollback and
        "what did you already do?"; the durable mirror is
        sandbox/audit_log.json, written by the data layer.
    """

    messages: Annotated[list[Any], add_messages]
    pending_proposal: dict[str, Any] | None
    applied_actions: Annotated[list[dict[str, Any]], operator.add]
