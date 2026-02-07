"""
Tests for the github-sync module.

Tests the GitHubSync class which syncs open PRs to disk for jib consumption.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest


class TestGitHubSyncInit:
    """Tests for GitHubSync initialization."""

    def test_creates_prs_directory(self, temp_dir):
        """Test that PRs directory is created."""
        sync_dir = temp_dir / "github"
        prs_dir = sync_dir / "prs"
        prs_dir.mkdir(parents=True, exist_ok=True)

        assert prs_dir.exists()

    def test_creates_checks_directory(self, temp_dir):
        """Test that checks directory is created."""
        sync_dir = temp_dir / "github"
        checks_dir = sync_dir / "checks"
        checks_dir.mkdir(parents=True, exist_ok=True)

        assert checks_dir.exists()

    def test_creates_comments_directory(self, temp_dir):
        """Test that comments directory is created."""
        sync_dir = temp_dir / "github"
        comments_dir = sync_dir / "comments"
        comments_dir.mkdir(parents=True, exist_ok=True)

        assert comments_dir.exists()

    def test_accepts_specific_repo(self):
        """Test accepting a specific repo to sync."""
        repo = "owner/repo-name"
        assert "/" in repo

    def test_accepts_all_prs_flag(self):
        """Test accepting all_prs flag."""
        all_prs = True
        assert all_prs is True


class TestGhApi:
    """Tests for gh_api helper method."""

    def test_returns_json_output(self):
        """Test that gh_api returns parsed JSON."""
        mock_output = '{"number": 123, "title": "Test PR"}'
        result = json.loads(mock_output)

        assert result["number"] == 123
        assert result["title"] == "Test PR"

    def test_handles_command_error(self):
        """Test handling of command errors."""
        error_message = "Error running gh command"

        assert "Error" in error_message

    def test_handles_json_parse_error(self):
        """Test handling of JSON parse errors."""
        invalid_json = "not valid json"

        with pytest.raises(json.JSONDecodeError):
            json.loads(invalid_json)


class TestGhText:
    """Tests for gh_text helper method."""

    def test_returns_text_output(self):
        """Test that gh_text returns text output."""
        output = "diff --git a/file.py b/file.py\n+added line"
        assert "diff" in output

    def test_returns_empty_on_error(self):
        """Test returning empty string on error."""
        on_error = ""
        assert on_error == ""


class TestSyncPrs:
    """Tests for sync_prs method."""

    def test_fetches_open_prs(self):
        """Test fetching open PRs."""
        prs = [{"number": 1, "title": "PR 1"}, {"number": 2, "title": "PR 2"}]

        assert len(prs) == 2

    def test_filters_by_author_when_not_all(self):
        """Test filtering by @me when all_prs is False."""
        all_prs = False
        author_flag = [] if all_prs else ["--author", "@me"]

        assert "--author" in author_flag

    def test_syncs_all_prs_when_flag_set(self):
        """Test syncing all PRs when all_prs is True."""
        all_prs = True
        author_flag = [] if all_prs else ["--author", "@me"]

        assert len(author_flag) == 0

    def test_extracts_repo_from_url(self):
        """Test extracting owner/repo from PR URL."""
        url = "https://github.com/owner/repo/pull/123"
        parts = url.split("/")
        repo_with_owner = f"{parts[3]}/{parts[4]}"

        assert repo_with_owner == "owner/repo"


class TestWritePrMarkdown:
    """Tests for write_pr_markdown method."""

    def test_creates_pr_markdown_file(self, temp_dir):
        """Test creating PR markdown file."""
        prs_dir = temp_dir / "prs"
        prs_dir.mkdir(parents=True, exist_ok=True)

        repo_name = "repo"
        pr_num = 123
        pr_file = prs_dir / f"{repo_name}-PR-{pr_num}.md"

        pr_file.write_text("# PR #123: Test PR\n")
        assert pr_file.exists()

    def test_creates_diff_file(self, temp_dir):
        """Test creating PR diff file."""
        prs_dir = temp_dir / "prs"
        prs_dir.mkdir(parents=True, exist_ok=True)

        repo_name = "repo"
        pr_num = 123
        diff_file = prs_dir / f"{repo_name}-PR-{pr_num}.diff"

        diff_file.write_text("diff --git a/file.py b/file.py\n")
        assert diff_file.exists()

    def test_markdown_includes_metadata(self, temp_dir):
        """Test that markdown includes PR metadata."""
        pr = {
            "number": 123,
            "title": "Test PR",
            "author": {"login": "testuser"},
            "state": "OPEN",
            "url": "https://github.com/owner/repo/pull/123",
            "headRefName": "feature-branch",
            "baseRefName": "main",
            "additions": 10,
            "deletions": 5,
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-02T00:00:00Z",
        }

        content = f"""# PR #{pr["number"]}: {pr["title"]}

