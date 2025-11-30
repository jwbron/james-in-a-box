"""
Tests for the GitHub watcher host-side service.

Tests the GitHub Watcher host service:
- Configuration loading
- State management
- GitHub CLI integration
- Task invocation via jib --exec
"""

import json
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import MagicMock, patch


# Load github watcher module
watcher_path = (
    Path(__file__).parent.parent.parent
    / "host-services"
    / "analysis"
    / "github-watcher"
    / "github-watcher.py"
)
loader = SourceFileLoader("github_watcher", str(watcher_path))
github_watcher = loader.load_module()


class TestLoadConfig:
    """Tests for configuration loading."""

    def test_load_config_returns_dict(self, temp_dir):
        """Test loading config returns a dictionary."""
        config = github_watcher.load_config()
        # Should return a dict with at least writable_repos key
        assert isinstance(config, dict)
        assert "writable_repos" in config or config == {"writable_repos": []}

    def test_load_config_with_file(self, temp_dir):
        """Test loading config from file."""
        config_dir = temp_dir / "khan" / "james-in-a-box" / "config"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "repositories.yaml"
        config_file.write_text("""
writable_repos:
  - owner/repo1
  - owner/repo2
""")

        with patch.object(Path, "home", return_value=temp_dir):
            config = github_watcher.load_config()
            assert "owner/repo1" in config.get("writable_repos", [])
            assert "owner/repo2" in config.get("writable_repos", [])


class TestStateManagement:
    """Tests for state load/save."""

    def test_load_state_no_file(self, temp_dir):
        """Test loading state when file doesn't exist."""
        with patch.object(Path, "home", return_value=temp_dir):
            state = github_watcher.load_state()
            assert state == {
                "processed_failures": {},
                "processed_comments": {},
                "processed_reviews": {},
                "processed_conflicts": {},
                "last_run_start": None,
            }

    def test_load_state_with_file(self, temp_dir):
        """Test loading state from existing file."""
        state_dir = temp_dir / ".local" / "share" / "github-watcher"
        state_dir.mkdir(parents=True)
        state_file = state_dir / "state.json"
        state_file.write_text(
            json.dumps(
                {
                    "processed_failures": {"repo-123:test": "2025-01-01T00:00:00"},
                    "processed_comments": {},
                    "processed_reviews": {},
                }
            )
        )

        with patch.object(Path, "home", return_value=temp_dir):
            state = github_watcher.load_state()
            assert "repo-123:test" in state["processed_failures"]

    def test_save_state(self, temp_dir):
        """Test saving state to file."""
        state = {
            "processed_failures": {"key": "value"},
            "processed_comments": {},
            "processed_reviews": {},
        }

        with patch.object(Path, "home", return_value=temp_dir):
            github_watcher.save_state(state)

            state_file = temp_dir / ".local" / "share" / "github-watcher" / "state.json"
            assert state_file.exists()

            loaded = json.loads(state_file.read_text())
            assert loaded["processed_failures"]["key"] == "value"


class TestGhJson:
    """Tests for gh CLI JSON helper."""

    def test_gh_json_success(self):
        """Test successful gh CLI call."""
        mock_result = MagicMock()
        mock_result.stdout = '{"key": "value"}'
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = github_watcher.gh_json(["pr", "list"])

            assert result == {"key": "value"}
            mock_run.assert_called_once()

    def test_gh_json_failure(self):
        """Test failed gh CLI call."""
        from subprocess import CalledProcessError

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = CalledProcessError(1, "gh", stderr="error")
            result = github_watcher.gh_json(["pr", "list"])

            assert result is None

    def test_gh_json_invalid_json(self):
        """Test gh CLI with invalid JSON output."""
        mock_result = MagicMock()
        mock_result.stdout = "not json"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = github_watcher.gh_json(["pr", "list"])
            assert result is None


