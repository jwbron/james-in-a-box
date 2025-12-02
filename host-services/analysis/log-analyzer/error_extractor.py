"""
Error Extractor - Identifies errors in aggregated logs.

Extracts errors based on:
- Severity level (ERROR, CRITICAL)
- Exception patterns (stack traces, exception messages)
- Known error indicators ("failed", "timeout", "refused", etc.)
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

# Add shared library to path
import sys
jib_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(jib_root / "shared"))

from jib_logging import get_logger

logger = get_logger("error-extractor")


@dataclass
class ExtractedError:
    """An error extracted from logs."""

    id: str  # Unique identifier
    timestamp: str
    source: str
    source_file: str
    severity: str
    message: str
    stack_trace: str | None = None
    context: dict = field(default_factory=dict)
    original: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source,
            "source_file": self.source_file,
            "severity": self.severity,
            "message": self.message,
            "stack_trace": self.stack_trace,
            "context": self.context,
            "original": self.original,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractedError":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            source=data["source"],
            source_file=data["source_file"],
            severity=data["severity"],
            message=data["message"],
            stack_trace=data.get("stack_trace"),
            context=data.get("context", {}),
            original=data.get("original", {}),
        )


class ErrorExtractor:
    """Extracts errors from aggregated logs.

    Identifies errors based on:
    - Severity level (ERROR, CRITICAL)
    - Exception patterns in message
    - Known error keywords

    Usage:
        extractor = ErrorExtractor()
        errors = extractor.extract_from_file(log_file)
        extractor.save_errors(errors, output_file)
    """

    # Severity levels considered errors
    ERROR_SEVERITIES = {"ERROR", "CRITICAL", "FATAL"}

    # Patterns that indicate errors even at INFO/WARNING level
    ERROR_PATTERNS = [
        r"exception",
        r"traceback",
        r"error:",
        r"failed",
        r"failure",
        r"timeout",
        r"refused",
        r"denied",
        r"not found",
        r"invalid",
        r"cannot",
        r"unable to",
        r"unexpected",
    ]

    # Compiled patterns for efficiency
    _error_regex = re.compile(
        "|".join(ERROR_PATTERNS),
        re.IGNORECASE,
    )

    # Stack trace patterns
    _stack_trace_patterns = [
        r"Traceback \(most recent call last\):",
        r"^\s+File \".*\", line \d+",
        r"^\s+at\s+\S+\(",  # JavaScript stack
        r"^\s+\d+\s+\|",  # Node.js stack
    ]

    _stack_trace_regex = re.compile(
        "|".join(_stack_trace_patterns),
        re.MULTILINE,
    )

    def __init__(self, logs_dir: Path | None = None):
        """Initialize the extractor.

        Args:
            logs_dir: Base directory for logs (default: ~/.jib-sharing/logs)
        """
        self.logs_dir = logs_dir or (Path.home() / ".jib-sharing" / "logs")
        self.errors_dir = self.logs_dir / "analysis" / "errors"
        self.errors_dir.mkdir(parents=True, exist_ok=True)

        self._error_counter = 0

    def _generate_error_id(self) -> str:
        """Generate a unique error ID."""
        self._error_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"err-{timestamp}-{self._error_counter:04d}"

    def _is_error_entry(self, entry: dict) -> bool:
        """Check if a log entry represents an error.

        Args:
            entry: Parsed log entry

        Returns:
            True if the entry is an error
        """
        # Check severity
        severity = entry.get("severity", entry.get("level", "")).upper()
        if severity in self.ERROR_SEVERITIES:
            return True

        # Check message for error patterns
        message = entry.get("message", "")
        if self._error_regex.search(message):
            return True

        # Check for exception info
        if entry.get("exc_info") or entry.get("exception"):
            return True

        return False

    def _extract_stack_trace(self, entry: dict) -> str | None:
        """Extract stack trace from log entry.

        Args:
            entry: Parsed log entry

        Returns:
            Stack trace string or None
        """
        # Check for explicit stack trace fields
        for field in ["stack_trace", "stackTrace", "traceback", "exc_info"]:
            if field in entry:
                trace = entry[field]
                if isinstance(trace, list):
                    return "\n".join(trace)
                return str(trace)

        # Check message for inline stack trace
        message = entry.get("message", "")
        if self._stack_trace_regex.search(message):
            return message

        return None

    def _extract_context(self, entry: dict) -> dict:
        """Extract context fields from log entry.

        Args:
            entry: Parsed log entry

        Returns:
            Context dictionary with relevant fields
        """
        context = {}

        # Standard context fields
        context_fields = [
            "task_id",
            "repository",
            "pr_number",
            "container_id",
            "trace_id",
            "span_id",
            "service",
            "component",
        ]

        for field in context_fields:
            if field in entry:
                context[field] = entry[field]

        # Check nested context
        if "context" in entry and isinstance(entry["context"], dict):
            context.update(entry["context"])

        return context

    def extract_from_file(self, log_file: Path) -> list[ExtractedError]:
        """Extract errors from a log file.

        Args:
            log_file: Path to aggregated log file (JSONL format)

        Returns:
            List of extracted errors
        """
        errors = []

        if not log_file.exists():
            logger.warning(f"Log file not found: {log_file}")
            return errors

        logger.info(f"Extracting errors from {log_file}")

        with open(log_file) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not self._is_error_entry(entry):
                    continue

                # Create error object
                error = ExtractedError(
                    id=self._generate_error_id(),
                    timestamp=entry.get("timestamp", ""),
                    source=entry.get("source", "unknown"),
                    source_file=entry.get("source_file", log_file.name),
                    severity=entry.get("severity", "ERROR").upper(),
                    message=entry.get("message", str(entry)),
                    stack_trace=self._extract_stack_trace(entry),
                    context=self._extract_context(entry),
                    original=entry,
                )
                errors.append(error)

        logger.info(f"Extracted {len(errors)} errors from {log_file}")
        return errors

    def extract_recent(self, hours: int = 24) -> list[ExtractedError]:
        """Extract errors from recent aggregated logs.

        Args:
            hours: Look back this many hours (default: 24)

        Returns:
            List of extracted errors
        """
        errors = []
        aggregated_dir = self.logs_dir / "aggregated"

        if not aggregated_dir.exists():
            logger.warning(f"Aggregated logs directory not found: {aggregated_dir}")
            return errors

        # Find recent log files
        cutoff = datetime.now().timestamp() - (hours * 3600)

        for log_file in aggregated_dir.glob("*.jsonl"):
            if log_file.stat().st_mtime >= cutoff:
                errors.extend(self.extract_from_file(log_file))

        # Sort by timestamp
        errors.sort(key=lambda e: e.timestamp or "")

        return errors

    def save_errors(
        self,
        errors: list[ExtractedError],
        output_file: Path | None = None,
    ) -> Path:
        """Save extracted errors to file.

        Args:
            errors: List of extracted errors
            output_file: Output file path (default: errors/YYYY-MM-DD.jsonl)

        Returns:
            Path to the saved file
        """
        if output_file is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.errors_dir / f"{date_str}.jsonl"

        with open(output_file, "w") as f:
            for error in errors:
                f.write(json.dumps(error.to_dict()) + "\n")

        logger.info(f"Saved {len(errors)} errors to {output_file}")
        return output_file

    def load_errors(self, error_file: Path) -> list[ExtractedError]:
        """Load errors from file.

        Args:
            error_file: Path to error file (JSONL format)

        Returns:
            List of extracted errors
        """
        errors = []

        if not error_file.exists():
            return errors

        with open(error_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    errors.append(ExtractedError.from_dict(data))
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Error loading entry: {e}")

        return errors

    def get_error_signature(self, error: ExtractedError) -> str:
        """Generate a signature for grouping similar errors.

        Args:
            error: Extracted error

        Returns:
            Signature string for grouping
        """
        # Normalize message (remove variable parts)
        message = error.message

        # Remove UUIDs, timestamps, numbers
        message = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>", message)
        message = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "<TIMESTAMP>", message)
        message = re.sub(r"\d+", "<N>", message)
        message = re.sub(r"'[^']*'", "'<STR>'", message)
        message = re.sub(r'"[^"]*"', '"<STR>"', message)

        return f"{error.source}:{error.severity}:{message[:100]}"


def main():
    """CLI for error extraction."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract errors from logs")
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Extract errors from the last N hours (default: 24)",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Extract from specific log file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path",
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

    # Run extraction
    extractor = ErrorExtractor()

    if args.file:
        errors = extractor.extract_from_file(args.file)
    else:
        errors = extractor.extract_recent(hours=args.hours)

    output_file = extractor.save_errors(errors, args.output)

    print(f"Extracted {len(errors)} errors to: {output_file}")

    # Show summary
    if errors:
        print("\nTop error sources:")
        sources = {}
        for error in errors:
            sources[error.source] = sources.get(error.source, 0) + 1

        for source, count in sorted(sources.items(), key=lambda x: -x[1])[:5]:
            print(f"  {source}: {count}")


if __name__ == "__main__":
    main()
