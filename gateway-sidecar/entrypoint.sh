#!/bin/bash
set -e

# =============================================================================
# Gateway Sidecar Entrypoint
#
# Starts the gateway API server and Squid proxy for network filtering.
#
# PRIVATE_MODE controls both network access AND repository visibility:
# - true:  Network locked down (Anthropic API only) + private repos only
# - false: Full internet access + public repos only (default)
#
# This single flag ensures you can't accidentally combine open network
# with private repo access (a security anti-pattern).
# =============================================================================

# PRIVATE_MODE controls the entire security posture:
# - true: private repos + locked network
# - false: public repos + full internet (default)
PRIVATE_MODE="${PRIVATE_MODE:-false}"

if [ "$PRIVATE_MODE" = "true" ] || [ "$PRIVATE_MODE" = "1" ]; then
    echo "=== Gateway Sidecar Starting (Private Mode) ==="
    echo "  Network: Locked down (Anthropic API only)"
    echo "  Repos:   Private/internal only"
    export PRIVATE_MODE=true
    SQUID_CONF="/etc/squid/squid.conf"
else
    echo "=== Gateway Sidecar Starting (Public Mode) ==="
    echo "  Network: Full internet access"
    echo "  Repos:   Public only"
    export PRIVATE_MODE=false
    SQUID_CONF="/etc/squid/squid-allow-all.conf"
fi
echo ""

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

# Export launcher secret for session management (optional - only needed for session auth)
if [ -f "/secrets/launcher-secret" ]; then
    export JIB_LAUNCHER_SECRET=$(cat /secrets/launcher-secret)
fi

# github_client.py reads directly from /secrets/.github-token
# No symlinks needed since we mount the directory

# =============================================================================
# Start Squid Proxy for Network Filtering
# =============================================================================

echo "Starting Squid proxy for network filtering..."
echo "Using config: $SQUID_CONF"

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

# Verify Squid configuration exists
if [ ! -f "$SQUID_CONF" ]; then
    echo "ERROR: Squid configuration not found: $SQUID_CONF"
    exit 1
fi
# Only check allowed_domains.txt in lockdown mode (not used in allow-all mode)
if [ "$SQUID_CONF" = "/etc/squid/squid.conf" ] && [ ! -f "/etc/squid/allowed_domains.txt" ]; then
    echo "ERROR: Allowed domains file not found: /etc/squid/allowed_domains.txt"
    exit 1
fi

# Start Squid in daemon mode
/usr/sbin/squid -f "$SQUID_CONF"

# Wait for Squid to start
elapsed=0
max_wait=30
while [ $elapsed -lt $max_wait ]; do
    if /usr/sbin/squid -k check 2>/dev/null; then
        echo "Squid proxy started successfully on port 3128"
        break
    fi
    sleep 1
    elapsed=$((elapsed + 1))
    echo "Waiting for Squid to start... ($elapsed/$max_wait)"
done

if [ $elapsed -ge $max_wait ]; then
    echo "ERROR: Squid failed to start within $max_wait seconds"
    cat /var/log/squid/cache.log 2>/dev/null || true
    exit 1
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
#
# If HOST_UID/HOST_GID are set, drop privileges using gosu before starting
# the Python gateway. This is required because:
# - Container starts as root so Squid can read its certificate
# - Gateway Python code must run as host user to avoid root-owned git files
if [ -n "${HOST_UID:-}" ] && [ -n "${HOST_GID:-}" ] && [ "$(id -u)" = "0" ]; then
    echo "Dropping privileges to UID=$HOST_UID GID=$HOST_GID"
    exec gosu "$HOST_UID:$HOST_GID" python3 gateway.py --host 0.0.0.0 --port 9847
else
    exec python3 gateway.py --host 0.0.0.0 --port 9847
fi
