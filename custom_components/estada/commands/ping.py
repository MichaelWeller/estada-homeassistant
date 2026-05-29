"""Ping command implementation."""

from datetime import UTC, datetime
from typing import Any

from .base import CommandContext, CommandDefinition


async def async_handle_ping(
    _: CommandContext,
    __: dict[str, Any],
) -> dict[str, Any]:
    """Return a health response."""
    return {
        "response": "pong",
        "time": datetime.now(UTC).isoformat(),
    }


DEFINITION = CommandDefinition(
    name="ping",
    args={
        "commandSequenceId": {
            "type": "string",
            "required": True,
        }
    },
    handler=async_handle_ping,
)
