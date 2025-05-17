# IBA Tunnelflight Integration for Home Assistant

This integration connects to the [International Bodyflight Association](https://www.tunnelflight.com/) (IBA) Tunnelflight platform to provide information about your wind tunnel flying status, skills, and flight time.

## Features

- Track your IBA membership status and currency
- Monitor your Static, Dynamic, and Formation flying skill levels
- View detailed information about your completed skills
- Log flight time directly to your IBA logbook
- Search the global database of wind tunnels

## Installation

### HACS (Recommended)

1. Open HACS
2. Go to "Integrations"
3. Click the "+" button
4. Search for "IBA Tunnelflight"
5. Click "Install"
6. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Extract the folder `tunnelflight` to `<config>/custom_components/`
3. Restart Home Assistant

## Configuration

Add the integration via the Home Assistant UI:

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "IBA Tunnelflight"
4. Enter your IBA username and password

## Services

The integration provides several services:

### tunnelflight.log_flight_time

Logs flight time to your IBA logbook.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| tunnel_id | int | Yes | ID of the tunnel where you flew |
| time | int | Yes | Flight time in minutes (1-120) |
| comment | string | No | Optional comment for the entry |
| entry_date | datetime | No | Date of flight (defaults to current time) |
| username | string | No | Specific account username (required if multiple accounts configured) |

### tunnelflight.find_tunnels

Searches for wind tunnels by name, city, or country.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| search_term | string | No | Text to search in tunnel name or city |
| country | string | No | Country to filter results |

### tunnelflight.list_countries

Lists all countries that have wind tunnels in the IBA database.

### tunnelflight.refresh_data

Forces a refresh of all data from the Tunnelflight API.

## Finding Tunnel IDs

To log flight time, you need the correct tunnel ID:

1. Use the `tunnelflight.find_tunnels` service with a search term like your tunnel's city name
2. If you're not sure of the country, first use `tunnelflight.list_countries` to see all available countries
3. The search results will include the tunnel ID needed for logging flight time

## License

This integration is licensed under the MIT License.