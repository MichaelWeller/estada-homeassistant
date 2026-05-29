"""Tests for Estada state import and service resolution."""

import json
from typing import Any

import pytest

from homeassistant.core import HomeAssistant

from custom_components.estada.mqtt_bridge import EstadaMqttBridge


async def test_import_calls_resolved_service(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test entity import resolves to expected Home Assistant service call."""
    recorded_calls: list[dict[str, Any]] = []

    async def _handle_turn_on(call) -> None:
        recorded_calls.append(dict(call.data))

    hass.services.async_register("switch", "turn_on", _handle_turn_on)
    hass.states.async_set("switch.estada_test", "off")

    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()
    mqtt_env.published.clear()

    await mqtt_env.async_fire_message(
        "estada/test-client/entities/switch.estada_test",
        json.dumps({"state": "on"}),
    )
    await hass.async_block_till_done()

    assert recorded_calls == [{"entity_id": "switch.estada_test"}]

    response_topics = [topic for topic, _payload, _qos, _retain in mqtt_env.published]
    assert "estada/test-client/commands/response/state-update" in response_topics

    await bridge.async_unload()


@pytest.mark.parametrize(
    (
        "entity_id",
        "input_state",
        "expected_service_domain",
        "expected_service_name",
        "expected_data",
    ),
    [
        pytest.param(
            "lock.front_door",
            "locked",
            "lock",
            "lock",
            {"entity_id": "lock.front_door"},
            id="lock-locked",
        ),
        pytest.param(
            "cover.terrace",
            "opening",
            "cover",
            "open_cover",
            {"entity_id": "cover.terrace"},
            id="cover-opening",
        ),
        pytest.param(
            "select.hvac_mode",
            "eco",
            "select",
            "select_option",
            {"entity_id": "select.hvac_mode", "option": "eco"},
            id="select-option",
        ),
        pytest.param(
            "number.target_temp",
            "21.5",
            "number",
            "set_value",
            {"entity_id": "number.target_temp", "value": 21.5},
            id="number-value",
        ),
    ],
)
async def test_import_resolver_mappings(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
    entity_id: str,
    input_state: str,
    expected_service_domain: str,
    expected_service_name: str,
    expected_data: dict[str, Any],
) -> None:
    """Test resolver mappings across supported domains."""
    recorded_calls: list[dict[str, Any]] = []

    async def _record_service_call(call) -> None:
        recorded_calls.append(dict(call.data))

    hass.services.async_register(
        expected_service_domain,
        expected_service_name,
        _record_service_call,
    )
    hass.states.async_set(entity_id, "unknown")

    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()
    mqtt_env.published.clear()

    await mqtt_env.async_fire_message(
        f"estada/test-client/entities/{entity_id}",
        json.dumps({"state": input_state}),
    )
    await hass.async_block_till_done()

    assert recorded_calls == [expected_data]

    await bridge.async_unload()


async def test_import_reports_unknown_entity_as_error(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test unknown entity inbound message is published as an error."""
    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()
    mqtt_env.published.clear()

    await mqtt_env.async_fire_message(
        "estada/test-client/entities/switch.unknown_entity",
        json.dumps({"state": "on"}),
    )
    await hass.async_block_till_done()

    assert len(mqtt_env.published) == 1
    topic, payload_raw, _qos, _retain = mqtt_env.published[0]
    payload = json.loads(payload_raw)

    assert topic == "estada/test-client/errors"
    assert payload["error"] == "unknown_entity"

    await bridge.async_unload()
