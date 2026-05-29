"""Standalone test fixtures for the Estada custom integration."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, cast

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant

from custom_components.estada.const import (
    CONF_CLIENT_ID,
    DATA_KNX_ENTITIES,
    DATA_STATUS_COORDINATOR,
)
from custom_components.estada.status import EstadaStatusCoordinator


@dataclass(slots=True)
class FakeConfigEntry:
    """Minimal config entry substitute for unit tests."""

    data: dict[str, Any]
    options: dict[str, Any]
    entry_id: str = "entry-1"
    _on_unload: list[Any] | None = None

    def async_on_unload(self, func: Any) -> Any:
        """Register unload callback and return function for compatibility."""
        if self._on_unload is None:
            self._on_unload = []
        self._on_unload.append(func)
        return func


@dataclass(slots=True)
class FakeState:
    """Minimal state object used by the bridge tests."""

    state: str
    attributes: dict[str, Any]
    last_changed: datetime


@dataclass(slots=True)
class FakeServiceCall:
    """Minimal service call object for registered handlers."""

    data: dict[str, Any]


class FakeBus:
    """Very small event bus implementation for tests."""

    def __init__(self, hass_obj: HomeAssistant | None) -> None:
        self._hass = hass_obj
        self._listeners: dict[str, list[Any]] = defaultdict(list)

    def async_listen(self, event_type: str, callback: Any):
        """Register listener and return unsubscribe callback."""
        self._listeners[event_type].append(callback)

        def _unsubscribe() -> None:
            listeners = self._listeners[event_type]
            if callback in listeners:
                listeners.remove(callback)

        return _unsubscribe

    async def async_fire(self, event_type: str, data: dict[str, Any]) -> None:
        """Fire event to listeners."""
        for callback in list(self._listeners[event_type]):
            result = callback(SimpleNamespace(data=data))
            if asyncio.iscoroutine(result):
                await result


class FakeServices:
    """Service registry/caller for tests."""

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], Any] = {}

    def async_register(self, domain: str, service: str, handler: Any) -> None:
        """Register a service handler."""
        self._handlers[(domain, service)] = handler

    def has_service(self, domain: str, service: str) -> bool:
        """Return whether a service exists."""
        return (domain, service) in self._handlers

    async def async_call(
        self,
        domain: str,
        service: str,
        data: dict[str, Any],
        blocking: bool = True,
    ) -> None:
        """Invoke a registered service handler."""
        del blocking
        if (domain, service) not in self._handlers:
            raise ValueError(f"Service {domain}.{service} not registered")
        call = FakeServiceCall(data)
        result = self._handlers[(domain, service)](call)
        if asyncio.iscoroutine(result):
            await result


class FakeStates:
    """State machine used by tests."""

    def __init__(self, hass_obj: HomeAssistant | None, bus: FakeBus) -> None:
        self._hass = hass_obj
        self._bus = bus
        self._states: dict[str, FakeState] = {}

    def async_set(
        self,
        entity_id: str,
        state: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Set state and emit state_changed event."""
        old_state = self._states.get(entity_id)
        new_state = FakeState(
            state=state,
            attributes=attributes or {},
            last_changed=datetime.now(UTC),
        )
        self._states[entity_id] = new_state
        self._hass.async_create_task(
            self._bus.async_fire(
                EVENT_STATE_CHANGED,
                {
                    "entity_id": entity_id,
                    "old_state": old_state,
                    "new_state": new_state,
                },
            )
        )

    def get(self, entity_id: str) -> FakeState | None:
        """Get state for an entity."""
        return self._states.get(entity_id)

    def async_remove(self, entity_id: str) -> None:
        """Remove state for an entity."""
        self._states.pop(entity_id, None)


class FakeConfig:
    """Fake Home Assistant config object for tests."""

    def __init__(self) -> None:
        """Initialize fake config."""
        self._temp_dir = TemporaryDirectory()
        self._config_dir = self._temp_dir.name

    def path(self, *parts: str) -> str:
        """Build a path from config directory."""
        return str(Path(self._config_dir).joinpath(*parts))

    def __del__(self) -> None:
        """Clean up temp directory."""
        try:
            self._temp_dir.cleanup()
        except Exception:
            pass


