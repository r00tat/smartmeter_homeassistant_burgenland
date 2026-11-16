"""Constants for the Smartmeter Austria integration."""

DOMAIN = "smartmeter_at"

CONF_METER_TYPE = "meter_type"
CONF_PORT = "port"
CONF_KEY = "key"
CONF_INTERFACE_TYPE = "interface_type"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_METER_TYPE = "burgenland"
# Lower case: Home Assistant requires lower-case selector option keys for
# translations. Converted to the core's "OPTICAL"/"PHYSICAL" when building
# the reader.
INTERFACE_TYPES = ["optical", "physical"]
DEFAULT_INTERFACE_TYPE = "optical"
# Seconds between entity updates. The meter pushes every 1-5 s; writing each
# telegram to the recorder would bloat the database.
DEFAULT_UPDATE_INTERVAL = 10

DATA_CORE = f"{DOMAIN}_core"
