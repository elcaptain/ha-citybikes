"""Tests for the CityBikes sensor platform."""

from datetime import timedelta
from unittest.mock import MagicMock

from aiohttp import ClientError, ClientResponseError
from citybikes.model import Network
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_load_json_object_fixture,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.citybikes.const import (
    CONF_NETWORK,
    DOMAIN,
    SUBENTRY_TYPE_STATION,
)
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import SOURCE_IGNORE
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from . import setup_integration

STATION_1_BIKES = "sensor.station_1_available_bikes"
STATION_2_BIKES = "sensor.station_2_available_bikes"


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "mock_citybikes_client")
async def test_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the sensors of every station."""
    await setup_integration(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)
    # Station 2 reports no e-bike count, so it gets no e-bike sensor.
    assert hass.states.get("sensor.station_1_available_e_bikes")
    assert not hass.states.get("sensor.station_2_available_e_bikes")


async def test_unavailable_when_api_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_citybikes_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test sensors become unavailable while the API fails, and recover."""
    await setup_integration(hass, mock_config_entry)
    fetch = mock_citybikes_client.network.return_value.fetch
    network = fetch.return_value

    fetch.side_effect = ClientError
    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(STATION_1_BIKES).state == STATE_UNAVAILABLE

    fetch.side_effect = None
    fetch.return_value = network
    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(STATION_1_BIKES).state == "5"


async def test_unavailable_when_station_removed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_citybikes_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a station that leaves the network becomes unavailable."""
    await setup_integration(hass, mock_config_entry)
    network = (await async_load_json_object_fixture(hass, "network.json"))[
        "network"
    ]
    network["stations"] = network["stations"][:1]
    mock_citybikes_client.network.return_value.fetch.return_value = Network.from_dict(
        network
    )

    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(STATION_1_BIKES).state == "5"
    assert hass.states.get(STATION_2_BIKES).state == STATE_UNAVAILABLE


async def _setup_yaml(hass: HomeAssistant, *platforms: dict[str, object]) -> None:
    """Set up the legacy YAML sensor platform."""
    assert await async_setup_component(
        hass,
        SENSOR_DOMAIN,
        {SENSOR_DOMAIN: [{"platform": DOMAIN, **conf} for conf in platforms]},
    )
    await hass.async_block_till_done()


def _station_ids(hass: HomeAssistant) -> list[str | None]:
    """Return the station subentries of the only CityBikes entry."""
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    return sorted(
        sub.unique_id for sub in entry.get_subentries_of_type(SUBENTRY_TYPE_STATION)
    )


@pytest.mark.usefixtures("mock_citybikes_client")
async def test_yaml_import_stations(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """Test YAML stations, by ID or by uid, are imported as subentries."""
    await _setup_yaml(
        hass, {"network": "mock-network", "stations": ["station-1", "uid-2"]}
    )

    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert entry.title == "Mock Network"
    assert entry.data == {CONF_NETWORK: "mock-network"}
    assert _station_ids(hass) == ["station-1", "station-2"]
    assert hass.states.get(STATION_1_BIKES).state == "5"
    assert issue_registry.async_get_issue(
        HOMEASSISTANT_DOMAIN, f"deprecated_yaml_{DOMAIN}"
    )


@pytest.mark.usefixtures("mock_citybikes_client")
@pytest.mark.parametrize(
    ("units", "expected"),
    [
        pytest.param(METRIC_SYSTEM, ["station-1", "station-2"], id="meters"),
        # 2000 ft is about 610 m, and station 2 is about 1.1 km away.
        pytest.param(US_CUSTOMARY_SYSTEM, ["station-1"], id="feet"),
    ],
)
async def test_yaml_import_radius(
    hass: HomeAssistant, units: object, expected: list[str]
) -> None:
    """Test YAML radius picks the closest network and nearby stations."""
    hass.config.units = units
    await _setup_yaml(
        hass, {"latitude": 32.87336, "longitude": -117.22743, "radius": 2000}
    )

    assert _station_ids(hass) == expected


@pytest.mark.usefixtures("mock_citybikes_client")
async def test_yaml_import_merges_blocks(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """Test two YAML blocks for one network end up in one entry."""
    await _setup_yaml(
        hass,
        {"network": "mock-network", "stations": ["station-1"]},
        {"network": "mock-network", "stations": ["station-2"]},
    )

    assert _station_ids(hass) == ["station-1", "station-2"]
    assert issue_registry.async_get_issue(
        HOMEASSISTANT_DOMAIN, f"deprecated_yaml_{DOMAIN}"
    )


@pytest.mark.usefixtures("mock_citybikes_client")
async def test_yaml_import_ignored_entry(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """Test an ignored network gets no stations from YAML."""
    ignored = MockConfigEntry(
        domain=DOMAIN, source=SOURCE_IGNORE, unique_id="mock-network", data={}
    )
    ignored.add_to_hass(hass)

    await _setup_yaml(hass, {"network": "mock-network", "stations": ["station-1"]})

    assert not ignored.subentries
    assert issue_registry.async_get_issue(
        HOMEASSISTANT_DOMAIN, f"deprecated_yaml_{DOMAIN}"
    )


@pytest.mark.parametrize(
    ("side_effect", "reason"),
    [
        pytest.param(ClientError, "cannot_connect", id="cannot_connect"),
        pytest.param(TimeoutError, "cannot_connect", id="timeout"),
        pytest.param(
            ClientResponseError(MagicMock(), (), status=500),
            "cannot_connect",
            id="server_error",
        ),
        pytest.param(
            ClientResponseError(MagicMock(), (), status=404),
            "unknown_network",
            id="unknown_network",
        ),
    ],
)
async def test_yaml_import_failure(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    mock_citybikes_client: MagicMock,
    side_effect: Exception | type[Exception],
    reason: str,
) -> None:
    """Test a failed YAML import raises a repair issue explaining why."""
    mock_citybikes_client.network.return_value.fetch.side_effect = side_effect

    await _setup_yaml(hass, {"network": "mock-network", "stations": ["station-1"]})

    assert not hass.config_entries.async_entries(DOMAIN)
    assert issue_registry.async_get_issue(
        DOMAIN, f"deprecated_yaml_import_issue_{reason}"
    )
    assert not issue_registry.async_get_issue(
        HOMEASSISTANT_DOMAIN, f"deprecated_yaml_{DOMAIN}"
    )
