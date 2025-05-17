import logging
import voluptuous as vol
from datetime import datetime
from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .api import TunnelflightApi

_LOGGER = logging.getLogger(__name__)

# Service names
SERVICE_LOG_TIME = "log_flight_time"
SERVICE_FIND_TUNNELS = "find_tunnels"

# Service schemas
SERVICE_LOG_TIME_SCHEMA = vol.Schema(
    {
        vol.Required("tunnel_id"): cv.positive_int,
        vol.Required("time"): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
        vol.Optional("comment", default=""): cv.string,
        vol.Optional("entry_date"): cv.datetime,
    }
)

SERVICE_FIND_TUNNELS_SCHEMA = vol.Schema(
    {
        vol.Optional("search_term"): cv.string,
        vol.Optional("country"): cv.string,
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for the Tunnelflight integration."""

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

        # Get API instance for first config entry
        api = None
        for entry_id, entry_api in api_instances.items():
            api = entry_api
            break

        if not api:
            _LOGGER.error("No API instances available")
            return

        # Get tunnel name
        tunnel_name = await get_tunnel_name(tunnel_id, api)

        try:
            _LOGGER.debug(
                f"Attempting to log {time_minutes} minutes at {tunnel_name} with comment: {comment}"
            )

            # Ensure user is logged in
            if not api._logged_in:
                await api.login()
                if not api._logged_in:
                    _LOGGER.error("Failed to log time: Login failed")
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
                                f"Successfully logged {time_minutes} minutes at {tunnel_name}"
                            )

                            # Update the state of the main sensor with the new total time
                            for entry_id in hass.data.get(DOMAIN, {}):
                                state_obj = hass.states.get(f"sensor.{DOMAIN}")
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
                                            f"sensor.{DOMAIN}",
                                            state_obj.state,
                                            old_attrs,
                                        )
                                    except Exception as e:
                                        _LOGGER.warning(
                                            f"Error updating sensor state: {e}"
                                        )
                        else:
                            _LOGGER.error(
                                f"Failed to log time: {response_data.get('message', 'Unknown error')}"
                            )
                    except Exception as e:
                        _LOGGER.error(f"Error parsing log time response: {e}")
                        try:
                            # Log the raw response text
                            content = await response.text()
                            _LOGGER.debug(f"Raw response: {content[:200]}")

                            # If response contains "success" somewhere, consider it a success despite JSON parsing error
                            if "success" in content.lower() or "ok" in content.lower():
                                _LOGGER.info(
                                    f"Assuming success based on response text for {time_minutes} minutes at {tunnel_name}"
                                )
                                return
                        except:
                            pass
                else:
                    _LOGGER.error(f"Failed to log time: HTTP status {response.status}")
                    try:
                        # Try to get the error message from the response
                        content = await response.text()
                        _LOGGER.debug(f"Error response: {content[:200]}")
                    except:
                        pass

        except Exception as e:
            _LOGGER.error(f"Error logging flight time: {e}")

    async def find_tunnels(call: ServiceCall) -> None:
        """Service to find tunnels by name or country."""
        search_term = call.data.get("search_term", "").lower()
        country = call.data.get("country", "").lower()
        list_countries = call.data.get("list_countries", False)

        # Get API instance for first config entry
        api = None
        for entry_id, entry_api in api_instances.items():
            api = entry_api
            break

        if not api:
            _LOGGER.error("No API instances available")
            return

        # Ensure tunnels are loaded in cache
        if not tunnels_cache:
            tunnels_cache.update(await fetch_tunnels(api))

        if not tunnels_cache:
            _LOGGER.error("Failed to fetch tunnels list")
            return

        # If list_countries is True, display all available countries
        if list_countries:
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
                "message": f"No tunnels found matching your search criteria.\n\nSearch term: {search_term or 'None'}\nCountry: {country or 'None'}\n\nTip: Use the 'list_countries: true' parameter to see all available countries.",
            }
            await hass.services.async_call(
                "persistent_notification", "create", service_data
            )
            _LOGGER.info("No tunnels found matching criteria")

    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_LOG_TIME, log_flight_time, schema=SERVICE_LOG_TIME_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_FIND_TUNNELS, find_tunnels, schema=SERVICE_FIND_TUNNELS_SCHEMA
    )

    # Store API instances
    for entry_id in hass.data.get(DOMAIN, {}):
        config_entry = hass.config_entries.async_get_entry(entry_id)
        if config_entry:
            username = config_entry.data["username"]
            password = config_entry.data["password"]

            # Create a new API instance or reuse existing one
            api = TunnelflightApi(username, password, None)
            api_instances[entry_id] = api
            _LOGGER.debug(f"Added API instance for {username} with entry_id {entry_id}")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Tunnelflight services."""
    if hass.services.has_service(DOMAIN, SERVICE_LOG_TIME):
        hass.services.async_remove(DOMAIN, SERVICE_LOG_TIME)
    if hass.services.has_service(DOMAIN, SERVICE_FIND_TUNNELS):
        hass.services.async_remove(DOMAIN, SERVICE_FIND_TUNNELS)
