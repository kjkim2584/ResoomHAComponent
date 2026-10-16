"""Constants backed by the captured Resoom UI and protocol."""

from homeassistant.const import Platform

DOMAIN = "resoom"
PLATFORMS = [Platform.FAN, Platform.NUMBER, Platform.SELECT, Platform.SWITCH, Platform.SENSOR]
PRESSURE_MODES = {"positive": 1, "balanced": 0, "negative": -1}
FUNCTIONS = {"cutoff": 1, "intake": 2, "exhaust": 4, "sleep": 8, "bypass": 16}
OPERATING_MODES = {
    1: "sensing",
    2: "smart",
    3: "immediate",
    4: "ventilation_standby",
    5: "cutoff",
    6: "reservation",
    7: "stopped",
}
