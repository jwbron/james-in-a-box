#!/usr/bin/env python3
"""
Conversation Analysis Job for jib (James-in-a-Box)

Analyzes Slack threads and GitHub PRs where jib has contributed to generate
insights about communication quality, response patterns, and areas for improvement.

Data Sources:
- Slack: Threads in configured channel where jib has participated
- GitHub: PRs and comments from jib

Reports: ~/sharing/analysis/

Runs on host (not in container) via systemd timer:
- Weekly (checks if last run was within 7 days)
- Can force run with --force flag

Usage:
    conversation-analyzer.py [--days N] [--output DIR] [--force]

Example:
    conversation-analyzer.py --days 7
    conversation-analyzer.py --force
    conversation-analyzer.py --days 30 --output ~/sharing/analysis/monthly
"""

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


try:
    import requests
except ImportError:
    print("Error: requests module not found.", file=sys.stderr)
    print("Run 'uv sync' from host-services/ or run setup.sh", file=sys.stderr)
    sys.exit(1)


# Constants
ANALYSIS_DIR = Path.home() / "sharing" / "analysis"
PROMPTS_DIR = Path.home() / "sharing" / "prompts"
JIB_CONFIG_DIR = Path.home() / ".config" / "jib"


@dataclass
class SlackThread:
    """Represents a Slack thread where jib participated."""

    thread_ts: str
    channel: str
    start_time: datetime
    messages: list[dict[str, Any]]
    jib_message_count: int
    human_message_count: int
    total_messages: int
    duration_seconds: float
    topic: str | None = None
    outcome: str | None = None  # 'resolved', 'pending', 'escalated'


@dataclass
class GitHubPR:
    """Represents a GitHub PR where jib contributed."""

    number: int
    repo: str
    title: str
    state: str  # 'open', 'closed', 'merged'
    created_at: datetime
    closed_at: datetime | None
    jib_commits: int
    jib_comments: int
    review_comments: int
    human_comments: int
    iterations: int  # Number of review cycles
    files_changed: int
    lines_added: int
    lines_deleted: int
    url: str


