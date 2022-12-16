#!/bin/bash
# build and push the image
set -eo pipefail

ARCH=$(uname -m)
if [[ "$ARCH" =~ "armv7.*" ]]; then
  ARCH="armv7"
elif [[ "$ARCH" == "x86_64" ]]; then
  ARCH="amd64"
fi

if [[ -z "$(which yq)" && -n "$(which apk)" ]]; then
  apk add yq
fi

VERSION=$(yq -r '.version' config.yaml)

echo "Building version ${VERSION} for ${ARCH}"

docker build -t paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:$VERSION --build-arg BUILD_FROM=homeassistant/${ARCH}-base-python:latest .
docker tag paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:$VERSION paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:latest
docker push paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:$VERSION
docker push paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:latest

echo "done."
