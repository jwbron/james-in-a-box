# Context Watcher Service

Systemd service for context file monitoring (future).

## Status

This directory is reserved for future context-watcher systemd integration.

Currently, context-watcher runs via control script:
```bash
bin/context-watcher-ctl start
```

## Planned

Future systemd service will:
- Auto-start on boot
- Monitor context directories
- Trigger Claude analysis on changes
- Integrate with systemd logging
