#!/bin/bash
# smartmeter start script

# make sure we have the cwd in the base folder
cd $(dirname "$0")

# make sure we have a valid python venv
if [[ ! -d .venv ]]; then
  uv venv
  source .venv/bin/activate
  uv pip install -r requirements.txt
fi

source .venv/bin/activate
python3 -m meter -c $PWD/smartmeter-config.yaml
