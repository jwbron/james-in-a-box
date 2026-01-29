#!/bin/bash
# create-networks.sh - Create Docker networks for network lockdown
#
# This script creates the dual-network architecture for full network isolation:
# - jib-isolated: Internal network (no external route) for jib container
# - jib-external: Standard bridge network for gateway external access
#
# The gateway is dual-homed, connecting to both networks. The jib container
# connects only to jib-isolated and must route all traffic through the gateway.

set -e

# Network configuration (can be overridden via environment)
JIB_ISOLATED_SUBNET="${JIB_ISOLATED_SUBNET:-172.30.0.0/24}"
JIB_EXTERNAL_SUBNET="${JIB_EXTERNAL_SUBNET:-172.31.0.0/24}"

# Check if a subnet is already in use
check_subnet_available() {
    local subnet="$1"
    local network_name="$2"

    # Check if our network already exists with correct subnet
    if docker network inspect "$network_name" &>/dev/null; then
        existing_subnet=$(docker network inspect "$network_name" --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
        if [ "$existing_subnet" = "$subnet" ]; then
            echo "Network $network_name already exists with correct subnet $subnet"
            return 0
        else
            echo "ERROR: Network $network_name exists with different subnet: $existing_subnet (expected $subnet)" >&2
            return 1
        fi
    fi

    # Check if subnet is used by any other network
    for net in $(docker network ls -q 2>/dev/null); do
        net_subnet=$(docker network inspect "$net" --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null || true)
        if [ "$net_subnet" = "$subnet" ]; then
            net_name=$(docker network inspect "$net" --format '{{.Name}}' 2>/dev/null)
            echo "ERROR: Subnet $subnet already in use by network: $net_name" >&2
            return 1
        fi
    done

    return 0
}

# Create network if it doesn't exist
create_network() {
    local name="$1"
    local subnet="$2"
    local internal="$3"  # "true" or "false"

    if docker network inspect "$name" &>/dev/null; then
        echo "Network $name already exists"
        return 0
    fi

    echo "Creating network: $name (subnet: $subnet, internal: $internal)"

    local cmd=(docker network create --driver bridge --subnet "$subnet")

    if [ "$internal" = "true" ]; then
        cmd+=(--internal)
    fi

    cmd+=("$name")

    "${cmd[@]}"
    echo "Created network: $name"
}

# Main execution
main() {
    echo "=== Network Lockdown Setup ==="
    echo ""
    echo "Creating dual-network architecture for full network isolation:"
    echo "  - jib-isolated ($JIB_ISOLATED_SUBNET): Internal network for jib container"
    echo "  - jib-external ($JIB_EXTERNAL_SUBNET): External network for gateway"
    echo ""

    # Check subnet availability
    if ! check_subnet_available "$JIB_ISOLATED_SUBNET" "jib-isolated"; then
        echo ""
        echo "To use different subnets, set environment variables:"
        echo "  JIB_ISOLATED_SUBNET=172.30.0.0/24 JIB_EXTERNAL_SUBNET=172.31.0.0/24 $0"
        exit 1
    fi

    if ! check_subnet_available "$JIB_EXTERNAL_SUBNET" "jib-external"; then
        echo ""
        echo "To use different subnets, set environment variables:"
        echo "  JIB_ISOLATED_SUBNET=172.30.0.0/24 JIB_EXTERNAL_SUBNET=172.31.0.0/24 $0"
        exit 1
    fi

    # Create internal network (no external route)
    # The --internal flag prevents traffic from leaving this network
    create_network "jib-isolated" "$JIB_ISOLATED_SUBNET" "true"

    # Create external network (standard bridge)
    create_network "jib-external" "$JIB_EXTERNAL_SUBNET" "false"

    echo ""
    echo "=== Network Setup Complete ==="
    echo ""
    echo "Network topology:"
    echo "  jib containers -> jib-isolated (172.30.0.x) -> gateway (172.30.0.2)"
    echo "  gateway (172.31.0.2) -> jib-external -> Internet (allowlisted)"
    echo ""
    echo "IP Assignments:"
    echo "  Gateway (jib-isolated): 172.30.0.2"
    echo "  Gateway (jib-external): 172.31.0.2"
    echo "  jib containers:         Dynamic (172.30.0.3+)"
}

main "$@"
