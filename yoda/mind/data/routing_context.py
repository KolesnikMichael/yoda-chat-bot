from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RoutingContext:
    """User turn + short conversation tail for routing and agent skill selection."""

    current_user_text: str
    recent_messages: list[dict]


def format_recent_messages_block(recent_messages: list[dict]) -> str:
    if not recent_messages:
        return ""
    lines = ["Recent conversation (newest last):"]
    for i, msg in enumerate(recent_messages, start=1):
        role = msg.get("role", "")
        content = msg.get("content", "")
        lines.append(f"{i}. [{role}] {content}")
    return "\n".join(lines)
