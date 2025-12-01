#!/usr/bin/env python3
"""
Weekly Inefficiency Report Generator - Phase 3+4 of ADR-LLM-Inefficiency-Reporting

Generates weekly reports on LLM processing inefficiencies, generates improvement
proposals, and delivers them via GitHub PRs and Slack notifications.

This is the automated component that:
1. Analyzes trace sessions from the past week
2. Generates comprehensive inefficiency reports
3. Creates PRs with reports committed to docs/analysis/inefficiency/
4. (Phase 4) Generates improvement proposals from detected inefficiencies
5. (Phase 4) Sends Slack notifications for proposal review
6. (Phase 4) Tracks impact of implemented proposals

Reports: Creates PRs with reports committed to docs/analysis/inefficiency/ in the repo.
         Keeps only the last 5 reports (deletes older ones when creating PR #6).

Runs on host (not in container) via systemd timer:
- Weekly (Monday at 11:00 AM, after beads-analyzer)
- Can force run with --force flag

Usage:
    weekly_report_generator.py [--days N] [--force] [--stdout] [--no-proposals] [--no-slack]

Example:
    weekly_report_generator.py                    # Run weekly analysis
    weekly_report_generator.py --force            # Force run regardless of schedule
    weekly_report_generator.py --days 14          # Analyze last 14 days
    weekly_report_generator.py --no-proposals     # Skip proposal generation
"""

import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


# Add the inefficiency-detector and config to path for imports
sys.path.insert(0, str(Path(__file__).parent))
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import contextlib

from impact_tracker import ImpactTracker
from improvement_proposer import ImprovementProposer
from inefficiency_detector import InefficiencyDetector
from inefficiency_schema import AggregateInefficiencyReport, Severity
from proposal_schema import ProposalBatch, ProposalPriority

from config.model_pricing import calculate_blended_cost, get_active_model, get_model_pricing


# Constants
ANALYSIS_DIR = REPO_ROOT / "docs" / "analysis" / "inefficiency"
PROPOSALS_DIR = REPO_ROOT / "docs" / "analysis" / "proposals"
IMPACT_DIR = REPO_ROOT / "docs" / "analysis" / "impact"


