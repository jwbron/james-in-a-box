# Why This Isn't a Dotfile

Originally I (Claude) created this as `.context-watcher/` (dotfile, hidden).

Jacob correctly questioned this choice. Here's why it was wrong and what changed:

## The Problem

1. **Inconsistent with project structure** - Scripts were in visible `scripts/`, but config/docs were hidden
2. **Hard to discover** - Dotfiles are hidden by default (`ls` won't show them)
3. **Not a system/config dir** - This is user-facing tooling, not background config like `.claude/`
4. **Goes against convention** - `~/tools/` exists specifically for "reusable scripts and utilities"

## The Fix

Renamed `.context-watcher/` → `context-watcher/` (visible directory)

## Proper Organization

```
~/khan/cursor-sandboxed/
├── context-watcher/           # Example configs and docs (visible!)
│   ├── config/
│   │   └── context-watcher.yaml  # Example/template
│   ├── README.md
│   └── SETUP.md
└── scripts/                   # Executable scripts (visible!)
    ├── context-watcher.sh
    ├── context-watcher-ctl.sh
    └── test-context-watcher.sh

~/sharing/                     # Runtime/persistent data
├── config/
│   └── context-watcher.yaml  # Actual config (copied from template)
├── notifications/            # Outputs
└── context-tracking/         # State and logs
```

## Lesson Learned

Dotfiles are for:
- User preferences (`.bashrc`, `.vimrc`)
- Application config (`.claude/`, `.config/`)
- Hidden system data

NOT for:
- User-facing tools and utilities
- Documentation
- Template/example files

When in doubt: **make it visible**.
