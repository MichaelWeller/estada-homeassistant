"""Tests for Estada MQTT command handling."""

import json

from custom_components.estada.mqtt_bridge import EstadaMqttBridge

from homeassistant.core import HomeAssistant


async def test_ping_command_returns_pong(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test ping command produces a response message."""
    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()
    mqtt_env.published.clear()

    await mqtt_env.async_fire_message(
        "estada/test-client/commands/ping",
        json.dumps({"commandSequenceId": "seq-1", "params": {}}),
    )
    await hass.async_block_till_done()

    assert len(mqtt_env.published) == 1
    topic, payload_raw, _qos, _retain = mqtt_env.published[0]
    payload = json.loads(payload_raw)

    assert topic == "estada/test-client/commands/response/ping"
    assert payload["status"] == "ok"
    assert payload["result"]["response"] == "pong"

    await bridge.async_unload()


async def test_missing_command_sequence_id_returns_error(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test command validation fails when commandSequenceId is missing."""
    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()
    mqtt_env.published.clear()

    await mqtt_env.async_fire_message(
        "estada/test-client/commands/ping",
        json.dumps({"params": {}}),
    )
    await hass.async_block_till_done()

    assert len(mqtt_env.published) == 1
    topic, payload_raw, _qos, _retain = mqtt_env.published[0]
    payload = json.loads(payload_raw)

    assert topic == "estada/test-client/errors"
    assert payload["error"] == "command_failed"

    await bridge.async_unload()


async def test_import_project_creates_entities(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test import-project command creates KNX entities."""
    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()
    mqtt_env.published.clear()

    project_json = {
        "groupAddresses": [
            {
                "id": "ga1-1",
                "address": "1",
                "name": "Lights",
            }
        ],
        "floors": [
            {
                "id": "floor-1",
                "name": "Ground Floor",
                "tag": "eg",
                "rooms": [
                    {
                        "id": "room-1",
                        "name": "Living Room",
                        "tag": "wz",
                        "functions": [
                            {
                                "id": "func-1",
                                "name": "Main Light",
                                "tag": "light_main",
                                "type": "light_switch",
                                "datapoints": {
                                    "switch": {
                                        "command": "1/1/1",
                                        "state": "1/1/2",
                                    }
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }

    await mqtt_env.async_fire_message(
        "estada/test-client/commands/import-project",
        json.dumps(
            {
                "commandSequenceId": "seq-1",
                "params": {"project": project_json},
            }
        ),
    )
    await hass.async_block_till_done()

    assert len(mqtt_env.published) >= 1
    topic, payload_raw, _qos, _retain = mqtt_env.published[-1]
    payload = json.loads(payload_raw)

    assert topic == "estada/test-client/commands/response/import-project"
    assert payload["status"] == "ok"
    assert payload["result"]["summary"]["created"] == 1
    assert len(payload["result"]["errors"]) == 0

    await bridge.async_unload()


async def test_import_project_missing_project_param(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test import-project command fails without project parameter."""
    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()
    mqtt_env.published.clear()

    await mqtt_env.async_fire_message(
        "estada/test-client/commands/import-project",
        json.dumps(
            {
                "commandSequenceId": "seq-1",
                "params": {},
            }
        ),
    )
    await hass.async_block_till_done()

    assert len(mqtt_env.published) >= 1
    topic, payload_raw, _qos, _retain = mqtt_env.published[-1]
    payload = json.loads(payload_raw)

    assert topic == "estada/test-client/errors"
    assert payload["error"] == "command_failed"

    await bridge.async_unload()
