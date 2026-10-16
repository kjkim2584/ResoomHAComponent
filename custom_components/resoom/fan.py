"""Reported power; configured speed is deliberately a separate number entity."""

from homeassistant.components.fan import FanEntity, FanEntityFeature

from .entity import ResoomEntity, discover_entities


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    discover_entities(entry, async_add_entities, lambda did: [ResoomFan(entry.runtime_data, did)])


class ResoomFan(ResoomEntity, FanEntity):
    _attr_supported_features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF

    def __init__(self, coordinator, device_id) -> None:
        super().__init__(coordinator, device_id, "power")

    @property
    def is_on(self) -> bool | None:
        power = (self.device.get("state") or {}).get("power")
        return power == 2 if power in (2, 3) else None

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        await self.coordinator.async_set_power(self.device_id, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_power(self.device_id, False)
