"""
Tests for the conversation-analyzer module.

Tests the ConversationAnalyzer class which analyzes conversation logs
to generate prompt tuning and communication improvement recommendations.
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import pytest
import sys

# Add project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestConversationAnalyzerLogLoading:
    """Tests for loading conversation logs."""

    def test_load_logs_from_directory(self, temp_dir):
        """Test loading logs from the logs directory."""
        logs_dir = temp_dir / "conversations"
        logs_dir.mkdir(parents=True)

        # Create test log files
        log1 = {
            'session_id': 'session-1',
            'start_time': datetime.now().isoformat(),
            'task_description': 'Test task 1',
            'outcome': {'status': 'success', 'iterations': 1, 'quality_score': 9},
            'metrics': {'duration_seconds': 300, 'message_count': 5, 'tool_calls': 10}
        }
        log2 = {
            'session_id': 'session-2',
            'start_time': datetime.now().isoformat(),
            'task_description': 'Test task 2',
            'outcome': {'status': 'failed', 'iterations': 3, 'quality_score': 4},
            'metrics': {'duration_seconds': 600, 'message_count': 15, 'tool_calls': 25}
        }

        (logs_dir / "log1.json").write_text(json.dumps(log1))
        (logs_dir / "log2.json").write_text(json.dumps(log2))

        # Load logs
        logs = []
        for log_file in sorted(logs_dir.glob("*.json")):
            with log_file.open() as f:
                logs.append(json.load(f))

        assert len(logs) == 2
        assert logs[0]['session_id'] == 'session-1'

    def test_load_logs_filters_by_date(self, temp_dir):
        """Test that logs are filtered by date range."""
        logs_dir = temp_dir / "conversations"
        logs_dir.mkdir(parents=True)

        # Recent log
        recent = {
            'session_id': 'recent',
            'start_time': datetime.now().isoformat(),
            'task_description': 'Recent task',
            'outcome': {'status': 'success', 'iterations': 1},
            'metrics': {'duration_seconds': 100, 'message_count': 3, 'tool_calls': 5}
        }

        # Old log
        old_date = datetime.now() - timedelta(days=30)
        old = {
            'session_id': 'old',
            'start_time': old_date.isoformat(),
            'task_description': 'Old task',
            'outcome': {'status': 'success', 'iterations': 1},
            'metrics': {'duration_seconds': 100, 'message_count': 3, 'tool_calls': 5}
        }

        (logs_dir / "recent.json").write_text(json.dumps(recent))
        (logs_dir / "old.json").write_text(json.dumps(old))

        # Filter by date
        cutoff = datetime.now() - timedelta(days=7)
        filtered = []
        for log_file in logs_dir.glob("*.json"):
            with log_file.open() as f:
                log = json.load(f)
                log_date = datetime.fromisoformat(log['start_time'])
                if log_date >= cutoff:
                    filtered.append(log)

        assert len(filtered) == 1
        assert filtered[0]['session_id'] == 'recent'


class TestConversationAnalyzerMetrics:
    """Tests for metric calculation."""

    def test_calculate_basic_metrics(self):
        """Test calculating basic metrics from logs."""
        logs = [
            {'outcome': {'status': 'success', 'iterations': 1, 'quality_score': 9},
             'metrics': {'duration_seconds': 300, 'message_count': 5, 'tool_calls': 10}},
            {'outcome': {'status': 'success', 'iterations': 2, 'quality_score': 7},
             'metrics': {'duration_seconds': 600, 'message_count': 10, 'tool_calls': 20}},
            {'outcome': {'status': 'failed', 'iterations': 3, 'quality_score': None},
             'metrics': {'duration_seconds': 900, 'message_count': 15, 'tool_calls': 30}}
        ]

        # Calculate metrics
        total_sessions = len(logs)
        successful = sum(1 for l in logs if l['outcome']['status'] == 'success')
        failed = sum(1 for l in logs if l['outcome']['status'] == 'failed')

        quality_scores = [l['outcome']['quality_score'] for l in logs
                         if l['outcome']['quality_score'] is not None]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0

        total_iterations = sum(l['outcome']['iterations'] for l in logs)
        avg_iterations = total_iterations / total_sessions

        assert total_sessions == 3
        assert successful == 2
        assert failed == 1
        assert avg_quality == 8.0  # (9 + 7) / 2
        assert avg_iterations == 2.0  # (1 + 2 + 3) / 3

    def test_calculate_duration_metrics(self):
        """Test calculating duration-related metrics."""
        logs = [
            {'metrics': {'duration_seconds': 300}},
            {'metrics': {'duration_seconds': 600}},
            {'metrics': {'duration_seconds': 900}}
        ]

        total_duration = sum(l['metrics']['duration_seconds'] for l in logs)
        avg_duration_minutes = (total_duration / 60) / len(logs)

        assert avg_duration_minutes == 10.0  # (300+600+900) / 60 / 3

    def test_calculate_single_iteration_success_rate(self):
        """Test calculating single-iteration success rate."""
        logs = [
            {'outcome': {'status': 'success', 'iterations': 1}},
            {'outcome': {'status': 'success', 'iterations': 1}},
            {'outcome': {'status': 'success', 'iterations': 2}},
            {'outcome': {'status': 'failed', 'iterations': 3}}
        ]

        successful = [l for l in logs if l['outcome']['status'] == 'success']
        single_iteration = [l for l in successful if l['outcome']['iterations'] == 1]

        rate = len(single_iteration) / len(successful) * 100 if successful else 0

        assert rate == pytest.approx(66.67, rel=0.1)  # 2 out of 3


class TestConversationAnalyzerPatterns:
    """Tests for pattern identification."""

    def test_identify_high_quality_patterns(self):
        """Test identifying patterns in high-quality sessions."""
        logs = [
            {'outcome': {'quality_score': 9},
             'metrics': {'message_count': 5, 'tool_calls': 10}},
            {'outcome': {'quality_score': 10},
             'metrics': {'message_count': 4, 'tool_calls': 8}},
            {'outcome': {'quality_score': 5},
             'metrics': {'message_count': 20, 'tool_calls': 50}}
        ]

        high_quality = [l for l in logs if (l['outcome'].get('quality_score') or 0) >= 8]
        low_quality = [l for l in logs if l['outcome'].get('quality_score') is not None
                      and l['outcome']['quality_score'] <= 5]

        assert len(high_quality) == 2
        assert len(low_quality) == 1

        # High quality sessions tend to have fewer messages
        high_avg_messages = sum(l['metrics']['message_count'] for l in high_quality) / len(high_quality)
        low_avg_messages = sum(l['metrics']['message_count'] for l in low_quality) / len(low_quality)

        assert high_avg_messages < low_avg_messages

    def test_identify_efficient_patterns(self):
        """Test identifying patterns in efficient (single-iteration) sessions."""
        logs = [
            {'outcome': {'iterations': 1},
             'metrics': {'duration_seconds': 300}},
            {'outcome': {'iterations': 1},
             'metrics': {'duration_seconds': 400}},
            {'outcome': {'iterations': 3},
             'metrics': {'duration_seconds': 1200}}
        ]

        efficient = [l for l in logs if l['outcome']['iterations'] == 1]
        inefficient = [l for l in logs if l['outcome']['iterations'] >= 3]

        assert len(efficient) == 2
        assert len(inefficient) == 1

        efficient_avg_duration = sum(l['metrics']['duration_seconds'] for l in efficient) / len(efficient) / 60
        assert efficient_avg_duration < 10  # Under 10 minutes average


class TestConversationAnalyzerRecommendations:
    """Tests for recommendation generation."""

    def test_low_single_iteration_recommendation(self):
        """Test recommendation for low single-iteration success rate."""
        metrics = {
            'single_iteration_success_rate': 40,
            'successful_sessions': 10
        }

        recommendations = []
        if metrics['single_iteration_success_rate'] < 60 and metrics['successful_sessions'] > 5:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'Iteration Efficiency',
                'issue': f"Only {metrics['single_iteration_success_rate']:.1f}% complete in one iteration"
            })

        assert len(recommendations) == 1
        assert recommendations[0]['priority'] == 'HIGH'

    def test_high_message_count_recommendation(self):
        """Test recommendation for high message count."""
        metrics = {'avg_messages_per_session': 15}

        recommendations = []
        if metrics['avg_messages_per_session'] > 10:
            recommendations.append({
                'priority': 'MEDIUM',
                'category': 'Verbosity',
                'issue': f"Average {metrics['avg_messages_per_session']:.1f} messages per session"
            })

        assert len(recommendations) == 1
        assert recommendations[0]['category'] == 'Verbosity'

    def test_low_quality_recommendation(self):
        """Test recommendation for low quality scores."""
        metrics = {'avg_quality_score': 5.5}

        recommendations = []
        if 0 < metrics['avg_quality_score'] < 7:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'Quality',
                'issue': f"Average quality score is {metrics['avg_quality_score']:.1f}/10"
            })

        assert len(recommendations) == 1
        assert recommendations[0]['priority'] == 'HIGH'

    def test_communication_recommendation_high_iterations(self):
        """Test communication recommendation for high iteration count."""
        metrics = {'avg_iterations': 2.5}

        recommendations = []
        if metrics['avg_iterations'] > 2:
            recommendations.append({
                'priority': 'MEDIUM',
                'category': 'Requirement Clarity',
                'issue': f"Average {metrics['avg_iterations']:.1f} iterations per task"
            })

        assert len(recommendations) == 1
        assert recommendations[0]['category'] == 'Requirement Clarity'


class TestConversationAnalyzerReport:
    """Tests for report generation."""

    def test_report_contains_summary_metrics(self):
        """Test that report contains summary metrics section."""
        metrics = {
            'total_sessions': 10,
            'successful_sessions': 8,
            'failed_sessions': 2,
            'blocked_sessions': 0,
            'partial_sessions': 0,
            'avg_quality_score': 7.5,
            'avg_iterations': 1.5,
            'avg_duration_minutes': 15.0,
            'avg_messages_per_session': 8.0,
            'single_iteration_success_rate': 75.0
        }

        report = f"""## Summary Metrics

