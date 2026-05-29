"""Sensor platform for Estada runtime status metrics."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CLIENT_ID, CONF_MQTT_CLIENT_ID, DATA_STATUS_COORDINATOR, DOMAIN
from .status import EstadaStatusCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Estada status sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_STATUS_COORDINATOR]
    client_id = str(
        entry.data.get(CONF_CLIENT_ID) or entry.data.get(CONF_MQTT_CLIENT_ID)
    )

    async_add_entities(
        [
            EstadaMqttMessagesReceivedSensor(coordinator, entry.entry_id, client_id),
            EstadaMqttMessagesSentSensor(coordinator, entry.entry_id, client_id),
            EstadaMqttMessagesSendFailedSensor(coordinator, entry.entry_id, client_id),
            EstadaKnxTelegramsReceivedSensor(coordinator, entry.entry_id, client_id),
            EstadaKnxTelegramsForwardedSensor(coordinator, entry.entry_id, client_id),
        ]
    )


class EstadaStatusSensorBase(CoordinatorEntity[EstadaStatusCoordinator], SensorEntity):
    """Base class for Estada status sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "msg"

    def __init__(
        self,
        coordinator: EstadaStatusCoordinator,
        entry_id: str,
        client_id: str,
    ) -> None:
        """Initialize base sensor."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._client_id = client_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return Estada pseudo device to group status entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=f"Estada {self._client_id}",
            manufacturer="Estada",
            model="MQTT Bridge",
        )


class EstadaMqttMessagesReceivedSensor(EstadaStatusSensorBase):
    """Sensor for inbound MQTT message count."""

    _attr_name = "MQTT messages received"

    def __init__(
        self,
        coordinator: EstadaStatusCoordinator,
        entry_id: str,
        client_id: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry_id, client_id)
        self._attr_unique_id = f"{entry_id}_mqtt_messages_received"

    @property
    def native_value(self) -> int:
        """Return MQTT message count."""
        return int(self.coordinator.data["mqtt_messages_received"])


class EstadaMqttMessagesSentSensor(EstadaStatusSensorBase):
    """Sensor for outbound MQTT message count."""

    _attr_name = "MQTT messages sent"

    def __init__(
        self,
        coordinator: EstadaStatusCoordinator,
        entry_id: str,
        client_id: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry_id, client_id)
        self._attr_unique_id = f"{entry_id}_mqtt_messages_sent"

    @property
    def native_value(self) -> int:
        """Return MQTT message count."""
        return int(self.coordinator.data["mqtt_messages_sent"])


class EstadaMqttMessagesSendFailedSensor(EstadaStatusSensorBase):
    """Sensor for failed outbound MQTT message count."""

    _attr_name = "MQTT messages send failed"

    def __init__(
        self,
        coordinator: EstadaStatusCoordinator,
        entry_id: str,
        client_id: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry_id, client_id)
        self._attr_unique_id = f"{entry_id}_mqtt_messages_send_failed"

    @property
    def native_value(self) -> int:
        """Return failed MQTT publish count."""
        return int(self.coordinator.data["mqtt_messages_send_failed"])


class EstadaKnxTelegramsReceivedSensor(EstadaStatusSensorBase):
    """Sensor for received KNX telegram count."""

    _attr_name = "KNX telegrams received"

    def __init__(
        self,
        coordinator: EstadaStatusCoordinator,
        entry_id: str,
        client_id: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry_id, client_id)
        self._attr_unique_id = f"{entry_id}_knx_telegrams_received"

    @property
    def native_value(self) -> int:
        """Return received KNX telegram count."""
        return int(self.coordinator.data["knx_telegrams_received"])


class EstadaKnxTelegramsForwardedSensor(EstadaStatusSensorBase):
    """Sensor for KNX telegrams forwarded to MQTT."""

    _attr_name = "KNX telegrams forwarded"

    def __init__(
        self,
        coordinator: EstadaStatusCoordinator,
        entry_id: str,
        client_id: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry_id, client_id)
        self._attr_unique_id = f"{entry_id}_knx_telegrams_forwarded"

    @property
    def native_value(self) -> int:
        """Return forwarded KNX telegram count."""
        return int(self.coordinator.data["knx_telegrams_forwarded"])
