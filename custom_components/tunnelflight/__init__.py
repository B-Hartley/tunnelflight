import logging
from homeassistant.helpers import config_validation as cv
from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN
from .logbook_service import async_setup_services, async_unload_services
from .api import TunnelflightApi

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
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
            await async_setup_services(hass)
            SERVICES_REGISTERED = True
        except Exception:
            _LOGGER.exception(
                "Error setting up Tunnelflight services during async_setup"
            )

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IBA Tunnelflight from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Verify the remote service is ready before forwarding platform setup.
    # Home Assistant expects ConfigEntryNotReady to be raised here rather than
    # from a forwarded sensor platform.
    session = aiohttp_client.async_get_clientsession(hass)
    api = TunnelflightApi(
        entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], session
    )
    try:
        initial_data = await api.get_user_data()
    except Exception as err:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise ConfigEntryNotReady(
            f"Unable to connect to Tunnelflight: {err}"
        ) from err

    if not initial_data:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise ConfigEntryNotReady("Tunnelflight returned no user data")

    # Set up platforms only after the API has been confirmed available.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Only set up services once - use global flag to track
    global SERVICES_REGISTERED
    if not SERVICES_REGISTERED:
        try:
            await async_setup_services(hass)
            SERVICES_REGISTERED = True
        except Exception:
            _LOGGER.exception("Error setting up Tunnelflight services")

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
