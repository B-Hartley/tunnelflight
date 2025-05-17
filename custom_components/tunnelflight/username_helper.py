import logging
import re
import json
from datetime import datetime

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def normalize_username(username):
    """Normalize username for comparison."""
    if not username:
        return ""
    # Remove whitespace and convert to lowercase
    normalized = username.lower().replace(" ", "")
    # Remove any special characters
    normalized = re.sub(r"[^a-z0-9]", "", normalized)
    return normalized


class TunnelflightSensorEntity(CoordinatorEntity, SensorEntity):
    """Base class for Tunnelflight sensor entities."""

    def __init__(self, coordinator, name, username, icon=None):
        """Initialize the entity."""
        super().__init__(coordinator)
        self._name = name
        self._username = username
        self._attr_icon = icon
        self._attr_unique_id = f"{DOMAIN}_{username}_{self.__class__.__name__}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, username)},
            "name": f"IBA Tunnelflight ({username})",
            "manufacturer": "International Bodyflight Association",
            "model": "Tunnelflight Account",
        }
        self._attr_has_entity_name = True

    @property
    def name(self):
        """Return the name of the entity."""
        return self._name

    @property
    def available(self):
        """Return True if data is available."""
        return (
            self.coordinator.last_update_success and self.coordinator.data is not None
        )

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            # Check if the data belongs to this user using more lenient comparison
            fetched_username = self.coordinator.data.get("screen_name", "")
            # Also check alternate fields that might contain the username
            if not fetched_username:
                fetched_username = self.coordinator.data.get("real_name", "")
            if not fetched_username:
                fetched_username = self.coordinator.data.get("user_real_name", "")

            # If we couldn't find any username in the fetched data, don't do the comparison
            if fetched_username:
                fetched_normalized = normalize_username(fetched_username)
                config_normalized = normalize_username(self._username)

                # Only log the warning if the normalized usernames have significant differences
                # The check now allows for "bruceh" to match "Bruce Hartley"
                if (
                    fetched_normalized
                    and config_normalized
                    and not fetched_normalized.startswith(config_normalized[:3])
                    and not config_normalized.startswith(fetched_normalized[:3])
                ):
                    _LOGGER.debug(
                        f"Username mismatch: Fetched '{fetched_username}' (normalized: '{fetched_normalized}') "
                        f"but expected '{self._username}' (normalized: '{config_normalized}')"
                    )

            self.async_write_ha_state()

    @property
    def device_info(self):
        """Return device information about this entity."""
        return self._attr_device_info
