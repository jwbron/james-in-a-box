#!/usr/bin/env python3
"""
Beads Analyzer Processor - Container-side beads health analysis.

This script runs INSIDE the jib container, ensuring all file operations
happen in an isolated worktree rather than tainting the host's main worktree.

Invoked via `jib --exec` from the host-side beads-analyzer service.

Usage:
    jib --exec python3 beads-analyzer-processor.py --task run_analysis --context <json>

Context expected:
    - days: int (number of days to analyze, default 7)
    - force: bool (force run even if recently analyzed)
    - skip_claude: bool (skip AI analysis for faster results)

Output:
    JSON to stdout with:
    {
        "success": true/false,
        "result": {
            "health_score": int,
            "total_tasks": int,
            "pr_url": str (if PR created),
            "report_path": str
        },
        "error": null or "error message"
    }
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


# Constants
BEADS_DIR = Path.home() / "beads"
REPO_ROOT = Path.home() / "khan" / "james-in-a-box"
ANALYSIS_DIR = REPO_ROOT / "docs" / "analysis" / "beads"
ABANDONED_THRESHOLD_HOURS = 24


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

    total_tasks: int = 0
    tasks_created: int = 0
    tasks_closed: int = 0
    tasks_abandoned: int = 0
    tasks_in_progress: int = 0
    tasks_blocked: int = 0
    tasks_with_notes: int = 0
    tasks_with_description: int = 0
    tasks_with_labels: int = 0
    tasks_with_searchable_title: int = 0
    avg_time_to_close_hours: float = 0
    avg_notes_per_task: float = 0
    proper_lifecycle_rate: float = 0
    slack_linked_tasks: int = 0
    pr_linked_tasks: int = 0
    jira_linked_tasks: int = 0
    duplicate_tasks: int = 0
    orphan_tasks: int = 0
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
    """Claude-generated analysis of beads usage."""

    executive_summary: str = ""
    smart_issues: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    trend_analysis: str = ""
    task_quality_scores: dict[str, dict] = field(default_factory=dict)
    patterns_detected: list[str] = field(default_factory=list)
    success: bool = False
    error: str | None = None


def output_result(success: bool, result: dict | str | None = None, error: str | None = None):
    """Output a JSON result and exit."""
    output = {
        "success": success,
        "result": result,
        "error": error,
    }
    print(json.dumps(output))
    return 0 if success else 1


def parse_datetime(dt_str: str | None) -> datetime | None:
    """Parse ISO datetime string."""
    if not dt_str:
        return None
    try:
        dt_str = dt_str.replace("Z", "+00:00")
        if "." in dt_str:
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


def fetch_tasks(days: int = 7) -> list[BeadsTask]:
    """Fetch all tasks from the last N days."""
    try:
        result = subprocess.run(
            ["bd", "--allow-stale", "list", "--json"],
            check=False,
            capture_output=True,
            text=True,
            cwd=BEADS_DIR,
            timeout=30,
        )

        if result.returncode != 0:
            print(f"WARNING: bd list failed: {result.stderr}", file=sys.stderr)
            return []

        tasks_json = json.loads(result.stdout)
        cutoff = datetime.now() - timedelta(days=days)
        tasks = []

        for task_data in tasks_json:
            created_at = parse_datetime(task_data.get("created_at"))
            updated_at = parse_datetime(task_data.get("updated_at"))
            closed_at = parse_datetime(task_data.get("closed_at"))

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


def is_searchable_title(title: str) -> bool:
    """Check if a title contains searchable identifiers."""
    title_lower = title.lower()

    if "pr #" in title_lower or "pr-" in title_lower or "#" in title_lower:
        return True

    if any(repo in title_lower for repo in ["james-in-a-box", "webapp", "services", "jib"]):
        return True

    if any(pattern in title_lower for pattern in ["jira-", "project-", "issue-"]):
        return True

    good_prefixes = ["fix:", "feat:", "refactor:", "bug:", "feature:"]
    if any(title_lower.startswith(prefix) for prefix in good_prefixes):
        return True

    generic_titles = [
        "fix bug",
        "update code",
        "wip",
        "work in progress",
        "todo",
        "task",
    ]
    return bool(len(title) > 20 and title_lower not in generic_titles)


def count_duplicates(tasks: list[BeadsTask]) -> int:
    """Count tasks with very similar titles."""
    titles = [t.title.lower().strip() for t in tasks]
    duplicates = 0
    seen = set()
    for title in titles:
        normalized = " ".join(title.split())
        if normalized in seen:
            duplicates += 1
        seen.add(normalized)
    return duplicates


def calculate_metrics(tasks: list[BeadsTask], days: int) -> BeadsMetrics:
    """Calculate comprehensive metrics from tasks."""
    metrics = BeadsMetrics()
    metrics.total_tasks = len(tasks)

    if not tasks:
        return metrics

    now = datetime.now()
    cutoff = now - timedelta(days=days)
    total_close_time = 0
    close_count = 0
    total_notes_length = 0

    for task in tasks:
        status = task.status
        metrics.tasks_by_status[status] = metrics.tasks_by_status.get(status, 0) + 1

        if status == "in_progress":
            metrics.tasks_in_progress += 1
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

        if task.created_at >= cutoff:
            metrics.tasks_created += 1

        if task.notes:
            metrics.tasks_with_notes += 1
            total_notes_length += len(task.notes)

        if task.description:
            metrics.tasks_with_description += 1

        if task.labels:
            metrics.tasks_with_labels += 1

        if is_searchable_title(task.title):
            metrics.tasks_with_searchable_title += 1

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

        if not task.labels and not task.description:
            metrics.orphan_tasks += 1

    if close_count > 0:
        metrics.avg_time_to_close_hours = total_close_time / close_count

    if metrics.tasks_with_notes > 0:
        metrics.avg_notes_per_task = total_notes_length / metrics.tasks_with_notes

    properly_managed = sum(1 for t in tasks if t.status == "closed" and t.notes)
    if metrics.tasks_closed > 0:
        metrics.proper_lifecycle_rate = (properly_managed / metrics.tasks_closed) * 100

    metrics.duplicate_tasks = count_duplicates(tasks)

    return metrics


def identify_issues(tasks: list[BeadsTask], metrics: BeadsMetrics) -> list[BeadsIssue]:
    """Identify issues with Beads usage."""
    issues = []

    if metrics.tasks_abandoned > 0:
        abandoned = [
            t.id
            for t in tasks
            if t.status == "in_progress"
            and (datetime.now() - t.updated_at).total_seconds() > ABANDONED_THRESHOLD_HOURS * 3600
        ]
        issues.append(
            BeadsIssue(
                severity="high",
                category="Task Abandonment",
                description=f"{metrics.tasks_abandoned} tasks in_progress for >{ABANDONED_THRESHOLD_HOURS}h without updates",
                task_ids=abandoned[:10],
                recommendation="Review and either close or update these tasks. If blocked, mark as blocked with notes.",
            )
        )

    notes_rate = (metrics.tasks_with_notes / metrics.total_tasks * 100) if metrics.total_tasks else 0
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

    searchable_rate = (
        (metrics.tasks_with_searchable_title / metrics.total_tasks * 100) if metrics.total_tasks else 0
    )
    if searchable_rate < 60 and metrics.total_tasks >= 5:
        bad_titles = [t.id for t in tasks if not is_searchable_title(t.title)]
        issues.append(
            BeadsIssue(
                severity="medium",
                category="Unsearchable Titles",
                description=f"Only {searchable_rate:.0f}% of tasks have searchable titles",
                task_ids=bad_titles[:10],
                recommendation="Include PR numbers, repo names, or feature keywords in task titles.",
            )
        )

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


def calculate_health_score(metrics: BeadsMetrics, issues: list[BeadsIssue]) -> int:
    """Calculate overall health score (0-100)."""
    if metrics.total_tasks == 0:
        return 100

    score = 100

    for issue in issues:
        if issue.severity == "high":
            score -= 15
        elif issue.severity == "medium":
            score -= 8
        else:
            score -= 3

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


def get_health_emoji(score: int) -> str:
    """Get emoji for health score."""
    if score >= 90:
        return "star"
    elif score >= 70:
        return "check"
    elif score >= 50:
        return "warning"
    else:
        return "alert"


def generate_recommendations(metrics: BeadsMetrics, issues: list[BeadsIssue]) -> list[str]:
    """Generate actionable recommendations."""
    recommendations = []

    high_issues = [i for i in issues if i.severity == "high"]
    if high_issues:
        recommendations.append(f"**Priority**: Address {len(high_issues)} high-severity issues first")

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


def run_claude_analysis(
    tasks: list[BeadsTask],
    metrics: BeadsMetrics,
    issues: list[BeadsIssue],
    days: int,
) -> ClaudeAnalysis:
    """Run intelligent analysis using Claude.

    Uses the shared claude module available inside the container.
    """
    print("Running Claude-powered analysis...", file=sys.stderr)

    # Import claude module
    sys.path.insert(0, str(REPO_ROOT / "jib-container" / "shared"))
    from claude import run_claude

    task_summaries = []
    for task in tasks[:50]:
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
    previous_report = get_previous_report()

    issue_summaries = [
        {
            "severity": i.severity,
            "category": i.category,
            "description": i.description,
            "task_count": len(i.task_ids),
        }
        for i in issues
    ]

    prompt = f"""You are analyzing Beads task tracking usage for an AI software engineering agent.
