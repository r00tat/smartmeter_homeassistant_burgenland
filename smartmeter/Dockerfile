# Use python:3.13-slim-trixie (per review §7.3 fallback): HA base-python images
# have not been published for Python 3.13 (latest is 3.11-alpine3.18), so we use
# the official Debian trixie Python image and install bashio manually for run.sh.
ARG BUILD_FROM=python:3.13-slim-trixie
FROM $BUILD_FROM

ENV LANG=C.UTF-8

# Install runtime tools and bashio (required by run.sh shebang).
ARG BASHIO_VERSION=v0.16.2
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        bash ca-certificates curl git jq tzdata && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir -p /usr/src && \
    git clone --depth 1 --branch "${BASHIO_VERSION}" \
        https://github.com/hassio-addons/bashio.git /usr/src/bashio && \
    mv /usr/src/bashio/lib /usr/lib/bashio && \
    ln -s /usr/lib/bashio/bashio /usr/bin/bashio && \
    rm -rf /usr/src/bashio

WORKDIR /app

# Copy data for add-on
COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir uv && uv venv && \
    . .venv/bin/activate && \
    uv pip install -r requirements.txt

COPY run.sh config.yaml ./
COPY  meter ./meter/

CMD [ "/app/run.sh" ]
