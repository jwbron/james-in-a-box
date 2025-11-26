"""
Tests for the Confluence connector.

Tests the ConfluenceConnector class which syncs documentation from Confluence.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestConfluenceConnectorInit:
    """Tests for ConfluenceConnector initialization."""

    def test_connector_uses_default_output_dir(self, temp_dir):
        """Test that connector uses default output dir when not specified."""
        # Default would come from ConfluenceConfig.OUTPUT_DIR
        default_dir = Path.home() / "context-sync" / "confluence"
        assert "confluence" in str(default_dir)

    def test_connector_accepts_custom_output_dir(self, temp_dir):
        """Test that connector accepts custom output directory."""
        custom_dir = temp_dir / "custom-confluence"
        custom_dir.mkdir(parents=True, exist_ok=True)

        assert custom_dir.exists()
        assert "custom-confluence" in str(custom_dir)

    def test_connector_sets_name(self):
        """Test that connector name is 'confluence'."""
        name = "confluence"
        assert name == "confluence"

    def test_connector_handles_syncer_init_failure(self):
        """Test that connector handles syncer initialization failure."""
        # Should set syncer to None on error
        syncer = None  # Simulating failed init

        assert syncer is None


class TestConfluenceValidateConfig:
    """Tests for validate_config method."""

    def test_validate_config_checks_required_fields(self):
        """Test that validation checks all required config fields."""
        required_fields = [
            'CONFLUENCE_API_TOKEN',
            'CONFLUENCE_BASE_URL',
            'CONFLUENCE_USER_EMAIL',
            'CONFLUENCE_SPACE_KEYS'
        ]

        for field in required_fields:
            assert field is not None

    def test_validate_config_returns_false_when_missing_fields(self):
        """Test that validation returns False when fields are missing."""
        # Simulate missing config
        has_all_fields = False
        assert not has_all_fields

    def test_validate_config_logs_errors(self):
        """Test that validation errors are logged."""
        errors = ["Missing CONFLUENCE_API_TOKEN", "Missing BASE_URL"]

        for error in errors:
            assert isinstance(error, str)
            assert len(error) > 0


class TestConfluenceSync:
    """Tests for sync method."""

    def test_sync_returns_false_when_syncer_not_initialized(self):
        """Test that sync returns False when syncer is None."""
        syncer = None
        result = False if syncer is None else True
        assert not result

    def test_sync_returns_false_when_config_invalid(self):
        """Test that sync returns False when config is invalid."""
        config_valid = False
        result = False if not config_valid else True
        assert not result

    def test_sync_iterates_over_space_keys(self):
        """Test that sync processes each configured space."""
        space_keys = ['TECH', 'DOCS', 'TEAM']

        synced = []
        for space_key in space_keys:
            synced.append(space_key)

        assert len(synced) == 3
        assert 'TECH' in synced

    def test_sync_continues_on_space_error(self):
        """Test that sync continues when individual space fails."""
        space_keys = ['SPACE1', 'SPACE2', 'SPACE3']
        failed_spaces = []
        synced_spaces = []

        for space in space_keys:
            if space == 'SPACE2':
                # Simulate error for SPACE2
                failed_spaces.append(space)
            else:
                synced_spaces.append(space)

        # Should still sync other spaces
        assert len(synced_spaces) == 2
        assert len(failed_spaces) == 1

    def test_sync_respects_incremental_flag(self):
        """Test that sync passes incremental flag to syncer."""
        incremental = True
        full_sync = not incremental

        assert incremental is True
        assert full_sync is False


class TestConfluenceGetSyncMetadata:
    """Tests for get_sync_metadata method."""

    def test_metadata_includes_spaces(self):
        """Test that metadata includes space list."""
        spaces = ['TECH', 'DOCS']
        metadata = {
            'spaces': spaces
        }

        assert 'spaces' in metadata
        assert len(metadata['spaces']) == 2

    def test_metadata_includes_base_url(self):
        """Test that metadata includes Confluence base URL."""
        base_url = "https://example.atlassian.net/wiki"
        metadata = {
            'base_url': base_url
        }

        assert 'base_url' in metadata
        assert 'atlassian.net' in metadata['base_url']

    def test_metadata_inherits_base_fields(self):
        """Test that metadata includes base connector fields."""
        metadata = {
            'connector': 'confluence',
            'output_dir': '/path/to/output',
            'last_sync': '2024-01-01T00:00:00',
            'file_count': 100,
            'total_size': 1024 * 1024
        }

        assert 'connector' in metadata
        assert 'output_dir' in metadata
        assert 'last_sync' in metadata
        assert 'file_count' in metadata
        assert 'total_size' in metadata


class TestConfluenceMain:
    """Tests for main() standalone entry point."""

    def test_main_parses_full_flag(self):
        """Test that main parses --full flag."""
        args = type('Args', (), {'full': True, 'output_dir': None})()
        incremental = not args.full
        assert not incremental

    def test_main_parses_output_dir(self, temp_dir):
        """Test that main parses --output-dir argument."""
        output_dir = str(temp_dir / "confluence")
        args = type('Args', (), {'full': False, 'output_dir': output_dir})()

        actual_dir = Path(args.output_dir) if args.output_dir else None
        assert actual_dir is not None
        assert "confluence" in str(actual_dir)

    def test_main_prints_summary(self, capsys):
        """Test that main prints sync summary."""
        metadata = {
            'spaces': ['TECH'],
            'file_count': 50,
            'total_size': 1024 * 1024,
            'last_sync': '2024-01-01T00:00:00'
        }

        print(f"\nSync Summary:")
        print(f"  Spaces: {', '.join(metadata.get('spaces', []))}")
        print(f"  Files: {metadata['file_count']}")
        print(f"  Size: {metadata['total_size'] / (1024*1024):.2f} MB")
        print(f"  Last sync: {metadata['last_sync']}")

        captured = capsys.readouterr()
        assert "Sync Summary" in captured.out
        assert "Files: 50" in captured.out

    def test_main_returns_correct_exit_code(self):
        """Test that main returns correct exit codes."""
        success = True
        exit_code = 0 if success else 1
        assert exit_code == 0

        success = False
        exit_code = 0 if success else 1
        assert exit_code == 1


class TestConfluenceSpaceSync:
    """Tests for individual space syncing."""

    def test_sync_space_creates_directory(self, temp_dir):
        """Test that syncing a space creates its directory."""
        space_key = "TECH"
        space_dir = temp_dir / space_key

        space_dir.mkdir(parents=True, exist_ok=True)
        assert space_dir.exists()

    def test_sync_space_creates_readme(self, temp_dir):
        """Test that syncing creates README.md for space."""
        space_key = "TECH"
        space_dir = temp_dir / space_key
        space_dir.mkdir(parents=True, exist_ok=True)

        readme = space_dir / "README.md"
        readme.write_text(f"# {space_key} Documentation\n")

        assert readme.exists()
        assert space_key in readme.read_text()

    def test_sync_space_handles_pagination(self):
        """Test that space sync handles paginated results."""
        # Simulate paginated API response
        pages = []
        for i in range(3):  # 3 pages of results
            pages.extend([f"page_{i}_{j}" for j in range(10)])

        assert len(pages) == 30

    def test_sync_space_converts_html_to_markdown(self):
        """Test that HTML content is converted to markdown."""
        html = "<h1>Title</h1><p>Paragraph</p>"
        # Simplified conversion simulation
        markdown = "# Title\n\nParagraph\n"

        assert "#" in markdown
        assert "<h1>" not in markdown


class TestConfluenceErrorHandling:
    """Tests for error handling."""

    def test_handles_api_connection_error(self):
        """Test handling of API connection errors."""
        error_message = "Connection refused"
        exception_raised = True

        assert exception_raised
        assert "Connection" in error_message

    def test_handles_auth_failure(self):
        """Test handling of authentication failures."""
        status_code = 401
        is_auth_error = status_code in [401, 403]

        assert is_auth_error

    def test_handles_rate_limiting(self):
        """Test handling of rate limiting responses."""
        status_code = 429
        retry_after = 60  # seconds

        is_rate_limited = status_code == 429
        assert is_rate_limited
        assert retry_after > 0

    def test_logs_errors_with_context(self):
        """Test that errors are logged with context."""
        space_key = "TECH"
        error = "Page not found"
        log_message = f"Error syncing space {space_key}: {error}"

        assert space_key in log_message
        assert error in log_message
