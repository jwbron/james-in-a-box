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

Reports: ~/sharing/analysis/beads/

Runs on host (not in container) via systemd timer:
- Weekly (checks if last run was within 7 days)
- Can force run with --force flag

Usage:
    beads-analyzer.py [--days N] [--output DIR] [--force]

Example:
    beads-analyzer.py --days 7
    beads-analyzer.py --force
    beads-analyzer.py --days 30 --output ~/sharing/analysis/beads/monthly
"""

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# Constants
ANALYSIS_DIR = Path.home() / "sharing" / "analysis" / "beads"
BEADS_DIR = Path.home() / "beads"


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


class BeadsFetcher:
    """Fetches and parses Beads task data."""

    def __init__(self, beads_dir: Path = BEADS_DIR):
        self.beads_dir = beads_dir

    def fetch_tasks(self, days: int = 7) -> list[BeadsTask]:
        """Fetch all tasks from the last N days."""
        try:
            result = subprocess.run(
                ["bd", "--allow-stale", "list", "--json"],
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

                # Filter by date range
                if created_at and created_at < cutoff:
                    # Include if updated within range
                    if not updated_at or updated_at < cutoff:
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
                # Check for abandoned tasks (no update in 24h)
                if (now - task.updated_at).total_seconds() > 24 * 3600:
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
                    metrics.tasks_by_source["slack"] = (
                        metrics.tasks_by_source.get("slack", 0) + 1
                    )
                    source_found = True
                    break
                elif label.startswith("pr-") or "github-pr" in label:
                    metrics.pr_linked_tasks += 1
                    metrics.tasks_by_source["github"] = (
                        metrics.tasks_by_source.get("github", 0) + 1
                    )
                    source_found = True
                    break
                elif "jira" in label:
                    metrics.jira_linked_tasks += 1
                    metrics.tasks_by_source["jira"] = (
                        metrics.tasks_by_source.get("jira", 0) + 1
                    )
                    source_found = True
                    break

            if not source_found:
                metrics.tasks_by_source["unknown"] = (
                    metrics.tasks_by_source.get("unknown", 0) + 1
                )

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
            metrics.proper_lifecycle_rate = (
                properly_managed / metrics.tasks_closed
            ) * 100

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
        if any(
            repo in title_lower
            for repo in ["james-in-a-box", "webapp", "services", "jib"]
        ):
            return True

        # Check for JIRA tickets
        if any(
            pattern in title_lower for pattern in ["jira-", "project-", "issue-"]
        ):
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
        if len(title) > 20 and title_lower not in generic_titles:
            return True

        return False

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

    def identify_issues(
        self, tasks: list[BeadsTask], metrics: BeadsMetrics
    ) -> list[BeadsIssue]:
        """Identify issues with Beads usage."""
        issues = []

        # High: Abandoned tasks
        if metrics.tasks_abandoned > 0:
            abandoned = [
                t.id
                for t in tasks
                if t.status == "in_progress"
                and (datetime.now() - t.updated_at).total_seconds() > 24 * 3600
            ]
            issues.append(
                BeadsIssue(
                    severity="high",
                    category="Task Abandonment",
                    description=f"{metrics.tasks_abandoned} tasks in_progress for >24h without updates",
                    task_ids=abandoned[:10],  # Limit to first 10
                    recommendation="Review and either close or update these tasks. If blocked, mark as blocked with notes.",
                )
            )

        # High: Low notes coverage
        notes_rate = (
            (metrics.tasks_with_notes / metrics.total_tasks * 100)
            if metrics.total_tasks
            else 0
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
            (metrics.tasks_with_labels / metrics.total_tasks * 100)
            if metrics.total_tasks
            else 0
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
    ) -> str:
        """Generate markdown report."""
        now = datetime.now()

        # Calculate rates
        notes_rate = (
            (metrics.tasks_with_notes / metrics.total_tasks * 100)
            if metrics.total_tasks
            else 0
        )
        label_rate = (
            (metrics.tasks_with_labels / metrics.total_tasks * 100)
            if metrics.total_tasks
            else 0
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
        for source, count in sorted(
            metrics.tasks_by_source.items(), key=lambda x: -x[1]
        ):
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
                severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}[
                    issue.severity
                ]
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

        report += f"""
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

        report += f"""
---

*Report generated from {metrics.total_tasks} tasks over {self.days} days*
*Saved to: ~/sharing/analysis/beads/*
"""
        return report

    def _calculate_health_score(
        self, metrics: BeadsMetrics, issues: list[BeadsIssue]
    ) -> int:
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
        notes_rate = (
            metrics.tasks_with_notes / metrics.total_tasks if metrics.total_tasks else 0
        )
        if notes_rate < 0.8:
            recommendations.append(
                "Add progress notes when updating tasks to maintain context across sessions"
            )

        label_rate = (
            metrics.tasks_with_labels / metrics.total_tasks if metrics.total_tasks else 0
        )
        if label_rate < 0.9:
            recommendations.append(
                "Add labels to all tasks: source (slack/github), type (feature/bug), repo name"
            )

        searchable_rate = (
            metrics.tasks_with_searchable_title / metrics.total_tasks
            if metrics.total_tasks
            else 0
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

    def run_analysis(self) -> str | None:
        """Run full analysis and generate report."""
        print(f"Analyzing Beads integration from last {self.days} days...")

        # Fetch tasks
        print("Fetching Beads tasks...")
        tasks = self.fetcher.fetch_tasks(self.days)
        print(f"  Found {len(tasks)} tasks")

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

        # Generate report
        print("Generating report...")
        report = self.generate_report(tasks, metrics, issues)

        # Ensure output directory exists
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_file = self.analysis_dir / f"beads-analysis-{timestamp}.md"
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

        # Send notification if there are high-severity issues
        high_issues = [i for i in issues if i.severity == "high"]
        if high_issues or metrics.tasks_abandoned > 0:
            self._send_notification(metrics, issues, report_file, report)

        return report

    def _send_notification(
        self,
        metrics: BeadsMetrics,
        issues: list[BeadsIssue],
        report_file: Path,
        full_report: str,
    ):
        """Send notification about analysis results."""
        notification_dir = Path.home() / "sharing" / "notifications"
        notification_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_id = f"{timestamp}-beads-analysis"

        # Determine priority
        high_count = len([i for i in issues if i.severity == "high"])
        if high_count >= 2 or metrics.tasks_abandoned >= 3:
            priority = "HIGH"
        elif high_count >= 1 or metrics.tasks_abandoned >= 1:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        health_score = self._calculate_health_score(metrics, issues)

        summary_file = notification_dir / f"{task_id}.md"
        summary = f"""# 📊 Beads Integration Health Report

**Priority**: {priority}
**Health Score**: {health_score}/100 {self._get_health_emoji(health_score)}

**Quick Stats:**
- 📝 Total Tasks: {metrics.total_tasks}
- ✅ Closed: {metrics.tasks_closed}
- ⏳ In Progress: {metrics.tasks_in_progress}
- ⚠️ Abandoned: {metrics.tasks_abandoned}

**Issues Found:**
- 🔴 High: {len([i for i in issues if i.severity == "high"])}
- 🟡 Medium: {len([i for i in issues if i.severity == "medium"])}
- 🟢 Low: {len([i for i in issues if i.severity == "low"])}

📄 Full report in thread below
"""

        with open(summary_file, "w") as f:
            f.write(summary)

        print(f"  Summary notification: {summary_file}")

        # Create detailed report (thread reply)
        detail_file = notification_dir / f"RESPONSE-{task_id}.md"
        with open(detail_file, "w") as f:
            f.write(full_report)

        print(f"  Detailed report (thread): {detail_file}")


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
        "--output", type=Path, help="Output directory (default: ~/sharing/analysis/beads)"
    )
    parser.add_argument("--print", action="store_true", help="Print report to stdout")
    parser.add_argument(
        "--force", action="store_true", help="Force analysis even if run recently"
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

    report = analyzer.run_analysis()

    if args.print and report:
        print("\n" + "=" * 80)
        print(report)
        print("=" * 80)


if __name__ == "__main__":
    main()
