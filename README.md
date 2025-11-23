# James-In-A-Box (JIB)

Autonomous software engineering agent in a sandboxed container.

## Structure

```
components/                    # Host components (systemd)
├── slack-notifier/           # Send Slack DMs
├── slack-receiver/           # Receive Slack messages
├── codebase-analyzer/        # Code analysis
├── conversation-analyzer/    # Conversation analysis
└── service-monitor/          # Failure notifications

jib-container/                 # Container
├── components/context-watcher/  # Monitor context
├── .claude/                  # Claude config
└── docker-setup.py

archive/                       # Old structure (READMEs, empty dirs)
lib/                           # Shared libraries
docs/                          # Architecture
```

## Quick Start

**Host:** `cd components/<component> && ./setup.sh`  
**Container:** `cd ~/khan/james-in-a-box/jib-container && python3 docker-setup.py`

## Migration

See [MIGRATION.md](MIGRATION.md) for host machine update steps.

## Documentation

Each component has its own README. See `components/*/README.md` and `jib-container/components/*/README.md`.
