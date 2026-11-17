"""Sensors for the CityBikes integration."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import override

from citybikes.model import Station
import probatio

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import SOURCE_IMPORT, ConfigSubentry
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RADIUS,
    EntityCategory,
)
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    AddEntitiesCallback,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType, StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import (
    CONF_NETWORK,
    CONF_STATION_ID,
    CONF_STATIONS,
    DOMAIN,
    SUBENTRY_TYPE_STATION,
)
from .coordinator import CityBikesConfigEntry, CityBikesDataUpdateCoordinator

PARALLEL_UPDATES = 0

BREAKS_IN_HA_VERSION = "2027.6.0"
INTEGRATION_TITLE = "CityBikes"

ATTRIBUTION = (
    "Information provided by the CityBikes Project (https://citybik.es/#about)"
)

IMPORT_LOCK: HassKey[asyncio.Lock] = HassKey(f"{DOMAIN}_import_lock")

PLATFORM_SCHEMA = probatio.All(
    probatio.AtLeastOne(CONF_RADIUS, CONF_STATIONS),
    SENSOR_PLATFORM_SCHEMA.extend(
        {
            probatio.Optional(CONF_NAME, default=""): cv.string,
            probatio.Optional(CONF_NETWORK): cv.string,
            probatio.Inclusive(CONF_LATITUDE, "coordinates"): cv.latitude,
            probatio.Inclusive(CONF_LONGITUDE, "coordinates"): cv.longitude,
            probatio.Optional(CONF_RADIUS, "station_filter"): cv.positive_int,
            probatio.Optional(CONF_STATIONS, "station_filter"): probatio.All(
                probatio.EnsureList(), probatio.NonEmpty(), [cv.string]
            ),
        }
    ),
)


@dataclass(frozen=True, kw_only=True)
class CityBikesSensorEntityDescription(SensorEntityDescription):
    """Describes a CityBikes station sensor."""

    value_fn: Callable[[Station], StateType | datetime]
    exists_fn: Callable[[Station], bool] = lambda _: True


SENSOR_TYPES: tuple[CityBikesSensorEntityDescription, ...] = (
    CityBikesSensorEntityDescription(
        key="free_bikes",
        translation_key="free_bikes",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda station: station.free_bikes,
    ),
    CityBikesSensorEntityDescription(
        key="free_ebikes",
        translation_key="free_ebikes",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda station: station.extra.get("ebikes"),
        exists_fn=lambda station: "ebikes" in station.extra,
    ),
    CityBikesSensorEntityDescription(
        key="empty_slots",
        translation_key="empty_slots",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda station: station.empty_slots,
    ),
    CityBikesSensorEntityDescription(
        key="last_reported",
        translation_key="last_reported",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda station: dt_util.parse_datetime(station.timestamp),
    ),
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Import the YAML sensor platform into a config entry."""
    # Serialize imports so YAML blocks for the same network merge their stations.
    async with hass.data.setdefault(IMPORT_LOCK, asyncio.Lock()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=config
        )

    if (
        result["type"] is FlowResultType.ABORT
        and (reason := result["reason"]) != "already_configured"
    ):
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"deprecated_yaml_import_issue_{reason}",
            breaks_in_ha_version=BREAKS_IN_HA_VERSION,
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=ir.IssueSeverity.WARNING,
            translation_key=f"deprecated_yaml_import_issue_{reason}",
            translation_placeholders={
                "domain": DOMAIN,
                "integration_title": INTEGRATION_TITLE,
            },
        )
        return

    ir.async_create_issue(
        hass,
        HOMEASSISTANT_DOMAIN,
        f"deprecated_yaml_{DOMAIN}",
        breaks_in_ha_version=BREAKS_IN_HA_VERSION,
        is_fixable=False,
        issue_domain=DOMAIN,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deprecated_yaml",
        translation_placeholders={
            "domain": DOMAIN,
            "integration_title": INTEGRATION_TITLE,
        },
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CityBikesConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CityBikes sensors for every configured station."""
    coordinator = entry.runtime_data
    for subentry in entry.get_subentries_of_type(SUBENTRY_TYPE_STATION):
        station = coordinator.data.get(subentry.data[CONF_STATION_ID])
        async_add_entities(
            (
                CityBikesStationSensor(coordinator, subentry, description)
                for description in SENSOR_TYPES
                if station is None or description.exists_fn(station)
            ),
            config_subentry_id=subentry.subentry_id,
        )


class CityBikesStationSensor(
    CoordinatorEntity[CityBikesDataUpdateCoordinator], SensorEntity
):
    """A sensor for one value of a bike-share station."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    entity_description: CityBikesSensorEntityDescription

    def __init__(
        self,
        coordinator: CityBikesDataUpdateCoordinator,
        subentry: ConfigSubentry,
        description: CityBikesSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._station_id: str = subentry.data[CONF_STATION_ID]
        network_id = coordinator.network_id
        self._attr_unique_id = f"{network_id}_{self._station_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{network_id}_{self._station_id}")},
            name=subentry.title,
            manufacturer=coordinator.config_entry.title,
            model="Station",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    @override
    def available(self) -> bool:
        """Return if the station is still part of the network."""
        return super().available and self._station_id in self.coordinator.data

    @property
    @override
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data[self._station_id])
