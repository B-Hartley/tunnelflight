import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Store coordinators for each entry_id
COORDINATORS = {}


def register_coordinator(entry_id, coordinator):
    """Register a coordinator for use by services."""
    COORDINATORS[entry_id] = coordinator
    _LOGGER.debug("Registered coordinator for entry_id: %s", entry_id)


def get_coordinator(entry_id):
    """Get the coordinator for an entry_id."""
    return COORDINATORS.get(entry_id)
