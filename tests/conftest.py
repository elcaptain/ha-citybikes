"""Fixtures for the CityBikes integration tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from citybikes.model import Network
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, load_json_object_fixture

from custom_components.citybikes.const import (
    CONF_NETWORK,
    CONF_STATION_ID,
    DOMAIN,
    SUBENTRY_TYPE_STATION,
)
from homeassistant.config_entries import ConfigSubentryData


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Mock setting up a config entry."""
    with patch(
        "custom_components.citybikes.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture
def mock_citybikes_client() -> Generator[MagicMock]:
    """Mock the CityBikes API client."""
    networks = [
        Network.from_dict(network)
        for network in load_json_object_fixture("networks.json")["networks"]
    ]
    network = Network.from_dict(
        load_json_object_fixture("network.json")["network"]
    )
    with patch(
        "custom_components.citybikes.coordinator.CitybikesClient"
    ) as mock_client_class:
        client = mock_client_class.return_value
        client.close = AsyncMock()
        client.networks.fetch = AsyncMock(return_value=networks)
        client.network.return_value.fetch = AsyncMock(return_value=network)
        yield client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a CityBikes config entry watching two stations."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Mock Network",
        data={CONF_NETWORK: "mock-network"},
        unique_id="mock-network",
        entry_id="01JR3TZKNXVJ4S6ZKPD7A9BQ2E",
        subentries_data=[
            ConfigSubentryData(
                data={CONF_STATION_ID: station_id},
                subentry_type=SUBENTRY_TYPE_STATION,
                title=title,
                unique_id=station_id,
            )
            for station_id, title in (
                ("station-1", "Station 1"),
                ("station-2", "Station 2"),
            )
        ],
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in every test."""


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Enable entities that are disabled by default."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield
