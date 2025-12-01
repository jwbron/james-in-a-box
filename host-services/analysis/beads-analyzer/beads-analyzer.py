#!/usr/bin/env python3
"""
Beads Integration Analyzer for jib (James-in-a-Box)

Analyzes how well the Beads task tracking system is being used to identify
integration health issues and improvement opportunities.

Metrics tracked:
1. Task Lifecycle - Are tasks properly created, progressed, and closed?
2. Context Continuity - Are related tasks properly linked?
3. Task Quality - Are titles searchable? Are notes meaningful?
4. Integration Coverage - What percentage of work is tracked?
5. Abandonment Patterns - How many tasks are left hanging?

Reports: Creates PRs with reports committed to docs/analysis/beads/ in the repo.
         Keeps only the last 5 reports (deletes older ones when creating PR #6).

Runs on host (not in container) via systemd timer:
- Weekly (checks if last run was within 7 days)
- Can force run with --force flag

Usage:
    beads-analyzer.py [--days N] [--output DIR] [--stdout] [--force]

Example:
    beads-analyzer.py --days 7
    beads-analyzer.py --force
    beads-analyzer.py --days 30 --output ~/custom/path
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


# Add host-services/shared to path for jib_exec
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "shared"))
from jib_exec import jib_exec


# Constants
# Write to repo for version control and analyzer accessibility
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ANALYSIS_DIR = REPO_ROOT / "docs" / "analysis" / "beads"
BEADS_DIR = Path.home() / ".jib-sharing" / "beads"
ABANDONED_THRESHOLD_HOURS = 24  # Tasks in_progress longer than this are considered abandoned


@dataclass
class BeadsTask:
    """Represents a Beads task."""

    id: str
    title: str
    description: str
    notes: str
    status: str
    priority: int
    issue_type: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    labels: list[str]
    dependency_count: int
    dependent_count: int


@dataclass
class BeadsMetrics:
    """Aggregated metrics about Beads usage."""

    # Volume metrics
    total_tasks: int = 0
    tasks_created: int = 0
    tasks_closed: int = 0
    tasks_abandoned: int = 0  # in_progress for >24h without updates
    tasks_in_progress: int = 0
    tasks_blocked: int = 0

    # Quality metrics
    tasks_with_notes: int = 0
    tasks_with_description: int = 0
    tasks_with_labels: int = 0
    tasks_with_searchable_title: int = 0  # Contains PR#, repo name, or feature keyword

    # Lifecycle metrics
    avg_time_to_close_hours: float = 0
    avg_notes_per_task: float = 0
    proper_lifecycle_rate: float = 0  # open -> in_progress -> closed

    # Integration metrics
    slack_linked_tasks: int = 0
    pr_linked_tasks: int = 0
    jira_linked_tasks: int = 0

    # Pattern metrics
    duplicate_tasks: int = 0  # Tasks with very similar titles
    orphan_tasks: int = 0  # Tasks with no labels or context

    # Raw data for detailed analysis
    tasks_by_status: dict[str, int] = field(default_factory=dict)
    tasks_by_source: dict[str, int] = field(default_factory=dict)


@dataclass
class BeadsIssue:
    """Represents an identified issue with Beads usage."""

    severity: str  # high, medium, low
    category: str
    description: str
    task_ids: list[str]
    recommendation: str


@dataclass
class ClaudeAnalysis:
    """Claude-generated intelligent analysis of beads usage."""

    executive_summary: str = ""
    smart_issues: list[dict] = field(default_factory=list)  # Issues Claude detected
    recommendations: list[dict] = field(default_factory=list)  # Prioritized recommendations
    trend_analysis: str = ""  # Comparison with previous reports
    task_quality_scores: dict[str, dict] = field(
        default_factory=dict
    )  # task_id -> {score, reasons}
    patterns_detected: list[str] = field(default_factory=list)  # Workflow patterns observed
    success: bool = False
    error: str | None = None


class BeadsFetcher:
    """Fetches and parses Beads task data."""

    def __init__(self, beads_dir: Path = BEADS_DIR):
        self.beads_dir = beads_dir

    def fetch_tasks(self, days: int = 7) -> list[BeadsTask]:
        """Fetch all tasks from the last N days."""
        try:
            result = subprocess.run(
                ["bd", "--allow-stale", "list", "--json"],
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=30,
            )

            if result.returncode != 0:
                print(f"WARNING: bd list failed: {result.stderr}", file=sys.stderr)
                return []

            tasks_json = json.loads(result.stdout)
            cutoff = datetime.now() - timedelta(days=days)
            tasks = []

            for task_data in tasks_json:
                # Parse dates
                created_at = self._parse_datetime(task_data.get("created_at"))
                updated_at = self._parse_datetime(task_data.get("updated_at"))
                closed_at = self._parse_datetime(task_data.get("closed_at"))

                # Filter by date range - skip if created before cutoff AND not updated within range
                if created_at and created_at < cutoff and (not updated_at or updated_at < cutoff):
                    continue

                task = BeadsTask(
                    id=task_data.get("id", ""),
                    title=task_data.get("title", ""),
                    description=task_data.get("description", ""),
                    notes=task_data.get("notes", ""),
                    status=task_data.get("status", ""),
                    priority=task_data.get("priority", 2),
                    issue_type=task_data.get("issue_type", "task"),
                    created_at=created_at or datetime.now(),
                    updated_at=updated_at or datetime.now(),
                    closed_at=closed_at,
                    labels=task_data.get("labels", []),
                    dependency_count=task_data.get("dependency_count", 0),
                    dependent_count=task_data.get("dependent_count", 0),
                )
                tasks.append(task)

            return tasks

        except subprocess.TimeoutExpired:
            print("WARNING: bd list timed out", file=sys.stderr)
            return []
        except json.JSONDecodeError as e:
            print(f"WARNING: Failed to parse bd output: {e}", file=sys.stderr)
            return []
        except FileNotFoundError:
            print("WARNING: bd command not found", file=sys.stderr)
            return []

    def _parse_datetime(self, dt_str: str | None) -> datetime | None:
        """Parse ISO datetime string."""
        if not dt_str:
            return None
        try:
            # Handle various ISO formats
            dt_str = dt_str.replace("Z", "+00:00")
            if "." in dt_str:
                # Truncate nanoseconds to microseconds
                parts = dt_str.split(".")
                if len(parts) == 2:
                    fractional = parts[1]
                    if "+" in fractional:
                        frac_parts = fractional.split("+")
                        fractional = frac_parts[0][:6] + "+" + frac_parts[1]
                    elif "-" in fractional:
                        frac_parts = fractional.split("-")
                        fractional = frac_parts[0][:6] + "-" + frac_parts[1]
                    else:
                        fractional = fractional[:6]
                    dt_str = parts[0] + "." + fractional

            return datetime.fromisoformat(dt_str).replace(tzinfo=None)
        except ValueError:
            return None


class BeadsAnalyzer:
    """Analyzes Beads task tracking patterns."""

    def __init__(self, days: int = 7):
        self.days = days
        self.analysis_dir = ANALYSIS_DIR
        self.fetcher = BeadsFetcher()

    def calculate_metrics(self, tasks: list[BeadsTask]) -> BeadsMetrics:
        """Calculate comprehensive metrics from tasks."""
        metrics = BeadsMetrics()
        metrics.total_tasks = len(tasks)

        if not tasks:
            return metrics

        now = datetime.now()
        cutoff = now - timedelta(days=self.days)
        total_close_time = 0
        close_count = 0
        total_notes_length = 0

        for task in tasks:
            # Status distribution
            status = task.status
            metrics.tasks_by_status[status] = metrics.tasks_by_status.get(status, 0) + 1

            if status == "in_progress":
                metrics.tasks_in_progress += 1
                # Check for abandoned tasks (no update beyond threshold)
                if (now - task.updated_at).total_seconds() > ABANDONED_THRESHOLD_HOURS * 3600:
                    metrics.tasks_abandoned += 1
            elif status == "blocked":
                metrics.tasks_blocked += 1
            elif status == "closed":
                metrics.tasks_closed += 1
                if task.closed_at and task.created_at:
                    close_time = (task.closed_at - task.created_at).total_seconds() / 3600
                    total_close_time += close_time
                    close_count += 1

            # Count created in period
            if task.created_at >= cutoff:
                metrics.tasks_created += 1

            # Quality metrics
            if task.notes:
                metrics.tasks_with_notes += 1
                total_notes_length += len(task.notes)

            if task.description:
                metrics.tasks_with_description += 1

            if task.labels:
                metrics.tasks_with_labels += 1

            # Check for searchable title patterns
            if self._is_searchable_title(task.title):
                metrics.tasks_with_searchable_title += 1

            # Source tracking via labels
            labels_lower = [l.lower() for l in task.labels]
            source_found = False
            for label in labels_lower:
                if "slack" in label or label.startswith("task-"):
                    metrics.slack_linked_tasks += 1
                    metrics.tasks_by_source["slack"] = metrics.tasks_by_source.get("slack", 0) + 1
                    source_found = True
                    break
                elif label.startswith("pr-") or "github-pr" in label:
                    metrics.pr_linked_tasks += 1
                    metrics.tasks_by_source["github"] = metrics.tasks_by_source.get("github", 0) + 1
                    source_found = True
                    break
                elif "jira" in label:
                    metrics.jira_linked_tasks += 1
                    metrics.tasks_by_source["jira"] = metrics.tasks_by_source.get("jira", 0) + 1
                    source_found = True
                    break

            if not source_found:
                metrics.tasks_by_source["unknown"] = metrics.tasks_by_source.get("unknown", 0) + 1

            # Orphan detection
            if not task.labels and not task.description:
                metrics.orphan_tasks += 1

        # Calculate averages
        if close_count > 0:
            metrics.avg_time_to_close_hours = total_close_time / close_count

        if metrics.tasks_with_notes > 0:
            metrics.avg_notes_per_task = total_notes_length / metrics.tasks_with_notes

        # Calculate proper lifecycle rate
        # Tasks that went through open -> in_progress -> closed
        properly_managed = sum(
            1
            for t in tasks
            if t.status == "closed" and t.notes  # Has progress notes
        )
        if metrics.tasks_closed > 0:
            metrics.proper_lifecycle_rate = (properly_managed / metrics.tasks_closed) * 100

        # Detect duplicates (similar titles)
        metrics.duplicate_tasks = self._count_duplicates(tasks)

        return metrics

    def _is_searchable_title(self, title: str) -> bool:
        """Check if a title contains searchable identifiers."""
        title_lower = title.lower()

        # Check for PR numbers
        if "pr #" in title_lower or "pr-" in title_lower or "#" in title_lower:
            return True

        # Check for repo names (common patterns)
        if any(repo in title_lower for repo in ["james-in-a-box", "webapp", "services", "jib"]):
            return True

        # Check for JIRA tickets
        if any(pattern in title_lower for pattern in ["jira-", "project-", "issue-"]):
            return True

        # Check for meaningful prefixes
        good_prefixes = ["fix:", "feat:", "refactor:", "bug:", "feature:"]
        if any(title_lower.startswith(prefix) for prefix in good_prefixes):
            return True

        # Check minimum length and not generic
        generic_titles = [
            "fix bug",
            "update code",
            "wip",
            "work in progress",
            "todo",
            "task",
        ]
        return bool(len(title) > 20 and title_lower not in generic_titles)

    def _count_duplicates(self, tasks: list[BeadsTask]) -> int:
        """Count tasks with very similar titles."""
        # Simple duplicate detection based on title similarity
        titles = [t.title.lower().strip() for t in tasks]
        duplicates = 0

        seen = set()
        for title in titles:
            # Normalize title
            normalized = " ".join(title.split())
            if normalized in seen:
                duplicates += 1
            seen.add(normalized)

        return duplicates

    def identify_issues(self, tasks: list[BeadsTask], metrics: BeadsMetrics) -> list[BeadsIssue]:
        """Identify issues with Beads usage."""
        issues = []

        # High: Abandoned tasks
        if metrics.tasks_abandoned > 0:
            abandoned = [
                t.id
                for t in tasks
                if t.status == "in_progress"
                and (datetime.now() - t.updated_at).total_seconds()
                > ABANDONED_THRESHOLD_HOURS * 3600
            ]
            issues.append(
                BeadsIssue(
                    severity="high",
                    category="Task Abandonment",
                    description=f"{metrics.tasks_abandoned} tasks in_progress for >{ABANDONED_THRESHOLD_HOURS}h without updates",
                    task_ids=abandoned[:10],  # Limit to first 10
                    recommendation="Review and either close or update these tasks. If blocked, mark as blocked with notes.",
                )
            )

        # High: Low notes coverage
        notes_rate = (
            (metrics.tasks_with_notes / metrics.total_tasks * 100) if metrics.total_tasks else 0
        )
        if notes_rate < 50 and metrics.total_tasks >= 5:
            no_notes = [t.id for t in tasks if not t.notes]
            issues.append(
                BeadsIssue(
                    severity="high",
                    category="Missing Context",
                    description=f"Only {notes_rate:.0f}% of tasks have notes (goal: >80%)",
                    task_ids=no_notes[:10],
                    recommendation="Add progress notes to tasks. Notes are critical for context continuity across sessions.",
                )
            )

        # Medium: Low label coverage
        label_rate = (
            (metrics.tasks_with_labels / metrics.total_tasks * 100) if metrics.total_tasks else 0
        )
        if label_rate < 70 and metrics.total_tasks >= 5:
            no_labels = [t.id for t in tasks if not t.labels]
            issues.append(
                BeadsIssue(
                    severity="medium",
                    category="Poor Discoverability",
                    description=f"Only {label_rate:.0f}% of tasks have labels (goal: >90%)",
                    task_ids=no_labels[:10],
                    recommendation="Add labels for source (slack/github/jira), type (feature/bug), and repo name.",
                )
            )

        # Medium: Poor searchable titles
        searchable_rate = (
            (metrics.tasks_with_searchable_title / metrics.total_tasks * 100)
            if metrics.total_tasks
            else 0
        )
        if searchable_rate < 60 and metrics.total_tasks >= 5:
            bad_titles = [t.id for t in tasks if not self._is_searchable_title(t.title)]
            issues.append(
                BeadsIssue(
                    severity="medium",
                    category="Unsearchable Titles",
                    description=f"Only {searchable_rate:.0f}% of tasks have searchable titles",
                    task_ids=bad_titles[:10],
                    recommendation="Include PR numbers, repo names, or feature keywords in task titles.",
                )
            )

        # Medium: Many tasks from unknown sources
        unknown_count = metrics.tasks_by_source.get("unknown", 0)
        if unknown_count > metrics.total_tasks * 0.3 and metrics.total_tasks >= 5:
            unknown = [
                t.id
                for t in tasks
                if not any(
                    l.lower().startswith(("slack", "pr-", "github", "jira", "task-"))
                    for l in t.labels
                )
            ]
            issues.append(
                BeadsIssue(
                    severity="medium",
                    category="Unknown Source",
                    description=f"{unknown_count} tasks have no source tracking labels",
                    task_ids=unknown[:10],
                    recommendation="Add source labels (slack-thread, github-pr, jira-XXXX) to track where tasks originated.",
                )
            )

        # Low: Orphan tasks
        if metrics.orphan_tasks > 0:
            orphans = [t.id for t in tasks if not t.labels and not t.description]
            issues.append(
                BeadsIssue(
                    severity="low",
                    category="Orphan Tasks",
                    description=f"{metrics.orphan_tasks} tasks have no labels or description",
                    task_ids=orphans[:10],
                    recommendation="Add context to these tasks or close if no longer relevant.",
                )
            )

        # Low: Duplicate tasks
        if metrics.duplicate_tasks > 0:
            issues.append(
                BeadsIssue(
                    severity="low",
                    category="Duplicate Tasks",
                    description=f"Found {metrics.duplicate_tasks} potential duplicate tasks",
                    task_ids=[],
                    recommendation="Review tasks with similar titles and consolidate if appropriate.",
                )
            )

        # Low: Long average close time
        if metrics.avg_time_to_close_hours > 48:
            issues.append(
                BeadsIssue(
                    severity="low",
                    category="Slow Closure",
                    description=f"Average time to close is {metrics.avg_time_to_close_hours:.1f} hours",
                    task_ids=[],
                    recommendation="Break large tasks into smaller ones. Close tasks promptly when work is done.",
                )
            )

        return sorted(issues, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x.severity])

    def generate_report(
        self,
        tasks: list[BeadsTask],
        metrics: BeadsMetrics,
        issues: list[BeadsIssue],
        claude_analysis: ClaudeAnalysis | None = None,
    ) -> str:
        """Generate markdown report."""
        now = datetime.now()

        # Calculate rates
        notes_rate = (
            (metrics.tasks_with_notes / metrics.total_tasks * 100) if metrics.total_tasks else 0
        )
        label_rate = (
            (metrics.tasks_with_labels / metrics.total_tasks * 100) if metrics.total_tasks else 0
        )
        searchable_rate = (
            (metrics.tasks_with_searchable_title / metrics.total_tasks * 100)
            if metrics.total_tasks
            else 0
        )

        # Health score (0-100)
        health_score = self._calculate_health_score(metrics, issues)

        report = f"""# Beads Integration Health Report
