#!/usr/bin/env python3
"""
Conversation Analysis Job for jib (James-in-a-Box)

Analyzes conversation logs to generate prompt tuning recommendations and
communication improvement suggestions.

This should run daily (via cron) to process accumulated logs and identify
patterns that can improve jib's performance.

Usage:
    analyze-conversations [--days N] [--output DIR]

Example:
    analyze-conversations --days 7
    analyze-conversations --days 30 --output ~/sharing/analysis/monthly
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
import subprocess

# Constants
# Use .jib-sharing for host paths (script runs on host, not in container)
LOGS_DIR = Path.home() / ".jib-sharing" / "logs" / "conversations"
ANALYSIS_DIR = Path.home() / ".jib-sharing" / "analysis"
PROMPTS_DIR = Path.home() / ".jib-sharing" / "prompts"


class ConversationAnalyzer:
    def __init__(self, days: int = 7):
        self.days = days
        self.logs_dir = LOGS_DIR
        self.analysis_dir = ANALYSIS_DIR
        self.prompts_dir = PROMPTS_DIR

        # Create directories
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

    def load_logs(self) -> List[Dict[str, Any]]:
        """Load conversation logs from the last N days"""
        cutoff = datetime.now() - timedelta(days=self.days)
        logs = []

        if not self.logs_dir.exists():
            print(f"WARNING: Logs directory does not exist: {self.logs_dir}", file=sys.stderr)
            return logs

        for log_file in sorted(self.logs_dir.glob("*.json")):
            try:
                with open(log_file, 'r') as f:
                    log = json.load(f)

                    # Check if within date range
                    log_date = datetime.fromisoformat(log['start_time'])
                    if log_date >= cutoff:
                        logs.append(log)
            except Exception as e:
                print(f"ERROR: Failed to load {log_file}: {e}", file=sys.stderr)

        return logs

    def calculate_metrics(self, logs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate aggregate metrics from logs"""
        metrics = {
            "total_sessions": len(logs),
            "successful_sessions": 0,
            "failed_sessions": 0,
            "blocked_sessions": 0,
            "partial_sessions": 0,
            "avg_iterations": 0,
            "avg_quality_score": 0,
            "avg_duration_minutes": 0,
            "avg_messages_per_session": 0,
            "avg_tool_calls_per_session": 0,
            "single_iteration_success_rate": 0,
            "quality_by_iteration": defaultdict(list),
            "duration_by_outcome": defaultdict(list),
            "messages_by_outcome": defaultdict(list)
        }

        if not logs:
            return metrics

        total_iterations = 0
        total_quality = 0
        quality_count = 0
        total_duration = 0
        total_messages = 0
        total_tools = 0
        single_iteration_success = 0

        for log in logs:
            outcome = log.get('outcome', {})
            status = outcome.get('status', 'unknown')
            iterations = outcome.get('iterations', 0)
            quality = outcome.get('quality_score')
            duration = log['metrics'].get('duration_seconds', 0)
            messages = log['metrics'].get('message_count', 0)
            tools = log['metrics'].get('tool_calls', 0)

            # Count by outcome
            if status == 'success':
                metrics['successful_sessions'] += 1
                if iterations == 1:
                    single_iteration_success += 1
            elif status == 'failed':
                metrics['failed_sessions'] += 1
            elif status == 'blocked':
                metrics['blocked_sessions'] += 1
            elif status == 'partial':
                metrics['partial_sessions'] += 1

            # Accumulate for averages
            total_iterations += iterations
            total_duration += duration
            total_messages += messages
            total_tools += tools

            if quality is not None:
                total_quality += quality
                quality_count += 1
                metrics['quality_by_iteration'][iterations].append(quality)

            # Track duration and messages by outcome
            metrics['duration_by_outcome'][status].append(duration / 60)  # Convert to minutes
            metrics['messages_by_outcome'][status].append(messages)

        # Calculate averages
        metrics['avg_iterations'] = total_iterations / len(logs) if logs else 0
        metrics['avg_quality_score'] = total_quality / quality_count if quality_count else 0
        metrics['avg_duration_minutes'] = (total_duration / 60) / len(logs) if logs else 0
        metrics['avg_messages_per_session'] = total_messages / len(logs) if logs else 0
        metrics['avg_tool_calls_per_session'] = total_tools / len(logs) if logs else 0
        metrics['single_iteration_success_rate'] = (single_iteration_success / metrics['successful_sessions'] * 100) if metrics['successful_sessions'] else 0

        return metrics

    def identify_patterns(self, logs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Identify patterns in successful vs unsuccessful conversations"""
        patterns = {
            "high_quality_patterns": [],
            "low_quality_patterns": [],
            "efficient_patterns": [],
            "inefficient_patterns": []
        }

        # Separate by quality (filter out None quality scores)
        high_quality = [l for l in logs if (l.get('outcome', {}).get('quality_score') or 0) >= 8]
        low_quality = [l for l in logs if l.get('outcome', {}).get('quality_score') is not None and l.get('outcome', {}).get('quality_score') <= 5]

        # Separate by efficiency (iterations)
        efficient = [l for l in logs if l.get('outcome', {}).get('iterations', 99) == 1]
        inefficient = [l for l in logs if l.get('outcome', {}).get('iterations', 0) >= 3]

        # Analyze high quality sessions
        if high_quality:
            avg_messages = sum(l['metrics']['message_count'] for l in high_quality) / len(high_quality)
            avg_tools = sum(l['metrics']['tool_calls'] for l in high_quality) / len(high_quality)
            patterns['high_quality_patterns'].append(f"Average {avg_messages:.1f} messages and {avg_tools:.1f} tool calls")

        # Analyze low quality sessions
        if low_quality:
            avg_messages = sum(l['metrics']['message_count'] for l in low_quality) / len(low_quality)
            avg_tools = sum(l['metrics']['tool_calls'] for l in low_quality) / len(low_quality)
            patterns['low_quality_patterns'].append(f"Average {avg_messages:.1f} messages and {avg_tools:.1f} tool calls")

        # Analyze efficient sessions
        if efficient:
            avg_duration = sum(l['metrics']['duration_seconds'] for l in efficient) / len(efficient) / 60
            patterns['efficient_patterns'].append(f"Single iteration sessions average {avg_duration:.1f} minutes")

        # Analyze inefficient sessions
        if inefficient:
            avg_duration = sum(l['metrics']['duration_seconds'] for l in inefficient) / len(inefficient) / 60
            common_tasks = [l['task_description'][:50] for l in inefficient[:5]]
            patterns['inefficient_patterns'].append(f"Multi-iteration sessions average {avg_duration:.1f} minutes")
            patterns['inefficient_patterns'].append(f"Common multi-iteration tasks: {', '.join(common_tasks)}")

        return patterns

    def generate_prompt_recommendations(self, logs: List[Dict[str, Any]], metrics: Dict[str, Any], patterns: Dict[str, Any]) -> List[str]:
        """Generate recommendations for tuning Claude prompts"""
        recommendations = []

        # Low single-iteration success rate
        if metrics['single_iteration_success_rate'] < 60 and metrics['successful_sessions'] > 5:
            recommendations.append({
                "priority": "HIGH",
                "category": "Iteration Efficiency",
                "issue": f"Only {metrics['single_iteration_success_rate']:.1f}% of successful sessions complete in one iteration",
                "recommendation": "Add to prompts: 'Before responding, gather ALL necessary context in parallel tool calls. Avoid back-and-forth for information gathering.'",
                "prompt_section": "Tool usage policy"
            })

        # High message count
        if metrics['avg_messages_per_session'] > 10:
            recommendations.append({
                "priority": "MEDIUM",
                "category": "Verbosity",
                "issue": f"Average {metrics['avg_messages_per_session']:.1f} messages per session",
                "recommendation": "Add to prompts: 'Be concise. Combine status updates with action. Minimize conversational messages.'",
                "prompt_section": "Tone and style"
            })

        # Low quality scores
        if metrics['avg_quality_score'] < 7 and metrics['avg_quality_score'] > 0:
            recommendations.append({
                "priority": "HIGH",
                "category": "Quality",
                "issue": f"Average quality score is {metrics['avg_quality_score']:.1f}/10",
                "recommendation": "Review quality issues in logs and add specific anti-patterns to prompts. Consider adding pre-submission checklist.",
                "prompt_section": "Quality Standards"
            })

        # Too many tool calls might indicate inefficiency
        if metrics['avg_tool_calls_per_session'] > 20:
            recommendations.append({
                "priority": "MEDIUM",
                "category": "Tool Efficiency",
                "issue": f"Average {metrics['avg_tool_calls_per_session']:.1f} tool calls per session",
                "recommendation": "Add to prompts: 'Plan tool usage. Use parallel calls. Avoid redundant reads. Use Task agent for exploration.'",
                "prompt_section": "Tool usage policy"
            })

        # Failed sessions
        if metrics['failed_sessions'] > metrics['successful_sessions'] * 0.2:
            recommendations.append({
                "priority": "HIGH",
                "category": "Success Rate",
                "issue": f"{metrics['failed_sessions']} failed sessions out of {metrics['total_sessions']} total",
                "recommendation": "Analyze failure modes and add preventive guidance to prompts. Consider adding error recovery patterns.",
                "prompt_section": "Error Handling"
            })

        return recommendations

    def generate_communication_recommendations(self, logs: List[Dict[str, Any]], metrics: Dict[str, Any]) -> List[str]:
        """Generate recommendations for human to improve communication with jib"""
        recommendations = []

        # High iteration sessions might indicate unclear requirements
        if metrics['avg_iterations'] > 2:
            recommendations.append({
                "priority": "MEDIUM",
                "category": "Requirement Clarity",
                "issue": f"Average {metrics['avg_iterations']:.1f} iterations per task",
                "recommendation": "When assigning tasks, include: (1) Clear success criteria, (2) Examples of expected output, (3) Constraints and preferences upfront",
                "example": "Instead of: 'Add OAuth2'\nTry: 'Add OAuth2 using the pattern in auth_service.py, support Google and GitHub providers, include tests similar to test_auth_basic.py'"
            })

        # Analyze blocked sessions
        if metrics['blocked_sessions'] > 0:
            blocked_logs = [l for l in logs if l.get('outcome', {}).get('status') == 'blocked']
            if blocked_logs:
                recommendations.append({
                    "priority": "HIGH",
                    "category": "Blocked Sessions",
                    "issue": f"{metrics['blocked_sessions']} sessions were blocked",
                    "recommendation": "Review blocked session notes to identify common blockers. Consider providing more context upfront or setting up additional access/tools.",
                    "details": f"Review logs: {', '.join([l['session_id'] for l in blocked_logs[:3]])}"
                })

        # Long duration might indicate complex tasks that need breaking down
        if metrics['avg_duration_minutes'] > 30:
            recommendations.append({
                "priority": "LOW",
                "category": "Task Scoping",
                "issue": f"Average session duration is {metrics['avg_duration_minutes']:.1f} minutes",
                "recommendation": "Consider breaking larger tasks into smaller, focused sub-tasks. This allows for incremental progress and easier review.",
                "example": "Instead of: 'Refactor the entire authentication system'\nTry: 'Step 1: Extract OAuth logic into separate module' (then review), 'Step 2: Add tests for extracted module', etc."
            })

        return recommendations

    def generate_report(self, logs: List[Dict[str, Any]], metrics: Dict[str, Any], patterns: Dict[str, Any],
                       prompt_recs: List[Dict], comm_recs: List[Dict]) -> str:
        """Generate markdown report"""
        # Pre-format pattern lists to avoid f-string complexity
        high_quality_text = '\n'.join('- ' + p for p in patterns['high_quality_patterns']) if patterns['high_quality_patterns'] else '- No high quality sessions in this period'
        low_quality_text = '\n'.join('- ' + p for p in patterns['low_quality_patterns']) if patterns['low_quality_patterns'] else '- No low quality sessions in this period'
        efficient_text = '\n'.join('- ' + p for p in patterns['efficient_patterns']) if patterns['efficient_patterns'] else '- No single-iteration sessions in this period'
        inefficient_text = '\n'.join('- ' + p for p in patterns['inefficient_patterns']) if patterns['inefficient_patterns'] else '- No multi-iteration sessions in this period'

        report = f"""# jib Conversation Analysis Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Period: Last {self.days} days

## Summary Metrics

- **Total Sessions**: {metrics['total_sessions']}
- **Success Rate**: {metrics['successful_sessions']/metrics['total_sessions']*100:.1f}% ({metrics['successful_sessions']}/{metrics['total_sessions']})
- **Single-Iteration Success Rate**: {metrics['single_iteration_success_rate']:.1f}%
- **Average Quality Score**: {metrics['avg_quality_score']:.1f}/10
- **Average Iterations**: {metrics['avg_iterations']:.1f}
- **Average Duration**: {metrics['avg_duration_minutes']:.1f} minutes
- **Average Messages**: {metrics['avg_messages_per_session']:.1f} per session
- **Average Tool Calls**: {metrics['avg_tool_calls_per_session']:.1f} per session

### Outcome Distribution
- ✓ Successful: {metrics['successful_sessions']}
- ⚠ Partial: {metrics['partial_sessions']}
- ✗ Failed: {metrics['failed_sessions']}
- ⊗ Blocked: {metrics['blocked_sessions']}

## Identified Patterns

### High Quality Sessions (8-10)
{high_quality_text}

### Low Quality Sessions (1-5)
{low_quality_text}

### Efficient Sessions (1 iteration)
{efficient_text}

### Inefficient Sessions (3+ iterations)
{inefficient_text}

## Prompt Tuning Recommendations

{self._format_recommendations(prompt_recs) if prompt_recs else '*No recommendations at this time*'}

## Communication Improvement Suggestions

{self._format_recommendations(comm_recs) if comm_recs else '*No suggestions at this time*'}

## Next Steps

1. **Review HIGH priority recommendations** and update Claude prompts accordingly
2. **Apply communication improvements** in next task assignment
3. **Re-run analysis** after {self.days} days to measure impact
4. **Review individual logs** for specific patterns:
   - Highest quality: {self._get_top_sessions(logs, 'quality_score', 3)}
   - Most efficient: {self._get_top_sessions(logs, 'iterations', 3, reverse=True)}

---

*Logs analyzed: {len(logs)} sessions*
*Report saved to: ~/sharing/analysis/*
"""
        return report

    def _format_recommendations(self, recommendations: List[Dict]) -> str:
        """Format recommendations as markdown"""
        if not recommendations:
            return "*No recommendations*"

        formatted = []
        for i, rec in enumerate(recommendations, 1):
            # Build optional sections
            prompt_section = f"**Prompt Section**: `{rec['prompt_section']}`" if 'prompt_section' in rec else ''
            example_section = f"**Example**:\n```\n{rec['example']}\n```" if 'example' in rec else ''
            details_section = f"**Details**: {rec['details']}" if 'details' in rec else ''

            formatted.append(f"""### {i}. [{rec['priority']}] {rec['category']}

**Issue**: {rec['issue']}

**Recommendation**: {rec['recommendation']}

{prompt_section}
{example_section}
{details_section}
""")
        return '\n'.join(formatted)

    def _get_top_sessions(self, logs: List[Dict[str, Any]], metric: str, n: int = 3, reverse: bool = False) -> str:
        """Get top N sessions by a metric"""
        def get_metric_value(log):
            if metric == 'quality_score':
                return log.get('outcome', {}).get('quality_score', 0) or 0
            elif metric == 'iterations':
                return log.get('outcome', {}).get('iterations', 999) or 999
            return 0

        sorted_logs = sorted(logs, key=get_metric_value, reverse=not reverse)
        top = sorted_logs[:n]

        if not top:
            return "None"

        return ', '.join([f"{l['session_id']} ({l['task_description'][:30]}...)" for l in top])

    def run_analysis(self) -> str:
        """Run full analysis and generate report"""
        print(f"Loading conversation logs from last {self.days} days...")
        logs = self.load_logs()

        if not logs:
            print("WARNING: No logs found for analysis", file=sys.stderr)
            return None

        print(f"Loaded {len(logs)} conversation logs")

        print("Calculating metrics...")
        metrics = self.calculate_metrics(logs)

        print("Identifying patterns...")
        patterns = self.identify_patterns(logs)

        print("Generating prompt recommendations...")
        prompt_recs = self.generate_prompt_recommendations(logs, metrics, patterns)

        print("Generating communication recommendations...")
        comm_recs = self.generate_communication_recommendations(logs, metrics)

        print("Generating report...")
        report = self.generate_report(logs, metrics, patterns, prompt_recs, comm_recs)

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_file = self.analysis_dir / f"analysis-{timestamp}.md"
        with open(report_file, 'w') as f:
            f.write(report)

        # Save recommendations as JSON for programmatic access
        recs_file = self.analysis_dir / f"recommendations-{timestamp}.json"
        with open(recs_file, 'w') as f:
            json.dump({
                "timestamp": timestamp,
                "metrics": metrics,
                "patterns": patterns,
                "prompt_recommendations": prompt_recs,
                "communication_recommendations": comm_recs
            }, f, indent=2)

        # Create latest symlinks
        latest_report = self.analysis_dir / "latest-report.md"
        latest_recs = self.analysis_dir / "latest-recommendations.json"

        if latest_report.exists():
            latest_report.unlink()
        if latest_recs.exists():
            latest_recs.unlink()

        latest_report.symlink_to(report_file.name)
        latest_recs.symlink_to(recs_file.name)

        print(f"\n✓ Analysis complete!")
        print(f"  Report: {report_file}")
        print(f"  Recommendations: {recs_file}")
        print(f"  Latest: {latest_report}")

        # Send notification to Slack if there are recommendations
        if prompt_recs or comm_recs:
            self.send_notification(metrics, len(prompt_recs), len(comm_recs), report_file, report)

        return report

    def send_notification(self, metrics: Dict[str, Any], prompt_rec_count: int, comm_rec_count: int, report_file: Path, full_report: str):
        """Send notification about analysis results via Slack with threading"""
        notification_dir = Path.home() / ".jib-sharing" / "notifications"
        notification_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_id = f"{timestamp}-conversation-analysis"

        # Determine priority based on recommendations
        total_recs = prompt_rec_count + comm_rec_count
        if total_recs >= 5:
            priority = "HIGH"
        elif total_recs >= 2:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        # Create short summary notification (top-level message)
        summary_file = notification_dir / f"{task_id}.md"
        summary = f"""# 📊 Conversation Analysis Complete

**Priority**: {priority} | {metrics['total_sessions']} conversations analyzed | {total_recs} recommendations

**Quick Stats:**
- ✅ Success: {metrics['successful_sessions']} | ❌ Failed: {metrics['failed_sessions']} | 🚫 Blocked: {metrics['blocked_sessions']}
- Quality: {metrics['avg_quality_score']:.1f}/10 | Single-iteration success: {metrics['single_iteration_success_rate']:.1f}%
- 🎯 Prompt improvements: {prompt_rec_count} | 💬 Communication improvements: {comm_rec_count}

📄 Full report in thread below
"""

        with open(summary_file, 'w') as f:
            f.write(summary)

        print(f"  Summary notification: {summary_file}")

        # Create detailed report (thread reply)
        detail_file = notification_dir / f"RESPONSE-{task_id}.md"
        detail = f"""# Full Conversation Analysis Report

## Session Outcomes
- ✅ Successful: {metrics['successful_sessions']}
- ❌ Failed: {metrics['failed_sessions']}
- 🚫 Blocked: {metrics['blocked_sessions']}
- ⚠️ Partial: {metrics['partial_sessions']}

## Performance Metrics
- Average iterations: {metrics['avg_iterations']:.1f}
- Average quality score: {metrics['avg_quality_score']:.1f}/10
- Single-iteration success rate: {metrics['single_iteration_success_rate']:.1f}%
- Average duration: {metrics['avg_duration_minutes']:.1f} minutes
- Average messages: {metrics['avg_messages_per_session']:.1f} per session

## Recommendations
- 🎯 Prompt improvements: {prompt_rec_count}
- 💬 Communication improvements: {comm_rec_count}

---

{full_report}

---

**Report Location**: `{report_file}`
"""

        with open(detail_file, 'w') as f:
            f.write(detail)

        print(f"  Detailed report (thread): {detail_file}")


def main():
    parser = argparse.ArgumentParser(description="Analyze jib conversation logs")
    parser.add_argument('--days', type=int, default=7, help='Number of days to analyze (default: 7)')
    parser.add_argument('--output', type=Path, help='Output directory (default: ~/sharing/analysis)')
    parser.add_argument('--print', action='store_true', help='Print report to stdout')

    args = parser.parse_args()

    analyzer = ConversationAnalyzer(days=args.days)

    if args.output:
        analyzer.analysis_dir = args.output
        analyzer.analysis_dir.mkdir(parents=True, exist_ok=True)

    report = analyzer.run_analysis()

    if args.print and report:
        print("\n" + "="*80)
        print(report)
        print("="*80)


if __name__ == '__main__':
    main()
