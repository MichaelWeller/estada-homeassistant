"""Command registry and execution for Estada MQTT commands."""

from dataclasses import dataclass
from typing import Any

from . import create_knx_entity, delete_knx_entity, import_project, ping
from .base import CommandContext, CommandDefinition


@dataclass(slots=True, frozen=True)
class CommandExecutionResult:
    """Result payload for a command execution."""

    command_name: str
    payload: dict[str, Any]


class CommandRegistry:
    """Registry and executor for Estada command handlers."""

    def __init__(self) -> None:
        self._definitions: dict[str, CommandDefinition] = {
            create_knx_entity.DEFINITION.name: create_knx_entity.DEFINITION,
            delete_knx_entity.DEFINITION.name: delete_knx_entity.DEFINITION,
            import_project.DEFINITION.name: import_project.DEFINITION,
            ping.DEFINITION.name: ping.DEFINITION,
        }

    @property
    def list_payload(self) -> dict[str, dict[str, object]]:
        """Return command metadata for MQTT publication."""
        return {
            name: {"args": definition.args}
            for name, definition in self._definitions.items()
        }

    def has_command(self, command_name: str) -> bool:
        """Return whether a command exists."""
        return command_name in self._definitions

    async def async_execute(
        self,
        ctx: CommandContext,
        command_name: str,
        payload: dict[str, Any],
    ) -> CommandExecutionResult:
        """Validate and execute command payload."""
        if command_name not in self._definitions:
            raise ValueError(f"Unsupported command '{command_name}'")

        command_sequence_id = payload.get("commandSequenceId")
        if not isinstance(command_sequence_id, str) or not command_sequence_id.strip():
            raise ValueError(
                "'commandSequenceId' is required and must be a non-empty string"
            )

        params = payload.get("params", {})
        if not isinstance(params, dict):
            raise ValueError("'params' must be a JSON object")

        definition = self._definitions[command_name]
        handler_result = await definition.handler(ctx, params)

        return CommandExecutionResult(
            command_name=command_name,
            payload={
                "status": "ok",
                "command": command_name,
                "commandSequenceId": command_sequence_id,
                "result": handler_result,
            },
        )
