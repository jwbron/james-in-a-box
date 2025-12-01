# Beads Integration Analyzer

Analyzes how well the Beads task tracking system is being used to identify integration health issues and improvement opportunities.

## Overview

The Beads Integration Analyzer evaluates task tracking patterns across the jib system and generates reports with actionable insights:

- **Task Lifecycle** - Are tasks properly created, progressed, and closed?
- **Context Continuity** - Are related tasks properly linked via labels?
- **Task Quality** - Are titles searchable? Are notes meaningful?
- **Integration Coverage** - What percentage of work is tracked?
- **Abandonment Patterns** - How many tasks are left hanging?

## Metrics Tracked

| Category | Metrics |
|----------|---------|
| Volume | Total tasks, created, closed, abandoned, in-progress |
| Quality | Notes coverage, label coverage, searchable titles |
| Lifecycle | Average time to close, proper lifecycle rate |
| Integration | Slack-linked, PR-linked, JIRA-linked tasks |
| Patterns | Duplicate tasks, orphan tasks |

## Health Score

The analyzer produces a health score (0-100) based on:
- Issue severity and count (-15 for high, -8 for medium, -3 for low)
- Notes coverage bonus (+5 if >= 80%)
- Label coverage bonus (+5 if >= 90%)
- Searchable titles bonus (+5 if >= 60%)
- No abandoned tasks bonus (+5)

## Reports

Reports are submitted via **Pull Requests** with files at `docs/analysis/beads/` in the repository:
- `beads-health-YYYYMMDD-HHMMSS.md` - Full markdown report
- `beads-metrics-YYYYMMDD-HHMMSS.json` - Machine-readable metrics
- `latest-report.md` / `latest-metrics.json` - Symlinks to most recent

**Report Management:**
- Each analysis creates a new PR with the latest health report
- Only the last **5 reports** are kept in the repository
- When creating the 6th report, the oldest report is automatically deleted in the same PR
- This keeps the repository clean while maintaining recent history

**Why PRs?** Opening PRs for reports provides:
- Review-friendly format for stakeholders to review health trends
- Clear changelog of beads integration quality over time
- Automated merge via human review when ready

## Usage

```bash
# Run if last analysis was >7 days ago
./beads-analyzer.py

# Force run regardless of schedule
./beads-analyzer.py --force

# Analyze last 30 days
./beads-analyzer.py --days 30

# Print report to stdout
./beads-analyzer.py --force --stdout
```

## Systemd Timer

The analyzer runs weekly on Monday at 10:00 AM via systemd timer.

### Setup

```bash
./setup.sh
```

### Manual Commands

```bash
# Check timer status
systemctl --user list-timers | grep beads

# Run analysis now
systemctl --user start beads-analyzer.service

# View logs
journalctl --user -u beads-analyzer.service -f
```

## Issues Detected

The analyzer identifies these issue types:

| Severity | Issue | Description |
|----------|-------|-------------|
| High | Task Abandonment | Tasks in_progress for >24h without updates |
| High | Missing Context | <50% of tasks have notes |
| Medium | Poor Discoverability | <70% of tasks have labels |
| Medium | Unsearchable Titles | <60% of tasks have searchable titles |
| Medium | Unknown Source | >30% of tasks have no source labels |
| Low | Orphan Tasks | Tasks with no labels or description |
| Low | Duplicate Tasks | Tasks with similar titles |
| Low | Slow Closure | Average close time >48 hours |

## Integration with Other Analyzers

This analyzer complements:
- **conversation-analyzer** - Analyzes Slack/GitHub communication quality
- **doc-generator** - Generates documentation from codebase
- **index-generator** - Builds searchable documentation indexes

The beads-analyzer runs at 10:00 AM, before conversation-analyzer at 11:00 AM, to ensure Beads health data is available for correlation.

## See Also

- [Beads Reference](../../../docs/reference/beads.md) - Full Beads command reference
- [Beads Integration Guide](../../../docs/development/beads-integration.md) - How to integrate Beads
- [ADR: LLM Inefficiency Reporting](../../../docs/adr/not-implemented/ADR-LLM-Inefficiency-Reporting.md) - Parent ADR for this analyzer
