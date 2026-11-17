#!/bin/bash
# Starts a Home Assistant test instance in a container and syncs the
# smartmeter_at integration and the smartmeter-austria library from the
# working tree into its config directory.
set -euo pipefail

COMPONENT="smartmeter_at"
LIBRARY="smartmeter-austria"
DOCKER_NAME="smartmeter-ha-dev"
IMAGE="ghcr.io/home-assistant/home-assistant:stable"
# Host port. Inside the container Home Assistant always listens on 8123.
# The default differs from 8123 so this instance can run next to other
# Home Assistant dev containers.
HTTP_PORT="${HTTP_PORT:-8124}"
# Optional serial device passed into the container, e.g. /dev/ttyUSB0 or
# /dev/serial/by-id/usb-...  Only works on Linux hosts: Docker Desktop on
# macOS/Windows cannot pass USB serial devices into containers.
SERIAL_DEVICE="${SERIAL_DEVICE:-}"

RECREATE=0
FOLLOW_LOGS=1

usage() {
  cat <<EOF
Usage: $0 [--recreate] [--no-logs]

  --recreate   Remove and recreate the container. Needed when the port,
               image or serial device changed.
  --no-logs    Do not follow the container logs after starting.

Environment variables:
  HTTP_PORT      Host port for the web UI (default: 8124)
  SERIAL_DEVICE  Serial device to pass into the container (Linux only)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --recreate) RECREATE=1 ;;
    --no-logs) FOLLOW_LOGS=0 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

