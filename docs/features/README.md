# Feature Documentation

This directory contains detailed documentation for each major feature category in james-in-a-box.

## Quick Reference

| Category | Description | Key Scripts |
|----------|-------------|-------------|
| [Communication](communication.md) | Bidirectional Slack integration for human-agent co... | `slack-notifier`, `slack-receiver` |
| [Context Management](context-management.md) | External knowledge synchronization and persistent ... | `context-sync`, `beads` |
| [GitHub Integration](github-integration.md) | Automated PR monitoring, code reviews, and CI/CD f... | `github-watcher`, `pr-reviewer` |
| [Self-Improvement System](self-improvement.md) | LLM efficiency analysis, inefficiency detection, a... | `trace-collector`, `inefficiency-detector` |
| [Documentation System](documentation-system.md) | Automated documentation generation, sync, and main... | `feature-analyzer`, `doc-generator` |
| [Custom Commands](container-infrastructure.md) | Part of container infrastructure - slash commands ... | - |
| [Utilities](utilities.md) | Helper tools, maintenance scripts, and supporting ... | `worktree-watcher`, `test discovery` |

## How to Use These Docs

1. **Finding a feature**: Use the category docs above or search [FEATURES.md](../FEATURES.md) for the comprehensive list
2. **Understanding a feature**: Each category doc includes:
   - Overview and purpose
   - Helper scripts and commands
   - Configuration options
   - Links to detailed documentation
3. **Extending a feature**: Check the linked source files and ADRs for implementation details

## Auto-Generation

These documents are maintained by the Feature Analyzer:

```bash
# Regenerate all feature docs
feature-analyzer generate-feature-docs

# Update after changes
feature-analyzer full-repo --repo-root ~/repos/james-in-a-box
```

## Related Documentation

- [FEATURES.md](../FEATURES.md) - Complete feature-to-source mapping
- [Architecture Overview](../architecture/README.md) - System design
- [ADR Index](../adr/README.md) - Design decisions

---

*Last updated: 2025-12-02*
