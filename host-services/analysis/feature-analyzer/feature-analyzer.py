#!/usr/bin/env python3
"""
Feature Analyzer - Documentation Sync Workflow Tool

Implements Phase 1-5 of ADR-Feature-Analyzer-Documentation-Sync.

This tool maintains FEATURES.md and synchronizes documentation with implemented ADRs.
It runs on the host (NOT in the container) and uses the jib command to spawn
Claude-powered documentation agents inside containers.

Workflows:
1. sync-docs --adr <path>: Manually sync documentation for a specific implemented ADR
2. generate --adr <path>: Generate and optionally create PR with doc updates (Phase 3)
3. watch (Phase 2+): Automatically detect ADR status changes and trigger sync
4. weekly-analysis (Phase 5): Scan merged code and update FEATURES.md

Usage (Phase 1 - Manual):
  # Sync documentation for a specific implemented ADR
  feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md

  # Dry-run mode (show what would be updated without making changes)
  feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md --dry-run

  # Validate only (check if docs need updating)
  feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md --validate-only

Usage (Phase 3 - Multi-Doc Updates with PR):
  # Generate doc updates and create PR (uses jib by default)
  feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md

  # Generate without jib containers
  feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md --no-jib

  # Dry-run (show what would be done)
  feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md --dry-run
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# Add host-services shared modules to path for jib_exec
sys.path.insert(0, "/opt/jib-runtime/shared")
from jib_exec import jib_exec


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
        description="Feature Analyzer - Documentation Sync Tool (Phase 1-5)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # sync-docs command (Phase 1)
    sync_parser = subparsers.add_parser(
        "sync-docs", help="Manually sync documentation for a specific ADR (Phase 1)"
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

    # generate command (Phase 3-4)
    gen_parser = subparsers.add_parser(
        "generate", help="Generate doc updates and create PR (Phase 3-4)"
    )
    gen_parser.add_argument(
        "--adr",
        type=Path,
        required=True,
        help="Path to ADR file (e.g., docs/adr/implemented/ADR-Example.md)",
    )
    gen_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without creating PR",
    )
    gen_parser.add_argument(
        "--no-jib",
        action="store_true",
        help="Disable jib containers for LLM-powered generation",
    )
    gen_parser.add_argument(
        "--no-pr",
        action="store_true",
        help="Generate updates but don't create PR",
    )
    gen_parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Skip HTML comment metadata injection (Phase 4)",
    )
    gen_parser.add_argument(
        "--no-tag",
        action="store_true",
        help="Skip git tag creation for traceability (Phase 4)",
    )
    gen_parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: current directory)",
    )

    # rollback command (Phase 4)
    rollback_parser = subparsers.add_parser(
        "rollback", help="Rollback utilities for auto-generated documentation (Phase 4)"
    )
    rollback_parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: current directory)",
    )
    rollback_subparsers = rollback_parser.add_subparsers(dest="rollback_command")

    # rollback list-commits
    rollback_list_commits = rollback_subparsers.add_parser(
        "list-commits", help="List auto-generated commits"
    )
    rollback_list_commits.add_argument(
        "--since", help="Show commits since date (e.g., '1 week ago')"
    )
    rollback_list_commits.add_argument("--adr", help="Filter by ADR filename")

    # rollback list-files
    rollback_subparsers.add_parser("list-files", help="List files with auto-generated metadata")

    # rollback list-tags
    rollback_subparsers.add_parser("list-tags", help="List auto-doc-sync tags")

    # rollback revert-file
    rollback_revert_file = rollback_subparsers.add_parser(
        "revert-file", help="Revert a single file"
    )
    rollback_revert_file.add_argument("file", type=Path, help="Path to file to revert")
    rollback_revert_file.add_argument(
        "--to", help="Commit to revert to (default: before last auto-generated)"
    )

    # rollback revert-adr
    rollback_revert_adr = rollback_subparsers.add_parser(
        "revert-adr", help="Revert all changes from an ADR"
    )
    rollback_revert_adr.add_argument("adr_name", help="ADR filename (e.g., ADR-Feature-Analyzer)")

    # weekly-analyze command (Phase 5)
    weekly_parser = subparsers.add_parser(
        "weekly-analyze",
        help="Analyze recent code changes and update FEATURES.md (Phase 5)",
    )
    weekly_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)",
    )
    weekly_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without modifying files",
    )
    weekly_parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM extraction, use heuristics only",
    )
    weekly_parser.add_argument(
        "--no-pr",
        action="store_true",
        help="Update FEATURES.md but don't create PR",
    )
    weekly_parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: current directory)",
    )

    # full-repo command (Phase 6 - Full Repository Analysis)
    full_repo_parser = subparsers.add_parser(
        "full-repo",
        help="Analyze entire repository and generate comprehensive FEATURES.md (Phase 6)",
    )
    full_repo_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without modifying files",
    )
    full_repo_parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM extraction, use heuristics only",
    )
    full_repo_parser.add_argument(
        "--no-pr",
        action="store_true",
        help="Generate FEATURES.md but don't create PR",
    )
    full_repo_parser.add_argument(
        "--output",
        type=Path,
        help="Custom output path (default: docs/FEATURES.md)",
    )
    full_repo_parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: current directory)",
    )
    full_repo_parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of parallel workers for directory analysis (default: 5)",
    )

    # generate-feature-docs command (Phase 7 - Feature Sub-Documentation)
    feature_docs_parser = subparsers.add_parser(
        "generate-feature-docs",
        help="Generate feature category documentation in docs/features/ (Phase 7)",
    )
    feature_docs_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without modifying files",
    )
    feature_docs_parser.add_argument(
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
                print("\nPhase 1 Note: This is the MVP. Use 'generate' command for Phase 3:")
                print("  feature-analyzer generate --adr <path>")

        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.exit(1)

    elif args.command == "generate":
        # Phase 3-4: Multi-doc updates with PR creation and traceability
        from doc_generator import DocGenerator
        from pr_creator import PRCreator

        analyzer = FeatureAnalyzer(args.repo_root)

        try:
            # Parse ADR
            print(f"Parsing ADR: {args.adr}")
            adr_metadata = analyzer.parse_adr(args.adr)

            print(f"ADR: {adr_metadata.title}")
            print(f"Status: {adr_metadata.status}")
            print()

            # Generate updates
            print("Generating documentation updates...")
            generator = DocGenerator(args.repo_root, use_jib=not args.no_jib)
            gen_result = generator.generate_updates_for_adr(adr_metadata)

            # Read ADR content for traceability validation (Phase 4)
            adr_content = adr_metadata.path.read_text()

            # Validate all updates with full validation suite (Phase 4)
            gen_result = generator.validate_all_updates(gen_result, adr_content)

            # Apply HTML metadata comments (Phase 4)
            if not args.no_metadata:
                gen_result = generator.apply_metadata_to_updates(gen_result, adr_metadata.filename)

            # Report results
            print("\nGeneration Results:")
            print(f"  Updates generated: {len(gen_result.updates)}")
            print(f"  Docs skipped: {len(gen_result.skipped_docs)}")

            valid_updates = [u for u in gen_result.updates if u.validation_passed]
            invalid_updates = [u for u in gen_result.updates if not u.validation_passed]

            print(f"  Valid updates: {len(valid_updates)}")
            print(f"  Failed validation: {len(invalid_updates)}")

            for update in gen_result.updates:
                status = "✓" if update.validation_passed else "✗"
                print(f"\n  {status} {update.doc_path.relative_to(args.repo_root)}")
                print(f"    Confidence: {update.confidence:.0%}")
                print(f"    Summary: {update.changes_summary}")
                if update.adr_reference:
                    print(f"    Metadata: {update.adr_reference} ({update.update_timestamp})")
                if update.validation_errors:
                    for error in update.validation_errors:
                        print(f"    Error: {error}")

            for path, reason in gen_result.skipped_docs:
                print(f"\n  - Skipped {path.name}: {reason}")

            if gen_result.errors:
                print("\nErrors:")
                for error in gen_result.errors:
                    print(f"  - {error}")

            # Create PR if requested and we have valid updates
            if not args.no_pr and valid_updates:
                print("\n" + "=" * 50)
                print("Creating Pull Request...")

                pr_creator = PRCreator(args.repo_root)
                pr_result = pr_creator.create_doc_sync_pr(
                    adr_title=adr_metadata.title,
                    adr_path=adr_metadata.path,
                    updates=gen_result.updates,
                    dry_run=args.dry_run,
                    create_tag=not args.no_tag,  # Phase 4: Git tagging
                )

                if pr_result.success:
                    print("\n✓ PR created successfully!")
                    print(f"  Branch: {pr_result.branch_name}")
                    if pr_result.tag_name:
                        print(f"  Tag: {pr_result.tag_name}")
                    if pr_result.pr_url:
                        print(f"  PR URL: {pr_result.pr_url}")
                else:
                    print(f"\n✗ PR creation failed: {pr_result.error}")
                    if pr_result.branch_name:
                        print(f"  Branch (may have partial changes): {pr_result.branch_name}")
                    sys.exit(1)

            elif args.no_pr:
                print("\n[--no-pr] Skipping PR creation.")
            elif not valid_updates:
                print("\nNo valid updates to create PR from.")

            if args.dry_run:
                print("\n[DRY RUN] No actual changes were made.")

        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.exit(1)

    elif args.command == "rollback":
        # Phase 4: Rollback utilities
        from rollback import Rollback

        rollback = Rollback(args.repo_root)

        if args.rollback_command == "list-commits":
            commits = rollback.find_auto_generated_commits(since=args.since, adr_filename=args.adr)

            if not commits:
                print("No auto-generated commits found.")
            else:
                print(f"Found {len(commits)} auto-generated commit(s):\n")
                for commit in commits:
                    print(f"  {commit.sha[:8]} - {commit.message}")
                    print(f"    Date: {commit.date}")
                    if commit.adr_filename:
                        print(f"    ADR: {commit.adr_filename}")
                    if commit.files:
                        print(f"    Files: {', '.join(commit.files[:3])}")
                        if len(commit.files) > 3:
                            print(f"           ... and {len(commit.files) - 3} more")
                    print()

        elif args.rollback_command == "list-files":
            files = rollback.find_files_with_metadata()

            if not files:
                print("No files with auto-generated metadata found.")
            else:
                print(f"Found {len(files)} file(s) with auto-generated metadata:\n")
                for file_path, adr_ref in files:
                    rel_path = file_path.relative_to(args.repo_root)
                    print(f"  {rel_path}")
                    print(f"    Updated from: {adr_ref}")
                    print()

        elif args.rollback_command == "list-tags":
            tags = rollback.find_auto_generated_tags()

            if not tags:
                print("No auto-doc-sync tags found.")
            else:
                print(f"Found {len(tags)} auto-doc-sync tag(s):\n")
                for tag in tags:
                    print(f"  {tag}")

        elif args.rollback_command == "revert-file":
            result = rollback.revert_single_file(args.file, target_commit=args.to)

            if result.success:
                print(f"✓ {result.message}")
                print("\nNote: Changes are staged but not committed.")
                print("Review and commit with: git commit -m 'Revert auto-generated changes'")
            else:
                print(f"✗ {result.message}")
                sys.exit(1)

        elif args.rollback_command == "revert-adr":
            result = rollback.revert_adr_batch(args.adr_name)

            if result.success:
                print(f"✓ {result.message}")
                if result.reverted_files:
                    print("\nReverted files:")
                    for f in result.reverted_files:
                        print(f"  - {f}")
                print("\nNote: Changes are staged but not committed.")
                print("Review and commit with: git commit -m 'Revert auto-generated changes'")
            else:
                print(f"✗ {result.message}")
                sys.exit(1)

        else:
            parser.print_help()

    elif args.command == "weekly-analyze":
        # Phase 5: Weekly code analysis for FEATURES.md
        # IMPORTANT: All file writes and git operations must happen INSIDE the container
        # to avoid modifying files in the host's main worktree.
        # We delegate everything to analysis-processor's weekly_feature_analysis task.

        print("Feature Analyzer - Weekly Code Analysis (Phase 5)")
        print(f"Repository: {args.repo_root.name}")
        print(f"Analyzing past {args.days} days")
        print()

        try:
            # Delegate to container via jib_exec
            # The container's analysis-processor has handle_weekly_feature_analysis which:
            # 1. Creates a fresh branch from origin/main
            # 2. Runs the full multi-agent analysis pipeline
            # 3. Updates FEATURES.md
            # 4. Commits, pushes, and creates PR
            print("Delegating to jib container for analysis and PR creation...")
            print("(All file modifications happen inside the container)")
            print()

            result = jib_exec(
                processor="analysis-processor",
                task_type="weekly_feature_analysis",
                context={
                    "repo_name": args.repo_root.name,
                    "days": args.days,
                    "dry_run": args.dry_run or args.no_pr,
                    "max_workers": 5,
                },
                timeout=600,  # 10 minute timeout for comprehensive analysis
            )

            if result.success and result.json_output:
                data = result.json_output.get("result", {})

                print("=" * 50)
                print("Analysis Results:")
                print(f"  Directories analyzed: {data.get('directories_analyzed', 0)}")
                print(f"  Features detected: {data.get('features_detected', 0)}")
                print(f"  Features added: {data.get('features_added', 0)}")
                print(f"  Features skipped: {data.get('features_skipped', 0)}")

                if data.get("pr_url"):
                    print("\n✓ PR created successfully!")
                    print(f"  Branch: {data.get('branch', 'unknown')}")
                    print(f"  PR URL: {data.get('pr_url')}")
                elif args.dry_run:
                    print("\n[DRY RUN] No files were modified.")
                elif args.no_pr:
                    print("\n[--no-pr] Analysis complete, PR not created.")
                elif data.get("features_added", 0) == 0:
                    print("\nNo new features to add - FEATURES.md is up to date.")

            else:
                error_msg = result.error or "Unknown error"
                if result.json_output:
                    error_msg = result.json_output.get("error", error_msg)
                print(f"\n✗ Analysis failed: {error_msg}")
                if result.stderr:
                    print(f"\nStderr:\n{result.stderr[:500]}")
                sys.exit(1)

        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.exit(1)

    elif args.command == "full-repo":
        # Phase 6: Full repository analysis for comprehensive FEATURES.md
        # IMPORTANT: All file writes and git operations must happen INSIDE the container
        # to avoid modifying files in the host's main worktree.
        # We delegate everything to analysis-processor's full_repo_analysis task.

        print("Feature Analyzer - Full Repository Analysis (Phase 6)")
        print(f"Repository: {args.repo_root.name}")
        print()

        try:
            # Delegate to container via jib_exec
            # The container's analysis-processor has handle_full_repo_analysis which:
            # 1. Creates a fresh branch from origin/main
            # 2. Runs the full multi-agent analysis pipeline on the entire repo
            # 3. Generates comprehensive FEATURES.md
            # 4. Commits, pushes, and creates PR
            print("Delegating to jib container for analysis and PR creation...")
            print("(All file modifications happen inside the container)")
            print()

            context = {
                "repo_name": args.repo_root.name,
                "dry_run": args.dry_run or args.no_pr,
                "max_workers": args.workers,
            }
            if args.output:
                context["output_path"] = str(args.output)

            result = jib_exec(
                processor="analysis-processor",
                task_type="full_repo_analysis",
                context=context,
                timeout=900,  # 15 minute timeout for full repo analysis
            )

            if result.success and result.json_output:
                data = result.json_output.get("result", {})

                print("=" * 50)
                print("Analysis Results:")
                print(f"  Directories scanned: {data.get('directories_scanned', 0)}")
                print(f"  Files analyzed: {data.get('files_analyzed', 0)}")
                print(f"  Features detected: {data.get('features_detected', 0)}")

                features_by_category = data.get("features_by_category", {})
                if features_by_category:
                    print("\nFeatures by category:")
                    for cat, count in sorted(features_by_category.items()):
                        print(f"  {cat}: {count}")

                if data.get("pr_url"):
                    print("\n✓ PR created successfully!")
                    print(f"  Branch: {data.get('branch', 'unknown')}")
                    print(f"  PR URL: {data.get('pr_url')}")
                elif args.dry_run:
                    print("\n[DRY RUN] No files were modified.")
                elif args.no_pr:
                    print("\n[--no-pr] Analysis complete, PR not created.")

            else:
                error_msg = result.error or "Unknown error"
                if result.json_output:
                    error_msg = result.json_output.get("error", error_msg)
                print(f"\n✗ Analysis failed: {error_msg}")
                if result.stderr:
                    print(f"\nStderr:\n{result.stderr[:500]}")
                sys.exit(1)

        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            import traceback

            traceback.print_exc()
            sys.exit(1)

    elif args.command == "generate-feature-docs":
        # Phase 7: Generate feature category documentation
        from feature_doc_generator import FeatureDocGenerator

        print("Feature Analyzer - Generate Feature Docs (Phase 7)")
        print(f"Repository: {args.repo_root}")
        print()

        try:
            generator = FeatureDocGenerator(args.repo_root)
            result = generator.run(dry_run=args.dry_run)

            print()
            print("=" * 50)
            print("Summary:")
            print(f"  Categories parsed: {result['categories']}")
            print(f"  Features found: {result['features']}")
            print(f"  Category docs generated: {result['generated_docs']}")
            print(f"  Total doc files: {result['total_docs']}")

            if args.dry_run:
                print("\n[DRY RUN] No files were modified.")
            else:
                print("\n✓ Feature documentation generated successfully!")
                print("\nGenerated files in docs/features/:")
                print("  - README.md (navigation index)")
                print("  - Category docs (communication.md, github-integration.md, etc.)")

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
