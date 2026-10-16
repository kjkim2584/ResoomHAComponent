"""UI account registration and reauthentication."""

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import AuthError, ProtocolError, ResoomApi, ResoomError
from .const import DOMAIN

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class ResoomConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one account and preserve its identity during reauthentication."""

    VERSION = 1

    async def _validate(self, username: str, password: str) -> dict[str, str]:
        if not username or not password:
            return {"base": "invalid_auth"}
        session = async_create_clientsession(self.hass, auto_cleanup=False)
        try:
            await ResoomApi(session, username, password).async_login()
        except AuthError:
            return {"base": "invalid_auth"}
        except ProtocolError:
            return {"base": "invalid_response"}
        except ResoomError:
            return {"base": "cannot_connect"}
        finally:
            session.detach()
        return {}

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip().casefold()
            await self.async_set_unique_id(username)
            self._abort_if_unique_id_configured()
            password = user_input[CONF_PASSWORD]
            errors = await self._validate(username, password)
            if not errors:
                return self.async_create_entry(
                    title=username,
                    data={CONF_USERNAME: username, CONF_PASSWORD: password},
                )
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.EMAIL)
                    ),
                    vol.Required(CONF_PASSWORD): PASSWORD,
                }
            ),
        )

    async def async_step_reauth(self, entry_data) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            errors = await self._validate(entry.data[CONF_USERNAME], password)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: password},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD}),
        )
