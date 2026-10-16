"""Reported operating state and captured filter capacity readings."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE

from .const import OPERATING_MODES
from .entity import ResoomEntity, discover_entities


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    discover_entities(
        entry,
        async_add_entities,
        lambda did: [
            ResoomSensor(entry.runtime_data, did, key)
            for key in ("reported_speed", "mode", "filter", "element")
        ],
    )


class ResoomSensor(ResoomEntity, SensorEntity):
    def __init__(self, coordinator, device_id, key) -> None:
        super().__init__(coordinator, device_id, key)
        self.key = key
        if key in ("filter", "element"):
            self._attr_native_unit_of_measurement = PERCENTAGE
        if key == "mode":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(OPERATING_MODES.values())

    @property
    def native_value(self) -> int | str | None:
        state = self.device.get("state") or {}
        if self.key == "reported_speed":
            return state.get("fan_speed")
        if self.key == "mode":
            return OPERATING_MODES.get(state.get("mode"))
        filter_type = 1 if self.key == "filter" else 2
        return next(
            (
                f.get("remaining_capacity")
                for f in self.device.get("filter") or []
                if f.get("filter_type") == filter_type
            ),
            None,
        )