class SlackThreadFetcher:
    """Fetches Slack threads where jib has participated."""

    def __init__(self, config: dict[str, Any]):
        self.slack_token = config.get("slack_token")
        self.channel = config.get("slack_channel")
        self.bot_user_id = config.get("bot_user_id")

        if not self.slack_token:
            raise ValueError("SLACK_TOKEN not configured")
        if not self.channel:
            raise ValueError("SLACK_CHANNEL not configured")

    def _make_request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """Make a request to Slack API."""
        response = requests.get(
            f"https://slack.com/api/{endpoint}",
            headers={"Authorization": f"Bearer {self.slack_token}"},
            params=params,
            timeout=30,
        )
        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(f"Slack API error: {result.get('error', 'unknown')}")
        return result

    def _get_bot_user_id(self) -> str:
        """Get the bot's user ID."""
        if self.bot_user_id:
            return self.bot_user_id

        result = self._make_request("auth.test", {})
        return result.get("user_id", "")

    def _get_user_name(self, user_id: str, user_cache: dict[str, str]) -> str:
        """Get user display name, with caching."""
        if user_id in user_cache:
            return user_cache[user_id]

        try:
            result = self._make_request("users.info", {"user": user_id})
            name = result.get("user", {}).get("real_name", user_id)
            user_cache[user_id] = name
            return name
        except Exception:
            user_cache[user_id] = user_id
            return user_id

    def _is_jib_message(self, message: dict[str, Any], bot_user_id: str) -> bool:
        """Check if a message was sent by jib."""
        # Check user ID
        if message.get("user") == bot_user_id:
            return True
        # Check bot_id (for bot messages)
        if message.get("bot_id"):
            return True
        # Check for jib signature in text
        text = message.get("text", "")
        return "Authored by jib" in text or "Generated with Claude" in text

    def fetch_threads(self, days: int = 7) -> list[SlackThread]:
        """Fetch all threads from the channel where jib participated in the last N days."""
        bot_user_id = self._get_bot_user_id()
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_ts = str(cutoff.timestamp())

        threads = []
        user_cache: dict[str, str] = {}

        # Get channel history
        cursor = None
        while True:
            params = {
                "channel": self.channel,
                "oldest": cutoff_ts,
                "limit": 200,
            }
            if cursor:
                params["cursor"] = cursor

            result = self._make_request("conversations.history", params)
            messages = result.get("messages", [])

            for msg in messages:
                # Check if this message has a thread
                thread_ts = msg.get("thread_ts") or msg.get("ts")
                reply_count = msg.get("reply_count", 0)

                # Skip messages without replies (not a thread)
                if reply_count == 0:
                    continue

                # Fetch thread replies
                thread_result = self._make_request(
                    "conversations.replies",
                    {
                        "channel": self.channel,
                        "ts": thread_ts,
                        "limit": 1000,
                    },
                )
                thread_messages = thread_result.get("messages", [])

                # Check if jib participated in this thread
                jib_messages = [m for m in thread_messages if self._is_jib_message(m, bot_user_id)]
                if not jib_messages:
                    continue

                # Count messages
                jib_count = len(jib_messages)
                human_count = len(thread_messages) - jib_count

                # Calculate duration
                timestamps = [float(m.get("ts", "0")) for m in thread_messages]
                if timestamps:
                    start_ts = min(timestamps)
                    end_ts = max(timestamps)
                    duration = end_ts - start_ts
                    start_time = datetime.fromtimestamp(start_ts)
                else:
                    duration = 0
                    start_time = datetime.now()

                # Extract topic from first message
                topic = thread_messages[0].get("text", "")[:100] if thread_messages else None

                # Determine outcome based on last message content
                outcome = self._determine_outcome(thread_messages)

                # Add user names to messages
                for m in thread_messages:
                    m["user_name"] = self._get_user_name(m.get("user", "unknown"), user_cache)
                    m["is_jib"] = self._is_jib_message(m, bot_user_id)

                thread = SlackThread(
                    thread_ts=thread_ts,
                    channel=self.channel,
                    start_time=start_time,
                    messages=thread_messages,
                    jib_message_count=jib_count,
                    human_message_count=human_count,
                    total_messages=len(thread_messages),
                    duration_seconds=duration,
                    topic=topic,
                    outcome=outcome,
                )
                threads.append(thread)

            # Check for more pages
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return threads

    def _determine_outcome(self, messages: list[dict[str, Any]]) -> str:
        """Determine the outcome of a thread based on message content."""
        if not messages:
            return "unknown"

        # Look for common patterns in recent messages
        recent_texts = " ".join([m.get("text", "") for m in messages[-3:]])
        recent_lower = recent_texts.lower()

        # Check for resolution indicators
        if any(
            word in recent_lower
            for word in ["thanks", "thank you", "perfect", "done", "merged", "lgtm", "approved"]
        ):
            return "resolved"
        if any(
            word in recent_lower
            for word in ["blocked", "stuck", "help", "issue", "error", "failed"]
        ):
            return "escalated"

        return "pending"