Generated: {now.strftime("%Y-%m-%d %H:%M:%S")}
Period: Last {self.days} days

## Health Score: {health_score}/100 {self._get_health_emoji(health_score)}

## Executive Summary

| Metric | Value | Status |
|--------|-------|--------|
| Total Tasks | {metrics.total_tasks} | - |
| Tasks Created | {metrics.tasks_created} | - |
| Tasks Closed | {metrics.tasks_closed} | {"✅" if metrics.tasks_closed > 0 else "⚠️"} |
| Tasks In Progress | {metrics.tasks_in_progress} | - |
| Abandoned Tasks | {metrics.tasks_abandoned} | {"✅" if metrics.tasks_abandoned == 0 else "⚠️"} |
| Notes Coverage | {notes_rate:.0f}% | {"✅" if notes_rate >= 80 else "⚠️"} |
| Label Coverage | {label_rate:.0f}% | {"✅" if label_rate >= 90 else "⚠️"} |
| Searchable Titles | {searchable_rate:.0f}% | {"✅" if searchable_rate >= 60 else "⚠️"} |

## Task Distribution

### By Status
```
"""
        # Status bar chart
        max_count = max(metrics.tasks_by_status.values()) if metrics.tasks_by_status else 1
        for status, count in sorted(metrics.tasks_by_status.items()):
            bar_len = int((count / max_count) * 20)
            bar = "█" * bar_len
            report += f"{status:15} {bar:20} {count}\n"

        report += """```

