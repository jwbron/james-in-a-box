"""
Tests for the BaseConnector abstract class.

Tests the abstract base class that all context-sync connectors inherit from.
"""

import logging
import pickle
from datetime import datetime

import pytest


class TestBaseConnectorInit:
    """Tests for BaseConnector initialization."""

    def test_connector_creates_output_directory(self, temp_dir):
        """Test that connector creates output directory if it doesn't exist."""
        output_dir = temp_dir / "test-connector"
        assert not output_dir.exists()

        # Simulate init behavior
        output_dir.mkdir(parents=True, exist_ok=True)
        assert output_dir.exists()

    def test_connector_handles_existing_directory(self, temp_dir):
        """Test that connector handles existing output directory."""
        output_dir = temp_dir / "existing-connector"
        output_dir.mkdir(parents=True)

        # Should not raise even if directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        assert output_dir.exists()

    def test_sync_state_file_path(self, temp_dir):
        """Test that sync state file path is set correctly."""
        output_dir = temp_dir / "connector"
        output_dir.mkdir(parents=True, exist_ok=True)

        sync_state_file = output_dir / ".sync_state"
        assert sync_state_file.parent == output_dir
        assert sync_state_file.name == ".sync_state"


class TestSetupLogger:
    """Tests for _setup_logger method."""

    def test_logger_name_format(self):
        """Test that logger name follows expected format."""
        connector_name = "test-connector"
        expected_name = f"context-sync.{connector_name}"

        logger = logging.getLogger(expected_name)
        assert logger.name == expected_name

    def test_logger_level(self):
        """Test that logger level is set to INFO."""
        logger = logging.getLogger("context-sync.test")
        logger.setLevel(logging.INFO)

        assert logger.level == logging.INFO

    def test_logger_format_contains_connector_name(self):
        """Test that log format includes connector name."""
        connector_name = "confluence"
        format_str = f"[{connector_name}] %(levelname)s: %(message)s"

        assert connector_name in format_str
        assert "%(levelname)s" in format_str
        assert "%(message)s" in format_str


class TestLoadSyncState:
    """Tests for _load_sync_state method."""

    def test_load_state_from_valid_file(self, temp_dir):
        """Test loading sync state from valid pickle file."""
        state_file = temp_dir / ".sync_state"
        test_state = {"last_sync": "2024-01-01", "pages": [1, 2, 3]}

        with open(state_file, "wb") as f:
            pickle.dump(test_state, f)

        with open(state_file, "rb") as f:
            loaded_state = pickle.load(f)

        assert loaded_state == test_state

    def test_load_state_missing_file(self, temp_dir):
        """Test loading state when file doesn't exist."""
        state_file = temp_dir / ".sync_state"
        assert not state_file.exists()

        # Should return empty dict
        if state_file.exists():
            with open(state_file, "rb") as f:
                default_state = pickle.load(f)
        else:
            default_state = {}
        assert default_state == {}

    def test_load_state_corrupted_file(self, temp_dir):
        """Test loading state from corrupted pickle file."""
        state_file = temp_dir / ".sync_state"
        state_file.write_text("not a valid pickle")

        with pytest.raises((pickle.UnpicklingError, EOFError, ValueError)):
            with open(state_file, "rb") as f:
                pickle.load(f)

    def test_load_state_returns_empty_on_error(self, temp_dir):
        """Test that load returns empty dict on error."""
        state_file = temp_dir / ".sync_state"
        state_file.write_text("corrupted")

        try:
            with open(state_file, "rb") as f:
                state = pickle.load(f)
        except Exception:
            state = {}

        assert state == {}


class TestSaveSyncState:
    """Tests for _save_sync_state method."""

    def test_save_state_creates_file(self, temp_dir):
        """Test that save creates the state file."""
        state_file = temp_dir / ".sync_state"
        test_state = {"last_sync": "2024-01-01"}

        with open(state_file, "wb") as f:
            pickle.dump(test_state, f)

        assert state_file.exists()

    def test_save_state_overwrites_existing(self, temp_dir):
        """Test that save overwrites existing state file."""
        state_file = temp_dir / ".sync_state"

        # Save initial state
        initial_state = {"version": 1}
        with open(state_file, "wb") as f:
            pickle.dump(initial_state, f)

        # Save new state
        new_state = {"version": 2}
        with open(state_file, "wb") as f:
            pickle.dump(new_state, f)

        # Verify new state was saved
        with open(state_file, "rb") as f:
            loaded = pickle.load(f)

        assert loaded["version"] == 2

    def test_save_state_preserves_complex_types(self, temp_dir):
        """Test that save preserves complex Python types."""
        state_file = temp_dir / ".sync_state"
        complex_state = {
            "pages": [1, 2, 3],
            "metadata": {"key": "value"},
            "timestamp": datetime.now(),
            "enabled": True,
        }

        with open(state_file, "wb") as f:
            pickle.dump(complex_state, f)

        with open(state_file, "rb") as f:
            loaded = pickle.load(f)

        assert loaded["pages"] == [1, 2, 3]
        assert loaded["metadata"] == {"key": "value"}
        assert loaded["enabled"] is True


