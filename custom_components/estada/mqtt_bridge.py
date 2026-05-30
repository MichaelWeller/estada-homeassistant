"""MQTT bridge for Estada integration state export/import and commands."""

import asyncio
from datetime import UTC, datetime
import fnmatch
import json
import logging
from typing import Any

from voluptuous.error import MultipleInvalid

from homeassistant.components import mqtt
from homeassistant.components.knx.const import KNX_MODULE_KEY
from homeassistant.components.mqtt import ReceiveMessage
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.json import JSONEncoder

from .commands import CommandRegistry
from .commands.base import CommandContext
from .const import (
    CONF_CLIENT_ID,
    CONF_MQTT_CLIENT_ID,
    DATA_KNX_ENTITIES,
    DATA_STATUS_COORDINATOR,
    DEFAULT_ENTITY_EXCLUDE_PATTERNS,
    DEFAULT_KNX_GA_EXCLUDE_PATTERNS,
    DEFAULT_KNX_GA_INCLUDE_PATTERNS,
    DEFAULT_QOS,
    DEFAULT_RETAIN,
    EVENT_KNX_EVENT,
    OPTION_DOMAIN_ALLOWLIST,
    OPTION_ENTITY_ALLOWLIST,
    OPTION_ENTITY_EXCLUDE_PATTERNS,
    OPTION_KNX_GA_EXCLUDE_PATTERNS,
    OPTION_KNX_GA_INCLUDE_PATTERNS,
    SOURCE_TAG_HA,
    topic_alive,
    topic_base,
    topic_command_response,
    topic_commands_list,
    topic_entities,
    topic_errors,
    topic_telegram,
)
from .mqtt_entities_init import init_mqtt_entities
from .service_resolver import resolve_service_call
from .status import EstadaStatusCoordinator

_LOGGER = logging.getLogger(__name__)


