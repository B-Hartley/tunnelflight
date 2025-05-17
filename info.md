# IBA Tunnelflight

This integration connects to the International Bodyflight Association (IBA) website and displays your indoor skydiving data in Home Assistant.

## Features

- Display your IBA membership status
- Show flight skills (Static, Dynamic, and Formation levels)
- Track total flight time
- Monitor payment and currency expiry dates
- Support for multiple IBA accounts in one Home Assistant instance

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

## Links

- [Documentation](https://github.com/B-Hartley/tunnelflight)
- [Report an issue](https://github.com/B-Hartley/tunnelflight/issues)