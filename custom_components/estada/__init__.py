import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    BRIDGE_SETUP_RETRY_SECONDS,
    BRIDGE_START_DELAY_SECONDS,
    DATA_ALIVE_TASK,
    DATA_BRIDGE,
    DATA_KNX_ENTITIES,
    DATA_STARTUP_TASK,
    DATA_STATUS_COORDINATOR,
    DOMAIN,
)
from .mqtt_bridge import EstadaMqttBridge
from .status import EstadaStatusCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Estada from a config entry."""

    _LOGGER.warning(
        "ESTADA INIT [1/5] async_setup_entry gestartet (entry_id=%s)", entry.entry_id
    )
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.warning("ESTADA INIT [2/5] hass.data initialisiert")

    status_coordinator = EstadaStatusCoordinator(hass, entry)
    _LOGGER.warning("ESTADA INIT [3/5] StatusCoordinator erstellt")

    runtime_data: dict[str, object] = {
        DATA_KNX_ENTITIES: {},
        DATA_STATUS_COORDINATOR: status_coordinator,
    }
    # Ensure MQTT Bridge is initialized even if KNX is unavailable
    try:
        bridge = EstadaMqttBridge(hass, entry, runtime_data)
        runtime_data[DATA_BRIDGE] = bridge
        _LOGGER.warning(
            "ESTADA INIT [4/5] Bridge-Objekt erstellt und in runtime_data gespeichert"
        )
    except Exception as e:
        _LOGGER.error(
            "ESTADA INIT [FEHLER] Bridge konnte nicht initialisiert werden: %s", e
        )
        runtime_data[DATA_BRIDGE] = None

    hass.data[DOMAIN][entry.entry_id] = runtime_data

    if runtime_data.get(DATA_BRIDGE) is not None:
        startup_task = entry.async_create_background_task(
            hass,
            _async_setup_bridge_with_retry(hass, entry),
            f"{DOMAIN}_bridge_setup_{entry.entry_id}",
        )
        runtime_data[DATA_STARTUP_TASK] = startup_task
        _LOGGER.warning("ESTADA INIT [4b/5] Bridge-Setup-Task gestartet")

    _LOGGER.warning("ESTADA INIT [5/5] Platforms werden geladen: %s", PLATFORMS)
    for platform in PLATFORMS:
        _LOGGER.warning(
            "ESTADA INIT [5/%s] Lade Platform: %s", len(PLATFORMS), platform
        )
        await hass.config_entries.async_forward_entry_setups(entry, [platform])
        _LOGGER.warning(
            "ESTADA INIT [5/%s] Platform geladen: %s", len(PLATFORMS), platform
        )

    _LOGGER.warning("ESTADA INIT [OK] async_setup_entry abgeschlossen")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Estada config entry."""
    _LOGGER.warning(
        "ESTADA UNLOAD [1/4] async_unload_entry gestartet (entry_id=%s)", entry.entry_id
    )
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    _LOGGER.warning("ESTADA UNLOAD [2/4] Platforms entladen (ok=%s)", unload_ok)

    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_data and (startup_task := entry_data.get(DATA_STARTUP_TASK)) is not None:
        _LOGGER.warning("ESTADA UNLOAD [3/4] Startup-Task wird abgebrochen")
        assert isinstance(startup_task, asyncio.Task)
        startup_task.cancel()
        await asyncio.gather(startup_task, return_exceptions=True)
        _LOGGER.warning("ESTADA UNLOAD [3/4] Startup-Task abgebrochen")

    if entry_data and (alive_task := entry_data.get(DATA_ALIVE_TASK)) is not None:
        assert isinstance(alive_task, asyncio.Task)
        alive_task.cancel()
        await asyncio.gather(alive_task, return_exceptions=True)
        _LOGGER.warning("ESTADA UNLOAD [3b/4] Alive-Task abgebrochen")

    if entry_data and (bridge := entry_data.get(DATA_BRIDGE)) is not None:
        _LOGGER.warning("ESTADA UNLOAD [4/4] Bridge wird entladen")
        await bridge.async_unload()
        _LOGGER.warning("ESTADA UNLOAD [4/4] Bridge entladen")

    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    _LOGGER.warning(
        "ESTADA UNLOAD [OK] async_unload_entry abgeschlossen (ok=%s)", unload_ok
    )
    return unload_ok


async def _async_setup_bridge_with_retry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Set up bridge with delayed, retrying background initialization."""
    _LOGGER.warning(
        "ESTADA BRIDGE [1] Setup-Task gestartet, warte %s Sekunden...",
        BRIDGE_START_DELAY_SECONDS,
    )
    await asyncio.sleep(BRIDGE_START_DELAY_SECONDS)
    _LOGGER.warning("ESTADA BRIDGE [2] Wartezeit abgelaufen, starte Bridge-Setup")

    attempt = 0
    while True:
        attempt += 1
        _LOGGER.warning("ESTADA BRIDGE [3] Setup-Versuch #%d", attempt)
        entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if not entry_data:
            _LOGGER.warning(
                "ESTADA BRIDGE [ABBRUCH] entry_data nicht mehr vorhanden – Task beendet"
            )
            return

        bridge = entry_data.get(DATA_BRIDGE)
        assert isinstance(bridge, EstadaMqttBridge)

        _LOGGER.warning(
            "ESTADA BRIDGE [4] Rufe bridge.async_setup() auf (Versuch #%d)", attempt
        )
        try:
            ok = await asyncio.wait_for(
                bridge.async_setup(),
                timeout=30,
            )
        except asyncio.CancelledError:
            _LOGGER.warning("ESTADA BRIDGE [ABBRUCH] Task wurde abgebrochen")
            raise
        except Exception:
            _LOGGER.exception(
                "ESTADA BRIDGE [FEHLER] bridge.async_setup() fehlgeschlagen (Versuch #%d)",
                attempt,
            )
            ok = False

        if ok:
            entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if entry_data is not None:
                bridge = entry_data.get(DATA_BRIDGE)
                assert isinstance(bridge, EstadaMqttBridge)
                alive_task = entry.async_create_background_task(
                    hass,
                    _send_alive_message(hass, bridge),
                    f"{DOMAIN}_alive_{entry.entry_id}",
                )
                entry_data[DATA_ALIVE_TASK] = alive_task
                _LOGGER.warning("ESTADA BRIDGE [OK] Alive-Task gestartet")

            _LOGGER.warning(
                "ESTADA BRIDGE [OK] Bridge-Setup erfolgreich abgeschlossen (Versuch #%d)",
                attempt,
            )

            return

        _LOGGER.warning(
            "ESTADA BRIDGE [RETRY] Setup fehlgeschlagen – erneuter Versuch in %s Sekunden",
            BRIDGE_SETUP_RETRY_SECONDS,
        )
        await asyncio.sleep(BRIDGE_SETUP_RETRY_SECONDS)


async def _send_alive_message(hass: HomeAssistant, bridge: EstadaMqttBridge) -> None:
    """Send an alive message to MQTT every 30 seconds."""

    while True:
        try:
            _LOGGER.warning("ESTADA ALIVE: Sende Alive-Message an MQTT")
            await bridge.async_send_alive_message()
        except Exception as e:
            _LOGGER.error("ESTADA ALIVE: Fehler beim Senden der Alive-Message: %s", e)
        await asyncio.sleep(30)
