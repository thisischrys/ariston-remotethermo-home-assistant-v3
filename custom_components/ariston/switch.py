"""Support for Ariston switches."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ARISTON_SWITCH_TYPES, DOMAIN, AristonSwitchEntityDescription
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston switches from config entry."""
    ariston_switches: list[AristonSwitch] = []
    for description in ARISTON_SWITCH_TYPES:
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            description.coordinator
        ]
        if (
            coordinator
            and coordinator.device
            and coordinator.device.are_device_features_available(
                description.device_features,
                description.system_types,
                description.whe_types,
            )
        ):
            ariston_switches.append(
                AristonSwitch(
                    coordinator,
                    description,
                )
            )

    async_add_entities(ariston_switches)


class AristonSwitch(AristonEntity, SwitchEntity):
    """Base class for specific ariston switches."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description)

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self.entity_description.get_is_on(self)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        key = self.entity_description.key
        in_data = hasattr(self.device, "data") and key in self.device.data
        old_val = self.device.data.get(key) if in_data else None
        if in_data:
            self.device.data[key] = True
            self.coordinator.async_set_updated_data(None)
        try:
            await self.entity_description.set_value(self, True)
        except Exception:
            if in_data:
                self.device.data[key] = old_val
                self.coordinator.async_set_updated_data(None)
            raise
        self.coordinator.async_set_updated_data(None)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        key = self.entity_description.key
        in_data = hasattr(self.device, "data") and key in self.device.data
        old_val = self.device.data.get(key) if in_data else None
        if in_data:
            self.device.data[key] = False
            self.coordinator.async_set_updated_data(None)
        try:
            await self.entity_description.set_value(self, False)
        except Exception:
            if in_data:
                self.device.data[key] = old_val
                self.coordinator.async_set_updated_data(None)
            raise
        self.coordinator.async_set_updated_data(None)
