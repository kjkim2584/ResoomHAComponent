"""Resoom's captured web API. No Home Assistant dependencies or live probes."""

import asyncio
import json
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

BASE_URL = "https://resoom.net"
BOARD_PATH = "/api/web/device/controlboard"


class ResoomError(Exception):
    """Base error with a safe, credential-free message."""


class AuthError(ResoomError):
    """Authentication expired or was rejected."""


class ResoomConnectionError(ResoomError):
    """Network or upstream service failure."""


class ProtocolError(ResoomError):
    """Response or existing settings cannot be used safely."""


class CommandUnconfirmed(ResoomError):
    """A command was sent but its reported result could not be confirmed."""


class _CsrfParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None
        self.header = "X-CSRF-TOKEN"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("name") == "_csrf":
            self.token = values.get("content") or values.get("value")
        if tag == "meta" and values.get("name") == "_csrf_header":
            self.header = values.get("content") or self.header


def parse_devices(payload: Any) -> dict[str, dict]:
    """Validate the board envelope; keep settings distinct from reported state."""
    if not isinstance(payload, dict):
        raise ProtocolError("Invalid controlboard response")
    result = {}
    for group in ("me", "shared"):
        section = payload.get(group)
        if not isinstance(section, dict) or not isinstance(section.get("devices"), list):
            raise ProtocolError("Invalid device list")
        for device in section["devices"]:
            if not isinstance(device, dict):
                raise ProtocolError("Invalid device entry")
            identity = device.get("device_id")
            if type(identity) is not int or identity <= 0:
                raise ProtocolError("Invalid device identity")
            metadata = device.get("device")
            if not isinstance(metadata, dict) or metadata.get("id") != identity:
                raise ProtocolError("Inconsistent device identity")
            if "state" not in device:
                raise ProtocolError("Missing device state")
            state = device["state"]
            if state is not None and (
                not isinstance(state, dict)
                or type(state.get("power")) is not int
                or state["power"] not in (1, 2, 3)
            ):
                raise ProtocolError("Invalid device power state")
            if device.get("immediately") is not None and not isinstance(
                device["immediately"], dict
            ):
                raise ProtocolError("Invalid immediate settings")
            if device.get("filter") is not None and (
                not isinstance(device["filter"], list)
                or any(not isinstance(f, dict) for f in device["filter"])
            ):
                raise ProtocolError("Invalid filter data")
            result.setdefault(str(identity), device)
    return result


def immediate_payload(settings: Any) -> dict:
    """Serialize only captured fields, preserving every existing setting."""
    if not isinstance(settings, dict):
        raise ProtocolError("Immediate settings unavailable")
    fields = (
        "repetition",
        "operation_time_minutes",
        "fan_speed",
        "additional_functions",
        "fan_ratio_sign",
    )
    if any(field not in settings for field in fields):
        raise ProtocolError("Incomplete immediate settings")
    result = {field: settings[field] for field in fields}
    for field in ("repetition", "fan_speed", "additional_functions", "fan_ratio_sign"):
        if type(result[field]) is not int:
            raise ProtocolError("Invalid immediate setting type")
    if (
        result["repetition"] not in (0, 1)
        or not 1 <= result["fan_speed"] <= 10
        or result["additional_functions"] < 0
        or result["fan_ratio_sign"] not in (-1, 0, 1)
    ):
        raise ProtocolError("Invalid immediate setting value")
    duration = result["operation_time_minutes"]
    if duration is not None and (type(duration) is not int or duration < 0):
        raise ProtocolError("Invalid operation duration")
    if result["repetition"] == 0 and not duration:
        raise ProtocolError("Finite operation requires a positive duration")
    if result["repetition"] == 1 and duration == 0:
        result["operation_time_minutes"] = None
    result["fan_ratio_sign"] = str(result["fan_ratio_sign"])
    return result


