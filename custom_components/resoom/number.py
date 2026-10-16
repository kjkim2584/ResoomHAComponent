"""Captured 1–10 immediate-mode speed setting."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.exceptions import HomeAssistantError

from .entity import ResoomSettingEntity, discover_entities


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    discover_entities(entry, async_add_entities, lambda did: [ResoomSpeed(entry.runtime_data, did)])


class ResoomSpeed(ResoomSettingEntity, NumberEntity):
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator, device_id) -> None:
        super().__init__(coordinator, device_id, "speed")

    @property
    def native_value(self) -> int | None:
        return (self.device.get("immediately") or {}).get("fan_speed")

    async def async_set_native_value(self, value: float) -> None:
        if type(value) not in (int, float) or not float(value).is_integer():
            raise HomeAssistantError("Fan speed must be a whole number")
        if not 1 <= value <= 10:
            raise HomeAssistantError("Fan speed must be between 1 and 10")
        await self.coordinator.async_set_immediate(self.device_id, "fan_speed", int(value))
