"""
Log Aggregator - Centralizes logs from multiple jib sources.

Collects logs from:
- Container logs (~/.jib-sharing/container-logs/)
- Context sync logs (~/context-sync/logs/)
- LLM traces (~/sharing/traces/)
- Host service logs

Aggregates into unified location (~/.jib-sharing/logs/) for analysis.
"""

import json

# Add shared library to path
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


jib_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(jib_root / "shared"))

from jib_logging import get_logger


logger = get_logger("log-aggregator")


@dataclass
class LogSource:
    """Configuration for a log source."""

    name: str
    path: Path
    pattern: str = "*.log"
    format: str = "json"  # json, jsonl, text
    enabled: bool = True


@dataclass
class AggregatedEntry:
    """A log entry with source metadata."""

    timestamp: str
    source: str
    source_file: str
    severity: str
    message: str
    original: dict = field(default_factory=dict)


class LogAggregator:
    """Centralizes logs from multiple sources.

    Creates a unified log directory with:
    - Aggregated daily log files
    - Symlinks to source directories
    - Index for fast queries

    Usage:
        aggregator = LogAggregator()
        aggregator.aggregate()  # Aggregate all sources
        aggregator.aggregate(since=datetime.now() - timedelta(hours=1))  # Recent only
    """

    # Default log sources
    DEFAULT_SOURCES = [
        LogSource(
            name="container",
            path=Path.home() / ".jib-sharing" / "container-logs",
            pattern="*.log",
            format="json",
        ),
        LogSource(
            name="context-sync",
            path=Path.home() / "context-sync" / "logs",
            pattern="sync_*.log",
            format="json",
        ),
        LogSource(
            name="traces",
            path=Path.home() / "sharing" / "traces",
            pattern="**/*.jsonl",
            format="jsonl",
        ),
    ]

    def __init__(
        self,
        output_dir: Path | None = None,
        sources: list[LogSource] | None = None,
    ):
        """Initialize the aggregator.

        Args:
            output_dir: Directory for aggregated logs (default: ~/.jib-sharing/logs)
            sources: List of log sources (default: standard jib sources)
        """
        self.output_dir = output_dir or (Path.home() / ".jib-sharing" / "logs")
        self.sources = sources or self.DEFAULT_SOURCES.copy()

        # Subdirectories
        self.aggregated_dir = self.output_dir / "aggregated"
        self.analysis_dir = self.output_dir / "analysis"
        self.errors_dir = self.analysis_dir / "errors"
        self.classifications_dir = self.analysis_dir / "classifications"
        self.summaries_dir = self.analysis_dir / "summaries"

        # Create directories
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create required directories."""
        for directory in [
            self.output_dir,
            self.aggregated_dir,
            self.analysis_dir,
            self.errors_dir,
            self.classifications_dir,
            self.summaries_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def _create_symlinks(self) -> None:
        """Create symlinks to source directories for easy navigation."""
        for source in self.sources:
            if not source.enabled or not source.path.exists():
                continue

            link_path = self.output_dir / source.name
            if link_path.exists():
                if link_path.is_symlink():
                    link_path.unlink()
                else:
                    continue  # Don't overwrite non-symlink

            try:
                link_path.symlink_to(source.path)
                logger.debug(f"Created symlink: {link_path} -> {source.path}")
            except OSError as e:
                logger.warning(f"Could not create symlink for {source.name}: {e}")

    def _parse_log_entry(self, line: str, source: LogSource) -> dict | None:
        """Parse a single log line.

        Args:
            line: Raw log line
            source: Source configuration

        Returns:
            Parsed log entry dict or None if parsing fails
        """
        line = line.strip()
        if not line:
            return None

        if source.format in ("json", "jsonl"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                # Not JSON, treat as text
                return {"message": line, "severity": "INFO"}
        else:
            return {"message": line, "severity": "INFO"}

    def _read_source_logs(
        self,
        source: LogSource,
        since: datetime | None = None,
    ) -> Iterator[AggregatedEntry]:
        """Read logs from a source.

        Args:
            source: Source configuration
            since: Only include logs after this time

        Yields:
            AggregatedEntry for each log line
        """
        if not source.path.exists():
            logger.debug(f"Source path does not exist: {source.path}")
            return

        # Find matching files
        files = list(source.path.glob(source.pattern))
        logger.debug(f"Found {len(files)} files for source {source.name}")

        for log_file in files:
            if not log_file.is_file():
                continue

            # Skip files older than cutoff based on mtime
            if since:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < since:
                    continue

            try:
                with open(log_file) as f:
                    for line in f:
                        entry = self._parse_log_entry(line, source)
                        if entry is None:
                            continue

                        # Extract standard fields
                        timestamp = entry.get("timestamp", entry.get("time", ""))
                        severity = entry.get("severity", entry.get("level", "INFO")).upper()
                        message = entry.get("message", entry.get("msg", str(entry)))

                        # Filter by time if specified
                        if since and timestamp:
                            try:
                                entry_time = datetime.fromisoformat(
                                    timestamp.replace("Z", "+00:00")
                                )
                                if entry_time.replace(tzinfo=None) < since:
                                    continue
                            except (ValueError, AttributeError):
                                pass

                        yield AggregatedEntry(
                            timestamp=timestamp,
                            source=source.name,
                            source_file=log_file.name,
                            severity=severity,
                            message=message,
                            original=entry,
                        )
            except Exception as e:
                logger.warning(f"Error reading {log_file}: {e}")

    def aggregate(
        self,
        since: datetime | None = None,
        output_file: Path | None = None,
    ) -> Path:
        """Aggregate logs from all sources.

        Args:
            since: Only include logs after this time (default: last 24 hours)
            output_file: Output file path (default: aggregated/YYYY-MM-DD.jsonl)

        Returns:
            Path to the aggregated log file
        """
        if since is None:
            since = datetime.now() - timedelta(hours=24)

        if output_file is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.aggregated_dir / f"{date_str}.jsonl"

        # Create symlinks
        self._create_symlinks()

        # Collect all entries
        entries = []
        for source in self.sources:
            if not source.enabled:
                continue

            logger.info(f"Reading logs from {source.name}...")
            source_entries = list(self._read_source_logs(source, since))
            logger.info(f"  Found {len(source_entries)} entries")
            entries.extend(source_entries)

        # Sort by timestamp
        def get_sort_key(e: AggregatedEntry) -> str:
            return e.timestamp or ""

        entries.sort(key=get_sort_key)

        # Write aggregated file
        with open(output_file, "w") as f:
            for entry in entries:
                record = {
                    "timestamp": entry.timestamp,
                    "source": entry.source,
                    "source_file": entry.source_file,
                    "severity": entry.severity,
                    "message": entry.message,
                    **entry.original,
                }
                f.write(json.dumps(record) + "\n")

        logger.info(f"Aggregated {len(entries)} entries to {output_file}")

        # Update index
        self._update_index(output_file, len(entries))

        return output_file

    def _update_index(self, log_file: Path, entry_count: int) -> None:
        """Update the log index with aggregation info."""
        index_file = self.output_dir / "index.json"

        # Load existing index
        index = {"files": [], "last_updated": None}
        if index_file.exists():
            try:
                with open(index_file) as f:
                    index = json.load(f)
            except json.JSONDecodeError:
                pass

        # Add/update file entry
        file_entry = {
            "path": str(log_file),
            "date": log_file.stem,
            "entry_count": entry_count,
            "aggregated_at": datetime.now().isoformat(),
        }

        # Remove existing entry for same date
        index["files"] = [f for f in index.get("files", []) if f.get("date") != log_file.stem]
        index["files"].append(file_entry)
        index["last_updated"] = datetime.now().isoformat()

        # Write index
        with open(index_file, "w") as f:
            json.dump(index, f, indent=2)

    def get_aggregated_file(self, date: datetime | None = None) -> Path | None:
        """Get the aggregated log file for a specific date.

        Args:
            date: Date to get logs for (default: today)

        Returns:
            Path to aggregated file or None if not found
        """
        if date is None:
            date = datetime.now()

        date_str = date.strftime("%Y-%m-%d")
        log_file = self.aggregated_dir / f"{date_str}.jsonl"

        return log_file if log_file.exists() else None

    def add_source(self, source: LogSource) -> None:
        """Add a log source.

        Args:
            source: Log source configuration
        """
        # Remove existing source with same name
        self.sources = [s for s in self.sources if s.name != source.name]
        self.sources.append(source)


def main():
    """CLI for log aggregation."""
    import argparse

    parser = argparse.ArgumentParser(description="Aggregate jib logs")
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Aggregate logs from the last N hours (default: 24)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: ~/.jib-sharing/logs/aggregated/YYYY-MM-DD.jsonl)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)

    # Run aggregation
    aggregator = LogAggregator()
    since = datetime.now() - timedelta(hours=args.hours)
    output_file = aggregator.aggregate(since=since, output_file=args.output)

    print(f"Logs aggregated to: {output_file}")


if __name__ == "__main__":
    main()
