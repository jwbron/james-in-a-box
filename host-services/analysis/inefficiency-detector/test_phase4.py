#!/usr/bin/env python3
"""
Tests for Phase 4: Self-Improvement Loop Components

Tests cover:
- Proposal schema serialization/deserialization
- Improvement proposer template generation
- Impact tracker measurement and tracking
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from impact_tracker import ImpactMeasurement, ImpactReport, ImpactTracker
from improvement_proposer import PROPOSAL_TEMPLATES, ImprovementProposer
from inefficiency_schema import (
    AggregateInefficiencyReport,
    DetectedInefficiency,
    InefficiencyCategory,
    SessionInefficiencyReport,
    Severity,
)
from proposal_schema import (
    ImprovementProposal,
    ProposalBatch,
    ProposalCategory,
    ProposalPriority,
    ProposalStatus,
    ProposedChange,
)


class TestProposalSchema(unittest.TestCase):
    """Tests for proposal_schema.py data structures."""

    def test_proposed_change_serialization(self):
        """Test ProposedChange to_dict and from_dict."""
        change = ProposedChange(
            file_path="CLAUDE.md",
            section="Doing tasks",
            change_type="add",
            description="Add glob guidance",
            content="> Use glob patterns first",
        )

        data = change.to_dict()
        assert data["file_path"] == "CLAUDE.md"
        assert data["section"] == "Doing tasks"

        restored = ProposedChange.from_dict(data)
        assert restored.file_path == change.file_path
        assert restored.content == change.content

    def test_improvement_proposal_serialization(self):
        """Test ImprovementProposal to_dict and from_dict."""
        proposal = ImprovementProposal(
            proposal_id="prop-20251201-001",
            created_at=datetime(2025, 12, 1, 10, 0, 0),
            category=ProposalCategory.PROMPT_REFINEMENT,
            priority=ProposalPriority.HIGH,
            status=ProposalStatus.PENDING,
            title="Tool Discovery Guidance",
            description="Add guidance for glob patterns",
            rationale="34 documentation misses detected",
            occurrences_count=34,
            total_wasted_tokens=5000,
            expected_token_savings=2500,
            expected_improvement_percent=50.0,
            changes=[
                ProposedChange(
                    file_path="CLAUDE.md",
                    section="Doing tasks",
                    change_type="add",
                    description="Add glob guidance",
                    content="> Use glob first",
                )
            ],
        )

        data = proposal.to_dict()
        assert data["proposal_id"] == "prop-20251201-001"
        assert data["category"] == "prompt_refinement"
        assert data["priority"] == "high"
        assert data["status"] == "pending"
        assert len(data["changes"]) == 1

        restored = ImprovementProposal.from_dict(data)
        assert restored.proposal_id == proposal.proposal_id
        assert restored.category == ProposalCategory.PROMPT_REFINEMENT
        assert restored.priority == ProposalPriority.HIGH
        assert len(restored.changes) == 1

    def test_proposal_batch_serialization(self):
        """Test ProposalBatch to_dict and from_dict."""
        batch = ProposalBatch(
            batch_id="batch-20251201",
            created_at=datetime(2025, 12, 1, 10, 0, 0),
            time_period="2025-11-25 to 2025-12-01",
        )

        proposal = ImprovementProposal(
            proposal_id="prop-20251201-001",
            created_at=datetime.now(),
            category=ProposalCategory.PROMPT_REFINEMENT,
            priority=ProposalPriority.HIGH,
            status=ProposalStatus.PENDING,
            title="Test Proposal",
            description="Test description",
            rationale="Test rationale",
            expected_token_savings=1000,
        )
        batch.add_proposal(proposal)

        data = batch.to_dict()
        assert data["batch_id"] == "batch-20251201"
        assert data["total_proposals"] == 1
        assert data["total_expected_savings"] == 1000

        restored = ProposalBatch.from_dict(data)
        assert restored.batch_id == batch.batch_id
        assert len(restored.proposals) == 1

    def test_proposal_markdown_generation(self):
        """Test ImprovementProposal.to_markdown()."""
        proposal = ImprovementProposal(
            proposal_id="prop-20251201-001",
            created_at=datetime.now(),
            category=ProposalCategory.PROMPT_REFINEMENT,
            priority=ProposalPriority.HIGH,
            status=ProposalStatus.PENDING,
            title="Test Proposal",
            description="Test description",
            rationale="Test rationale",
            occurrences_count=10,
            total_wasted_tokens=1000,
            expected_token_savings=500,
            expected_improvement_percent=50.0,
        )

        md = proposal.to_markdown()
        assert "Test Proposal" in md
        assert "HIGH" in md
        assert "prop-20251201-001" in md
        assert "500" in md  # expected savings


class TestImprovementProposer(unittest.TestCase):
    """Tests for improvement_proposer.py."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.proposer = ImprovementProposer(
            proposals_dir=Path(self.temp_dir),
            min_occurrences=2,  # Lower threshold for testing
            min_wasted_tokens=100,
        )

    def tearDown(self):
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_template_coverage(self):
        """Verify templates exist for common inefficiency types."""
        expected_templates = [
            "documentation_miss",
            "retry_storm",
            "redundant_read",
            "excessive_context",
        ]
        for template_key in expected_templates:
            assert template_key in PROPOSAL_TEMPLATES

    def test_generate_proposals_from_report(self):
        """Test proposal generation from an aggregate report."""
        # Create a mock aggregate report with inefficiencies
        report = AggregateInefficiencyReport(
            time_period="2025-11-25 to 2025-12-01",
            total_sessions=5,
            total_tokens=50000,
            total_wasted_tokens=5000,
            average_inefficiency_rate=10.0,
        )

        # Add session with documentation_miss inefficiencies
        session = SessionInefficiencyReport(
            session_id="sess-001",
            task_id="bd-001",
            total_tokens=10000,
            total_wasted_tokens=1000,
            inefficiency_rate=10.0,
        )

        for i in range(3):  # Create 3 occurrences
            ineff = DetectedInefficiency(
                category=InefficiencyCategory.TOOL_DISCOVERY,
                sub_category="documentation_miss",
                severity=Severity.MEDIUM,
                trace_event_ids=[f"ev-{i}"],
                session_id="sess-001",
                task_id="bd-001",
                token_cost=500,
                estimated_optimal_cost=200,
                wasted_tokens=300,
                wasted_percentage=60.0,
                description="Searched 3 times before success",
                recommendation="Use glob patterns",
            )
            session.add_inefficiency(ineff)

        report.add_session_report(session)
        report.compute_top_issues()

        # Generate proposals
        batch = self.proposer.generate_proposals(report)

        assert batch.total_proposals > 0
        assert batch.time_period == report.time_period

        # Check proposal was generated for documentation_miss
        doc_miss_proposals = [
            p for p in batch.proposals if "Tool Discovery" in p.title or "Glob" in p.title
        ]
        assert len(doc_miss_proposals) > 0

    def test_save_and_load_batch(self):
        """Test saving and loading proposal batches."""
        batch = ProposalBatch(
            batch_id="batch-test",
            created_at=datetime.now(),
            time_period="test period",
        )
        proposal = ImprovementProposal(
            proposal_id="prop-test-001",
            created_at=datetime.now(),
            category=ProposalCategory.PROMPT_REFINEMENT,
            priority=ProposalPriority.MEDIUM,
            status=ProposalStatus.PENDING,
            title="Test",
            description="Test",
            rationale="Test",
            expected_token_savings=100,
        )
        batch.add_proposal(proposal)

        # Save
        filepath = self.proposer.save_batch(batch)
        assert filepath.exists()

        # Load
        loaded = self.proposer.load_batch("batch-test")
        assert loaded is not None
        assert loaded.batch_id == batch.batch_id
        assert len(loaded.proposals) == 1

    def test_update_proposal_status(self):
        """Test updating proposal status."""
        batch = ProposalBatch(
            batch_id="batch-status-test",
            created_at=datetime.now(),
            time_period="test",
        )
        proposal = ImprovementProposal(
            proposal_id="prop-status-001",
            created_at=datetime.now(),
            category=ProposalCategory.PROMPT_REFINEMENT,
            priority=ProposalPriority.MEDIUM,
            status=ProposalStatus.PENDING,
            title="Test",
            description="Test",
            rationale="Test",
            expected_token_savings=100,
        )
        batch.add_proposal(proposal)
        self.proposer.save_batch(batch)

        # Update status
        success = self.proposer.update_proposal_status(
            "prop-status-001",
            ProposalStatus.APPROVED,
            reviewed_by="test_user",
            review_notes="LGTM",
        )
        assert success

        # Verify
        loaded = self.proposer.load_batch("batch-status-test")
        assert loaded.proposals[0].status == ProposalStatus.APPROVED
        assert loaded.proposals[0].reviewed_by == "test_user"

    def test_slack_summary_generation(self):
        """Test Slack summary generation."""
        batch = ProposalBatch(
            batch_id="batch-slack-test",
            created_at=datetime.now(),
            time_period="2025-11-25 to 2025-12-01",
        )
        proposal = ImprovementProposal(
            proposal_id="prop-slack-001",
            created_at=datetime.now(),
            category=ProposalCategory.PROMPT_REFINEMENT,
            priority=ProposalPriority.HIGH,
            status=ProposalStatus.PENDING,
            title="High Priority Fix",
            description="Important fix",
            rationale="Evidence",
            occurrences_count=10,
            total_wasted_tokens=5000,
            expected_token_savings=2500,
        )
        batch.add_proposal(proposal)

        summary = self.proposer.generate_slack_summary(batch)

        assert "Improvement Proposals" in summary
        assert "High Priority" in summary
        assert "prop-slack-001" in summary
        assert "approve" in summary.lower()
        assert "reject" in summary.lower()


