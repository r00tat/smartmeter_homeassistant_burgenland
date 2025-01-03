# build base images
set -eo pipefail

VERSION=$(yq -r '.version' config.yaml)

function builder() {
  docker run \
    --rm \
    -it \
    --privileged \
    -v ${PWD}:/data \
    -v /var/run/docker.sock:/var/run/docker.sock:ro \
    ghcr.io/home-assistant/aarch64-builder:latest --target /data \
    --docker-hub "${DOCKERHUB_USER}" \
    --docker-user "${DOCKERHUB_USER}" \
    --docker-password "${DOCKERHUB_PASSWORD}" \
    $@
}

for ARCH in aarch64 amd64; do
  echo "Building version ${VERSION} for ${ARCH}"
  builder --${ARCH}
  # docker buildx build -t paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:$VERSION --build-arg BUILD_FROM=homeassistant/${ARCH}-base-python:latest --platform linux/${ARCH} .
  # docker tag paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:$VERSION paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:latest
  # docker push paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:$VERSION
  # docker push paulwoelfel/smartmeter_homeassistant_burgenland_${ARCH}:latest

  echo "completed build for ${ARCH}."
done
