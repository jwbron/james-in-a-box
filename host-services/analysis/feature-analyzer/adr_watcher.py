#!/usr/bin/env python3
"""
ADR Watcher - Automated ADR Detection Service (Phase 3)

This module monitors the ADR directories for status changes (ADRs moving to
implemented/) and triggers documentation sync automatically.

It runs as a systemd service on a 15-minute interval.

By default, uses Phase 3 mode which:
- Generates documentation updates using jib containers (LLM-powered)
- Creates PRs automatically for review

State persistence:
- Tracks which ADRs have been processed
- Persists state across restarts in ~/.local/share/feature-analyzer/state.json

Usage:
  # Run the watcher (default: Phase 3 with jib)
  python adr_watcher.py watch

  # Run without jib containers (simple updates)
  python adr_watcher.py watch --no-jib

  # Check for new implemented ADRs without triggering sync
  python adr_watcher.py check

  # Reset state (reprocess all ADRs)
  python adr_watcher.py reset
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class WatcherState:
    """Persistent state for the ADR watcher."""

    # Set of ADR filenames that have been processed
    processed_adrs: set[str] = field(default_factory=set)

    # Last time the watcher ran successfully
    last_check_timestamp: str | None = None

    # Version for future state migrations
    version: int = 1

    def to_dict(self) -> dict:
        """Serialize state to dict for JSON storage."""
        return {
            "processed_adrs": list(self.processed_adrs),
            "last_check_timestamp": self.last_check_timestamp,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WatcherState":
        """Deserialize state from dict."""
        return cls(
            processed_adrs=set(data.get("processed_adrs", [])),
            last_check_timestamp=data.get("last_check_timestamp"),
            version=data.get("version", 1),
        )


@dataclass
class NewADR:
    """Represents a newly detected implemented ADR."""

    path: Path
    filename: str
    detected_at: str


class ADRWatcher:
    """Watches ADR directories for status changes."""

    def __init__(self, repo_root: Path, state_dir: Path | None = None):
        self.repo_root = repo_root
        self.adr_dir = repo_root / "docs" / "adr"
        self.implemented_dir = self.adr_dir / "implemented"

        # State persistence
        if state_dir is None:
            state_dir = Path.home() / ".local" / "share" / "feature-analyzer"
        self.state_dir = state_dir
        self.state_file = state_dir / "state.json"

        self.state = self._load_state()

    def _load_state(self) -> WatcherState:
        """Load state from disk or create new."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                return WatcherState.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not load state file, starting fresh: {e}")
                return WatcherState()
        return WatcherState()

    def _save_state(self) -> None:
        """Persist state to disk."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state.to_dict(), f, indent=2)

    def get_implemented_adrs(self) -> list[Path]:
        """Get all ADRs in the implemented directory."""
        if not self.implemented_dir.exists():
            return []
        return sorted(self.implemented_dir.glob("ADR-*.md"))

    def detect_new_adrs(self) -> list[NewADR]:
        """Detect ADRs that have been moved to implemented/ since last check."""
        new_adrs = []
        current_time = datetime.now(UTC).isoformat()

        for adr_path in self.get_implemented_adrs():
            filename = adr_path.name
            if filename not in self.state.processed_adrs:
                new_adrs.append(
                    NewADR(
                        path=adr_path,
                        filename=filename,
                        detected_at=current_time,
                    )
                )

        return new_adrs

    def mark_processed(self, adr: NewADR) -> None:
        """Mark an ADR as processed."""
        self.state.processed_adrs.add(adr.filename)
        self._save_state()

    def update_last_check(self) -> None:
        """Update the last check timestamp."""
        self.state.last_check_timestamp = datetime.now(UTC).isoformat()
        self._save_state()

    def reset_state(self) -> None:
        """Reset all state (for reprocessing)."""
        self.state = WatcherState()
        self._save_state()
        print("State reset. All ADRs will be reprocessed on next run.")

    def trigger_sync(
        self, adr: NewADR, dry_run: bool = False, phase3: bool = False, use_jib: bool = False
    ) -> bool:
        """
        Trigger documentation sync for a newly implemented ADR.

        Args:
            adr: The newly detected ADR
            dry_run: If True, don't make actual changes
            phase3: If True, use Phase 3 generation and PR creation
            use_jib: If True and phase3, use jib containers for LLM generation

        Returns True if sync was successful.
        """
        relative_path = adr.path.relative_to(self.repo_root)

        if dry_run:
            mode = "generate (Phase 3)" if phase3 else "sync-docs (Phase 2)"
            print(f"  [DRY RUN] Would run {mode} for: {relative_path}")
            return True

        # Import and use the existing sync functionality
        try:
            script_dir = Path(__file__).parent
            analyzer_script = script_dir / "feature-analyzer.py"

            if phase3:
                # Phase 3: Generate updates and create PR
                cmd = [
                    sys.executable,
                    str(analyzer_script),
                    "generate",
                    "--adr",
                    str(relative_path),
                    "--repo-root",
                    str(self.repo_root),
                ]
                if use_jib:
                    cmd.append("--use-jib")
            else:
                # Phase 2: Sync analysis only (dry-run)
                cmd = [
                    sys.executable,
                    str(analyzer_script),
                    "sync-docs",
                    "--adr",
                    str(relative_path),
                    "--repo-root",
                    str(self.repo_root),
                    "--dry-run",  # Phase 2 still uses dry-run by default
                ]

            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                cwd=self.repo_root,
            )

            if result.returncode == 0:
                mode = "Generation" if phase3 else "Sync analysis"
                print(f"  ✓ {mode} complete for: {relative_path}")
                if result.stdout:
                    # Indent the output
                    for line in result.stdout.strip().split("\n"):
                        print(f"    {line}")
                return True
            else:
                print(f"  ✗ Processing failed for: {relative_path}")
                if result.stderr:
                    print(f"    Error: {result.stderr}")
                if result.stdout:
                    # Show output even on failure
                    for line in result.stdout.strip().split("\n")[-10:]:
                        print(f"    {line}")
                return False

        except Exception as e:
            print(f"  ✗ Error triggering sync for {relative_path}: {e}")
            return False

    def run_check(self, dry_run: bool = False) -> list[NewADR]:
        """
        Check for new implemented ADRs.

        Returns list of newly detected ADRs (without processing them).
        """
        new_adrs = self.detect_new_adrs()

        if not new_adrs:
            print("No new implemented ADRs detected.")
        else:
            print(f"Found {len(new_adrs)} new implemented ADR(s):")
            for adr in new_adrs:
                print(f"  - {adr.filename}")

        return new_adrs

    def run_watch(self, dry_run: bool = False, phase3: bool = False, use_jib: bool = False) -> int:
        """
        Main watch loop - detect and process new ADRs.

        Args:
            dry_run: If True, don't make actual changes
            phase3: If True, use Phase 3 generation and PR creation
            use_jib: If True and phase3, use jib containers for LLM generation

        Returns the number of ADRs processed.
        """
        mode_str = "Phase 3 (with PR creation)" if phase3 else "Phase 2 (analysis only)"
        print(f"ADR Watcher starting at {datetime.now(UTC).isoformat()}")
        print(f"Mode: {mode_str}")
        print(f"Checking: {self.implemented_dir}")

        if self.state.last_check_timestamp:
            print(f"Last check: {self.state.last_check_timestamp}")
        else:
            print("First run - scanning all implemented ADRs")

        new_adrs = self.detect_new_adrs()

        if not new_adrs:
            print("\nNo new implemented ADRs to process.")
            self.update_last_check()
            return 0

        print(f"\nFound {len(new_adrs)} new implemented ADR(s):")

        processed_count = 0
        for adr in new_adrs:
            print(f"\nProcessing: {adr.filename}")

            success = self.trigger_sync(adr, dry_run=dry_run, phase3=phase3, use_jib=use_jib)

            if success:
                if not dry_run:
                    self.mark_processed(adr)
                processed_count += 1

        self.update_last_check()

        print(f"\nProcessed {processed_count}/{len(new_adrs)} ADR(s)")
        return processed_count


def main():
    parser = argparse.ArgumentParser(
        description="ADR Watcher - Automated ADR Detection (Phase 3 by default)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # watch command
    watch_parser = subparsers.add_parser(
        "watch", help="Run the watcher to detect and process new implemented ADRs"
    )
    watch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect ADRs but do not trigger sync or update state",
    )
    watch_parser.add_argument(
        "--no-jib",
        action="store_true",
        help="Disable jib containers for LLM generation (use simple updates instead)",
    )
    watch_parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root directory (auto-detected if not specified)",
    )

    # check command
    check_parser = subparsers.add_parser(
        "check", help="Check for new implemented ADRs without processing"
    )
    check_parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root directory (auto-detected if not specified)",
    )

    # reset command
    reset_parser = subparsers.add_parser("reset", help="Reset state to reprocess all ADRs")
    reset_parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root directory (auto-detected if not specified)",
    )

    # status command
    status_parser = subparsers.add_parser("status", help="Show watcher status")
    status_parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root directory (auto-detected if not specified)",
    )

    args = parser.parse_args()

    # Auto-detect repo root if not specified
    repo_root = args.repo_root
    if repo_root is None:
        # Try to find repo root from script location
        script_dir = Path(__file__).parent
        # Navigate up: feature-analyzer -> analysis -> host-services -> james-in-a-box
        repo_root = script_dir.parent.parent.parent
        if not (repo_root / ".git").exists() and not (repo_root / "docs" / "adr").exists():
            print("Error: Could not auto-detect repository root. Use --repo-root option.")
            sys.exit(1)

    watcher = ADRWatcher(repo_root)

    if args.command == "watch":
        # Phase 3 with jib is now the default behavior
        count = watcher.run_watch(
            dry_run=args.dry_run,
            phase3=True,  # Always use Phase 3
            use_jib=not args.no_jib,  # Use jib by default unless --no-jib is passed
        )
        sys.exit(0 if count >= 0 else 1)

    elif args.command == "check":
        watcher.run_check()

    elif args.command == "reset":
        watcher.reset_state()

    elif args.command == "status":
        print("ADR Watcher Status")
        print("=" * 40)
        print(f"State file: {watcher.state_file}")
        print(f"State exists: {watcher.state_file.exists()}")
        print(f"Last check: {watcher.state.last_check_timestamp or 'Never'}")
        print(f"Processed ADRs: {len(watcher.state.processed_adrs)}")
        if watcher.state.processed_adrs:
            print("\nProcessed ADR files:")
            for adr in sorted(watcher.state.processed_adrs):
                print(f"  - {adr}")

        # Show current implemented ADRs
        implemented = watcher.get_implemented_adrs()
        print(f"\nCurrent implemented ADRs: {len(implemented)}")

        # Check for unprocessed
        new_adrs = watcher.detect_new_adrs()
        if new_adrs:
            print(f"\nUnprocessed ADRs ({len(new_adrs)}):")
            for adr in new_adrs:
                print(f"  - {adr.filename}")


if __name__ == "__main__":
    main()
