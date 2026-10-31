"""Coordinator class for Ariston module."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging

from ariston.base_device import AristonBaseDevice
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class DeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages polling for state changes from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: AristonBaseDevice,
        scan_interval_seconds: int,
        coordinator_name: str,
        async_update_state: Callable,
    ) -> None:
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{device.name}-{coordinator_name}",
            update_interval=timedelta(seconds=scan_interval_seconds),
            update_method=async_update_state,
        )

        self.device = device

    async def _async_update_data(self):
        """Fetch data from API endpoint, preserving state if cloud returns empty dict."""
        prev_data = (
            dict(self.device.data)
            if getattr(self.device, "data", None)
            else None
        )
        result = await super()._async_update_data()
        if prev_data and hasattr(self.device, "data") and not self.device.data:
            _LOGGER.warning(
                "Ariston cloud returned empty data for %s; preserving last known state",
                self.name,
            )
            self.device.data = prev_data
        return result
