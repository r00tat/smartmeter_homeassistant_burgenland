#!/bin/sh
set -e

CONFIG="${SMARTMETER_CONFIG:-/config/smartmeter-config.yaml}"

if [ ! -f "$CONFIG" ] || [ ! -s "$CONFIG" ]; then
    echo "ERROR: Config file not found or empty: $CONFIG" >&2
    echo "" >&2
    echo "Mount your configuration file and retry, e.g.:" >&2
    echo "  docker run -v /path/to/your/smartmeter-config.yaml:/config/smartmeter-config.yaml smartmeter-standalone" >&2
    echo "" >&2
    echo "Or point to a different path via the SMARTMETER_CONFIG environment variable:" >&2
    echo "  docker run -e SMARTMETER_CONFIG=/myconfig.yaml -v /path/to/myconfig.yaml:/myconfig.yaml smartmeter-standalone" >&2
    exit 1
fi

cd /app
exec python3 -m meter -c "$CONFIG"
