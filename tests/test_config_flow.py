"""Tests for the CityBikes config flow."""

from unittest.mock import AsyncMock, MagicMock

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.citybikes.const import (
    CONF_NETWORK,
    CONF_STATION_ID,
    CONF_STATIONS,
    DOMAIN,
    SUBENTRY_TYPE_STATION,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from . import setup_integration


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow(hass: HomeAssistant, mock_citybikes_client: MagicMock) -> None:
    """Test picking a network and stations creates an entry with subentries."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # The network closest to home is listed first and suggested.
    schema = result["data_schema"].schema
    key = next(iter(schema))
    assert key.description == {"suggested_value": "mock-network"}
    assert [o["value"] for o in schema[key].config["options"]] == [
        "mock-network",
        "far-network",
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NETWORK: "mock-network"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "stations"
    mock_citybikes_client.network.assert_called_with(uid="mock-network")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_STATIONS: ["station-2"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Mock Network"
    assert result["data"] == {CONF_NETWORK: "mock-network"}
    assert result["result"].unique_id == "mock-network"
    assert [
        (sub.title, sub.unique_id, dict(sub.data))
        for sub in result["result"].subentries.values()
    ] == [("Station 2", "station-2", {CONF_STATION_ID: "station-2"})]
    # Every client the flow opened is closed again.
    assert mock_citybikes_client.close.await_count == 2


@pytest.mark.usefixtures("mock_setup_entry", "mock_citybikes_client")
async def test_user_flow_without_stations(hass: HomeAssistant) -> None:
    """Test the stations step can be skipped."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NETWORK: "mock-network"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "mock-network"
    assert not result["result"].subentries


@pytest.mark.parametrize(
    ("side_effect", "reason"),
    [
        pytest.param(ClientError, "cannot_connect", id="cannot_connect"),
        pytest.param(TimeoutError, "cannot_connect", id="timeout"),
        pytest.param(ValueError, "unknown", id="unknown"),
    ],
)
async def test_user_flow_networks_error(
    hass: HomeAssistant,
    mock_citybikes_client: MagicMock,
    side_effect: type[Exception],
    reason: str,
) -> None:
    """Test the flow aborts when the networks cannot be listed."""
    mock_citybikes_client.networks.fetch.side_effect = side_effect

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


@pytest.mark.usefixtures("mock_setup_entry")
@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        pytest.param(ClientError, "cannot_connect", id="cannot_connect"),
        pytest.param(ValueError, "unknown", id="unknown"),
    ],
)
async def test_user_flow_network_error_recovers(
    hass: HomeAssistant,
    mock_citybikes_client: MagicMock,
    side_effect: type[Exception],
    error: str,
) -> None:
    """Test an error fetching the picked network is shown and can be retried."""
    fetch: AsyncMock = mock_citybikes_client.network.return_value.fetch
    network = fetch.return_value
    fetch.side_effect = side_effect

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NETWORK: "mock-network"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}

    fetch.side_effect = None
    fetch.return_value = network
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NETWORK: "mock-network"}
    )
    assert result["step_id"] == "stations"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_citybikes_client")
async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test a network can only be added once."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NETWORK: "mock-network"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("mock_citybikes_client")
async def test_station_subentry_flow(hass: HomeAssistant) -> None:
    """Test adding a station that is not configured yet."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Mock Network",
        data={CONF_NETWORK: "mock-network"},
        unique_id="mock-network",
    )
    await setup_integration(hass, entry)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_STATION), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    key = next(iter(result["data_schema"].schema))
    # Closest to home first.
    assert [
        o["value"] for o in result["data_schema"].schema[key].config["options"]
    ] == ["station-1", "station-2"]

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_STATION_ID: "station-2"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Station 2"
    assert result["data"] == {CONF_STATION_ID: "station-2"}
    assert result["unique_id"] == "station-2"
    await hass.async_block_till_done()
    # The entry reloads, so the new station gets its entities.
    assert hass.states.get("sensor.station_2_available_bikes")


@pytest.mark.usefixtures("mock_citybikes_client")
async def test_station_subentry_flow_all_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the subentry flow aborts when every station is already added."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_STATION),
        context={"source": SOURCE_USER},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_stations"


async def test_station_subentry_flow_entry_not_loaded(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_citybikes_client: MagicMock,
) -> None:
    """Test the subentry flow aborts while the network is not loaded."""
    mock_citybikes_client.network.return_value.fetch.side_effect = ClientError
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_STATION),
        context={"source": SOURCE_USER},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"
