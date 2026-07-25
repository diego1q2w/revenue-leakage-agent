"""Chat endpoints — the conversational surface of the agent.

POST /chat is mounted at the root (no /api prefix) to match the frozen
frontend contract.
"""

from fastapi import APIRouter, Depends

from backend.app.agent.service import AgentService, get_agent_service
from backend.app.api.schemas import (
    ApprovalRequestReply,
    ChatHistoryResponse,
    ChatRequest,
    MessageReply,
)

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(
    request: ChatRequest,
    service: AgentService = Depends(get_agent_service),
) -> MessageReply | ApprovalRequestReply:
    """Send a user message to the agent and return its reply.

    The service decides whether this text starts a fresh turn or resumes a
    graph parked at the write gate — the frontend never knows resumes exist.
    """
    result = await service.chat(request.thread_id, request.message)
    if result["type"] == "approval_request":
        return ApprovalRequestReply(text=result["text"], proposal=result["proposal"])
    return MessageReply(text=result["text"])


@router.get("/chat/{thread_id}/history")
async def chat_history(
    thread_id: str,
    service: AgentService = Depends(get_agent_service),
) -> ChatHistoryResponse:
    """Return the human/assistant message history for a thread."""
    messages = await service.history(thread_id)
    return ChatHistoryResponse(thread_id=thread_id, messages=messages)
