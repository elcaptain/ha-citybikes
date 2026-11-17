"""Tests for the CityBikes integration setup."""

from unittest.mock import MagicMock

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from . import setup_integration


async def test_load_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_citybikes_client: MagicMock,
) -> None:
    """Test loading and unloading closes the API client."""
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_citybikes_client.network.assert_called_with(uid="mock-network")

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    mock_citybikes_client.close.assert_awaited_once()


@pytest.mark.parametrize("side_effect", [ClientError, TimeoutError])
async def test_setup_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_citybikes_client: MagicMock,
    side_effect: type[Exception],
) -> None:
    """Test setup is retried, and the client closed, when the API is unreachable."""
    mock_citybikes_client.network.return_value.fetch.side_effect = side_effect

    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_citybikes_client.close.assert_awaited_once()
