"""Support for Ariston water heaters."""

from __future__ import annotations

import logging

from ariston.const import (
    ARISTON_VELIS,
    NuosSplitProperties,
    PlantData,
    SlpDeviceSettings,
    SystemType,
    VelisBaseDeviceProperties,
    WheType,
)
from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant

from .const import (
    ARISTON_WATER_HEATER_TYPES,
    DOMAIN,
    AristonWaterHeaterEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the Ariston water heater device from config entry."""
    ariston_water_heaters: list[AristonWaterHeater] = []
    for description in ARISTON_WATER_HEATER_TYPES:
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
            ariston_water_heaters.append(AristonWaterHeater(coordinator, description))

    async_add_entities(ariston_water_heaters)


class AristonWaterHeater(AristonEntity, WaterHeaterEntity):
    """Ariston Water Heater Device."""

    _attr_translation_key = "ariston_water_heater"

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonWaterHeaterEntityDescription,
    ) -> None:
        """Initialize the water heater."""
        super().__init__(coordinator, description)

    @property
    def name(self) -> str:
        """Return the name of the device."""
        return self.device.name or ""

    @property
    def unique_id(self) -> str:
        """Return a unique id for the device."""
        return f"{self.device.gateway}-water_heater"

    @property
    def current_temperature(self):
        """Return the temperature."""
        return self.device.water_heater_current_temperature

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.device.water_heater_minimum_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        target = self.device.water_heater_target_temperature
        max_t = self.max_temp
        if target is not None and max_t is not None and target > max_t:
            return max_t
        return target

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if (
            self.device.whe_type == WheType.NuosSplit
            and self.current_operation == "GREEN"
        ):
            max_green = getattr(self.device, "plant_settings", {}).get(
                SlpDeviceSettings.SLP_MAX_GREEN_TEMPERATURE
            )
            if max_green is not None:
                return max_green
        return self.device.water_heater_maximum_temperature

    @property
    def precision(self) -> float:
        """Return the precision of temperature for the device."""
        return 1 / 10**self.device.water_heater_temperature_decimals

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self.device.water_heater_temperature_unit

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
        if self.device.dhw_mode_changeable:
            features |= WaterHeaterEntityFeature.OPERATION_MODE
        if (
            self.device.system_type == SystemType.VELIS
            and "ON_OFF"
            in WaterHeaterEntityFeature.__members__  # check entity feature for backward compatibility
        ):
            features |= WaterHeaterEntityFeature.ON_OFF
        return features

    @property
    def operation_list(self):
        """List of available operation modes."""
        return [
            mode
            for mode in self.device.water_heater_mode_operation_texts
            if mode != "IMEMORY"
        ]

    @property
    def current_operation(self):
        """Return current operation."""
        return self.device.water_heater_current_mode_text

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ValueError(f"Missing parameter {ATTR_TEMPERATURE}")

        temperature = kwargs[ATTR_TEMPERATURE]
        if self.max_temp is not None and temperature > self.max_temp:
            temperature = self.max_temp
        _LOGGER.debug(
            "Setting temperature to %d for %s",
            temperature,
            self.name,
        )

        if self.device.whe_type == WheType.NuosSplit:
            old_comfort = self.device.water_heater_target_temperature
            old_reduced = self.device.water_heater_reduced_temperature
            old_proc = self.device.data.get(NuosSplitProperties.PROC_REQ_TEMP)
            self.device.data[NuosSplitProperties.COMFORT_TEMP] = temperature
            self.device.data[NuosSplitProperties.PROC_REQ_TEMP] = temperature
            self.coordinator.async_set_updated_data(None)
            try:
                await self.device.api.async_set_nuos_temperature(
                    self.device.gw,
                    temperature,
                    old_reduced if old_reduced is not None else 0,
                    old_comfort,
                    old_reduced,
                )
            except Exception:
                self.device.data[NuosSplitProperties.COMFORT_TEMP] = old_comfort
                self.device.data[NuosSplitProperties.PROC_REQ_TEMP] = old_proc
                self.coordinator.async_set_updated_data(None)
                raise
            self.coordinator.async_set_updated_data(None)
            return

        await self.device.async_set_water_heater_temperature(temperature)
        self.coordinator.async_set_updated_data(None)

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        if self.device.whe_type == WheType.NuosSplit:
            old_op_mode = self.device.data.get(NuosSplitProperties.OP_MODE)
            new_mode_val = self.device.water_heater_mode[operation_mode].value
            self.device.data[NuosSplitProperties.OP_MODE] = new_mode_val
            self.coordinator.async_set_updated_data(None)
            try:
                await self.device.api._async_post(
                    f"{self.device.api._AristonAPI__api_url}{ARISTON_VELIS}/{PlantData.Slp.value}/{self.device.gw}/operativeMode",
                    {
                        "new": new_mode_val,
                        "old": old_op_mode if old_op_mode is not None else 1,
                    },
                )
            except Exception:
                self.device.data[NuosSplitProperties.OP_MODE] = old_op_mode
                self.coordinator.async_set_updated_data(None)
                raise
            self.device.data[NuosSplitProperties.OP_MODE] = new_mode_val
            self.coordinator.async_set_updated_data(None)
            return

        await self.device.async_set_water_heater_operation_mode(operation_mode)
        self.coordinator.async_set_updated_data(None)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the water heater off."""
        old_power = self.device.data.get(VelisBaseDeviceProperties.ON)
        self.device.data[VelisBaseDeviceProperties.ON] = False
        self.coordinator.async_set_updated_data(None)
        try:
            await self.device.async_set_power(False)
        except Exception:
            self.device.data[VelisBaseDeviceProperties.ON] = old_power
            self.coordinator.async_set_updated_data(None)
            raise
        self.coordinator.async_set_updated_data(None)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the water heater on."""
        old_power = self.device.data.get(VelisBaseDeviceProperties.ON)
        self.device.data[VelisBaseDeviceProperties.ON] = True
        self.coordinator.async_set_updated_data(None)
        try:
            await self.device.async_set_power(True)
        except Exception:
            self.device.data[VelisBaseDeviceProperties.ON] = old_power
            self.coordinator.async_set_updated_data(None)
            raise
        self.coordinator.async_set_updated_data(None)