class EstadaMqttBridge:
    """Bridge between Home Assistant state/services and MQTT topics."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        runtime_data: dict[str, object],
    ) -> None:
        """Initialize the bridge for a single config entry."""
        self._hass = hass
        self._entry = entry
        self._runtime_data = runtime_data
        self._client_id = str(
            entry.data.get(CONF_CLIENT_ID) or entry.data.get(CONF_MQTT_CLIENT_ID) or ""
        ).strip()
        self._base_topic = topic_base(self._client_id)
        self._command_registry = CommandRegistry()
        self._mqtt_available = False
        self._status_coordinator = runtime_data[DATA_STATUS_COORDINATOR]
        assert isinstance(self._status_coordinator, EstadaStatusCoordinator)

        self._unsubscribe_mqtt: Any = None
        self._unsubscribe_state: Any = None
        self._unsubscribe_knx_event: Any = None
        self._knx_telegram_callback: Any = None
        self._use_direct_knx_telegrams = False

    async def async_setup(self) -> bool:
        """Set up subscriptions and publishers."""
        if not self._client_id:
            _LOGGER.error("Missing client_id in config entry")
            return False

        try:
            mqtt_available = await asyncio.wait_for(
                mqtt.async_wait_for_mqtt_client(self._hass),
                timeout=5.0,
            )
        except TimeoutError:
            _LOGGER.warning("MQTT integration is not available within timeout")
            return False

        if not mqtt_available:
            _LOGGER.error("MQTT integration is not available")
            return False
        self._mqtt_available = True
        self._status_coordinator.mark_mqtt_connected()
        knx_installed, knx_running = self._get_knx_status()
        self._status_coordinator.mark_knx_status(
            installed=knx_installed,
            running=knx_running,
        )

        if not knx_installed:
            _LOGGER.info(
                "KNX integration is not installed; Estada KNX export is disabled"
            )
        elif not knx_running:
            _LOGGER.info(
                "KNX integration is installed but currently not running; "
                "Estada KNX export is waiting for KNX events"
            )
        else:
            self._use_direct_knx_telegrams = self._setup_direct_knx_telegram_callback()
            if self._use_direct_knx_telegrams:
                _LOGGER.info(
                    "Using direct KNX telegram callback for full telegram monitoring"
                )
            else:
                await self._async_register_knx_event_addresses()

        @callback
        def _mqtt_callback(message: ReceiveMessage) -> None:
            self._hass.async_create_task(self._async_handle_mqtt_message(message))

        self._unsubscribe_mqtt = await mqtt.async_subscribe(
            self._hass,
            f"{self._base_topic}/#",
            _mqtt_callback,
            DEFAULT_QOS,
        )

        self._unsubscribe_state = self._hass.bus.async_listen(
            EVENT_STATE_CHANGED,
            self._async_handle_state_changed,
        )

        self._unsubscribe_knx_event = self._hass.bus.async_listen(
            EVENT_KNX_EVENT,
            self._async_handle_knx_event,
        )

        self._hass.async_create_task(
            self._async_publish_startup_exports(),
            eager_start=False,
        )
        return True

    async def _async_publish_startup_exports(self) -> None:
        """Publish startup MQTT exports without blocking integration setup."""
        published = await self._publish_command_list()
        if not published:
            _LOGGER.warning(
                "Initial command list publish failed; continuing and retrying later"
            )

        published_entities, skipped_entities = await init_mqtt_entities(
            self._hass,
            self._client_id,
            self._is_export_allowed,
            self._async_publish_safe,
        )
        _LOGGER.info(
            "Initial MQTT entity export finished: published=%d skipped=%d",
            published_entities,
            skipped_entities,
        )

    async def async_send_alive_message(self) -> None:
        """Publish a heartbeat message to the alive topic."""
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "client_id": self._client_id,
        }
        await self._async_publish_safe(
            topic_alive(self._client_id),
            payload,
        )

    async def async_unload(self) -> None:
        """Unload MQTT subscriptions and callbacks."""
        if self._unsubscribe_mqtt is not None:
            self._unsubscribe_mqtt()
            self._unsubscribe_mqtt = None

        if self._unsubscribe_state is not None:
            self._unsubscribe_state()
            self._unsubscribe_state = None

        if self._unsubscribe_knx_event is not None:
            self._unsubscribe_knx_event()
            self._unsubscribe_knx_event = None

        if self._knx_telegram_callback is not None:
            knx_module = self._get_knx_module()
            if knx_module is not None:
                telegram_queue = getattr(
                    getattr(knx_module, "xknx", None), "telegram_queue", None
                )
                unregister_cb = getattr(
                    telegram_queue, "unregister_telegram_received_cb", None
                )
                if callable(unregister_cb):
                    unregister_cb(self._knx_telegram_callback)
            self._knx_telegram_callback = None

        self._mqtt_available = False
        self._status_coordinator.mark_mqtt_disconnected("Bridge unloaded")

    async def _async_handle_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Publish state changes to MQTT."""
        entity_id = event.data["entity_id"]
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if new_state is None:
            return

        if not self._is_export_allowed(entity_id):
            return

        if _is_state_unchanged(old_state, new_state):
            return

        payload: dict[str, Any] = {
            "state": new_state.state,
            "attributes": dict(new_state.attributes),
            "last_changed": new_state.last_changed.isoformat(),
            "source_tag": SOURCE_TAG_HA,
        }

        await self._async_publish_safe(
            topic_entities(self._client_id, entity_id),
            payload,
        )

    async def _async_handle_mqtt_message(self, message: ReceiveMessage) -> None:
        """Dispatch inbound MQTT message by topic branch and filter loopbacks."""
        try:
            is_loopback = False
            try:
                payload = json.loads(message.payload)
                if isinstance(payload, dict):
                    if payload.get("source_tag") == "HA":
                        is_loopback = True
            except (TypeError, json.JSONDecodeError):
                pass

            if not is_loopback:
                self._status_coordinator.mark_message_received(message.topic)

            if not message.topic.startswith(f"{self._base_topic}/"):
                return

            relative_topic = message.topic[len(self._base_topic) + 1 :]

            if relative_topic.startswith("entities/"):
                entity_id = relative_topic.removeprefix("entities/")
                if entity_id:
                    await self._async_handle_entity_import(entity_id, message.payload)
                return

            if not relative_topic.startswith("command/"):
                return

            command_path = relative_topic.removeprefix("command/")
            if command_path == "list-of-commands" or command_path.startswith(
                "response/"
            ):
                return

            if "/" in command_path:
                command_name, _ = command_path.split("/", 1)
            else:
                command_name = command_path

            if command_name:
                await self._async_handle_command(command_name, message.payload)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Failed to process incoming MQTT message on topic '%s'", message.topic
            )
            await self._publish_error(
                error_code="message_processing_failed",
                message=str(err),
            )

    async def _async_handle_knx_event(self, event: Event) -> None:
        """Publish incoming KNX telegrams as raw GA payloads to MQTT."""
        if self._use_direct_knx_telegrams:
            # Direct KNX queue callback is active and already covers these telegrams.
            return

        direction_raw = event.data.get("direction")
        direction = str(direction_raw) if direction_raw is not None else ""
        if direction.lower() != "incoming":
            return

        group_address = event.data.get("destination")
        if not isinstance(group_address, str) or not group_address:
            return

        await self._async_publish_knx_payload(
            group_address=group_address,
            source=event.data.get("source"),
            telegramtype=event.data.get("telegramtype"),
            direction=direction,
            data=event.data.get("data"),
            value=event.data.get("value"),
        )

    async def _async_handle_knx_telegram(self, telegram: Any) -> None:
        """Publish KNX telegrams received directly from KNX telegram queue."""
        direction_obj = getattr(telegram, "direction", None)
        direction = (
            str(getattr(direction_obj, "value", direction_obj))
            if direction_obj is not None
            else ""
        )
        if direction.lower() != "incoming":
            return

        destination_address = getattr(telegram, "destination_address", None)
        if destination_address is None:
            return
        group_address = str(destination_address)
        if not group_address:
            return

        payload_obj = getattr(telegram, "payload", None)
        value_obj = getattr(payload_obj, "value", None)

        data = None
        if value_obj is not None and hasattr(value_obj, "value"):
            data = value_obj.value

        decoded_value = self._decode_knx_value(destination_address, value_obj)

        await self._async_publish_knx_payload(
            group_address=group_address,
            source=(
                str(source_address)
                if (source_address := getattr(telegram, "source_address", None))
                is not None
                else None
            ),
            telegramtype=(
                payload_obj.__class__.__name__ if payload_obj is not None else None
            ),
            direction=direction,
            data=data,
            value=decoded_value,
        )

    async def _async_handle_entity_import(
        self, entity_id: str, raw_payload: str
    ) -> None:
        """Handle inbound entity state update message."""
        payload = _safe_json_loads(raw_payload)
        if payload is None:
            await self._publish_error(
                error_code="invalid_json",
                message="Entity payload is not valid JSON",
                entity_id=entity_id,
            )
            return

        source_tag = payload.get("source_tag")
        if isinstance(source_tag, str) and source_tag == SOURCE_TAG_HA:
            return

        state_value = payload.get("state")
        if state_value is None:
            await self._publish_error(
                error_code="missing_state",
                message="Entity payload does not contain 'state'",
                entity_id=entity_id,
            )
            return

        if self._hass.states.get(entity_id) is None:
            await self._publish_error(
                error_code="unknown_entity",
                message=f"Entity '{entity_id}' does not exist",
                entity_id=entity_id,
            )
            return

        explicit_service = payload.get("service") or payload.get("action")
        if explicit_service is not None and not isinstance(explicit_service, str):
            await self._publish_error(
                error_code="invalid_service",
                message="Payload field 'service'/'action' must be a string",
                entity_id=entity_id,
            )
            return

        params = payload
        if params is not None and not isinstance(params, dict):
            await self._publish_error(
                error_code="invalid_params",
                message="Payload field 'params' must be a JSON object",
                entity_id=entity_id,
            )
            return

        resolved_service = resolve_service_call(
            self._hass,
            entity_id,
            str(state_value),
            explicit_service,
            params,
        )
        if resolved_service is None:
            await self._publish_error(
                error_code="service_resolution_failed",
                message=(
                    "Could not resolve a valid Home Assistant service "
                    f"for entity '{entity_id}' and state '{state_value}'"
                ),
                entity_id=entity_id,
            )
            return

        service_call, sanitized_params = resolved_service

        try:
            await self._hass.services.async_call(
                service_call.domain,
                service_call.service,
                {"entity_id": entity_id, **sanitized_params},
                blocking=True,
            )
        except MultipleInvalid as err:
            await self._publish_error(
                error_code="invalid_service_data",
                message=str(err),
                entity_id=entity_id,
            )
            return
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.exception("Failed to call service for %s", entity_id)
            await self._publish_error(
                error_code="service_call_failed",
                message=str(err),
                entity_id=entity_id,
            )
            return
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Unexpected error while importing state for %s", entity_id
            )
            await self._publish_error(
                error_code="entity_import_failed",
                message=str(err),
                entity_id=entity_id,
            )
            return

        response_payload = {
            "status": "ok",
            "entity_id": entity_id,
            "state": str(state_value),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self._async_publish_safe(
            topic_command_response(self._client_id, "state-update"),
            response_payload,
        )

    async def _async_handle_command(self, command_name: str, raw_payload: str) -> None:
        """Handle inbound command message."""
        payload = _safe_json_loads(raw_payload)
        if payload is None:
            await self._publish_error(
                error_code="invalid_json",
                message="Command payload is not valid JSON",
                command=command_name,
            )
            return

        if not isinstance(payload, dict):
            await self._publish_error(
                error_code="invalid_payload",
                message="Command payload must be a JSON object",
                command=command_name,
            )
            return

        if not self._command_registry.has_command(command_name):
            await self._publish_error(
                error_code="unsupported_command",
                message=f"Command '{command_name}' is not supported",
                command=command_name,
            )
            return

        knx_entities = self._runtime_data[DATA_KNX_ENTITIES]
        assert isinstance(knx_entities, dict)

        context = CommandContext(
            hass=self._hass,
            entry_id=self._entry.entry_id,
            client_id=self._client_id,
            knx_entities=knx_entities,
        )

        try:
            result = await self._command_registry.async_execute(
                context, command_name, payload
            )
        except ValueError as err:
            await self._publish_error(
                error_code="command_failed",
                message=str(err),
                command=command_name,
            )
            return

        await self._async_publish_safe(
            topic_command_response(self._client_id, result.command_name),
            result.payload,
        )

    async def _publish_command_list(self) -> bool:
        """Publish supported command metadata to MQTT."""
        return await self._async_publish_safe(
            topic_commands_list(self._client_id),
            self._command_registry.list_payload,
        )

    async def _publish_error(
        self,
        *,
        error_code: str,
        message: str,
        command: str | None = None,
        entity_id: str | None = None,
    ) -> None:
        """Publish an error payload to MQTT and also log it."""
        payload: dict[str, Any] = {
            "error": error_code,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if command is not None:
            payload["command"] = command
        if entity_id is not None:
            payload["entity_id"] = entity_id

        _LOGGER.warning("Estada error: %s", payload)
        try:
            await self._async_publish_safe(
                topic_errors(self._client_id),
                payload,
            )
        except HomeAssistantError:
            _LOGGER.debug(
                "Failed to publish Estada error payload because MQTT is unavailable"
            )

    async def _async_publish_safe(self, topic: str, payload_obj: Any) -> bool:
        """Publish MQTT payload object as JSON and handle MQTT unavailability."""
        if not await self._async_ensure_mqtt_connected():
            return False

        if not isinstance(payload_obj, dict):
            self._status_coordinator.mark_message_send_failed(
                topic, "Payload must be a JSON object"
            )
            _LOGGER.warning(
                "Failed to publish MQTT topic '%s': payload must be a JSON object",
                topic,
            )
            return False

        payload_data = dict(payload_obj)
        payload_data["source_tag"] = SOURCE_TAG_HA

        try:
            payload_json = json.dumps(payload_data, cls=JSONEncoder)
        except (TypeError, ValueError) as err:
            self._status_coordinator.mark_message_send_failed(
                topic, "JSON serialization failed"
            )
            _LOGGER.warning("Failed to serialize MQTT payload for '%s': %s", topic, err)
            return False

        try:
            await mqtt.async_publish(
                self._hass,
                topic,
                payload_json,
                DEFAULT_QOS,
                DEFAULT_RETAIN,
            )
        except HomeAssistantError:
            self._mqtt_available = False
            self._status_coordinator.mark_mqtt_disconnected("MQTT publish failed")
            _LOGGER.warning(
                "MQTT publish failed for topic '%s'; trying reconnect and one retry",
                topic,
            )

            if not await self._async_ensure_mqtt_connected():
                self._status_coordinator.mark_message_send_failed(
                    topic, "MQTT publish failed (reconnect failed)"
                )
                return False

            try:
                await mqtt.async_publish(
                    self._hass,
                    topic,
                    payload_json,
                    DEFAULT_QOS,
                    DEFAULT_RETAIN,
                )
            except HomeAssistantError:
                self._mqtt_available = False
                self._status_coordinator.mark_mqtt_disconnected(
                    "MQTT publish failed after reconnect"
                )
                self._status_coordinator.mark_message_send_failed(
                    topic, "MQTT publish failed after reconnect"
                )
                _LOGGER.warning(
                    "MQTT publish retry failed for topic '%s' after reconnect", topic
                )
                return False

            _LOGGER.warning(
                "MQTT publish topic succeeded '%s'",
                topic,
            )

        self._status_coordinator.mark_message_sent(topic)
        return True

    async def _async_ensure_mqtt_connected(self) -> bool:
        """Ensure MQTT client is connected and authenticated."""
        if self._mqtt_available:
            return True

        try:
            mqtt_available = await asyncio.wait_for(
                mqtt.async_wait_for_mqtt_client(self._hass),
                timeout=5.0,
            )
        except TimeoutError:
            self._status_coordinator.mark_mqtt_disconnected(
                "MQTT not available (timeout)"
            )
            return False

        if not mqtt_available:
            self._status_coordinator.mark_mqtt_disconnected("MQTT not available")
            return False

        self._mqtt_available = True
        self._status_coordinator.mark_mqtt_connected()
        return True

    def _is_export_allowed(self, entity_id: str) -> bool:
        """Return whether an entity should be exported."""
        exclude_patterns = tuple(
            self._entry.options.get(
                OPTION_ENTITY_EXCLUDE_PATTERNS,
                list(DEFAULT_ENTITY_EXCLUDE_PATTERNS),
            )
        )
        if any(fnmatch.fnmatchcase(entity_id, pattern) for pattern in exclude_patterns):
            return False

        entity_allowlist = set(self._entry.options.get(OPTION_ENTITY_ALLOWLIST, []))
        domain_allowlist = set(self._entry.options.get(OPTION_DOMAIN_ALLOWLIST, []))

        if not entity_allowlist and not domain_allowlist:
            return True

        if entity_id in entity_allowlist:
            return True

        if "." in entity_id:
            domain, _ = entity_id.split(".", 1)
            return domain in domain_allowlist

        return False

    def _is_knx_ga_export_allowed(self, group_address: str) -> bool:
        """Return whether a KNX group address should be exported."""
        include_patterns = tuple(
            self._entry.options.get(
                OPTION_KNX_GA_INCLUDE_PATTERNS,
                list(DEFAULT_KNX_GA_INCLUDE_PATTERNS),
            )
        )
        exclude_patterns = tuple(
            self._entry.options.get(
                OPTION_KNX_GA_EXCLUDE_PATTERNS,
                list(DEFAULT_KNX_GA_EXCLUDE_PATTERNS),
            )
        )

        if include_patterns and not any(
            fnmatch.fnmatchcase(group_address, pattern) for pattern in include_patterns
        ):
            return False

        if any(
            fnmatch.fnmatchcase(group_address, pattern) for pattern in exclude_patterns
        ):
            return False

        return True

    async def _async_publish_knx_payload(
        self,
        *,
        group_address: str,
        source: str | None,
        telegramtype: str | None,
        direction: str,
        data: Any,
        value: Any,
    ) -> None:
        """Publish normalized KNX telegram payload and update counters."""
        self._status_coordinator.mark_knx_telegram_received()

        if not self._is_knx_ga_export_allowed(group_address):
            return

        payload = {
            "destination": group_address,
            "source": source,
            "telegramtype": telegramtype,
            "direction": direction,
            "data": data,
            "value": value,
            "timestamp": datetime.now(UTC).isoformat(),
            "source_tag": SOURCE_TAG_HA,
        }

        published = await self._async_publish_safe(
            topic_telegram(self._client_id, group_address),
            payload,
        )
        if published:
            self._status_coordinator.mark_knx_telegram_forwarded()

    def _setup_direct_knx_telegram_callback(self) -> bool:
        """Attach direct KNX telegram callback for full telegram monitoring."""
        knx_module = self._get_knx_module()
        if knx_module is None:
            return False

        telegram_queue = getattr(
            getattr(knx_module, "xknx", None), "telegram_queue", None
        )
        register_cb = getattr(telegram_queue, "register_telegram_received_cb", None)
        if not callable(register_cb):
            return False

        @callback
        def _telegram_callback(telegram: Any) -> None:
            self._hass.async_create_task(self._async_handle_knx_telegram(telegram))

        self._knx_telegram_callback = register_cb(_telegram_callback)
        return True

    async def _async_register_knx_event_addresses(self) -> None:
        """Register known KNX group addresses for `knx_event` generation."""
        if not self._hass.services.has_service("knx", "event_register"):
            _LOGGER.info(
                "KNX service knx.event_register is not available; "
                "automatic KNX event registration skipped"
            )
            return

        addresses = self._known_knx_group_addresses()
        if not addresses:
            _LOGGER.info(
                "No known KNX group addresses found for automatic knx_event "
                "registration"
            )
            return

        registered = 0
        chunk_size = 100
        for i in range(0, len(addresses), chunk_size):
            chunk = addresses[i : i + chunk_size]
            try:
                await self._hass.services.async_call(
                    "knx",
                    "event_register",
                    {"address": chunk},
                    blocking=True,
                )
            except (HomeAssistantError, ValueError) as err:
                _LOGGER.warning(
                    "Automatic KNX event registration failed for %d addresses: %s",
                    len(chunk),
                    err,
                )
                continue

            registered += len(chunk)

        if registered:
            _LOGGER.info(
                "Registered %d KNX group addresses for knx_event forwarding",
                registered,
            )

    def _decode_knx_value(self, destination_address: Any, value_obj: Any) -> Any:
        """Try to decode KNX telegram value using KNX configured DPT mappings."""
        if value_obj is None:
            return None

        knx_module = self._get_knx_module()
        if knx_module is None:
            return None

        group_address_transcoder = getattr(knx_module, "group_address_transcoder", None)
        if isinstance(group_address_transcoder, dict):
            transcoder = group_address_transcoder.get(destination_address)
            if transcoder is not None:
                try:
                    return transcoder.from_knx(value_obj)
                except (ValueError, TypeError):
                    return None

        address_filter_transcoder = getattr(
            knx_module, "_address_filter_transcoder", None
        )
        if isinstance(address_filter_transcoder, dict):
            for address_filter, transcoder in address_filter_transcoder.items():
                matcher = getattr(address_filter, "match", None)
                if callable(matcher) and matcher(destination_address):
                    try:
                        return transcoder.from_knx(value_obj)
                    except (ValueError, TypeError):
                        return None

        return None

    def _known_knx_group_addresses(self) -> list[str]:
        """Return known KNX group addresses from KNX module metadata."""
        knx_module = self._get_knx_module()
        if knx_module is None:
            return []

        group_address_entities = getattr(knx_module, "group_address_entities", None)
        if not isinstance(group_address_entities, dict):
            return []

        known_addresses = {
            str(group_address)
            for group_address in group_address_entities
            if self._is_knx_ga_export_allowed(str(group_address))
        }
        return sorted(known_addresses)

    def _get_knx_module(self) -> Any | None:
        """Return KNX module instance from hass.data when available."""
        hass_data = getattr(self._hass, "data", None)
        if not isinstance(hass_data, dict):
            return None
        return hass_data.get(KNX_MODULE_KEY)

    def _get_knx_status(self) -> tuple[bool, bool]:
        """Return KNX installed/running status without hard dependency."""
        installed = False
        running = False

        config_entries = getattr(self._hass, "config_entries", None)
        if config_entries is not None and hasattr(config_entries, "async_entries"):
            try:
                installed = bool(config_entries.async_entries("knx"))
            except (TypeError, ValueError):
                installed = False

        config = getattr(self._hass, "config", None)
        components = getattr(config, "components", None)
        if isinstance(components, set):
            running = "knx" in components
            installed = installed or running

        return installed, running


def _is_state_unchanged(old_state: State | None, new_state: State) -> bool:
    """Return True if state and attributes are unchanged."""
    if old_state is None:
        return False
    return (
        old_state.state == new_state.state
        and old_state.attributes == new_state.attributes
    )


def _safe_json_loads(raw_payload: str) -> dict[str, Any] | None:
    """Parse JSON payload and return object payload if valid."""
    try:
        parsed = json.loads(raw_payload)
    except (TypeError, ValueError):
        return None

    if not isinstance(parsed, dict):
        return None

    return parsed