class TestGhText:
    """Tests for gh CLI text helper."""

    def test_gh_text_success(self):
        """Test successful gh CLI call for text output."""
        mock_result = MagicMock()
        mock_result.stdout = "diff --git a/file.py"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = github_watcher.gh_text(["pr", "diff", "1"])

            assert result == "diff --git a/file.py"


class TestInvokeJib:
    """Tests for jib container invocation."""

    def test_invoke_jib_success(self):
        """Test successful jib invocation."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        context = {"repository": "owner/repo", "pr_number": 123}

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = github_watcher.invoke_jib("check_failure", context)

            assert result is True
            mock_run.assert_called_once()

            # Verify command structure
            call_args = mock_run.call_args[0][0]
            assert "jib" in call_args
            assert "--exec" in call_args
            assert "--task" in call_args
            assert "check_failure" in call_args
            assert "--context" in call_args

    def test_invoke_jib_failure(self):
        """Test failed jib invocation."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error"

        context = {"repository": "owner/repo"}

        with patch("subprocess.run", return_value=mock_result):
            result = github_watcher.invoke_jib("check_failure", context)

            assert result is False

    def test_invoke_jib_not_found(self):
        """Test jib command not found."""
        context = {"repository": "owner/repo"}

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = github_watcher.invoke_jib("check_failure", context)

            assert result is False


class TestCheckPrForFailures:
    """Tests for PR failure detection."""

    def test_no_failed_checks(self):
        """Test PR with all passing checks."""
        pr_data = {"number": 123, "title": "Fix bug", "headRefOid": "abc123"}
        state = {"processed_failures": {}}

        with patch.object(github_watcher, "gh_json") as mock_gh:
            # API returns check_runs wrapper with conclusion field
            mock_gh.return_value = {
                "check_runs": [
                    {"name": "test", "conclusion": "success"},
                    {"name": "lint", "conclusion": "success"},
                ]
            }

            result = github_watcher.check_pr_for_failures("owner/repo", pr_data, state)

            assert result is None

    def test_failed_checks_returns_context(self):
        """Test PR with failed checks returns context."""
        pr_data = {
            "number": 123,
            "title": "Fix bug",
            "url": "https://github.com/owner/repo/pull/123",
            "headRefName": "fix-branch",
            "baseRefName": "main",
            "headRefOid": "abc123def456",
        }
        state = {"processed_failures": {}}

        with patch.object(github_watcher, "gh_json") as mock_gh:
            # First call: get check runs via API
            # Second call: get PR details
            mock_gh.side_effect = [
                {
                    "check_runs": [
                        {
                            "name": "test",
                            "conclusion": "failure",
                            "html_url": "",
                            "started_at": "",
                            "completed_at": "",
                            "output": {},
                            "app": {},
                        }
                    ]
                },
                {"body": "PR description"},
            ]

            with patch.object(github_watcher, "fetch_check_logs", return_value=None):
                result = github_watcher.check_pr_for_failures("owner/repo", pr_data, state)

            assert result is not None
            assert result["type"] == "check_failure"
            assert result["repository"] == "owner/repo"
            assert result["pr_number"] == 123
            assert len(result["failed_checks"]) == 1

    def test_already_processed_skipped(self):
        """Test already processed failures are skipped."""
        pr_data = {"number": 123, "title": "Fix bug", "headRefOid": "abc123"}
        state = {"processed_failures": {"owner/repo-123-abc123:test": "2025-01-01"}}

        with patch.object(github_watcher, "gh_json") as mock_gh:
            mock_gh.return_value = {
                "check_runs": [
                    {
                        "name": "test",
                        "conclusion": "failure",
                        "html_url": "",
                        "output": {},
                        "app": {},
                    }
                ]
            }

            result = github_watcher.check_pr_for_failures("owner/repo", pr_data, state)

            assert result is None

    def test_no_head_sha_skipped(self):
        """Test PR without headRefOid is skipped."""
        pr_data = {"number": 123, "title": "Fix bug"}
        state = {"processed_failures": {}}

        result = github_watcher.check_pr_for_failures("owner/repo", pr_data, state)

        assert result is None


