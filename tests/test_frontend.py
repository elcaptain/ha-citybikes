"""Tests for the bundled CityBikes dashboard card."""

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

import pytest

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant

from . import setup_integration


@pytest.mark.usefixtures("mock_citybikes_client")
async def test_card_registered_and_served(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the card loads on every dashboard and its file is served."""
    await setup_integration(hass, mock_config_entry)

    assert "/citybikes/citybikes-card.js?v=1.1.0" in hass.data[DATA_EXTRA_MODULE_URL].urls

    client = await hass_client()
    response = await client.get("/citybikes/citybikes-card.js")
    assert response.status == 200
    assert 'customElements.define("citybikes-card"' in await response.text()
