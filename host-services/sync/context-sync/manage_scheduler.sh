#!/bin/bash
# Manage context-sync systemd scheduler

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="context-sync"
TIMER_FILE="$HOME/.config/systemd/user/context-sync.timer"

# Convert frequency name to OnCalendar value
get_oncalendar_value() {
    case "$1" in
        15min)
            echo "*:0/15"
            ;;
        30min)
            echo "*:0/30"
            ;;
        hourly)
            echo "hourly"
            ;;
        daily)
            echo "*-*-* 00:00:00"
            ;;
        *)
            echo "Invalid frequency: $1" >&2
            echo "Valid options: 15min, 30min, hourly, daily" >&2
            return 1
            ;;
    esac
}

# Update the timer file with new frequency
update_timer_frequency() {
    local freq="$1"
    local oncalendar
    oncalendar=$(get_oncalendar_value "$freq") || return 1

    # Update the timer file
    local timer_source="${SCRIPT_DIR}/context-sync.timer"
    sed -i "s|^OnCalendar=.*|OnCalendar=$oncalendar|" "$timer_source"

    echo "✓ Updated timer frequency to: $freq ($oncalendar)"

    # Reload systemd if timer is enabled
    if systemctl --user is-enabled context-sync.timer &>/dev/null; then
        systemctl --user daemon-reload
        systemctl --user restart context-sync.timer
        echo "✓ Timer reloaded and restarted"
    fi
}

show_usage() {
    cat <<EOF
Usage: $0 <command> [frequency]

Commands:
    enable [FREQ]   Enable and start the sync timer (default: hourly)
    disable         Disable and stop the timer
    start           Manually run a sync now
    status          Show service and timer status
    logs            Show recent logs
    logs-follow     Follow logs in real-time
    set-frequency FREQ  Change sync frequency

Frequency options:
    15min           Every 15 minutes
    30min           Every 30 minutes
    hourly          Every hour (default)
    daily           Daily at midnight

Examples:
    $0 enable               # Enable hourly automatic syncing
    $0 enable 15min         # Enable syncing every 15 minutes
    $0 set-frequency 30min  # Change to sync every 30 minutes
    $0 start                # Run sync now
    $0 status               # Check if scheduler is running
    $0 logs                 # View recent sync logs

EOF
}

case "${1:-}" in
    enable)
        # Get frequency (default to hourly)
        FREQ="${2:-hourly}"

        # Update frequency before enabling
        echo "Setting sync frequency to: $FREQ"
        update_timer_frequency "$FREQ"
        echo ""

        echo "Installing systemd files..."
        mkdir -p ~/.config/systemd/user

        # Create symlinks (remove existing files/links first)
        rm -f ~/.config/systemd/user/context-sync.service
        rm -f ~/.config/systemd/user/context-sync.timer
        ln -s "${SCRIPT_DIR}/context-sync.service" ~/.config/systemd/user/
        ln -s "${SCRIPT_DIR}/context-sync.timer" ~/.config/systemd/user/
        echo "✓ Symlinks created in ~/.config/systemd/user/"

        echo "Reloading systemd daemon..."
        systemctl --user daemon-reload

        echo "Enabling context-sync timer..."
        systemctl --user enable context-sync.timer
        systemctl --user start context-sync.timer
        echo "✓ Timer enabled and started"
        echo ""
        systemctl --user status context-sync.timer --no-pager
        echo ""
        echo "Next sync times:"
        systemctl --user list-timers context-sync.timer --no-pager
        ;;

    set-frequency)
        if [ -z "${2:-}" ]; then
            echo "Error: Frequency required"
            echo "Usage: $0 set-frequency <15min|30min|hourly|daily>"
            exit 1
        fi
        update_timer_frequency "$2"
        echo ""
        echo "Next sync times:"
        systemctl --user list-timers context-sync.timer --no-pager
        ;;

    disable)
        echo "Disabling context-sync timer..."
        systemctl --user stop context-sync.timer
        systemctl --user disable context-sync.timer
        echo "✓ Timer disabled and stopped"
        ;;

    start)
        echo "Running context-sync now..."
        systemctl --user start context-sync.service
        echo "✓ Sync started"
        echo ""
        echo "View progress with: $0 logs-follow"
        ;;

    status)
        echo "=== Timer Status ==="
        systemctl --user status context-sync.timer --no-pager || true
        echo ""
        echo "=== Service Status ==="
        systemctl --user status context-sync.service --no-pager || true
        echo ""
        echo "=== Upcoming Syncs ==="
        systemctl --user list-timers context-sync.timer --no-pager
        ;;

    logs)
        echo "=== Recent Sync Logs ==="
        journalctl --user -u context-sync.service -n 100 --no-pager
        ;;

    logs-follow)
        echo "=== Following Sync Logs (Ctrl+C to stop) ==="
        journalctl --user -u context-sync.service -f
        ;;

    *)
        show_usage
        exit 1
        ;;
esac

