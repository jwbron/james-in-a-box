# Codebase Analyzer

Runs daily codebase analysis (Monday 11 AM PST) and sends reports via Slack.

**Status**: Operational
**Type**: Host-side systemd timer
**Purpose**: Comprehensive code quality, structure, and pattern analysis

## Setup

```bash
cd ~/khan/james-in-a-box/host-services/analysis/codebase-analyzer
./setup.sh
```

This installs and enables the systemd timer.

## Management

```bash
# Check timer status
systemctl --user status codebase-analyzer.timer
systemctl --user list-timers | grep codebase

# Check service status
systemctl --user status codebase-analyzer.service

# Run manually (doesn't wait for timer)
systemctl --user start codebase-analyzer.service

# View logs
journalctl --user -u codebase-analyzer.service -f

# Enable/disable timer
systemctl --user enable codebase-analyzer.timer
systemctl --user disable codebase-analyzer.timer
```

## Files

- `codebase-analyzer.service` - Systemd service file
- `codebase-analyzer.timer` - Systemd timer (runs Monday 11 AM)
- `setup.sh` - Installation script
- `codebase-analyzer.py` - Analysis script

## Analysis Categories

The analyzer performs comprehensive analysis across eight categories:

| Category | Description | Auto-fixable |
|----------|-------------|--------------|
| **Code Quality** | Bare except clauses, missing error handling, style issues | Yes |
| **Structural** | Directory organization, file placement, project structure | No (human review) |
| **Unused Code** | Dead code, obsolete files, unreferenced modules | No (human review) |
| **Duplication** | Similar code patterns, repeated implementations | Partial |
| **Documentation** | README drift, outdated references, missing docs | Yes |
| **Symlinks** | Broken symlinks, incorrect targets | No (human review) |
| **Naming** | Inconsistent naming conventions (snake_case vs kebab-case) | Yes |
| **Patterns** | Design pattern consistency, anti-patterns | Partial |

## Usage

```bash
# Full analysis report (no changes)
./codebase-analyzer.py

# Focus on specific category
./codebase-analyzer.py --focus structural
./codebase-analyzer.py --focus duplication
./codebase-analyzer.py --focus unused

# Auto-fix top 10 issues and create PR
./codebase-analyzer.py --implement

# Auto-fix top 5 issues
./codebase-analyzer.py --implement --max-fixes 5
```

## Features

- **Comprehensive analysis** - Checks code quality, structure, duplication, and more
- **Pre-flight checks** - Detects broken symlinks and README issues before Claude analysis
- **Duplicate detection** - Finds similar files based on content similarity
- **Pattern detection** - Identifies anti-patterns and best practice violations
- **Auto-fix capability** - Can automatically fix code quality issues
- **Human review flagging** - Structural changes flagged for human review
- **Slack notifications** - Summary + threaded detail for mobile-first experience
- **Systemd timer integration** - Automated scheduling (Monday 11 AM PST)

## Notification Format

Reports use the **summary + thread pattern** for mobile-first Slack experience:

**Summary (top-level message)**:
- Concise key metrics (3-5 lines)
- Priority indicator
- Quick stats (HIGH/MEDIUM issue counts, security rating)

**Detail (threaded reply)**:
- Full analysis report
- File-specific improvements
- Web research findings
- Strategic recommendations

This creates two files:
- `YYYYMMDD-HHMMSS-codebase-improvements.md` (summary)
- `RESPONSE-YYYYMMDD-HHMMSS-codebase-improvements.md` (detail)

See: `slack-notifier` component for threading implementation

## Self-Improvement Tracking

The analyzer tracks its own performance metrics to identify optimization opportunities:

**Metrics tracked** (`~/.jib-sharing/tracking/codebase-analyzer-runs.jsonl`):
- Run duration and file analysis counts
- Claude API success/failure rates
- Issue detection by category and priority
- Web search query effectiveness

**Analysis performed** (based on last 10 runs):
- Performance trends (duration, throughput)
- API reliability patterns
- Common issue categories (for automated fixes)
- Search result yield effectiveness

**Self-improvement recommendations included in reports**:
- Performance optimizations (caching, parallelization)
- Reliability improvements (retry logic, timeouts)
- Analysis focus adjustments (linters, automated fixes)
- Research effectiveness (query updates, new search sources)
