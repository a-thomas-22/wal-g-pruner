# Dockerfile
# Uses multi-stage builds requiring Docker 17.05 or higher
# See https://docs.docker.com/develop/develop-images/multistage-build/

# Version definitions for easy updates
ARG PYTHON_VERSION=3.12-slim
ARG POETRY_VERSION=1.4.1
ARG WAL_G_VERSION=v2.0.1

# Creating a python base with shared environment variables
FROM python:${PYTHON_VERSION} as python-base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PYSETUP_PATH="/opt/pysetup" \
    VENV_PATH="/opt/pysetup/.venv"

ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
    git \
    ca-certificates \
    wget \
    # Add any other necessary packages here
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# builder-base is used to build dependencies and download wal-g
FROM python-base as builder-base
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
    curl 

# Install Poetry - respects $POETRY_VERSION & $POETRY_HOME
ENV POETRY_VERSION=${POETRY_VERSION}
ENV POETRY_HOME=/opt/poetry
RUN curl -sSL https://install.python-poetry.org | python -

# We copy our Python requirements here to cache them
# and install only runtime deps using poetry
WORKDIR $PYSETUP_PATH
COPY ./poetry.lock ./pyproject.toml ./
RUN poetry install --no-dev

# Install wget and download wal-g
ARG TARGETARCH
RUN apt-get update && apt-get install -y wget && rm -rf /var/lib/apt/lists/* && \
    if [ "${TARGETARCH}" = "arm64" ]; then \
    export WALG_ARCH="aarch64"; \
    else \
    export WALG_ARCH="${TARGETARCH}"; \
    fi && \
    wget -O /wal-g-pg-ubuntu-20.04.tar.gz https://github.com/wal-g/wal-g/releases/download/v2.0.1/wal-g-pg-ubuntu-20.04-${WALG_ARCH}.tar.gz
RUN tar -xvf /wal-g-pg-ubuntu-20.04.tar.gz && (mv wal-g-pg-ubuntu20.04-* /usr/local/bin/wal-g || mv wal-g-pg-ubuntu-20.04-* /usr/local/bin/wal-g)

# 'production' stage uses the clean 'python-base' stage and copies
# in only our runtime deps that were installed in the 'builder-base'
FROM python-base as production
ENV FASTAPI_ENV=production

COPY --from=builder-base $VENV_PATH $VENV_PATH
COPY --from=builder-base /usr/bin/git /usr/bin/git
COPY --from=builder-base /usr/local/bin/wal-g /usr/local/bin/wal-g

RUN adduser --disabled-password --gecos '' --uid 1000 walgpruner
USER walgpruner

COPY . /app
WORKDIR /app

CMD ["python", "main.py"]
