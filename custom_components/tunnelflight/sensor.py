import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_NAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)

from .const import DOMAIN, DEFAULT_NAME
from .api import TunnelflightApi
from .service_fix import register_coordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=6)  # Update every 6 hours


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the IBA Tunnelflight sensor from config entry."""
    config = entry.data

    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    name = config.get(CONF_NAME, DEFAULT_NAME)

    session = async_get_clientsession(hass)
    api = TunnelflightApi(username, password, session)

    # Create a data coordinator to handle updates
    coordinator = TunnelflightCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    register_coordinator(entry.entry_id, coordinator)

    # Log the data we received to check if expiry dates are present
    if coordinator.data:
        _LOGGER.debug(f"User data from API: {coordinator.data}")
        _LOGGER.debug(
            f"Payment expiry date: {coordinator.data.get('payment_expiry_date')}"
        )
        _LOGGER.debug(
            f"Currency renewal date: {coordinator.data.get('currency_renewal_date')}"
        )

    # Create entities
    entities = []

    # Create main sensor entity
    entities.append(TunnelflightSensor(coordinator, name, entry.entry_id, username))

    # Create binary sensors
    payment_sensor = TunnelflightBinarySensor(
        coordinator,
        f"{name} Payment Status",
        entry.entry_id,
        username,
        "payment_status",
        "Payment status",
        "mdi:credit-card",
    )

    currency_sensor = TunnelflightBinarySensor(
        coordinator,
        f"{name} Flyer Currency",
        entry.entry_id,
        username,
        "currency_flyer",
        "Flyer currency status",
        "mdi:parachute-outline",
    )

    entities.extend([payment_sensor, currency_sensor])

    # Create additional sensors
    entities.append(
        TunnelflightDataSensor(
            coordinator,
            f"{name} Total Flight Time",
            entry.entry_id,
            username,
            "total_flight_time",
            "Total flight time",
            "mdi:clock-outline",
        )
    )

    entities.append(
        TunnelflightDataSensor(
            coordinator,
            f"{name} Last Flight",
            entry.entry_id,
            username,
            "last_flight",
            "Last flight date",
            "mdi:calendar",
        )
    )

    # Add skill level sensors - only add if data exists
    if coordinator.data:
        # Get skill levels from API data
        static_level = coordinator.data.get("static_level", 0)
        dynamic_level = coordinator.data.get("dynamic_level", 0)
        formation_level = coordinator.data.get("formation_level", 0)

        # Create the skill level sensors
        entities.append(
            TunnelflightSkillSensor(
                coordinator,
                f"{name} Static Level",
                entry.entry_id,
                username,
                "static_level",
                "Static flying level",
                "mdi:alpha-s-circle",
            )
        )

        entities.append(
            TunnelflightSkillSensor(
                coordinator,
                f"{name} Dynamic Level",
                entry.entry_id,
                username,
                "dynamic_level",
                "Dynamic flying level",
                "mdi:alpha-d-circle",
            )
        )

        entities.append(
            TunnelflightSkillSensor(
                coordinator,
                f"{name} Formation Level",
                entry.entry_id,
                username,
                "formation_level",
                "Formation flying level",
                "mdi:alpha-f-circle",
            )
        )

        # Create skills category sensors if we have logbook data
        if "skills_by_category" in coordinator.data:
            skills_by_category = coordinator.data.get("skills_by_category", {})

            for category_name, skills_data in skills_by_category.items():
                if skills_data:  # Only create sensors for categories with data
                    entities.append(
                        TunnelflightSkillsCategorySensor(
                            coordinator,
                            name,
                            entry.entry_id,
                            username,
                            category_name,
                            skills_data,
                        )
                    )

                    _LOGGER.debug(
                        f"Created skills sensor for category: {category_name} with {len(skills_data)} skills"
                    )

    async_add_entities(entities, False)  # False = don't update entities right away


class TunnelflightCoordinator(DataUpdateCoordinator):
    """Class to coordinate data updates for all entities."""

    def __init__(self, hass, api):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self._api = api
        # Store the API for use in services
        self.api = api
        # Internal cache for data
        self._cached_data = {}  # Dict to store data by endpoint

    async def _async_update_data(self):
        """Fetch data from the API."""
        try:
            _LOGGER.debug("Starting coordinator data refresh")

            # Use the ETags system in the API to check if data has changed
            data = await self._api.get_user_data()

            if data:
                _LOGGER.debug("Successfully updated user data")
                # If we got a 304 response, the API method should have logged it
                return data
            else:
                # If we didn't get data but have cached data, use that as a fallback
                if hasattr(self, "data") and self.data:
                    _LOGGER.warning("Using existing data as no new data was received")
                    return self.data

                _LOGGER.error("No data available and no cached data")
                raise Exception("Failed to fetch data and no cache available")
        except Exception as e:
            _LOGGER.error(f"Error updating data: {e}")
            # Return existing data if available, otherwise raise the exception
            if hasattr(self, "data") and self.data:
                _LOGGER.warning(f"Using existing data after error: {e}")
                return self.data
            raise


class TunnelflightSensor(CoordinatorEntity, SensorEntity):
    """Representation of an IBA Tunnelflight sensor."""

    def __init__(self, coordinator, name, entry_id, username):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._name = name
        self._entry_id = entry_id
        self._unique_id = f"tunnelflight_{username}"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        # Try to get payment status from API data
        payment_status = self.coordinator.data.get("payment_status")
        if payment_status:
            return payment_status

        # Fallback to payment status from paymentData
        payment_data = self.coordinator.data.get("paymentData", {})
        return payment_data.get("paymentStatus", "Unknown")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}

        user_info = self.coordinator.data

        # Extract and store relevant user info
        attributes = {}

        # Map appropriate fields from API data
        if "member_id" in user_info:
            attributes["member_id"] = str(user_info.get("member_id")).replace(",", "")

        if "role_name" in user_info:
            attributes["role_name"] = user_info.get("role_name")

        # Currency status
        if "currency_flyer" in user_info:
            attributes["currency_flyer"] = self._format_currency_status(
                user_info.get("currency_flyer")
            )

        # User information
        if "screen_name" in user_info:
            attributes["username"] = user_info.get("screen_name")

        if "email" in user_info:
            attributes["email"] = user_info.get("email")

        # Real name might be in a different field in the API
        for possible_name_field in ["real_name", "name", "user_real_name"]:
            if possible_name_field in user_info and user_info.get(possible_name_field):
                attributes["real_name"] = user_info.get(possible_name_field)
                break

        # Tunnel info
        if "tunnel_name" in user_info:
            attributes["tunnel"] = user_info.get("tunnel_name")

        # Country might be in tunnel_country or country field
        for possible_country_field in ["tunnel_country", "country"]:
            if possible_country_field in user_info and user_info.get(
                possible_country_field
            ):
                attributes["country"] = user_info.get(possible_country_field)
                break

        # Join date formatting
        if "join_date" in user_info:
            attributes["join_date"] = self._format_timestamp(user_info.get("join_date"))

        # Last flight date formatting
        if "last_flight" in user_info:
            attributes["last_flight"] = self._format_timestamp(
                user_info.get("last_flight")
            )

        # Only add instructor/coach currency if user has those roles
        if user_info.get("role_name") != "Flyer":
            if "currency_instructor" in user_info:
                attributes["currency_instructor"] = self._format_currency_status(
                    user_info.get("currency_instructor")
                )
            if "currency_coach" in user_info:
                attributes["currency_coach"] = self._format_currency_status(
                    user_info.get("currency_coach")
                )

        return attributes

    @property
    def available(self):
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._name,
            "manufacturer": "International Bodyflight Association",
            "model": "Tunnelflight Account",
        }

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:parachute"

    def _format_timestamp(self, timestamp):
        """Format a UNIX timestamp to a human-readable date."""
        if not timestamp:
            return None
        try:
            # If the timestamp is a string that looks like ISO format, try to parse it directly
            if isinstance(timestamp, str) and "T" in timestamp:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            # Otherwise assume it's a UNIX timestamp
            return datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d")
        except:
            return str(timestamp)

    def _format_currency_status(self, status):
        """Format currency status to a readable value."""
        if status == 1:
            return "current"
        elif status == 0:
            return "not_current"
        else:
            return "unknown"


class TunnelflightBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an IBA Tunnelflight binary sensor."""

    def __init__(
        self, coordinator, name, entry_id, username, sensor_type, description, icon
    ):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._name = name
        self._entry_id = entry_id
        self._unique_id = f"tunnelflight_{username}_{sensor_type}"
        self._sensor_type = sensor_type
        self._description = description
        self._icon = icon

        # Log initialization to verify entities are being created
        _LOGGER.debug(f"Creating binary sensor: {self._name} ({self._sensor_type})")

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        if not self.coordinator.data:
            return None

        user_info = self.coordinator.data

        if self._sensor_type == "currency_flyer":
            # First try the currency_flyer field
            currency_flyer = user_info.get("currency_flyer")
            if currency_flyer is not None:
                return currency_flyer == 1

            # Then try the flyer_currency_status field
            flyer_currency_status = user_info.get("flyer_currency_status")
            if flyer_currency_status:
                return flyer_currency_status.lower() == "active"

            return False

        elif self._sensor_type == "payment_status":
            # First try the payment_status field
            payment_status = user_info.get("payment_status")
            if payment_status:
                return payment_status.lower() == "active"

            # Then try paymentData.paymentStatus field
            payment_data = user_info.get("paymentData", {})
            payment_status = payment_data.get("paymentStatus")
            if payment_status:
                return payment_status.lower() == "active"

            return False

        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            _LOGGER.debug(f"No coordinator data for {self._name}")
            return {}

        user_info = self.coordinator.data
        attributes = {}

        if self._sensor_type == "currency_flyer":
            # Try different possible date fields for currency renewal
            currency_renewal = None

            # First try direct currency_renewal_date field
            if "currency_renewal_date" in user_info:
                currency_renewal = user_info.get("currency_renewal_date")

            # Then try currency_renewal_date_flyer field
            elif "currency_renewal_date_flyer" in user_info:
                # This might be a timestamp
                try:
                    timestamp = user_info.get("currency_renewal_date_flyer")
                    if timestamp:
                        currency_renewal = datetime.fromtimestamp(
                            int(timestamp)
                        ).strftime("%Y-%m-%d")
                except Exception as e:
                    _LOGGER.error(f"Error formatting currency_renewal_date_flyer: {e}")

            _LOGGER.debug(f"Currency renewal date for {self._name}: {currency_renewal}")

            if currency_renewal:
                # Add the expiry date as an attribute
                attributes["expiry_date"] = currency_renewal

                # Calculate days remaining
                try:
                    expiry_date = datetime.strptime(currency_renewal, "%Y-%m-%d")
                    today = datetime.now().replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    days_remaining = (expiry_date - today).days
                    attributes["days_remaining"] = days_remaining
                    _LOGGER.debug(
                        f"Days remaining until currency expiry: {days_remaining}"
                    )
                except Exception as e:
                    _LOGGER.error(f"Error calculating days until currency expiry: {e}")

        elif self._sensor_type == "payment_status":
            # Try different possible date fields for payment expiry
            expiry_date = None

            # First check payment_expiry_date field
            if "payment_expiry_date" in user_info:
                expiry_date = user_info.get("payment_expiry_date")

            # Then try paymentData.nextDate field
            elif "paymentData" in user_info and "nextDate" in user_info["paymentData"]:
                try:
                    timestamp = user_info["paymentData"]["nextDate"]
                    if timestamp:
                        expiry_date = datetime.fromtimestamp(int(timestamp)).strftime(
                            "%Y-%m-%d"
                        )
                except Exception as e:
                    _LOGGER.error(f"Error formatting paymentData.nextDate: {e}")

            _LOGGER.debug(f"Payment expiry date for {self._name}: {expiry_date}")

            if expiry_date:
                # Add the expiry date as an attribute
                attributes["expiry_date"] = expiry_date

                # Calculate days remaining
                try:
                    expiry_date_obj = datetime.strptime(expiry_date, "%Y-%m-%d")
                    today = datetime.now().replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    days_remaining = (expiry_date_obj - today).days
                    attributes["days_remaining"] = days_remaining
                    _LOGGER.debug(
                        f"Days remaining until payment expiry: {days_remaining}"
                    )
                except Exception as e:
                    _LOGGER.error(f"Error calculating days until payment expiry: {e}")

        _LOGGER.debug(f"Attributes for {self._name}: {attributes}")
        return attributes

    @property
    def available(self):
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._name.split(" ")[0],  # Use base name
            "manufacturer": "International Bodyflight Association",
            "model": "Tunnelflight Account",
        }

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return "connectivity"


