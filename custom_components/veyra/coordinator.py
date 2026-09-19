from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VeyraApi, VeyraApiError
from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class VeyraCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, api: VeyraApi, config_entry) -> None:
        self.api = api
        self.recovery_callback = None
        # The initial setup is already online. Only an actual later
        # online -> offline -> online transition should trigger self-heal.
        self._veyra_was_online = True
        super().__init__(
            hass,
            _LOGGER,
            name="Veyra",
            config_entry=config_entry,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            always_update=False,
        )

    async def _async_update_data(self) -> dict:
        try:
            data = await self.api.async_status()
        except VeyraApiError as err:
            self._veyra_was_online = False
            raise UpdateFailed(f"Error communicating with Veyra: {err}") from err

        recovered = not self._veyra_was_online
        self._veyra_was_online = True
        if recovered and self.recovery_callback is not None:
            _LOGGER.info("Veyra CORE recovered; rearming notification listener")
            self.hass.async_create_task(self.recovery_callback())
        return data