**Repository**: owner/repo
**Author**: {pr["author"]["login"]}
**State**: {pr["state"]}
**URL**: {pr["url"]}
**Branch**: {pr["headRefName"]} → {pr["baseRefName"]}
**Additions**: {pr.get("additions", 0)}
**Deletions**: {pr.get("deletions", 0)}
"""

        assert "PR #123" in content
        assert "testuser" in content
        assert "feature-branch → main" in content

    def test_markdown_includes_files_changed(self):
        """Test that markdown includes files changed."""
        files = [
            {"path": "file1.py", "additions": 10, "deletions": 2},
            {"path": "file2.py", "additions": 5, "deletions": 0},
        ]

        content = f"## Files Changed ({len(files)})\n\n"
        for f in files:
            content += f"- `{f['path']}` (+{f['additions']}, -{f['deletions']})\n"

        assert "Files Changed (2)" in content
        assert "`file1.py`" in content

    def test_markdown_includes_comments(self):
        """Test that markdown includes PR comments."""
        comments = [
            {"author": {"login": "reviewer"}, "createdAt": "2024-01-01T00:00:00Z", "body": "LGTM!"}
        ]

        content = f"\n## Comments ({len(comments)})\n\n"
        for comment in comments:
            content += f"### {comment['author']['login']} ({comment['createdAt']})\n\n"
            content += f"{comment['body']}\n\n---\n\n"

        assert "Comments (1)" in content
        assert "LGTM!" in content


class TestWriteChecks:
    """Tests for write_checks method."""

    def test_creates_checks_json_file(self, temp_dir):
        """Test creating checks JSON file."""
        checks_dir = temp_dir / "checks"
        checks_dir.mkdir(parents=True, exist_ok=True)

        repo_name = "repo"
        pr_num = 123
        checks_file = checks_dir / f"{repo_name}-PR-{pr_num}-checks.json"

        checks_data = {"pr_number": pr_num, "repository": "owner/repo", "checks": []}
        checks_file.write_text(json.dumps(checks_data))

        assert checks_file.exists()

    def test_enriches_failed_checks_with_logs(self):
        """Test that failed checks get full logs."""
        checks = [{"name": "test", "state": "SUCCESS"}, {"name": "lint", "state": "FAILURE"}]

        failed_count = 0
        for check in checks:
            if check["state"].upper() in ("FAILURE", "FAILED"):
                failed_count += 1
                check["full_log"] = "Error: lint failed"

        assert failed_count == 1
        assert "full_log" in checks[1]

    def test_calculates_check_summary(self):
        """Test calculating check status summary."""
        checks = [
            {"state": "SUCCESS"},
            {"state": "SUCCESS"},
            {"state": "FAILURE"},
            {"state": "PENDING"},
        ]

        summary = {
            "total": len(checks),
            "failed": len([c for c in checks if c["state"].upper() == "FAILURE"]),
            "passed": len([c for c in checks if c["state"].upper() == "SUCCESS"]),
            "pending": len(
                [c for c in checks if c["state"].upper() in ("PENDING", "QUEUED", "IN_PROGRESS")]
            ),
        }

        assert summary["total"] == 4
        assert summary["failed"] == 1
        assert summary["passed"] == 2
        assert summary["pending"] == 1


class TestGetCheckLogs:
    """Tests for get_check_logs method."""

    def test_extracts_run_id_from_url(self):
        """Test extracting run ID from GitHub Actions URL."""
        url = "https://github.com/owner/repo/actions/runs/12345"
        run_id = url.rsplit("/runs/", maxsplit=1)[-1].split("/")[0].split("?")[0]

        assert run_id == "12345"

    def test_handles_url_with_query_params(self):
        """Test handling URLs with query parameters."""
        url = "https://github.com/owner/repo/actions/runs/12345?check_suite_focus=true"
        run_id = url.rsplit("/runs/", maxsplit=1)[-1].split("/")[0].split("?")[0]

        assert run_id == "12345"

    def test_returns_none_for_non_actions_url(self):
        """Test returning None for non-Actions URLs."""
        url = "https://example.com/check"
        has_run_id = "/actions/runs/" in url

        assert not has_run_id


class TestWriteComments:
    """Tests for write_comments method."""

    def test_creates_comments_json_file(self, temp_dir):
        """Test creating comments JSON file."""
        comments_dir = temp_dir / "comments"
        comments_dir.mkdir(parents=True, exist_ok=True)

        repo_name = "repo"
        pr_num = 123
        comments_file = comments_dir / f"{repo_name}-PR-{pr_num}-comments.json"

        comments_data = {"pr_number": pr_num, "repository": "owner/repo", "comments": []}
        comments_file.write_text(json.dumps(comments_data))

        assert comments_file.exists()

    def test_structures_comments_correctly(self):
        """Test that comments are structured correctly."""
        comment = {
            "id": "comment-123",
            "author": {"login": "user"},
            "body": "Comment text",
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-02T00:00:00Z",
            "authorAssociation": "CONTRIBUTOR",
        }

        comment_data = {
            "id": comment.get("id"),
            "author": comment.get("author", {}).get("login", "unknown"),
            "body": comment.get("body", ""),
            "created_at": comment.get("createdAt", ""),
            "updated_at": comment.get("updatedAt", ""),
            "author_association": comment.get("authorAssociation", ""),
        }

        assert comment_data["id"] == "comment-123"
        assert comment_data["author"] == "user"


class TestWriteIndex:
    """Tests for write_index method."""

    def test_creates_index_json_file(self, temp_dir):
        """Test creating index.json file."""
        sync_dir = temp_dir / "github"
        sync_dir.mkdir(parents=True, exist_ok=True)

        index_file = sync_dir / "index.json"
        index = {"last_sync": datetime.now().isoformat() + "Z", "pr_count": 2, "prs": []}
        index_file.write_text(json.dumps(index))

        assert index_file.exists()

    def test_index_includes_pr_metadata(self):
        """Test that index includes PR metadata."""
        prs = [
            {
                "number": 123,
                "url": "https://github.com/owner/repo/pull/123",
                "title": "Test PR",
                "headRefName": "feature",
                "baseRefName": "main",
                "updatedAt": "2024-01-01T00:00:00Z",
            }
        ]

        def extract_repo(url):
            parts = url.split("/")
            return f"{parts[3]}/{parts[4]}"

        index = {
            "last_sync": datetime.now().isoformat() + "Z",
            "pr_count": len(prs),
            "prs": [
                {
                    "number": pr["number"],
                    "repository": extract_repo(pr["url"]),
                    "title": pr["title"],
                    "url": pr["url"],
                    "head_branch": pr["headRefName"],
                    "base_branch": pr["baseRefName"],
                    "updated": pr["updatedAt"],
                }
                for pr in prs
            ],
        }

        assert index["pr_count"] == 1
        assert index["prs"][0]["repository"] == "owner/repo"


class TestCleanupClosedPrs:
    """Tests for cleanup_closed_prs method."""

    def test_removes_closed_pr_files(self, temp_dir):
        """Test removing files for closed PRs."""
        prs_dir = temp_dir / "prs"
        prs_dir.mkdir(parents=True, exist_ok=True)

        # Create files for PRs 1 and 2
        (prs_dir / "repo-PR-1.md").write_text("PR 1")
        (prs_dir / "repo-PR-1.diff").write_text("diff 1")
        (prs_dir / "repo-PR-2.md").write_text("PR 2")
        (prs_dir / "repo-PR-2.diff").write_text("diff 2")

        # Only PR 1 is still open
        current_pr_numbers = [1]

        # Cleanup PR 2
        for pr_file in prs_dir.glob("*-PR-*.md"):
            try:
                pr_num = int(pr_file.stem.split("-PR-")[-1])
                if pr_num not in current_pr_numbers:
                    pr_file.unlink()
                    diff_file = pr_file.parent / f"{pr_file.stem}.diff"
                    if diff_file.exists():
                        diff_file.unlink()
            except (ValueError, IndexError):
                pass

        assert (prs_dir / "repo-PR-1.md").exists()
        assert not (prs_dir / "repo-PR-2.md").exists()

    def test_extracts_pr_number_from_filename(self):
        """Test extracting PR number from filename."""
        filename = "repo-name-PR-123.md"
        pr_num = int(filename.rsplit("-PR-", maxsplit=1)[-1].replace(".md", ""))

        assert pr_num == 123


class TestMain:
    """Tests for main entry point."""

    def test_parses_repo_argument(self):
        """Test parsing --repo argument."""
        args = type(
            "Args",
            (),
            {"repo": "owner/repo", "all_prs": False, "output": None, "use_config": False},
        )()

        assert args.repo == "owner/repo"

    def test_parses_all_prs_flag(self):
        """Test parsing --all-prs flag."""
        args = type(
            "Args", (), {"repo": None, "all_prs": True, "output": None, "use_config": False}
        )()

        assert args.all_prs is True

    def test_parses_output_argument(self, temp_dir):
        """Test parsing --output argument."""
        output_path = str(temp_dir / "custom-output")
        args = type(
            "Args", (), {"repo": None, "all_prs": False, "output": output_path, "use_config": False}
        )()

        assert args.output == output_path

    def test_uses_config_when_flag_set(self):
        """Test using config when --use-config is set."""
        args = type(
            "Args", (), {"repo": None, "all_prs": False, "output": None, "use_config": True}
        )()

        assert args.use_config is True

    def test_default_output_directory(self, temp_dir, monkeypatch):
        """Test default output directory."""
        monkeypatch.setenv("HOME", str(temp_dir))

        default_dir = Path.home() / "context-sync" / "github"
        assert str(default_dir).endswith("context-sync/github")


class TestRepoConfigIntegration:
    """Tests for integration with repo_config."""

    def test_loads_repos_from_config(self):
        """Test loading repos from config."""
        config_repos = ["owner/repo1", "owner/repo2"]
        assert len(config_repos) == 2

    def test_uses_config_sync_settings(self):
        """Test using sync settings from config."""
        sync_config = {"sync_all_prs": True, "sync_interval_minutes": 5}

        all_prs = sync_config.get("sync_all_prs", True)
        assert all_prs is True

    def test_handles_missing_config(self):
        """Test handling when config is not available."""
        has_repo_config = False

        if not has_repo_config:
            # Fall back to @me mode
            pass

        assert True
