import re
import json
import logging
import aiohttp
import asyncio
from urllib.parse import urlencode
from datetime import datetime

_LOGGER = logging.getLogger(__name__)


class TunnelflightApi:
    """Class to handle API calls to the IBA Tunnelflight website."""

    def __init__(self, username, password, session=None):
        """Initialize the API."""
        self._username = username.lower()  # Store username in lowercase for consistency
        self._password = password
        self._session = session or aiohttp.ClientSession()
        self._logged_in = False

        # Log which username this API instance is for
        _LOGGER.debug(f"Created TunnelflightApi instance for user: {self._username}")

        # Common browser headers that should be added to all standard requests
        self._browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

        # Special headers for AJAX requests
        self._ajax_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.tunnelflight.com",
            "Referer": "https://www.tunnelflight.com/",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    async def _clear_session(self):
        """Clear the session by logging out and getting a fresh session."""
        try:
            # Try to log out first
            logout_url = "https://www.tunnelflight.com/logout"
            await self._session.get(logout_url, headers=self._browser_headers)
            _LOGGER.debug(f"Logged out to clear session for {self._username}")

            # Get a fresh session
            await self._session.get(
                "https://www.tunnelflight.com/", headers=self._browser_headers
            )
            _LOGGER.debug(f"Got fresh session for {self._username}")

            # Wait a moment for the server to process the logout
            await asyncio.sleep(2)

        except Exception as e:
            _LOGGER.error(f"Error clearing session for {self._username}: {e}")

    async def login(self, retry=True):
        """Login to the IBA website."""
        _LOGGER.debug(f"Starting login process for username: {self._username}")

        # First, visit the main page to get cookies
        try:
            _LOGGER.debug(
                f"Getting main page to establish session for {self._username}"
            )
            await self._session.get(
                "https://www.tunnelflight.com/", headers=self._browser_headers
            )
        except Exception as e:
            _LOGGER.error(f"Error accessing main page for {self._username}: {e}")
            return False

        login_url = "https://www.tunnelflight.com/login"
        login_data = {
            "username": self._username,
            "password": self._password,
            "passcode": "",
            "enable2fa": False,
            "checkTwoFactor": True,
            "passcodeOption": "email",
        }

        _LOGGER.debug(f"Sending login request to {login_url} for {self._username}")
        try:
            async with self._session.post(
                login_url, json=login_data, headers=self._ajax_headers
            ) as response:
                _LOGGER.debug(
                    f"Login response status for {self._username}: {response.status}"
                )

                # Handle 409 Conflict - this likely means there's an existing session
                if response.status == 409 and retry:
                    _LOGGER.warning(
                        f"Got 409 conflict for {self._username}, clearing session and retrying"
                    )
                    await self._clear_session()
                    return await self.login(
                        retry=False
                    )  # Retry once with retry=False to prevent infinite loops

                # Try to get the response content
                try:
                    content = await response.text()
                    # Log partial content to avoid exposing sensitive data
                    content_preview = (
                        content[:100] + "..." if len(content) > 100 else content
                    )
                    _LOGGER.debug(
                        f"Login response preview for {self._username}: {content_preview}"
                    )
                except Exception as e:
                    _LOGGER.error(
                        f"Could not read response content for {self._username}: {e}"
                    )
                    content = ""

                # Check status code first
                if response.status != 200:
                    _LOGGER.error(
                        f"Login failed with status {response.status} for {self._username}"
                    )
                    self._logged_in = False
                    return False

                # Try to parse as JSON
                try:
                    response_data = json.loads(content)
                    # Fix for the issue: The site returns "success" in "message" field!
                    # Check if token exists, or if message contains "success" or "successfully"
                    if "token" in response_data:
                        self._logged_in = True
                        _LOGGER.debug(
                            f"Login successful - token found in response for {self._username}"
                        )
                    elif response_data.get("message", "").lower().find("success") >= 0:
                        self._logged_in = True
                        _LOGGER.debug(
                            f"Login successful via success message for {self._username}: {response_data.get('message')}"
                        )
                    else:
                        self._logged_in = False
                        _LOGGER.error(
                            f"Login JSON indicates failure for {self._username}: {response_data.get('message', 'Unknown error')}"
                        )
                    return self._logged_in
                except json.JSONDecodeError:
                    _LOGGER.debug(
                        f"Response is not valid JSON for {self._username}, checking for success in text"
                    )
                    # Sometimes the response is not JSON
                    self._logged_in = "success" in content.lower()
                    if self._logged_in:
                        _LOGGER.debug(
                            f"Login successful via text response for {self._username}"
                        )
                    else:
                        _LOGGER.error(
                            f"Login failed - success not found in response for {self._username}"
                        )
                    return self._logged_in
        except Exception as e:
            _LOGGER.error(f"Error during login request for {self._username}: {e}")
            self._logged_in = False
            return False

    async def _fetch_api_endpoint(self, endpoint):
        """Fetch data from an API endpoint."""
        if not self._logged_in:
            _LOGGER.debug(f"Not logged in, attempting login first for {self._username}")
            success = await self.login()
            if not success:
                _LOGGER.error(
                    f"Login failed, cannot fetch data from {endpoint} for {self._username}"
                )
                return None

        try:
            _LOGGER.debug(f"Fetching data from {endpoint} for {self._username}")
            async with self._session.get(
                endpoint, headers=self._ajax_headers
            ) as response:
                if response.status != 200:
                    _LOGGER.error(
                        f"Failed to fetch data from {endpoint}: {response.status} for {self._username}"
                    )
                    # If we get a 401 or 403, try to re-login and fetch again
                    if response.status in (401, 403):
                        _LOGGER.debug(f"Attempting to re-login and retry fetch")
                        self._logged_in = False
                        success = await self.login()
                        if success:
                            return await self._fetch_api_endpoint(endpoint)
                    return None

                data = await response.json()
                _LOGGER.debug(
                    f"Data fetched from {endpoint} for {self._username}, length: {len(str(data))}"
                )
                return data
        except Exception as e:
            _LOGGER.error(
                f"Error fetching data from {endpoint} for {self._username}: {e}"
            )
            return None

    async def _fetch_skills_levels(self):
        """Fetch the user's skill levels from the skills-levels endpoint."""
        if not self._logged_in:
            _LOGGER.debug(f"Not logged in, attempting login first for {self._username}")
            success = await self.login()
            if not success:
                _LOGGER.error(
                    f"Login failed, cannot fetch skills levels for {self._username}"
                )
                return None

        # Based on the JavaScript code, this is the endpoint for skills levels
        skills_url = "/account/dashboard/flyer-skills-levels"

        # First get the member ID from the flyer-card endpoint
        flyer_card_data = await self._fetch_api_endpoint(
            "https://www.tunnelflight.com/user/module-type/flyer-card/"
        )
        if not flyer_card_data or "member_id" not in flyer_card_data:
            _LOGGER.error(f"Could not get member ID for {self._username}")
            return None

        member_id = flyer_card_data.get("member_id")

        # Now fetch the skills data with the member ID
        skills_url = f"https://www.tunnelflight.com/account/dashboard/flyer-skills-levels/{member_id}"

        try:
            _LOGGER.debug(
                f"Fetching skills levels from {skills_url} for {self._username}"
            )
            async with self._session.get(
                skills_url, headers=self._ajax_headers
            ) as response:
                # Accept 201 Created as well as 200 OK - the API sometimes returns 201
                if response.status not in (200, 201):
                    _LOGGER.error(
                        f"Failed to fetch skills levels: {response.status} for {self._username}"
                    )
                    return None

                # Try to parse as JSON
                try:
                    data = await response.json()
                    _LOGGER.debug(f"Skills levels fetched for {self._username}: {data}")

                    # Log the raw skill values for debugging
                    level1 = data.get("level1", "N/A")
                    static = data.get("static", "N/A")
                    dynamic = data.get("dynamic", "N/A")
                    formation = data.get("formation", "N/A")
                    _LOGGER.debug(
                        f"Raw skill values for {self._username}: level1={level1}, static={static}, dynamic={dynamic}, formation={formation}"
                    )

                    # Also log the pending statuses
                    level1_pending = data.get("level1Pending", False)
                    static_pending = data.get("staticPending", False)
                    dynamic_pending = data.get("dynamicPending", False)
                    formation_pending = data.get("formationPending", False)
                    _LOGGER.debug(
                        f"Pending statuses for {self._username}: level1={level1_pending}, static={static_pending}, dynamic={dynamic_pending}, formation={formation_pending}"
                    )

                    return data
                except Exception as e:
                    _LOGGER.error(
                        f"Error parsing skills JSON for {self._username}: {e}"
                    )

                    # Try to get the text content
                    try:
                        content = await response.text()
                        _LOGGER.debug(f"Raw response from skills endpoint: {content}")
                    except:
                        pass

                    return None
        except Exception as e:
            _LOGGER.error(f"Error fetching skills levels for {self._username}: {e}")
            return None

    async def get_logbook_entries(self):
        """Get the user's logbook entries containing skills data."""
        if not self._logged_in:
            _LOGGER.debug(f"Not logged in, attempting login first for {self._username}")
            success = await self.login()
            if not success:
                _LOGGER.error(
                    f"Login failed, cannot fetch logbook for {self._username}"
                )
                return None

        # First get the member ID from the flyer-card endpoint
        flyer_card_data = await self._fetch_api_endpoint(
            "https://www.tunnelflight.com/user/module-type/flyer-card/"
        )
        if not flyer_card_data or "member_id" not in flyer_card_data:
            _LOGGER.error(f"Could not get member ID for {self._username}")
            return None

        member_id = flyer_card_data.get("member_id")

        # Construct the logbook URL with the member ID
        logbook_url = f"https://www.tunnelflight.com/account/logbook/member/skills/open-suspended/{member_id}"

        _LOGGER.warning(
            f"Using member_id: {member_id} to fetch logbook entries from {logbook_url}"
        )

        try:
            async with self._session.get(
                logbook_url, headers=self._ajax_headers
            ) as response:
                # Accept both 200 OK and 201 Created as valid responses
                if response.status not in (200, 201):
                    _LOGGER.error(f"Failed to fetch logbook entries: {response.status}")
                    return None

                try:
                    data = await response.json()
                    _LOGGER.warning(
                        f"Fetched {len(data) if data else 'no'} logbook entries"
                    )
                    return data
                except Exception as e:
                    _LOGGER.error(f"Error parsing logbook entries: {e}")
                    content = await response.text()
                    _LOGGER.warning(f"Raw response content: {content[:200]}")
                    return None
        except Exception as e:
            _LOGGER.error(f"Error fetching logbook entries: {e}")
            return None

    async def get_user_data(self):
        """Get user data from both API endpoints and combine them."""
        flyer_card_data = await self._fetch_api_endpoint(
            "https://www.tunnelflight.com/user/module-type/flyer-card/"
        )
        flyer_charts_data = await self._fetch_api_endpoint(
            "https://www.tunnelflight.com/user/module-type/flyer-charts/"
        )

        if not flyer_card_data:
            _LOGGER.error(f"Failed to fetch flyer card data for {self._username}")
            return None

        # Also try to fetch the user info from the dashboard for any additional details
        dashboard_data = await self._fetch_dashboard_data()

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

        # Add any additional data from dashboard
        if dashboard_data:
            for key, value in dashboard_data.items():
                if key not in user_data or user_data[key] is None:
                    user_data[key] = value

        # Process and enrich the combined data
        if user_data:
            # Format the payment and currency status
            payment_status = user_data.get("paymentData", {}).get("paymentStatus")
            if payment_status:
                user_data["payment_status"] = payment_status

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
                    _LOGGER.debug(
                        f"Level1 is Yes for {self._username}, ensuring minimum level 1 for all skills"
                    )
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
                user_data["level1"] = "No"
                user_data["static"] = "No"
                user_data["dynamic"] = "No"
                user_data["formation"] = "No"
                user_data["level1_pending"] = False
                user_data["static_pending"] = False
                user_data["dynamic_pending"] = False
                user_data["formation_pending"] = False

            # Set skill status based on level and pending status
            # For static level
            if user_data.get("static_pending", False):
                user_data["static_level_status"] = "Pending"
            elif user_data.get("static_level", 0) > 0:
                user_data["static_level_status"] = "Passed"
            else:
                user_data["static_level_status"] = "Not Passed"

            # For dynamic level
            if user_data.get("dynamic_pending", False):
                user_data["dynamic_level_status"] = "Pending"
            elif user_data.get("dynamic_level", 0) > 0:
                user_data["dynamic_level_status"] = "Passed"
            else:
                user_data["dynamic_level_status"] = "Not Passed"

            # For formation level
            if user_data.get("formation_pending", False):
                user_data["formation_level_status"] = "Pending"
            elif user_data.get("formation_level", 0) > 0:
                user_data["formation_level_status"] = "Passed"
            else:
                user_data["formation_level_status"] = "Not Passed"

            # Validate that the data belongs to the correct user
            fetched_username = user_data.get("screen_name", "")
            if fetched_username:
                # Do a more forgiving comparison
                fetched_normalized = fetched_username.lower().replace(" ", "")
                config_normalized = self._username.lower().replace(" ", "")

                # Only warn if there's a significant mismatch
                if not (
                    fetched_normalized.startswith(config_normalized[:3])
                    or config_normalized.startswith(fetched_normalized[:3])
                ):
                    _LOGGER.warning(
                        f"Data mismatch! Fetched data for {fetched_username} but expected {self._username}"
                    )

        # Add logbook entries to user data
        if logbook_entries:
            user_data["logbook_entries"] = logbook_entries

            # Process the entries to get a summary of skills by category
            skills_by_category = {}

            for entry in logbook_entries:
                cat_name = entry.get("cat_name", "Unknown")
                skill_name = entry.get("skill_name", "Unknown")
                status = entry.get("status", "Unknown")

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

    async def _fetch_dashboard_data(self):
        """Get user data from the dashboard HTML."""
        if not self._logged_in:
            _LOGGER.debug(f"Not logged in, attempting login first for {self._username}")
            success = await self.login()
            if not success:
                _LOGGER.error(
                    f"Login failed, cannot fetch dashboard data for {self._username}"
                )
                return None

        dashboard_url = "https://www.tunnelflight.com/account/dashboard"
        _LOGGER.debug(f"Fetching dashboard from {dashboard_url} for {self._username}")

        try:
            async with self._session.get(
                dashboard_url, headers=self._browser_headers
            ) as response:
                if response.status != 200:
                    _LOGGER.error(
                        f"Failed to fetch dashboard: {response.status} for {self._username}"
                    )
                    return None

                html = await response.text()
                _LOGGER.debug(
                    f"Dashboard fetched for {self._username}, HTML length: {len(html)}"
                )

                # Extract the user info JSON from the HTML
                user_info_match = re.search(
                    r'<script id="userInfoObj" type="application/json">(.*?)</script>',
                    html,
                    re.DOTALL,
                )

                if not user_info_match:
                    _LOGGER.error(
                        f"Could not find user info in dashboard HTML for {self._username}"
                    )
                    # Log a portion of the HTML to help debugging
                    html_snippet = html[:500] + "..." if len(html) > 500 else html
                    _LOGGER.debug(f"HTML snippet for {self._username}: {html_snippet}")
                    return None

                try:
                    user_info_json = user_info_match.group(1)
                    _LOGGER.debug(
                        f"Found user info JSON snippet for {self._username}: {user_info_json[:100]}"
                    )
                    user_info = json.loads(user_info_json)
                    return user_info
                except json.JSONDecodeError as e:
                    _LOGGER.error(
                        f"Failed to parse user info for {self._username}: {e}"
                    )
                    return None
        except Exception as e:
            _LOGGER.error(f"Error fetching dashboard for {self._username}: {e}")
            return None

    # Don't close the session - Home Assistant will manage it
    async def close(self):
        """Previously closed the session, but now we let HA manage it."""
        # Don't close the session if it's from Home Assistant
        pass
