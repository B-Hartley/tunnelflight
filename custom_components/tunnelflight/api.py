import re
import json
import logging
import aiohttp
import asyncio
from urllib.parse import urlencode
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)


class TunnelflightApi:
    """Class to handle API calls to the IBA Tunnelflight website."""

    def __init__(self, username, password, session=None):
        """Initialize the API."""
        self._username = username.lower()  # Store username in lowercase for consistency
        self._password = password
        self._session = session or aiohttp.ClientSession()
        self._token = None
        self._token_expiry = None
        self._etags = {}  # Store ETags for different endpoints

        # Minimal browser header that should be added to all requests
        self._browser_header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        }

    @property
    def _auth_header(self):
        """Return the authorization header with the token."""
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    @property
    def is_token_valid(self):
        """Check if the token is still valid."""
        if not self._token or not self._token_expiry:
            return False
        # Consider token valid if it expires in more than 5 minutes
        return datetime.now() + timedelta(minutes=5) < self._token_expiry

    async def login(self):
        """Login to the IBA website and get an authentication token."""
        _LOGGER.debug("Starting login process")

        # If we already have a valid token, no need to login again
        if self.is_token_valid:
            _LOGGER.debug("Using existing valid token")
            return True

        login_url = "https://www.tunnelflight.com/login"
        login_data = {
            "username": self._username,
            "password": self._password,
            "passcode": "",
            "enable2fa": False,
            "checkTwoFactor": True,
            "passcodeOption": "email",
        }

        try:
            async with self._session.post(
                login_url, json=login_data, headers=self._browser_header
            ) as response:
                _LOGGER.debug(f"Login response status: {response.status}")

                # Check status code first
                if response.status not in (200, 201, 202):
                    _LOGGER.error(f"Login failed with status {response.status}")
                    return False

                # Try to parse as JSON
                try:
                    content = await response.text()
                    response_data = json.loads(content)
                    
                    # Check if token exists in the response
                    if "token" in response_data:
                        self._token = response_data["token"]
                        # Set token expiry to 24 hours from now
                        self._token_expiry = datetime.now() + timedelta(hours=24)
                        _LOGGER.debug("Login successful - received token")
                        return True
                    elif response_data.get("message", "").lower().find("success") >= 0:
                        _LOGGER.warning(
                            "Login successful but no token found. Response message: "
                            f"{response_data.get('message')}"
                        )
                        # Even if the message says success but we don't have a token, consider it a failure
                        return False
                    else:
                        _LOGGER.error(
                            f"Login JSON indicates failure: {response_data.get('message', 'Unknown error')}"
                        )
                        return False
                except json.JSONDecodeError:
                    _LOGGER.error("Response is not valid JSON")
                    return False
        except Exception as e:
            _LOGGER.error(f"Error during login request: {e}")
            return False

    async def _fetch_api_endpoint(self, endpoint, use_etag=True):
        """Fetch data from an API endpoint with ETag support."""
        # Ensure we have a valid token
        if not self.is_token_valid:
            _LOGGER.debug("Token invalid or missing, attempting login")
            success = await self.login()
            if not success:
                _LOGGER.error(f"Login failed, cannot fetch data from {endpoint}")
                return None

        # Prepare request headers
        headers = {**self._browser_header, **self._auth_header}

        # Add If-None-Match header if we have an ETag for this endpoint and use_etag is True
        if use_etag and endpoint in self._etags:
            headers["If-None-Match"] = self._etags[endpoint]

        try:
            _LOGGER.debug(f"Fetching data from {endpoint}")
            async with self._session.get(endpoint, headers=headers) as response:
                # Handle 304 Not Modified - return cached data
                if response.status == 304:
                    _LOGGER.info(f"Resource not modified for {endpoint} (304) - ETag match")
                    # In a complete implementation, we would return cached data here
                    # For now, we'll just fetch it again with use_etag=False
                    return await self._fetch_api_endpoint(endpoint, use_etag=False)

                # Handle 401/403 Unauthorized - token may have expired
                if response.status in (401, 403):
                    _LOGGER.debug("Unauthorized access (401/403), refreshing token")
                    self._token = None  # Clear the token
                    success = await self.login()
                    if success:
                        return await self._fetch_api_endpoint(endpoint, use_etag)
                    return None

                # Accept both 200 OK and 201 Created as valid responses
                if response.status not in (200, 201, 202):
                    _LOGGER.error(f"Failed to fetch data from {endpoint}: {response.status}")
                    return None

                # Store the ETag if available
                if "ETag" in response.headers:
                    self._etags[endpoint] = response.headers["ETag"]

                # Parse and return the JSON data
                try:
                    data = await response.json()
                    return data
                except Exception as e:
                    _LOGGER.error(f"Error parsing JSON from {endpoint}: {e}")
                    # Try to get the text content
                    try:
                        content = await response.text()
                        # Check if response contains "success" or "ok" despite JSON parsing error
                        if content and (
                            "success" in content.lower() or "ok" in content.lower()
                        ):
                            _LOGGER.info("Response contains success indicators despite parsing error")
                            return {"success": True}  # Return a simple success object
                    except:
                        pass
                    return None
        except Exception as e:
            _LOGGER.error(f"Error fetching data from {endpoint}: {e}")
            return None

    async def _fetch_skills_levels(self):
        """Fetch the user's skill levels from the skills-levels endpoint."""
        # First get the member ID from the flyer-card endpoint
        flyer_card_data = await self._fetch_api_endpoint(
            "https://www.tunnelflight.com/user/module-type/flyer-card/"
        )
        if not flyer_card_data or "member_id" not in flyer_card_data:
            _LOGGER.error("Could not get member ID")
            return None

        member_id = flyer_card_data.get("member_id")

        # Now fetch the skills data with the member ID
        skills_url = f"https://www.tunnelflight.com/account/dashboard/flyer-skills-levels/{member_id}"
        return await self._fetch_api_endpoint(skills_url)

    async def get_logbook_entries(self):
        """Get the user's logbook entries containing skills data."""
        # First get the member ID from the flyer-card endpoint
        flyer_card_data = await self._fetch_api_endpoint(
            "https://www.tunnelflight.com/user/module-type/flyer-card/"
        )
        if not flyer_card_data or "member_id" not in flyer_card_data:
            _LOGGER.error("Could not get member ID")
            return None

        member_id = flyer_card_data.get("member_id")

        # Construct the logbook URL with the member ID
        logbook_url = f"https://www.tunnelflight.com/account/logbook/member/skills/open-suspended/{member_id}"
        return await self._fetch_api_endpoint(logbook_url)

    async def _post_api_endpoint(self, endpoint, data):
        """Post data to an API endpoint."""
        # Ensure we have a valid token
        if not self.is_token_valid:
            _LOGGER.debug("Token invalid or missing, attempting login")
            success = await self.login()
            if not success:
                _LOGGER.error(f"Login failed, cannot post data to {endpoint}")
                return None

        # Prepare request headers
        headers = {
            **self._browser_header,
            **self._auth_header,
            "Content-Type": "application/json",
        }

        try:
            _LOGGER.debug(f"Posting data to {endpoint}")
            async with self._session.post(
                endpoint, json=data, headers=headers
            ) as response:
                # Handle 401/403 Unauthorized - token may have expired
                if response.status in (401, 403):
                    _LOGGER.debug("Unauthorized post (401/403), refreshing token")
                    self._token = None  # Clear the token
                    success = await self.login()
                    if success:
                        return await self._post_api_endpoint(endpoint, data)
                    return None

                # Accept 200 OK, 201 Created, and 202 Accepted as valid responses
                if response.status not in (200, 201, 202):
                    _LOGGER.error(f"Failed to post data to {endpoint}: {response.status}")
                    return None

                # Parse and return the JSON data
                try:
                    data = await response.json()
                    _LOGGER.debug(f"Response received from {endpoint}")
                    return data
                except Exception as e:
                    _LOGGER.error(f"Error parsing JSON response: {e}")
                    # Try to get the text content
                    try:
                        content = await response.text()
                        # If response contains "success" somewhere, consider it a success despite JSON parsing error
                        if "success" in content.lower() or "ok" in content.lower():
                            _LOGGER.info("Assuming success based on response text")
                            return {
                                "message": "Ok",
                                "success": True,
                            }  # Return a dummy success response
                    except Exception as parse_error:
                        _LOGGER.error(f"Error parsing response text: {parse_error}")
                    return None
        except Exception as e:
            _LOGGER.error(f"Error posting data to {endpoint}: {e}")
            return None

    async def log_flight_time(
        self, tunnel_id, time_minutes, comment="", entry_date=None
    ):
        """Log flight time to the user's logbook."""
        # Use current timestamp if entry_date not provided
        if entry_date is None:
            entry_date = int(datetime.now().timestamp())
        elif isinstance(entry_date, datetime):
            entry_date = int(entry_date.timestamp())

        # Get tunnel name
        tunnels = await self.get_tunnels()
        tunnel_name = "unknown_tunnel"
        if tunnels and tunnel_id in tunnels:
            tunnel_name = tunnels[tunnel_id]["title"]

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

        _LOGGER.info(f"Logging {time_minutes} minutes at {tunnel_name} (ID: {tunnel_id})")
        
        # Post the logbook entry
        return await self._post_api_endpoint(
            "https://www.tunnelflight.com/account/logbook/member/time/", log_data
        )

    async def get_tunnels(self):
        """Fetch the list of tunnels from the API."""
        tunnels_data = await self._fetch_api_endpoint(
            "https://www.tunnelflight.com/account/logbook/tunnels/"
        )

        if not tunnels_data or not isinstance(tunnels_data, list):
            _LOGGER.error("Failed to fetch tunnels list or invalid format")
            return {}

        # Convert to a more usable format (ID-indexed dictionary)
        tunnels = {}
        for tunnel in tunnels_data:
            try:
                tunnel_id = int(tunnel.get("entry_id", 0))
                if tunnel_id > 0:
                    tunnels[tunnel_id] = {
                        "title": tunnel.get("title", "unknown"),
                        "country": tunnel.get("country", "unknown"),
                        "size": tunnel.get("size", "Unknown"),
                        "manufacturer": tunnel.get("manufacturer", "unknown"),
                        "address": tunnel.get("address", ""),
                        "address_city": tunnel.get("address_city", ""),
                        "status": tunnel.get("status", "unknown"),
                    }
            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"Error processing tunnel data: {e}")

        _LOGGER.debug(f"Fetched {len(tunnels)} tunnels from API")
        return tunnels

    async def get_user_data(self):
        """Get user data from both API endpoints and combine them."""
        # If token is invalid, try to login first
        if not self.is_token_valid:
            login_success = await self.login()
            if not login_success:
                _LOGGER.error("Login failed, cannot fetch user data")
                return None

        flyer_card_data = await self._fetch_api_endpoint(
            "https://www.tunnelflight.com/user/module-type/flyer-card/"
        )
        flyer_charts_data = await self._fetch_api_endpoint(
            "https://www.tunnelflight.com/user/module-type/flyer-charts/"
        )

        if not flyer_card_data:
            _LOGGER.error("Failed to fetch flyer card data")
            return None

        # Fetch the skills levels data
        skills_data = await self._fetch_skills_levels()

        # Fetch the logbook entries data
        logbook_entries = await self.get_logbook_entries()

        # Combine all the data
        user_data = {}

        # Start with flyer_card_data as the base
        if flyer_card_data:
            user_data.update(flyer_card_data)

        # Add any additional data from flyer_charts
        if flyer_charts_data:
            # Only add keys that don't already exist or have None values
            for key, value in flyer_charts_data.items():
                if key not in user_data or user_data[key] is None:
                    user_data[key] = value

        # Process and enrich the combined data
        if user_data:
            # Format the payment and currency status
            payment_status = user_data.get("paymentData", {}).get("paymentStatus")
            if payment_status:
                user_data["payment_status"] = payment_status.lower()

            # Extract payment expiry date from nextDate timestamp
            payment_next_date = user_data.get("paymentData", {}).get("nextDate")
            if payment_next_date:
                try:
                    user_data["payment_expiry_date"] = datetime.fromtimestamp(
                        payment_next_date
                    ).strftime("%Y-%m-%d")
                except Exception as e:
                    _LOGGER.error(f"Error formatting payment expiry date: {e}")

            # Extract currency renewal date for flyer
            currency_renewal_date = user_data.get("currency_renewal_date_flyer")
            if currency_renewal_date:
                try:
                    user_data["currency_renewal_date"] = datetime.fromtimestamp(
                        currency_renewal_date
                    ).strftime("%Y-%m-%d")
                except Exception as e:
                    _LOGGER.error(f"Error formatting currency renewal date: {e}")

            # Process total flight time (format: "3:34")
            flight_time = user_data.get("total_flight_time")
            if flight_time:
                try:
                    hours, minutes = flight_time.split(":")
                    user_data["total_flight_time_hours"] = int(hours)
                    user_data["total_flight_time_minutes"] = int(minutes)
                except Exception as e:
                    _LOGGER.error(f"Error parsing flight time: {e}")

            # Process last flight date
            last_flight = user_data.get("last_flight")
            if last_flight:
                try:
                    # Check if it's ISO-8601 format: "2024-11-20T14:50:10.000Z"
                    if isinstance(last_flight, str) and "T" in last_flight:
                        # Convert to timestamp for compatibility with existing code
                        last_flight_date = datetime.fromisoformat(
                            last_flight.replace("Z", "+00:00")
                        )
                        user_data["last_flight"] = int(last_flight_date.timestamp())
                except Exception as e:
                    _LOGGER.error(f"Error parsing last flight date: {e}")

            # Process skills data
            if skills_data:
                # The skills data uses "Yes"/"No" format with Pending flags
                # Default to 0 for all skills if not found
                user_data["static_level"] = 0
                user_data["dynamic_level"] = 0
                user_data["formation_level"] = 0

                # Also store the raw values from the API
                user_data["level1"] = skills_data.get("level1", "No")
                user_data["static"] = skills_data.get("static", "No")
                user_data["dynamic"] = skills_data.get("dynamic", "No")
                user_data["formation"] = skills_data.get("formation", "No")

                # Store the pending flags
                user_data["level1_pending"] = skills_data.get("level1Pending", False)
                user_data["static_pending"] = skills_data.get("staticPending", False)
                user_data["dynamic_pending"] = skills_data.get("dynamicPending", False)
                user_data["formation_pending"] = skills_data.get(
                    "formationPending", False
                )

                # Convert raw values to numeric levels
                # First, process the individual skill values (static, dynamic, formation)
                if skills_data.get("static") == "Yes":
                    user_data["static_level"] = 1
                elif skills_data.get("static", "").lower().startswith("level"):
                    try:
                        # Extract the number from "Level X"
                        level_num = int(skills_data.get("static").split(" ")[1])
                        user_data["static_level"] = level_num
                    except (IndexError, ValueError) as e:
                        _LOGGER.error(
                            f"Error parsing static level '{skills_data.get('static')}': {e}"
                        )

                if skills_data.get("dynamic") == "Yes":
                    user_data["dynamic_level"] = 1
                elif skills_data.get("dynamic", "").lower().startswith("level"):
                    try:
                        # Extract the number from "Level X"
                        level_num = int(skills_data.get("dynamic").split(" ")[1])
                        user_data["dynamic_level"] = level_num
                    except (IndexError, ValueError) as e:
                        _LOGGER.error(
                            f"Error parsing dynamic level '{skills_data.get('dynamic')}': {e}"
                        )

                # For formation, it might be Yes or a level
                formation = skills_data.get("formation")
                if formation == "Yes":
                    user_data["formation_level"] = 1
                elif formation and formation.lower().startswith("level"):
                    try:
                        # Extract the number from "Level X"
                        level_num = int(formation.split(" ")[1])
                        user_data["formation_level"] = level_num
                    except (IndexError, ValueError) as e:
                        _LOGGER.error(
                            f"Error parsing formation level '{formation}': {e}"
                        )

                # Second, if level1 is Yes but a specific skill is still at 0,
                # set that skill to level 1 as well
                if skills_data.get("level1") == "Yes":
                    # Only set to 1 if not already set to a higher value
                    if user_data.get("static_level", 0) == 0:
                        user_data["static_level"] = 1
                    if user_data.get("dynamic_level", 0) == 0:
                        user_data["dynamic_level"] = 1
                    if user_data.get("formation_level", 0) == 0:
                        user_data["formation_level"] = 1
            else:
                # Make sure all required fields exist even if we couldn't get skills data
                user_data["static_level"] = 0
                user_data["dynamic_level"] = 0
                user_data["formation_level"] = 0

                # Set default values for other skill fields
                user_data["level1"] = "no"
                user_data["static"] = "no"
                user_data["dynamic"] = "no"
                user_data["formation"] = "no"
                user_data["level1_pending"] = False
                user_data["static_pending"] = False
                user_data["dynamic_pending"] = False
                user_data["formation_pending"] = False

            # Set skill status based on level and pending status
            # For static level
            if user_data.get("static_pending", False):
                user_data["static_level_status"] = "pending"
            elif user_data.get("static_level", 0) > 0:
                user_data["static_level_status"] = "passed"
            else:
                user_data["static_level_status"] = "not_passed"

            # For dynamic level
            if user_data.get("dynamic_pending", False):
                user_data["dynamic_level_status"] = "pending"
            elif user_data.get("dynamic_level", 0) > 0:
                user_data["dynamic_level_status"] = "passed"
            else:
                user_data["dynamic_level_status"] = "not_passed"

            # For formation level
            if user_data.get("formation_pending", False):
                user_data["formation_level_status"] = "pending"
            elif user_data.get("formation_level", 0) > 0:
                user_data["formation_level_status"] = "passed"
            else:
                user_data["formation_level_status"] = "not_passed"

            # For user-specific data operations, validate that the data belongs to the authenticated user
            # For general operations like tunnel listings, this validation is skipped
            fetched_username = user_data.get("screen_name", "") or user_data.get(
                "real_name", ""
            )
            if (
                fetched_username and "member_id" in user_data
            ):  # Only validate for member-specific data
                # Do a sanity check to verify we're getting the right user's data
                fetched_normalized = fetched_username.lower().replace(" ", "")
                config_normalized = self._username.lower().replace(" ", "")

                # If there's a significant mismatch between the authenticated user and the data we received
                if not (
                    fetched_normalized.startswith(config_normalized[:3])
                    or config_normalized.startswith(fetched_normalized[:3])
                ):
                    _LOGGER.warning(
                        f"Data mismatch! Authenticated as {self._username} but received data for {fetched_username}. "
                        f"This suggests an issue with token/authentication handling."
                    )

        # Add logbook entries to user data
        if logbook_entries:
            user_data["logbook_entries"] = logbook_entries

            # Process the entries to get a summary of skills by category
            skills_by_category = {}

            for entry in logbook_entries:
                cat_name = entry.get("cat_name", "unknown")
                skill_name = entry.get("skill_name", "unknown")
                status = entry.get("status", "unknown")

                if cat_name not in skills_by_category:
                    skills_by_category[cat_name] = []

                skills_by_category[cat_name].append(
                    {
                        "id": entry.get("id"),
                        "name": skill_name,
                        "status": status,
                        "entry_date": entry.get("entry_date"),
                        "approval_date": entry.get("approval_date"),
                        "instructor": entry.get("instructor_name"),
                    }
                )

            user_data["skills_by_category"] = skills_by_category

        return user_data

    # Don't close the session - Home Assistant will manage it
    async def close(self):
        """Previously closed the session, but now we let HA manage it."""
        # Don't close the session if it's from Home Assistant
        pass