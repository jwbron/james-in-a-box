#!/usr/bin/env python3
"""
Documentation Generator - LLM-Powered Content Generation (Phase 3-4)

This module uses jib containers to generate updated documentation content
based on ADR changes. It spawns Claude-powered agents to analyze ADRs and
propose documentation updates.

The generator:
1. Analyzes ADR content to understand the change
2. Maps to affected documentation files
3. Generates updated content for each affected doc
4. Injects HTML comment metadata for traceability (Phase 4)
5. Validates updates with full validation suite (Phase 4)
6. Returns proposed updates for review

Usage:
    generator = DocGenerator(repo_root)
    updates = generator.generate_updates_for_adr(adr_metadata, affected_docs)
"""

import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING


# Add host-services shared modules to path (for jib_exec)
# NOTE: Host-side code must use jib_exec which invokes processors via jib --exec
# because Claude CLI is only available inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
from jib_exec import jib_exec


if TYPE_CHECKING:
    from feature_analyzer import ADRMetadata


@dataclass
class GeneratedUpdate:
    """A generated documentation update."""

    doc_path: Path
    original_content: str
    updated_content: str
    changes_summary: str
    confidence: float  # 0.0-1.0
    validation_passed: bool = False
    validation_errors: list[str] = field(default_factory=list)
    adr_reference: str = ""  # ADR filename for traceability metadata
    update_timestamp: str = ""  # ISO timestamp of update generation


@dataclass
class GenerationResult:
    """Result of documentation generation."""

    adr_title: str
    updates: list[GeneratedUpdate] = field(default_factory=list)
    skipped_docs: list[tuple[Path, str]] = field(default_factory=list)  # (path, reason)
    errors: list[str] = field(default_factory=list)