class TunnelflightDataSensor(CoordinatorEntity, SensorEntity):
    """Representation of an IBA Tunnelflight data sensor for specific attributes."""

    def __init__(
        self, coordinator, name, entry_id, username, sensor_type, description, icon
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._name = name
        self._entry_id = entry_id
        self._unique_id = f"tunnelflight_{username}_{sensor_type}"
        self._sensor_type = sensor_type
        self._description = description
        self._icon = icon

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        user_info = self.coordinator.data

        if self._sensor_type == "total_flight_time":
            # Use the formatted flight time directly from API if available
            if "total_flight_time" in user_info:
                # Format properly to ensure minutes have leading zeros
                time_str = user_info['total_flight_time']
                if ":" in time_str:
                    try:
                        hours_str, minutes_str = time_str.split(":")
                        hours = int(hours_str)
                        minutes = int(minutes_str)
                        return f"{hours}:{minutes:02d} hours"
                    except (ValueError, TypeError):
                        # In case of parsing error, return the original string
                        return f"{time_str} hours"
                else:
                    return f"{time_str} hours"

            # Otherwise use the parsed components if available
            elif (
                "total_flight_time_hours" in user_info
                and "total_flight_time_minutes" in user_info
            ):
                hours = user_info.get("total_flight_time_hours", 0)
                minutes = user_info.get("total_flight_time_minutes", 0)
                return f"{hours}:{minutes:02d} hours"

            return "0:00 hours"

        elif self._sensor_type == "last_flight":
            # Try to get last_flight data, could be a timestamp or ISO string
            last_flight = user_info.get("last_flight")
            if last_flight:
                return self._format_timestamp(last_flight)

            return None

        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}

        user_info = self.coordinator.data
        attributes = {}

        if self._sensor_type == "total_flight_time":
            # Calculate total minutes for additional use
            # First try to parse from the original format "3:34"
            flight_time = user_info.get("total_flight_time")
            hours = 0
            minutes = 0

            if flight_time and ":" in flight_time:
                try:
                    hours_str, minutes_str = flight_time.split(":")
                    hours = int(hours_str)
                    minutes = int(minutes_str)
                except Exception as e:
                    _LOGGER.error(f"Error parsing flight time {flight_time}: {e}")
            else:
                # Fallback to individual components
                hours = user_info.get("total_flight_time_hours", 0)
                minutes = user_info.get("total_flight_time_minutes", 0)

            total_minutes = (hours * 60) + minutes

            attributes = {
                "hours_decimal": round(total_minutes / 60, 2),
                "total_minutes": total_minutes,
            }

        return attributes

    @property
    def available(self):
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._name.split(" ")[0],  # Use base name
            "manufacturer": "International Bodyflight Association",
            "model": "Tunnelflight Account",
        }

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    def _format_timestamp(self, timestamp):
        """Format a UNIX timestamp to a human-readable date."""
        if not timestamp:
            return None
        try:
            # If the timestamp is a string that looks like ISO format, try to parse it directly
            if isinstance(timestamp, str) and "T" in timestamp:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            # Otherwise assume it's a UNIX timestamp
            return datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d")
        except:
            return str(timestamp)