class WeeklyReportGenerator:
    """
    Generates weekly inefficiency reports and creates GitHub PRs with the results.

    Phase 4 additions:
    - Generates improvement proposals from detected inefficiencies
    - Sends Slack notifications for proposal review
    - Tracks impact of implemented proposals
    """

    def __init__(
        self,
        days: int = 7,
        generate_proposals: bool = True,
        send_slack: bool = True,
    ):
        self.days = days
        self.analysis_dir = ANALYSIS_DIR
        self.detector = InefficiencyDetector()

        # Phase 4 components
        self.generate_proposals = generate_proposals
        self.send_slack = send_slack
        self.proposer = ImprovementProposer(proposals_dir=PROPOSALS_DIR)
        self.impact_tracker = ImpactTracker(tracking_dir=IMPACT_DIR, proposals_dir=PROPOSALS_DIR)

    def generate_weekly_report(self) -> tuple[AggregateInefficiencyReport | None, Path | None]:
        """
        Generate the weekly inefficiency report.

        Returns:
            Tuple of (report, report_file_path) or (None, None) if no data
        """
        print(f"Analyzing LLM inefficiencies from last {self.days} days...")

        # Calculate time range
        end = datetime.now()
        start = end - timedelta(days=self.days)

        # Run analysis
        report = self.detector.analyze_period(since=start, until=end)

        if report.total_sessions == 0:
            print("No sessions found in the specified period")
            return None, None

        # Ensure output directory exists
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_file = self.analysis_dir / f"inefficiency-report-{timestamp}.md"
        metrics_file = self.analysis_dir / f"inefficiency-metrics-{timestamp}.json"

        # Generate markdown report
        self._generate_enhanced_markdown_report(report, report_file, timestamp)

        # Save JSON metrics
        self.detector.export_report(report, metrics_file)

        # Create latest symlinks
        latest_report = self.analysis_dir / "latest-report.md"
        latest_metrics = self.analysis_dir / "latest-metrics.json"

        if latest_report.exists() or latest_report.is_symlink():
            latest_report.unlink()
        if latest_metrics.exists() or latest_metrics.is_symlink():
            latest_metrics.unlink()

        latest_report.symlink_to(report_file.name)
        latest_metrics.symlink_to(metrics_file.name)

        print("\n✓ Report generated!")
        print(f"  Markdown: {report_file}")
        print(f"  JSON: {metrics_file}")

        return report, report_file

    def _generate_enhanced_markdown_report(
        self, report: AggregateInefficiencyReport, output_path: Path, timestamp: str
    ) -> None:
        """Generate an enhanced markdown report with additional formatting."""
        with open(output_path, "w") as f:
            # Header
            f.write("# LLM Inefficiency Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Period:** {report.time_period}\n\n")

            # Health Score
            health_score = self._calculate_health_score(report)
            f.write(
                f"## Health Score: {health_score}/100 {self._get_health_emoji(health_score)}\n\n"
            )

            # Executive Summary
            f.write("## Executive Summary\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Total Sessions Analyzed | {report.total_sessions} |\n")
            f.write(f"| Total Tokens Consumed | {report.total_tokens:,} |\n")
            f.write(f"| Total Wasted Tokens | {report.total_wasted_tokens:,} |\n")
            f.write(f"| Average Inefficiency Rate | {report.average_inefficiency_rate:.1f}% |\n")

            # Calculate potential savings using actual model pricing from configuration
            if report.total_wasted_tokens > 0:
                # Get pricing for active model from configuration
                active_model = get_active_model()
                pricing = get_model_pricing(active_model)
                # Wasted tokens are primarily output tokens from failed/retried tool calls
                # Using blended rate assuming ~60% output, 40% input for wasted tokens
                potential_savings = calculate_blended_cost(
                    report.total_wasted_tokens, input_ratio=0.4, model=active_model
                )
                f.write(f"| Estimated Weekly Savings | ~${potential_savings:.2f} |\n")
                f.write(
                    f"| *(Based on {active_model} pricing: ${pricing['input']}/MTok in, ${pricing['output']}/MTok out)* | |\n"
                )

            f.write("\n")

            # Key Finding
            if report.top_issues:
                top_issue = report.top_issues[0]
                f.write(f"**Top Issue:** {top_issue['sub_category'].replace('_', ' ').title()} ")
                f.write(f"accounts for {top_issue['total_waste_tokens']:,} wasted tokens ")
                f.write(f"across {top_issue['occurrences']} occurrences.\n\n")

            # Inefficiency Breakdown by Category
            f.write("## Inefficiency Breakdown by Category\n\n")
            if report.category_counts:
                total_count = sum(report.category_counts.values())
                f.write("```\n")
                for category, count in sorted(report.category_counts.items(), key=lambda x: -x[1]):
                    percentage = (count / total_count * 100) if total_count > 0 else 0
                    bar_len = int(percentage / 2.5)  # 40 chars max
                    bar = "█" * bar_len
                    f.write(
                        f"{category.replace('_', ' ').title():<25} {bar:<40} {percentage:.0f}%\n"
                    )
                f.write("```\n\n")
            else:
                f.write("*No inefficiencies detected this period!*\n\n")

            # Severity Breakdown
            f.write("## Inefficiency Breakdown by Severity\n\n")
            if report.severity_counts:
                for severity in ["high", "medium", "low"]:
                    count = report.severity_counts.get(severity, 0)
                    emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}[severity]
                    f.write(f"- {emoji} **{severity.upper()}**: {count}\n")
                f.write("\n")
            else:
                f.write("*No issues detected.*\n\n")

            # Top Issues (detailed)
            if report.top_issues:
                f.write("## Top 5 Issues\n\n")
                for i, issue in enumerate(report.top_issues, 1):
                    f.write(f"### {i}. {issue['sub_category'].replace('_', ' ').title()}\n\n")
                    f.write(f"**Category:** {issue['category'].replace('_', ' ').title()}\n\n")
                    f.write(f"**Occurrences:** {issue['occurrences']}\n\n")
                    f.write(f"**Total Waste:** {issue['total_waste_tokens']:,} tokens\n\n")
                    f.write(f"**Example:** {issue['example_description']}\n\n")
                    f.write(f"**Recommendation:** {issue['recommendation']}\n\n")
                    f.write("---\n\n")

            # Sessions with Highest Inefficiency
            f.write("## Sessions with Highest Inefficiency\n\n")
            top_sessions = sorted(report.sessions, key=lambda s: s.inefficiency_rate, reverse=True)[
                :5
            ]

            if top_sessions:
                for session in top_sessions:
                    f.write(f"### Session: `{session.session_id}`\n\n")
                    f.write(f"- **Task:** {session.task_id or 'N/A'}\n")
                    f.write(f"- **Inefficiency Rate:** {session.inefficiency_rate:.1f}%\n")
                    f.write(
                        f"- **Wasted Tokens:** {session.total_wasted_tokens:,} / {session.total_tokens:,}\n"
                    )
                    f.write(f"- **Issues Found:** {len(session.inefficiencies)}\n\n")

                    if session.inefficiencies:
                        f.write("**Issues:**\n")
                        for ineff in session.inefficiencies[:5]:  # Limit to 5
                            severity_emoji = {
                                Severity.HIGH: "🔴",
                                Severity.MEDIUM: "🟡",
                                Severity.LOW: "🟢",
                            }.get(ineff.severity, "⚪")
                            f.write(f"- {severity_emoji} {ineff.description}\n")
                        if len(session.inefficiencies) > 5:
                            f.write(f"- *(+{len(session.inefficiencies) - 5} more)*\n")
                        f.write("\n")
            else:
                f.write("*No sessions analyzed in this period.*\n\n")

            # Actionable Improvements Section
            f.write("## Actionable Improvements\n\n")
            recommendations = self._generate_recommendations(report)
            if recommendations:
                f.write("### High Priority (This Week)\n\n")
                for i, rec in enumerate(recommendations[:3], 1):
                    f.write(f"{i}. {rec}\n")
                f.write("\n")

                if len(recommendations) > 3:
                    f.write("### Medium Priority (Next Sprint)\n\n")
                    for i, rec in enumerate(recommendations[3:], 4):
                        f.write(f"{i}. {rec}\n")
                    f.write("\n")
            else:
                f.write("*No specific recommendations - keep up the good work!*\n\n")

            # Footer
            f.write("---\n\n")
            f.write(
                f"*Report generated from {report.total_sessions} sessions over {self.days} days*\n"
            )
            f.write(
                "*Analysis performed by [LLM Inefficiency Detector](../../../docs/adr/in-progress/ADR-LLM-Inefficiency-Reporting.md)*\n"
            )

    def _calculate_health_score(self, report: AggregateInefficiencyReport) -> int:
        """Calculate an overall health score (0-100)."""
        if report.total_sessions == 0:
            return 100

        score = 100

        # Deduct based on inefficiency rate
        avg_rate = report.average_inefficiency_rate
        if avg_rate > 20:
            score -= 30
        elif avg_rate > 15:
            score -= 20
        elif avg_rate > 10:
            score -= 10
        elif avg_rate > 5:
            score -= 5

        # Deduct for severity
        high_count = report.severity_counts.get("high", 0)
        medium_count = report.severity_counts.get("medium", 0)

        score -= high_count * 5
        score -= medium_count * 2

        # Bonus for low waste percentage
        if report.total_tokens > 0:
            waste_pct = (report.total_wasted_tokens / report.total_tokens) * 100
            if waste_pct < 5:
                score += 10
            elif waste_pct < 10:
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

    def _generate_recommendations(self, report: AggregateInefficiencyReport) -> list[str]:
        """Generate actionable recommendations based on the report."""
        recommendations = []

        for issue in report.top_issues[:5]:
            sub_cat = issue["sub_category"]
            rec = issue["recommendation"]

            if sub_cat == "documentation_miss":
                recommendations.append(
                    f"**Update CLAUDE.md**: Add guidance to prefer glob patterns for file discovery. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "retry_storm":
                recommendations.append(
                    f"**Add error handling guidance**: Investigate errors before retrying, check prerequisites. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "redundant_read":
                recommendations.append(
                    f"**Improve context management**: Add guidance to avoid re-reading files already in context. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "excessive_context":
                recommendations.append(
                    f"**Add file reading guidance**: Use limit/offset for large files. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "api_confusion":
                recommendations.append(
                    f"**Improve tool documentation**: Add clearer parameter examples. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "search_failure":
                recommendations.append(
                    f"**Add search strategy guidance**: Verify targets exist before extensive searching. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "parameter_error":
                recommendations.append(
                    f"**Add parameter validation guidance**: Verify tool parameters before calling. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            else:
                recommendations.append(f"**{sub_cat.replace('_', ' ').title()}**: {rec}")

        return recommendations

    def _cleanup_old_reports(self, max_reports: int = 5) -> list[Path]:
        """Keep only the last N reports, return files to be deleted."""
        report_files = sorted(
            self.analysis_dir.glob("inefficiency-report-*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        metrics_files = sorted(
            self.analysis_dir.glob("inefficiency-metrics-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        to_delete = []

        if len(report_files) > max_reports:
            to_delete.extend(report_files[max_reports:])
        if len(metrics_files) > max_reports:
            to_delete.extend(metrics_files[max_reports:])

        return to_delete

    def create_pr_with_report(
        self,
        report: AggregateInefficiencyReport,
        report_file: Path,
        timestamp: str,
        proposal_batch: ProposalBatch | None = None,
    ) -> str | None:
        """
        Create a PR with the inefficiency report.

        Args:
            report: The aggregate inefficiency report.
            report_file: Path to the report markdown file.
            timestamp: Timestamp string for the report.
            proposal_batch: Optional proposal batch to include in PR.

        Returns:
            PR URL if successful, None otherwise
        """
        print("\nPreparing to create PR with inefficiency report...")

        # Cleanup old reports
        to_delete = self._cleanup_old_reports(max_reports=5)

        branch_name = f"inefficiency-report-{timestamp}"

        try:
            # Create new branch from origin/main
            subprocess.run(
                ["git", "checkout", "-b", branch_name, "origin/main"],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            print(f"✓ Created branch: {branch_name}")

            # Delete old reports if any
            if to_delete:
                for file_path in to_delete:
                    subprocess.run(
                        ["git", "rm", str(file_path)],
                        check=True,
                        cwd=REPO_ROOT,
                        capture_output=True,
                        text=True,
                    )
                print(f"✓ Removed {len(to_delete)} old report(s)")

            # Stage new report files
            subprocess.run(
                ["git", "add", str(self.analysis_dir)],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            # Commit
            health_score = self._calculate_health_score(report)
            commit_message = f"""chore: Add LLM inefficiency report {timestamp}

Health Score: {health_score}/100
- Sessions Analyzed: {report.total_sessions}
- Total Tokens: {report.total_tokens:,}
- Wasted Tokens: {report.total_wasted_tokens:,}
- Inefficiency Rate: {report.average_inefficiency_rate:.1f}%

High-severity issues: {report.severity_counts.get("high", 0)}
"""
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            print("✓ Committed changes")

            # Push branch
            subprocess.run(
                ["git", "push", "origin", branch_name],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            print(f"✓ Pushed to origin/{branch_name}")

            # Create PR
            pr_title = f"LLM Inefficiency Report - {timestamp}"
            pr_body = f"""## LLM Inefficiency Report

**Health Score**: {health_score}/100 {self._get_health_emoji(health_score)}

### Quick Stats
- 📊 Sessions Analyzed: {report.total_sessions}
- 🔢 Total Tokens: {report.total_tokens:,}
- ⚠️ Wasted Tokens: {report.total_wasted_tokens:,}
- 📈 Inefficiency Rate: {report.average_inefficiency_rate:.1f}%

### Severity Summary
- 🔴 High: {report.severity_counts.get("high", 0)}
- 🟡 Medium: {report.severity_counts.get("medium", 0)}
- 🟢 Low: {report.severity_counts.get("low", 0)}

### Top Issues
"""
            for issue in report.top_issues[:3]:
                pr_body += f"- **{issue['sub_category'].replace('_', ' ').title()}**: {issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens\n"

            pr_body += f"""
### Files in this PR
- `docs/analysis/inefficiency/inefficiency-report-{timestamp}.md` - Full report
- `docs/analysis/inefficiency/inefficiency-metrics-{timestamp}.json` - Machine-readable metrics
- Symlinks updated to point to latest reports

See the full report for detailed analysis and actionable recommendations.
"""
            # Add Phase 4: Proposals section
            if proposal_batch and proposal_batch.total_proposals > 0:
                pr_body += f"""
### Improvement Proposals (Phase 4)
- **Total Proposals:** {proposal_batch.total_proposals}
- **Expected Savings:** ~{proposal_batch.total_expected_savings:,} tokens/week

"""
                high_priority = [
                    p for p in proposal_batch.proposals if p.priority == ProposalPriority.HIGH
                ]
                if high_priority:
                    pr_body += "**High Priority:**\n"
                    for p in high_priority[:3]:
                        pr_body += f"- `{p.proposal_id}`: {p.title}\n"

                pr_body += "\nProposals require human review. Reply to the Slack notification to approve/reject.\n"

            # Add cleanup note if files were deleted
            if to_delete:
                pr_body += f"\n### Cleanup\n- Removed {len(to_delete)} old report(s) to maintain max 5 reports\n"

            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    pr_title,
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
            print(f"✓ Created PR: {pr_url}")
            return pr_url

        except subprocess.CalledProcessError as e:
            print(f"ERROR creating PR: {e}", file=sys.stderr)
            print(f"  stdout: {e.stdout}", file=sys.stderr)
            print(f"  stderr: {e.stderr}", file=sys.stderr)
            # Try to return to original branch
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["git", "checkout", "-"],
                    check=False,
                    cwd=REPO_ROOT,
                    capture_output=True,
                )
            return None

    def run(self) -> bool:
        """
        Run the full weekly report generation workflow.

        Returns:
            True if report generated successfully
        """
        # Generate report
        report, report_file = self.generate_weekly_report()

        if report is None:
            print("No data to report")
            return False

        # Create timestamp for PR
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Phase 4: Generate improvement proposals
        proposal_batch = None
        if self.generate_proposals and report.total_sessions > 0:
            proposal_batch = self._generate_improvement_proposals(report)

        # Phase 4: Check impact of previously implemented proposals
        impact_report = self._check_proposal_impacts()

        # Create PR with report (and proposals if generated)
        pr_url = self.create_pr_with_report(report, report_file, timestamp, proposal_batch)

        # Phase 4: Send Slack notification with proposals for review
        if self.send_slack and proposal_batch and proposal_batch.total_proposals > 0:
            self._send_slack_notification(report, proposal_batch, impact_report, pr_url)

        print("\n" + "=" * 60)
        print("Weekly Inefficiency Report Complete")
        print("=" * 60)
        print(f"Sessions Analyzed: {report.total_sessions}")
        print(f"Inefficiency Rate: {report.average_inefficiency_rate:.1f}%")
        print(f"Health Score: {self._calculate_health_score(report)}/100")
        if pr_url:
            print(f"PR Created: {pr_url}")
        if proposal_batch:
            print(f"Proposals Generated: {proposal_batch.total_proposals}")
            print(f"Expected Savings: ~{proposal_batch.total_expected_savings:,} tokens/week")
        print("=" * 60)

        return True

    def _generate_improvement_proposals(
        self, report: AggregateInefficiencyReport
    ) -> ProposalBatch | None:
        """Generate improvement proposals from the inefficiency report.

        Args:
            report: The aggregate inefficiency report.

        Returns:
            ProposalBatch with generated proposals, or None if no proposals.
        """
        print("\nGenerating improvement proposals...")

        try:
            batch = self.proposer.generate_proposals(report)

            if batch.total_proposals == 0:
                print("  No proposals generated (thresholds not met)")
                return None

            # Save the batch
            batch_file = self.proposer.save_batch(batch)
            print(f"  Generated {batch.total_proposals} proposals")
            print(f"  Saved to: {batch_file}")

            # Also save markdown version
            md_file = batch_file.with_suffix(".md")
            with open(md_file, "w") as f:
                f.write(batch.to_markdown())

            return batch

        except Exception as e:
            print(f"  ERROR generating proposals: {e}")
            return None

    def _check_proposal_impacts(self) -> dict | None:
        """Check impact of previously implemented proposals.

        Returns:
            Impact summary or None if no proposals to check.
        """
        print("\nChecking implemented proposal impacts...")

        try:
            # Get proposals due for measurement
            due = self.impact_tracker.get_proposals_due_for_measurement()

            if due:
                print(f"  {len(due)} proposals due for impact measurement")
                # Note: Actual measurement requires comparing with new report data
                # This would be automated in a real implementation

            # Get implementation summary
            summary = self.impact_tracker.get_implementation_summary()

            if summary["total_implemented"] > 0:
                print(f"  Total implemented: {summary['total_implemented']}")
                print(f"  Awaiting measurement: {summary['awaiting_measurement']}")
                print(f"  Already measured: {summary['measured']}")
                if summary["measured"] > 0:
                    print(f"  Overall effectiveness: {summary['overall_effectiveness']:.0%}")

            return summary if summary["total_implemented"] > 0 else None

        except Exception as e:
            print(f"  ERROR checking impacts: {e}")
            return None

    def _send_slack_notification(
        self,
        report: AggregateInefficiencyReport,
        batch: ProposalBatch,
        impact_report: dict | None,
        pr_url: str | None,
    ) -> bool:
        """Send Slack notification with proposals for review.

        Args:
            report: The inefficiency report.
            batch: The proposal batch.
            impact_report: Impact summary of previous proposals.
            pr_url: URL of the PR created.

        Returns:
            True if notification sent successfully.
        """
        print("\nSending Slack notification...")

        try:
            # Try to import notifications library
            try:
                # Add shared lib to path
                shared_path = REPO_ROOT / "shared"
                if str(shared_path) not in sys.path:
                    sys.path.insert(0, str(shared_path))
                from notifications import NotificationContext, NotificationType, slack_notify
            except ImportError:
                print("  WARNING: notifications library not available, using file-based fallback")
                return self._send_slack_file_notification(report, batch, impact_report, pr_url)

            # Build notification content
            health_score = self._calculate_health_score(report)
            title = f"LLM Inefficiency Report - {batch.total_proposals} Proposals"

            body_lines = []
            body_lines.append(
                f"**Health Score:** {health_score}/100 {self._get_health_emoji(health_score)}"
            )
            body_lines.append(f"**Period:** {report.time_period}")
            body_lines.append("")
            body_lines.append("## Quick Stats")
            body_lines.append(f"- Sessions: {report.total_sessions}")
            body_lines.append(f"- Inefficiency Rate: {report.average_inefficiency_rate:.1f}%")
            body_lines.append(f"- Wasted Tokens: {report.total_wasted_tokens:,}")
            body_lines.append("")

            # Proposals summary
            body_lines.append("## Improvement Proposals")
            body_lines.append(f"**Total:** {batch.total_proposals}")
            body_lines.append(
                f"**Expected Savings:** ~{batch.total_expected_savings:,} tokens/week"
            )
            body_lines.append("")

            # List high priority proposals
            high = [p for p in batch.proposals if p.priority == ProposalPriority.HIGH]
            if high:
                body_lines.append("### High Priority")
                for p in high[:3]:  # Limit to top 3
                    body_lines.append(f"- **{p.title}** (`{p.proposal_id}`)")
                    body_lines.append(
                        f"  - {p.occurrences_count} occurrences, ~{p.expected_token_savings:,} savings"
                    )
                body_lines.append("")

            # Impact summary if available
            if impact_report and impact_report.get("measured", 0) > 0:
                body_lines.append("## Previous Proposals Impact")
                body_lines.append(f"- Implemented: {impact_report['total_implemented']}")
                body_lines.append(f"- Measured: {impact_report['measured']}")
                body_lines.append(f"- Effectiveness: {impact_report['overall_effectiveness']:.0%}")
                body_lines.append("")

            # Links
            if pr_url:
                body_lines.append(f"**Full Report PR:** {pr_url}")
            body_lines.append("")
            body_lines.append("## Review Commands")
            body_lines.append(
                "Reply with: `approve <id>`, `reject <id> <reason>`, `defer <id>`, `details <id>`"
            )
            body_lines.append("Or: `approve all` to approve all proposals")

            body = "\n".join(body_lines)

            # Send notification
            context = NotificationContext(
                task_id=f"inefficiency-report-{datetime.now().strftime('%Y%m%d')}",
                source="inefficiency-reporter",
                repository="jwbron/james-in-a-box",
            )

            result = slack_notify(
                title=title,
                body=body,
                context=context,
                notification_type=NotificationType.ACTION_REQUIRED,
            )

            if result.success:
                print(f"  Notification sent: {result.message_id}")
                return True
            else:
                print(f"  WARNING: Notification failed: {result.error_message}")
                return False

        except Exception as e:
            print(f"  ERROR sending Slack notification: {e}")
            return False

    def _send_slack_file_notification(
        self,
        report: AggregateInefficiencyReport,
        batch: ProposalBatch,
        impact_report: dict | None,
        pr_url: str | None,
    ) -> bool:
        """Fallback: Send notification via file-based system.

        Args:
            report: The inefficiency report.
            batch: The proposal batch.
            impact_report: Impact summary.
            pr_url: PR URL.

        Returns:
            True if file written successfully.
        """
        notifications_dir = Path.home() / "sharing" / "notifications"
        notifications_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}-inefficiency-proposals.md"
        filepath = notifications_dir / filename

        content = self.proposer.generate_slack_summary(batch)

        # Add PR link
        if pr_url:
            content += f"\n\n**Full Report PR:** {pr_url}"

        try:
            filepath.write_text(content)
            print(f"  Notification file written: {filepath}")
            return True
        except Exception as e:
            print(f"  ERROR writing notification file: {e}")
            return False


def check_last_run(analysis_dir: Path) -> datetime | None:
    """Check when the analyzer was last run."""
    try:
        reports = list(analysis_dir.glob("inefficiency-report-*.md"))
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
        description="Generate weekly LLM inefficiency reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run if last analysis was >7 days ago
  %(prog)s --force            # Force run regardless of schedule
  %(prog)s --days 14          # Analyze last 14 days
  %(prog)s --no-proposals     # Skip proposal generation (Phase 4)
  %(prog)s --no-slack         # Skip Slack notification
        """,
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to analyze (default: 7)"
    )
    parser.add_argument("--force", action="store_true", help="Force analysis even if run recently")
    parser.add_argument("--stdout", action="store_true", help="Print report to stdout")
    parser.add_argument(
        "--no-proposals", action="store_true", help="Skip improvement proposal generation"
    )
    parser.add_argument("--no-slack", action="store_true", help="Skip Slack notification")

    args = parser.parse_args()

    # Check if we should run
    if not should_run_analysis(ANALYSIS_DIR, force=args.force):
        sys.exit(0)

    # Run report generation
    generator = WeeklyReportGenerator(
        days=args.days,
        generate_proposals=not args.no_proposals,
        send_slack=not args.no_slack,
    )
    success = generator.run()

    # Optionally print to stdout
    if args.stdout:
        latest = ANALYSIS_DIR / "latest-report.md"
        if latest.exists():
            print("\n" + "=" * 80)
            print(latest.read_text())
            print("=" * 80)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
