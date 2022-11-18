#!/bin/bash
# smartmeter start script

# make sure we have the cwd in the base folder
cd $(dirname "$0")

# make sure we have a valid python venv
if [[ ! -d bin || ! -d lib ]]; then
  python3 -m venv .
  source bin/activate
  pip3 install -r requirements.txt
fi

source bin/activate
python3 -m meter -c $PWD/config.yaml
