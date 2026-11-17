# CityBikes for Home Assistant

See how many bikes, e-bikes and empty docks are at your bike-share stations, for
[hundreds of networks worldwide](https://citybik.es/), using the open
[CityBikes API](https://api.citybik.es/v2/). No account or API key needed.

This is a modernized version of Home Assistant's built-in CityBikes integration. It
replaces the YAML-only sensor with:

- **Setup from the UI.** Pick your network (the one closest to your home is
  suggested), then the stations you care about.
- **A device per station** with sensors for available bikes, available e-bikes
  (on networks that report them), empty docks, and the time the station last
  reported (disabled by default).
- **Add or remove stations at any time** with *Add station* on the network.
- **Automatic import of your existing YAML configuration.**
- **A dashboard card**, included and ready to use. No separate download or
  resource to add.

## Installation

This integration is not listed in the Marketplace catalog. The catalog does not
accept custom integrations that replace a built-in one, and replacing the built-in
integration is what lets your YAML configuration be imported. Add it by its link
instead.

### Marketplace (Home Assistant 2026.11 and newer)

1. Go to **Settings > Marketplace**, open the menu in the top right and choose
   **Custom repositories**.
2. Add `https://github.com/elcaptain/ha-citybikes` with the type **Integration**.
3. Open **CityBikes**, download it, and restart Home Assistant.

### HACS (Home Assistant 2026.10)

1. In HACS, open the menu in the top right and choose **Custom repositories**.
2. Add `https://github.com/elcaptain/ha-citybikes` with the type **Integration**.
3. Search for **CityBikes**, download it, and restart Home Assistant.

### Manual

Copy `custom_components/citybikes` into the `custom_components` folder of your Home
Assistant configuration, then restart Home Assistant.

Home Assistant 2026.10 or newer is required.

## Setup

1. Go to **Settings > Devices & services > Add integration** and pick **CityBikes**.
2. Choose your bike-share network.
3. Optionally pick the first stations to follow. You can add more later with
   **Add station** on the CityBikes integration page.

Each network can be added once. To follow stations in several cities, add each
network separately.

## Dashboard card

The integration comes with a CityBikes card. For each station it shows the number
of available bikes, a bar of how full the docks are, and the e-bikes and empty
docks.

- Bike counts of 2 or fewer show in orange; empty stations show in red.
- E-bikes show only for networks that report them.
- Tap a station to open its details.
- With the station's **Last reported** sensor enabled, the card shows how long ago
  the station reported.
- Follows your theme, light and dark, and the sections layout.

Edit a dashboard, choose **Add card** and pick **CityBikes**. The visual editor lets
you set a title and pick stations. Without stations it shows every CityBikes
station, sorted by name.

```yaml
type: custom:citybikes-card
title: Bikes near home
devices:            # optional; device IDs of CityBikes stations
  - 0123456789abcdef0123456789abcdef
```

| Option    | Description                                                       |
| --------- | ----------------------------------------------------------------- |
| `title`   | Optional card title.                                              |
| `devices` | Optional list of station devices. Leave out to show all stations. |

The card is loaded automatically once the integration is installed. If it does not
show up in the card picker right after an update, reload the page.

## Moving from YAML

If you used the built-in YAML sensor platform, your configuration is imported on
the first start:

- Your network (or the one closest to the configured coordinates) becomes a
  CityBikes entry.
- Stations matched by `radius` or listed under `stations` become stations of that
  entry. Several YAML blocks for the same network are merged.

After the import, remove the `citybikes` sensor platform from your
`configuration.yaml`. A repair issue reminds you to do so, or explains why the import
failed.

The new sensors get new entity IDs, like `sensor.central_station_available_bikes`,
so update any automations and dashboards that used the old ones. The `name` option
is no longer used, and the latitude, longitude and uid attributes are gone; the
report time is now its own sensor.

> [!NOTE]
> This custom integration uses the same `citybikes` domain as the built-in one, so
> it replaces the built-in integration while installed. Home Assistant shows a
> warning about this in the log at startup; that is expected.

## Data updates

Station data is fetched every 5 minutes for each network. If CityBikes cannot be
reached, the sensors show as unavailable until the next successful update. If a
station is removed from the network, its sensors stay unavailable; remove the
station from the integration.

## Removal

1. Go to **Settings > Devices & services > CityBikes**, open the menu and choose
   **Delete**.
2. To uninstall the integration itself, remove it in the Marketplace (or HACS), or
   delete the
   `custom_components/citybikes` folder, then restart Home Assistant.

## Credits

Station data comes from the [CityBikes project](https://citybik.es/#about). This
integration is based on the CityBikes integration in
[Home Assistant Core](https://github.com/home-assistant/core), licensed under the
Apache License 2.0.
