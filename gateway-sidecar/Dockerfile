FROM python:3.11-slim

# Install git, gh CLI, and Squid proxy for Phase 2 network lockdown
RUN apt-get update && apt-get install -y \
    git curl gnupg \
    # Squid HTTP proxy with SSL support for SNI inspection
    squid-openssl \
    # OpenSSL for certificate generation
    openssl \
    # gosu for dropping privileges (Squid needs root start, gateway needs non-root)
    gosu \
    && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
    dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
    https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y gh && \
    rm -rf /var/lib/apt/lists/*

# Generate self-signed certificate for Squid SSL bump (peek/splice, not MITM)
# This certificate is used only to inspect the SNI field, not to decrypt traffic
# Using 10-year validity (3650 days) since this is internal-only and doesn't
# require the security properties of short-lived certificates (no chain of trust)
RUN mkdir -p /etc/squid/ssl /var/log/squid /var/spool/squid && \
    openssl req -new -newkey rsa:2048 -sha256 -days 3650 -nodes -x509 \
        -subj "/CN=jib-gateway-proxy/O=jib/C=US" \
        -keyout /etc/squid/squid-ca.pem \
        -out /etc/squid/squid-ca.pem && \
    # Squid runs as proxy user - ensure it can read the certificate
    chown proxy:proxy /etc/squid/squid-ca.pem && \
    chmod 400 /etc/squid/squid-ca.pem && \
    chown -R proxy:proxy /var/log/squid /var/spool/squid && \
    # Initialize Squid cache directories
    /usr/sbin/squid -z -N 2>/dev/null || true

WORKDIR /app

# Copy gateway code
COPY gateway-sidecar/*.py ./

# Copy shared modules (jib_logging for logging, jib_config for config parsing)
COPY shared/jib_logging/ ./jib_logging/
COPY shared/jib_config/ ./jib_config/

# Copy config module (repo_config needed by github_client for incognito mode)
COPY config/repo_config.py /config/

# Copy Squid configuration for network lockdown
# squid.conf is the restrictive allowlist-based config (used in private mode)
# squid-allow-all.conf allows full internet access (used in public mode)
COPY gateway-sidecar/squid.conf /etc/squid/squid.conf
COPY gateway-sidecar/squid-allow-all.conf /etc/squid/squid-allow-all.conf
COPY gateway-sidecar/allowed_domains.txt /etc/squid/allowed_domains.txt
RUN chmod 644 /etc/squid/squid.conf /etc/squid/squid-allow-all.conf /etc/squid/allowed_domains.txt

# Copy config validator for startup checks
COPY gateway-sidecar/config_validator.py ./config_validator.py

# Install dependencies
RUN pip install --no-cache-dir flask waitress pyyaml requests

ENV PYTHONPATH="/app"
# Expose both gateway API port and Squid proxy port
EXPOSE 9847 3128

COPY gateway-sidecar/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