class GitHubPRFetcher:
    """Fetches GitHub PRs where jib has contributed."""

    def __init__(self, config: dict[str, Any]):
        self.github_token = config.get("github_token")
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN not configured")

        self.headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        # Repos to search - can be configured
        self.repos = config.get("github_repos", ["jwbron/james-in-a-box"])

    def _make_request(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list:
        """Make a request to GitHub API."""
        url = f"https://api.github.com/{endpoint}"
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch_prs(self, days: int = 7) -> list[GitHubPR]:
        """Fetch PRs where jib contributed in the last N days."""
        cutoff = datetime.now() - timedelta(days=days)
        prs = []

        for repo in self.repos:
            # Search for PRs created or updated by jib
            # Using search API to find PRs involving jib
            try:
                # Get PRs where jib is the author
                search_query = f"repo:{repo} is:pr author:app/github-actions created:>{cutoff.strftime('%Y-%m-%d')}"
                result = self._make_request("search/issues", {"q": search_query, "per_page": 100})

                for item in result.get("items", []):
                    pr_data = self._get_pr_details(repo, item["number"])
                    if pr_data:
                        prs.append(pr_data)

                # Also get PRs where jib has commented
                # Get recent PRs and check for jib comments
                owner, repo_name = repo.split("/")
                recent_prs = self._make_request(
                    f"repos/{owner}/{repo_name}/pulls",
                    {"state": "all", "sort": "updated", "direction": "desc", "per_page": 50},
                )

                for pr in recent_prs:
                    updated = datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00"))
                    if updated.replace(tzinfo=None) < cutoff:
                        continue

                    # Check if this PR was already added
                    if any(p.number == pr["number"] and p.repo == repo for p in prs):
                        continue

                    pr_data = self._get_pr_details(repo, pr["number"])
                    if pr_data and (pr_data.jib_commits > 0 or pr_data.jib_comments > 0):
                        prs.append(pr_data)

            except Exception as e:
                print(f"WARNING: Failed to fetch PRs from {repo}: {e}", file=sys.stderr)
                continue

        return prs

    def _get_pr_details(self, repo: str, pr_number: int) -> GitHubPR | None:
        """Get detailed information about a specific PR."""
        try:
            owner, repo_name = repo.split("/")
            base = f"repos/{owner}/{repo_name}/pulls/{pr_number}"

            # Get PR details
            pr = self._make_request(base)

            # Get commits
            commits = self._make_request(f"{base}/commits", {"per_page": 100})
            jib_commits = sum(1 for c in commits if self._is_jib_commit(c))

            # Get review comments
            review_comments = self._make_request(f"{base}/comments", {"per_page": 100})
            jib_review_comments = sum(1 for c in review_comments if self._is_jib_comment(c))
            human_review_comments = len(review_comments) - jib_review_comments

            # Get issue comments
            issue_comments = self._make_request(
                f"repos/{owner}/{repo_name}/issues/{pr_number}/comments", {"per_page": 100}
            )
            jib_issue_comments = sum(1 for c in issue_comments if self._is_jib_comment(c))

            # Count iterations (review cycles) - simplified as number of reviews
            reviews = self._make_request(f"{base}/reviews", {"per_page": 100})
            iterations = max(
                1, len([r for r in reviews if r.get("state") in ["CHANGES_REQUESTED", "APPROVED"]])
            )

            # Parse dates
            created_at = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00")).replace(
                tzinfo=None
            )
            closed_at = None
            if pr.get("closed_at"):
                closed_at = datetime.fromisoformat(pr["closed_at"].replace("Z", "+00:00")).replace(
                    tzinfo=None
                )

            # Determine state
            state = pr["state"]
            if pr.get("merged"):
                state = "merged"

            return GitHubPR(
                number=pr_number,
                repo=repo,
                title=pr["title"],
                state=state,
                created_at=created_at,
                closed_at=closed_at,
                jib_commits=jib_commits,
                jib_comments=jib_review_comments + jib_issue_comments,
                review_comments=len(review_comments),
                human_comments=human_review_comments + len(issue_comments) - jib_issue_comments,
                iterations=iterations,
                files_changed=pr.get("changed_files", 0),
                lines_added=pr.get("additions", 0),
                lines_deleted=pr.get("deletions", 0),
                url=pr["html_url"],
            )

        except Exception as e:
            print(f"WARNING: Failed to get PR details for {repo}#{pr_number}: {e}", file=sys.stderr)
            return None

    def _is_jib_commit(self, commit: dict[str, Any]) -> bool:
        """Check if a commit was made by jib."""
        # Check commit message for jib signature
        message = commit.get("commit", {}).get("message", "")
        if "Generated with Claude" in message or "Co-Authored-By: Claude" in message:
            return True
        # Check author
        author = commit.get("commit", {}).get("author", {}).get("name", "")
        return "jib" in author.lower() or "claude" in author.lower()

    def _is_jib_comment(self, comment: dict[str, Any]) -> bool:
        """Check if a comment was made by jib."""
        body = comment.get("body", "")
        # Check for jib signature
        if "Authored by jib" in body or "Generated with Claude" in body:
            return True
        # Check user login
        user = comment.get("user", {}).get("login", "")
        return "jib" in user.lower() or "bot" in user.lower()


