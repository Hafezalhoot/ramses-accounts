# Trusted image built from the reviewed main branch; PR content is mounted only at runtime.
FROM python:3.13-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY requirements.lock /opt/ramses/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/ramses/requirements.txt 'playwright==1.64.1' \
    && python -m playwright install --with-deps chromium \
    && python -m pip check
WORKDIR /work
