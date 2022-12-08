#!/usr/bin/env bashio
set -eo pipefail

CONFIG_PATH=/data/options.json

CONFIGFILE="$(bashio::config 'configfile')"

# start the programm
# make sure we have the cwd in the base folder
cd /app

source bin/activate

bashio::log.info "starting smartmeter app"
python3 -m meter -c $CONFIGFILE