class ConversationAnalyzer:
    """Analyzes jib's Slack threads and GitHub PRs."""

    def __init__(self, days: int = 7):
        self.days = days
        self.analysis_dir = ANALYSIS_DIR
        self.prompts_dir = PROMPTS_DIR

        # Create directories
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

        # Load configuration
        self.config = self._load_config()

        # Initialize fetchers (may be None if credentials not available)
        self.slack_fetcher = None
        self.github_fetcher = None

        try:
            self.slack_fetcher = SlackThreadFetcher(self.config)
        except ValueError as e:
            print(f"WARNING: Slack fetcher disabled: {e}", file=sys.stderr)

        try:
            self.github_fetcher = GitHubPRFetcher(self.config)
        except ValueError as e:
            print(f"WARNING: GitHub fetcher disabled: {e}", file=sys.stderr)

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from ~/.config/jib/."""
        config = {}

        secrets_file = JIB_CONFIG_DIR / "secrets.env"
        config_file = JIB_CONFIG_DIR / "config.yaml"

        # Load secrets
        if secrets_file.exists():
            with open(secrets_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip("\"'")
                        if key == "SLACK_TOKEN" and value:
                            config["slack_token"] = value
                        elif key == "GITHUB_TOKEN" and value:
                            config["github_token"] = value

        # Load YAML config
        if config_file.exists():
            try:
                import yaml

                with open(config_file) as f:
                    yaml_config = yaml.safe_load(f) or {}
                config.update(yaml_config)
            except ImportError:
                pass

        # Environment overrides
        for key in ["SLACK_TOKEN", "GITHUB_TOKEN", "SLACK_CHANNEL"]:
            if os.environ.get(key):
                config[key.lower()] = os.environ[key]

        return config

    def calculate_slack_metrics(self, threads: list[SlackThread]) -> dict[str, Any]:
        """Calculate metrics from Slack threads."""
        metrics = {
            "total_threads": len(threads),
            "resolved_threads": 0,
            "pending_threads": 0,
            "escalated_threads": 0,
            "avg_messages_per_thread": 0,
            "avg_jib_messages_per_thread": 0,
            "avg_response_time_minutes": 0,
            "avg_thread_duration_minutes": 0,
            "total_jib_messages": 0,
            "total_human_messages": 0,
            "resolution_rate": 0,
        }

        if not threads:
            return metrics

        total_messages = 0
        total_jib_messages = 0
        total_human_messages = 0
        total_duration = 0

        for thread in threads:
            # Count by outcome
            if thread.outcome == "resolved":
                metrics["resolved_threads"] += 1
            elif thread.outcome == "escalated":
                metrics["escalated_threads"] += 1
            else:
                metrics["pending_threads"] += 1

            # Accumulate totals
            total_messages += thread.total_messages
            total_jib_messages += thread.jib_message_count
            total_human_messages += thread.human_message_count
            total_duration += thread.duration_seconds

        # Calculate averages
        metrics["avg_messages_per_thread"] = total_messages / len(threads)
        metrics["avg_jib_messages_per_thread"] = total_jib_messages / len(threads)
        metrics["avg_thread_duration_minutes"] = (total_duration / 60) / len(threads)
        metrics["total_jib_messages"] = total_jib_messages
        metrics["total_human_messages"] = total_human_messages
        metrics["resolution_rate"] = (
            (metrics["resolved_threads"] / len(threads) * 100) if threads else 0
        )

        return metrics

    def calculate_github_metrics(self, prs: list[GitHubPR]) -> dict[str, Any]:
        """Calculate metrics from GitHub PRs."""
        metrics = {
            "total_prs": len(prs),
            "merged_prs": 0,
            "closed_prs": 0,
            "open_prs": 0,
            "avg_iterations": 0,
            "avg_files_changed": 0,
            "avg_lines_changed": 0,
            "total_jib_commits": 0,
            "total_jib_comments": 0,
            "avg_pr_duration_hours": 0,
            "merge_rate": 0,
            "first_try_success_rate": 0,  # PRs merged on first iteration
        }

        if not prs:
            return metrics

        total_iterations = 0
        total_files = 0
        total_lines = 0
        total_duration = 0
        first_try_merges = 0
        duration_count = 0

        for pr in prs:
            # Count by state
            if pr.state == "merged":
                metrics["merged_prs"] += 1
                if pr.iterations == 1:
                    first_try_merges += 1
            elif pr.state == "closed":
                metrics["closed_prs"] += 1
            else:
                metrics["open_prs"] += 1

            # Accumulate totals
            total_iterations += pr.iterations
            total_files += pr.files_changed
            total_lines += pr.lines_added + pr.lines_deleted
            metrics["total_jib_commits"] += pr.jib_commits
            metrics["total_jib_comments"] += pr.jib_comments

            # Calculate duration for closed/merged PRs
            if pr.closed_at:
                duration = (pr.closed_at - pr.created_at).total_seconds() / 3600
                total_duration += duration
                duration_count += 1

        # Calculate averages
        metrics["avg_iterations"] = total_iterations / len(prs)
        metrics["avg_files_changed"] = total_files / len(prs)
        metrics["avg_lines_changed"] = total_lines / len(prs)
        if duration_count > 0:
            metrics["avg_pr_duration_hours"] = total_duration / duration_count
        metrics["merge_rate"] = (metrics["merged_prs"] / len(prs) * 100) if prs else 0
        metrics["first_try_success_rate"] = (
            (first_try_merges / metrics["merged_prs"] * 100) if metrics["merged_prs"] else 0
        )

        return metrics

    def identify_patterns(
        self, threads: list[SlackThread], prs: list[GitHubPR]
    ) -> dict[str, list[str]]:
        """Identify patterns in jib's communications."""
        patterns = {
            "strengths": [],
            "areas_for_improvement": [],
            "common_topics": [],
            "efficiency_patterns": [],
        }

        # Analyze Slack patterns
        if threads:
            resolved = [t for t in threads if t.outcome == "resolved"]
            escalated = [t for t in threads if t.outcome == "escalated"]

            if len(resolved) > len(threads) * 0.7:
                patterns["strengths"].append(
                    f"High thread resolution rate: {len(resolved)}/{len(threads)} threads resolved"
                )

            if escalated:
                avg_escalated_messages = sum(t.total_messages for t in escalated) / len(escalated)
                patterns["areas_for_improvement"].append(
                    f"{len(escalated)} threads escalated, avg {avg_escalated_messages:.1f} messages before escalation"
                )

            # Analyze topics
            topic_words = defaultdict(int)
            for thread in threads:
                if thread.topic:
                    words = re.findall(r"\b\w{4,}\b", thread.topic.lower())
                    for word in words:
                        topic_words[word] += 1

            common_words = sorted(topic_words.items(), key=lambda x: -x[1])[:5]
            if common_words:
                patterns["common_topics"].append(
                    f"Common discussion topics: {', '.join(w[0] for w in common_words)}"
                )

        # Analyze GitHub patterns
        if prs:
            merged = [p for p in prs if p.state == "merged"]
            first_try = [p for p in merged if p.iterations == 1]

            if first_try and len(first_try) > len(merged) * 0.5:
                patterns["strengths"].append(
                    f"Good first-try success: {len(first_try)}/{len(merged)} PRs merged on first iteration"
                )

            multi_iteration = [p for p in merged if p.iterations > 2]
            if multi_iteration:
                patterns["areas_for_improvement"].append(
                    f"{len(multi_iteration)} PRs required 3+ iterations - review feedback patterns"
                )

            # Efficiency patterns
            avg_lines = sum(p.lines_added + p.lines_deleted for p in prs) / len(prs) if prs else 0
            if avg_lines < 200:
                patterns["efficiency_patterns"].append(
                    f"PRs are well-scoped: avg {avg_lines:.0f} lines changed"
                )
            elif avg_lines > 500:
                patterns["efficiency_patterns"].append(
                    f"Consider smaller PRs: avg {avg_lines:.0f} lines changed"
                )

        return patterns

    def generate_recommendations(
        self,
        slack_metrics: dict[str, Any],
        github_metrics: dict[str, Any],
        patterns: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        """Generate actionable recommendations."""
        recommendations = []

        # Slack-based recommendations
        if slack_metrics["total_threads"] > 0:
            if slack_metrics["resolution_rate"] < 60:
                recommendations.append(
                    {
                        "priority": "HIGH",
                        "category": "Thread Resolution",
                        "issue": f"Only {slack_metrics['resolution_rate']:.1f}% of threads resolved",
                        "recommendation": "Review unresolved threads for common blockers. Add proactive clarification questions.",
                    }
                )

            if slack_metrics["avg_thread_duration_minutes"] > 60:
                recommendations.append(
                    {
                        "priority": "MEDIUM",
                        "category": "Response Efficiency",
                        "issue": f"Average thread duration is {slack_metrics['avg_thread_duration_minutes']:.1f} minutes",
                        "recommendation": "Provide more comprehensive initial responses to reduce back-and-forth.",
                    }
                )

            if slack_metrics["escalated_threads"] > slack_metrics["total_threads"] * 0.2:
                recommendations.append(
                    {
                        "priority": "HIGH",
                        "category": "Escalation Rate",
                        "issue": f"{slack_metrics['escalated_threads']} threads escalated ({slack_metrics['escalated_threads'] / slack_metrics['total_threads'] * 100:.1f}%)",
                        "recommendation": "Analyze escalated threads for common failure patterns. Improve error handling and communication.",
                    }
                )

        # GitHub-based recommendations
        if github_metrics["total_prs"] > 0:
            if github_metrics["first_try_success_rate"] < 50:
                recommendations.append(
                    {
                        "priority": "HIGH",
                        "category": "PR Quality",
                        "issue": f"Only {github_metrics['first_try_success_rate']:.1f}% PRs merged on first try",
                        "recommendation": "Run tests before creating PRs. Review code for common issues. Add self-review checklist.",
                    }
                )

            if github_metrics["avg_iterations"] > 2:
                recommendations.append(
                    {
                        "priority": "MEDIUM",
                        "category": "Review Cycles",
                        "issue": f"Average {github_metrics['avg_iterations']:.1f} iterations per PR",
                        "recommendation": "Address all review comments in single iteration. Ask clarifying questions upfront.",
                    }
                )

            if github_metrics["avg_lines_changed"] > 500:
                recommendations.append(
                    {
                        "priority": "LOW",
                        "category": "PR Scope",
                        "issue": f"Average {github_metrics['avg_lines_changed']:.0f} lines per PR",
                        "recommendation": "Break large changes into smaller, focused PRs for easier review.",
                    }
                )

        return recommendations

    def generate_report(
        self,
        threads: list[SlackThread],
        prs: list[GitHubPR],
        slack_metrics: dict[str, Any],
        github_metrics: dict[str, Any],
        patterns: dict[str, list[str]],
        recommendations: list[dict[str, Any]],
    ) -> str:
        """Generate markdown report."""
        report = f"""# jib Communication Analysis Report
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Period: Last {self.days} days

## Executive Summary

| Source | Total | Success Rate |
|--------|-------|--------------|
| Slack Threads | {slack_metrics["total_threads"]} | {slack_metrics["resolution_rate"]:.1f}% resolved |
| GitHub PRs | {github_metrics["total_prs"]} | {github_metrics["merge_rate"]:.1f}% merged |

## Slack Thread Analysis

### Metrics
- **Total Threads**: {slack_metrics["total_threads"]}
- **Resolved**: {slack_metrics["resolved_threads"]} | **Pending**: {slack_metrics["pending_threads"]} | **Escalated**: {slack_metrics["escalated_threads"]}
- **Resolution Rate**: {slack_metrics["resolution_rate"]:.1f}%
- **Avg Messages/Thread**: {slack_metrics["avg_messages_per_thread"]:.1f}
- **Avg jib Messages/Thread**: {slack_metrics["avg_jib_messages_per_thread"]:.1f}
- **Avg Thread Duration**: {slack_metrics["avg_thread_duration_minutes"]:.1f} minutes

### Thread Summary
"""
        # Add thread summaries
        for thread in sorted(threads, key=lambda t: t.start_time, reverse=True)[:10]:
            outcome_emoji = {"resolved": "✅", "pending": "⏳", "escalated": "⚠️"}.get(
                thread.outcome, "❓"
            )
            topic_preview = (
                (thread.topic or "No topic")[:50] + "..."
                if thread.topic and len(thread.topic) > 50
                else (thread.topic or "No topic")
            )
            report += f"- {outcome_emoji} {thread.start_time.strftime('%m/%d')}: {topic_preview} ({thread.total_messages} msgs)\n"

        report += f"""
## GitHub PR Analysis

### Metrics
- **Total PRs**: {github_metrics["total_prs"]}
- **Merged**: {github_metrics["merged_prs"]} | **Closed**: {github_metrics["closed_prs"]} | **Open**: {github_metrics["open_prs"]}
- **Merge Rate**: {github_metrics["merge_rate"]:.1f}%
- **First-Try Success Rate**: {github_metrics["first_try_success_rate"]:.1f}%
- **Avg Iterations**: {github_metrics["avg_iterations"]:.1f}
- **Avg Files Changed**: {github_metrics["avg_files_changed"]:.1f}
- **Avg Lines Changed**: {github_metrics["avg_lines_changed"]:.0f}
- **Avg PR Duration**: {github_metrics["avg_pr_duration_hours"]:.1f} hours

### PR Summary
"""
        # Add PR summaries
        for pr in sorted(prs, key=lambda p: p.created_at, reverse=True)[:10]:
            state_emoji = {"merged": "✅", "closed": "❌", "open": "🔵"}.get(pr.state, "❓")
            report += f"- {state_emoji} [{pr.repo}#{pr.number}]({pr.url}): {pr.title[:50]}{'...' if len(pr.title) > 50 else ''}\n"

        report += """
## Identified Patterns

### Strengths
"""
        for pattern in patterns["strengths"]:
            report += f"- ✨ {pattern}\n"
        if not patterns["strengths"]:
            report += "- No specific strengths identified in this period\n"

        report += """
### Areas for Improvement
"""
        for pattern in patterns["areas_for_improvement"]:
            report += f"- 🎯 {pattern}\n"
        if not patterns["areas_for_improvement"]:
            report += "- No specific areas identified in this period\n"

        report += """
### Efficiency Patterns
"""
        for pattern in patterns["efficiency_patterns"]:
            report += f"- 📊 {pattern}\n"
        if not patterns["efficiency_patterns"]:
            report += "- No efficiency patterns identified\n"

        report += """
## Recommendations
"""
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                report += f"""
### {i}. [{rec["priority"]}] {rec["category"]}

**Issue**: {rec["issue"]}

**Recommendation**: {rec["recommendation"]}
"""
        else:
            report += "\n*No specific recommendations at this time*\n"

        report += f"""
---

*Analysis based on {slack_metrics["total_threads"]} Slack threads and {github_metrics["total_prs"]} GitHub PRs*
*Report saved to: ~/sharing/analysis/*
"""
        return report

    def run_analysis(self) -> str | None:
        """Run full analysis and generate report."""
        print(f"Analyzing jib communications from last {self.days} days...")

        # Fetch Slack threads
        threads = []
        if self.slack_fetcher:
            print("Fetching Slack threads...")
            try:
                threads = self.slack_fetcher.fetch_threads(self.days)
                print(f"  Found {len(threads)} threads with jib participation")
            except Exception as e:
                print(f"  WARNING: Failed to fetch Slack threads: {e}", file=sys.stderr)

        # Fetch GitHub PRs
        prs = []
        if self.github_fetcher:
            print("Fetching GitHub PRs...")
            try:
                prs = self.github_fetcher.fetch_prs(self.days)
                print(f"  Found {len(prs)} PRs with jib contribution")
            except Exception as e:
                print(f"  WARNING: Failed to fetch GitHub PRs: {e}", file=sys.stderr)

        if not threads and not prs:
            print("WARNING: No data found for analysis", file=sys.stderr)
            return None

        # Calculate metrics
        print("Calculating metrics...")
        slack_metrics = self.calculate_slack_metrics(threads)
        github_metrics = self.calculate_github_metrics(prs)

        # Identify patterns
        print("Identifying patterns...")
        patterns = self.identify_patterns(threads, prs)

        # Generate recommendations
        print("Generating recommendations...")
        recommendations = self.generate_recommendations(slack_metrics, github_metrics, patterns)

        # Generate report
        print("Generating report...")
        report = self.generate_report(
            threads, prs, slack_metrics, github_metrics, patterns, recommendations
        )

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_file = self.analysis_dir / f"analysis-{timestamp}.md"
        with open(report_file, "w") as f:
            f.write(report)

        # Save metrics as JSON
        metrics_file = self.analysis_dir / f"metrics-{timestamp}.json"
        with open(metrics_file, "w") as f:
            json.dump(
                {
                    "timestamp": timestamp,
                    "slack_metrics": slack_metrics,
                    "github_metrics": github_metrics,
                    "patterns": patterns,
                    "recommendations": recommendations,
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

        # Send notification if there are recommendations
        if recommendations:
            self.send_notification(
                slack_metrics, github_metrics, recommendations, report_file, report
            )

        return report

    def send_notification(
        self,
        slack_metrics: dict[str, Any],
        github_metrics: dict[str, Any],
        recommendations: list[dict[str, Any]],
        report_file: Path,
        full_report: str,
    ):
        """Send notification about analysis results."""
        notification_dir = Path.home() / "sharing" / "notifications"
        notification_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_id = f"{timestamp}-conversation-analysis"

        # Determine priority
        high_priority_count = sum(1 for r in recommendations if r["priority"] == "HIGH")
        if high_priority_count >= 2:
            priority = "HIGH"
        elif high_priority_count >= 1 or len(recommendations) >= 3:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        # Create summary notification
        summary_file = notification_dir / f"{task_id}.md"
        summary = f"""# 📊 Communication Analysis Complete

**Priority**: {priority} | {len(recommendations)} recommendations

**Quick Stats:**
- 💬 Slack: {slack_metrics["total_threads"]} threads ({slack_metrics["resolution_rate"]:.0f}% resolved)
- 🔀 GitHub: {github_metrics["total_prs"]} PRs ({github_metrics["merge_rate"]:.0f}% merged)
- 🎯 First-try success: {github_metrics["first_try_success_rate"]:.0f}%

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
        reports = list(analysis_dir.glob("analysis-*.md"))
        if not reports:
            return None

        reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        most_recent = reports[0]
        return datetime.fromtimestamp(most_recent.stat().st_mtime)
    except Exception as e:
        logging.error(f"Error checking last run: {e}")
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
        description="Analyze jib's Slack threads and GitHub PRs",
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
        "--output", type=Path, help="Output directory (default: ~/sharing/analysis)"
    )
    parser.add_argument("--print", action="store_true", help="Print report to stdout")
    parser.add_argument("--force", action="store_true", help="Force analysis even if run recently")

    args = parser.parse_args()

    # Determine analysis directory
    analysis_dir = args.output if args.output else ANALYSIS_DIR

    # Check if we should run
    if not should_run_analysis(analysis_dir, force=args.force):
        sys.exit(0)

    analyzer = ConversationAnalyzer(days=args.days)

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
