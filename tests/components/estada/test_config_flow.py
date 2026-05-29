"""Tests for Estada config flow."""

from unittest.mock import AsyncMock
from unittest.mock import Mock

import pytest

from homeassistant.data_entry_flow import AbortFlow
from homeassistant.data_entry_flow import FlowResultType

from custom_components.estada.config_flow import EstadaConfigFlow
from custom_components.estada.const import CONF_CLIENT_ID


async def test_async_step_user_creates_entry() -> None:
    """Test creating an entry from user step."""
    flow = EstadaConfigFlow()
    flow.context = {"source": "user"}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()

    result = await flow.async_step_user({CONF_CLIENT_ID: "  test-client  "})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Estada test-client"
    assert result["data"] == {CONF_CLIENT_ID: "test-client"}


async def test_async_step_user_empty_client_id_returns_error() -> None:
    """Test empty client_id returns form error."""
    flow = EstadaConfigFlow()
    flow.context = {"source": "user"}

    result = await flow.async_step_user({CONF_CLIENT_ID: "  "})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_CLIENT_ID: "client_id_required"}


async def test_async_step_user_aborts_when_already_configured() -> None:
    """Test duplicate client_id aborts the flow."""
    flow = EstadaConfigFlow()
    flow.context = {"source": "user"}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock(
        side_effect=AbortFlow("already_configured")
    )

    with pytest.raises(AbortFlow, match="already_configured"):
        await flow.async_step_user({CONF_CLIENT_ID: "test-client"})