class TestImpactTracker(unittest.TestCase):
    """Tests for impact_tracker.py."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.tracking_dir = Path(self.temp_dir) / "impact"
        self.proposals_dir = Path(self.temp_dir) / "proposals"
        self.tracking_dir.mkdir(parents=True)
        self.proposals_dir.mkdir(parents=True)

        self.tracker = ImpactTracker(
            tracking_dir=self.tracking_dir,
            proposals_dir=self.proposals_dir,
            measurement_delay_days=7,
        )

        # Create a proposal batch for testing
        batch = ProposalBatch(
            batch_id="batch-impact-test",
            created_at=datetime.now(),
            time_period="test",
        )
        self.test_proposal = ImprovementProposal(
            proposal_id="prop-impact-001",
            created_at=datetime.now(),
            category=ProposalCategory.PROMPT_REFINEMENT,
            priority=ProposalPriority.HIGH,
            status=ProposalStatus.APPROVED,
            title="Test Proposal",
            description="Test",
            rationale="Test",
            occurrences_count=10,
            total_wasted_tokens=1000,
            expected_token_savings=500,
            source_inefficiencies=["sess-001:ev-001"],
        )
        batch.add_proposal(self.test_proposal)

        with open(self.proposals_dir / "batch-impact-test.json", "w") as f:
            json.dump(batch.to_dict(), f)

    def tearDown(self):
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_mark_implemented(self):
        """Test marking a proposal as implemented."""
        success = self.tracker.mark_implemented(
            "prop-impact-001",
            "https://github.com/test/repo/pull/1",
            datetime.now(),
        )
        assert success

        # Verify tracking entry created
        tracking_file = self.tracking_dir / "tracking-prop-impact-001.json"
        assert tracking_file.exists()

        with open(tracking_file) as f:
            entry = json.load(f)

        assert entry["proposal_id"] == "prop-impact-001"
        assert entry["expected_savings"] == 500
        assert not entry["measured"]

    def test_get_proposals_due_for_measurement(self):
        """Test getting proposals due for measurement."""
        # Mark as implemented with past date
        past_date = datetime.now() - timedelta(days=10)
        self.tracker.mark_implemented(
            "prop-impact-001",
            "https://github.com/test/repo/pull/1",
            past_date,
        )

        due = self.tracker.get_proposals_due_for_measurement()
        assert len(due) == 1
        assert due[0]["proposal_id"] == "prop-impact-001"

    def test_record_measurement(self):
        """Test recording an impact measurement."""
        self.tracker.mark_implemented(
            "prop-impact-001",
            "https://github.com/test/repo/pull/1",
        )

        measurement = self.tracker.record_measurement(
            "prop-impact-001",
            measured_occurrences=5,
            measured_wasted_tokens=500,
            notes="50% reduction observed",
        )

        assert measurement is not None
        assert measurement.token_savings == 500  # 1000 - 500
        assert measurement.occurrence_reduction == 5  # 10 - 5
        assert measurement.savings_ratio == 1.0  # 500 / 500 expected

    def test_impact_measurement_serialization(self):
        """Test ImpactMeasurement serialization."""
        measurement = ImpactMeasurement(
            proposal_id="prop-001",
            measurement_date=datetime.now(),
            baseline_occurrences=10,
            baseline_wasted_tokens=1000,
            measured_occurrences=5,
            measured_wasted_tokens=400,
            occurrence_reduction=5,
            token_savings=600,
            improvement_percent=60.0,
            expected_savings=500,
            savings_ratio=1.2,
            notes="Good improvement",
        )

        data = measurement.to_dict()
        restored = ImpactMeasurement.from_dict(data)

        assert restored.proposal_id == measurement.proposal_id
        assert restored.token_savings == 600
        assert restored.savings_ratio == 1.2

    def test_impact_report_generation(self):
        """Test impact report generation."""
        # Mark and measure
        self.tracker.mark_implemented(
            "prop-impact-001",
            "https://github.com/test/repo/pull/1",
        )
        self.tracker.record_measurement(
            "prop-impact-001",
            measured_occurrences=3,
            measured_wasted_tokens=300,
        )

        # Generate report
        report = self.tracker.generate_impact_report("Test Period")

        assert report.total_proposals_tracked == 1
        assert report.total_actual_savings > 0

    def test_impact_report_markdown(self):
        """Test ImpactReport.to_markdown()."""
        report = ImpactReport(
            report_date=datetime.now(),
            time_period="Test Period",
        )

        measurement = ImpactMeasurement(
            proposal_id="prop-001",
            measurement_date=datetime.now(),
            baseline_occurrences=10,
            baseline_wasted_tokens=1000,
            measured_occurrences=5,
            measured_wasted_tokens=400,
            occurrence_reduction=5,
            token_savings=600,
            improvement_percent=60.0,
            expected_savings=500,
            savings_ratio=1.2,
        )
        report.add_measurement(measurement)

        md = report.to_markdown()
        assert "Impact Report" in md
        assert "prop-001" in md
        assert "600" in md  # token savings

    def test_implementation_summary(self):
        """Test getting implementation summary."""
        self.tracker.mark_implemented(
            "prop-impact-001",
            "https://github.com/test/repo/pull/1",
        )

        summary = self.tracker.get_implementation_summary()

        assert summary["total_implemented"] == 1
        assert summary["awaiting_measurement"] == 1
        assert summary["measured"] == 0


class TestPriorityCalculation(unittest.TestCase):
    """Tests for proposal priority calculation."""

    def test_high_priority_threshold(self):
        """Test that high savings result in HIGH priority."""
        proposer = ImprovementProposer(min_occurrences=1, min_wasted_tokens=0)

        # Create report with high waste
        report = AggregateInefficiencyReport(
            time_period="test",
            total_sessions=1,
            total_tokens=100000,
            total_wasted_tokens=10000,
            average_inefficiency_rate=10.0,
        )

        session = SessionInefficiencyReport(
            session_id="sess-001",
            task_id=None,
            total_tokens=100000,
            total_wasted_tokens=10000,
            inefficiency_rate=10.0,
        )

        # Add many occurrences to generate high expected savings
        for i in range(20):
            ineff = DetectedInefficiency(
                category=InefficiencyCategory.TOOL_EXECUTION,
                sub_category="retry_storm",
                severity=Severity.HIGH,
                trace_event_ids=[f"ev-{i}"],
                session_id="sess-001",
                task_id=None,
                token_cost=500,
                estimated_optimal_cost=100,
                wasted_tokens=400,
                wasted_percentage=80.0,
                description="Test retry storm",
                recommendation="Test recommendation",
            )
            session.add_inefficiency(ineff)

        report.add_session_report(session)
        report.compute_top_issues()

        batch = proposer.generate_proposals(report)

        # Should have at least one HIGH priority proposal
        high_priority = [p for p in batch.proposals if p.priority == ProposalPriority.HIGH]
        assert len(high_priority) > 0


if __name__ == "__main__":
    unittest.main()
