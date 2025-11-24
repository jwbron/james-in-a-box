# Systemd Service Files

This directory contains systemd user service and timer files for automated context-sync scheduling.

## Files

- `context-sync.service` - Systemd service unit that runs the sync
- `context-sync.timer` - Systemd timer unit that triggers the service (configurable frequency)

## Installation

To install the systemd files, you can either:

### Option 1: Use the management script (recommended)

```bash
# Enable with default hourly frequency
./manage_scheduler.sh enable

# Or enable with custom frequency
./manage_scheduler.sh enable 15min   # Every 15 minutes
./manage_scheduler.sh enable 30min   # Every 30 minutes
./manage_scheduler.sh enable hourly  # Every hour (default)
./manage_scheduler.sh enable daily   # Daily at midnight
```

This will automatically install the files and enable the timer with your chosen frequency.

**Changing Frequency Later:**

```bash
# Change frequency of existing timer
./manage_scheduler.sh set-frequency 30min
```

### Option 2: Manual installation

```bash
# Create systemd user directory if it doesn't exist
mkdir -p ~/.config/systemd/user

# Create symlinks to service files
ln -s "$(pwd)/systemd/context-sync.service" ~/.config/systemd/user/
ln -s "$(pwd)/systemd/context-sync.timer" ~/.config/systemd/user/

# Reload systemd
systemctl --user daemon-reload

# Enable and start the timer
systemctl --user enable context-sync.timer
systemctl --user start context-sync.timer
```

**Note:** Symlinks are used instead of copies so any updates to the service files in the repository are automatically reflected without needing to reinstall.

## Usage

After installation:

```bash
# Check status
systemctl --user status context-sync.timer

# View upcoming sync times
systemctl --user list-timers context-sync.timer

# View logs
journalctl --user -u context-sync.service

# Manually trigger a sync
systemctl --user start context-sync.service

# Disable automatic syncing
systemctl --user stop context-sync.timer
systemctl --user disable context-sync.timer
```

## Configuration

The timer is configured to run every hour with:
- Random delay up to 5 minutes to avoid load spikes
- Persistence across reboots
- Low priority (nice=10) to avoid impacting other work

To change the schedule, edit `context-sync.timer` and modify the `OnCalendar=` line:
- `hourly` - Every hour
- `daily` - Once per day at midnight
- `*:0/30` - Every 30 minutes
- `Mon-Fri 09:00` - Weekdays at 9am

After making changes, reload systemd (the symlinks will automatically reflect the changes):

```bash
systemctl --user daemon-reload
systemctl --user restart context-sync.timer
```

