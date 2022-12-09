ARG BUILD_FROM=homeassistant/aarch64-base:latest
FROM $BUILD_FROM

ENV LANG C.UTF-8

# Install requirements for add-on
RUN apk --no-cache --no-progress upgrade && \
    apk --no-cache --no-progress add jq python3 py3-pip && \
    rm -rf /tmp/*

WORKDIR /app

# Copy data for add-on
COPY requirements.txt ./
RUN python3 -m venv . && \
    source bin/activate && \
    pip3 install -r requirements.txt

COPY run.sh ./
COPY  meter ./meter/

CMD [ "/app/run.sh" ]