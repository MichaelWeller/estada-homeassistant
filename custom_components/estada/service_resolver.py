"""Service resolution helpers for inbound Estada entity state messages."""

from collections.abc import Mapping
from dataclasses import dataclass

from voluptuous.error import MultipleInvalid

from homeassistant.core import HomeAssistant


@dataclass(slots=True, frozen=True)
class ServiceCallDefinition:
    """Resolved Home Assistant service call."""

    domain: str
    service: str
    data: dict[str, object]


_DOMAIN_STATE_SERVICE_MAP: dict[str, dict[str, str]] = {
    "light": {"on": "turn_on", "off": "turn_off"},
    "switch": {"on": "turn_on", "off": "turn_off"},
    "fan": {"on": "turn_on", "off": "turn_off"},
    "input_boolean": {"on": "turn_on", "off": "turn_off"},
    "lock": {"locked": "lock", "unlocked": "unlock"},
    "media_player": {"on": "turn_on", "off": "turn_off"},
}

_COVER_MAP: dict[str, str] = {
    "open": "open_cover",
    "opening": "open_cover",
    "closed": "close_cover",
    "closing": "close_cover",
    "stop": "stop_cover",
}


def resolve_service_call(
    hass: HomeAssistant,
    entity_id: str,
    state_value: str,
    explicit_service: str | None,
    params: Mapping[str, object] | None,
) -> tuple[ServiceCallDefinition, dict[str, object]] | None:
    """Resolve service + data for an incoming entity state update.

    Returns None if no valid service mapping can be built.
    """
    if "." not in entity_id:
        return None

    domain, _ = entity_id.split(".", 1)

    service_name = _resolve_service_name(domain, state_value, explicit_service)
    if service_name is None:
        return None

    if not hass.services.has_service(domain, service_name):
        return None

    merged_params: dict[str, object] = {}
    if params:
        merged_params.update(params)

    if domain in {"select", "input_select"} and service_name == "select_option":
        merged_params["option"] = state_value

    if domain in {"number", "input_number"} and service_name == "set_value":
        try:
            merged_params["value"] = float(state_value)
        except (TypeError, ValueError):
            return None

    service_data: dict[str, object] = {"entity_id": entity_id, **merged_params}
    service_data = _sanitize_service_data(hass, domain, service_name, service_data)

    sanitized_params = {
        key: value for key, value in service_data.items() if key != "entity_id"
    }
    return (
        ServiceCallDefinition(domain=domain, service=service_name, data=service_data),
        sanitized_params,
    )


def _sanitize_service_data(
    hass: HomeAssistant,
    domain: str,
    service_name: str,
    service_data: dict[str, object],
) -> dict[str, object]:
    """Best-effort sanitize service payload against the registered schema."""
    service_obj = hass.services.async_services_for_domain(domain).get(service_name)
    if service_obj is None or service_obj.schema is None:
        return service_data

    sanitized = dict(service_data)
    while True:
        try:
            validated = service_obj.schema(sanitized)
        except MultipleInvalid as err:
            removable_keys = {
                error.path[0]
                for error in err.errors
                if error.path and isinstance(error.path[0], str)
            }
            removable_keys.discard("entity_id")

            if not removable_keys:
                return sanitized

            for key in removable_keys:
                sanitized.pop(key, None)
            continue

        if isinstance(validated, Mapping):
            return dict(validated)
        return sanitized


def _resolve_service_name(
    domain: str,
    state_value: str,
    explicit_service: str | None,
) -> str | None:
    """Resolve a service name from explicit payload or fallback mappings."""
    if explicit_service:
        return explicit_service

    lowered_state = state_value.lower()

    if domain in _DOMAIN_STATE_SERVICE_MAP:
        return _DOMAIN_STATE_SERVICE_MAP[domain].get(lowered_state)

    if domain == "cover":
        return _COVER_MAP.get(lowered_state)

    if domain in {"select", "input_select"}:
        return "select_option"

    if domain in {"number", "input_number"}:
        return "set_value"

    return None
