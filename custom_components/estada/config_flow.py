"""Config flow for Estada integration."""

import voluptuous as vol

from homeassistant import config_entries

from .const import CONF_CLIENT_ID, CONF_MQTT_CLIENT_ID, DOMAIN


@config_entries.HANDLERS.register(DOMAIN)
class EstadaConfigFlow(config_entries.ConfigFlow):
    """Handle an Estada config flow."""

    VERSION = 1

    @staticmethod
    def _client_id_schema(default_client_id: str = "") -> vol.Schema:
        """Return schema used for client id input forms."""
        return vol.Schema(
            {vol.Required(CONF_CLIENT_ID, default=default_client_id): str}
        )

    async def async_step_reconfigure(self, user_input: dict | None = None):
        """Handle reconfiguration of an existing Estada entry."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID].strip()

            if not client_id:
                errors[CONF_CLIENT_ID] = "client_id_required"
            else:
                if (
                    client_id != reconfigure_entry.unique_id
                    and await self.async_set_unique_id(client_id)
                ):
                    errors["base"] = "already_configured"

                if not errors:
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        title=f"Estada {client_id}",
                        unique_id=client_id,
                        data_updates={CONF_CLIENT_ID: client_id},
                    )

        current_client_id = str(
            reconfigure_entry.data.get(CONF_CLIENT_ID)
            or reconfigure_entry.data.get(CONF_MQTT_CLIENT_ID)
            or reconfigure_entry.unique_id
            or ""
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._client_id_schema(current_client_id),
            errors=errors,
        )

    async def async_step_user(self, user_input: dict | None = None):
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID].strip()

            if not client_id:
                errors[CONF_CLIENT_ID] = "client_id_required"
            else:
                await self.async_set_unique_id(client_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Estada {client_id}",
                    data={CONF_CLIENT_ID: client_id},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self._client_id_schema(),
            errors=errors,
        )


# Compatibility alias for environments that import a module-level ConfigFlow.
ConfigFlow = EstadaConfigFlow
