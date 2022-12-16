#!/usr/bin/env bashio
set -eo pipefail

CONFIG_PATH=/data/options.json

bashio::log.info "config file:"
cat $CONFIG_PATH
bashio::log.info "end file"
# bashio::log.info "config option configfile: $(jq -r '.configfile' $CONFIG_PATH)"

CONFIGFILE="$CONFIG_PATH"
# CONFIGFILE="$(bashio::config 'configfile')"
# CONFIGFILE=$(jq -r '.configfile' $CONFIG_PATH)

if [[ -z "$CONFIGFILE" || "$CONFIGFILE" == "null" ]]; then
    bashio::log.error "No config file option provided. Please configure it in the addon options!"
    exit 1
fi

# start the programm
# make sure we have the cwd in the base folder
cd /app

source bin/activate

bashio::log.info "starting smartmeter app"
python3 -m meter -c "$CONFIGFILE"
