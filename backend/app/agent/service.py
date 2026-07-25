"""AgentService — the boundary between the API layer and the agent graph.

This is where the interrupt machinery stays invisible to the frontend: the
UI just POSTs text, and this service decides whether that text is a fresh
message or the resume value for a graph parked at the write gate. Sending
approval text as a fresh message instead of a resume is the classic wiring
bug — the parked check below is what prevents it.
"""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.types import Command

from backend.app.agent.graph import build_graph
from backend.app.agent.trace import log_chat_end, log_chat_start, log_gate_parked
from backend.app.config import Settings, get_settings


def _extract_text(message: BaseMessage) -> str:
    """Pull the plain text out of a message whose content may be a string or
    a list of content blocks (Anthropic returns blocks when tools are bound)."""
    content = message.content
    if isinstance(content, str):
        return content
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(part for part in parts if part)


class AgentService:
    """Owns the compiled graph and drives conversations against it."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graph = build_graph(settings)

    def _pending_interrupt(self, config: dict[str, Any]) -> dict[str, Any] | None:
        """Return the write-gate payload if this thread is parked at an
        interrupt, else None."""
        snapshot = self._graph.get_state(config)
        if snapshot is None:
            return None
        for task in snapshot.tasks:
            for intr in task.interrupts:
                return intr.value
        return None

    async def chat(self, thread_id: str, message: str) -> dict[str, Any]:
        """Send user text into the graph for this thread and shape the reply
        per the frontend contract.

        Parked thread -> the text is the resume value (the human authorization
        for the write gate). Otherwise -> a fresh user message. If this run
        parks at the gate, surface the proposal as an approval_request.
        """
        config = {"configurable": {"thread_id": thread_id}}
        parked = self._pending_interrupt(config) is not None
        log_chat_start(thread_id, message, resume=parked)

        if parked:
            # Always resume — the gate accepts only "yes, apply it"; anything
            # else declines, clears pending_proposal, and loops to the agent.
            result = await self._graph.ainvoke(Command(resume=message), config)
        else:
            result = await self._graph.ainvoke(
                {"messages": [HumanMessage(content=message)]}, config
            )

        gate_payload = self._pending_interrupt(config)
        if gate_payload is not None:
            log_gate_parked(gate_payload["proposal"])
            log_chat_end(thread_id, "approval_request", gate_payload["question"])
            return {
                "type": "approval_request",
                "text": gate_payload["question"],
                "proposal": gate_payload["proposal"],
            }

        text = _extract_text(result["messages"][-1])
        log_chat_end(thread_id, "message", text)
        return {"type": "message", "text": text}

    async def history(self, thread_id: str) -> list[dict[str, Any]]:
        """Return the human/assistant message history stored for a thread."""
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = self._graph.get_state(config)
        if snapshot is None or not snapshot.values:
            return []
        history = []
        for message in snapshot.values.get("messages", []):
            if message.type not in ("human", "ai"):
                continue
            text = _extract_text(message)
            if text:
                history.append({"role": message.type, "content": text})
        return history


_service: AgentService | None = None


def get_agent_service() -> AgentService:
    """FastAPI dependency returning the singleton AgentService."""
    global _service
    if _service is None:
        _service = AgentService(get_settings())
    return _service
