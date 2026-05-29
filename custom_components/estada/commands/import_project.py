"""Import KNX project from Estada command implementation."""

import logging
from typing import Any

from homeassistant.util import slugify

from .base import CommandContext, CommandDefinition
from .create_knx_entity import async_handle_create_knx_entity
from ..import_store import EstadaImportStore

_LOGGER = logging.getLogger(__name__)


async def async_handle_import_project(
    ctx: CommandContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Import KNX project structure from Estada."""
    # Extract the project JSON from params
    project_json = params.get("project")
    if not isinstance(project_json, dict):
        raise ValueError("'project' parameter must be a JSON object")

    # Validate basic structure
    floors = project_json.get("floors", [])
    if not isinstance(floors, list):
        raise ValueError("'floors' must be an array")

    # Initialize storage
    data_dir = ctx.hass.config.path("estada_import", ctx.entry_id)
    store = EstadaImportStore(ctx.hass, ctx.entry_id, data_dir)

    # Load previous import state
    last_import = await store.load_last_import()
    mappings = await store.load_mappings()

    # Track import results
    created_count = 0
    updated_count = 0
    deleted_count = 0
    errors: list[dict[str, Any]] = []

    # Build a map of all entities from current project by function-id
    current_entities_by_id: dict[str, dict[str, Any]] = {}

    for floor in floors:
        rooms = floor.get("rooms", [])
        for room in rooms:
            functions = room.get("functions", [])
            for function in functions:
                function_id = function.get("id")
                if function_id:
                    current_entities_by_id[function_id] = {
                        "function": function,
                        "floor_name": floor.get("name", "Unknown"),
                        "room_name": room.get("name", "Unknown"),
                    }

    # Process current entities (create or update)
    for function_id, entity_info in current_entities_by_id.items():
        function = entity_info["function"]
        entity_name = function.get("name", f"KNX {function_id}")
        entity_type = function.get("type", "unknown")
        datapoints = function.get("datapoints", {})

        # Check if entity existed before
        ha_entity_id = mappings.get(function_id)

        try:
            if ha_entity_id:
                # Entity already exists - for now, we don't update, just track
                # Future: could support updating name and datapoint mappings
                updated_count += 1
                _LOGGER.debug(
                    "Entity %s already exists as %s", function_id, ha_entity_id
                )
            else:
                # New entity - create it
                create_params = {
                    "name": entity_name,
                    "entity_id": f"knx.{slugify(entity_name)}",
                    "attributes": {
                        "estada_id": function_id,
                        "entity_type": entity_type,
                        "floor": entity_info["floor_name"],
                        "room": entity_info["room_name"],
                        "function_tag": function.get("tag", ""),
                        "datapoints": datapoints,
                    },
                }

                result = await async_handle_create_knx_entity(ctx, create_params)
                ha_id = result.get("entity_id")
                mappings[function_id] = ha_id
                created_count += 1
                _LOGGER.info("Created entity %s (%s)", ha_id, function_id)

        except Exception as err:
            error_msg = str(err)
            errors.append(
                {
                    "function_id": function_id,
                    "name": entity_name,
                    "type": entity_type,
                    "error": error_msg,
                }
            )
            _LOGGER.error("Failed to create/update entity %s: %s", function_id, err)

    # Process deletions (entities in last import but not in current)
    if last_import:
        last_entities_by_id: dict[str, str] = {}

        for floor in last_import.get("floors", []):
            rooms = floor.get("rooms", [])
            for room in rooms:
                functions = room.get("functions", [])
                for function in functions:
                    function_id = function.get("id")
                    if function_id:
                        last_entities_by_id[function_id] = function.get(
                            "name", "Unknown"
                        )

        # Find deleted entities
        for function_id in last_entities_by_id:
            if function_id not in current_entities_by_id:
                ha_id = mappings.get(function_id)
                if ha_id:
                    try:
                        # Delete the entity from HA state machine
                        ctx.hass.states.async_remove(ha_id)
                        del mappings[function_id]
                        del ctx.knx_entities[ha_id]
                        deleted_count += 1
                        _LOGGER.info("Deleted entity %s (%s)", ha_id, function_id)
                    except Exception as err:
                        error_msg = str(err)
                        errors.append(
                            {
                                "function_id": function_id,
                                "name": last_entities_by_id.get(function_id, "Unknown"),
                                "error": f"Delete failed: {error_msg}",
                            }
                        )
                        _LOGGER.error(
                            "Failed to delete entity %s: %s", function_id, err
                        )

    # Save updated state
    try:
        await store.save_last_import(project_json)
        await store.save_mappings(mappings)
    except Exception as err:
        _LOGGER.error("Failed to save import state: %s", err)
        raise ValueError(f"Failed to save import state: {err}")

    # Build response
    return {
        "status": "completed",
        "summary": {
            "created": created_count,
            "updated": updated_count,
            "deleted": deleted_count,
            "errors": len(errors),
        },
        "errors": errors if errors else [],
    }


DEFINITION = CommandDefinition(
    name="import-project",
    args={
        "project": {
            "type": "object",
            "required": True,
        },
    },
    handler=async_handle_import_project,
)
