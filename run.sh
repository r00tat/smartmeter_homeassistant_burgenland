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

set -x
bashio::log.info "getting raw config"
service="mqtt"
config=$(bashio::api.supervisor GET "/services/${service}" false)
echo "${config}"

bashio::log.info "requesting mqtt config"
MQTT_HOST=$(bashio::services mqtt "host")
MQTT_USER=$(bashio::services mqtt "username")
MQTT_PASSWORD=$(bashio::services mqtt "password")
bashio::log.info "MQTT ${MQTT_HOST} ${MQTT_USER}"

CONFIGFILE=$(mktemp)
bashio::log.info "generating config file ${CONFIGFILE}"
jq ".mqtt.host=\"${MQTT_HOST}\" | .mqtt.user=\"${MQTT_USER}\" | .mqtt.password=\"${MQTT_PASSWORD}\"" "$CONFIG_PATH" > $CONFIGFILE


# start the programm
# make sure we have the cwd in the base folder
cd /app

source bin/activate

bashio::log.info "starting smartmeter app"
python3 -m meter -c "$CONFIGFILE"
