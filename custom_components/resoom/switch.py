"""Immediate-mode feature settings; the cutoff flag is not an emergency stop."""

from homeassistant.components.switch import SwitchEntity

from .const import FUNCTIONS
from .entity import ResoomSettingEntity, discover_entities


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    discover_entities(
        entry,
        async_add_entities,
        lambda did: [
            ResoomFunction(entry.runtime_data, did, key, flag) for key, flag in FUNCTIONS.items()
        ],
    )


class ResoomFunction(ResoomSettingEntity, SwitchEntity):
    def __init__(self, coordinator, device_id, key, flag) -> None:
        super().__init__(coordinator, device_id, key)
        self.flag = flag

    @property
    def is_on(self) -> bool | None:
        flags = (self.device.get("immediately") or {}).get("additional_functions")
        return bool(flags & self.flag) if type(flags) is int else None

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_flag(self.device_id, self.flag, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_flag(self.device_id, self.flag, False)
