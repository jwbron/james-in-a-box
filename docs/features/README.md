# Feature Documentation

This directory contains detailed documentation for each major feature category in james-in-a-box.

## Quick Reference

| Category | Description | Key Scripts |
|----------|-------------|-------------|
| [Communication](communication.md) | Bidirectional Slack integration for human-agent communication | `slack-notifier`, `slack-receiver` |
| [Context Management](context-management.md) | External knowledge synchronization and persistent task tracking | `context-sync`, `beads` |
| [GitHub Integration](github-integration.md) | GitHub command handling and PR workflows | `github-processor` |
| [Container Infrastructure](container-infrastructure.md) | Container management, custom commands, rules | `jib` |
| [Utilities](utilities.md) | Helper tools, maintenance scripts, and supporting services | `discover-tests` |

## How to Use These Docs

1. **Finding a feature**: Use the category docs above or search [FEATURES.md](../FEATURES.md) for the comprehensive list
2. **Understanding a feature**: Each category doc includes:
   - Overview and purpose
   - Helper scripts and commands
   - Configuration options
   - Links to detailed documentation
3. **Extending a feature**: Check the linked source files and ADRs for implementation details

## Related Documentation

- [FEATURES.md](../FEATURES.md) - Complete feature-to-source mapping
- [Architecture Overview](../architecture/README.md) - System design
- [ADR Index](../adr/README.md) - Design decisions

---

*Last updated: 2026-01-28*
