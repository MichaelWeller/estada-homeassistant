"""Status tracking for Estada integration runtime diagnostics."""

from datetime import UTC, datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def _initial_status() -> dict[str, Any]:
    """Create initial status payload."""
    return {
        "mqtt_connected": False,
        "knx_installed": False,
        "knx_running": False,
        "mqtt_messages_received": 0,
        "mqtt_messages_sent": 0,
        "mqtt_messages_send_failed": 0,
        "knx_telegrams_received": 0,
        "knx_telegrams_forwarded": 0,
        "last_received_topic": None,
        "last_received_at": None,
        "last_sent_topic": None,
        "last_sent_at": None,
        "last_error": None,
    }


class EstadaStatusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Push coordinator for runtime status metrics."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize status coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=entry,
            name=f"estada_status_{entry.entry_id}",
        )
        self.async_set_updated_data(_initial_status())

    @callback
    def mark_mqtt_connected(self) -> None:
        """Mark MQTT as connected."""
        self._update({"mqtt_connected": True})

    @callback
    def mark_mqtt_disconnected(self, error_message: str | None = None) -> None:
        """Mark MQTT as disconnected and record optional error."""
        patch: dict[str, Any] = {"mqtt_connected": False}
        if error_message is not None:
            patch["last_error"] = error_message
        self._update(patch)

    @callback
    def mark_knx_status(self, *, installed: bool, running: bool) -> None:
        """Update KNX integration availability status."""
        self._update(
            {
                "knx_installed": installed,
                "knx_running": running,
            }
        )

    @callback
    def mark_message_received(self, topic: str) -> None:
        """Increment inbound MQTT message metrics."""
        current = self.data
        self._update(
            {
                "mqtt_messages_received": int(current["mqtt_messages_received"]) + 1,
                "last_received_topic": topic,
                "last_received_at": datetime.now(UTC).isoformat(),
            }
        )

    @callback
    def mark_message_sent(self, topic: str) -> None:
        """Increment outbound MQTT success metrics."""
        current = self.data
        self._update(
            {
                "mqtt_messages_sent": int(current["mqtt_messages_sent"]) + 1,
                "last_sent_topic": topic,
                "last_sent_at": datetime.now(UTC).isoformat(),
            }
        )

    @callback
    def mark_message_send_failed(self, topic: str, error_message: str) -> None:
        """Increment outbound MQTT failure metrics."""
        current = self.data
        self._update(
            {
                "mqtt_messages_send_failed": int(current["mqtt_messages_send_failed"])
                + 1,
                "last_error": f"publish:{topic}: {error_message}",
            }
        )

    @callback
    def mark_knx_telegram_received(self) -> None:
        """Increment received KNX telegram counter."""
        current = self.data
        self._update(
            {
                "knx_telegrams_received": int(current["knx_telegrams_received"]) + 1,
            }
        )

    @callback
    def mark_knx_telegram_forwarded(self) -> None:
        """Increment forwarded KNX telegram counter."""
        current = self.data
        self._update(
            {
                "knx_telegrams_forwarded": int(current["knx_telegrams_forwarded"]) + 1,
            }
        )

    @callback
    def _update(self, patch: dict[str, Any]) -> None:
        """Apply patch and push fresh status payload."""
        updated = dict(self.data)
        updated.update(patch)
        self.async_set_updated_data(updated)
