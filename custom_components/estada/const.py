DOMAIN = "estada"

CONF_CLIENT_ID = "client_id"
# Backward-compatible key for older config entries.
CONF_MQTT_CLIENT_ID = "mqtt_client_id"

DATA_ALIVE_TASK = "alive_task"
DATA_BRIDGE = "bridge"
DATA_KNX_ENTITIES = "knx_entities"
DATA_STATUS_COORDINATOR = "status_coordinator"
DATA_STARTUP_TASK = "startup_task"

BRIDGE_START_DELAY_SECONDS = 20
BRIDGE_SETUP_RETRY_SECONDS = 60

OPTION_ENTITY_ALLOWLIST = "entity_allowlist"
OPTION_DOMAIN_ALLOWLIST = "domain_allowlist"
OPTION_ENTITY_EXCLUDE_PATTERNS = "entity_exclude_patterns"
OPTION_KNX_GA_INCLUDE_PATTERNS = "knx_ga_include_patterns"
OPTION_KNX_GA_EXCLUDE_PATTERNS = "knx_ga_exclude_patterns"

EVENT_KNX_EVENT = "knx_event"

DEFAULT_ENTITY_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "sensor.estada_*",
    "binary_sensor.estada_*",
)

DEFAULT_KNX_GA_INCLUDE_PATTERNS: tuple[str, ...] = ("*",)
DEFAULT_KNX_GA_EXCLUDE_PATTERNS: tuple[str, ...] = ()

SOURCE_TAG_HA = "HA"

DEFAULT_QOS = 0
DEFAULT_RETAIN = False


def topic_base(client_id: str) -> str:
    """Return integration base topic for a client id."""
    return f"estada/{client_id}"


def topic_entities(client_id: str, entity_id: str) -> str:
    """Return entities topic for a specific entity."""
    return f"{topic_base(client_id)}/entities/{entity_id}"


def topic_commands(client_id: str) -> str:
    """Return command wildcard topic."""
    return f"{topic_base(client_id)}/commands/#"


def topic_commands_list(client_id: str) -> str:
    """Return command list topic."""
    return f"{topic_base(client_id)}/commands/list-of-commands"


def topic_command_response(client_id: str, command_name: str) -> str:
    """Return command response topic."""
    return f"{topic_base(client_id)}/commands/response/{command_name}"


def topic_errors(client_id: str) -> str:
    """Return errors topic."""
    return f"{topic_base(client_id)}/errors"


def topic_telegram(client_id: str, group_address: str) -> str:
    """Return topic for KNX raw telegram payloads."""
    return f"{topic_base(client_id)}/telegrams/{group_address}"


def topic_alive(client_id: str) -> str:
    """Return alive/heartbeat topic."""
    return f"{topic_base(client_id)}/alive"
