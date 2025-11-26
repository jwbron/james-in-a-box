"""
Base connector class for context-sync.

All connectors should inherit from BaseConnector and implement the required methods.
"""

import logging
import pickle
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path


class BaseConnector(ABC):
    """Base class for all context-sync connectors."""

    def __init__(self, name: str, output_dir: Path):
        """Initialize the connector.

        Args:
            name: Name of the connector (e.g., 'confluence', 'github')
            output_dir: Directory where synced content should be stored
        """
        self.name = name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Set up logging
        self.logger = self._setup_logger()

        # Sync state management
        self.sync_state_file = self.output_dir / ".sync_state"

    def _setup_logger(self) -> logging.Logger:
        """Set up logger for this connector."""
        logger = logging.getLogger(f"context-sync.{self.name}")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(f"[{self.name}] %(levelname)s: %(message)s")
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        return logger

    def _load_sync_state(self) -> dict:
        """Load sync state from file."""
        if self.sync_state_file.exists():
            try:
                with open(self.sync_state_file, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load sync state: {e}")
        return {}

    def _save_sync_state(self, state: dict):
        """Save sync state to file."""
        try:
            with open(self.sync_state_file, "wb") as f:
                pickle.dump(state, f)
        except Exception as e:
            self.logger.error(f"Failed to save sync state: {e}")

    @abstractmethod
    def validate_config(self) -> bool:
        """Validate connector configuration.

        Returns:
            True if configuration is valid, False otherwise
        """

    @abstractmethod
    def sync(self, incremental: bool = True) -> bool:
        """Run the sync operation.

        Args:
            incremental: If True, only sync changed content. If False, sync everything.

        Returns:
            True if sync was successful, False otherwise
        """

    def get_sync_metadata(self) -> dict:
        """Get metadata about the last sync.

        Returns:
            Dictionary with sync metadata (last sync time, file count, etc.)
        """
        metadata = {
            "connector": self.name,
            "output_dir": str(self.output_dir),
            "last_sync": None,
            "file_count": 0,
            "total_size": 0,
        }

        # Count files and calculate size
        if self.output_dir.exists():
            files = list(self.output_dir.rglob("*"))
            metadata["file_count"] = len([f for f in files if f.is_file()])
            metadata["total_size"] = sum(f.stat().st_size for f in files if f.is_file())

        # Get last sync time from state file
        if self.sync_state_file.exists():
            metadata["last_sync"] = datetime.fromtimestamp(
                self.sync_state_file.stat().st_mtime
            ).isoformat()

        return metadata

    def cleanup(self, dry_run: bool = True) -> dict:
        """Clean up old or orphaned files.

        Args:
            dry_run: If True, only report what would be deleted

        Returns:
            Dictionary with cleanup results
        """
        results = {"files_to_remove": [], "bytes_to_free": 0, "dry_run": dry_run}

        self.logger.info(f"Cleanup not implemented for {self.name}")
        return results
