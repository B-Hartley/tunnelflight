import logging
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .logbook_service import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

# Add binary_sensor to the platforms list
PLATFORMS = ["sensor", "binary_sensor"]

# Track whether services have been set up
SERVICES_REGISTERED = False


async def async_setup(hass, config):
    """Set up the IBA Tunnelflight component."""
    _LOGGER.debug("Setting up IBA Tunnelflight integration")
    # Initialize domain data
    hass.data.setdefault(DOMAIN, {})

    # Set up services if we have any entries
    global SERVICES_REGISTERED
    if DOMAIN in hass.config_entries.async_entries() and not SERVICES_REGISTERED:
        try:
            _LOGGER.warning("Setting up Tunnelflight services during async_setup")
            await async_setup_services(hass)
            SERVICES_REGISTERED = True
            _LOGGER.warning(
                "Tunnelflight services set up successfully during async_setup"
            )
        except Exception as e:
            _LOGGER.error(
                f"Error setting up Tunnelflight services during async_setup: {e}"
            )
            import traceback

            _LOGGER.error(f"Traceback: {traceback.format_exc()}")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IBA Tunnelflight from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Only set up services once - use global flag to track
    global SERVICES_REGISTERED
    if not SERVICES_REGISTERED:
        try:
            _LOGGER.warning(
                "Setting up Tunnelflight services - this should appear in your logs"
            )
            await async_setup_services(hass)
            SERVICES_REGISTERED = True
            _LOGGER.warning(
                "Tunnelflight services set up successfully - this should appear in your logs"
            )
        except Exception as e:
            _LOGGER.error(f"Error setting up Tunnelflight services: {e}")
            # Add this to get a full traceback
            import traceback

            _LOGGER.error(f"Traceback: {traceback.format_exc()}")

    _LOGGER.debug(
        f"Tunnelflight entry setup complete for {entry.data.get('username', 'unknown')}"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

        # Only unload services if this was the last entry AND services were registered
        global SERVICES_REGISTERED
        if not hass.data[DOMAIN] and SERVICES_REGISTERED:
            await async_unload_services(hass)
            SERVICES_REGISTERED = False

    return unload_ok
