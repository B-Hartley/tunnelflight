# IBA Tunnelflight Integration for Home Assistant

A custom integration that connects to the International Bodyflight Association (IBA) website and displays your indoor skydiving data in Home Assistant.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

## Features

- Display your IBA membership status
- Show flight skills (Static, Dynamic, and Formation levels)
- Track total flight time
- Monitor payment and currency expiry dates
- Support for multiple IBA accounts in one Home Assistant instance

## Installation

### HACS Installation (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Add this repository as a custom repository in HACS:
   - Go to HACS → Integrations
   - Click the three dots in the top right corner
   - Select "Custom repositories"
   - Add the URL: `https://github.com/B-Hartley/tunnelflight`
   - Select "Integration" as the category
3. Click "Download" on the IBA Tunnelflight integration
4. Restart Home Assistant

### Manual Installation

1. Create the directory structure in your Home Assistant configuration directory:
   ```
   custom_components/tunnelflight/translations/
   ```

2. Copy these files to the tunnelflight directory:
   - `__init__.py`
   - `api.py`
   - `binary_sensor.py`
   - `config_flow.py`
   - `const.py`
   - `manifest.json`
   - `sensor.py`
   - And `en.json` to the translations subdirectory

3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "IBA Tunnelflight" and follow the setup process
3. Enter your IBA username and password
4. Optionally, provide a custom name for the integration

The integration verifies your credentials before completing the setup.

## Available Entities

Each IBA account will create the following entities:

### Sensors

- `sensor.iba_[username]`: Main sensor showing membership status
- `sensor.iba_[username]_total_flight_time`: Total flight time
- `sensor.iba_[username]_last_flight`: Date of last flight
- `sensor.iba_[username]_static_level`: Static flying level
- `sensor.iba_[username]_dynamic_level`: Dynamic flying level
- `sensor.iba_[username]_formation_level`: Formation flying level

### Binary Sensors

- `binary_sensor.iba_[username]_flyer_currency`: Flyer currency status with expiry date
- `binary_sensor.iba_[username]_payment_status`: Payment status with expiry date

## Skill Levels and Attributes

The skill sensors provide rich data about your IBA certification levels:

| Attribute | Description |
|-----------|-------------|
| `state` | The numeric level (0, 1, 2, etc.) |
| `status` | Status: "Passed", "Not Passed", or "Pending" |
| `raw_value` | Raw value from IBA website (e.g., "Yes", "No", "Level 2") |
| `pending` | Whether the certification is pending (true/false) |
| `level1` | Status of the prerequisite Level1 certification |
| `level1_pending` | Whether Level1 is pending |

## Dashboard Examples

### Basic Card

```yaml
type: entities
title: Indoor Skydiving
entities:
  - entity: sensor.iba_username
    name: Membership Status
  - entity: sensor.iba_username_total_flight_time
    name: Total Flight Time
  - entity: sensor.iba_username_last_flight
    name: Last Flight
  - entity: binary_sensor.iba_username_flyer_currency
    name: Flyer Currency
    secondary_info: attribute
    secondary_info_attribute: expiry_date
  - entity: binary_sensor.iba_username_payment_status
    name: Payment Status
    secondary_info: attribute
    secondary_info_attribute: expiry_date
```

### Skills Card

```yaml
type: glance
title: Flying Skills
entities:
  - entity: sensor.iba_username_static_level
    name: Static
    icon: mdi:alpha-s-circle
  - entity: sensor.iba_username_dynamic_level
    name: Dynamic
    icon: mdi:alpha-d-circle
  - entity: sensor.iba_username_formation_level
    name: Formation
    icon: mdi:alpha-f-circle
```

### Conditional Card with Skill Status

```yaml
type: conditional
conditions:
  - entity: sensor.iba_username_static_level
    state_not: "0"
card:
  type: markdown
  content: >
    ## Static Level {{ states('sensor.iba_username_static_level') }}
    
    Status: {{ state_attr('sensor.iba_username_static_level', 'status') }}
```

## Automations

### Payment Expiry Notification