class TunnelflightSkillSensor(CoordinatorEntity, SensorEntity):
    """Representation of an IBA Tunnelflight skill level sensor."""

    def __init__(
        self, coordinator, name, entry_id, username, skill_type, description, icon
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._name = name
        self._entry_id = entry_id
        self._unique_id = f"tunnelflight_{username}_{skill_type}"
        self._skill_type = skill_type
        self._description = description
        self._icon = icon

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None

        user_info = self.coordinator.data

        # Get skill level from the API data
        # The levels are extracted in the API class using several endpoints
        if self._skill_type == "static_level":
            # Get the static level
            level = user_info.get("static_level")
            if level is not None:
                return str(level)
            return "0"

        elif self._skill_type == "dynamic_level":
            # Get the dynamic level
            level = user_info.get("dynamic_level")
            if level is not None:
                return str(level)
            return "0"

        elif self._skill_type == "formation_level":
            # Get the formation level
            level = user_info.get("formation_level")
            if level is not None:
                return str(level)
            return "0"

        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}

        user_info = self.coordinator.data
        attributes = {}

        # Add skill status to attributes
        if self._skill_type == "static_level":
            # First check for pending status
            if user_info.get("static_pending", False):
                attributes["status"] = "pending"
            # Then check for explicit status
            elif "static_level_status" in user_info:
                attributes["status"] = user_info.get("static_level_status")
            else:
                # Otherwise derive status from level
                level = user_info.get("static_level", 0)
                attributes["status"] = "passed" if level > 0 else "not_passed"

            # Include the raw value from the API if available (Yes/No)
            if "static" in user_info:
                attributes["raw_value"] = user_info.get("static")

            # Include pending flag
            if "static_pending" in user_info:
                attributes["pending"] = user_info.get("static_pending", False)

        elif self._skill_type == "dynamic_level":
            # First check for pending status
            if user_info.get("dynamic_pending", False):
                attributes["status"] = "pending"
            # Then check for explicit status
            elif "dynamic_level_status" in user_info:
                attributes["status"] = user_info.get("dynamic_level_status")
            else:
                # Otherwise derive status from level
                level = user_info.get("dynamic_level", 0)
                attributes["status"] = "passed" if level > 0 else "not_passed"

            # Include the raw value from the API if available
            if "dynamic" in user_info:
                attributes["raw_value"] = user_info.get("dynamic")

            # Include pending flag
            if "dynamic_pending" in user_info:
                attributes["pending"] = user_info.get("dynamic_pending", False)

        elif self._skill_type == "formation_level":
            # First check for pending status
            if user_info.get("formation_pending", False):
                attributes["status"] = "pending"
            # Then check for explicit status
            elif "formation_level_status" in user_info:
                attributes["status"] = user_info.get("formation_level_status")
            else:
                # Otherwise derive status from level
                level = user_info.get("formation_level", 0)
                attributes["status"] = "passed" if level > 0 else "not_passed"

            # Include the raw value from the API if available
            if "formation" in user_info:
                attributes["raw_value"] = user_info.get("formation")

            # Include pending flag
            if "formation_pending" in user_info:
                attributes["pending"] = user_info.get("formation_pending", False)

        # Add level1 info for all skill sensors, since it's a prerequisite
        if "level1" in user_info:
            attributes["level1"] = user_info.get("level1")

        if "level1_pending" in user_info:
            attributes["level1_pending"] = user_info.get("level1_pending", False)

        return attributes

    @property
    def available(self):
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._name.split(" ")[0],  # Use base name
            "manufacturer": "International Bodyflight Association",
            "model": "Tunnelflight Account",
        }

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon


