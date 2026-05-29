"""Tests for Estada runtime status counters."""

import json
from types import SimpleNamespace

from homeassistant.core import HomeAssistant

from custom_components.estada.const import DATA_STATUS_COORDINATOR
from custom_components.estada.mqtt_bridge import EstadaMqttBridge


async def test_status_updates_for_received_and_sent_messages(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test status counters for in/out MQTT traffic."""
    hass.config = SimpleNamespace(components={"knx"})
    hass.config_entries = SimpleNamespace(
        async_entries=lambda domain: [object()] if domain == "knx" else []
    )

    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()

    coordinator = runtime_data[DATA_STATUS_COORDINATOR]
    assert coordinator.data["mqtt_connected"] is True
    assert coordinator.data["knx_installed"] is True
    assert coordinator.data["knx_running"] is True
    assert coordinator.data["messages_received"] == 0
    assert coordinator.data["messages_sent"] == 1
    assert coordinator.data["knx_telegrams_received"] == 0
    assert coordinator.data["knx_telegrams_forwarded"] == 0

    mqtt_env.published.clear()
    hass.states.async_set("switch.estada_test", "off")
    await hass.async_block_till_done()
    mqtt_env.published.clear()

    hass.states.async_set("switch.estada_test", "on")
    await hass.async_block_till_done()

    await mqtt_env.async_fire_message(
        "estada/test-client/entities/switch.estada_test",
        json.dumps({"state": "off"}),
    )
    await hass.async_block_till_done()

    assert coordinator.data["messages_received"] == 1
    assert coordinator.data["messages_sent"] >= 2
    assert (
        coordinator.data["last_received_topic"]
        == "estada/test-client/entities/switch.estada_test"
    )
    assert coordinator.data["last_sent_topic"] is not None

    await bridge.async_unload()
    assert coordinator.data["mqtt_connected"] is False


async def test_status_tracks_knx_telegrams_received_and_forwarded(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test KNX telegram counters track received and forwarded telegrams."""
    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()

    coordinator = runtime_data[DATA_STATUS_COORDINATOR]
    mqtt_env.published.clear()

    await hass.bus.async_fire(
        "knx_event",
        {
            "destination": "1/2/3",
            "source": "1.1.10",
            "direction": "incoming",
            "telegramtype": "GroupValueWrite",
            "data": [1],
            "value": 1,
        },
    )
    await hass.async_block_till_done()

    assert coordinator.data["knx_telegrams_received"] == 1
    assert coordinator.data["knx_telegrams_forwarded"] == 1

    await bridge.async_unload()
