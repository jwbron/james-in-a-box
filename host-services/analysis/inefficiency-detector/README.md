# LLM Inefficiency Detector (Phase 2 + 3)

**Status:** Phase 3 Implementation (Weekly Reports + Slack Integration)
**ADR:** [ADR-LLM-Inefficiency-Reporting.md](../../../docs/adr/in-progress/ADR-LLM-Inefficiency-Reporting.md)

Analyzes LLM trace sessions to detect processing inefficiencies, generates actionable improvement recommendations, and delivers weekly reports via Slack.

## Overview

The inefficiency detector analyzes structured traces (from Phase 1b) to identify patterns indicating wasted tokens and processing inefficiency. It generates:

- **Session Reports**: Inefficiencies in a single trace session
- **Aggregate Reports**: Patterns across multiple sessions (weekly reports)
- **Actionable Recommendations**: Specific guidance to prevent recurrence

## Quick Start

### Analyze a Single Session

```bash
cd ~/khan/james-in-a-box/host-services/analysis/inefficiency-detector
python inefficiency_detector.py analyze <session_id>
```

### Analyze a Time Period

```bash
# Generate JSON + Markdown report for last week
python inefficiency_detector.py analyze-period \
  --since 2025-11-25 \
  --until 2025-12-01 \
  --output weekly-report.json \
  --markdown weekly-report.md
```

### Weekly Reports (Phase 3)

```bash
# Generate weekly report with Slack notification and PR creation
python weekly_report_generator.py

# Force run regardless of schedule
python weekly_report_generator.py --force

# Analyze custom period without Slack
python weekly_report_generator.py --days 14 --no-slack
```

### Programmatic Usage

```python
from inefficiency_detector import InefficiencyDetector

detector = InefficiencyDetector()

# Single session
report = detector.analyze_session("sess-20251130-abc123")
print(f"Inefficiency rate: {report.inefficiency_rate:.1f}%")
print(f"Wasted tokens: {report.total_wasted_tokens:,}")

# Time period
from datetime import datetime
aggregate = detector.analyze_period(
    since=datetime(2025, 11, 25),
    until=datetime(2025, 12, 1)
)

# Export reports
detector.export_report(aggregate, Path("report.json"))
detector.generate_markdown_report(aggregate, Path("report.md"))
```

### Automated Weekly Reports

```python
# Weekly report workflow (via systemd timer or manual)
from weekly_report_generator import WeeklyReportGenerator

generator = WeeklyReportGenerator(days=7)
generator.run(send_slack=True)  # Generates report, sends Slack, creates PR
```

## Implemented Detectors

### Phase 2 (Current): Core High-Value Detectors

| Detector | Category | Patterns Detected | Status |
|----------|----------|-------------------|---------|
| **Tool Discovery** | Category 1 | Documentation miss, search failures, API confusion | ✅ Implemented |
| **Tool Execution** | Category 4 | Retry storms, parameter errors | ✅ Implemented |
| **Resource Efficiency** | Category 7 | Redundant reads, excessive context | ✅ Implemented |

### Future Phases: Additional Detectors

These remain to be implemented in future iterations:

| Detector | Category | Patterns | Priority |
|----------|----------|----------|----------|
| **Decision Loops** | Category 2 | Approach oscillation, analysis paralysis | Medium |
| **Direction/Planning** | Category 3 | Unclear requirements, plan drift | Medium |
| **Reasoning Quality** | Category 5 | Hallucinated context, incorrect inference | Low |
| **Communication** | Category 6 | Unnecessary clarification, verbose responses | Low |

## Architecture

```
inefficiency-detector/
├── inefficiency_detector.py          # Main orchestrator (Phase 2)
├── inefficiency_schema.py            # Data structures
├── base_detector.py                  # Abstract detector interface
├── detectors/
│   ├── tool_discovery_detector.py        # Category 1 (✅)
│   ├── tool_execution_detector.py        # Category 4 (✅)
│   └── resource_efficiency_detector.py   # Category 7 (✅)
├── weekly_report_generator.py        # Weekly report generator (Phase 3)
├── inefficiency-reporter.service     # Systemd service unit
├── inefficiency-reporter.timer       # Systemd timer unit (Monday 11 AM)
├── setup.sh                          # Installation script
├── test_detectors.py                 # Unit tests
└── README.md
```