class DocGenerator:
    """Generates documentation updates using LLM assistance."""

    def __init__(self, repo_root: Path, use_jib: bool = True):
        """
        Initialize the documentation generator.

        Args:
            repo_root: Path to the repository root
            use_jib: If True, use jib containers for LLM generation.
                     If False, use direct prompting (for testing).
        """
        self.repo_root = repo_root
        self.use_jib = use_jib
        self.features_md = repo_root / "docs" / "FEATURES.md"
        self.docs_index = repo_root / "docs" / "index.md"

    def query_features_md(self, concepts: list[str]) -> list[dict]:
        """
        Query FEATURES.md for features related to given concepts.

        Returns list of feature entries that match the concepts.
        """
        if not self.features_md.exists():
            return []

        content = self.features_md.read_text()
        features = []

        # Parse FEATURES.md to find features matching concepts
        # Look for feature headers (#### Feature Name **[status]**)
        feature_pattern = r"####\s+(.+?)\s+\*\*\[([^\]]+)\]\*\*"
        current_feature = None

        lines = content.split("\n")
        for i, line in enumerate(lines):
            match = re.match(feature_pattern, line)
            if match:
                if current_feature:
                    features.append(current_feature)
                current_feature = {
                    "name": match.group(1),
                    "status": match.group(2),
                    "line_number": i + 1,
                    "content": line,
                    "description": "",
                    "implementation": [],
                }
            elif current_feature:
                if line.startswith("- **Description**:"):
                    current_feature["description"] = line.replace("- **Description**:", "").strip()
                elif line.startswith("  - ") and "Implementation" not in line:
                    # Capture implementation files
                    current_feature["implementation"].append(line.strip().lstrip("- "))
                elif line.startswith(("####", "###")):
                    # End of current feature
                    features.append(current_feature)
                    current_feature = None

        if current_feature:
            features.append(current_feature)

        # Filter to features matching concepts
        matching_features = []
        for feature in features:
            for concept in concepts:
                concept_lower = concept.lower()
                if (
                    concept_lower in feature["name"].lower()
                    or concept_lower in feature["description"].lower()
                ):
                    matching_features.append(feature)
                    break

        return matching_features

    def extract_concepts_from_adr(self, adr_content: str) -> list[str]:
        """
        Extract key concepts from ADR content.

        Looks for technology names, component names, and key terms.
        """
        concepts = []

        # Extract from title
        title_match = re.search(r"^#\s+ADR:\s+(.+)", adr_content, re.MULTILINE)
        if title_match:
            title = title_match.group(1)
            # Split on common separators and filter short words
            words = re.split(r"[-:\s]+", title)
            concepts.extend(w for w in words if len(w) > 3)

        # Look for technical terms (capitalized words, acronyms)
        tech_terms = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", adr_content)  # CamelCase
        concepts.extend(tech_terms[:10])  # Limit

        acronyms = re.findall(r"\b[A-Z]{2,6}\b", adr_content)  # Acronyms
        concepts.extend(a for a in acronyms if a not in ["ADR", "TBD", "URL", "API"])

        # Look for file paths and component names
        paths = re.findall(r"`([^`]+/[^`]+)`", adr_content)
        for path in paths[:5]:
            # Extract component name from path
            parts = path.split("/")
            if len(parts) > 1:
                concepts.append(parts[-1].replace(".py", "").replace(".md", ""))

        # Deduplicate while preserving order
        seen = set()
        unique_concepts = []
        for c in concepts:
            c_lower = c.lower()
            if c_lower not in seen and len(c) > 2:
                seen.add(c_lower)
                unique_concepts.append(c)

        return unique_concepts[:20]  # Limit to top 20

    def map_adr_to_docs(self, adr_path: Path, adr_content: str, concepts: list[str]) -> list[Path]:
        """
        Identify documentation files affected by this ADR.

        Uses concepts and FEATURES.md to find related documentation.
        """
        affected_docs = []

        # Standard docs that may reference architecture
        standard_docs = [
            self.repo_root / "docs" / "index.md",
            self.repo_root / "CLAUDE.md",
            self.repo_root / "README.md",
            self.repo_root / "docs" / "setup" / "README.md",
            self.repo_root / "docs" / "FEATURES.md",
        ]

        # Query FEATURES.md for related features
        matching_features = self.query_features_md(concepts)

        # Add docs referenced by matching features
        for feature in matching_features:
            for impl_path in feature.get("implementation", []):
                # Extract doc paths from implementation entries
                if ".md" in impl_path and impl_path.startswith("`"):
                    doc_path = impl_path.strip("`").split("`")[0]
                    full_path = self.repo_root / doc_path
                    if full_path.exists() and full_path not in standard_docs:
                        affected_docs.append(full_path)

        # Check standard docs for concept mentions
        adr_slug = adr_path.stem.lower()
        for doc_path in standard_docs:
            if doc_path.exists():
                content = doc_path.read_text().lower()

                # Check if doc mentions ADR or concepts
                mentions_adr = adr_slug in content
                mentions_concepts = any(c.lower() in content for c in concepts[:5])

                if (mentions_adr or mentions_concepts) and doc_path not in affected_docs:
                    affected_docs.append(doc_path)

        return affected_docs

    def _generate_prompt(
        self, adr_content: str, adr_title: str, doc_path: Path, doc_content: str
    ) -> str:
        """Generate the prompt for LLM documentation update."""
        relative_path = doc_path.relative_to(self.repo_root)

        return f"""You are updating documentation to reflect an implemented ADR (Architecture Decision Record).

## ADR: {adr_title}

{adr_content}

## Current Documentation ({relative_path})

{doc_content}

## Your Task

Update this documentation to accurately reflect the implemented ADR. Follow these rules:

1. **Preserve structure**: Keep all existing section headers
2. **Minimal changes**: Only modify sections directly affected by the ADR
3. **Accurate references**: Update any outdated references to match the ADR
4. **Consistent style**: Match the existing documentation style
5. **No removals**: Do not remove major sections unless explicitly required
6. **Add traceability**: If adding new content about the ADR, you may add a comment like:
   <!-- Updated from {adr_title} -->

Output ONLY the updated documentation content. Do not include any explanation or commentary outside the documentation.
"""

    def _call_jib_for_generation(self, prompt: str, doc_path: Path) -> tuple[str, float]:
        """
        Use jib container to generate documentation update via LLM.

        Returns (updated_content, confidence_score).

        Uses jib_exec to invoke the container-side analysis processor,
        which has access to Claude CLI. Host-side code cannot directly
        call Claude (it's only available inside the container).
        """
        try:
            # Use jib_exec to run the analysis processor in the container
            # The processor handles the LLM call and returns JSON
            result = jib_exec(
                processor="jib-container/jib-tasks/analysis/analysis-processor.py",
                task_type="llm_prompt",
                context={
                    "prompt": prompt,
                    "timeout": 300,
                    "cwd": str(self.repo_root),
                    "stream": False,
                },
                timeout=420,  # Extra time for container startup
            )

            if result.success and result.json_output:
                output = result.json_output.get("result", {})
                content = output.get("stdout", "").strip()
                if content:
                    # High confidence if we got substantial output
                    confidence = 0.85 if len(content) > 100 else 0.6
                    return (content, confidence)

            # Handle failure
            error_msg = result.error or "Unknown error"
            if result.json_output:
                error_msg = result.json_output.get("error") or error_msg
            print(f"    Warning: jib generation failed: {error_msg}")
            return ("", 0.3)

        except Exception as e:
            print(f"    Warning: jib generation error: {e}")
            return ("", 0.2)

    def _generate_simple_update(
        self, adr_content: str, adr_title: str, doc_path: Path, doc_content: str
    ) -> tuple[str, float, str]:
        """
        Generate a simple documentation update without LLM.

        This is a fallback for when jib is not available or for testing.
        Returns (updated_content, confidence, changes_summary).
        """
        # For Phase 3 MVP, we can do simple updates like:
        # - Adding ADR references where missing
        # - Updating status flags in FEATURES.md

        changes_summary = ""

        # Handle FEATURES.md specially - update status if needed
        if doc_path.name == "FEATURES.md":
            adr_slug = Path(adr_title).stem if "/" in adr_title else adr_title
            # Look for feature entries that reference this ADR
            # and update their status to [implemented] if not already
            pattern = r"\*\*\[in-progress\]\*\*"
            if adr_slug.lower() in doc_content.lower() and re.search(pattern, doc_content):
                # This is a simplified update - real implementation would be smarter
                changes_summary = f"Feature status may need update based on {adr_title}"
                return (doc_content, 0.5, changes_summary)

        # For other docs, just flag them as potentially needing review
        changes_summary = (
            f"Document references concepts from {adr_title} - manual review recommended"
        )
        return (doc_content, 0.4, changes_summary)

    def generate_updates_for_adr(
        self,
        adr_metadata: "ADRMetadata",
        affected_docs: list[Path] | None = None,
    ) -> GenerationResult:
        """
        Generate documentation updates for an implemented ADR.

        Args:
            adr_metadata: Parsed ADR metadata
            affected_docs: Optional list of docs to update. If None, auto-detect.

        Returns:
            GenerationResult with proposed updates.
        """
        result = GenerationResult(adr_title=adr_metadata.title)

        # Read ADR content
        adr_content = adr_metadata.path.read_text()

        # Extract concepts for mapping
        concepts = self.extract_concepts_from_adr(adr_content)
        adr_metadata.concepts = concepts

        # Map to affected docs if not provided
        if affected_docs is None:
            affected_docs = self.map_adr_to_docs(adr_metadata.path, adr_content, concepts)

        print(f"  Concepts extracted: {concepts[:5]}...")
        print(f"  Affected documents: {len(affected_docs)}")

        for doc_path in affected_docs:
            try:
                doc_content = doc_path.read_text()

                if self.use_jib:
                    # Generate prompt
                    prompt = self._generate_prompt(
                        adr_content, adr_metadata.title, doc_path, doc_content
                    )

                    # Call jib for generation
                    updated_content, confidence = self._call_jib_for_generation(prompt, doc_path)

                    if updated_content:
                        changes_summary = f"LLM-generated update for {adr_metadata.title}"
                    else:
                        # Fallback to simple update
                        updated_content, confidence, changes_summary = self._generate_simple_update(
                            adr_content, adr_metadata.title, doc_path, doc_content
                        )
                else:
                    # No jib - use simple update
                    updated_content, confidence, changes_summary = self._generate_simple_update(
                        adr_content, adr_metadata.title, doc_path, doc_content
                    )

                # Create update if content changed
                if updated_content and updated_content != doc_content:
                    update = GeneratedUpdate(
                        doc_path=doc_path,
                        original_content=doc_content,
                        updated_content=updated_content,
                        changes_summary=changes_summary,
                        confidence=confidence,
                    )
                    result.updates.append(update)
                else:
                    result.skipped_docs.append((doc_path, "No changes needed or generation failed"))

            except Exception as e:
                result.errors.append(f"Error processing {doc_path}: {e}")

        return result

    def validate_update(
        self, original: str, updated: str, adr_content: str | None = None
    ) -> tuple[bool, list[str]]:
        """
        Validate a proposed documentation update.

        Phase 4 Full Validation Suite (6 checks):
        1. Non-destructive (document length doesn't shrink >50%)
        2. Major sections preserved (## headers maintained)
        3. Link preservation (links not accidentally removed)
        4. Diff bounds (max 40% of doc changed)
        5. Structure preservation (document hierarchy maintained)
        6. Traceability (new claims traceable to ADR)

        Args:
            original: Original document content
            updated: Proposed updated content
            adr_content: Optional ADR content for traceability validation

        Returns: (passed, list of errors)
        """
        errors = []

        # Check 1: Non-destructive - document length doesn't shrink >50%
        if len(updated) < len(original) * 0.5:
            reduction = 100 - (len(updated) / len(original) * 100)
            errors.append(f"Document length shrunk by {reduction:.0f}% (max 50% allowed)")

        # Check 2: Major sections preserved (## level headers)
        original_headers = [line for line in original.split("\n") if line.startswith("## ")]
        updated_headers = [line for line in updated.split("\n") if line.startswith("## ")]

        removed_headers = set(original_headers) - set(updated_headers)
        if removed_headers:
            errors.append(f"Major sections removed: {', '.join(list(removed_headers)[:3])}")

        # Check 3: Link preservation
        link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
        original_links = re.findall(link_pattern, original)
        updated_links = re.findall(link_pattern, updated)

        if len(updated_links) < len(original_links) * 0.7:
            errors.append(f"Links reduced from {len(original_links)} to {len(updated_links)}")

        # Check 4: Diff bounds (max 40% change)
        diff_chars = abs(len(original) - len(updated))
        max_allowed = len(original) * 0.4
        if diff_chars > max_allowed:
            errors.append(
                f"Changes exceed 40% threshold ({diff_chars} chars, max {max_allowed:.0f})"
            )

        # Check 5: Structure preservation (document hierarchy maintained)
        # Ensure heading hierarchy is valid (no # followed directly by ###)
        original_heading_levels = self._extract_heading_levels(original)
        updated_heading_levels = self._extract_heading_levels(updated)

        # Check that we don't remove top-level structure
        if original_heading_levels and updated_heading_levels:
            # Verify minimum heading level is preserved
            if min(updated_heading_levels) > min(original_heading_levels):
                errors.append("Document hierarchy changed: top-level heading removed")

            # Verify we don't have orphaned sub-headings (### without ##)
            if self._has_orphaned_headings(updated):
                errors.append("Invalid heading hierarchy: orphaned sub-headings detected")

        # Check 6: Traceability (new content should relate to ADR)
        if adr_content:
            new_content = self._extract_new_content(original, updated)
            if new_content and len(new_content) > 100:
                # Check if new content contains terms from ADR
                adr_terms = self._extract_key_terms(adr_content)
                new_terms = self._extract_key_terms(new_content)

                # At least some overlap expected for traceability
                overlap = adr_terms & new_terms
                if not overlap and len(new_content) > 200:
                    errors.append(
                        "Traceability warning: new content may not relate to ADR "
                        "(no common terms found)"
                    )

        return (len(errors) == 0, errors)

    def _extract_heading_levels(self, content: str) -> list[int]:
        """Extract heading levels from markdown content."""
        levels = []
        for line in content.split("\n"):
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                if level > 0 and level <= 6:  # Valid markdown heading levels
                    levels.append(level)
        return levels

    def _has_orphaned_headings(self, content: str) -> bool:
        """Check if document has orphaned headings (e.g., ### without ##)."""
        levels = self._extract_heading_levels(content)
        if not levels:
            return False

        # Check for gaps in heading hierarchy
        seen_levels = set()
        for level in levels:
            seen_levels.add(level)
            # If we see level 3, we should have seen level 2
            if level > 1 and (level - 1) not in seen_levels and level != min(seen_levels):
                return True
        return False

    def _extract_new_content(self, original: str, updated: str) -> str:
        """Extract content that was added in the update."""
        original_lines = set(original.split("\n"))
        updated_lines = updated.split("\n")
        new_lines = [line for line in updated_lines if line not in original_lines]
        return "\n".join(new_lines)

    def _extract_key_terms(self, content: str) -> set[str]:
        """Extract key terms from content for traceability checking."""
        # Extract words longer than 4 characters, excluding common words
        common_words = {
            "this",
            "that",
            "with",
            "from",
            "have",
            "will",
            "would",
            "could",
            "should",
            "about",
            "which",
            "their",
            "there",
            "these",
            "those",
            "other",
            "being",
            "using",
            "after",
            "before",
        }
        words = re.findall(r"\b[a-zA-Z]{5,}\b", content.lower())
        return set(words) - common_words

    def validate_all_updates(
        self, result: GenerationResult, adr_content: str | None = None
    ) -> GenerationResult:
        """
        Validate all updates in a GenerationResult.

        Updates the validation_passed and validation_errors fields.

        Args:
            result: GenerationResult containing updates to validate
            adr_content: Optional ADR content for traceability validation (Phase 4)
        """
        for update in result.updates:
            passed, errors = self.validate_update(
                update.original_content, update.updated_content, adr_content
            )
            update.validation_passed = passed
            update.validation_errors = errors

        return result

    def inject_metadata_comments(
        self, content: str, adr_filename: str, timestamp: str | None = None
    ) -> str:
        """
        Inject HTML comment metadata into updated documentation (Phase 4).

        Adds traceability metadata as HTML comments that:
        - Enable filtering: grep -r "Auto-updated from" docs/
        - Provide audit trail for auto-generated changes
        - Don't affect rendered markdown

        Args:
            content: Document content to inject metadata into
            adr_filename: ADR filename (e.g., "ADR-Feature-Analyzer.md")
            timestamp: Optional ISO timestamp (defaults to now)

        Returns:
            Content with metadata comment injected at the end
        """
        if timestamp is None:
            timestamp = datetime.now(UTC).strftime("%Y-%m-%d")

        # Create metadata comment
        metadata_comment = f"\n<!-- Auto-updated from {adr_filename} on {timestamp} -->\n"

        # Check if this metadata already exists (avoid duplicates)
        if f"Auto-updated from {adr_filename}" in content:
            # Update existing timestamp
            pattern = (
                rf"<!-- Auto-updated from {re.escape(adr_filename)} on \d{{4}}-\d{{2}}-\d{{2}} -->"
            )
            return re.sub(pattern, metadata_comment.strip(), content)

        # Add at the end of the file, before any trailing newlines
        content = content.rstrip("\n")
        return content + metadata_comment

    def apply_metadata_to_updates(
        self, result: GenerationResult, adr_filename: str
    ) -> GenerationResult:
        """
        Apply metadata comments to all updates in a GenerationResult (Phase 4).

        Args:
            result: GenerationResult containing updates
            adr_filename: ADR filename for metadata

        Returns:
            GenerationResult with metadata injected into updated_content
        """
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d")

        for update in result.updates:
            if update.updated_content and update.validation_passed:
                update.updated_content = self.inject_metadata_comments(
                    update.updated_content, adr_filename, timestamp
                )
                update.adr_reference = adr_filename
                update.update_timestamp = timestamp

        return result


