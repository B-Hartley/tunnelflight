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

    async def fetch_tunnels(api):
        """Fetch the list of tunnels from the API."""
        try:
            # Ensure user is logged in
            if not api._logged_in:
                await api.login()
                if not api._logged_in:
                    _LOGGER.error("Failed to fetch tunnels: Login failed")
                    return {}

            # Fetch tunnels list
            async with api._session.get(
                "https://www.tunnelflight.com/account/logbook/tunnels/",
                headers=api._ajax_headers,
            ) as response:
                # Accept both 200 OK and 201 Created as valid responses
                if response.status in (200, 201):
                    try:
                        tunnels_data = await response.json()
                        _LOGGER.debug(
                            f"Received tunnels data, raw length: {len(str(tunnels_data))}"
                        )

                        if not isinstance(tunnels_data, list):
                            _LOGGER.error(
                                f"Expected a list of tunnels, got: {type(tunnels_data)}"
                            )
                            # Try to extract useful information from the response
                            content = await response.text()
                            _LOGGER.debug(
                                f"Raw response content (first 200 chars): {content[:200]}"
                            )
                            return {}

                        # Convert to a more usable format
                        tunnels = {}
                        for tunnel in tunnels_data:
                            try:
                                tunnel_id = int(tunnel.get("entry_id", 0))
                                if tunnel_id > 0:
                                    tunnels[tunnel_id] = {
                                        "title": tunnel.get("title", "Unknown"),
                                        "country": tunnel.get("country", "Unknown"),
                                        "size": tunnel.get("size", "Unknown"),
                                        "manufacturer": tunnel.get(
                                            "manufacturer", "Unknown"
                                        ),
                                        "address": tunnel.get("address", ""),
                                        "address_city": tunnel.get("address_city", ""),
                                        "status": tunnel.get("status", "Unknown"),
                                    }
                            except (ValueError, TypeError) as e:
                                _LOGGER.warning(f"Error processing tunnel data: {e}")

                        _LOGGER.debug(f"Fetched {len(tunnels)} tunnels from API")
                        return tunnels
                    except Exception as e:
                        _LOGGER.error(f"Error parsing tunnels response: {e}")
                        try:
                            # Log the raw text to help debug
                            content = await response.text()
                            _LOGGER.debug(
                                f"Response content (first 200 chars): {content[:200]}"
                            )
                        except:
                            pass
                        return {}
                else:
                    _LOGGER.error(
                        f"Failed to fetch tunnels: HTTP status {response.status}"
                    )
                    try:
                        # Try to get any error message from the response
                        content = await response.text()
                        _LOGGER.debug(f"Error response content: {content[:200]}")
                    except:
                        pass
                    return {}
        except Exception as e:
            _LOGGER.error(f"Error fetching tunnels: {e}")
            return {}

    async def get_tunnel_name(tunnel_id, api):
        """Get tunnel name from the API or cache."""
        # Ensure tunnels are loaded in cache
        if not tunnels_cache and api:
            tunnels_cache.update(await fetch_tunnels(api))

        if tunnel_id in tunnels_cache:
            return tunnels_cache[tunnel_id]["title"]

        # Fallback to common tunnels if not found
        fallback_tunnels = {
            225: "Milton Keynes iFLY",
            242: "Manchester iFLY",
            248: "Basingstoke iFLY",
            264: "Downunder iFLY",
            228: "SF Bay iFLY",
            230: "Paraclete XP SkyVenture",
            249: "InFlight Dubai",
            250: "Toronto - Oakville iFLY",
        }
        return fallback_tunnels.get(tunnel_id, f"Tunnel ID {tunnel_id}")

    async def log_flight_time(call: ServiceCall) -> None:
        """Service to add a new flight time entry to the Tunnelflight logbook."""
        tunnel_id = call.data["tunnel_id"]
        time_minutes = call.data["time"]
        comment = call.data.get("comment", "")

        # Use current timestamp if entry_date not provided
        if "entry_date" in call.data:
            entry_date = int(datetime.timestamp(call.data["entry_date"]))
        else:
            entry_date = int(datetime.now().timestamp())

        # Get requested username if specified
        requested_username = call.data.get("username")
        _LOGGER.warning(
            f"log_flight_time called with requested_username: {requested_username}"
        )

        # Count number of configured entries
        entry_count = len(hass.data.get(DOMAIN, {}))
        _LOGGER.warning(f"Found {entry_count} configured entries")

        # Initialize the API to use
        api = None
        selected_entry_id = None
        selected_username = None  # Add this to track which username we actually use

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
            _LOGGER.warning(
                f"Looking for entry matching requested_username: {requested_username}"
            )
            requested_username_norm = requested_username.lower().strip()

            for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
                config_entry = hass.config_entries.async_get_entry(entry_id)
                if config_entry:
                    entry_username = config_entry.data.get("username", "")
                    entry_username_norm = entry_username.lower().strip()

                    _LOGGER.warning(
                        f"Checking entry with username: {entry_username} (normalized: {entry_username_norm})"
                    )

                    # More flexible comparison - either exact match or username starts with
                    if (
                        entry_username_norm == requested_username_norm
                        or entry_username_norm.startswith(requested_username_norm)
                        or requested_username_norm.startswith(entry_username_norm)
                    ):
                        selected_entry_id = entry_id
                        selected_username = (
                            entry_username  # Store the actual username from config
                        )

                        # Get or create API instance using the credentials from this specific entry
                        if entry_id not in api_instances:
                            session = async_get_clientsession(hass)
                            api_instances[entry_id] = TunnelflightApi(
                                config_entry.data["username"],
                                config_entry.data["password"],
                                session,
                            )
                        api = api_instances[entry_id]
                        _LOGGER.warning(
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
                _LOGGER.warning("Using the only configured account")
                for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
                    config_entry = hass.config_entries.async_get_entry(entry_id)
                    if config_entry:
                        selected_entry_id = entry_id
                        selected_username = config_entry.data.get(
                            "username"
                        )  # Store the actual username
                        # Get or create API instance
                        if entry_id not in api_instances:
                            session = async_get_clientsession(hass)
                            api_instances[entry_id] = TunnelflightApi(
                                config_entry.data["username"],
                                config_entry.data["password"],
                                session,
                            )
                        api = api_instances[entry_id]
                        _LOGGER.warning(
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

        # Get tunnel name - make sure we're using the same API instance
        tunnel_name = await get_tunnel_name(tunnel_id, api)

        try:
            _LOGGER.debug(
                f"Attempting to log {time_minutes} minutes at {tunnel_name} with comment: {comment} for user {selected_username}"
            )

            # Ensure user is logged in - CRITICAL to ensure we're using the correct account's session
            # First check if already logged in
            if not api._logged_in:
                login_success = await api.login()
                if not login_success:
                    _LOGGER.error(
                        f"Failed to log time: Login failed for user {selected_username}"
                    )
                    service_data = {
                        "title": "Tunnelflight Log Time Failed",
                        "message": f"Login failed for {selected_username}. Please check your credentials.",
                    }
                    await hass.services.async_call(
                        "persistent_notification", "create", service_data
                    )
                    return

            # Force session renewal to ensure we're using the most current session
            # This is important especially if multiple accounts are configured
            await api._clear_session()
            login_success = await api.login()
            if not login_success:
                _LOGGER.error(f"Failed to renew session for user {selected_username}")
                service_data = {
                    "title": "Tunnelflight Log Time Failed",
                    "message": f"Failed to establish a fresh session for {selected_username}.",
                }
                await hass.services.async_call(
                    "persistent_notification", "create", service_data
                )
                return

            # Log current session state
            _LOGGER.debug(
                f"Using API instance with username {api._username} and logged_in={api._logged_in}"
            )

            # Confirm session validity before proceeding
            # Try to fetch something simple to verify session
            member_check = await api._fetch_api_endpoint(
                "https://www.tunnelflight.com/user/module-type/flyer-card/"
            )
            if not member_check or not member_check.get("member_id"):
                _LOGGER.error(
                    f"Session verification failed for {selected_username} - could not fetch member data"
                )
                service_data = {
                    "title": "Tunnelflight Log Time Failed",
                    "message": f"Session verification failed for {selected_username}. Please try again later.",
                }
                await hass.services.async_call(
                    "persistent_notification", "create", service_data
                )
                return

            # Prepare log entry data
            log_data = {
                "entry_id": "",  # Empty for new entries
                "status": "open",
                "entry_date": entry_date,
                "tunnel": str(tunnel_id),
                "tunnel_name": tunnel_name,
                "comment": comment,
                "time": str(time_minutes),
            }

            # Post the logbook entry
            _LOGGER.warning(
                f"Sending log time request for {selected_username} to {api._username}'s session"
            )
            async with api._session.post(
                "https://www.tunnelflight.com/account/logbook/member/time/",
                json=log_data,
                headers=api._ajax_headers,
            ) as response:
                # Accept both 200 OK and 201 Created as valid responses
                if response.status in (200, 201):
                    try:
                        response_data = await response.json()
                        _LOGGER.debug(f"Received log time response: {response_data}")

                        # Check for success message (could be "Ok" or other variations)
                        if isinstance(response_data, dict) and (
                            response_data.get("message") == "Ok"
                            or "success"
                            in str(response_data.get("message", "")).lower()
                        ):
                            _LOGGER.info(
                                f"Successfully logged {time_minutes} minutes at {tunnel_name} for {selected_username}"
                            )

                            # Update the state of the main sensor with the new total time
                            if selected_entry_id:
                                state_obj = hass.states.get(
                                    f"sensor.{DOMAIN}_{selected_username}"
                                )
                                if state_obj:
                                    # Calculate new total time
                                    try:
                                        old_attrs = dict(state_obj.attributes)
                                        if "last_flight" in old_attrs:
                                            old_attrs["last_flight"] = (
                                                datetime.fromtimestamp(
                                                    entry_date
                                                ).strftime("%Y-%m-%d")
                                            )

                                        if "total_flight_time" in old_attrs:
                                            # Try to extract current hours and minutes
                                            current_time = old_attrs.get(
                                                "total_flight_time", "0:00"
                                            )
                                            try:
                                                if ":" in current_time:
                                                    hours, minutes = current_time.split(
                                                        ":"
                                                    )
                                                    current_minutes = int(
                                                        hours
                                                    ) * 60 + int(minutes)
                                                else:
                                                    current_minutes = 0
                                            except (ValueError, TypeError):
                                                current_minutes = 0

                                            # Add new time
                                            new_total_minutes = (
                                                current_minutes + time_minutes
                                            )
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
                                        _LOGGER.warning(
                                            f"Error updating sensor state: {e}"
                                        )

                            # Force refresh coordinator data
                            coordinator = get_coordinator(selected_entry_id)
                            if coordinator:
                                await coordinator.async_refresh()
                                _LOGGER.debug(
                                    f"Refreshed data for {selected_username} after logging time"
                                )

                            # Show success notification - only use selected_username for consistency
                            service_data = {
                                "title": "Flight Time Logged Successfully",
                                "message": f"Logged {time_minutes} minutes at {tunnel_name} for user {selected_username}",
                            }
                            await hass.services.async_call(
                                "persistent_notification", "create", service_data
                            )
                        else:
                            _LOGGER.error(
                                f"Failed to log time for {selected_username}: {response_data.get('message', 'Unknown error')}"
                            )
                            service_data = {
                                "title": "Flight Time Logging Failed",
                                "message": f"Error for {selected_username}: {response_data.get('message', 'Unknown error')}",
                            }
                            await hass.services.async_call(
                                "persistent_notification", "create", service_data
                            )
                    except Exception as e:
                        _LOGGER.error(
                            f"Error parsing log time response for {selected_username}: {e}"
                        )
                        try:
                            # Log the raw response text
                            content = await response.text()
                            _LOGGER.debug(f"Raw response: {content[:200]}")

                            # If response contains "success" somewhere, consider it a success despite JSON parsing error
                            if "success" in content.lower() or "ok" in content.lower():
                                _LOGGER.info(
                                    f"Assuming success based on response text for {time_minutes} minutes at {tunnel_name}"
                                )
                                service_data = {
                                    "title": "Flight Time Probably Logged",
                                    "message": f"Assuming success for {time_minutes} minutes at {tunnel_name} for {selected_username}",
                                }
                                await hass.services.async_call(
                                    "persistent_notification", "create", service_data
                                )
                                return
                        except:
                            pass

                        service_data = {
                            "title": "Flight Time Logging Failed",
                            "message": f"Error processing response for {selected_username}: {e}",
                        }
                        await hass.services.async_call(
                            "persistent_notification", "create", service_data
                        )
                else:
                    _LOGGER.error(
                        f"Failed to log time for {selected_username}: HTTP status {response.status}"
                    )
                    try:
                        # Try to get the error message from the response
                        content = await response.text()
                        _LOGGER.debug(f"Error response: {content[:200]}")
                        service_data = {
                            "title": "Flight Time Logging Failed",
                            "message": f"HTTP Error {response.status} for {selected_username}: {content[:200]}",
                        }
                        await hass.services.async_call(
                            "persistent_notification", "create", service_data
                        )
                    except:
                        service_data = {
                            "title": "Flight Time Logging Failed",
                            "message": f"HTTP Error {response.status} for {selected_username}",
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
        """Service to find tunnels by name or country."""
        search_term = call.data.get("search_term", "").lower()
        country = call.data.get("country", "").lower()

        # Get API instance - create only once
        api = None
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            config_entry = hass.config_entries.async_get_entry(entry_id)
            if config_entry:
                # Get or create API instance
                if entry_id not in api_instances:
                    session = async_get_clientsession(hass)
                    api_instances[entry_id] = TunnelflightApi(
                        config_entry.data["username"],
                        config_entry.data["password"],
                        session,
                    )
                api = api_instances[entry_id]
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

        # Ensure tunnels are loaded in cache
        if not tunnels_cache:
            tunnels_cache.update(await fetch_tunnels(api))

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
        """Service to list all countries with wind tunnels."""
        # Get API instance - create only once
        api = None
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            config_entry = hass.config_entries.async_get_entry(entry_id)
            if config_entry:
                # Get or create API instance
                if entry_id not in api_instances:
                    session = async_get_clientsession(hass)
                    api_instances[entry_id] = TunnelflightApi(
                        config_entry.data["username"],
                        config_entry.data["password"],
                        session,
                    )
                api = api_instances[entry_id]
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

        # Ensure tunnels are loaded in cache
        if not tunnels_cache:
            tunnels_cache.update(await fetch_tunnels(api))

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
        """Service to refresh data from the Tunnelflight API."""
        _LOGGER.info("Manually refreshing Tunnelflight data")

        success_count = 0
        error_count = 0

        # Loop through all API instances and refresh their data
        for entry_id in hass.data.get(DOMAIN, {}):
            try:
                # Get the coordinator for this entry
                coordinator = get_coordinator(entry_id)

                if coordinator and hasattr(coordinator, "async_refresh"):
                    await coordinator.async_refresh()
                    _LOGGER.debug(
                        f"Updated coordinator with fresh data for entry {entry_id}"
                    )
                    success_count += 1
                    _LOGGER.info(f"Successfully refreshed data for entry {entry_id}")
                else:
                    _LOGGER.error(f"No coordinator found for entry {entry_id}")
                    error_count += 1
            except Exception as e:
                _LOGGER.error(f"Error refreshing data for entry {entry_id}: {e}")
                error_count += 1

        # Show a notification with the results
        if success_count > 0:
            service_data = {
                "title": "Tunnelflight Data Refreshed",
                "message": f"Successfully refreshed data for {success_count} account(s)."
                f"{' Failed to refresh ' + str(error_count) + ' account(s).' if error_count > 0 else ''}",
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
    _LOGGER.warning(
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
