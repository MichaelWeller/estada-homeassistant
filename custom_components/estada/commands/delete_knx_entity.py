"""Delete KNX entity command implementation."""

from typing import Any

from .base import CommandContext, CommandDefinition


async def async_handle_delete_knx_entity(
    ctx: CommandContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Delete a KNX-like entity created by Estada command handling."""
    name = str(params.get("name", "")).strip()
    if not name:
        raise ValueError("'name' is required")

    entity_id = _find_entity_id_by_name(ctx.knx_entities, name)
    if entity_id is None:
        raise ValueError(f"No KNX entity found for name '{name}'")

    ctx.hass.states.async_remove(entity_id)
    ctx.knx_entities.pop(entity_id, None)

    return {
        "status": "deleted",
        "entity_id": entity_id,
    }


def _find_entity_id_by_name(
    entities: dict[str, dict[str, Any]],
    name: str,
) -> str | None:
    """Find first entity id by matching stored name."""
    lowered = name.casefold()
    for entity_id, data in entities.items():
        if str(data.get("name", "")).casefold() == lowered:
            return entity_id
    return None


DEFINITION = CommandDefinition(
    name="delete-knx-entity",
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
    handler=async_handle_delete_knx_entity,
)