### By Source
```
"""
        # Source bar chart
        max_count = max(metrics.tasks_by_source.values()) if metrics.tasks_by_source else 1
        for source, count in sorted(metrics.tasks_by_source.items(), key=lambda x: -x[1]):
            bar_len = int((count / max_count) * 20)
            bar = "█" * bar_len
            report += f"{source:15} {bar:20} {count}\n"

        report += f"""```

## Quality Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Tasks with Notes | {metrics.tasks_with_notes}/{metrics.total_tasks} ({notes_rate:.0f}%) | >80% | {"✅" if notes_rate >= 80 else "⚠️"} |
| Tasks with Labels | {metrics.tasks_with_labels}/{metrics.total_tasks} ({label_rate:.0f}%) | >90% | {"✅" if label_rate >= 90 else "⚠️"} |
| Searchable Titles | {metrics.tasks_with_searchable_title}/{metrics.total_tasks} ({searchable_rate:.0f}%) | >60% | {"✅" if searchable_rate >= 60 else "⚠️"} |
| Proper Lifecycle | {metrics.proper_lifecycle_rate:.0f}% | >70% | {"✅" if metrics.proper_lifecycle_rate >= 70 else "⚠️"} |

## Lifecycle Metrics

- **Average Time to Close**: {metrics.avg_time_to_close_hours:.1f} hours
- **Average Notes Length**: {metrics.avg_notes_per_task:.0f} characters
- **Orphan Tasks**: {metrics.orphan_tasks}
- **Duplicate Tasks**: {metrics.duplicate_tasks}