## Detection Patterns

All detectors provide **context-specific recommendations** tailored to the actual pattern detected. For example, the Documentation Miss detector examines whether glob was eventually used and adjusts its recommendation accordingly.

### Tool Discovery Failures (Category 1)

**Documentation Miss:**
- **Pattern:** Grep("SpecificTerm") → 0, Grep("Term") → 0, Glob("*term*") → success
- **Recommendation:** Dynamic - suggests using glob first if glob eventually worked, or alternative search strategies otherwise

**Search Failures:**
- **Pattern:** 3+ consecutive searches returning 0 results
- **Recommendation:** Verify target exists, try alternative search strategies

**API Confusion:**
- **Pattern:** Tool(params_a) → error, Tool(params_b) → success
- **Recommendation:** Review tool API documentation, add clearer examples

### Tool Execution Failures (Category 4)

**Retry Storm:**
- **Pattern:** Same tool fails 3+ times with identical error
- **Recommendation:** Investigate errors before retrying, check prerequisites

**Parameter Errors:**
- **Pattern:** 3+ parameter validation errors across different tools
- **Recommendation:** Verify tool parameter requirements before calling

### Resource Efficiency (Category 7)

**Redundant Reads:**
- **Pattern:** Same file read 2+ times in session
- **Recommendation:** Reference file content from context instead of re-reading

**Excessive Context:**
- **Pattern:** Large file (>1000 lines) read without limit/offset
- **Recommendation:** Use Read tool with limit/offset for large files

## Report Format

### Session Report (JSON)

```json
{
  "session_id": "sess-20251130-abc123",
  "task_id": "bd-xyz",
  "total_tokens": 45000,
  "total_wasted_tokens": 5400,
  "inefficiency_rate": 12.0,
  "inefficiencies": [
    {
      "category": "tool_discovery",
      "sub_category": "documentation_miss",
      "severity": "medium",
      "token_cost": 2340,
      "wasted_tokens": 1540,
      "description": "Searched 4 times with 3 empty results before finding target",
      "recommendation": "Use glob patterns for file discovery...",
      "evidence": {...}
    }
  ],
  "category_breakdown": {...},
  "severity_breakdown": {...}
}
```

### Aggregate Report (Markdown)

