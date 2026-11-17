# Build context is smartmeter/ (also for a local Supervisor build); the
# image installs the smartmeter-austria library from smartmeter-austria/
# of the same commit.
# Supervisor no longer reads build.yaml and stopped supplying BUILD_FROM by
# default in 2026.04, so the base image is defined here and here only.
ARG BUILD_FROM=ghcr.io/hassio-addons/base-python:stable
FROM $BUILD_FROM

ENV LANG=C.UTF-8

WORKDIR /app

COPY requirements.txt ./
COPY smartmeter-austria /tmp/smartmeter-austria
RUN apk add --no-cache libxml2 libxslt && \
    pip install --no-cache-dir -r requirements.txt /tmp/smartmeter-austria && \
    python3 -m smartmeter_austria.fix_source_encoding gurux_dlms gurux_common && \
    rm -rf /tmp/smartmeter-austria

COPY run.sh config.yaml ./
COPY meter ./meter/
# fail the build (and the PR test build) if the app cannot even be imported,
# e.g. a dependency that is incompatible with the base image's Python (#128)
RUN python3 -c "import meter.smartmeter"

CMD [ "/app/run.sh" ]
