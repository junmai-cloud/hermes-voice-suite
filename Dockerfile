FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VOICE_TECH_LEDGER_PATH=/var/lib/hermes/technical-ledger.sqlite3

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        ffmpeg \
        libopus0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install ".[voice]"

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin hermes \
    && mkdir --parents /var/lib/hermes \
    && chown --recursive hermes:hermes /var/lib/hermes

USER hermes

ENTRYPOINT ["voice-bot"]