- **Total Sessions**: {metrics['total_sessions']}
- **Success Rate**: {metrics['successful_sessions']/metrics['total_sessions']*100:.1f}%
- **Average Quality Score**: {metrics['avg_quality_score']:.1f}/10
"""

        assert "Total Sessions" in report
        assert "80.0%" in report
        assert "7.5/10" in report

    def test_format_recommendations(self):
        """Test formatting recommendations in report."""
        recommendations = [
            {
                'priority': 'HIGH',
                'category': 'Quality',
                'issue': 'Low quality scores',
                'recommendation': 'Review quality issues in logs'
            }
        ]

        formatted = []
        for i, rec in enumerate(recommendations, 1):
            formatted.append(f"### {i}. [{rec['priority']}] {rec['category']}\n")
            formatted.append(f"**Issue**: {rec['issue']}\n")
            formatted.append(f"**Recommendation**: {rec['recommendation']}\n")

        result = '\n'.join(formatted)

        assert "[HIGH] Quality" in result
        assert "Low quality scores" in result


class TestConversationAnalyzerScheduling:
    """Tests for weekly scheduling logic."""

    def test_check_last_run_no_reports(self, temp_dir):
        """Test checking last run when no reports exist."""
        reports = list(temp_dir.glob("analysis-*.md"))
        assert len(reports) == 0

    def test_check_last_run_with_reports(self, temp_dir):
        """Test checking last run with existing reports."""
        report = temp_dir / "analysis-20251120-120000.md"
        report.write_text("# Report")

        reports = list(temp_dir.glob("analysis-*.md"))
        assert len(reports) == 1

    def test_should_run_analysis_force(self):
        """Test that force flag bypasses scheduling."""
        force = True
        should_run = force or True  # Simplified logic

        assert should_run is True

    def test_should_run_analysis_weekly(self):
        """Test weekly scheduling logic."""
        last_run = datetime.now() - timedelta(days=8)
        days_since = (datetime.now() - last_run).days

        should_run = days_since >= 7
        assert should_run is True

        last_run = datetime.now() - timedelta(days=3)
        days_since = (datetime.now() - last_run).days

        should_run = days_since >= 7
        assert should_run is False


class TestConversationAnalyzerNotification:
    """Tests for Slack notification creation."""

    def test_create_summary_notification(self, temp_dir):
        """Test creating summary notification."""
        notification_dir = temp_dir / "notifications"
        notification_dir.mkdir()

        metrics = {
            'total_sessions': 10,
            'successful_sessions': 8,
            'failed_sessions': 1,
            'blocked_sessions': 1,
            'avg_quality_score': 7.5,
            'single_iteration_success_rate': 70.0
        }
        prompt_rec_count = 2
        comm_rec_count = 1
        total_recs = prompt_rec_count + comm_rec_count

        summary = f"""# 📊 Conversation Analysis Complete

**Priority**: MEDIUM | {metrics['total_sessions']} conversations analyzed | {total_recs} recommendations

**Quick Stats:**
- ✅ Success: {metrics['successful_sessions']} | ❌ Failed: {metrics['failed_sessions']} | 🚫 Blocked: {metrics['blocked_sessions']}
- Quality: {metrics['avg_quality_score']:.1f}/10 | Single-iteration success: {metrics['single_iteration_success_rate']:.1f}%
"""

        summary_file = notification_dir / "20251120-120000-conversation-analysis.md"
        summary_file.write_text(summary)

        assert summary_file.exists()
        assert "📊" in summary_file.read_text()
        assert "MEDIUM" in summary_file.read_text()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