class TunnelflightSkillsCategorySensor(CoordinatorEntity, SensorEntity):
    """Representation of an IBA Tunnelflight skills category sensor."""

    def __init__(
        self, coordinator, name, entry_id, username, category_name, skills_data
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._name = f"{name} {category_name} Skills"
        self._entry_id = entry_id
        self._unique_id = (
            f"tunnelflight_{username}_skills_{category_name.lower().replace(' ', '_')}"
        )
        self._category_name = category_name
        self._skills_data = skills_data

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def state(self):
        """Return the state of the sensor."""
        # Count how many skills are completed in this category
        completed_count = sum(
            1 for skill in self._skills_data if skill["status"] == "open"
        )
        return f"{completed_count}/{len(self._skills_data)}"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {
            "category": self._category_name,
            "skills_count": len(self._skills_data),
            "skills": [],
        }

        # Add each skill as an attribute
        for skill in self._skills_data:
            attributes["skills"].append(
                {
                    "name": skill["name"],
                    "status": skill["status"],
                    "completion_date": datetime.fromtimestamp(
                        skill["approval_date"]
                    ).strftime("%Y-%m-%d")
                    if skill.get("approval_date")
                    else None,
                    "instructor": skill.get("instructor", ""),
                }
            )

        return attributes

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._name.split(" ")[0],  # Use base name
            "manufacturer": "International Bodyflight Association",
            "model": "Tunnelflight Account",
        }

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return "mdi:certificate"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled by default."""
        return False  # Disabled by default as requested