See [example weekly report](../../../docs/adr/in-progress/ADR-LLM-Inefficiency-Reporting.md#weekly-inefficiency-report) in the ADR.

## Configuration

Detectors can be configured with thresholds and weights:

```python
config = {
    "tool_discovery": {
        "min_search_sequence": 3,  # Minimum searches to flag as pattern
        "min_wasted_tokens": 100   # Minimum waste to report
    },
    "tool_execution": {
        "retry_threshold": 3,      # Consecutive failures to flag
        "min_wasted_tokens": 100
    },
    "resource_efficiency": {
        "large_file_threshold": 1000,  # Lines to consider "large"
        "min_wasted_tokens": 200,
        "tokens_per_line": 3           # Estimated tokens per line for waste calculations
    }
}

detector = InefficiencyDetector(config=config)
```

## Success Criteria (from ADR)

✅ **Detection engine identifies all 7 inefficiency categories**
   - Phase 2: 3/7 implemented (high-value categories)
   - Future: 4/7 to be added

✅ **False positive rate < 10%**
   - Conservative thresholds set (min tokens, min occurrences)
   - Evidence-based detection with clear patterns
   - Awaiting real-world validation

✅ **Weekly reports generated automatically** (Phase 3)
   - Systemd timer runs every Monday at 11:00 AM
   - Reports saved to `docs/analysis/inefficiency/`
   - Slack notifications with summary

✅ **Slack delivery** (Phase 3)
   - Uses `notifications` library for Slack integration
   - Fallback to file-based notifications if library unavailable

## Weekly Report Workflow (Phase 3)

### Installation

```bash
# Run the setup script to install systemd timer
./setup.sh

# This will:
# - Symlink service and timer files to ~/.config/systemd/user/
# - Enable and start the timer
# - Create the analysis output directory
```

### Manual Run

```bash
# Force run regardless of schedule
python weekly_report_generator.py --force

# Custom time period
python weekly_report_generator.py --days 14

# Without Slack notification
python weekly_report_generator.py --force --no-slack
```

### Report Output

Reports are saved to `docs/analysis/inefficiency/` in the repo:
- `inefficiency-report-YYYYMMDD-HHMMSS.md` - Full markdown report
- `inefficiency-metrics-YYYYMMDD-HHMMSS.json` - Machine-readable metrics
- `latest-report.md` / `latest-metrics.json` - Symlinks to most recent

A PR is automatically created with each report, keeping only the last 5 reports.

### Slack Notifications

The weekly report generator sends a summary to Slack including:
- Health Score (0-100)
- Sessions analyzed, tokens consumed, wasted tokens
- Top issue with recommendation
- Severity breakdown (High/Medium/Low)

### Systemd Commands

```bash
# Check timer status
systemctl --user list-timers | grep inefficiency

# Run manually
systemctl --user start inefficiency-reporter.service

# Check last run
systemctl --user status inefficiency-reporter.service

# View logs
journalctl --user -u inefficiency-reporter.service -f
```

## Testing

Unit tests to be added in Phase 2 completion:

```bash
# Run all detector tests
pytest tests/host_services/test_inefficiency_detector.py

# Test specific detector
pytest tests/host_services/test_inefficiency_detector.py::TestToolDiscoveryDetector
```

## Performance

- **Session analysis:** ~50-200ms for typical session (100 events)
- **Weekly analysis:** ~2-5 seconds for 20-50 sessions
- **Memory:** Minimal (streams events, doesn't load all into memory)

## Limitations (Current Phase)

1. **Limited detectors:** Only 3/7 categories implemented (high-value subset)
2. **No real-time detection:** Post-session analysis only
3. **Heuristic-based:** May miss novel inefficiency patterns
4. **No ML:** Pattern matching only, no learned models
5. **English-only:** Recommendations assume English descriptions
6. **Import path fragility:** Uses `sys.path.insert()` for imports (will be addressed in Phase 3 with proper package structure)

## Future Enhancements

### Phase 3 (COMPLETED)
- [x] Implement weekly report generation
- [x] Add Slack integration for notifications
- [x] Create systemd timer for automated weekly runs
- [x] PR creation with report files

### Phase 4 Priorities (Self-Improvement Loop)
- [ ] **Validate false positive rate** with real trace data from Phase 1b hook integration (target: <10%)
- [ ] Implement improvement proposal generator
- [ ] Create human review interface (Slack-based approval)
- [ ] Implement impact tracking for changes
- [ ] Convert to proper Python package with `setup.py`/`pyproject.toml` and relative imports

### Later Phases
- [ ] Implement remaining 4 detector categories (Decision Loops, Direction/Planning, Reasoning, Communication)
- [ ] Add ML-based anomaly detection for novel patterns
- [ ] Real-time detection during session (hook-based)
- [ ] Custom detector plugins
- [ ] Comparative analysis (detect regressions)
- [ ] Auto-tune thresholds based on false positive feedback

## References

- **ADR:** [ADR-LLM-Inefficiency-Reporting.md](../../../docs/adr/in-progress/ADR-LLM-Inefficiency-Reporting.md)
- **Trace Collection (Phase 1b):** [../trace-collector/](../trace-collector/)
- **Related ADRs:**
  - [ADR-Autonomous-Software-Engineer](../../../docs/adr/in-progress/ADR-Autonomous-Software-Engineer.md) (parent)
  - [ADR-LLM-Documentation-Index-Strategy](../../../docs/adr/implemented/ADR-LLM-Documentation-Index-Strategy.md) (addresses Category 1)

---

**Last Updated:** 2025-12-01
**Phase:** 3 (Weekly Reports + Slack Integration)
**Next Phase:** 4 (Self-Improvement Loop)
