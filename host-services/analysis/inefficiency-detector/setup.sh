#!/bin/bash
# Setup script for LLM Inefficiency Reporter (Phase 3)
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="inefficiency-reporter.service"
TIMER_NAME="inefficiency-reporter.timer"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "Setting up LLM Inefficiency Reporter..."

# Create systemd user directory
mkdir -p "$SYSTEMD_DIR"

# Symlink service and timer files
ln -sf "$COMPONENT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"
ln -sf "$COMPONENT_DIR/$TIMER_NAME" "$SYSTEMD_DIR/"
echo "✓ Service and timer symlinked"

# Reload systemd
systemctl --user daemon-reload
echo "✓ Systemd daemon reloaded"

# Enable timer
systemctl --user enable "$TIMER_NAME"
echo "✓ Timer enabled"

# Start timer
systemctl --user start "$TIMER_NAME"
echo "✓ Timer started"

# Create analysis output directory
mkdir -p "${HOME}/repos/james-in-a-box/docs/analysis/inefficiency"
echo "✓ Analysis output directory created"

# Check status
echo ""
echo "Timer status:"
systemctl --user status "$TIMER_NAME" --no-pager || true
echo ""
systemctl --user list-timers | grep inefficiency || true

echo ""
echo "Setup complete!"
echo ""
echo "The inefficiency reporter will run weekly (Monday 11 AM)."
echo ""
echo "Useful commands:"
echo "  systemctl --user list-timers | grep inefficiency  # Check timer"
echo "  systemctl --user start $SERVICE_NAME              # Run now"
echo "  systemctl --user status $SERVICE_NAME             # Check last run"
echo "  journalctl --user -u $SERVICE_NAME -f             # View logs"
echo ""
echo "Manual run:"
echo "  python3 $COMPONENT_DIR/weekly_report_generator.py --force"
