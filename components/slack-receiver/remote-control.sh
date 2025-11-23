#!/bin/bash
# Remote control script for JIB - executed from Slack commands
# This runs on the host machine to control container and services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../.. && pwd)"
LOG_FILE="$HOME/.config/jib-notifier/remote-control.log"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Send notification back to user
notify() {
    local notification_dir="$HOME/.jib-sharing/notifications"
    mkdir -p "$notification_dir"

    local timestamp=$(date +%Y%m%d-%H%M%S)
    local notification_file="$notification_dir/${timestamp}-remote-command.md"

    cat > "$notification_file" <<EOF
# 🎮 Remote Command Result

\`\`\`
$1
\`\`\`

Executed at: $(date)
EOF

    log "Notification sent: $notification_file"
}

# Container operations
jib_status() {
    log "Checking JIB container status"

    if docker ps | grep -q jib-claude; then
        status="✅ Running"
        container_id=$(docker ps --filter name=jib-claude --format "{{.ID}}")
        uptime=$(docker ps --filter name=jib-claude --format "{{.Status}}")
    else
        status="❌ Not running"
        container_id="N/A"
        uptime="N/A"
    fi

    notify "JIB Container Status
Status: $status
Container ID: $container_id
Uptime: $uptime"
}

jib_restart() {
    log "Restarting JIB container"

    # Stop existing container
    if docker ps | grep -q jib-claude; then
        log "Stopping existing container"
        docker stop jib-claude || true
    fi

    # Start new container
    log "Starting container"
    cd "$SCRIPT_DIR/jib-container"
    ./jib &

    sleep 3

    if docker ps | grep -q jib-claude; then
        notify "✅ JIB container restarted successfully"
    else
        notify "❌ JIB container failed to restart
Check logs: docker logs jib-claude"
    fi
}

jib_rebuild() {
    log "Rebuilding JIB container"

    # Stop and remove existing container
    if docker ps -a | grep -q jib-claude; then
        log "Stopping and removing existing container"
        docker stop jib-claude || true
        docker rm jib-claude || true
    fi

    # Rebuild and start
    log "Rebuilding container"
    cd "$SCRIPT_DIR/jib-container"
    ./jib --rebuild &

    sleep 5

    if docker ps | grep -q jib-claude; then
        notify "✅ JIB container rebuilt and started successfully"
    else
        notify "❌ JIB container rebuild failed
Check logs: docker logs jib-claude"
    fi
}

jib_logs() {
    log "Fetching JIB container logs"

    if docker ps | grep -q jib-claude; then
        logs=$(docker logs --tail 50 jib-claude 2>&1)
        notify "JIB Container Logs (last 50 lines)

$logs"
    else
        notify "❌ JIB container is not running"
    fi
}

# Service operations
service_status() {
    local service_name=$1
    log "Checking status of $service_name"

    if systemctl --user is-active --quiet "$service_name"; then
        active="✅ Active"
    else
        active="❌ Inactive"
    fi

    if systemctl --user is-enabled --quiet "$service_name" 2>/dev/null; then
        enabled="✅ Enabled"
    else
        enabled="❌ Disabled"
    fi

    status=$(systemctl --user status "$service_name" --no-pager 2>&1 | tail -10)

    notify "Service Status: $service_name

Active: $active
Enabled: $enabled

Recent Status:
$status"
}

service_restart() {
    local service_name=$1
    log "Restarting service: $service_name"

    systemctl --user restart "$service_name"
    sleep 2

    if systemctl --user is-active --quiet "$service_name"; then
        notify "✅ Service restarted: $service_name"
    else
        notify "❌ Service failed to restart: $service_name
Check logs: journalctl --user -u $service_name -n 50"
    fi
}

service_stop() {
    local service_name=$1
    log "Stopping service: $service_name"

    systemctl --user stop "$service_name"

    notify "Service stopped: $service_name"
}

service_start() {
    local service_name=$1
    log "Starting service: $service_name"

    systemctl --user start "$service_name"
    sleep 2

    if systemctl --user is-active --quiet "$service_name"; then
        notify "✅ Service started: $service_name"
    else
        notify "❌ Service failed to start: $service_name
Check logs: journalctl --user -u $service_name -n 50"
    fi
}

service_logs() {
    local service_name=$1
    local lines=${2:-50}
    log "Fetching logs for service: $service_name"

    logs=$(journalctl --user -u "$service_name" -n "$lines" --no-pager 2>&1)

    notify "Service Logs: $service_name (last $lines lines)

$logs"
}

list_services() {
    log "Listing JIB services"

    services=$(systemctl --user list-units --type=service,timer --all | grep -E 'slack-|codebase-|conversation-|service-failure' || echo "No JIB services found")
    timers=$(systemctl --user list-timers --all | grep -E 'codebase-|conversation-' || echo "No timers found")

    notify "JIB Services and Timers

Services:
$services

Timers:
$timers"
}

# Help text
show_help() {
    notify "JIB Remote Control Commands

Container:
  /jib status          - Check container status
  /jib restart         - Restart container
  /jib rebuild         - Rebuild and restart container
  /jib logs            - Show recent container logs

Services:
  /service list                    - List all JIB services
  /service status <name>           - Check service status
  /service restart <name>          - Restart a service
  /service start <name>            - Start a service
  /service stop <name>             - Stop a service
  /service logs <name> [lines]     - Show service logs

Examples:
  /jib restart
  /service restart slack-notifier.service
  /service logs slack-receiver.service 100"
}

# Main command routing
main() {
    local command=$1
    local subcommand=$2
    local arg1=$3
    local arg2=$4

    log "Remote command received: $command $subcommand $arg1 $arg2"

    case "$command" in
        jib)
            case "$subcommand" in
                status)   jib_status ;;
                restart)  jib_restart ;;
                rebuild)  jib_rebuild ;;
                logs)     jib_logs ;;
                *)        show_help ;;
            esac
            ;;
        service)
            case "$subcommand" in
                list)     list_services ;;
                status)   service_status "$arg1" ;;
                restart)  service_restart "$arg1" ;;
                start)    service_start "$arg1" ;;
                stop)     service_stop "$arg1" ;;
                logs)     service_logs "$arg1" "${arg2:-50}" ;;
                *)        show_help ;;
            esac
            ;;
        help)
            show_help
            ;;
        *)
            notify "❌ Unknown command: $command

Send 'help' for available commands"
            ;;
    esac
}

# Execute
main "$@"
