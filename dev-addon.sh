#!/bin/bash
# Copies the add-on (smartmeter/, including the smartmeter-austria library)
# from the working tree to a Home Assistant host as a local add-on, so the
# Supervisor builds it from this checkout instead of pulling the published
# image. Needs the "Advanced SSH & Web Terminal" (or "Terminal & SSH") add-on
# with rsync on the host, and yq locally.
set -euo pipefail

HA_HOST="${HA_HOST:-root@homeassistant.local}"
HA_SSH_PORT="${HA_SSH_PORT:-22}"
TARGET_DIR="/addons/smartmeter_dev"
# Local add-ons get the "local_" prefix in front of their slug.
ADDON_SLUG="local_smartmeter_bgld_mqtt"

usage() {
  cat <<EOF
Usage: $0 [--no-rebuild]

  --no-rebuild  Only copy the files; do not reload and rebuild the add-on.

Environment variables:
  HA_HOST      SSH target (default: root@homeassistant.local)
  HA_SSH_PORT  SSH port (default: 22)

The add-on shows up under Settings > Add-ons > Add-on Store > Local add-ons
as "Smartmeter Burgenland MQTT (dev)". Install it there once; later runs
rebuild it with the current working tree.
EOF
}

REBUILD=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-rebuild) REBUILD=0 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 1 ;;
  esac
  shift
done

cd "$(dirname "$0")"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

rsync -a \
  --exclude .venv --exclude __pycache__ --exclude '*.pyc' \
  --exclude .pytest_cache --exclude .mypy_cache --exclude .ruff_cache \
  --exclude tests --exclude scripts \
  --exclude smartmeter-config.yaml \
  smartmeter/ "$STAGE/"

# Without "image" the Supervisor builds the add-on locally. A version that
# changes with every commit makes it offer the update.
VERSION="$(yq -r '.version' smartmeter/config.yaml)-dev.$(git rev-parse --short HEAD)"
if ! git diff --quiet HEAD -- smartmeter; then
  VERSION="${VERSION}.dirty$(date +%s)"
fi
yq -i "del(.image) | .name = .name + \" (dev)\" | .version = \"${VERSION}\"" \
  "$STAGE/config.yaml"

echo "Copying add-on ${VERSION} to ${HA_HOST}:${TARGET_DIR}"
rsync -a --delete -e "ssh -p ${HA_SSH_PORT}" "$STAGE/" "${HA_HOST}:${TARGET_DIR}/"

if [[ "$REBUILD" -eq 1 ]]; then
  # shellcheck disable=SC2029  # ADDON_SLUG is meant to expand locally
  ssh -p "$HA_SSH_PORT" "$HA_HOST" "ha store reload && \
    if ha addons info ${ADDON_SLUG} >/dev/null 2>&1; then \
      ha addons update ${ADDON_SLUG} || ha addons rebuild ${ADDON_SLUG}; \
    else echo 'Add-on not installed yet: install it from the local add-ons in the store.'; fi"
fi
