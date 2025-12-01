# Beads Health Reports

This directory contains automated health analysis reports for the Beads task tracking system.

## Purpose

Reports are submitted via Pull Requests to provide:
- Review-friendly format for stakeholders to review health trends
- Historical tracking of task tracking quality over time (last 5 reports)
- Accessible context for all analyzers and LLM agents
- Transparency into how well beads is being used for persistent memory

## Report Structure

- `beads-health-YYYYMMDD-HHMMSS.md` - Full health report with metrics and issues
- `beads-metrics-YYYYMMDD-HHMMSS.json` - Machine-readable metrics
- `latest-report.md` - Symlink to most recent report
- `latest-metrics.json` - Symlink to most recent metrics

## Generation

Reports are generated weekly via systemd timer on the host:
```bash
beads-analyzer.py --force  # Force run
```

Each run creates a new PR with the health report. Only the last **5 reports** are kept - when the 6th report is generated, the oldest is automatically removed in the same PR.

## Metrics Tracked

| Category | Metrics |
|----------|---------|
| **Volume** | Total, created, closed, abandoned, in-progress, blocked |
| **Quality** | Notes coverage, label coverage, searchable titles |
| **Lifecycle** | Avg time to close, proper lifecycle rate |
| **Integration** | Source tracking (Slack/GitHub/JIRA) |
| **Patterns** | Duplicates, orphans |

## Health Score

0-100 score based on:
- Task quality (notes, labels, searchable titles)
- Lifecycle health (proper transitions, low abandonment)
- Integration coverage (linked to Slack/GitHub/JIRA)

Issues are categorized by severity (high/medium/low) and factored into the score.