## Integration Coverage

| Source | Tasks | Percentage |
|--------|-------|------------|
| Slack | {metrics.slack_linked_tasks} | {(metrics.slack_linked_tasks / metrics.total_tasks * 100) if metrics.total_tasks else 0:.0f}% |
| GitHub PR | {metrics.pr_linked_tasks} | {(metrics.pr_linked_tasks / metrics.total_tasks * 100) if metrics.total_tasks else 0:.0f}% |
| JIRA | {metrics.jira_linked_tasks} | {(metrics.jira_linked_tasks / metrics.total_tasks * 100) if metrics.total_tasks else 0:.0f}% |
| Unknown | {metrics.tasks_by_source.get("unknown", 0)} | {(metrics.tasks_by_source.get("unknown", 0) / metrics.total_tasks * 100) if metrics.total_tasks else 0:.0f}% |

## Issues Identified

"""
        if issues:
            for issue in issues:
                severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}[issue.severity]
                report += f"""### {severity_emoji} [{issue.severity.upper()}] {issue.category}

**Issue**: {issue.description}

**Recommendation**: {issue.recommendation}

"""
                if issue.task_ids:
                    report += "**Affected Tasks**: " + ", ".join(
                        f"`{tid}`" for tid in issue.task_ids[:5]
                    )
                    if len(issue.task_ids) > 5:
                        report += f" (+{len(issue.task_ids) - 5} more)"
                    report += "\n\n"
        else:
            report += "*No issues identified - great work!*\n\n"

        report += """## Recommendations

"""
        # Generate recommendations based on metrics
        recommendations = self._generate_recommendations(metrics, issues)
        for i, rec in enumerate(recommendations, 1):
            report += f"{i}. {rec}\n"

        report += """
## Recent Tasks

| ID | Title | Status | Source | Updated |
|----|-------|--------|--------|---------|
"""
        # Show recent tasks
        recent = sorted(tasks, key=lambda t: t.updated_at, reverse=True)[:15]
        for task in recent:
            title_short = task.title[:40] + "..." if len(task.title) > 40 else task.title
            source = "unknown"
            for label in task.labels:
                if "slack" in label.lower() or label.startswith("task-"):
                    source = "slack"
                    break
                elif label.startswith("pr-") or "github" in label.lower():
                    source = "github"
                    break
                elif "jira" in label.lower():
                    source = "jira"
                    break
            updated = task.updated_at.strftime("%m/%d %H:%M")
            report += f"| `{task.id}` | {title_short} | {task.status} | {source} | {updated} |\n"

        # Add Claude-powered analysis section if available
        if claude_analysis:
            report += self._format_claude_analysis_section(claude_analysis)

        report += f"""