class TestCheckPrForComments:
    """Tests for PR comment detection."""

    def test_no_comments(self):
        """Test PR with no comments."""
        pr_data = {"number": 123, "title": "Fix bug"}
        state = {"processed_comments": {}}

        with patch.object(github_watcher, "gh_json") as mock_gh:
            # First call: gh pr view returns comments/reviews
            # Second call: gh api for line-level review comments returns empty list
            mock_gh.side_effect = [{"comments": [], "reviews": []}, []]

            result = github_watcher.check_pr_for_comments("owner/repo", pr_data, state, "testuser")

            assert result is None

    def test_comments_from_others(self):
        """Test PR with comments from others."""
        pr_data = {
            "number": 123,
            "title": "Fix bug",
            "url": "https://github.com/owner/repo/pull/123",
            "headRefName": "fix-branch",
        }
        state = {"processed_comments": {}}

        with patch.object(github_watcher, "gh_json") as mock_gh:
            # First call: gh pr view returns comments/reviews
            # Second call: gh api for line-level review comments returns empty list
            mock_gh.side_effect = [
                {
                    "comments": [
                        {
                            "id": "comment-1",
                            "author": {"login": "reviewer"},
                            "body": "Please fix this",
                            "createdAt": "2025-01-01T00:00:00Z",
                        }
                    ],
                    "reviews": [],
                },
                [],  # No line-level review comments
            ]

            result = github_watcher.check_pr_for_comments("owner/repo", pr_data, state, "testuser")

            assert result is not None
            assert result["type"] == "comment"
            assert len(result["comments"]) == 1

    def test_bot_comments_filtered(self):
        """Test that bot comments are filtered out."""
        pr_data = {"number": 123, "title": "Fix bug"}
        state = {"processed_comments": {}}

        with patch.object(github_watcher, "gh_json") as mock_gh:
            # First call: gh pr view returns comments/reviews
            # Second call: gh api for line-level review comments returns empty list
            mock_gh.side_effect = [
                {
                    "comments": [
                        {
                            "id": "c1",
                            "author": {"login": "github-actions[bot]"},
                            "body": "CI passed",
                            "createdAt": "2025-01-01",
                        },
                        {
                            "id": "c2",
                            "author": {"login": "dependabot[bot]"},
                            "body": "Update deps",
                            "createdAt": "2025-01-01",
                        },
                    ],
                    "reviews": [],
                },
                [],  # No line-level review comments
            ]

            result = github_watcher.check_pr_for_comments("owner/repo", pr_data, state, "testuser")

            assert result is None


class TestCheckPrsForReview:
    """Tests for PR review detection."""

    def test_no_prs_from_others(self):
        """Test when no PRs from others exist."""
        state = {"processed_reviews": {}}
        all_prs = []  # Pre-fetched empty list

        result = github_watcher.check_prs_for_review(
            "owner/repo", all_prs, state, "testuser", "botuser"
        )

        assert result == []

    def test_prs_from_others_detected(self):
        """Test PRs from others are detected."""
        state = {"processed_reviews": {}}
        all_prs = [
            {
                "number": 456,
                "title": "New feature",
                "url": "https://github.com/owner/repo/pull/456",
                "headRefName": "feature",
                "baseRefName": "main",
                "author": {"login": "other-dev"},
                "createdAt": "2025-01-01",
                "additions": 100,
                "deletions": 50,
                "files": [{"path": "app.py"}],
            }
        ]

        with patch.object(github_watcher, "gh_text", return_value="diff content"):
            result = github_watcher.check_prs_for_review(
                "owner/repo", all_prs, state, "testuser", "botuser"
            )

        assert len(result) == 1
        assert result[0]["type"] == "review_request"
        assert result[0]["pr_number"] == 456
        assert result[0]["author"] == "other-dev"

    def test_already_reviewed_skipped(self):
        """Test already reviewed PRs are skipped."""
        state = {"processed_reviews": {"owner/repo-456:review": "2025-01-01"}}
        all_prs = [
            {
                "number": 456,
                "title": "New feature",
                "author": {"login": "other-dev"},
            }
        ]

        result = github_watcher.check_prs_for_review(
            "owner/repo", all_prs, state, "testuser", "botuser"
        )

        assert result == []