```yaml
- alias: IBA Payment Expiring Soon
  trigger:
    - platform: numeric_state
      entity_id: binary_sensor.iba_username_payment_status
      attribute: days_remaining
      below: 30
  action:
    - service: notify.mobile_app
      data:
        title: "IBA Payment Expiring Soon"
        message: "Your IBA payment expires in {{ state_attr('binary_sensor.iba_username_payment_status', 'days_remaining') }} days ({{ state_attr('binary_sensor.iba_username_payment_status', 'expiry_date') }})"
```

### Currency Expiry Notification

```yaml
- alias: IBA Currency Expiring Soon
  trigger:
    - platform: numeric_state
      entity_id: binary_sensor.iba_username_flyer_currency
      attribute: days_remaining
      below: 30
  action:
    - service: notify.mobile_app
      data:
        title: "IBA Currency Expiring Soon"
        message: "Your IBA currency expires in {{ state_attr('binary_sensor.iba_username_flyer_currency', 'days_remaining') }} days ({{ state_attr('binary_sensor.iba_username_flyer_currency', 'expiry_date') }})"
```

### Skill Level Change Notification

```yaml
- alias: IBA Skill Level Changed
  trigger:
    - platform: state
      entity_id: 
        - sensor.iba_username_static_level
        - sensor.iba_username_dynamic_level
        - sensor.iba_username_formation_level
  action:
    - service: notify.mobile_app
      data:
        title: "IBA Skill Level Changed"
        message: "Your {{ trigger.to_state.name }} has changed to {{ trigger.to_state.state }}"
```

## Multiple Accounts

The integration supports multiple IBA accounts. Each account creates its own set of entities with the username included in the entity ID to avoid conflicts.

For example, if you have accounts for "bruceh" and "sarahh", you'll get:
- `sensor.iba_bruceh_total_flight_time`
- `sensor.iba_sarahh_total_flight_time`

## Troubleshooting

### Enable Debug Logging

Add this to your `configuration.yaml` file:

```yaml
logger:
  default: info
  logs:
    custom_components.tunnelflight: debug
```

### Common Issues

- **Authentication errors**: Verify your IBA username and password
- **Missing data**: The integration may not be able to find some data on the IBA website
- **Incorrect skill levels**: Use the raw_value attribute to see what the IBA website is reporting

## Privacy and Security

This integration stores your IBA credentials in Home Assistant's configuration and uses them to log in to the IBA website. Your credentials are not sent anywhere else.

## Credits

This integration is an independent community project and is not affiliated with or endorsed by the International Bodyflight Association.

## License

This project is licensed under the MIT License - see the LICENSE file for details.


## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "IBA Tunnelflight" and follow the setup process
3. Enter your IBA username and password
4. Optionally, provide a custom name for the integration

The integration verifies your credentials before completing the setup.

## Available Entities

Each IBA account will create the following entities:

### Sensors

- `sensor.iba_[username]`: Main sensor showing membership status
- `sensor.iba_[username]_total_flight_time`: Total flight time
- `sensor.iba_[username]_last_flight`: Date of last flight
- `sensor.iba_[username]_static_level`: Static flying level
- `sensor.iba_[username]_dynamic_level`: Dynamic flying level
- `sensor.iba_[username]_formation_level`: Formation flying level

### Binary Sensors

- `binary_sensor.iba_[username]_flyer_currency`: Flyer currency status with expiry date
- `binary_sensor.iba_[username]_payment_status`: Payment status with expiry date

## Skill Levels and Attributes

The skill sensors provide rich data about your IBA certification levels:

| Attribute | Description |
|-----------|-------------|
| `state` | The numeric level (0, 1, 2, etc.) |
| `status` | Status: "Passed", "Not Passed", or "Pending" |
| `raw_value` | Raw value from IBA website (e.g., "Yes", "No", "Level 2") |
| `pending` | Whether the certification is pending (true/false) |
| `level1` | Status of the prerequisite Level1 certification |
| `level1_pending` | Whether Level1 is pending |

## Dashboard Examples

