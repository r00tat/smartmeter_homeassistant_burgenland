ARG BUILD_FROM=homeassistant/aarch64-base-python:latest
FROM $BUILD_FROM

ENV LANG=C.UTF-8

# Install requirements for add-on
RUN apk --no-cache --no-progress upgrade && \
    apk --no-cache --no-progress add jq patch && \
    rm -rf /tmp/*

WORKDIR /app

# Copy data for add-on
COPY requirements.txt ./
RUN python3 -m pip install uv && uv venv && \
    source .venv/bin/activate && \
    uv pip install -r requirements.txt

RUN cd .venv/lib/python3.*/site-packages/gurux_dlms && sed -i 's@if buff.available < len_:@if buff.available() < len_:@g' GXDLMS.py

COPY run.sh config.yaml ./
COPY  meter ./meter/

CMD [ "/app/run.sh" ]