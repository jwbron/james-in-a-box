#!/bin/bash
set -e

# Verify secrets are mounted
if [ ! -f "/secrets/.github-token" ]; then
    echo "ERROR: /secrets/.github-token not mounted"
    exit 1
fi
if [ ! -f "/secrets/gateway-secret" ]; then
    echo "ERROR: /secrets/gateway-secret not mounted"
    exit 1
fi

# Setup expected paths for gateway.py
mkdir -p "$HOME/.jib-sharing" "$HOME/.config/jib"
ln -sf /secrets/.github-token "$HOME/.jib-sharing/.github-token"
ln -sf /secrets/gateway-secret "$HOME/.config/jib/gateway-secret"

# Export gateway secret for authentication
export JIB_GATEWAY_SECRET=$(cat /secrets/gateway-secret)

# Run gateway on all interfaces (for container networking)
exec python3 gateway.py --host 0.0.0.0 --port 9847
