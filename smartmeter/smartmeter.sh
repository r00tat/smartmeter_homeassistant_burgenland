#!/bin/bash
# smartmeter start script
set -euo pipefail

# systemd starts this script with a minimal PATH. The uv installer puts
# uv into ~/.local/bin (older versions: ~/.cargo/bin), so add both.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null; then
  echo "uv not found in PATH ($PATH), see docs/installation.md" >&2
  exit 1
fi

# make sure we have the cwd in the base folder
cd "$(dirname "$0")"

# The reader core lives in smartmeter-austria/. Install it
# editable, so a `git pull` takes effect on the next start without
# reinstalling. uv skips everything that is already up to date.
if [[ ! -d .venv ]]; then
  uv venv --python 3.15
fi
# shellcheck source=/dev/null
source .venv/bin/activate
uv pip install --quiet -r requirements.txt -e ./smartmeter-austria

exec python3 -m meter -c "$PWD/smartmeter-config.yaml"
