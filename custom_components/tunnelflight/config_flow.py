import logging
import voluptuous as vol
import aiohttp
import json

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_NAME
from homeassistant.helpers import aiohttp_client

from .const import DOMAIN, DEFAULT_NAME
from .api import TunnelflightApi

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


async def validate_auth(username, password, hass):
    """Validate the user credentials using the API class."""
    _LOGGER.debug("Validating credentials for username: %s", username)
    session = aiohttp_client.async_get_clientsession(hass)

    # Create an instance of our API class
    api = TunnelflightApi(username, password, session)

    # Attempt to login
    login_success = await api.login()

    if not login_success:
        _LOGGER.error("Login failed for username: %s", username)
        return False

    # Try to fetch user data to further verify the account
    user_data = await api.get_user_data()

    if not user_data:
        _LOGGER.error("Could not fetch user data for username: %s", username)
        # If login succeeded but we couldn't get user data, still consider it valid
        # as there might be API changes or temporary issues
        return login_success

    _LOGGER.debug("Successfully validated credentials for username: %s", username)
    return True


class TunnelflightConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IBA Tunnelflight."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]

            # Check if we already have this account configured
            await self.async_set_unique_id(f"tunnelflight_{username}")
            self._abort_if_unique_id_configured()

            # Validate the credentials
            valid = await validate_auth(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD], self.hass
            )

            if valid:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data=user_input,
                )
            else:
                errors["base"] = "auth"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )
