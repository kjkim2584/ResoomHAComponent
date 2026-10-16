"""Resoom cloud integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import ResoomApi
from .const import PLATFORMS
from .coordinator import ResoomCoordinator

type ResoomConfigEntry = ConfigEntry[ResoomCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ResoomConfigEntry) -> bool:
    """Create a separate cookie session for each Resoom account."""
    session = async_create_clientsession(hass, auto_cleanup=False)
    api = ResoomApi(session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = ResoomCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        # The connector belongs to HA; detach only this account's cookie session.
        session.detach()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ResoomConfigEntry) -> bool:
    """Unload entities before closing their account session."""
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry.runtime_data.api.session.detach()
        return True
    return False
