"""Create KNX entity command implementation."""

from typing import Any

from homeassistant.util import slugify

from .base import CommandContext, CommandDefinition


async def async_handle_create_knx_entity(
    ctx: CommandContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Create an in-memory KNX-like entity representation in HA state machine."""
    name = str(params.get("name", "")).strip()
    if not name:
        raise ValueError("'name' is required")

    suggested_entity_id = str(params.get("entity_id", "")).strip()
    entity_id = suggested_entity_id or f"knx.{slugify(name)}"

    attributes: dict[str, Any] = {
        "friendly_name": name,
        "integration": "estada",
        "protocol": "knx",
    }
    custom_attributes = params.get("attributes")
    if isinstance(custom_attributes, dict):
        attributes.update(custom_attributes)

    initial_state = str(params.get("initial_state", "unknown"))
    ctx.hass.states.async_set(entity_id, initial_state, attributes)
    ctx.knx_entities[entity_id] = {
        "name": name,
        "attributes": attributes,
    }

    return {
        "status": "created",
        "entity_id": entity_id,
    }


DEFINITION = CommandDefinition(
    name="create-knx-entity",
    args={
        "name": {
            "type": "string",
            "required": True,
        },
        "commandSequenceId": {
            "type": "string",
            "required": True,
        },
    },
    handler=async_handle_create_knx_entity,
)
