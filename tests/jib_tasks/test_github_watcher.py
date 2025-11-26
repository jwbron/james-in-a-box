"""
Tests for the GitHub watcher module.

Tests the GitHub PR check watcher:
- State management (load/save)
- Check file processing
- Failure analysis
- PR context extraction
"""

import json
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch


# Load github watcher module
watcher_path = (
    Path(__file__).parent.parent.parent / "jib-container" / "jib-tasks" / "github" / "watcher.py"
)
loader = SourceFileLoader("github_watcher", str(watcher_path))
github_watcher = loader.load_module()

GitHubWatcher = github_watcher.GitHubWatcher


class TestGitHubWatcherInit:
    """Tests for watcher initialization."""

    def test_init_paths(self, temp_dir, monkeypatch):
        """Test that paths are initialized correctly."""
        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()

            assert watcher.github_dir == temp_dir / "context-sync" / "github"
            assert watcher.checks_dir == temp_dir / "context-sync" / "github" / "checks"
            assert watcher.prs_dir == temp_dir / "context-sync" / "github" / "prs"
            assert watcher.notifications_dir == temp_dir / "sharing" / "notifications"
            assert watcher.beads_dir == temp_dir / "beads"


class TestStateManagement:
    """Tests for state load/save."""

    def test_load_state_no_file(self, temp_dir):
        """Test loading state when file doesn't exist."""
        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()
            state = watcher.load_state()

            assert state == {"notified": {}}

    def test_load_state_valid_file(self, temp_dir):
        """Test loading state from existing file."""
        state_file = temp_dir / "sharing" / "tracking" / "github-watcher-state.json"
        state_file.parent.mkdir(parents=True)
        state_file.write_text(
            json.dumps({"notified": {"repo-123:check1,check2": "2025-01-01T00:00:00Z"}})
        )

        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()
            state = watcher.load_state()

            assert "repo-123:check1,check2" in state["notified"]

    def test_load_state_invalid_json(self, temp_dir):
        """Test loading state when file contains invalid JSON."""
        state_file = temp_dir / "sharing" / "tracking" / "github-watcher-state.json"
        state_file.parent.mkdir(parents=True)
        state_file.write_text("invalid json{")

        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()
            state = watcher.load_state()

            assert state == {"notified": {}}

    def test_save_state(self, temp_dir):
        """Test saving state to file."""
        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()
            watcher.notified_failures = {"test-key": "2025-01-01T00:00:00Z"}
            watcher.save_state()

            # Verify state was saved
            state_file = temp_dir / "sharing" / "tracking" / "github-watcher-state.json"
            assert state_file.exists()

            saved = json.loads(state_file.read_text())
            assert saved["notified"]["test-key"] == "2025-01-01T00:00:00Z"


class TestAnalyzeFailure:
    """Tests for failure analysis."""

    def test_analyze_test_failure(self, temp_dir):
        """Test analyzing test failures."""
        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()

            pr_context = {"files_changed": ["src/app.py"]}
            failed_checks = [{"name": "pytest", "full_log": "AssertionError: expected 5, got 3"}]

            analysis = watcher.analyze_failure(pr_context, failed_checks)

            assert "test" in analysis["summary"].lower()
            assert analysis["root_cause"] is not None
            assert len(analysis["actions"]) > 0

    def test_analyze_lint_failure(self, temp_dir):
        """Test analyzing linting failures."""
        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()

            pr_context = {"files_changed": ["src/app.js"]}
            failed_checks = [{"name": "eslint", "full_log": "Missing semicolon"}]

            analysis = watcher.analyze_failure(pr_context, failed_checks)

            assert "lint" in analysis["summary"].lower() or "quality" in analysis["summary"].lower()
            assert analysis["can_auto_fix"] is True
            assert analysis["auto_fix_description"] is not None

    def test_analyze_build_failure(self, temp_dir):
        """Test analyzing build failures."""
        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()

            pr_context = {}
            failed_checks = [{"name": "build", "full_log": "Compilation error: syntax error"}]

            analysis = watcher.analyze_failure(pr_context, failed_checks)

            assert "build" in analysis["summary"].lower()
            assert analysis["can_auto_fix"] is False

    def test_analyze_import_error(self, temp_dir):
        """Test analyzing import/module errors."""
        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()

            pr_context = {}
            failed_checks = [
                {"name": "test", "full_log": 'ModuleNotFoundError: No module named "foo"'}
            ]

            analysis = watcher.analyze_failure(pr_context, failed_checks)

            assert (
                "missing dependency" in analysis["root_cause"].lower()
                or "import" in analysis["root_cause"].lower()
            )
            assert any(
                "requirements" in action.lower() or "dependencies" in action.lower()
                for action in analysis["actions"]
            )

    def test_analyze_unknown_failure(self, temp_dir):
        """Test analyzing unknown failure types."""
        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()

            pr_context = {}
            failed_checks = [{"name": "custom-check", "full_log": "Something went wrong"}]

            analysis = watcher.analyze_failure(pr_context, failed_checks)

            assert "failed" in analysis["summary"].lower()
            assert len(analysis["actions"]) > 0


