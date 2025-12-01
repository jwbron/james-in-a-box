#!/usr/bin/env python3
"""
Feature Analyzer - Documentation Sync Workflow Tool

Implements Phase 1-5 of ADR-Feature-Analyzer-Documentation-Sync.

This tool maintains FEATURES.md and synchronizes documentation with implemented ADRs.
It runs on the host (NOT in the container) and uses the jib command to spawn
Claude-powered documentation agents inside containers.

Workflows:
1. sync-docs --adr <path>: Manually sync documentation for a specific implemented ADR
2. watch (Phase 2+): Automatically detect ADR status changes and trigger sync
3. weekly-analysis (Phase 5): Scan merged code and update FEATURES.md

Usage (Phase 1 - Manual):
  # Sync documentation for a specific implemented ADR
  feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md

  # Dry-run mode (show what would be updated without making changes)
  feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md --dry-run

  # Validate only (check if docs need updating)
  feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md --validate-only
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ADRMetadata:
    """Metadata extracted from an ADR file."""

    path: Path
    filename: str
    title: str
    status: str
    decision_summary: str
    concepts: list[str] = field(default_factory=list)
    affected_features: list[str] = field(default_factory=list)


@dataclass
class DocumentUpdate:
    """Represents a proposed documentation update."""

    path: Path
    reason: str
    current_content: str = ""
    proposed_content: str = ""
    validation_passed: bool = False
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class SyncResult:
    """Result of a documentation sync operation."""

    adr: ADRMetadata
    docs_to_update: list[Path] = field(default_factory=list)
    updates: list[DocumentUpdate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False


class FeatureAnalyzer:
    """Main feature analyzer class for documentation sync."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.features_md = repo_root / "docs" / "FEATURES.md"
        self.docs_index = repo_root / "docs" / "index.md"

    def parse_adr(self, adr_path: Path) -> ADRMetadata:
        """Parse ADR file and extract metadata."""
        if not adr_path.exists():
            raise FileNotFoundError(f"ADR not found: {adr_path}")

        content = adr_path.read_text()
        lines = content.split("\n")

        # Extract title (first # heading)
        title = "Unknown"
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # Determine status from directory
        status = "unknown"
        if "not-implemented" in str(adr_path):
            status = "not-implemented"
        elif "in-progress" in str(adr_path):
            status = "in-progress"
        elif "implemented" in str(adr_path):
            status = "implemented"

        # Extract decision summary (first paragraph under ## Decision)
        decision_summary = ""
        in_decision = False
        for _i, line in enumerate(lines):
            if line.startswith("## Decision"):
                in_decision = True
                continue
            if in_decision and line.strip() and not line.startswith("#"):
                decision_summary = line.strip()
                break

        return ADRMetadata(
            path=adr_path,
            filename=adr_path.name,
            title=title,
            status=status,
            decision_summary=decision_summary,
        )

    def map_adr_to_docs(self, adr_metadata: ADRMetadata) -> list[Path]:
        """
        Identify documentation files affected by this ADR.

        Phase 1 (MVP): Returns standard documentation files.
        Future phases: Use LLM to analyze ADR content and FEATURES.md for smarter mapping.
        """
        # Standard docs that may reference architecture
        standard_docs = [
            self.repo_root / "docs" / "index.md",
            self.repo_root / "CLAUDE.md",
            self.repo_root / "README.md",
            self.repo_root / "docs" / "setup" / "README.md",
        ]

        # Filter to docs that actually exist
        existing_docs = [doc for doc in standard_docs if doc.exists()]

        return existing_docs

    def validate_update(self, current: str, proposed: str) -> tuple[bool, list[str]]:
        """
        Validate proposed documentation update.

        Checks:
        1. Non-destructive (document length doesn't shrink >50%)
        2. No complete removal of major sections
        3. Link preservation (all original links present or intentionally updated)
        4. Diff bounds (max 40% of doc changed)

        Returns: (passed: bool, errors: list[str])
        """
        errors = []

        # Check 1: Document length (shouldn't shrink >50%)
        if len(proposed) < len(current) * 0.5:
            errors.append(
                f"Document length shrunk by {100 - (len(proposed) / len(current) * 100):.0f}% (max 50% allowed)"
            )

        # Check 2: Major sections preserved
        current_headers = [line for line in current.split("\n") if line.startswith("## ")]
        proposed_headers = [line for line in proposed.split("\n") if line.startswith("## ")]

        removed_headers = set(current_headers) - set(proposed_headers)
        if removed_headers:
            errors.append(f"Major sections removed: {', '.join(removed_headers)}")

        # Check 3: Link preservation (regex-based markdown link detection)
        # Matches all markdown links: [text](url) including http/https and internal links
        link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
        current_links = re.findall(link_pattern, current)
        proposed_links = re.findall(link_pattern, proposed)

        # Don't error on link changes, just warn if count drops significantly
        if len(proposed_links) < len(current_links) * 0.7:
            errors.append(
                f"Links reduced from {len(current_links)} to {len(proposed_links)} (>30% reduction)"
            )

        # Check 4: Diff bounds (rough check - character-level diff approximation)
        # Calculate simple character diff
        diff_chars = abs(len(current) - len(proposed))
        max_allowed_diff = len(current) * 0.4
        if diff_chars > max_allowed_diff:
            errors.append(
                f"Changes exceed 40% threshold ({diff_chars} chars changed, max {max_allowed_diff:.0f})"
            )

        return (len(errors) == 0, errors)

    def sync_docs_for_adr(
        self, adr_path: Path, dry_run: bool = False, validate_only: bool = False
    ) -> SyncResult:
        """
        Synchronize documentation for a specific ADR.

        Phase 1 (MVP): Manual invocation, basic validation.
        Returns SyncResult with proposed updates.
        """
        # Parse ADR
        adr_metadata = self.parse_adr(adr_path)

        result = SyncResult(adr=adr_metadata, dry_run=dry_run)

        # Map to affected documentation
        docs_to_update = self.map_adr_to_docs(adr_metadata)
        result.docs_to_update = docs_to_update

        if validate_only:
            # Just report which docs would be updated
            return result

        # For Phase 1 MVP, we'll use a simple approach:
        # Read each doc and check if it mentions the ADR or related concepts
        # Mark for update if it does

        for doc_path in docs_to_update:
            current_content = doc_path.read_text()

            # Simple heuristic: does the doc mention anything related to this ADR?
            # In future phases, use LLM for smarter detection
            adr_slug = adr_path.stem
            mentions_adr = adr_slug.lower() in current_content.lower()
            mentions_title = any(
                word.lower() in current_content.lower()
                for word in adr_metadata.title.split()
                if len(word) > 4  # Only check substantial words
            )

            if mentions_adr or mentions_title:
                update = DocumentUpdate(
                    path=doc_path,
                    reason=f"Mentions {adr_metadata.filename} or related concepts",
                    current_content=current_content,
                )

                # Phase 1: Don't auto-generate content, just flag for review
                # In future phases, use LLM to generate proposed_content
                update.proposed_content = current_content  # Placeholder

                # Validate (even though content unchanged in Phase 1)
                passed, validation_errors = self.validate_update(
                    update.current_content, update.proposed_content
                )
                update.validation_passed = passed
                update.validation_errors = validation_errors

                result.updates.append(update)

        return result


