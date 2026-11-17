# Build context is the repository root, so the image installs the
# smartmeter-austria library from the same commit as the app:
#   docker build -f smartmeter/Dockerfile .
# Supervisor no longer reads build.yaml and stopped supplying BUILD_FROM by
# default in 2026.04, so the base image is defined here and here only.
ARG BUILD_FROM=ghcr.io/hassio-addons/base-python:stable
FROM $BUILD_FROM

ENV LANG=C.UTF-8

WORKDIR /app

COPY smartmeter/requirements.txt ./
COPY packages/smartmeter-austria /tmp/smartmeter-austria
RUN apk add --no-cache libxml2 libxslt && \
    pip install --no-cache-dir -r requirements.txt /tmp/smartmeter-austria && \
    python3 -m smartmeter_austria.fix_source_encoding gurux_dlms gurux_common && \
    rm -rf /tmp/smartmeter-austria

COPY smartmeter/run.sh smartmeter/config.yaml ./
COPY smartmeter/meter ./meter/
# fail the build (and the PR test build) if the app cannot even be imported,
# e.g. a dependency that is incompatible with the base image's Python (#128)
RUN python3 -c "import meter.smartmeter"

CMD [ "/app/run.sh" ]
