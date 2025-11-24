# Migration Guide: Single Confluence Sync → Multi-Connector Context-Sync

## Overview

This project has evolved from a single-purpose Confluence documentation sync to a multi-connector architecture called "context-sync" that can sync content from multiple sources.

## What Changed

### Output Directory

**Before:**
```
confluence-cursor-sync/
└── confluence-docs/     # Synced content lived here
```

**After:**
```
~/context-sync/
├── confluence/          # Confluence content now here
├── logs/                # Centralized logs
└── (future connectors)

confluence-cursor-sync/  # Code only, no output files
├── sync/
├── sync_all.py
└── systemd/
```

### Key Changes

1. **Output location**: Moved from `./confluence-docs/` to `~/context-sync/confluence/`
2. **New orchestrator**: `sync_all.py` runs all connectors (currently just Confluence)
3. **Scheduled syncing**: Systemd timer runs hourly syncs automatically
4. **Connector architecture**: Easy to add new data sources (GitHub, Slack, etc.)

## Migration Steps

### Step 1: Update to New Code

Pull the latest changes:
```bash
cd ~/khan/confluence-cursor-sync
git pull
```

### Step 2: Install Dependencies (if needed)

```bash
make deps
```

### Step 3: Update Configuration

The default output directory is now `~/context-sync/confluence/`. If you want to keep using the old location, set:

```bash
# In your .env file:
CONFLUENCE_OUTPUT_DIR=./confluence-docs
```

Or leave it unset to use the new default location.

### Step 4: Run a Test Sync

```bash
# Test the new connector-based sync
./sync_all.py

# Or test just Confluence
python -m sync.confluence_connector
```

### Step 5: Enable Scheduled Syncing (Optional)

To enable automatic hourly syncing:

```bash
./manage_scheduler.sh enable
```

This will:
- Install systemd service files (via symlinks)
- Enable the hourly timer
- Start the timer

Check status:
```bash
./manage_scheduler.sh status
```

### Step 6: Update Symlinks (if using)

If you created symlinks to `confluence-docs/` in other projects, update them:

**Option 1: Update existing symlinks**
```bash
# For each project with a symlink
cd ~/khan/some-project
rm confluence-docs
ln -s ~/context-sync/confluence confluence-docs
```

**Option 2: Use the linking tools**

The existing linking tools still work, but point them to the new location:

```bash
# This will work automatically with the new default location
make docs-link-khan-execute
```

### Step 7: Clean Up Old Data (Optional)

If you've migrated to `~/context-sync/confluence/` and want to remove the old location:

```bash
# Backup first!
tar -czf confluence-docs-backup.tar.gz confluence-docs/

# Verify new location has content
ls -la ~/context-sync/confluence/

# Remove old location
rm -rf confluence-docs/
```

## Backwards Compatibility

### Makefile Commands

All existing Makefile commands still work:

```bash
make docs-sync          # Still works, uses new location
make docs-search        # Still works
make docs-link-khan     # Still works
# etc.
```

### Environment Variables

All existing environment variables are respected:
- `CONFLUENCE_BASE_URL`
- `CONFLUENCE_USERNAME`
- `CONFLUENCE_API_TOKEN`
- `CONFLUENCE_SPACE_KEYS`
- `CONFLUENCE_OUTPUT_DIR` (now defaults to `~/context-sync/confluence`)

### Old Sync Script

The original `sync/confluence_sync.py` still exists and can be used directly:

```bash
# Old way (still works)
python -m sync.confluence_sync

# New way (recommended)
./sync_all.py
```

## New Features

### 1. Automated Scheduled Syncing

```bash
# Enable hourly syncing
./manage_scheduler.sh enable

# Check when next sync will run
./manage_scheduler.sh status

# View logs
./manage_scheduler.sh logs
```

### 2. Multi-Connector Ready

The architecture now supports multiple connectors:

```bash
# Run all connectors
./sync_all.py

# Future: Add more connectors
# - GitHub documentation
# - Slack threads
# - JIRA tickets
# etc.
```

### 3. Better Logging

Logs now go to:
- Systemd journal: `journalctl --user -u context-sync.service`
- File logs: `~/context-sync/logs/sync_YYYYMMDD.log`

## Rollback

If you need to rollback to the old behavior:

```bash
# 1. Disable scheduler if enabled
./manage_scheduler.sh disable

# 2. Set output to old location
echo "CONFLUENCE_OUTPUT_DIR=./confluence-docs" >> .env

# 3. Use old sync method
make docs-sync
```

## Common Issues

### Issue: Symlinks broken

If you have symlinks pointing to `confluence-docs/`, they need to be updated:

```bash
# Find all symlinks pointing to old location
find ~/khan -type l -lname "*confluence-docs*"

# Update each one
cd <project-directory>
rm confluence-docs
ln -s ~/context-sync/confluence confluence-docs
```

### Issue: Scheduler not running

Check systemd timer status:

```bash
./manage_scheduler.sh status

# or manually
systemctl --user status context-sync.timer
```

If timer is not running:
```bash
./manage_scheduler.sh enable
```

### Issue: Permission denied on ~/context-sync

Ensure directory exists and is writable:

```bash
mkdir -p ~/context-sync/confluence
chmod 755 ~/context-sync
```

## Getting Help

1. Check the logs:
   ```bash
   ./manage_scheduler.sh logs
   ```

2. Run a manual sync to see errors:
   ```bash
   ./sync_all.py
   ```

3. Check configuration:
   ```bash
   make docs-test
   ```

4. See full documentation:
   - `README.md` - Main documentation
   - `ARCHITECTURE.md` - System architecture
   - `systemd/README.md` - Scheduler documentation