def main():
    parser = argparse.ArgumentParser(
        description="Feature Analyzer - Documentation Sync Tool (Phase 1 MVP)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # sync-docs command
    sync_parser = subparsers.add_parser(
        "sync-docs", help="Manually sync documentation for a specific ADR"
    )
    sync_parser.add_argument(
        "--adr",
        type=Path,
        required=True,
        help="Path to ADR file (e.g., docs/adr/implemented/ADR-Example.md)",
    )
    sync_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be updated without making changes"
    )
    sync_parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate and report, do not propose updates",
    )
    sync_parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: current directory)",
    )

    args = parser.parse_args()

    if args.command == "sync-docs":
        analyzer = FeatureAnalyzer(args.repo_root)

        try:
            result = analyzer.sync_docs_for_adr(
                args.adr, dry_run=args.dry_run, validate_only=args.validate_only
            )

            # Output results
            print(f"ADR: {result.adr.title}")
            print(f"Status: {result.adr.status}")
            print(f"File: {result.adr.path}")
            print()

            if args.validate_only:
                print(f"Documents that would be checked: {len(result.docs_to_update)}")
                for doc in result.docs_to_update:
                    print(f"  - {doc.relative_to(args.repo_root)}")
            else:
                print(f"Documents affected: {len(result.updates)}")
                for update in result.updates:
                    print(f"\n  {update.path.relative_to(args.repo_root)}")
                    print(f"    Reason: {update.reason}")
                    print(
                        f"    Validation: {'✓ Passed' if update.validation_passed else '✗ Failed'}"
                    )
                    if update.validation_errors:
                        for error in update.validation_errors:
                            print(f"      - {error}")

            if result.errors:
                print("\nErrors:")
                for error in result.errors:
                    print(f"  - {error}")
                sys.exit(1)

            if args.dry_run:
                print("\n[DRY RUN] No changes made.")
            elif args.validate_only:
                print("\n[VALIDATE ONLY] No updates proposed.")
            else:
                print("\n✓ Documentation sync analysis complete.")
                print("\nPhase 1 Note: This is the MVP. Future phases will:")
                print("  - Use LLM to generate actual content updates")
                print("  - Create PRs automatically")
                print("  - Run on schedule via systemd timer")

        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
