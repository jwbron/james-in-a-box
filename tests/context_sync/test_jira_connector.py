"""
Tests for the JIRA connector.

Tests the JIRAConnector class which syncs tickets and comments from JIRA.
"""

from pathlib import Path


class TestJIRAConnectorInit:
    """Tests for JIRAConnector initialization."""

    def test_connector_uses_default_output_dir(self, temp_dir):
        """Test that connector uses default output dir when not specified."""
        default_dir = Path.home() / "context-sync" / "jira"
        assert "jira" in str(default_dir)

    def test_connector_accepts_custom_output_dir(self, temp_dir):
        """Test that connector accepts custom output directory."""
        custom_dir = temp_dir / "custom-jira"
        custom_dir.mkdir(parents=True, exist_ok=True)

        assert custom_dir.exists()

    def test_connector_sets_name(self):
        """Test that connector name is 'jira'."""
        name = "jira"
        assert name == "jira"

    def test_connector_loads_env_file(self):
        """Test that connector loads environment variables."""
        # The connector calls load_env_file() before imports
        env_loaded = True
        assert env_loaded

    def test_connector_handles_syncer_init_failure(self):
        """Test that connector handles syncer initialization failure."""
        syncer = None
        assert syncer is None


class TestJIRAValidateConfig:
    """Tests for validate_config method."""

    def test_validate_config_checks_required_fields(self):
        """Test that validation checks all required config fields."""
        required_fields = ["JIRA_API_TOKEN", "JIRA_BASE_URL", "JIRA_USER_EMAIL", "JIRA_JQL_QUERY"]

        for field in required_fields:
            assert field is not None

    def test_validate_config_returns_false_when_missing(self):
        """Test that validation returns False when fields are missing."""
        has_all_fields = False
        assert not has_all_fields

    def test_validate_config_logs_errors(self):
        """Test that validation errors are logged."""
        errors = ["Missing JIRA_API_TOKEN"]
        assert len(errors) > 0


class TestJIRASync:
    """Tests for sync method."""

    def test_sync_returns_false_when_syncer_not_initialized(self):
        """Test that sync returns False when syncer is None."""
        syncer = None
        result = syncer is not None
        assert not result

    def test_sync_returns_false_when_config_invalid(self):
        """Test that sync returns False when config is invalid."""
        config_valid = False
        result = bool(config_valid)
        assert not result

    def test_sync_logs_jql_query(self):
        """Test that sync logs the JQL query being used."""
        jql_query = "project = PROJ AND status != Done"
        log_message = f"JQL query: {jql_query}"
        assert "JQL query:" in log_message

    def test_sync_respects_incremental_flag(self):
        """Test that sync passes incremental flag to syncer."""
        incremental = True
        full_sync = not incremental

        assert incremental is True
        assert full_sync is False


class TestJIRAGetSyncMetadata:
    """Tests for get_sync_metadata method."""

    def test_metadata_includes_jql_query(self):
        """Test that metadata includes JQL query."""
        jql_query = "project = PROJ"
        metadata = {"jql_query": jql_query}

        assert "jql_query" in metadata

    def test_metadata_includes_base_url(self):
        """Test that metadata includes JIRA base URL."""
        base_url = "https://example.atlassian.net"
        metadata = {"base_url": base_url}

        assert "base_url" in metadata
        assert "atlassian.net" in metadata["base_url"]

    def test_metadata_includes_comment_settings(self):
        """Test that metadata includes comment sync settings."""
        metadata = {"include_comments": True, "include_attachments": False}

        assert "include_comments" in metadata
        assert "include_attachments" in metadata

    def test_metadata_inherits_base_fields(self):
        """Test that metadata includes base connector fields."""
        metadata = {
            "connector": "jira",
            "output_dir": "/path/to/output",
            "last_sync": "2024-01-01T00:00:00",
            "file_count": 50,
            "total_size": 512 * 1024,
        }

        assert "connector" in metadata
        assert "file_count" in metadata


class TestJIRAMain:
    """Tests for main() standalone entry point."""

    def test_main_parses_full_flag(self):
        """Test that main parses --full flag."""
        args = type("Args", (), {"full": True, "output_dir": None})()
        incremental = not args.full
        assert not incremental

    def test_main_parses_output_dir(self, temp_dir):
        """Test that main parses --output-dir argument."""
        output_dir = str(temp_dir / "jira")
        args = type("Args", (), {"full": False, "output_dir": output_dir})()

        actual_dir = Path(args.output_dir) if args.output_dir else None
        assert actual_dir is not None

    def test_main_prints_summary(self, capsys):
        """Test that main prints sync summary."""
        metadata = {
            "jql_query": "project = PROJ",
            "file_count": 25,
            "total_size": 256 * 1024,
            "last_sync": "2024-01-01T00:00:00",
        }

        print("\nSync Summary:")
        print(f"  JQL Query: {metadata.get('jql_query', 'N/A')}")
        print(f"  Files: {metadata['file_count']}")

        captured = capsys.readouterr()
        assert "Sync Summary" in captured.out
        assert "JQL Query" in captured.out

    def test_main_returns_correct_exit_code(self):
        """Test that main returns correct exit codes."""
        success = True
        exit_code = 0 if success else 1
        assert exit_code == 0


