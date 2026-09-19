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
            return await self.api.async_status()
        except VeyraApiError as err:
            raise UpdateFailed(f"Error communicating with Veyra: {err}") from err