class TestGetPrContext:
    """Tests for PR context extraction."""

    def test_get_pr_context_no_files(self, temp_dir):
        """Test getting context when no PR files exist."""
        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()
            context = watcher.get_pr_context("test-repo", 123)

            assert context["pr_number"] == 123
            assert context["title"] == "PR #123"
            assert context["files_changed"] == []

    def test_get_pr_context_with_pr_file(self, temp_dir):
        """Test getting context from PR markdown file."""
        prs_dir = temp_dir / "context-sync" / "github" / "prs"
        prs_dir.mkdir(parents=True)

        pr_file = prs_dir / "test-repo-PR-123.md"
        pr_file.write_text("""# PR #123: Fix important bug

**URL**: https://github.com/owner/test-repo/pull/123
**Branch**: feature-branch → main

## Files Changed
- `src/app.py` (+10, -5)
- `tests/test_app.py` (+20, -0)
""")

        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()
            context = watcher.get_pr_context("test-repo", 123)

            assert "Fix important bug" in context["title"]
            assert "github.com" in context["url"]
            assert "feature-branch" in context["branch"]
            assert len(context["files_changed"]) == 2

    def test_get_pr_context_with_diff(self, temp_dir):
        """Test getting context includes diff availability."""
        prs_dir = temp_dir / "context-sync" / "github" / "prs"
        prs_dir.mkdir(parents=True)

        diff_file = prs_dir / "test-repo-PR-123.diff"
        diff_file.write_text("diff --git a/file.py b/file.py\n+new line")

        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()
            context = watcher.get_pr_context("test-repo", 123)

            assert context.get("diff_available") is True
            assert context.get("diff_size", 0) > 0


class TestProcessCheckFile:
    """Tests for check file processing."""

    def test_process_passing_checks(self, temp_dir):
        """Test processing when all checks pass."""
        checks_dir = temp_dir / "context-sync" / "github" / "checks"
        checks_dir.mkdir(parents=True)

        check_file = checks_dir / "repo-PR-123-checks.json"
        check_file.write_text(
            json.dumps(
                {
                    "pr_number": 123,
                    "repository": "owner/repo",
                    "checks": [
                        {"name": "test", "state": "SUCCESS"},
                        {"name": "lint", "state": "SUCCESS"},
                    ],
                }
            )
        )

        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()
            # Should not create notification for passing checks
            watcher.process_check_file(check_file)

            # No notification should be created
            notifications = list((temp_dir / "sharing" / "notifications").glob("*.md"))
            assert len(notifications) == 0

    def test_process_failing_checks_creates_notification(self, temp_dir):
        """Test processing creates notification for failures."""
        checks_dir = temp_dir / "context-sync" / "github" / "checks"
        checks_dir.mkdir(parents=True)
        notifications_dir = temp_dir / "sharing" / "notifications"
        notifications_dir.mkdir(parents=True)

        check_file = checks_dir / "repo-PR-123-checks.json"
        check_file.write_text(
            json.dumps(
                {
                    "pr_number": 123,
                    "repository": "owner/repo",
                    "checks": [{"name": "test", "state": "FAILURE"}],
                }
            )
        )

        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()

            with patch.object(watcher, "create_beads_task", return_value=None):
                watcher.process_check_file(check_file)

            # Notification should be created
            notifications = list(notifications_dir.glob("*pr-check-failed*.md"))
            assert len(notifications) == 1

    def test_no_duplicate_notification(self, temp_dir):
        """Test that same failures don't trigger duplicate notifications."""
        checks_dir = temp_dir / "context-sync" / "github" / "checks"
        checks_dir.mkdir(parents=True)
        notifications_dir = temp_dir / "sharing" / "notifications"
        notifications_dir.mkdir(parents=True)

        check_file = checks_dir / "repo-PR-123-checks.json"
        check_file.write_text(
            json.dumps(
                {
                    "pr_number": 123,
                    "repository": "owner/repo",
                    "checks": [{"name": "test", "state": "FAILURE"}],
                }
            )
        )

        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()

            with patch.object(watcher, "create_beads_task", return_value=None):
                # Process twice
                watcher.process_check_file(check_file)
                watcher.process_check_file(check_file)

            # Only one notification
            notifications = list(notifications_dir.glob("*pr-check-failed*.md"))
            assert len(notifications) == 1


class TestWatch:
    """Tests for the main watch loop."""

    def test_watch_no_checks_dir(self, temp_dir, capsys):
        """Test watch when checks directory doesn't exist."""
        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()
            watcher.watch()

        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_watch_processes_all_check_files(self, temp_dir):
        """Test watch processes all check files."""
        checks_dir = temp_dir / "context-sync" / "github" / "checks"
        checks_dir.mkdir(parents=True)

        # Create multiple check files
        for i in range(3):
            check_file = checks_dir / f"repo-PR-{i}-checks.json"
            check_file.write_text(
                json.dumps(
                    {
                        "pr_number": i,
                        "repository": "owner/repo",
                        "checks": [{"name": "test", "state": "SUCCESS"}],
                    }
                )
            )

        with patch.object(Path, "home", return_value=temp_dir):
            watcher = GitHubWatcher()

            with patch.object(watcher, "process_check_file") as mock_process:
                watcher.watch()

            # Should process all 3 files
            assert mock_process.call_count == 3
