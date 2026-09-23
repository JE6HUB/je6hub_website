FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 開発用ツール (git, psql クライアントなど)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        git \
        openssh-client \
        postgresql-client \
        curl \
        less \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

WORKDIR /app
