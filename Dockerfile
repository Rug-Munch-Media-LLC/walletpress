# WalletPress — root Dockerfile (development)
# Canonical build config lives in backend/Dockerfile.
# This is a convenience alias so docker-compose works from repo root.
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc=4:14.2.0-1 \
    libffi-dev=3.4.8-2 \
    libssl-dev=3.5.6-1~deb13u2 && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Security: run as non-root user
RUN groupadd -r walletpress && useradd -r -g walletpress -d /app -s /sbin/nologin walletpress && \
    chown -R walletpress:walletpress /app
USER walletpress

EXPOSE 8010
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]
