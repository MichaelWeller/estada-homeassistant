"""Binary sensor platform for Estada connection status."""

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up Estada status binary sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_STATUS_COORDINATOR]
    client_id = str(
        entry.data.get(CONF_CLIENT_ID) or entry.data.get(CONF_MQTT_CLIENT_ID)
    )

    async_add_entities(
        [
            EstadaMqttConnectedBinarySensor(coordinator, entry.entry_id, client_id),
            EstadaKnxRunningBinarySensor(coordinator, entry.entry_id, client_id),
        ]
    )


class EstadaMqttConnectedBinarySensor(
    CoordinatorEntity[EstadaStatusCoordinator], BinarySensorEntity
):
    """Binary sensor indicating MQTT connectivity for Estada."""

    _attr_name = "MQTT connected"
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: EstadaStatusCoordinator,
        entry_id: str,
        client_id: str,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_mqtt_connected"
        self._entry_id = entry_id
        self._client_id = client_id

    @property
    def is_on(self) -> bool:
        """Return whether MQTT is connected."""
        return bool(self.coordinator.data["mqtt_connected"])

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Expose additional runtime diagnostic details."""
        return {
            "knx_installed": bool(self.coordinator.data["knx_installed"]),
            "knx_running": bool(self.coordinator.data["knx_running"]),
            "knx_telegrams_received": int(
                self.coordinator.data["knx_telegrams_received"]
            ),
            "knx_telegrams_forwarded": int(
                self.coordinator.data["knx_telegrams_forwarded"]
            ),
            "last_received_topic": self.coordinator.data["last_received_topic"],
            "last_received_at": self.coordinator.data["last_received_at"],
            "last_sent_topic": self.coordinator.data["last_sent_topic"],
            "last_sent_at": self.coordinator.data["last_sent_at"],
            "last_error": self.coordinator.data["last_error"],
            "mqtt_messages_received": int(
                self.coordinator.data["mqtt_messages_received"]
            ),
            "mqtt_messages_sent": int(self.coordinator.data["mqtt_messages_sent"]),
            "mqtt_messages_send_failed": int(
                self.coordinator.data["mqtt_messages_send_failed"]
            ),
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return Estada pseudo device to group status entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=f"Estada {self._client_id}",
            manufacturer="Estada",
            model="MQTT Bridge",
        )


class EstadaKnxRunningBinarySensor(
    CoordinatorEntity[EstadaStatusCoordinator], BinarySensorEntity
):
    """Binary sensor indicating KNX integration runtime status."""

    _attr_name = "KNX running"
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: EstadaStatusCoordinator,
        entry_id: str,
        client_id: str,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_knx_running"
        self._entry_id = entry_id
        self._client_id = client_id

    @property
    def is_on(self) -> bool:
        """Return whether KNX integration is running."""
        return bool(self.coordinator.data["knx_running"])

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        """Expose KNX availability details."""
        return {
            "knx_installed": bool(self.coordinator.data["knx_installed"]),
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return Estada pseudo device to group status entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=f"Estada {self._client_id}",
            manufacturer="Estada",
            model="MQTT Bridge",
        )