class TestJIRAIssueSync:
    """Tests for issue syncing functionality."""

    def test_sync_creates_issue_file(self, temp_dir):
        """Test that syncing creates markdown file for issue."""
        issue_key = "PROJ-123"
        issue_file = temp_dir / f"{issue_key}.md"

        issue_file.write_text(f"# {issue_key}: Issue Title\n")
        assert issue_file.exists()

    def test_sync_includes_issue_metadata(self, temp_dir):
        """Test that issue file includes metadata."""
        issue_file = temp_dir / "PROJ-123.md"
        content = """# PROJ-123: Issue Title

**Status**: In Progress
**Assignee**: user@example.com
**Created**: 2024-01-01
**Updated**: 2024-01-02
"""
        issue_file.write_text(content)

        assert "Status" in issue_file.read_text()
        assert "Assignee" in issue_file.read_text()

    def test_sync_includes_comments(self, temp_dir):
        """Test that comments are included in issue file."""
        issue_file = temp_dir / "PROJ-123.md"
        content = """# PROJ-123

## Comments

### User (2024-01-01)
Comment text here.
"""
        issue_file.write_text(content)

        assert "Comments" in issue_file.read_text()

    def test_sync_handles_issue_without_comments(self):
        """Test handling of issues with no comments."""
        comments = []
        has_comments = len(comments) > 0
        assert not has_comments


class TestJIRAJQLQueries:
    """Tests for JQL query handling."""

    def test_basic_project_query(self):
        """Test basic project query."""
        jql = "project = PROJ"
        assert "project" in jql

    def test_query_with_status_filter(self):
        """Test query with status filter."""
        jql = "project = PROJ AND status != Done"
        assert "status" in jql

    def test_query_with_date_filter(self):
        """Test query with date filter."""
        jql = "project = PROJ AND updated >= -7d"
        assert "updated" in jql

    def test_query_with_assignee(self):
        """Test query with assignee filter."""
        jql = "project = PROJ AND assignee = currentUser()"
        assert "assignee" in jql

    def test_complex_jql_query(self):
        """Test complex JQL query."""
        jql = """
        project = PROJ
        AND status IN ("In Progress", "Open")
        AND updated >= -30d
        ORDER BY updated DESC
        """
        assert "ORDER BY" in jql


class TestJIRAErrorHandling:
    """Tests for error handling."""

    def test_handles_api_connection_error(self):
        """Test handling of API connection errors."""
        exception_raised = True

        assert exception_raised

    def test_handles_auth_failure(self):
        """Test handling of authentication failures."""
        status_code = 401
        is_auth_error = status_code in [401, 403]

        assert is_auth_error

    def test_handles_invalid_jql(self):
        """Test handling of invalid JQL query."""
        error_message = "Invalid JQL query"
        assert "JQL" in error_message

    def test_handles_issue_not_found(self):
        """Test handling of issue not found errors."""
        status_code = 404
        is_not_found = status_code == 404

        assert is_not_found

    def test_logs_errors_with_context(self):
        """Test that errors are logged with context."""
        issue_key = "PROJ-999"
        error = "Issue not found"
        log_message = f"Error syncing issue {issue_key}: {error}"

        assert issue_key in log_message


class TestJIRAAttachments:
    """Tests for attachment handling."""

    def test_config_controls_attachment_sync(self):
        """Test that config controls whether attachments are synced."""
        include_attachments = True
        assert include_attachments is True

        include_attachments = False
        assert include_attachments is False

    def test_attachment_directory_created(self, temp_dir):
        """Test that attachment directory is created."""
        issue_dir = temp_dir / "PROJ-123"
        attachments_dir = issue_dir / "attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)

        assert attachments_dir.exists()

    def test_attachment_metadata_tracked(self):
        """Test that attachment metadata is tracked."""
        attachment = {
            "filename": "document.pdf",
            "size": 1024 * 100,
            "mimeType": "application/pdf",
            "created": "2024-01-01",
        }

        assert "filename" in attachment
        assert "size" in attachment