class ResoomApi:
    """Own authentication state; the caller owns the dedicated session."""

    def __init__(self, session: ClientSession, username: str, password: str) -> None:
        self.session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._header = "X-CSRF-TOKEN"
        self._logged_in = False
        self._auth_lock = asyncio.Lock()

    async def _fetch(self, method: str, path: str, **kwargs) -> tuple[int, Any, str]:
        try:
            async with self.session.request(
                method,
                BASE_URL + path,
                allow_redirects=False,
                timeout=ClientTimeout(total=20),
                **kwargs,
            ) as response:
                return response.status, response.headers, await response.text()
        except ClientError, TimeoutError, UnicodeError:
            raise ResoomConnectionError("Unable to communicate with Resoom") from None

    def _check_status(self, status: int) -> None:
        if status in (301, 302, 303, 307, 308, 401, 403):
            self._logged_in = False
            raise AuthError("Resoom authentication or CSRF validation failed")
        if status >= 500 or status == 429:
            raise ResoomConnectionError("Resoom service unavailable")
        if status != 200:
            raise ProtocolError("Unexpected Resoom response status")

    async def _csrf(self, path: str) -> None:
        status, _, text = await self._fetch("GET", path)
        self._check_status(status)
        parser = _CsrfParser()
        parser.feed(text)
        if not parser.token or not parser.header or "\n" in parser.header or "\r" in parser.header:
            raise ProtocolError("Missing or invalid CSRF metadata")
        self._token, self._header = parser.token, parser.header

    async def async_login(self) -> None:
        """Validate login using authenticated HTML and a JSON board response."""
        async with self._auth_lock:
            self._logged_in = False
            await self._csrf("/login")
            status, headers, _ = await self._fetch(
                "POST",
                "/login/p",
                data={"username": self._username, "password": self._password, "remember_me": "on"},
                headers={self._header: self._token},
            )
            if status >= 500 or status == 429:
                self._check_status(status)
            destination = urlsplit(urljoin(BASE_URL, headers.get("Location", "")))
            if (
                status not in (302, 303)
                or destination.scheme != "https"
                or destination.netloc != "resoom.net"
                or destination.path not in ("/", "/user", "/user/", "/user/home")
            ):
                raise AuthError("Resoom login was rejected")
            await self._csrf("/user/control")
            await self._get_devices()
            self._logged_in = True

    async def _json(self, method: str, path: str, **kwargs) -> Any:
        status, headers, text = await self._fetch(method, path, **kwargs)
        self._check_status(status)
        if "application/json" not in headers.get("Content-Type", "").lower():
            if "<html" in text.lower() or "<form" in text.lower():
                self._logged_in = False
                raise AuthError("Resoom session is not authenticated")
            raise ProtocolError("Expected a JSON response")
        try:
            return json.loads(text)
        except ValueError:
            raise ProtocolError("Invalid Resoom JSON response") from None

    async def _get_devices(self) -> dict[str, dict]:
        return parse_devices(
            await self._json("GET", BOARD_PATH, headers={"Accept": "application/json"})
        )

    async def async_get_devices(self) -> dict[str, dict]:
        if not self._logged_in:
            await self.async_login()
        try:
            return await self._get_devices()
        except AuthError:
            await self.async_login()
            return await self._get_devices()

    async def _command(self, device_id: str, suffix: str, payload: dict) -> None:
        if not device_id.isdecimal() or int(device_id) <= 0:
            raise ProtocolError("Invalid target device")
        if not self._logged_in:
            await self.async_login()
        response = await self._json(
            "POST",
            f"/api/web/device/{device_id}/{suffix}",
            headers={self._header: self._token},
            json=payload,
        )
        if not isinstance(response, dict) or type(response.get("code")) is not int:
            raise ProtocolError("Missing command acceptance code")
        if response["code"] <= 0:
            raise ProtocolError("Command was not accepted")

    async def async_set_power(self, device_id: str, power: bool) -> None:
        if type(power) is not bool:
            raise ProtocolError("Power must be a boolean")
        await self._command(device_id, "control/power", {"control": power})

    async def async_set_immediate(self, device_id: str, payload: dict) -> None:
        """Send an already validated full payload without replaying the POST."""
        await self._command(device_id, "mode/immediately", payload)
