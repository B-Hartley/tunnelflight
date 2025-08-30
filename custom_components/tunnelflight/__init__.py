import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TunnelflightApi
from .const import DOMAIN
from .logbook_service import async_setup_services, async_unload_services

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

    session = async_get_clientsession(hass)
    api = TunnelflightApi(
        entry.data.get("username"), entry.data.get("password"), session
    )

    try:
        login_success = await api.login()
    except Exception as err:
        raise ConfigEntryNotReady("Unable to connect to Tunnelflight API") from err

    if not login_success:
        raise ConfigEntryNotReady("Unable to authenticate with Tunnelflight API")

    hass.data[DOMAIN][entry.entry_id] = {"api": api, **entry.data}

    # Set up platforms
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
