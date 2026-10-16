"""Shared identity, availability and discovery for all Resoom platforms."""

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ResoomConfigEntry
from .api import BASE_URL, ProtocolError, immediate_payload
from .const import DOMAIN
from .coordinator import ResoomCoordinator


@callback
def discover_entities(
    entry: ResoomConfigEntry,
    add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[str], Iterable[Entity]],
) -> None:
    """Discover once per platform and add devices found on subsequent polls."""
    known: set[str] = set()
    coordinator = entry.runtime_data

    @callback
    def discover() -> None:
        new_entities = []
        for device_id in coordinator.data:
            if device_id not in known:
                new_entities.extend(factory(device_id))
                known.add(device_id)
        if new_entities:
            add_entities(new_entities)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class ResoomEntity(CoordinatorEntity[ResoomCoordinator]):
    """One stable identity per server device and supported function."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ResoomCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator, context=device_id)
        self.device_id = device_id
        # A shared physical device can be controlled by several account entries.
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{device_id}_{key}"
        self._attr_translation_key = key
        metadata = coordinator.data[device_id]["device"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=metadata.get("nickname") or metadata.get("name") or f"Resoom {device_id}",
            manufacturer="Resoom",
            configuration_url=BASE_URL + "/user/control",
        )

    @property
    def device(self) -> dict:
        return (self.coordinator.data or {}).get(self.device_id, {})

    @property
    def available(self) -> bool:
        state = self.device.get("state")
        return super().available and bool(state) and state.get("power") in (2, 3)


class ResoomSettingEntity(ResoomEntity):
    """Never allow edits when the complete existing configuration is unknown."""

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        try:
            immediate_payload(self.device.get("immediately"))
        except ProtocolError:
            return False
        return True
