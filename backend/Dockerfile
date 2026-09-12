FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS builder

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /app

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runner

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /app

# Install runtime deps (no gcc needed)
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy Python deps from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app code
COPY . .

# Create data dir + set perms (as root)
RUN mkdir -p /data && chmod 755 /data

# Add entrypoint (as root) that fixes data perms then drops to walletpress user
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create non-root user
RUN groupadd -r walletpress && useradd -r -g walletpress -d /app -s /sbin/nologin walletpress

# Chown app + data dirs to walletpress
RUN chown -R walletpress:walletpress /app /data

USER walletpress

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8010/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]