class FakeHass:
    """Minimal Home Assistant object for bridge tests."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()
        self.loop = asyncio.get_running_loop()
        self.bus = FakeBus(self)
        self.services = FakeServices()
        self.states = FakeStates(self, self.bus)
        self.config = FakeConfig()
        self.data: dict[str, Any] = {}

    def async_create_task(self, coro: Any) -> asyncio.Task:
        """Schedule async task."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def async_add_executor_job(self, func: Any, *args: Any) -> Any:
        """Run a function in the executor (thread pool)."""
        loop = asyncio.get_running_loop()
        if args:
            return await loop.run_in_executor(None, func, *args)
        return await loop.run_in_executor(None, func)

    async def async_block_till_done(self) -> None:
        """Wait until all scheduled tasks complete."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks))


class FakeMqttEnv:
    """MQTT environment used to patch bridge dependencies."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str, int, bool]] = []
        self._subscriptions: list[tuple[str, Any]] = []

    async def async_wait_for_mqtt_client(self, hass_obj: HomeAssistant | None) -> bool:
        """Pretend MQTT client is always available."""
        del hass_obj
        return True

    async def async_publish(
        self,
        hass_obj: HomeAssistant | None,
        topic: str,
        payload: str,
        qos: int,
        retain: bool,
    ) -> None:
        """Record published payload."""
        del hass_obj
        self.published.append((topic, payload, qos, retain))

    async def async_subscribe(
        self,
        hass_obj: HomeAssistant | None,
        topic: str,
        callback: Any,
        qos: int,
    ):
        """Store subscription callback."""
        del hass_obj, qos
        self._subscriptions.append((topic, callback))

        def _unsubscribe() -> None:
            if (topic, callback) in self._subscriptions:
                self._subscriptions.remove((topic, callback))

        return _unsubscribe

    async def async_fire_message(self, topic: str, payload: str) -> None:
        """Dispatch a fake MQTT message to matching subscriptions."""
        message = SimpleNamespace(topic=topic, payload=payload)

        for subscription_topic, callback in list(self._subscriptions):
            if _topic_matches(subscription_topic, topic):
                result = callback(message)
                if asyncio.iscoroutine(result):
                    await result


def _topic_matches(subscription_topic: str, topic: str) -> bool:
    """Match only exact topics and simple /# wildcard suffix."""
    if subscription_topic.endswith("/#"):
        return topic.startswith(subscription_topic[:-2])
    return topic == subscription_topic


@pytest.fixture(name="hass")
async def hass_fixture() -> HomeAssistant:
    """Return a minimal fake Home Assistant object."""
    return cast(HomeAssistant, FakeHass())


@pytest.fixture(name="estada_config_entry")
def estada_config_entry_fixture() -> FakeConfigEntry:
    """Return a default Estada config entry for tests."""
    return FakeConfigEntry(
        data={CONF_CLIENT_ID: "test-client"},
        options={},
    )


@pytest.fixture
def runtime_data(
    hass: HomeAssistant, estada_config_entry: FakeConfigEntry
) -> dict[str, object]:
    """Return runtime storage container for bridge tests."""
    return {
        DATA_KNX_ENTITIES: {},
        DATA_STATUS_COORDINATOR: EstadaStatusCoordinator(
            hass,
            cast(ConfigEntry, estada_config_entry),
        ),
    }


@pytest.fixture
def mqtt_env(monkeypatch: pytest.MonkeyPatch) -> FakeMqttEnv:
    """Patch MQTT functions used by Estada bridge and return environment."""
    env = FakeMqttEnv()

    monkeypatch.setattr(
        "custom_components.estada.mqtt_bridge.mqtt.async_wait_for_mqtt_client",
        env.async_wait_for_mqtt_client,
    )
    monkeypatch.setattr(
        "custom_components.estada.mqtt_bridge.mqtt.async_publish",
        env.async_publish,
    )
    monkeypatch.setattr(
        "custom_components.estada.mqtt_bridge.mqtt.async_subscribe",
        env.async_subscribe,
    )
    return env
