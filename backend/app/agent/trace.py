"""Console tracing for the ReAct agent loop.

Enable with LOG_LEVEL=INFO (default) in .env. All messages go to the
`agent.flow` logger on stderr — visible in the terminal running uvicorn.
"""

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

logger = logging.getLogger("agent.flow")

_PREVIEW_LEN = 500


def _preview(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) <= _PREVIEW_LEN:
        return text
    return f"{text[:_PREVIEW_LEN]}…"


def message_text(message: BaseMessage) -> str:
    """Plain text from a human or assistant message."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)
    return str(content)


def log_chat_start(thread_id: str, message: str, *, resume: bool) -> None:
    mode = "resume (write gate)" if resume else "new message"
    logger.info("── chat [%s] %s ──", thread_id[:8], mode)
    logger.info("user: %s", _preview(message))


def log_chat_end(thread_id: str, response_type: str, payload: str) -> None:
    logger.info("── reply [%s] type=%s ──", thread_id[:8], response_type)
    logger.info("assistant: %s", _preview(payload))


def log_agent_step(step: int, response: AIMessage) -> str:
    if response.tool_calls:
        names = [call["name"] for call in response.tool_calls]
        logger.info("loop %d | agent → tools (%s)", step, ", ".join(names))
        for call in response.tool_calls:
            logger.info("  call %s(%s)", call["name"], _preview(call["args"]))
        return "tools"

    text = message_text(response)
    logger.info("loop %d | agent → end", step)
    if text.strip():
        logger.info("  text: %s", _preview(text))
    return "end"


def log_tool_step(step: int, name: str, args: dict[str, Any], result: Any) -> None:
    logger.info("loop %d | tools → %s", step, name)
    logger.info("  args: %s", _preview(args))
    logger.info("  result: %s", _preview(result))


def log_gate_parked(proposal: dict[str, Any]) -> None:
    logger.info("write gate | parked — waiting for %r", "yes, apply it")
    logger.info("  proposal: %s", _preview(proposal))


def log_gate_decision(decision: str, *, applied: bool) -> None:
    outcome = "APPLIED" if applied else "DECLINED"
    logger.info("write gate | resume %r → %s", decision, outcome)


def log_route(decision: str) -> None:
    logger.debug("route: agent → %s", decision)
