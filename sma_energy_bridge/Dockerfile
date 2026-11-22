FROM ghcr.io/home-assistant/base:latest
ARG BUILD_VERSION=0.2.0
ARG BUILD_ARCH=amd64
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}"
RUN apk add --no-cache python3
WORKDIR /app
COPY main.py /app/main.py
CMD ["python3", "-u", "/app/main.py"]
