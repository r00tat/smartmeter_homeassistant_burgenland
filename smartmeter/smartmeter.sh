#!/bin/bash
# smartmeter start script
set -euo pipefail

# make sure we have the cwd in the base folder
cd "$(dirname "$0")"

# The reader core lives in ../packages/smartmeter-austria. Install it
# editable, so a `git pull` takes effect on the next start without
# reinstalling. uv skips everything that is already up to date.
if [[ ! -d .venv ]]; then
  uv venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
uv pip install --quiet -r requirements.txt -e ../packages/smartmeter-austria
# gurux ships Latin-1 sources; rewrite them once so Python can import them.
python3 -m smartmeter_austria.fix_source_encoding gurux_dlms gurux_common

exec python3 -m meter -c "$PWD/smartmeter-config.yaml"