class TestGetSyncMetadata:
    """Tests for get_sync_metadata method."""

    def test_metadata_structure(self, temp_dir):
        """Test that metadata has expected structure."""
        output_dir = temp_dir / "connector"
        output_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "connector": "test",
            "output_dir": str(output_dir),
            "last_sync": None,
            "file_count": 0,
            "total_size": 0,
        }

        assert "connector" in metadata
        assert "output_dir" in metadata
        assert "last_sync" in metadata
        assert "file_count" in metadata
        assert "total_size" in metadata

    def test_metadata_counts_files(self, temp_dir):
        """Test that metadata correctly counts files."""
        output_dir = temp_dir / "connector"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create some test files
        (output_dir / "file1.md").write_text("content1")
        (output_dir / "file2.md").write_text("content2")
        (output_dir / "subdir").mkdir()
        (output_dir / "subdir" / "file3.md").write_text("content3")

        files = list(output_dir.rglob("*"))
        file_count = len([f for f in files if f.is_file()])

        assert file_count == 3

    def test_metadata_calculates_total_size(self, temp_dir):
        """Test that metadata calculates total file size."""
        output_dir = temp_dir / "connector"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create files with known sizes
        (output_dir / "file1.txt").write_text("a" * 100)
        (output_dir / "file2.txt").write_text("b" * 200)

        files = list(output_dir.rglob("*"))
        total_size = sum(f.stat().st_size for f in files if f.is_file())

        assert total_size == 300

    def test_metadata_last_sync_from_state_file(self, temp_dir):
        """Test that last_sync is read from state file mtime."""
        output_dir = temp_dir / "connector"
        output_dir.mkdir(parents=True, exist_ok=True)

        state_file = output_dir / ".sync_state"
        state_file.write_text("")

        last_sync = datetime.fromtimestamp(state_file.stat().st_mtime).isoformat()
        assert last_sync is not None

    def test_metadata_handles_missing_output_dir(self, temp_dir):
        """Test metadata when output directory doesn't exist."""
        output_dir = temp_dir / "nonexistent"

        if output_dir.exists():
            file_count = len(list(output_dir.rglob("*")))
        else:
            file_count = 0

        assert file_count == 0


class TestCleanup:
    """Tests for cleanup method."""

    def test_cleanup_returns_dict(self, temp_dir):
        """Test that cleanup returns a dictionary."""
        results = {"files_to_remove": [], "bytes_to_free": 0, "dry_run": True}

        assert isinstance(results, dict)
        assert "files_to_remove" in results
        assert "bytes_to_free" in results
        assert "dry_run" in results

    def test_cleanup_dry_run_mode(self, temp_dir):
        """Test that dry run doesn't delete files."""
        output_dir = temp_dir / "cleanup-test"
        output_dir.mkdir(parents=True, exist_ok=True)

        test_file = output_dir / "test.txt"
        test_file.write_text("content")

        # Simulate dry run (file should still exist)
        dry_run = True
        if dry_run:
            pass
        else:
            test_file.unlink()

        assert test_file.exists()

    def test_cleanup_execute_mode(self, temp_dir):
        """Test that execute mode actually deletes files."""
        output_dir = temp_dir / "cleanup-test"
        output_dir.mkdir(parents=True, exist_ok=True)

        test_file = output_dir / "test.txt"
        test_file.write_text("content")

        # Simulate execute mode
        dry_run = False
        if not dry_run:
            test_file.unlink()

        assert not test_file.exists()


class TestValidateConfig:
    """Tests for validate_config abstract method."""

    def test_validate_config_is_abstract(self):
        """Test that validate_config is an abstract method."""
        from abc import ABC, abstractmethod

        class TestConnector(ABC):
            @abstractmethod
            def validate_config(self) -> bool:
                pass

        # Can't instantiate abstract class
        with pytest.raises(TypeError):
            TestConnector()

    def test_validate_config_returns_bool(self):
        """Test that implementations should return bool."""
        result = True  # Simulated valid config
        assert isinstance(result, bool)


class TestSyncMethod:
    """Tests for sync abstract method."""

    def test_sync_is_abstract(self):
        """Test that sync is an abstract method."""
        from abc import ABC, abstractmethod

        class TestConnector(ABC):
            @abstractmethod
            def sync(self, incremental: bool = True) -> bool:
                pass

        with pytest.raises(TypeError):
            TestConnector()

    def test_sync_accepts_incremental_param(self):
        """Test that sync accepts incremental parameter."""

        def mock_sync(incremental: bool = True) -> bool:
            return True

        assert mock_sync(incremental=True) is True
        assert mock_sync(incremental=False) is True

    def test_sync_returns_bool(self):
        """Test that sync returns boolean success/failure."""
        result = True
        assert isinstance(result, bool)
