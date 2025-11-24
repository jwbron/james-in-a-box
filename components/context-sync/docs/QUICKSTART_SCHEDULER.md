# Quick Start: Automated Hourly Syncing

## Setup (One-Time)

### 1. Enable the Scheduler

```bash
cd ~/khan/confluence-cursor-sync
./manage_scheduler.sh enable
```

This will:
- Create symlinks to systemd service files
- Reload systemd daemon
- Enable and start the hourly timer

### 2. Verify It's Running

```bash
./manage_scheduler.sh status
```

You should see:
- Timer is active and enabled
- Next scheduled run time
- Last run status (if any)

## Daily Usage

Once enabled, the sync runs automatically every hour. You don't need to do anything!

### Check When Next Sync Will Run

```bash
./manage_scheduler.sh status
```

### View Recent Sync Logs

```bash
./manage_scheduler.sh logs
```

### Follow Logs in Real-Time

```bash
./manage_scheduler.sh logs-follow
```
Press Ctrl+C to stop following.

### Manually Trigger a Sync Now

```bash
./manage_scheduler.sh start
```

## Where Are My Files?

All synced content goes to:
```
~/context-sync/confluence/
```

This is separate from the code repository and won't clutter your git workspace.

## Disabling the Scheduler

If you want to stop automatic syncing:

```bash
./manage_scheduler.sh disable
```

You can always re-enable it later with `./manage_scheduler.sh enable`.

## Troubleshooting

### "Timer is not loaded"

Run the enable command to install it:
```bash
./manage_scheduler.sh enable
```

### "Sync failed"

Check the logs for errors:
```bash
./manage_scheduler.sh logs
```

Common issues:
- Missing or invalid credentials in `.env`
- Network connectivity problems
- Rate limiting from Confluence API

### "No output in ~/context-sync/"

Make sure the sync is actually running:
```bash
./manage_scheduler.sh status
./manage_scheduler.sh start  # Trigger manually to see output
```

## Advanced

### Change Sync Frequency

Edit `systemd/context-sync.timer` and change:
```ini
OnCalendar=hourly          # Every hour (default)
# OnCalendar=daily         # Once per day at midnight
# OnCalendar=*:0/30        # Every 30 minutes
# OnCalendar=Mon-Fri 09:00 # Weekdays at 9am
```

Then reload:
```bash
systemctl --user daemon-reload
systemctl --user restart context-sync.timer
```

### View Full Systemd Details

```bash
# Timer details
systemctl --user status context-sync.timer

# Service details
systemctl --user status context-sync.service

# All timers
systemctl --user list-timers
```

### File Logs

In addition to systemd journal, logs are also written to:
```
~/context-sync/logs/sync_YYYYMMDD.log
```

One log file per day, with timestamps for each sync run.

