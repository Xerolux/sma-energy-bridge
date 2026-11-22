ARG BUILD_FROM
FROM ${BUILD_FROM}
ARG BUILD_VERSION
ARG BUILD_ARCH
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="addon" \
      io.hass.arch="${BUILD_ARCH}"
RUN apk add --no-cache python3
WORKDIR /app
COPY main.py /app/main.py
CMD ["python3", "-u", "/app/main.py"]
