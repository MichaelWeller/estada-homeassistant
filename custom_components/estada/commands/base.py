"""Shared command types for Estada command handlers."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant


@dataclass(slots=True)
class CommandContext:
    """Runtime context passed to command handlers."""

    hass: HomeAssistant
    entry_id: str
    client_id: str
    knx_entities: dict[str, dict[str, Any]]


@dataclass(slots=True, frozen=True)
class CommandDefinition:
    """A command descriptor with argument schema and async handler."""

    name: str
    args: dict[str, dict[str, object]]
    handler: Callable[[CommandContext, dict[str, Any]], Awaitable[dict[str, Any]]]