def main():
    """Test the doc generator."""
    import argparse

    parser = argparse.ArgumentParser(description="Test documentation generator")
    parser.add_argument("--adr", type=Path, required=True, help="Path to ADR file")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory",
    )
    parser.add_argument("--no-jib", action="store_true", help="Skip jib container generation")

    args = parser.parse_args()

    # Import feature_analyzer for ADRMetadata
    sys.path.insert(0, str(Path(__file__).parent))
    from feature_analyzer import FeatureAnalyzer

    analyzer = FeatureAnalyzer(args.repo_root)
    adr_metadata = analyzer.parse_adr(args.adr)

    generator = DocGenerator(args.repo_root, use_jib=not args.no_jib)

    print(f"Generating updates for: {adr_metadata.title}")
    print(f"ADR Status: {adr_metadata.status}")
    print()

    result = generator.generate_updates_for_adr(adr_metadata)
    result = generator.validate_all_updates(result)

    print("\nGeneration Results:")
    print(f"  Updates generated: {len(result.updates)}")
    print(f"  Docs skipped: {len(result.skipped_docs)}")
    print(f"  Errors: {len(result.errors)}")

    for update in result.updates:
        print(f"\n  {update.doc_path.name}:")
        print(f"    Confidence: {update.confidence:.0%}")
        print(f"    Summary: {update.changes_summary}")
        print(f"    Validation: {'Passed' if update.validation_passed else 'FAILED'}")
        if update.validation_errors:
            for error in update.validation_errors:
                print(f"      - {error}")

    for path, reason in result.skipped_docs:
        print(f"\n  Skipped {path.name}: {reason}")

    for error in result.errors:
        print(f"\n  Error: {error}")


if __name__ == "__main__":
    main()