### Basic Card

```yaml
type: entities
title: Indoor Skydiving
entities:
  - entity: sensor.iba_username
    name: Membership Status
  - entity: sensor.iba_username_total_flight_time
    name: Total Flight Time
  - entity: sensor.iba_username_last_flight
    name: Last Flight
  - entity: binary_sensor.iba_username_flyer_currency
    name: Flyer Currency
    secondary_info: attribute
    secondary_info_attribute: expiry_date
  - entity: binary_sensor.iba_username_payment_status
    name: Payment Status
    secondary_info: attribute
    secondary_info_attribute: expiry_date
```

### Skills Card

```yaml
type: glance
title: Flying Skills
entities:
  - entity: sensor.iba_username_static_level
    name: Static
    icon: mdi:alpha-s-circle
  - entity: sensor.iba_username_dynamic_level
    name: Dynamic
    icon: mdi:alpha-d-circle
  - entity: sensor.iba_username_formation_level
    name: Formation
    icon: mdi:alpha-f-circle
```

### Conditional Card with Skill Status

```yaml
type: conditional
conditions:
  - entity: sensor.iba_username_static_level
    state_not: "0"
card:
  type: markdown
  content: >
    ## Static Level {{ states('sensor.iba_username_static_level') }}
    
    Status: {{ state_attr('sensor.iba_username_static_level', 'status') }}
```

## Automations

### Payment Expiry Notification

```yaml
- alias: IBA Payment Expiring Soon
  trigger:
    - platform: numeric_state
      entity_id: binary_sensor.iba_username_payment_status
      attribute: days_remaining
      below: 30
  action:
    - service: notify.mobile_app
      data:
        title: "IBA Payment Expiring Soon"
        message: "Your IBA payment expires in {{ state_attr('binary_sensor.iba_username_payment_status', 'days_remaining') }} days ({{ state_attr('binary_sensor.iba_username_payment_status', 'expiry_date') }})"
```

### Currency Expiry Notification

```yaml
- alias: IBA Currency Expiring Soon
  trigger:
    - platform: numeric_state
      entity_id: binary_sensor.iba_username_flyer_currency
      attribute: days_remaining
      below: 30
  action:
    - service: notify.mobile_app
      data:
        title: "IBA Currency Expiring Soon"
        message: "Your IBA currency expires in {{ state_attr('binary_sensor.iba_username_flyer_currency', 'days_remaining') }} days ({{ state_attr('binary_sensor.iba_username_flyer_currency', 'expiry_date') }})"
```

### Skill Level Change Notification

```yaml
- alias: IBA Skill Level Changed
  trigger:
    - platform: state
      entity_id: 
        - sensor.iba_username_static_level
        - sensor.iba_username_dynamic_level
        - sensor.iba_username_formation_level
  action:
    - service: notify.mobile_app
      data:
        title: "IBA Skill Level Changed"
        message: "Your {{ trigger.to_state.name }} has changed to {{ trigger.to_state.state }}"
```

## Multiple Accounts

The integration supports multiple IBA accounts. Each account creates its own set of entities with the username included in the entity ID to avoid conflicts.

For example, if you have accounts for "bruceh" and "sarahh", you'll get:
- `sensor.iba_bruceh_total_flight_time`
- `sensor.iba_sarahh_total_flight_time`

## Troubleshooting

### Enable Debug Logging

Add this to your `configuration.yaml` file:

```yaml
logger:
  default: info
  logs:
    custom_components.tunnelflight: debug
```

### Common Issues

- **Authentication errors**: Verify your IBA username and password
- **Missing data**: The integration may not be able to find some data on the IBA website
- **Incorrect skill levels**: Use the raw_value attribute to see what the IBA website is reporting

## Privacy and Security

This integration stores your IBA credentials in Home Assistant's configuration and uses them to log in to the IBA website. Your credentials are not sent anywhere else.

## Credits

This integration is an independent community project and is not affiliated with or endorsed by the International Bodyflight Association.

## License

This project is licensed under the MIT License - see the LICENSE file for details.