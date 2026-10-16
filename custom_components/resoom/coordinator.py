"""One account poll, serialized device commands and bounded read-back checks."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AuthError,
    CommandUnconfirmed,
    ProtocolError,
    ResoomApi,
    ResoomError,
    immediate_payload,
)
from .const import DOMAIN, FUNCTIONS

_LOGGER = logging.getLogger(__name__)
CONFIRM_INTERVAL = 3
CONFIRM_ATTEMPTS = 3


class ResoomCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Keep actual reports authoritative; never optimistically change state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: ResoomApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.api = api
        self.entry = entry
        self._command_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            return await self.api.async_get_devices()
        except AuthError as error:
            raise ConfigEntryAuthFailed(str(error)) from None
        except ResoomError as error:
            raise UpdateFailed(str(error)) from None

    async def _latest(self, device_id: str) -> dict:
        devices = await self.api.async_get_devices()
        self.async_set_updated_data(devices)
        device = devices.get(device_id)
        if not device or not device.get("state") or device["state"].get("power") not in (2, 3):
            raise ProtocolError("Device is offline or no longer accessible")
        return device

    async def _confirm(self, device_id: str, matches: Callable[[dict], bool]) -> None:
        for attempt in range(CONFIRM_ATTEMPTS):
            if attempt:
                await asyncio.sleep(CONFIRM_INTERVAL)
            try:
                devices = await self.api.async_get_devices()
            except AuthError:
                raise
            except ResoomError:
                raise CommandUnconfirmed(
                    "Command sent; unable to confirm reported result"
                ) from None
            self.async_set_updated_data(devices)
            device = devices.get(device_id)
            if (
                device
                and device.get("state")
                and device["state"].get("power") in (2, 3)
                and matches(device)
            ):
                return
        raise CommandUnconfirmed("Command sent; unable to confirm reported result")

    def _service_error(self, error: ResoomError) -> HomeAssistantError:
        if isinstance(error, AuthError):
            self.entry.async_start_reauth(self.hass)
        return HomeAssistantError(str(error))

    async def async_set_power(self, device_id: str, power: bool) -> None:
        async with self._command_locks[device_id]:
            try:
                await self._latest(device_id)
                await self.api.async_set_power(device_id, power)
                await self._confirm(
                    device_id, lambda d: d["state"].get("power") == (2 if power else 3)
                )
            except ResoomError as error:
                raise self._service_error(error) from None

    async def _set_settings(
        self,
        device_id: str,
        change: Callable[[dict], None],
    ) -> None:
        async with self._command_locks[device_id]:
            try:
                device = await self._latest(device_id)
                current = device.get("immediately")
                # Reject missing/invalid settings before changing even a single field.
                immediate_payload(current)
                settings = dict(current)
                change(settings)
                payload = immediate_payload(settings)
                await self.api.async_set_immediate(device_id, payload)

                def matches(reported: dict) -> bool:
                    try:
                        # Canonicalize both null and zero continuous-time reports.
                        return immediate_payload(reported.get("immediately")) == payload
                    except ProtocolError:
                        return False

                await self._confirm(device_id, matches)
            except ResoomError as error:
                raise self._service_error(error) from None

    async def async_set_immediate(self, device_id: str, field: str, value: int) -> None:
        if field not in ("fan_speed", "fan_ratio_sign"):
            raise HomeAssistantError("Unsupported immediate setting")
        await self._set_settings(device_id, lambda settings: settings.update({field: value}))

    async def async_set_flag(self, device_id: str, flag: int, enabled: bool) -> None:
        if flag not in FUNCTIONS.values() or type(enabled) is not bool:
            raise HomeAssistantError("Unsupported immediate function")

        def change(settings: dict) -> None:
            previous = settings["additional_functions"]
            settings["additional_functions"] = previous | flag if enabled else previous & ~flag

        await self._set_settings(device_id, change)
