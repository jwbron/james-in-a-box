"""
Error Classifier - Claude-powered error classification.

Uses Claude to analyze and classify errors:
- Category (transient, configuration, bug, external, resource, unknown)
- Severity (low, medium, high, critical)
- Root cause analysis
- Recommendations

Includes caching to avoid re-classifying known error patterns.
"""

import hashlib
import json
import subprocess

# Add shared library to path
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


jib_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(jib_root / "shared"))

from jib_logging import get_logger

from .error_extractor import ExtractedError


logger = get_logger("error-classifier")


@dataclass
class ClassifiedError:
    """An error with Claude-generated classification."""

    # Original error info
    error_id: str
    timestamp: str
    source: str
    message: str
    stack_trace: str | None
    context: dict

    # Claude classification
    category: str  # transient, configuration, bug, external, resource, unknown
    severity: str  # low, medium, high, critical
    confidence: str  # high, medium, low - how confident Claude is in this classification
    root_cause: str
    recommendation: str
    related_errors: list[str] = field(default_factory=list)

    # Metadata
    signature: str = ""
    classification_model: str = ""
    classification_timestamp: str = ""
    occurrence_count: int = 1

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "error_id": self.error_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "message": self.message,
            "stack_trace": self.stack_trace,
            "context": self.context,
            "category": self.category,
            "severity": self.severity,
            "confidence": self.confidence,
            "root_cause": self.root_cause,
            "recommendation": self.recommendation,
            "related_errors": self.related_errors,
            "signature": self.signature,
            "classification_model": self.classification_model,
            "classification_timestamp": self.classification_timestamp,
            "occurrence_count": self.occurrence_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClassifiedError":
        """Create from dictionary."""
        return cls(
            error_id=data["error_id"],
            timestamp=data["timestamp"],
            source=data["source"],
            message=data["message"],
            stack_trace=data.get("stack_trace"),
            context=data.get("context", {}),
            category=data["category"],
            severity=data["severity"],
            confidence=data.get("confidence", "medium"),
            root_cause=data["root_cause"],
            recommendation=data["recommendation"],
            related_errors=data.get("related_errors", []),
            signature=data.get("signature", ""),
            classification_model=data.get("classification_model", ""),
            classification_timestamp=data.get("classification_timestamp", ""),
            occurrence_count=data.get("occurrence_count", 1),
        )


