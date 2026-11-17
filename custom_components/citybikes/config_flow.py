"""Config flow for the CityBikes integration."""

from collections.abc import Iterable
import logging
import math
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, override

from aiohttp import ClientError, ClientResponseError
from citybikes.model import Network, Station
import probatio

from homeassistant.config_entries import (
    SOURCE_IGNORE,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryData,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_RADIUS, UnitOfLength
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import location as location_util
from homeassistant.util.unit_conversion import DistanceConverter
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from .const import (
    CONF_NETWORK,
    CONF_STATION_ID,
    CONF_STATIONS,
    DOMAIN,
    SUBENTRY_TYPE_STATION,
)
from .coordinator import CityBikesConfigEntry, create_client

_LOGGER = logging.getLogger(__name__)

ATTR_UID = "uid"


async def _async_fetch_networks() -> list[Network]:
    """Fetch all networks known to CityBikes, without their stations."""
    client = create_client()
    try:
        return await client.networks.fetch()
    finally:
        await client.close()


async def _async_fetch_network(network_id: str) -> Network:
    """Fetch one network including its stations."""
    client = create_client()
    try:
        return await client.network(uid=network_id).fetch()
    finally:
        await client.close()


def _distance(
    latitude: float, longitude: float, other_lat: float, other_lon: float
) -> float:
    """Return the distance in meters, or infinity when it cannot be computed."""
    dist = location_util.distance(latitude, longitude, other_lat, other_lon)
    return math.inf if dist is None else dist


def _station_subentry(station: Station) -> ConfigSubentryData:
    """Return the subentry data for a station."""
    return ConfigSubentryData(
        data={CONF_STATION_ID: station.id},
        subentry_type=SUBENTRY_TYPE_STATION,
        title=station.name,
        unique_id=station.id,
    )


def _station_selector(stations: Iterable[Station], *, multiple: bool) -> SelectSelector:
    """Return a selector listing the given stations in their current order."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=station.id, label=station.name)
                for station in stations
            ],
            mode=SelectSelectorMode.DROPDOWN,
            multiple=multiple,
            sort=False,
        )
    )


class CityBikesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CityBikes."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._networks: list[Network] = []
        self._network: Network | None = None

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: CityBikesConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentry types supported by this integration."""
        return {SUBENTRY_TYPE_STATION: StationSubentryFlowHandler}

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the bike-share network."""
        errors: dict[str, str] = {}

        if not self._networks:
            try:
                self._networks = await _async_fetch_networks()
            except ClientError, TimeoutError:
                return self.async_abort(reason="cannot_connect")
            except Exception:
                _LOGGER.exception("Unexpected error fetching CityBikes networks")
                return self.async_abort(reason="unknown")

        if user_input is not None:
            network_id = user_input[CONF_NETWORK]
            await self.async_set_unique_id(network_id)
            self._abort_if_unique_id_configured()
            try:
                self._network = await _async_fetch_network(network_id)
            except ClientError, TimeoutError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error fetching CityBikes network")
                errors["base"] = "unknown"
            else:
                return await self.async_step_stations()

        home = (self.hass.config.latitude, self.hass.config.longitude)
        networks = sorted(
            self._networks,
            key=lambda n: _distance(*home, n.location.latitude, n.location.longitude),
        )
        schema = probatio.Schema(
            {
                probatio.Required(CONF_NETWORK): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=network.id,
                                label=(
                                    f"{network.name} ({network.location.city}, "
                                    f"{network.location.country})"
                                ),
                            )
                            for network in networks
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                        sort=False,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or {CONF_NETWORK: networks[0].id}
            ),
            errors=errors,
        )

    async def async_step_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optionally pick the first stations to monitor."""
        network = self._network
        if TYPE_CHECKING:
            assert network is not None

        stations = {station.id: station for station in network.stations}
        if user_input is not None:
            return self.async_create_entry(
                title=network.name,
                data={CONF_NETWORK: network.id},
                subentries=[
                    _station_subentry(stations[station_id])
                    for station_id in user_input.get(CONF_STATIONS, [])
                ],
            )

        home = (self.hass.config.latitude, self.hass.config.longitude)
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_STATIONS): _station_selector(
                    sorted(
                        stations.values(),
                        key=lambda s: _distance(*home, s.latitude, s.longitude),
                    ),
                    multiple=True,
                )
            }
        )
        return self.async_show_form(
            step_id="stations",
            data_schema=schema,
            description_placeholders={"network": network.name},
        )

    async def async_step_import(self, import_data: ConfigType) -> ConfigFlowResult:
        """Import a YAML sensor platform configuration."""
        latitude = import_data.get(CONF_LATITUDE, self.hass.config.latitude)
        longitude = import_data.get(CONF_LONGITUDE, self.hass.config.longitude)

        try:
            if (network_id := import_data.get(CONF_NETWORK)) is None:
                networks = await _async_fetch_networks()
                network_id = min(
                    networks,
                    key=lambda n: _distance(
                        latitude, longitude, n.location.latitude, n.location.longitude
                    ),
                ).id
            network = await _async_fetch_network(network_id)
        except ClientResponseError as err:
            if err.status == 404:
                return self.async_abort(reason="unknown_network")
            return self.async_abort(reason="cannot_connect")
        except ClientError, TimeoutError:
            return self.async_abort(reason="cannot_connect")

        radius = import_data.get(CONF_RADIUS, 0)
        if self.hass.config.units is US_CUSTOMARY_SYSTEM:
            radius = DistanceConverter.convert(
                radius, UnitOfLength.FEET, UnitOfLength.METERS
            )
        wanted = set(import_data.get(CONF_STATIONS, []))
        stations = [
            station
            for station in network.stations
            if _distance(latitude, longitude, station.latitude, station.longitude)
            < radius
            or wanted.intersection((station.id, str(station.extra.get(ATTR_UID, ""))))
        ]

        if existing := self.hass.config_entries.async_entry_for_domain_unique_id(
            DOMAIN, network.id
        ):
            # Several YAML blocks may watch the same network; merge their stations.
            if existing.source != SOURCE_IGNORE:
                configured = {sub.unique_id for sub in existing.subentries.values()}
                for station in stations:
                    if station.id not in configured:
                        self.hass.config_entries.async_add_subentry(
                            existing,
                            ConfigSubentry(
                                data=MappingProxyType({CONF_STATION_ID: station.id}),
                                subentry_type=SUBENTRY_TYPE_STATION,
                                title=station.name,
                                unique_id=station.id,
                            ),
                        )
            return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(network.id)
        return self.async_create_entry(
            title=network.name,
            data={CONF_NETWORK: network.id},
            subentries=[_station_subentry(station) for station in stations],
        )


class StationSubentryFlowHandler(ConfigSubentryFlow):
    """Handle adding a station to a network."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Pick a station of the network."""
        entry: CityBikesConfigEntry = self._get_entry()
        if entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        configured = {sub.unique_id for sub in entry.subentries.values()}
        stations = {
            station_id: station
            for station_id, station in entry.runtime_data.data.items()
            if station_id not in configured
        }

        if user_input is not None:
            station = stations[user_input[CONF_STATION_ID]]
            return self.async_create_entry(
                title=station.name,
                data={CONF_STATION_ID: station.id},
                unique_id=station.id,
            )

        if not stations:
            return self.async_abort(reason="no_stations")

        home = (self.hass.config.latitude, self.hass.config.longitude)
        schema = probatio.Schema(
            {
                probatio.Required(CONF_STATION_ID): _station_selector(
                    sorted(
                        stations.values(),
                        key=lambda s: _distance(*home, s.latitude, s.longitude),
                    ),
                    multiple=False,
                )
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={"network": entry.title},
        )
