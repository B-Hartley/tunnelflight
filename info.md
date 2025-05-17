# IBA Tunnelflight

This integration connects to the International Bodyflight Association (IBA) website and displays your indoor skydiving data in Home Assistant.

## Features

- Display your IBA membership status
- Show flight skills (Static, Dynamic, and Formation levels)
- Track total flight time
- Monitor payment and currency expiry dates
- Support for multiple IBA accounts in one Home Assistant instance
- Log flight time directly from Home Assistant
- Search for tunnels using a dynamic database

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "IBA Tunnelflight" and follow the setup process
3. Enter your IBA username and password

## Available Entities

Each IBA account will create:

- Membership status sensor
- Total flight time sensor
- Last flight date sensor
- Skill level sensors (Static, Dynamic, Formation)
- Currency status binary sensor
- Payment status binary sensor

## Services

The integration provides two services:

### Log Flight Time

Log new flight time entries to your Tunnelflight account:

```yaml
service: tunnelflight.log_flight_time
data:
  tunnel_id: 248  # Basingstoke iFLY
  time: 10  # Minutes (1-120)
  comment: "Great session!"
```

### Find Tunnels

Search for wind tunnels by name or location:

```yaml
service: tunnelflight.find_tunnels
data:
  search_term: "manchester"
  country: "united kingdom"
```

To list all available countries:

```yaml
service: tunnelflight.find_tunnels
data:
  list_countries: true

Results appear as a persistent notification in Home Assistant.

## Links

- [Documentation](https://github.com/B-Hartley/tunnelflight)
- [Report an issue](https://github.com/B-Hartley/tunnelflight/issues)
