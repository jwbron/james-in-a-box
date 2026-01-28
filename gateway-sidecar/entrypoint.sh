#!/bin/bash
set -e

# =============================================================================
# Gateway Sidecar Entrypoint
#
# Handles both Phase 1 (legacy) and Phase 2 (network lockdown) modes.
# In Phase 2, also starts Squid proxy for network filtering.
# =============================================================================

echo "=== Gateway Sidecar Starting ==="

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

# =============================================================================
# Phase 2: Start Squid Proxy (if configured)
# =============================================================================

SQUID_CONF="/etc/squid/squid.conf"
NETWORK_LOCKDOWN_MODE="${JIB_NETWORK_MODE:-}"

start_squid() {
    echo "Starting Squid proxy for network lockdown..."

    # Ensure log and spool directories exist and are writable
    # Note: We may not have permission to chown (running as non-root), so we
    # check writability directly and configure Squid to run with current user.
    mkdir -p /var/log/squid /var/spool/squid

    # Try to set ownership for squid's preferred user, but don't fail if we can't
    if chown -R proxy:proxy /var/log/squid /var/spool/squid 2>/dev/null; then
        echo "  Log directories owned by proxy:proxy"
    else
        # Running as non-root - verify directories are writable
        if [ -w /var/log/squid ] && [ -w /var/spool/squid ]; then
            echo "  Log directories writable by current user ($(id -un))"
        else
            echo "WARNING: Log directories may not be writable - Squid logging may fail"
        fi
    fi

    # Initialize cache directories if needed
    if [ ! -d "/var/spool/squid/00" ]; then
        /usr/sbin/squid -z -N 2>/dev/null || true
    fi

    # Start Squid in daemon mode
    /usr/sbin/squid -f "$SQUID_CONF"

    # Wait for Squid to start
    local elapsed=0
    local max_wait=30
    while [ $elapsed -lt $max_wait ]; do
        if /usr/sbin/squid -k check 2>/dev/null; then
            echo "Squid proxy started successfully on port 3128"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
        echo "Waiting for Squid to start... ($elapsed/$max_wait)"
    done

    echo "ERROR: Squid failed to start within $max_wait seconds"
    cat /var/log/squid/cache.log 2>/dev/null || true
    return 1
}

# Check if network lockdown mode is enabled
if [ -f "$SQUID_CONF" ] && [ -f "/etc/squid/allowed_domains.txt" ]; then
    if [ "$NETWORK_LOCKDOWN_MODE" = "lockdown" ]; then
        echo "Network lockdown mode: ENABLED"
        if ! start_squid; then
            echo "ERROR: Failed to start Squid - aborting"
            exit 1
        fi
    else
        echo "Network lockdown mode: AVAILABLE (set JIB_NETWORK_MODE=lockdown to enable)"
        echo "Running in Phase 1 compatibility mode (no proxy filtering)"
    fi
else
    echo "Network lockdown mode: NOT CONFIGURED (Squid config not present)"
    echo "Running in Phase 1 mode"
fi

# =============================================================================
# Run Configuration Validation
# =============================================================================

echo "Validating configuration..."
if ! python3 config_validator.py 2>/dev/null; then
    echo "WARNING: Configuration validation had warnings (continuing anyway)"
fi

# =============================================================================
# Start Gateway API Server
# =============================================================================

echo "Starting gateway API server on port 9847..."

# Run gateway on all interfaces (for container networking)
# Use exec to replace shell process with Python for proper signal handling
exec python3 gateway.py --host 0.0.0.0 --port 9847
