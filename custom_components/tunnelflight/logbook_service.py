import logging
import voluptuous as vol
from datetime import datetime
from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .api import TunnelflightApi
from .service_fix import get_coordinator

_LOGGER = logging.getLogger(__name__)

# Service names
SERVICE_LOG_TIME = "log_flight_time"
SERVICE_FIND_TUNNELS = "find_tunnels"
SERVICE_LIST_COUNTRIES = "list_countries"
SERVICE_REFRESH_DATA = "refresh_data"

# Service schemas
SERVICE_LOG_TIME_SCHEMA = vol.Schema(
    {
        vol.Required("tunnel_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1200)),
        vol.Required("time"): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
        vol.Optional("comment", default=""): cv.string,
        vol.Optional("entry_date"): cv.datetime,
        vol.Optional("username"): cv.string,  # Added username parameter
    }
)

# For the find_tunnels service, use a more permissive schema
SERVICE_FIND_TUNNELS_SCHEMA = vol.Schema(
    {
        vol.Optional("search_term"): cv.string,
        vol.Optional("country"): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

# Simple schema for list_countries service (no parameters needed)
SERVICE_LIST_COUNTRIES_SCHEMA = vol.Schema({})

# Simple schema for refresh_data service (no parameters needed)
SERVICE_REFRESH_DATA_SCHEMA = vol.Schema({})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the Tunnelflight integration."""

    _LOGGER.info(f"Setting up Tunnelflight services in domain: {DOMAIN}")

    # Dictionary to store API instances
    api_instances = {}

    # Cache for tunnels data
    tunnels_cache = {}

    async def log_flight_time(call: ServiceCall) -> None:
        """Service to add a new flight time entry to the Tunnelflight logbook."""
        tunnel_id = call.data["tunnel_id"]
        time_minutes = call.data["time"]
        comment = call.data.get("comment", "")

        # Use current timestamp if entry_date not provided
        entry_date = call.data.get("entry_date", datetime.now())

        # Get requested username if specified
        requested_username = call.data.get("username")
        _LOGGER.debug(
            f"log_flight_time called with requested_username: {requested_username}"
        )

        # Count number of configured entries
        entry_count = len(hass.data.get(DOMAIN, {}))
        _LOGGER.debug(f"Found {entry_count} configured entries")

        # Initialize the API to use
        api = None
        selected_entry_id = None
        selected_username = None

        # If multiple entries are configured but no username is specified, fail
        if entry_count > 1 and not requested_username:
            _LOGGER.error(
                "Multiple Tunnelflight integrations configured but no username specified"
            )
            service_data = {
                "title": "Tunnelflight Log Time Failed",
                "message": "Multiple Tunnelflight accounts are configured. You must specify a username parameter to indicate which account to log time for.",
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )
            return

        # If a specific username is requested, find the matching API instance
        if requested_username:
            _LOGGER.debug(
                f"Looking for entry matching requested_username: {requested_username}"
            )
            requested_username_norm = requested_username.lower().strip()

            for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
                config_entry = hass.config_entries.async_get_entry(entry_id)
                if config_entry:
                    entry_username = config_entry.data.get("username", "")
                    entry_username_norm = entry_username.lower().strip()

                    _LOGGER.debug(
                        f"Checking entry with username: {entry_username} (normalized: {entry_username_norm})"
                    )

                    # More flexible comparison - either exact match or username starts with
                    if (
                        entry_username_norm == requested_username_norm
                        or entry_username_norm.startswith(requested_username_norm)
                        or requested_username_norm.startswith(entry_username_norm)
                    ):
                        selected_entry_id = entry_id
                        selected_username = entry_username

                        # Get or create API instance using the credentials from this specific entry
                        if entry_id not in api_instances:
                            session = async_get_clientsession(hass)
                            api_instances[entry_id] = TunnelflightApi(
                                config_entry.data["username"],
                                config_entry.data["password"],
                                session,
                            )
                        api = api_instances[entry_id]
                        _LOGGER.debug(
                            f"Found matching account for username: {requested_username} -> {entry_username}"
                        )
                        break

            # If requested username wasn't found, fail
            if not api:
                _LOGGER.error(
                    f"Requested username '{requested_username}' not found in configured accounts"
                )
                service_data = {
                    "title": "Tunnelflight Log Time Failed",
                    "message": f"The specified username '{requested_username}' was not found in your configured Tunnelflight accounts.",
                }
                await hass.services.async_call(
                    "persistent_notification", "create", service_data
                )
                return
        else:
            # If only one entry is configured, use it
            if entry_count == 1:
                _LOGGER.debug("Using the only configured account")
                for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
                    config_entry = hass.config_entries.async_get_entry(entry_id)
                    if config_entry:
                        selected_entry_id = entry_id
                        selected_username = config_entry.data.get("username")
                        # Get or create API instance
                        if entry_id not in api_instances:
                            session = async_get_clientsession(hass)
                            api_instances[entry_id] = TunnelflightApi(
                                config_entry.data["username"],
                                config_entry.data["password"],
                                session,
                            )
                        api = api_instances[entry_id]
                        _LOGGER.debug(
                            f"Using the only configured account: {selected_username}"
                        )
                        break

        if not api:
            _LOGGER.error(
                "No valid API instance available. Make sure you've configured the integration."
            )
            service_data = {
                "title": "Tunnelflight Log Time Failed",
                "message": f"No valid account found. Please check your configuration.{' Username: ' + requested_username if requested_username else ''}",
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )
            return

        try:
            _LOGGER.debug(
                f"Attempting to log {time_minutes} minutes at tunnel {tunnel_id} with comment: {comment} for user {selected_username}"
            )

            # Use the new API method to log flight time
            response = await api.log_flight_time(
                tunnel_id, time_minutes, comment, entry_date
            )

            if response:
                _LOGGER.info(
                    f"Successfully logged {time_minutes} minutes at tunnel {tunnel_id} for {selected_username}"
                )

                # Update the state of the main sensor with the new total time
                if selected_entry_id:
                    state_obj = hass.states.get(f"sensor.{DOMAIN}_{selected_username}")
                    if state_obj:
                        # Calculate new total time
                        try:
                            old_attrs = dict(state_obj.attributes)
                            if "last_flight" in old_attrs:
                                old_attrs["last_flight"] = (
                                    entry_date.strftime("%Y-%m-%d")
                                    if isinstance(entry_date, datetime)
                                    else datetime.fromtimestamp(entry_date).strftime(
                                        "%Y-%m-%d"
                                    )
                                )

                            if "total_flight_time" in old_attrs:
                                # Try to extract current hours and minutes
                                current_time = old_attrs.get(
                                    "total_flight_time", "0:00"
                                )
                                try:
                                    if ":" in current_time:
                                        hours, minutes = current_time.split(":")
                                        current_minutes = int(hours) * 60 + int(minutes)
                                    else:
                                        current_minutes = 0
                                except (ValueError, TypeError):
                                    current_minutes = 0

                                # Add new time
                                new_total_minutes = current_minutes + time_minutes
                                new_hours = new_total_minutes // 60
                                new_minutes = new_total_minutes % 60
                                old_attrs["total_flight_time"] = (
                                    f"{new_hours}:{new_minutes:02d}"
                                )

                            # Update the state
                            hass.states.async_set(
                                f"sensor.{DOMAIN}_{selected_username}",
                                state_obj.state,
                                old_attrs,
                            )
                        except Exception as e:
                            _LOGGER.warning(f"Error updating sensor state: {e}")

                # Force refresh coordinator data
                coordinator = get_coordinator(selected_entry_id)
                if coordinator:
                    await coordinator.async_refresh()
                    _LOGGER.debug(
                        f"Refreshed data for {selected_username} after logging time"
                    )

                # Show success notification
                service_data = {
                    "title": "Flight Time Logged Successfully",
                    "message": f"Logged {time_minutes} minutes at tunnel {tunnel_id} for user {selected_username}",
                }
                await hass.services.async_call(
                    "persistent_notification", "create", service_data
                )
            else:
                _LOGGER.error(f"Failed to log time for {selected_username}")
                service_data = {
                    "title": "Flight Time Logging Failed",
                    "message": f"Error for {selected_username}: Unknown error",
                }
                await hass.services.async_call(
                    "persistent_notification", "create", service_data
                )

        except Exception as e:
            _LOGGER.error(f"Error logging flight time for {selected_username}: {e}")
            service_data = {
                "title": "Flight Time Logging Failed",
                "message": f"Error for {selected_username}: {e}",
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )

    async def find_tunnels(call: ServiceCall) -> None:
        """Find wind tunnels matching a search term or country."""
        search_term = call.data.get("search_term", "").lower()
        country = call.data.get("country", "").lower()

        # For non-user-specific operations like finding tunnels,
        # it doesn't matter which account we use - just pick the first available one
        api = None
        api_username = None

        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            config_entry = hass.config_entries.async_get_entry(entry_id)
            if config_entry:
                username = config_entry.data.get("username", "")
                # Get or create API instance
                if entry_id not in api_instances:
                    session = async_get_clientsession(hass)
                    api_instances[entry_id] = TunnelflightApi(
                        config_entry.data["username"],
                        config_entry.data["password"],
                        session,
                    )
                api = api_instances[entry_id]
                api_username = username
                _LOGGER.debug(
                    f"Using account {username} to find tunnels (any account works for this operation)"
                )
                break

        if not api:
            _LOGGER.error("No API instances available")
            service_data = {
                "title": "Tunnelflight Error",
                "message": "No configured accounts found. Please set up the integration first.",
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )
            return

        # Refresh the tunnels cache if empty
        if not tunnels_cache:
            tunnels = await api.get_tunnels()
            if tunnels:
                tunnels_cache.update(tunnels)
                _LOGGER.debug(
                    f"Updated tunnels cache using {api_username}'s API connection"
                )

        if not tunnels_cache:
            _LOGGER.error("Failed to fetch tunnels list")
            service_data = {
                "title": "Tunnelflight Error",
                "message": "Failed to fetch tunnels list. Please check logs for details.",
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )
            return

        # Filter tunnels based on search criteria
        matching_tunnels = []
        for tunnel_id, tunnel_data in tunnels_cache.items():
            title = tunnel_data.get("title", "").lower()
            tunnel_country = tunnel_data.get("country", "").lower()
            city = tunnel_data.get("address_city", "").lower()

            # Check if tunnel matches search criteria
            matches_search = (
                not search_term or search_term in title or search_term in city
            )
            matches_country = not country or country in tunnel_country

            if matches_search and matches_country:
                matching_tunnels.append(
                    {
                        "id": tunnel_id,
                        "title": tunnel_data.get("title"),
                        "country": tunnel_data.get("country"),
                        "city": tunnel_data.get("address_city"),
                        "size": tunnel_data.get("size"),
                        "manufacturer": tunnel_data.get("manufacturer"),
                        "status": tunnel_data.get("status"),
                    }
                )

        # Sort results by title
        matching_tunnels.sort(key=lambda x: x["title"])

        # Display results as a persistent notification
        if matching_tunnels:
            message = "## Matching Tunnels\n\n"
            message += "| ID | Name | Location | Size |\n"
            message += "|---|------|----------|------|\n"

            for tunnel in matching_tunnels[:20]:  # Limit to 20 results
                location = f"{tunnel['city']}, {tunnel['country']}".strip(", ")
                message += f"| {tunnel['id']} | {tunnel['title']} | {location} | {tunnel['size']} |\n"

            if len(matching_tunnels) > 20:
                message += f"\n_...and {len(matching_tunnels) - 20} more matches. Refine your search to see more specific results._"

            service_data = {
                "title": f"Found {len(matching_tunnels)} matching tunnels",
                "message": message,
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )
            _LOGGER.info(f"Found {len(matching_tunnels)} tunnels matching criteria")
        else:
            service_data = {
                "title": "No matching tunnels found",
                "message": f"No tunnels found matching your search criteria.\n\nSearch term: {search_term or 'None'}\nCountry: {country or 'None'}\n\nTip: Use the 'tunnelflight.list_countries' service to see all available countries.",
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )
            _LOGGER.info("No tunnels found matching criteria")

    async def list_countries(call: ServiceCall) -> None:
        """List all countries that have wind tunnels."""
        # For non-user-specific operations like listing countries,
        # it doesn't matter which account we use - just pick the first available one
        api = None
        api_username = None

        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            config_entry = hass.config_entries.async_get_entry(entry_id)
            if config_entry:
                username = config_entry.data.get("username", "")
                # Get or create API instance
                if entry_id not in api_instances:
                    session = async_get_clientsession(hass)
                    api_instances[entry_id] = TunnelflightApi(
                        config_entry.data["username"],
                        config_entry.data["password"],
                        session,
                    )
                api = api_instances[entry_id]
                api_username = username
                _LOGGER.debug(
                    f"Using account {username} to list countries (any account works for this operation)"
                )
                break

        if not api:
            _LOGGER.error("No API instances available")
            service_data = {
                "title": "Tunnelflight Error",
                "message": "No configured accounts found. Please set up the integration first.",
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )
            return

        # Refresh the tunnels cache if empty
        if not tunnels_cache:
            tunnels = await api.get_tunnels()
            if tunnels:
                tunnels_cache.update(tunnels)

        if not tunnels_cache:
            _LOGGER.error("Failed to fetch tunnels list")
            service_data = {
                "title": "Tunnelflight Error",
                "message": "Failed to fetch tunnels list. Please check logs for details.",
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )
            return

        # Extract unique countries from the database
        countries = sorted(
            list(
                set(
                    tunnel_data.get("country", "Unknown")
                    for tunnel_data in tunnels_cache.values()
                    if tunnel_data.get("country")
                )
            )
        )

        # Display countries as a persistent notification
        message = "## Available Countries\n\n"
        for country in countries:
            message += f"- {country}\n"

        service_data = {
            "title": f"Found {len(countries)} countries with tunnels",
            "message": message,
        }
        await hass.services.async_call(
            "persistent_notification", "create", service_data
        )
        _LOGGER.info(f"Listed {len(countries)} countries with tunnels")

    async def refresh_data(call: ServiceCall) -> None:
        """Force an immediate refresh of all configured accounts."""
        _LOGGER.info("Manually refreshing Tunnelflight data")

        success_count = 0
        error_count = 0
        not_modified_count = 0

        # Loop through all entries and refresh their data - using the APPROPRIATE API instance for each user
        for entry_id in hass.data.get(DOMAIN, {}):
            try:
                # Get the coordinator for this entry
                coordinator = get_coordinator(entry_id)
                config_entry = hass.config_entries.async_get_entry(entry_id)
                username = (
                    config_entry.data.get("username", "unknown")
                    if config_entry
                    else "unknown"
                )

                # Make sure we're using the right API instance for this user
                if coordinator and hasattr(coordinator, "async_refresh"):
                    _LOGGER.debug(f"Refreshing data for {username} (entry: {entry_id})")

                    # Ensure we're using the correct API instance for this user
                    if coordinator.api._username.lower() != username.lower():
                        _LOGGER.warning(
                            f"Coordinator for {username} has incorrect API instance. Recreating API."
                        )
                        if config_entry:
                            session = async_get_clientsession(hass)
                            coordinator.api = TunnelflightApi(
                                config_entry.data["username"],
                                config_entry.data["password"],
                                session,
                            )

                    # Track the current data hash to detect if it actually changed
                    old_data_hash = (
                        hash(str(coordinator.data)) if coordinator.data else None
                    )

                    # Perform the refresh
                    await coordinator.async_refresh()

                    # Check if data actually changed
                    new_data_hash = (
                        hash(str(coordinator.data)) if coordinator.data else None
                    )

                    if old_data_hash == new_data_hash and old_data_hash is not None:
                        _LOGGER.info(
                            f"Data unchanged for {username} (likely due to ETag/304 response)"
                        )
                        not_modified_count += 1
                    else:
                        _LOGGER.info(f"Successfully refreshed data for {username}")
                        success_count += 1
                else:
                    _LOGGER.error(f"No coordinator found for entry {entry_id}")
                    error_count += 1
            except Exception as e:
                _LOGGER.error(f"Error refreshing data for entry {entry_id}: {e}")
                error_count += 1

        # Show a notification with the results
        if success_count > 0 or not_modified_count > 0:
            message = ""
            if success_count > 0:
                message += (
                    f"Successfully refreshed data for {success_count} account(s). "
                )
            if not_modified_count > 0:
                message += f"Data unchanged (304 Not Modified) for {not_modified_count} account(s). "
            if error_count > 0:
                message += f"Failed to refresh {error_count} account(s)."

            service_data = {
                "title": "Tunnelflight Data Refreshed",
                "message": message.strip(),
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )
        else:
            service_data = {
                "title": "Tunnelflight Data Refresh Failed",
                "message": f"Failed to refresh data for {error_count} account(s). Check logs for details.",
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )

    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_LOG_TIME, log_flight_time, schema=SERVICE_LOG_TIME_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_FIND_TUNNELS, find_tunnels, schema=SERVICE_FIND_TUNNELS_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_COUNTRIES,
        list_countries,
        schema=SERVICE_LIST_COUNTRIES_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH_DATA, refresh_data, schema=SERVICE_REFRESH_DATA_SCHEMA
    )

    # Log that services have been registered
    _LOGGER.info(
        f"Successfully registered Tunnelflight services: {SERVICE_LOG_TIME}, {SERVICE_FIND_TUNNELS}, {SERVICE_LIST_COUNTRIES}, {SERVICE_REFRESH_DATA}"
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Tunnelflight services."""
    if hass.services.has_service(DOMAIN, SERVICE_LOG_TIME):
        hass.services.async_remove(DOMAIN, SERVICE_LOG_TIME)
    if hass.services.has_service(DOMAIN, SERVICE_FIND_TUNNELS):
        hass.services.async_remove(DOMAIN, SERVICE_FIND_TUNNELS)
    if hass.services.has_service(DOMAIN, SERVICE_LIST_COUNTRIES):
        hass.services.async_remove(DOMAIN, SERVICE_LIST_COUNTRIES)
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH_DATA):
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH_DATA)
