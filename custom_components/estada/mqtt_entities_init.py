"""Startup helpers to publish current Home Assistant entity states to MQTT."""

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import HomeAssistant

from .const import SOURCE_TAG_HA, topic_entities


async def init_mqtt_entities(
    hass: HomeAssistant,
    client_id: str,
    is_export_allowed: Callable[[str], bool],
    publish_safe: Callable[[str, Any], Awaitable[bool]],
) -> tuple[int, int]:
    """Publish all existing HA entity states once at startup.

    Returns tuple of (published_count, skipped_count).
    """
    published = 0
    skipped = 0

    for state in hass.states.async_all():
        entity_id = state.entity_id
        if not is_export_allowed(entity_id):
            skipped += 1
            continue

        payload: dict[str, Any] = {
            "state": state.state,
            "attributes": dict(state.attributes),
            "last_changed": state.last_changed.isoformat(),
            "source_tag": SOURCE_TAG_HA,
        }

        if await publish_safe(topic_entities(client_id, entity_id), payload):
            published += 1

    return published, skipped
