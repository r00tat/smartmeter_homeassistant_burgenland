# Supervisor no longer reads build.yaml and stopped supplying BUILD_FROM by
# default in 2026.04, so the base image is defined here and here only.
ARG BUILD_FROM=ghcr.io/hassio-addons/base-python:stable
FROM $BUILD_FROM

ENV LANG=C.UTF-8

WORKDIR /app

COPY requirements.txt ./
RUN apk add --no-cache libxml2 libxslt && \
    pip install --no-cache-dir -r requirements.txt

COPY run.sh config.yaml ./
COPY meter ./meter/

CMD [ "/app/run.sh" ]
