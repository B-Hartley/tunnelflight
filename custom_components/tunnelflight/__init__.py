import logging
import asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .logbook_service import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

# Add binary_sensor to the platforms list
PLATFORMS = ["sensor", "binary_sensor"]


async def async_setup(hass, config):
    """Set up the IBA Tunnelflight component."""
    _LOGGER.debug("Setting up IBA Tunnelflight integration")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IBA Tunnelflight from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Use the non-deprecated async_forward_entry_setups method
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Set up services after first entry is loaded
    if len(hass.data[DOMAIN]) == 1:
        await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

        # Unload services if this was the last entry
        if not hass.data[DOMAIN]:
            await async_unload_services(hass)

    return unload_ok
