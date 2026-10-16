"""Immediate pressure setting, not a smart/reservation operating preset."""

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError

from .const import PRESSURE_MODES
from .entity import ResoomSettingEntity, discover_entities


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    discover_entities(
        entry, async_add_entities, lambda did: [ResoomPressure(entry.runtime_data, did)]
    )


class ResoomPressure(ResoomSettingEntity, SelectEntity):
    _attr_options = list(PRESSURE_MODES)

    def __init__(self, coordinator, device_id) -> None:
        super().__init__(coordinator, device_id, "pressure")

    @property
    def current_option(self) -> str | None:
        sign = (self.device.get("immediately") or {}).get("fan_ratio_sign")
        return next((key for key, value in PRESSURE_MODES.items() if value == sign), None)

    async def async_select_option(self, option: str) -> None:
        if option not in PRESSURE_MODES:
            raise HomeAssistantError("Unsupported pressure setting")
        await self.coordinator.async_set_immediate(
            self.device_id,
            "fan_ratio_sign",
            PRESSURE_MODES[option],
        )