log() { printf '\n==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*" >&2; }

cd "$(dirname "$0")"

# --- Prerequisites -----------------------------------------------------------

log "Checking prerequisites"
if ! docker info >/dev/null 2>&1; then
  warn "Docker is not reachable - is the daemon running?"
  exit 1
fi
info "docker: reachable"

if [[ -n "$SERIAL_DEVICE" && ! -e "$SERIAL_DEVICE" ]]; then
  warn "SERIAL_DEVICE $SERIAL_DEVICE does not exist."
  exit 1
fi

# --- Mirror the integration into the test config -----------------------------

log "Syncing custom_components/$COMPONENT to config/"
mkdir -p "config/custom_components"
# A symlink here would make rsync --delete write through it into its target.
if [[ -L "config/custom_components/$COMPONENT" ]]; then
  warn "config/custom_components/$COMPONENT is a symlink - remove it first."
  exit 1
fi
# --delete so files removed in the repo do not linger and get loaded.
rsync -a --delete --exclude '__pycache__' \
  "custom_components/$COMPONENT/" "config/custom_components/$COMPONENT/"
info "$(find "config/custom_components/$COMPONENT" -name '*.py' | wc -l | tr -d ' ') Python files mirrored"

# The manifest pins smartmeter-austria; Home Assistant would install that
# version from PyPI. The container installs this copy at every start instead
# (see STARTUP below), so library changes show up without a release.
log "Syncing packages/$LIBRARY to config/.dev/"
mkdir -p config/.dev
rsync -a --delete --exclude '__pycache__' --exclude 'tests' --exclude 'scripts' \
  "packages/$LIBRARY/" "config/.dev/$LIBRARY/"

# --- Container ---------------------------------------------------------------

# Install the synced library, then hand over to the image's own entrypoint.
# Runs again on every docker restart. The version equals the manifest pin, so
# Home Assistant treats the requirement as installed and keeps this copy.
STARTUP="uv pip install --quiet --reinstall-package $LIBRARY /config/.dev/$LIBRARY && exec /init"

DOCKER_RUN_ARGS=(
  --name "$DOCKER_NAME"
  --entrypoint /bin/sh
  -e TZ=Europe/Vienna
  -v "$PWD/config:/config"
  # Publish on localhost only - the test instance does not belong in the LAN.
  -p "127.0.0.1:$HTTP_PORT:8123"
)

if [[ -n "$SERIAL_DEVICE" ]]; then
  # Map to the same path so the config flow shows the familiar name.
  DOCKER_RUN_ARGS+=(--device "$SERIAL_DEVICE:$SERIAL_DEVICE")
  info "serial device: $SERIAL_DEVICE"
else
  info "no SERIAL_DEVICE set - the config flow will not find a meter"
fi

# Exact match: -f name=... is a substring match otherwise.
container_id="$(docker ps -a -q -f "name=^${DOCKER_NAME}\$")"

# Port mapping, image and devices are fixed at docker run time and cannot be
# changed by docker restart - detect a mismatch instead of silently keeping
# the old container.
if [[ -n "$container_id" && "$RECREATE" -eq 0 ]]; then
  # HostConfig.PortBindings, not NetworkSettings.Ports: the latter is empty
  # for a stopped container and would fake a change.
  current_port="$(docker inspect "$container_id" \
    --format '{{with index .HostConfig.PortBindings "8123/tcp"}}{{(index . 0).HostPort}}{{end}}')"
  current_device="$(docker inspect "$container_id" \
    --format '{{range .HostConfig.Devices}}{{.PathOnHost}}{{end}}')"
  current_cmd="$(docker inspect "$container_id" --format '{{join .Config.Cmd " "}}')"
  if [[ "$current_port" != "$HTTP_PORT" ]]; then
    warn "Existing container publishes port ${current_port:-<none>}, wanted $HTTP_PORT - recreating it."
    RECREATE=1
  elif [[ "$current_device" != "$SERIAL_DEVICE" ]]; then
    warn "Existing container has serial device '${current_device}', wanted '${SERIAL_DEVICE}' - recreating it."
    RECREATE=1
  elif [[ "$current_cmd" != "-c $STARTUP" ]]; then
    warn "Existing container does not install the local $LIBRARY at startup - recreating it."
    RECREATE=1
  fi
fi

if [[ -n "$container_id" && "$RECREATE" -eq 1 ]]; then
  log "Removing existing container $DOCKER_NAME"
  # Stop gracefully first so Home Assistant closes its SQLite database in
  # config/; rm -f alone would be a SIGKILL.
  docker stop -t 30 "$DOCKER_NAME" >/dev/null 2>&1 || true
  docker rm -f "$DOCKER_NAME" >/dev/null
  container_id=""
fi

if [[ -z "$container_id" ]]; then
  log "Starting new container $DOCKER_NAME"
  info "image: $IMAGE"
  docker run -d "${DOCKER_RUN_ARGS[@]}" "$IMAGE" -c "$STARTUP" >/dev/null
else
  log "Restarting existing container $DOCKER_NAME"
  docker restart "$DOCKER_NAME" >/dev/null
fi

log "Home Assistant is starting - web UI: http://localhost:$HTTP_PORT"
info "The first start takes 20-30 s (plus installing the integration's requirements)."
info "Reload the integration: run ./dev.sh again (syncs and restarts)."

if [[ "$FOLLOW_LOGS" -eq 1 ]]; then
  # Ctrl-C stops the test instance instead of only detaching from the logs.
  # Use --no-logs to keep the container running in the background.
  stop_container() {
    trap - INT TERM
    log "Stopping container $DOCKER_NAME"
    # Home Assistant needs more than docker stop's default 10 s grace period
    # to shut down cleanly.
    docker stop -t 30 "$DOCKER_NAME" >/dev/null
    info "Stopped. Start again: ./dev.sh"
    exit 0
  }
  trap stop_container INT TERM

  log "Container logs - Ctrl-C stops the test instance"
  # If tailing ends on its own, the container is gone or crashed.
  docker logs -n 10 -f "$DOCKER_NAME" || true
  trap - INT TERM
  warn "Log tailing ended - the container is no longer running."
  docker ps -a -f "name=^${DOCKER_NAME}\$" --format '    {{.Names}}: {{.Status}}'
fi
