#!/bin/bash
set -e

# Verify secrets directory is mounted (contains .github-token from refresher)
if [ ! -f "/secrets/.github-token" ]; then
    echo "ERROR: /secrets/.github-token not found"
    echo "Ensure github-token-refresher is running and ~/.jib-gateway/ is mounted"
    exit 1
fi
if [ ! -f "/secrets/gateway-secret" ]; then
    echo "ERROR: /secrets/gateway-secret not mounted"
    exit 1
fi

# Export gateway secret for authentication
export JIB_GATEWAY_SECRET=$(cat /secrets/gateway-secret)

# github_client.py reads directly from /secrets/.github-token
# No symlinks needed since we mount the directory

# Run gateway on all interfaces (for container networking)
exec python3 gateway.py --host 0.0.0.0 --port 9847
