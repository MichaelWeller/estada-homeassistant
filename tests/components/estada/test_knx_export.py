"""Tests for KNX telegram export to MQTT."""

import json
from types import SimpleNamespace

from homeassistant.components.knx.const import KNX_MODULE_KEY
from homeassistant.core import HomeAssistant

from custom_components.estada.const import DATA_STATUS_COORDINATOR
from custom_components.estada.mqtt_bridge import EstadaMqttBridge


async def test_exports_incoming_knx_telegram_to_mqtt(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test incoming KNX telegrams are exported as raw payloads."""
    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()

    mqtt_env.published.clear()

    await hass.bus.async_fire(
        "knx_event",
        {
            "destination": "1/2/3",
            "source": "1.1.10",
            "direction": "incoming",
            "telegramtype": "GroupValueWrite",
            "data": [1, 2, 3],
            "value": None,
        },
    )
    await hass.async_block_till_done()

    assert len(mqtt_env.published) == 1
    topic, payload_raw, _qos, _retain = mqtt_env.published[0]
    payload = json.loads(payload_raw)

    assert topic == "estada/test-client/knx/ga/1/2/3"
    assert payload["destination"] == "1/2/3"
    assert payload["source"] == "1.1.10"
    assert payload["telegramtype"] == "GroupValueWrite"
    assert payload["direction"].lower() == "incoming"
    assert payload["data"] == [1, 2, 3]

    await bridge.async_unload()


async def test_knx_ga_exclude_pattern_blocks_export(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test KNX GA exclude pattern suppresses MQTT export."""
    estada_config_entry.options = {
        "knx_ga_include_patterns": ["*"],
        "knx_ga_exclude_patterns": ["1/2/*"],
    }

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
            "data": [255],
            "value": None,
        },
    )
    await hass.async_block_till_done()

    assert not mqtt_env.published
    assert coordinator.data["knx_telegrams_received"] == 1
    assert coordinator.data["knx_telegrams_forwarded"] == 0

    await bridge.async_unload()


async def test_knx_status_marks_installed_but_not_running(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test KNX status is tracked even when KNX is not running."""
    mqtt_env.published.clear()
    hass.config = SimpleNamespace(components=set())
    hass.config_entries = SimpleNamespace(
        async_entries=lambda domain: [object()] if domain == "knx" else []
    )

    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()

    coordinator = runtime_data[DATA_STATUS_COORDINATOR]
    assert coordinator.data["knx_installed"] is True
    assert coordinator.data["knx_running"] is False

    await bridge.async_unload()


async def test_registers_known_knx_group_addresses_for_knx_event(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test Estada fallback registers KNX group addresses via knx.event_register."""
    del mqtt_env
    hass.config = SimpleNamespace(components={"knx"})
    hass.config_entries = SimpleNamespace(
        async_entries=lambda domain: [object()] if domain == "knx" else []
    )

    calls: list[dict] = []

    async def _handle_event_register(call) -> None:
        calls.append(call.data)

    hass.services.async_register("knx", "event_register", _handle_event_register)
    hass.data = {
        KNX_MODULE_KEY: SimpleNamespace(
            xknx=SimpleNamespace(telegram_queue=SimpleNamespace()),
            group_address_entities={"1/2/3": set(), "2/3/4": set()},
        )
    }

    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()

    assert calls
    assert sorted(calls[0]["address"]) == ["1/2/3", "2/3/4"]

    await bridge.async_unload()


async def test_direct_knx_callback_exports_unknown_group_address(
    hass: HomeAssistant,
    mqtt_env,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test direct KNX telegram callback exports unknown group addresses."""

    class FakeTelegramQueue:
        def __init__(self) -> None:
            self.callback = None

        def register_telegram_received_cb(self, callback):
            self.callback = callback
            return callback

        def unregister_telegram_received_cb(self, callback):
            if self.callback == callback:
                self.callback = None

    queue = FakeTelegramQueue()

    hass.config = SimpleNamespace(components={"knx"})
    hass.config_entries = SimpleNamespace(
        async_entries=lambda domain: [object()] if domain == "knx" else []
    )
    hass.data = {
        KNX_MODULE_KEY: SimpleNamespace(
            xknx=SimpleNamespace(telegram_queue=queue),
            group_address_entities={},
            group_address_transcoder={},
            _address_filter_transcoder={},
        )
    }

    bridge = EstadaMqttBridge(hass, estada_config_entry, runtime_data)
    assert await bridge.async_setup()

    mqtt_env.published.clear()
    telegram = SimpleNamespace(
        direction=SimpleNamespace(value="incoming"),
        destination_address="31/7/255",
        source_address="1.1.10",
        payload=SimpleNamespace(value=SimpleNamespace(value=[1, 2, 3])),
    )

    assert queue.callback is not None
    queue.callback(telegram)
    await hass.async_block_till_done()

    assert len(mqtt_env.published) == 1
    topic, payload_raw, _qos, _retain = mqtt_env.published[0]
    payload = json.loads(payload_raw)

    assert topic == "estada/test-client/knx/ga/31/7/255"
    assert payload["destination"] == "31/7/255"
    assert payload["source"] == "1.1.10"

    await bridge.async_unload()
    assert queue.callback is None
