"""Data update coordinator for the CityBikes integration."""

from datetime import timedelta
import sys
from typing import override

import aiohttp
from citybikes import __version__ as CITYBIKES_CLIENT_VERSION
from citybikes.asyncio import Client as CitybikesClient
from citybikes.model import Station

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import APPLICATION_NAME, __version__
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_NETWORK, DOMAIN, LOGGER

HA_USER_AGENT = (
    f"{APPLICATION_NAME}/{__version__} "
    f"python-citybikes/{CITYBIKES_CLIENT_VERSION} "
    f"Python/{sys.version_info[0]}.{sys.version_info[1]}"
)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)

# Timely, and doesn't suffocate the API
SCAN_INTERVAL = timedelta(minutes=5)

type CityBikesConfigEntry = ConfigEntry[CityBikesDataUpdateCoordinator]


def create_client() -> CitybikesClient:
    """Create a CityBikes API client; the caller must close it."""
    return CitybikesClient(user_agent=HA_USER_AGENT, timeout=REQUEST_TIMEOUT)


class CityBikesDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Station]]):
    """Fetch all stations of one bike-share network, keyed by station ID."""

    config_entry: CityBikesConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: CityBikesConfigEntry,
        client: CitybikesClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.network_id: str = config_entry.data[CONF_NETWORK]

    @override
    async def _async_update_data(self) -> dict[str, Station]:
        """Fetch the latest station data for the network."""
        try:
            network = await self.client.network(uid=self.network_id).fetch()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"network": self.config_entry.title},
            ) from err
        return {station.id: station for station in network.stations}
