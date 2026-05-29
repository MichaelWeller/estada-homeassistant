"""Tests for Estada binary status sensors."""

from homeassistant.core import HomeAssistant

from custom_components.estada.binary_sensor import (
    EstadaKnxRunningBinarySensor,
    EstadaMqttConnectedBinarySensor,
)
from custom_components.estada.const import DATA_STATUS_COORDINATOR


async def test_binary_sensors_reflect_runtime_status(
    hass: HomeAssistant,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test binary sensors follow coordinator runtime status."""
    del hass, estada_config_entry
    coordinator = runtime_data[DATA_STATUS_COORDINATOR]

    mqtt_sensor = EstadaMqttConnectedBinarySensor(coordinator, "entry-1", "test-client")
    knx_sensor = EstadaKnxRunningBinarySensor(coordinator, "entry-1", "test-client")

    assert mqtt_sensor.is_on is False
    assert knx_sensor.is_on is False
    assert knx_sensor.extra_state_attributes["knx_installed"] is False

    coordinator.mark_mqtt_connected()
    coordinator.mark_knx_status(installed=True, running=True)

    assert mqtt_sensor.is_on is True
    assert knx_sensor.is_on is True
    assert knx_sensor.extra_state_attributes["knx_installed"] is True


async def test_knx_sensor_off_when_not_running(
    hass: HomeAssistant,
    estada_config_entry,
    runtime_data,
) -> None:
    """Test KNX sensor stays off when KNX is installed but not running."""
    del hass, estada_config_entry
    coordinator = runtime_data[DATA_STATUS_COORDINATOR]

    knx_sensor = EstadaKnxRunningBinarySensor(coordinator, "entry-1", "test-client")

    coordinator.mark_knx_status(installed=True, running=False)

    assert knx_sensor.is_on is False
    assert knx_sensor.extra_state_attributes["knx_installed"] is True
