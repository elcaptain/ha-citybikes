"""The CityBikes integration."""

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .coordinator import (
    CityBikesConfigEntry,
    CityBikesDataUpdateCoordinator,
    create_client,
)

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_FILENAME = "citybikes-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the CityBikes dashboard card and load it on every dashboard."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                CARD_URL, str(Path(__file__).parent / "frontend" / CARD_FILENAME), True
            )
        ]
    )
    # The version busts browser caches after an update.
    integration = await async_get_integration(hass, DOMAIN)
    add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CityBikesConfigEntry) -> bool:
    """Set up CityBikes from a config entry."""
    client = create_client()
    entry.async_on_unload(client.close)

    coordinator = CityBikesDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: CityBikesConfigEntry
) -> None:
    """Reload the entry when stations are added or removed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CityBikesConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
