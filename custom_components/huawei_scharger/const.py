"""Constants for the Huawei SCharger integration."""

from .portal.endpoints import DEFAULT_HOST

DOMAIN = "huawei_scharger"
MANUFACTURER = "Huawei"
DEVICE_NAME = "Huawei SCharger"
PLANT_DEVICE_NAME = "FusionSolar plant"

CONF_HOST = "host"
CONF_STATION_DN = "station_dn"
CONF_STATION_NAME = "station_name"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORTAL_HOST = DEFAULT_HOST
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30

PLATFORMS = ["number", "select", "sensor", "switch"]
