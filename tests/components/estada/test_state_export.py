"""Tests for Estada state export and loop protection."""

import json

from homeassistant.core import HomeAssistant

from custom_components.estada.const import OPTION_ENTITY_EXCLUDE_PATTERNS
from custom_components.estada.mqtt_bridge import EstadaMqttBridge


async def test_exports_state_changes_to_mqtt(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test that state changes are exported as MQTT JSON payloads."""
    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()

    mqtt_env.published.clear()

    hass.states.async_set("switch.estada_test", "off", {"friendly_name": "Estada Test"})
    await hass.async_block_till_done()
    mqtt_env.published.clear()

    hass.states.async_set("switch.estada_test", "on", {"friendly_name": "Estada Test"})
    await hass.async_block_till_done()

    assert len(mqtt_env.published) == 1
    topic, payload_raw, _qos, _retain = mqtt_env.published[0]
    assert topic == "estada/test-client/entities/switch.estada_test"

    payload = json.loads(payload_raw)
    assert payload["state"] == "on"
    assert payload["attributes"]["friendly_name"] == "Estada Test"
    assert payload["source_tag"] == "HA"

    await bridge.async_unload()


async def test_ignores_incoming_messages_with_ha_source_tag(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test inbound loop-protection for source_tag=HA."""
    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()

    hass.states.async_set("switch.estada_test", "off")
    await hass.async_block_till_done()

    mqtt_env.published.clear()

    await mqtt_env.async_fire_message(
        "estada/test-client/entities/switch.estada_test",
        json.dumps({"state": "on", "source_tag": "HA"}),
    )
    await hass.async_block_till_done()

    assert not mqtt_env.published

    await bridge.async_unload()


async def test_excludes_entities_by_wildcard_patterns(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test that wildcard exclude patterns suppress outbound export."""
    estada_config_entry.options = {
        OPTION_ENTITY_EXCLUDE_PATTERNS: [
            "sensor.estada_*",
            "switch.secret_*",
        ]
    }

    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()

    mqtt_env.published.clear()
    hass.states.async_set("sensor.estada_messages_sent", "5")
    hass.states.async_set("switch.secret_device", "on")
    await hass.async_block_till_done()

    assert not mqtt_env.published

    await bridge.async_unload()
