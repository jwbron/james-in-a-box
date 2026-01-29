#!/bin/bash
set -e

# =============================================================================
# Gateway Sidecar Entrypoint
#
# Starts the gateway API server and Squid proxy for network filtering.
# All jib containers run in network lockdown mode with traffic routed
# through the Squid proxy for domain-based filtering.
#
# Network Modes:
# - Default: Allowlist-based filtering (only api.anthropic.com)
# - ALLOW_ALL_NETWORK=true: Allow all domains
#
# Repository Visibility (PRIVATE_REPO_MODE):
# - true: Only private/internal repos accessible
# - false (default): Only public repos accessible
#
# Security Invariant:
# When ALLOW_ALL_NETWORK is enabled, PRIVATE_REPO_MODE is forced to false
# to ensure: open network access = public repos only.
# =============================================================================

# Determine network mode
ALLOW_ALL_NETWORK="${ALLOW_ALL_NETWORK:-false}"
PRIVATE_REPO_MODE="${PRIVATE_REPO_MODE:-false}"

if [ "$ALLOW_ALL_NETWORK" = "true" ] || [ "$ALLOW_ALL_NETWORK" = "1" ]; then
    echo "=== Gateway Sidecar Starting (Allow All Network Mode) ==="
    echo "WARNING: All network traffic allowed."
    # Force PRIVATE_REPO_MODE=false to ensure security invariant:
    # open network access requires public-repo-only repository access
    export PRIVATE_REPO_MODE=false
    echo "PRIVATE_REPO_MODE=false (security invariant: open network = public repos only)"
    SQUID_CONF="/etc/squid/squid-allow-all.conf"
else
    echo "=== Gateway Sidecar Starting (Network Lockdown Mode) ==="
    SQUID_CONF="/etc/squid/squid.conf"
fi

# Show repository access mode
if [ "$PRIVATE_REPO_MODE" = "true" ] || [ "$PRIVATE_REPO_MODE" = "1" ]; then
    echo "PRIVATE_REPO_MODE=true (only private repos accessible)"
    export PRIVATE_REPO_MODE=true
else
    echo "PRIVATE_REPO_MODE=false (only public repos accessible)"
    export PRIVATE_REPO_MODE=false
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