class ErrorClassifier:
    """Claude-powered error classification.

    Classifies errors using Claude:
    - Groups similar errors by signature
    - Caches classifications to avoid redundant API calls
    - Batches analysis for efficiency

    Usage:
        classifier = ErrorClassifier()
        classified = classifier.classify_errors(errors)
        classifier.save_classifications(classified, output_file)
    """

    # Prompt version - increment when prompt changes significantly to invalidate cache
    PROMPT_VERSION = "1.1"

    # Classification prompt template with few-shot examples
    CLASSIFICATION_PROMPT = """You are analyzing errors from a software system called "jib" (james-in-a-box).

jib is a Docker-sandboxed Claude Code agent system with these components:
- **Host services**: github-watcher (PR monitoring), slack-receiver (task intake), context-sync (data sync)
- **Container**: Runs Claude Code CLI for task processing in isolated Docker environment
- **Shared libraries**: jib_logging (structured logging), notifications (Slack DM)

For each error below, provide a JSON response with:

1. **category**: One of:
   - `transient`: Temporary failure that usually resolves on retry (network timeout, rate limit)
   - `configuration`: Misconfiguration requiring user action (missing API key, wrong path)
   - `bug`: Code defect requiring fix (null pointer, logic error)
   - `external`: External service failure (GitHub API down, auth server error)
   - `resource`: Resource exhaustion (disk full, memory limit)
   - `unknown`: Cannot classify from available information

2. **severity**: One of:
   - `low`: Cosmetic or minor issue, system continues normally
   - `medium`: Degraded functionality, workaround possible
   - `high`: Feature broken, user impacted
   - `critical`: System down or data loss risk

3. **confidence**: One of:
   - `high`: Clear error pattern, confident in classification
   - `medium`: Reasonable classification but some uncertainty
   - `low`: Unclear error, classification is a best guess

4. **root_cause**: Your analysis of the most likely cause (1-2 sentences)

5. **recommendation**: Specific steps to investigate or fix (1-3 bullet points)

## Examples

**Example 1 - Transient error:**
Error: "GitHub API rate limit exceeded. Retry after 2025-01-15T10:30:00Z"
```json
{{
  "category": "transient",
  "severity": "medium",
  "confidence": "high",
  "root_cause": "The GitHub API is rate limiting requests due to high request volume.",
  "recommendation": "- Wait for rate limit to reset\\n- Implement exponential backoff\\n- Consider batching requests"
}}
```

**Example 2 - Configuration error:**
Error: "GITHUB_TOKEN environment variable not set"
```json
{{
  "category": "configuration",
  "severity": "high",
  "confidence": "high",
  "root_cause": "Required environment variable is missing from the container configuration.",
  "recommendation": "- Add GITHUB_TOKEN to .env file\\n- Verify token has required permissions\\n- Restart the container after adding"
}}
```

**Example 3 - Bug:**
Error: "TypeError: Cannot read property 'id' of undefined at processTask"
```json
{{
  "category": "bug",
  "severity": "high",
  "confidence": "high",
  "root_cause": "Code is accessing a property on an undefined object, likely due to missing null check.",
  "recommendation": "- Add null/undefined check before accessing .id\\n- Investigate why the object is undefined\\n- Add defensive coding patterns"
}}
```

**Example 4 - External service:**
Error: "Connection refused to api.slack.com:443"
```json
{{
  "category": "external",
  "severity": "medium",
  "confidence": "medium",
  "root_cause": "Cannot connect to Slack API - could be network issue or Slack outage.",
  "recommendation": "- Check Slack status page\\n- Verify network connectivity\\n- Implement retry with backoff"
}}
```

**Example 5 - Resource exhaustion:**
Error: "OSError: [Errno 28] No space left on device"
```json
{{
  "category": "resource",
  "severity": "critical",
  "confidence": "high",
  "root_cause": "Disk is full, preventing file operations.",
  "recommendation": "- Clear old logs and temp files\\n- Increase disk allocation\\n- Add disk space monitoring"
}}
```

---

ERROR TO ANALYZE:

Source: {source}
Timestamp: {timestamp}
Message: {message}
{stack_trace_section}
Context: {context}
Occurrences: {occurrence_count} time(s)

---

Respond with ONLY a JSON object (no markdown, no explanation):
"""

    def __init__(
        self,
        logs_dir: Path | None = None,
        cache_file: Path | None = None,
        model: str = "claude-3-5-haiku-latest",
        timeout: int = 60,
    ):
        """Initialize the classifier.

        Args:
            logs_dir: Base directory for logs (default: ~/.jib-sharing/logs)
            cache_file: Path to classification cache (default: logs/analysis/classification_cache.json)
            model: Claude model to use for classification
            timeout: Timeout in seconds for Claude CLI calls (default: 60)
        """
        self.logs_dir = logs_dir or (Path.home() / ".jib-sharing" / "logs")
        self.classifications_dir = self.logs_dir / "analysis" / "classifications"
        self.classifications_dir.mkdir(parents=True, exist_ok=True)

        self.cache_file = cache_file or (self.logs_dir / "analysis" / "classification_cache.json")
        self.model = model
        self.timeout = timeout

        # Load cache
        self._cache = self._load_cache()

    def _load_cache(self) -> dict:
        """Load classification cache from file.

        Cache entries are versioned by prompt version. When the prompt changes
        significantly, increment PROMPT_VERSION to invalidate old cache entries.
        """
        if not self.cache_file.exists():
            return {"_meta": {"version": self.PROMPT_VERSION}, "entries": {}}

        try:
            with open(self.cache_file) as f:
                data = json.load(f)

            # Check cache version - if different, start fresh
            meta = data.get("_meta", {})
            cached_version = meta.get("version", "1.0")

            if cached_version != self.PROMPT_VERSION:
                logger.info(
                    f"Cache version mismatch ({cached_version} vs {self.PROMPT_VERSION}), "
                    f"starting with fresh cache"
                )
                return {"_meta": {"version": self.PROMPT_VERSION}, "entries": {}}

            # Handle old cache format (flat dict without _meta)
            if "entries" not in data:
                # Migrate old format
                logger.info("Migrating old cache format to new versioned format")
                return {
                    "_meta": {"version": self.PROMPT_VERSION},
                    "entries": {k: v for k, v in data.items() if k != "_meta"},
                }

            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Error loading cache: {e}")
            return {"_meta": {"version": self.PROMPT_VERSION}, "entries": {}}

    def _save_cache(self) -> None:
        """Save classification cache to file."""
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self._cache, f, indent=2)
        except OSError as e:
            logger.warning(f"Error saving cache: {e}")

    def _get_signature(self, error: ExtractedError) -> str:
        """Generate a signature for grouping similar errors.

        Uses a hash of normalized message + source + severity.
        Normalizes variable parts like UUIDs, timestamps, numbers, paths, IPs, URLs.
        """
        import re

        message = error.message

        # Normalize variable parts (order matters - more specific patterns first)

        # UUIDs
        message = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "<UUID>",
            message,
            flags=re.IGNORECASE,
        )

        # Timestamps (ISO format and common variants)
        message = re.sub(
            r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?",
            "<TIMESTAMP>",
            message,
        )

        # HTTP/HTTPS URLs (before paths to avoid partial matches)
        message = re.sub(
            r"https?://[^\s\"'<>]+",
            "<URL>",
            message,
        )

        # IP addresses (IPv4)
        message = re.sub(
            r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            "<IP>",
            message,
        )

        # File paths (Unix and Windows style)
        message = re.sub(
            r"(/[\w./-]+)+",
            "<PATH>",
            message,
        )
        message = re.sub(
            r"[A-Za-z]:\\[\w\\.-]+",
            "<PATH>",
            message,
        )

        # Port numbers (after IP to avoid double-matching)
        message = re.sub(
            r":\d{2,5}\b",
            ":<PORT>",
            message,
        )

        # Generic numbers (last, as other patterns contain numbers)
        message = re.sub(r"\b\d+\b", "<N>", message)

        signature_input = f"{error.source}:{error.severity}:{message[:200]}"
        return hashlib.sha256(signature_input.encode()).hexdigest()[:16]

    def _call_claude(self, prompt: str) -> dict | None:
        """Call Claude API for classification.

        Args:
            prompt: Classification prompt

        Returns:
            Parsed JSON response or None on failure
        """
        try:
            # Use claude CLI with --print for non-interactive output
            result = subprocess.run(
                [
                    "claude",
                    "--print",
                    "--model",
                    self.model,
                    "-p",
                    prompt,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )

            if result.returncode != 0:
                logger.warning(f"Claude CLI failed: {result.stderr}")
                return None

            # Parse JSON from response
            response = result.stdout.strip()

            # Extract JSON from markdown code block if present
            if "```json" in response:
                start = response.index("```json") + 7
                end = response.index("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.index("```") + 3
                end = response.index("```", start)
                response = response[start:end].strip()

            return json.loads(response)

        except subprocess.TimeoutExpired:
            logger.warning("Claude CLI timed out")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Claude response: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error calling Claude: {e}")
            return None

    def _classify_single(
        self,
        error: ExtractedError,
        occurrence_count: int = 1,
    ) -> ClassifiedError | None:
        """Classify a single error using Claude.

        Args:
            error: Error to classify
            occurrence_count: Number of similar errors

        Returns:
            ClassifiedError or None on failure
        """
        # Build prompt
        stack_trace_section = ""
        if error.stack_trace:
            stack_trace_section = f"\nStack Trace:\n{error.stack_trace[:1000]}\n"

        prompt = self.CLASSIFICATION_PROMPT.format(
            source=error.source,
            timestamp=error.timestamp,
            message=error.message[:500],
            stack_trace_section=stack_trace_section,
            context=json.dumps(error.context, indent=2)[:500],
            occurrence_count=occurrence_count,
        )

        # Call Claude
        result = self._call_claude(prompt)
        if result is None:
            return None

        # Create classified error
        return ClassifiedError(
            error_id=error.id,
            timestamp=error.timestamp,
            source=error.source,
            message=error.message,
            stack_trace=error.stack_trace,
            context=error.context,
            category=result.get("category", "unknown"),
            severity=result.get("severity", "medium"),
            confidence=result.get("confidence", "medium"),
            root_cause=result.get("root_cause", "Unable to determine"),
            recommendation=result.get("recommendation", "Investigate manually"),
            signature=self._get_signature(error),
            classification_model=self.model,
            classification_timestamp=datetime.now().isoformat(),
            occurrence_count=occurrence_count,
        )

    def classify_errors(
        self,
        errors: list[ExtractedError],
        max_classifications: int = 50,
    ) -> list[ClassifiedError]:
        """Classify a list of errors.

        Groups similar errors by signature and classifies unique patterns.
        Uses cache to avoid re-classifying known patterns.

        Args:
            errors: List of errors to classify
            max_classifications: Maximum number of Claude API calls

        Returns:
            List of classified errors
        """
        if not errors:
            return []

        # Group errors by signature
        groups: dict[str, list[ExtractedError]] = {}
        for error in errors:
            signature = self._get_signature(error)
            if signature not in groups:
                groups[signature] = []
            groups[signature].append(error)

        logger.info(f"Found {len(groups)} unique error patterns from {len(errors)} errors")

        classified = []
        new_classifications = 0

        cache_entries = self._cache.get("entries", {})

        for signature, group in groups.items():
            # Check cache first
            if signature in cache_entries:
                logger.debug(f"Using cached classification for {signature}")
                cached = cache_entries[signature]
                for error in group:
                    classified_error = ClassifiedError(
                        error_id=error.id,
                        timestamp=error.timestamp,
                        source=error.source,
                        message=error.message,
                        stack_trace=error.stack_trace,
                        context=error.context,
                        category=cached["category"],
                        severity=cached["severity"],
                        confidence=cached.get("confidence", "medium"),
                        root_cause=cached["root_cause"],
                        recommendation=cached["recommendation"],
                        signature=signature,
                        classification_model=cached.get("model", "cached"),
                        classification_timestamp=cached.get("timestamp", ""),
                        occurrence_count=len(group),
                    )
                    classified.append(classified_error)
                continue

            # New pattern - classify with Claude
            if new_classifications >= max_classifications:
                logger.warning(
                    f"Reached max classifications ({max_classifications}), "
                    f"skipping remaining patterns"
                )
                # Add unclassified
                for error in group:
                    classified.append(
                        ClassifiedError(
                            error_id=error.id,
                            timestamp=error.timestamp,
                            source=error.source,
                            message=error.message,
                            stack_trace=error.stack_trace,
                            context=error.context,
                            category="unknown",
                            severity="medium",
                            confidence="low",
                            root_cause="Classification limit reached",
                            recommendation="Run classifier again to process remaining errors",
                            signature=signature,
                            occurrence_count=len(group),
                        )
                    )
                continue

            logger.info(f"Classifying new pattern: {signature} ({len(group)} occurrences)")

            # Classify representative error
            result = self._classify_single(group[0], len(group))
            new_classifications += 1

            if result:
                # Cache the classification
                if "entries" not in self._cache:
                    self._cache["entries"] = {}
                self._cache["entries"][signature] = {
                    "category": result.category,
                    "severity": result.severity,
                    "confidence": result.confidence,
                    "root_cause": result.root_cause,
                    "recommendation": result.recommendation,
                    "model": self.model,
                    "timestamp": datetime.now().isoformat(),
                }

                # Apply to all errors in group
                for error in group:
                    classified_error = ClassifiedError(
                        error_id=error.id,
                        timestamp=error.timestamp,
                        source=error.source,
                        message=error.message,
                        stack_trace=error.stack_trace,
                        context=error.context,
                        category=result.category,
                        severity=result.severity,
                        confidence=result.confidence,
                        root_cause=result.root_cause,
                        recommendation=result.recommendation,
                        signature=signature,
                        classification_model=self.model,
                        classification_timestamp=datetime.now().isoformat(),
                        occurrence_count=len(group),
                    )
                    classified.append(classified_error)
            else:
                # Classification failed
                for error in group:
                    classified.append(
                        ClassifiedError(
                            error_id=error.id,
                            timestamp=error.timestamp,
                            source=error.source,
                            message=error.message,
                            stack_trace=error.stack_trace,
                            context=error.context,
                            category="unknown",
                            severity="medium",
                            confidence="low",
                            root_cause="Classification failed",
                            recommendation="Review error manually",
                            signature=signature,
                            occurrence_count=len(group),
                        )
                    )

        # Save cache
        self._save_cache()

        logger.info(f"Classified {len(classified)} errors ({new_classifications} new API calls)")

        return classified

    def save_classifications(
        self,
        classifications: list[ClassifiedError],
        output_file: Path | None = None,
    ) -> Path:
        """Save classifications to file.

        Args:
            classifications: List of classified errors
            output_file: Output file path (default: classifications/YYYY-MM-DD.json)

        Returns:
            Path to saved file
        """
        if output_file is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.classifications_dir / f"{date_str}.json"

        # Group by category for structured output
        output = {
            "generated_at": datetime.now().isoformat(),
            "total_errors": len(classifications),
            "by_category": {},
            "by_severity": {},
            "errors": [c.to_dict() for c in classifications],
        }

        for c in classifications:
            if c.category not in output["by_category"]:
                output["by_category"][c.category] = 0
            output["by_category"][c.category] += 1

            if c.severity not in output["by_severity"]:
                output["by_severity"][c.severity] = 0
            output["by_severity"][c.severity] += 1

        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Saved {len(classifications)} classifications to {output_file}")
        return output_file

    def load_classifications(self, classification_file: Path) -> list[ClassifiedError]:
        """Load classifications from file.

        Args:
            classification_file: Path to classification file

        Returns:
            List of classified errors
        """
        if not classification_file.exists():
            return []

        with open(classification_file) as f:
            data = json.load(f)

        return [ClassifiedError.from_dict(e) for e in data.get("errors", [])]


def main():
    """CLI for error classification."""
    import argparse

    parser = argparse.ArgumentParser(description="Classify errors using Claude")
    parser.add_argument(
        "--errors",
        type=Path,
        help="Path to extracted errors file (JSONL)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=50,
        help="Maximum number of Claude API calls (default: 50)",
    )
    parser.add_argument(
        "--model",
        default="claude-3-5-haiku-latest",
        help="Claude model to use (default: claude-3-5-haiku-latest)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout in seconds for Claude CLI calls (default: 60)",
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

    # Load errors
    from .error_extractor import ErrorExtractor

    extractor = ErrorExtractor()

    if args.errors:
        errors = extractor.load_errors(args.errors)
    else:
        errors = extractor.extract_recent(hours=24)

    if not errors:
        print("No errors to classify")
        return

    print(f"Found {len(errors)} errors to classify")

    # Classify
    classifier = ErrorClassifier(model=args.model, timeout=args.timeout)
    classified = classifier.classify_errors(errors, max_classifications=args.max_calls)

    # Save
    output_file = classifier.save_classifications(classified, args.output)
    print(f"Classifications saved to: {output_file}")

    # Summary
    print("\nClassification Summary:")
    categories = {}
    severities = {}
    for c in classified:
        categories[c.category] = categories.get(c.category, 0) + 1
        severities[c.severity] = severities.get(c.severity, 0) + 1

    print("\nBy Category:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    print("\nBy Severity:")
    for sev, count in sorted(severities.items(), key=lambda x: -x[1]):
        print(f"  {sev}: {count}")


if __name__ == "__main__":
    main()
