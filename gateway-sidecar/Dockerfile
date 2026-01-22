FROM python:3.11-slim

# Install git and gh CLI
RUN apt-get update && apt-get install -y git curl gnupg && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
    dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
    https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y gh && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy gateway code
COPY gateway-sidecar/*.py ./

# Copy shared modules (jib_logging for logging, jib_config for config parsing)
COPY shared/jib_logging/ ./jib_logging/
COPY shared/jib_config/ ./jib_config/

# Install dependencies
RUN pip install --no-cache-dir flask waitress pyyaml requests

ENV PYTHONPATH="/app"
EXPOSE 9847

COPY gateway-sidecar/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
