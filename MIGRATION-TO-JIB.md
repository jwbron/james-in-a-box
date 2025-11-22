# Migration to james-in-a-box (jib)

This project has been renamed from `cursor-sandboxed` to `james-in-a-box` with CLI command `jib`.

## What Changed

### Project Name
- **Old**: cursor-sandboxed / claude-sandbox
- **New**: james-in-a-box (repo), jib (CLI/short name)

### Host Directories
- `~/.claude-sandbox-sharing` → `~/.jib-sharing`
- `~/.claude-sandbox-tools` → `~/.jib-tools`
- `~/.config/slack-notifier` → `~/.config/jib-notifier`
- `~/khan/cursor-sandboxed` → `~/khan/james-in-a-box`

### Container Paths (unchanged)
- `~/sharing` (still ~/sharing inside container)
- `~/tools` (still ~/tools inside container)
- `~/khan/james-in-a-box` (updated to match repo name)

## Migration Steps

### Step 1: Rename Host Directories

Run the migration script ON THE HOST MACHINE:

```bash
cd ~/khan/cursor-sandboxed
./scripts/rename-host-dirs.sh
```

This will rename:
- ~/.claude-sandbox-sharing → ~/.jib-sharing
- ~/.claude-sandbox-tools → ~/.jib-tools
- ~/.config/slack-notifier → ~/.config/jib-notifier

### Step 2: Rename Repository Directory

```bash
cd ~/khan
mv cursor-sandboxed james-in-a-box
cd james-in-a-box
```

### Step 3: Update Docker Run Command

Update your docker run script to use new mount paths:

**Old:**
```bash
docker run -it \
  -v ~/.claude-sandbox-sharing:/home/user/sharing \
  -v ~/.claude-sandbox-tools:/home/user/tools \
  ...
```

**New:**
```bash
docker run -it \
  -v ~/.jib-sharing:/home/user/sharing \
  -v ~/.jib-tools:/home/user/tools \
  -v ~/khan/james-in-a-box:/home/user/khan/james-in-a-box:ro \
  ...
```

### Step 4: Restart Services

Restart the host-side services with updated paths:

```bash
# Notifier service
./scripts/host-notify-ctl.sh restart

# Slack receiver service
./scripts/host-receive-ctl.sh restart

# Context watcher (if running)
./scripts/context-watcher-ctl.sh restart
```

### Step 5: Rebuild Container (if needed)

If using a pre-built image, rebuild with the new Dockerfile:

```bash
docker build -t james-in-a-box .
```

## Verification

After migration, verify everything works:

```bash
# Check host directories exist
ls -la ~/.jib-sharing
ls -la ~/.jib-tools
ls -la ~/.config/jib-notifier

# Check notifier is running
./scripts/host-notify-ctl.sh status

# Check receiver is running
./scripts/host-receive-ctl.sh status
```

## Future CLI Command

The CLI entrypoint will be `jib` (short for james-in-a-box):

```bash
# Example future usage
jib start        # Start the container
jib stop         # Stop the container
jib logs         # View logs
jib shell        # Get a shell in container
```

(CLI not yet implemented - to be added)

## Rollback

If you need to roll back:

```bash
# Rename directories back
mv ~/.jib-sharing ~/.claude-sandbox-sharing
mv ~/.jib-tools ~/.claude-sandbox-tools
mv ~/.config/jib-notifier ~/.config/slack-notifier
mv ~/khan/james-in-a-box ~/khan/cursor-sandboxed

# Revert config files
cd ~/khan/cursor-sandboxed
git checkout HEAD -- .
```