Beads is a persistent task memory system that helps track work across container sessions.

## Current Metrics (Last {days} days)

- Total Tasks: {metrics.total_tasks}
- Created: {metrics.tasks_created}
- Closed: {metrics.tasks_closed}
- In Progress: {metrics.tasks_in_progress}
- Abandoned (>24h no update): {metrics.tasks_abandoned}
- Tasks with Notes: {metrics.tasks_with_notes} ({100 * metrics.tasks_with_notes // max(1, metrics.total_tasks)}%)
- Tasks with Labels: {metrics.tasks_with_labels} ({100 * metrics.tasks_with_labels // max(1, metrics.total_tasks)}%)
- Searchable Titles: {metrics.tasks_with_searchable_title} ({100 * metrics.tasks_with_searchable_title // max(1, metrics.total_tasks)}%)
- Avg Time to Close: {metrics.avg_time_to_close_hours:.1f} hours

## Task Distribution by Status
{json.dumps(metrics.tasks_by_status, indent=2)}

## Task Distribution by Source
{json.dumps(metrics.tasks_by_source, indent=2)}

## Rule-Based Issues Already Identified
{json.dumps(issue_summaries, indent=2)}

## Sample Tasks (most recent {len(task_summaries)})
{json.dumps(task_summaries, indent=2)}

{f'''## Previous Report Metrics (for trend comparison)
{json.dumps(previous_report, indent=2)}
''' if previous_report else "## Previous Report: None available (first report)"}

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

    analysis = ClaudeAnalysis()

    try:
        result = run_claude(
            prompt=prompt,
            timeout=120,
            cwd=REPO_ROOT,
            stream=False,
        )

        if not result.success:
            analysis.error = result.error or "Claude analysis failed"
            print(f"  Claude analysis failed: {analysis.error}", file=sys.stderr)
            return analysis

        claude_output = result.stdout.strip()

        # Extract JSON from response (may be wrapped in markdown)
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

        print("  Claude analysis complete", file=sys.stderr)
        print(f"    - {len(analysis.smart_issues)} smart issues detected", file=sys.stderr)
        print(f"    - {len(analysis.recommendations)} recommendations", file=sys.stderr)
        print(f"    - {len(analysis.patterns_detected)} patterns detected", file=sys.stderr)

    except json.JSONDecodeError as e:
        analysis.error = f"Failed to parse Claude response: {e}"
        print(f"  {analysis.error}", file=sys.stderr)
    except Exception as e:
        analysis.error = f"Error processing Claude response: {e}"
        print(f"  {analysis.error}", file=sys.stderr)

    return analysis


def get_previous_report() -> dict | None:
    """Load the most recent previous metrics report for trend comparison."""
    try:
        metrics_files = sorted(
            ANALYSIS_DIR.glob("beads-metrics-*.json"),
            key=lambda p: p.stem,
            reverse=True,
        )
        for metrics_file in metrics_files[1:2]:
            with open(metrics_file) as f:
                return json.load(f)
    except Exception:
        pass
    return None


def format_claude_analysis_section(analysis: ClaudeAnalysis) -> str:
    """Format Claude analysis as markdown for the report."""
    if not analysis.success:
        return f"""
## AI-Powered Analysis

*Analysis unavailable: {analysis.error}*
"""

    sections = []

    if analysis.executive_summary:
        sections.append(f"""
## Executive Summary

{analysis.executive_summary}
""")

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

    if analysis.trend_analysis:
        sections.append(f"""
## Trend Analysis

{analysis.trend_analysis}
""")

    if analysis.patterns_detected:
        patterns_md = "\n".join([f"- {p}" for p in analysis.patterns_detected])
        sections.append(f"""
## Workflow Patterns Detected

{patterns_md}
""")

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


def generate_report(
    tasks: list[BeadsTask],
    metrics: BeadsMetrics,
    issues: list[BeadsIssue],
    days: int,
    claude_analysis: ClaudeAnalysis | None = None,
) -> str:
    """Generate markdown report."""
    now = datetime.now()

    notes_rate = (metrics.tasks_with_notes / metrics.total_tasks * 100) if metrics.total_tasks else 0
    label_rate = (metrics.tasks_with_labels / metrics.total_tasks * 100) if metrics.total_tasks else 0
    searchable_rate = (
        (metrics.tasks_with_searchable_title / metrics.total_tasks * 100) if metrics.total_tasks else 0
    )

    health_score = calculate_health_score(metrics, issues)
    emoji_name = get_health_emoji(health_score)
    emoji_map = {"star": "star", "check": "white_check_mark", "warning": "warning", "alert": "rotating_light"}

    report = f"""# Beads Integration Health Report
Generated: {now.strftime("%Y-%m-%d %H:%M:%S")}
Period: Last {days} days

## Health Score: {health_score}/100 :{emoji_map.get(emoji_name, 'question')}:

## Executive Summary

| Metric | Value | Status |
|--------|-------|--------|
| Total Tasks | {metrics.total_tasks} | - |
| Tasks Created | {metrics.tasks_created} | - |
| Tasks Closed | {metrics.tasks_closed} | {"pass" if metrics.tasks_closed > 0 else "warn"} |
| Tasks In Progress | {metrics.tasks_in_progress} | - |
| Abandoned Tasks | {metrics.tasks_abandoned} | {"pass" if metrics.tasks_abandoned == 0 else "warn"} |
| Notes Coverage | {notes_rate:.0f}% | {"pass" if notes_rate >= 80 else "warn"} |
| Label Coverage | {label_rate:.0f}% | {"pass" if label_rate >= 90 else "warn"} |
| Searchable Titles | {searchable_rate:.0f}% | {"pass" if searchable_rate >= 60 else "warn"} |

## Task Distribution

### By Status
```
"""
    max_count = max(metrics.tasks_by_status.values()) if metrics.tasks_by_status else 1
    for status, count in sorted(metrics.tasks_by_status.items()):
        bar_len = int((count / max_count) * 20)
        bar = "#" * bar_len
        report += f"{status:15} {bar:20} {count}\n"

    report += """```

### By Source
```
"""
    max_count = max(metrics.tasks_by_source.values()) if metrics.tasks_by_source else 1
    for source, count in sorted(metrics.tasks_by_source.items(), key=lambda x: -x[1]):
        bar_len = int((count / max_count) * 20)
        bar = "#" * bar_len
        report += f"{source:15} {bar:20} {count}\n"

    report += f"""```

## Quality Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Tasks with Notes | {metrics.tasks_with_notes}/{metrics.total_tasks} ({notes_rate:.0f}%) | >80% | {"pass" if notes_rate >= 80 else "warn"} |
| Tasks with Labels | {metrics.tasks_with_labels}/{metrics.total_tasks} ({label_rate:.0f}%) | >90% | {"pass" if label_rate >= 90 else "warn"} |
| Searchable Titles | {metrics.tasks_with_searchable_title}/{metrics.total_tasks} ({searchable_rate:.0f}%) | >60% | {"pass" if searchable_rate >= 60 else "warn"} |
| Proper Lifecycle | {metrics.proper_lifecycle_rate:.0f}% | >70% | {"pass" if metrics.proper_lifecycle_rate >= 70 else "warn"} |

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
            severity_icon = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}[issue.severity]
            report += f"""### [{severity_icon}] {issue.category}

**Issue**: {issue.description}

**Recommendation**: {issue.recommendation}

"""
            if issue.task_ids:
                report += "**Affected Tasks**: " + ", ".join(f"`{tid}`" for tid in issue.task_ids[:5])
                if len(issue.task_ids) > 5:
                    report += f" (+{len(issue.task_ids) - 5} more)"
                report += "\n\n"
    else:
        report += "*No issues identified - great work!*\n\n"

    report += """## Recommendations

"""
    recommendations = generate_recommendations(metrics, issues)
    for i, rec in enumerate(recommendations, 1):
        report += f"{i}. {rec}\n"

    report += """

## Recent Tasks

| ID | Title | Status | Source | Updated |
|----|-------|--------|--------|---------|
"""
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

    if claude_analysis:
        report += format_claude_analysis_section(claude_analysis)

    report += f"""

---

*Report generated from {metrics.total_tasks} tasks over {days} days*
*Generated in jib container (isolated worktree)*
"""
    return report


def cleanup_old_reports(max_reports: int = 5) -> list[Path]:
    """Keep only the last N reports, return files to be deleted."""
    report_files = sorted(
        ANALYSIS_DIR.glob("beads-health-*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    metrics_files = sorted(
        ANALYSIS_DIR.glob("beads-metrics-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    to_delete = []

    if len(report_files) > max_reports:
        to_delete.extend(report_files[max_reports:])
    if len(metrics_files) > max_reports:
        to_delete.extend(metrics_files[max_reports:])

    return to_delete


def check_last_run() -> datetime | None:
    """Check when the analyzer was last run."""
    try:
        reports = list(ANALYSIS_DIR.glob("beads-health-*.md"))
        if not reports:
            return None

        reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        most_recent = reports[0]
        return datetime.fromtimestamp(most_recent.stat().st_mtime)
    except Exception:
        return None


def should_run_analysis(force: bool = False) -> bool:
    """Determine if analysis should run based on weekly schedule."""
    if force:
        print("Force flag set - running analysis", file=sys.stderr)
        return True

    last_run = check_last_run()

    if last_run is None:
        print("No previous analysis found - running analysis", file=sys.stderr)
        return True

    days_since_last_run = (datetime.now() - last_run).days

    if days_since_last_run >= 7:
        print(f"Last analysis was {days_since_last_run} days ago - running analysis", file=sys.stderr)
        return True
    else:
        print(f"Last analysis was {days_since_last_run} days ago (< 7 days) - skipping", file=sys.stderr)
        return False


def handle_run_analysis(context: dict) -> int:
    """Run the beads health analysis.

    Context:
        - days: int (default 7)
        - force: bool (default False)
        - skip_claude: bool (default False)
    """
    days = context.get("days", 7)
    force = context.get("force", False)
    skip_claude = context.get("skip_claude", False)

    # Check if we should run
    if not should_run_analysis(force):
        return output_result(
            success=True,
            result={
                "skipped": True,
                "reason": "Analysis run recently (within 7 days)",
            },
        )

    print(f"Analyzing Beads integration from last {days} days...", file=sys.stderr)

    # Fetch tasks
    print("Fetching Beads tasks...", file=sys.stderr)
    tasks = fetch_tasks(days)
    print(f"  Found {len(tasks)} tasks", file=sys.stderr)

    claude_analysis = None

    if not tasks:
        print("WARNING: No tasks found for analysis", file=sys.stderr)
        metrics = BeadsMetrics()
        issues = []
    else:
        print("Calculating metrics...", file=sys.stderr)
        metrics = calculate_metrics(tasks, days)

        print("Identifying issues...", file=sys.stderr)
        issues = identify_issues(tasks, metrics)

        if not skip_claude:
            claude_analysis = run_claude_analysis(tasks, metrics, issues, days)

    print("Generating report...", file=sys.stderr)
    report = generate_report(tasks, metrics, issues, days, claude_analysis)

    # Ensure output directory exists
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    # Save report
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_file = ANALYSIS_DIR / f"beads-health-{timestamp}.md"
    report_file.write_text(report)

    # Save metrics as JSON
    metrics_file = ANALYSIS_DIR / f"beads-metrics-{timestamp}.json"
    health_score = calculate_health_score(metrics, issues)
    metrics_file.write_text(
        json.dumps(
            {
                "timestamp": timestamp,
                "days_analyzed": days,
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
                "health_score": health_score,
            },
            indent=2,
        )
    )

    # Update symlinks
    latest_report = ANALYSIS_DIR / "latest-report.md"
    latest_metrics = ANALYSIS_DIR / "latest-metrics.json"

    if latest_report.exists() or latest_report.is_symlink():
        latest_report.unlink()
    if latest_metrics.exists() or latest_metrics.is_symlink():
        latest_metrics.unlink()

    os.symlink(report_file.name, latest_report)
    os.symlink(metrics_file.name, latest_metrics)

    print(f"\nAnalysis complete!", file=sys.stderr)
    print(f"  Report: {report_file}", file=sys.stderr)
    print(f"  Metrics: {metrics_file}", file=sys.stderr)

    # Cleanup old reports
    to_delete = cleanup_old_reports(max_reports=5)
    files_to_delete = [str(p.relative_to(REPO_ROOT)) for p in to_delete]

    # Create PR with the reports
    print("\nCreating PR with reports...", file=sys.stderr)
    pr_result = create_pr_with_reports(
        metrics, issues, report_file, metrics_file, timestamp, files_to_delete
    )

    return output_result(
        success=True,
        result={
            "health_score": health_score,
            "total_tasks": metrics.total_tasks,
            "tasks_created": metrics.tasks_created,
            "tasks_closed": metrics.tasks_closed,
            "tasks_abandoned": metrics.tasks_abandoned,
            "issues_high": len([i for i in issues if i.severity == "high"]),
            "issues_medium": len([i for i in issues if i.severity == "medium"]),
            "issues_low": len([i for i in issues if i.severity == "low"]),
            "report_path": str(report_file),
            "metrics_path": str(metrics_file),
            "pr_url": pr_result.get("pr_url") if pr_result else None,
            "pr_error": pr_result.get("error") if pr_result else None,
        },
    )


def create_pr_with_reports(
    metrics: BeadsMetrics,
    issues: list[BeadsIssue],
    report_file: Path,
    metrics_file: Path,
    timestamp: str,
    files_to_delete: list[str],
) -> dict:
    """Create a PR with the health reports.

    Since we're running in a container with an isolated worktree, we can safely
    create branches and commit without affecting the host's main worktree.
    """
    branch_name = f"beads-health-report-{timestamp}"
    health_score = calculate_health_score(metrics, issues)

    try:
        # Fetch origin/main
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        # Create branch from origin/main
        subprocess.run(
            ["git", "checkout", "-b", branch_name, "origin/main"],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        # Delete old files
        for file_rel_path in files_to_delete:
            file_path = REPO_ROOT / file_rel_path
            if file_path.exists():
                file_path.unlink()
                subprocess.run(
                    ["git", "add", file_rel_path],
                    check=True,
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                )

        # Stage the new report and metrics files
        subprocess.run(
            ["git", "add", str(report_file.relative_to(REPO_ROOT))],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "add", str(metrics_file.relative_to(REPO_ROOT))],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        # Stage symlinks
        subprocess.run(
            ["git", "add", "docs/analysis/beads/latest-report.md"],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "add", "docs/analysis/beads/latest-metrics.json"],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        # Commit
        commit_message = f"""chore: Add Beads health report {timestamp}

Health Score: {health_score}/100
- Total Tasks: {metrics.total_tasks}
- Closed: {metrics.tasks_closed}
- Abandoned: {metrics.tasks_abandoned}

High-severity issues: {len([i for i in issues if i.severity == "high"])}
"""
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        # Push
        subprocess.run(
            ["git", "push", "origin", branch_name],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        # Create PR
        emoji_name = get_health_emoji(health_score)
        emoji_map = {"star": ":star:", "check": ":white_check_mark:", "warning": ":warning:", "alert": ":rotating_light:"}

        pr_body = f"""## Beads Integration Health Report

**Health Score**: {health_score}/100 {emoji_map.get(emoji_name, '')}

### Quick Stats
- Total Tasks: {metrics.total_tasks}
- Closed: {metrics.tasks_closed}
- In Progress: {metrics.tasks_in_progress}
- Abandoned: {metrics.tasks_abandoned}

### Issues Summary
- HIGH: {len([i for i in issues if i.severity == "high"])}
- MEDIUM: {len([i for i in issues if i.severity == "medium"])}
- LOW: {len([i for i in issues if i.severity == "low"])}

### Files in this PR
- `docs/analysis/beads/beads-health-{timestamp}.md` - Full health report
- `docs/analysis/beads/beads-metrics-{timestamp}.json` - Machine-readable metrics
- Symlinks updated to point to latest reports
{f"- Removed {len(files_to_delete)} old report(s) to maintain max 5 reports" if files_to_delete else ""}

See the full report for detailed analysis.

---
*Generated by beads-analyzer running in jib container*
"""

        result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                f"Beads Health Report - {timestamp}",
                "--body",
                pr_body,
                "--base",
                "main",
                "--head",
                branch_name,
            ],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        pr_url = result.stdout.strip()
        print(f"Created PR: {pr_url}", file=sys.stderr)
        return {"pr_url": pr_url, "branch": branch_name}

    except subprocess.CalledProcessError as e:
        error = f"Git/PR operation failed: {e.stderr or e.stdout or str(e)}"
        print(f"ERROR: {error}", file=sys.stderr)
        return {"error": error}
    except Exception as e:
        error = f"Error creating PR: {e}"
        print(f"ERROR: {error}", file=sys.stderr)
        return {"error": error}


def main():
    parser = argparse.ArgumentParser(
        description="Beads analyzer processor for jib container",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--task",
        type=str,
        required=True,
        choices=["run_analysis"],
        help="Type of task to perform",
    )
    parser.add_argument(
        "--context",
        type=str,
        required=True,
        help="JSON context for the task",
    )

    args = parser.parse_args()

    try:
        context = json.loads(args.context)
    except json.JSONDecodeError as e:
        return output_result(False, error=f"Invalid JSON context: {e}")

    handlers = {
        "run_analysis": handle_run_analysis,
    }

    handler = handlers.get(args.task)
    if handler:
        return handler(context)
    else:
        return output_result(False, error=f"Unknown task type: {args.task}")


if __name__ == "__main__":
    sys.exit(main())