class TestCheckPrForMergeConflict:
    """Tests for PR merge conflict detection."""

    def test_no_conflict(self):
        """Test PR with no merge conflict."""
        pr_data = {"number": 123, "title": "Fix bug", "headRefOid": "abc123"}
        state = {"processed_conflicts": {}}

        with patch.object(github_watcher, "gh_json") as mock_gh:
            mock_gh.return_value = {
                "number": 123,
                "title": "Fix bug",
                "body": "PR description",
                "url": "https://github.com/owner/repo/pull/123",
                "headRefName": "fix-branch",
                "baseRefName": "main",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
            }

            result = github_watcher.check_pr_for_merge_conflict("owner/repo", pr_data, state)

            assert result is None

    def test_conflict_detected(self):
        """Test PR with merge conflict returns context."""
        pr_data = {
            "number": 123,
            "title": "Fix bug",
            "url": "https://github.com/owner/repo/pull/123",
            "headRefName": "fix-branch",
            "baseRefName": "main",
            "headRefOid": "abc123def456",
        }
        state = {"processed_conflicts": {}}

        with patch.object(github_watcher, "gh_json") as mock_gh:
            mock_gh.return_value = {
                "number": 123,
                "title": "Fix bug",
                "body": "PR description",
                "url": "https://github.com/owner/repo/pull/123",
                "headRefName": "fix-branch",
                "baseRefName": "main",
                "mergeable": "CONFLICTING",
                "mergeStateStatus": "DIRTY",
            }

            result = github_watcher.check_pr_for_merge_conflict("owner/repo", pr_data, state)

            assert result is not None
            assert result["type"] == "merge_conflict"
            assert result["repository"] == "owner/repo"
            assert result["pr_number"] == 123
            assert "conflict_signature" in result

    def test_dirty_state_detected(self):
        """Test PR with DIRTY mergeStateStatus is detected."""
        pr_data = {
            "number": 123,
            "title": "Fix bug",
            "headRefOid": "abc123",
        }
        state = {"processed_conflicts": {}}

        with patch.object(github_watcher, "gh_json") as mock_gh:
            mock_gh.return_value = {
                "number": 123,
                "title": "Fix bug",
                "body": "",
                "url": "",
                "headRefName": "fix-branch",
                "baseRefName": "main",
                "mergeable": "UNKNOWN",
                "mergeStateStatus": "DIRTY",
            }

            result = github_watcher.check_pr_for_merge_conflict("owner/repo", pr_data, state)

            assert result is not None
            assert result["type"] == "merge_conflict"

    def test_already_processed_skipped(self):
        """Test already processed conflicts are skipped."""
        pr_data = {"number": 123, "title": "Fix bug", "headRefOid": "abc123"}
        state = {"processed_conflicts": {"owner/repo-123-abc123:conflict": "2025-01-01"}}

        with patch.object(github_watcher, "gh_json") as mock_gh:
            mock_gh.return_value = {
                "number": 123,
                "title": "Fix bug",
                "body": "",
                "url": "",
                "headRefName": "fix-branch",
                "baseRefName": "main",
                "mergeable": "CONFLICTING",
                "mergeStateStatus": "DIRTY",
            }

            result = github_watcher.check_pr_for_merge_conflict("owner/repo", pr_data, state)

            assert result is None

    def test_api_failure_returns_none(self):
        """Test API failure returns None."""
        pr_data = {"number": 123, "title": "Fix bug", "headRefOid": "abc123"}
        state = {"processed_conflicts": {}}

        with patch.object(github_watcher, "gh_json", return_value=None):
            result = github_watcher.check_pr_for_merge_conflict("owner/repo", pr_data, state)

            assert result is None