---

*Report generated from {metrics.total_tasks} tasks over {self.days} days*
*Saved to: ~/sharing/analysis/beads/*
"""
        return report

    def _calculate_health_score(self, metrics: BeadsMetrics, issues: list[BeadsIssue]) -> int:
        """Calculate overall health score (0-100)."""
        if metrics.total_tasks == 0:
            return 100  # No tasks = nothing wrong

        score = 100

        # Deduct for issues
        for issue in issues:
            if issue.severity == "high":
                score -= 15
            elif issue.severity == "medium":
                score -= 8
            else:
                score -= 3

        # Bonus for good practices
        notes_rate = metrics.tasks_with_notes / metrics.total_tasks
        label_rate = metrics.tasks_with_labels / metrics.total_tasks
        searchable_rate = metrics.tasks_with_searchable_title / metrics.total_tasks

        if notes_rate >= 0.8:
            score += 5
        if label_rate >= 0.9:
            score += 5
        if searchable_rate >= 0.6:
            score += 5
        if metrics.tasks_abandoned == 0:
            score += 5

        return max(0, min(100, score))

    def _get_health_emoji(self, score: int) -> str:
        """Get emoji for health score."""
        if score >= 90:
            return "🌟"
        elif score >= 70:
            return "✅"
        elif score >= 50:
            return "⚠️"
        else:
            return "🔴"

    def _generate_recommendations(
        self, metrics: BeadsMetrics, issues: list[BeadsIssue]
    ) -> list[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Based on issues
        high_issues = [i for i in issues if i.severity == "high"]
        if high_issues:
            recommendations.append(
                f"**Priority**: Address {len(high_issues)} high-severity issues first"
            )

        # Based on metrics
        notes_rate = metrics.tasks_with_notes / metrics.total_tasks if metrics.total_tasks else 0
        if notes_rate < 0.8:
            recommendations.append(
                "Add progress notes when updating tasks to maintain context across sessions"
            )

        label_rate = metrics.tasks_with_labels / metrics.total_tasks if metrics.total_tasks else 0
        if label_rate < 0.9:
            recommendations.append(
                "Add labels to all tasks: source (slack/github), type (feature/bug), repo name"
            )

        searchable_rate = (
            metrics.tasks_with_searchable_title / metrics.total_tasks if metrics.total_tasks else 0
        )
        if searchable_rate < 0.6:
            recommendations.append(
                "Include PR numbers, repo names, or feature keywords in task titles for better searchability"
            )

        if metrics.tasks_abandoned > 0:
            recommendations.append(
                f"Review {metrics.tasks_abandoned} abandoned tasks and either close or update them"
            )

        if metrics.tasks_by_source.get("unknown", 0) > metrics.total_tasks * 0.3:
            recommendations.append(
                "Add source tracking labels (slack-thread, github-pr, jira-XXX) to improve traceability"
            )

        if not recommendations:
            recommendations.append("Keep up the good work! Beads integration is healthy.")

        return recommendations

    def _get_previous_report(self) -> dict | None:
        """Load the most recent previous metrics report for trend comparison."""
        try:
            metrics_files = sorted(
                self.analysis_dir.glob("beads-metrics-*.json"),
                key=lambda p: p.stem,
                reverse=True,
            )
            # Skip the current one if it exists, get the previous
            for metrics_file in metrics_files[1:2]:  # Get second most recent
                with open(metrics_file) as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def run_claude_analysis(
        self,
        tasks: list[BeadsTask],
        metrics: BeadsMetrics,
        issues: list[BeadsIssue],
    ) -> ClaudeAnalysis:
        """Run intelligent analysis using Claude via jib --exec.

        This provides:
        1. Executive summary - Human-readable overview
        2. Smart issue detection - Pattern-based issues beyond rule-based
        3. Prioritized recommendations - Actionable, specific advice
        4. Trend analysis - Comparison with previous reports
        5. Task quality scoring - Per-task quality assessment
        6. Pattern detection - Workflow patterns observed
        """
        print("Running Claude-powered analysis...")

        # Prepare task data for Claude (limit to avoid token limits)
        task_summaries = []
        for task in tasks[:50]:  # Limit to 50 most recent
            task_summaries.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "labels": task.labels,
                    "has_notes": bool(task.notes),
                    "has_description": bool(task.description),
                    "created": task.created_at.isoformat() if task.created_at else None,
                    "updated": task.updated_at.isoformat() if task.updated_at else None,
                    "closed": task.closed_at.isoformat() if task.closed_at else None,
                    "notes_preview": task.notes[:200] if task.notes else "",
                }
            )

        # Get previous report for trend analysis
        previous_report = self._get_previous_report()

        # Prepare issues for Claude
        issue_summaries = [
            {
                "severity": i.severity,
                "category": i.category,
                "description": i.description,
                "task_count": len(i.task_ids),
            }
            for i in issues
        ]

        # Build the prompt
        prompt = f"""You are analyzing Beads task tracking usage for an AI software engineering agent.
Beads is a persistent task memory system that helps track work across container sessions.

## Current Metrics (Last {self.days} days)

- Total Tasks: {metrics.total_tasks}
- Created: {metrics.tasks_created}
- Closed: {metrics.tasks_closed}
- In Progress: {metrics.tasks_in_progress}
- Abandoned (>24h no update): {metrics.tasks_abandoned}
- Tasks with Notes: {metrics.tasks_with_notes} ({
            100 * metrics.tasks_with_notes // max(1, metrics.total_tasks)
        }%)
- Tasks with Labels: {metrics.tasks_with_labels} ({
            100 * metrics.tasks_with_labels // max(1, metrics.total_tasks)
        }%)
- Searchable Titles: {metrics.tasks_with_searchable_title} ({
            100 * metrics.tasks_with_searchable_title // max(1, metrics.total_tasks)
        }%)
- Avg Time to Close: {metrics.avg_time_to_close_hours:.1f} hours

## Task Distribution by Status
{json.dumps(metrics.tasks_by_status, indent=2)}

## Task Distribution by Source
{json.dumps(metrics.tasks_by_source, indent=2)}

## Rule-Based Issues Already Identified
{json.dumps(issue_summaries, indent=2)}

## Sample Tasks (most recent {len(task_summaries)})
{json.dumps(task_summaries, indent=2)}

{
            f'''## Previous Report Metrics (for trend comparison)
{json.dumps(previous_report, indent=2)}
'''
            if previous_report
            else "## Previous Report: None available (first report)"
        }

---

Please analyze this data and provide a JSON response with the following structure:

```json
{{
  "executive_summary": "A 2-3 paragraph human-readable summary of the beads usage health, highlighting key strengths and concerns.",

  "smart_issues": [
    {{
      "severity": "high|medium|low",
      "title": "Brief issue title",
      "description": "Detailed description of the issue",
      "affected_tasks": ["task-id-1", "task-id-2"],
      "recommendation": "Specific action to fix this"
    }}
  ],

  "recommendations": [
    {{
      "priority": 1,
      "title": "Recommendation title",
      "description": "Why this matters and how to do it",
      "effort": "low|medium|high",
      "impact": "low|medium|high"
    }}
  ],

  "trend_analysis": "Analysis of how metrics have changed compared to the previous report. Note improvements and regressions.",

  "task_quality_scores": {{
    "task-id": {{
      "score": 85,
      "strengths": ["Good title", "Has labels"],
      "weaknesses": ["Missing notes"]
    }}
  }},

  "patterns_detected": [
    "Description of workflow pattern observed (e.g., 'Tasks from Slack often lack proper closure')"
  ]
}}
```

Focus on:
1. Identifying issues that simple rules might miss (e.g., tasks that seem related but aren't linked)
2. Providing specific, actionable recommendations with priority
3. Detecting workflow anti-patterns
4. Scoring task quality to identify which tasks need improvement
5. Comparing trends if previous data is available

Only output valid JSON, no other text."""

        # Call Claude via jib --exec
        result = jib_exec(
            processor="jib-container/jib-tasks/analysis/analysis-processor.py",
            task_type="llm_prompt",
            context={
                "prompt": prompt,
                "timeout": 120,
            },
            timeout=180,
        )

        analysis = ClaudeAnalysis()

        if not result.success:
            analysis.error = result.error or "Claude analysis failed"
            print(f"  Claude analysis failed: {analysis.error}")
            return analysis

        # Parse the response
        try:
            # The result is nested: result.json_output.result.stdout contains Claude's response
            if result.json_output and result.json_output.get("success"):
                claude_output = result.json_output.get("result", {}).get("stdout", "")

                # Extract JSON from the response (may be wrapped in markdown code blocks)
                json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", claude_output)
                if json_match:
                    claude_output = json_match.group(1)

                parsed = json.loads(claude_output)

                analysis.executive_summary = parsed.get("executive_summary", "")
                analysis.smart_issues = parsed.get("smart_issues", [])
                analysis.recommendations = parsed.get("recommendations", [])
                analysis.trend_analysis = parsed.get("trend_analysis", "")
                analysis.task_quality_scores = parsed.get("task_quality_scores", {})
                analysis.patterns_detected = parsed.get("patterns_detected", [])
                analysis.success = True

                print("  ✓ Claude analysis complete")
                print(f"    - {len(analysis.smart_issues)} smart issues detected")
                print(f"    - {len(analysis.recommendations)} recommendations")
                print(f"    - {len(analysis.patterns_detected)} patterns detected")

            else:
                analysis.error = (
                    result.json_output.get("error", "Unknown error")
                    if result.json_output
                    else "No output"
                )
                print(f"  Claude returned error: {analysis.error}")

        except json.JSONDecodeError as e:
            analysis.error = f"Failed to parse Claude response: {e}"
            print(f"  {analysis.error}")
        except Exception as e:
            analysis.error = f"Error processing Claude response: {e}"
            print(f"  {analysis.error}")

        return analysis

    def _format_claude_analysis_section(self, analysis: ClaudeAnalysis) -> str:
        """Format Claude analysis as markdown for the report."""
        if not analysis.success:
            return f"""
## AI-Powered Analysis

*Analysis unavailable: {analysis.error}*
"""

        sections = []

        # Executive Summary
        if analysis.executive_summary:
            sections.append(f"""
## Executive Summary

{analysis.executive_summary}
""")

        # Smart Issues
        if analysis.smart_issues:
            issues_md = "\n".join(
                [
                    f"### {i.get('severity', 'medium').upper()}: {i.get('title', 'Issue')}\n\n"
                    f"{i.get('description', '')}\n\n"
                    f"**Recommendation**: {i.get('recommendation', 'N/A')}\n"
                    for i in analysis.smart_issues
                ]
            )
            sections.append(f"""
## AI-Detected Issues

{issues_md}
""")

        # Prioritized Recommendations
        if analysis.recommendations:
            recs_md = "\n".join(
                [
                    f"{r.get('priority', '?')}. **{r.get('title', 'Recommendation')}** "
                    f"(effort: {r.get('effort', '?')}, impact: {r.get('impact', '?')})\n\n"
                    f"   {r.get('description', '')}\n"
                    for r in sorted(analysis.recommendations, key=lambda x: x.get("priority", 99))
                ]
            )
            sections.append(f"""
## AI Recommendations (Prioritized)

{recs_md}
""")

        # Trend Analysis
        if analysis.trend_analysis:
            sections.append(f"""
## Trend Analysis

{analysis.trend_analysis}
""")

        # Patterns Detected
        if analysis.patterns_detected:
            patterns_md = "\n".join([f"- {p}" for p in analysis.patterns_detected])
            sections.append(f"""
## Workflow Patterns Detected

{patterns_md}
""")

        # Task Quality (show worst 5)
        if analysis.task_quality_scores:
            worst_tasks = sorted(
                analysis.task_quality_scores.items(), key=lambda x: x[1].get("score", 100)
            )[:5]
            if worst_tasks:
                quality_md = "\n".join(
                    [
                        f"- **{tid}** (score: {info.get('score', '?')}/100): "
                        f"{', '.join(info.get('weaknesses', []))}"
                        for tid, info in worst_tasks
                    ]
                )
                sections.append(f"""
## Tasks Needing Improvement

{quality_md}
""")

        return "\n".join(sections)

    def run_analysis(self, skip_claude: bool = False) -> str | None:
        """Run full analysis and generate report.

        Args:
            skip_claude: If True, skip the Claude-powered analysis (faster but less insightful)
        """
        print(f"Analyzing Beads integration from last {self.days} days...")

        # Fetch tasks
        print("Fetching Beads tasks...")
        tasks = self.fetcher.fetch_tasks(self.days)
        print(f"  Found {len(tasks)} tasks")

        claude_analysis = None

        if not tasks:
            print("WARNING: No tasks found for analysis", file=sys.stderr)
            # Generate empty report
            metrics = BeadsMetrics()
            issues = []
        else:
            # Calculate metrics
            print("Calculating metrics...")
            metrics = self.calculate_metrics(tasks)

            # Identify issues
            print("Identifying issues...")
            issues = self.identify_issues(tasks, metrics)

            # Run Claude-powered analysis (unless skipped)
            if not skip_claude:
                claude_analysis = self.run_claude_analysis(tasks, metrics, issues)

        # Generate report (now includes Claude analysis)
        print("Generating report...")
        report = self.generate_report(tasks, metrics, issues, claude_analysis)

        # Ensure output directory exists
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_file = self.analysis_dir / f"beads-health-{timestamp}.md"
        with open(report_file, "w") as f:
            f.write(report)

        # Save metrics as JSON
        metrics_file = self.analysis_dir / f"beads-metrics-{timestamp}.json"
        with open(metrics_file, "w") as f:
            json.dump(
                {
                    "timestamp": timestamp,
                    "days_analyzed": self.days,
                    "total_tasks": metrics.total_tasks,
                    "tasks_created": metrics.tasks_created,
                    "tasks_closed": metrics.tasks_closed,
                    "tasks_abandoned": metrics.tasks_abandoned,
                    "tasks_in_progress": metrics.tasks_in_progress,
                    "tasks_blocked": metrics.tasks_blocked,
                    "tasks_with_notes": metrics.tasks_with_notes,
                    "tasks_with_labels": metrics.tasks_with_labels,
                    "tasks_with_searchable_title": metrics.tasks_with_searchable_title,
                    "avg_time_to_close_hours": metrics.avg_time_to_close_hours,
                    "proper_lifecycle_rate": metrics.proper_lifecycle_rate,
                    "slack_linked_tasks": metrics.slack_linked_tasks,
                    "pr_linked_tasks": metrics.pr_linked_tasks,
                    "jira_linked_tasks": metrics.jira_linked_tasks,
                    "tasks_by_status": metrics.tasks_by_status,
                    "tasks_by_source": metrics.tasks_by_source,
                    "issues_count": {
                        "high": len([i for i in issues if i.severity == "high"]),
                        "medium": len([i for i in issues if i.severity == "medium"]),
                        "low": len([i for i in issues if i.severity == "low"]),
                    },
                    "health_score": self._calculate_health_score(metrics, issues),
                },
                f,
                indent=2,
            )

        # Create latest symlinks
        latest_report = self.analysis_dir / "latest-report.md"
        latest_metrics = self.analysis_dir / "latest-metrics.json"

        if latest_report.exists():
            latest_report.unlink()
        if latest_metrics.exists():
            latest_metrics.unlink()

        latest_report.symlink_to(report_file.name)
        latest_metrics.symlink_to(metrics_file.name)

        print("\n✓ Analysis complete!")
        print(f"  Report: {report_file}")
        print(f"  Metrics: {metrics_file}")
        print(f"  Latest: {latest_report}")

        # Create PR with reports
        self._create_pr_with_reports(metrics, issues, report_file, timestamp)

        return report

    def _cleanup_old_reports(self, max_reports: int = 5) -> list[Path]:
        """Keep only the last N reports, return files to be deleted."""
        # Find all report files (both .md and .json)
        report_files = sorted(
            self.analysis_dir.glob("beads-health-*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        metrics_files = sorted(
            self.analysis_dir.glob("beads-metrics-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        to_delete = []

        # Keep only the last max_reports
        if len(report_files) > max_reports:
            to_delete.extend(report_files[max_reports:])
        if len(metrics_files) > max_reports:
            to_delete.extend(metrics_files[max_reports:])

        return to_delete

    def _create_pr_with_reports(
        self,
        metrics: BeadsMetrics,
        issues: list[BeadsIssue],
        report_file: Path,
        timestamp: str,
    ):
        """Create a PR with the health reports via jib --exec.

        Uses jib_exec to run git operations inside a container where worktrees
        are already set up, avoiding interference with the host's main worktree.
        """
        print("\nPreparing to create PR with health reports via jib --exec...")

        # Cleanup old reports (keep only last 5)
        to_delete = self._cleanup_old_reports(max_reports=5)

        # Determine branch name
        branch_name = f"beads-health-report-{timestamp}"

        # Calculate health score for commit message and PR
        health_score = self._calculate_health_score(metrics, issues)

        # Build list of files to commit
        files = []

        # Read all report files from analysis_dir
        for report_path in self.analysis_dir.glob("beads-health-*.md"):
            rel_path = report_path.relative_to(REPO_ROOT)
            files.append(
                {
                    "path": str(rel_path),
                    "content": report_path.read_text(),
                }
            )

        for metrics_path in self.analysis_dir.glob("beads-metrics-*.json"):
            rel_path = metrics_path.relative_to(REPO_ROOT)
            files.append(
                {
                    "path": str(rel_path),
                    "content": metrics_path.read_text(),
                }
            )

        # Create symlinks to latest report/metrics
        symlinks = [
            {
                "path": "docs/analysis/beads/latest-report.md",
                "target": f"beads-health-{timestamp}.md",
            },
            {
                "path": "docs/analysis/beads/latest-metrics.json",
                "target": f"beads-metrics-{timestamp}.json",
            },
        ]

        # Convert to_delete paths to relative paths for the container
        files_to_delete = [str(p.relative_to(REPO_ROOT)) for p in to_delete]

        if not files and not symlinks:
            print("ERROR: No report files to commit", file=sys.stderr)
            return

        # Build commit message
        commit_message = f"""chore: Add Beads health report {timestamp}

Health Score: {health_score}/100
- Total Tasks: {metrics.total_tasks}
- Closed: {metrics.tasks_closed}
- Abandoned: {metrics.tasks_abandoned}

High-severity issues: {len([i for i in issues if i.severity == "high"])}
"""

        # Build PR body
        pr_title = f"Beads Health Report - {timestamp}"
        pr_body = f"""## Beads Integration Health Report

**Health Score**: {health_score}/100 {self._get_health_emoji(health_score)}

### Quick Stats
- 📝 Total Tasks: {metrics.total_tasks}
- ✅ Closed: {metrics.tasks_closed}
- ⏳ In Progress: {metrics.tasks_in_progress}
- ⚠️ Abandoned: {metrics.tasks_abandoned}

### Issues Summary
- 🔴 High: {len([i for i in issues if i.severity == "high"])}
- 🟡 Medium: {len([i for i in issues if i.severity == "medium"])}
- 🟢 Low: {len([i for i in issues if i.severity == "low"])}

### Files in this PR
- `docs/analysis/beads/beads-health-{timestamp}.md` - Full health report
- `docs/analysis/beads/beads-metrics-{timestamp}.json` - Machine-readable metrics
- Symlinks updated to point to latest reports

{("### Cleanup" + chr(10) + f"- Removed {len(to_delete)} old report(s) to maintain max 5 reports") if to_delete else ""}

See the full report in `docs/analysis/beads/beads-health-{timestamp}.md` for detailed analysis.
"""

        # Call jib --exec to create PR inside container
        print(f"Invoking jib --exec to create PR on branch {branch_name}...")
        if files_to_delete:
            print(f"  Will delete {len(files_to_delete)} old report(s)")
        result = jib_exec(
            processor="jib-container/jib-tasks/analysis/analysis-processor.py",
            task_type="create_pr",
            context={
                "repo_name": "james-in-a-box",
                "branch_name": branch_name,
                "files": files,
                "symlinks": symlinks,
                "files_to_delete": files_to_delete,
                "commit_message": commit_message,
                "pr_title": pr_title,
                "pr_body": pr_body,
            },
            timeout=300,
        )

        if result.success and result.json_output:
            pr_url = result.json_output.get("result", {}).get("pr_url", "")
            print(f"✓ Created PR: {pr_url}")
        else:
            print(f"ERROR creating PR: {result.error}", file=sys.stderr)
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}", file=sys.stderr)


def check_last_run(analysis_dir: Path) -> datetime | None:
    """Check when the analyzer was last run."""
    try:
        reports = list(analysis_dir.glob("beads-analysis-*.md"))
        if not reports:
            return None

        reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        most_recent = reports[0]
        return datetime.fromtimestamp(most_recent.stat().st_mtime)
    except Exception:
        return None


def should_run_analysis(analysis_dir: Path, force: bool = False) -> bool:
    """Determine if analysis should run based on weekly schedule."""
    if force:
        print("Force flag set - running analysis")
        return True

    last_run = check_last_run(analysis_dir)

    if last_run is None:
        print("No previous analysis found - running analysis")
        return True

    days_since_last_run = (datetime.now() - last_run).days

    if days_since_last_run >= 7:
        print(f"Last analysis was {days_since_last_run} days ago - running analysis")
        return True
    else:
        print(f"Last analysis was {days_since_last_run} days ago (< 7 days) - skipping")
        print("Use --force to run anyway")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Beads task tracking integration health",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run if last analysis was >7 days ago
  %(prog)s --force            # Force run regardless of schedule
  %(prog)s --days 30          # Analyze last 30 days
        """,
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to analyze (default: 7)"
    )
    parser.add_argument(
        "--output", type=Path, help="Output directory (default: docs/analysis/beads in repo)"
    )
    parser.add_argument(
        "--stdout", action="store_true", dest="print_to_stdout", help="Print report to stdout"
    )
    parser.add_argument("--force", action="store_true", help="Force analysis even if run recently")
    parser.add_argument(
        "--skip-claude",
        action="store_true",
        help="Skip Claude-powered AI analysis (faster but less insightful)",
    )

    args = parser.parse_args()

    # Determine analysis directory
    analysis_dir = args.output if args.output else ANALYSIS_DIR

    # Check if we should run
    if not should_run_analysis(analysis_dir, force=args.force):
        sys.exit(0)

    analyzer = BeadsAnalyzer(days=args.days)

    if args.output:
        analyzer.analysis_dir = args.output
        analyzer.analysis_dir.mkdir(parents=True, exist_ok=True)

    report = analyzer.run_analysis(skip_claude=args.skip_claude)

    if args.print_to_stdout and report:
        print("\n" + "=" * 80)
        print(report)
        print("=" * 80)


if __name__ == "__main__":
    main()
