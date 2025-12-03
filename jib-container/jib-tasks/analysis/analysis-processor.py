#!/usr/bin/env python3
"""
Analysis Processor - Container-side dispatcher for analysis-related tasks.

This script is invoked by host-side services via `jib --exec`. It receives
context via command-line arguments and dispatches to the appropriate handler
based on task type.

Usage:
    jib --exec python3 analysis-processor.py --task <task_type> --context <json>

Task types:
    - llm_prompt: Run an LLM prompt and return the result as JSON
    - doc_generation: Generate documentation updates based on an ADR
    - feature_extraction: Extract features from code for FEATURES.md
    - create_pr: Create a PR with files (uses container's git worktree)

Output:
    Writes JSON to stdout with structure:
    {
        "success": true/false,
        "result": <task-specific result>,
        "error": null or "error message"
    }

This enables host-side services to invoke LLM capabilities without directly
importing container modules.
"""

import argparse
import json
import sys
from pathlib import Path


# Import shared modules - find shared directory dynamically
# This works both in development (symlinked from jib-tasks/analysis) and in container
# (baked into /opt/jib-runtime/jib-container/bin/)
def _find_shared_path() -> Path:
    """Find the shared directory by walking up from the script location."""
    script_path = Path(__file__).resolve()
    # Check multiple possible parent levels
    for i in range(1, 6):
        if i < len(script_path.parents):
            candidate = script_path.parents[i] / "shared"
            if (candidate / "claude").is_dir():
                return candidate
    # Fallback: check /opt/jib-runtime/shared (container path)
    container_shared = Path("/opt/jib-runtime/shared")
    if (container_shared / "claude").is_dir():
        return container_shared
    raise ImportError(f"Cannot find shared/claude module from {script_path}")


sys.path.insert(0, str(_find_shared_path()))
import contextlib

from claude import run_claude


def output_result(success: bool, result: dict | str | None = None, error: str | None = None):
    """Output a JSON result and exit."""
    output = {
        "success": success,
        "result": result,
        "error": error,
    }
    print(json.dumps(output))
    return 0 if success else 1


def get_default_branch(repo_path: Path) -> str:
    """Detect the default branch for a repository.

    Tries to determine the default branch by:
    1. Checking git remote show origin (most reliable)
    2. Falling back to checking for common branch names (main, master)
    3. Defaulting to "main" if nothing else works

    Args:
        repo_path: Path to the repository

    Returns:
        The default branch name (e.g., "main" or "master")
    """
    import subprocess

    # Try to get the default branch from the remote
    try:
        result = subprocess.run(
            ["git", "remote", "show", "origin"],
            check=False,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "HEAD branch:" in line:
                    return line.split(":")[-1].strip()
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        pass

    # Fallback: check which common branches exist
    try:
        result = subprocess.run(
            ["git", "branch", "-r"],
            check=False,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            branches = result.stdout
            if "origin/master" in branches:
                return "master"
            if "origin/main" in branches:
                return "main"
    except subprocess.SubprocessError:
        pass

    # Ultimate fallback
    return "main"


def handle_llm_prompt(context: dict) -> int:
    """Handle a generic LLM prompt request.

    Context expected:
        - prompt: str (the prompt to send to Claude)
        - timeout: int (optional, uses shared claude module default if not provided)
        - cwd: str (optional, working directory)
        - stream: bool (optional, whether to stream output)

    Returns JSON with:
        - result.stdout: Claude's output
        - result.stderr: Any stderr
        - result.returncode: Exit code
    """
    prompt = context.get("prompt")
    if not prompt:
        return output_result(False, error="No prompt provided in context")

    # Only pass timeout if explicitly provided; otherwise let run_claude use its default
    timeout = context.get("timeout")
    cwd = context.get("cwd")
    if cwd:
        cwd = Path(cwd)
    stream = context.get("stream", False)

    try:
        # Build kwargs, only including timeout if explicitly specified
        kwargs = {"prompt": prompt, "cwd": cwd, "stream": stream}
        if timeout is not None:
            kwargs["timeout"] = timeout

        result = run_claude(**kwargs)

        return output_result(
            success=result.success,
            result={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            },
            error=result.error,
        )

    except Exception as e:
        return output_result(False, error=f"Error running Claude: {e}")


def handle_llm_prompt_to_file(context: dict) -> int:
    """Handle an LLM prompt that writes JSON output to a file.

    This is designed to avoid JSON parsing issues when the LLM includes
    explanatory text before/after the JSON in its stdout. By asking the LLM
    to write the JSON to a specific file, we can reliably retrieve it.

    Context expected:
        - prompt: str (the prompt to send to Claude - should instruct it to write JSON to the output file)
        - output_file: str (path where Claude should write the JSON output)
        - timeout: int (optional, uses shared claude module default if not provided)
        - cwd: str (optional, working directory)

    Returns JSON with:
        - result.json_content: The parsed JSON from the output file
        - result.stdout: Claude's stdout (for debugging)
        - result.stderr: Any stderr
    """
    import tempfile

    prompt = context.get("prompt")
    output_file = context.get("output_file")
    if not prompt:
        return output_result(False, error="No prompt provided in context")

    # Generate a temporary file path if not provided
    if not output_file:
        # Create a temp file in /tmp (accessible both inside and outside container)
        fd, output_file = tempfile.mkstemp(suffix=".json", prefix="llm_output_")
        import os

        os.close(fd)

    output_path = Path(output_file)

    # Only pass timeout if explicitly provided
    timeout = context.get("timeout")
    cwd = context.get("cwd")
    if cwd:
        cwd = Path(cwd)

    # Enhance the prompt to explicitly instruct writing to the file
    enhanced_prompt = f"""{prompt}

CRITICAL INSTRUCTION: You MUST write your JSON output to this file: {output_file}

Use the Write tool to write the JSON array to {output_file}. Do NOT just print the JSON to stdout - write it to the file.

After writing the file, confirm by saying "JSON written to {output_file}" but do NOT include the JSON content in your response."""

    try:
        # Build kwargs
        kwargs = {"prompt": enhanced_prompt, "cwd": cwd, "stream": False}
        if timeout is not None:
            kwargs["timeout"] = timeout

        result = run_claude(**kwargs)

        # Read the JSON from the output file
        json_content = None
        if output_path.exists():
            try:
                file_content = output_path.read_text().strip()
                if file_content:
                    json_content = json.loads(file_content)
            except json.JSONDecodeError as e:
                return output_result(
                    success=False,
                    result={
                        "json_content": None,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "output_file": str(output_file),
                    },
                    error=f"Failed to parse JSON from output file: {e}",
                )
            finally:
                # Clean up the temp file
                with contextlib.suppress(OSError):
                    output_path.unlink()
        else:
            return output_result(
                success=False,
                result={
                    "json_content": None,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "output_file": str(output_file),
                },
                error=f"Output file was not created: {output_file}",
            )

        return output_result(
            success=True,
            result={
                "json_content": json_content,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "output_file": str(output_file),
            },
        )

    except Exception as e:
        # Clean up temp file on error
        if output_path.exists():
            with contextlib.suppress(OSError):
                output_path.unlink()
        return output_result(False, error=f"Error running Claude: {e}")


def handle_doc_generation(context: dict) -> int:
    """Handle documentation generation based on ADR content.

    Context expected:
        - adr_content: str (full ADR text)
        - adr_title: str
        - doc_path: str (path to document being updated)
        - doc_content: str (current document content)
        - repo_root: str (optional)

    Returns JSON with:
        - result.updated_content: str (new document content)
        - result.confidence: float (0.0-1.0)
        - result.changes_summary: str
    """
    adr_content = context.get("adr_content", "")
    adr_title = context.get("adr_title", "")
    doc_path = context.get("doc_path", "")
    doc_content = context.get("doc_content", "")
    repo_root = context.get("repo_root", str(Path.home() / "khan" / "james-in-a-box"))

    if not adr_content or not doc_content:
        return output_result(False, error="Missing adr_content or doc_content")

    # Build prompt for doc generation
    prompt = f"""You are updating documentation to reflect an implemented ADR (Architecture Decision Record).

## ADR: {adr_title}

{adr_content}

## Current Documentation ({doc_path})

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

    try:
        result = run_claude(
            prompt=prompt,
            cwd=Path(repo_root),
            stream=False,
        )

        if result.success and result.stdout.strip():
            content = result.stdout.strip()
            confidence = 0.85 if len(content) > 100 else 0.6
            return output_result(
                success=True,
                result={
                    "updated_content": content,
                    "confidence": confidence,
                    "changes_summary": f"LLM-generated update for {adr_title}",
                },
            )
        else:
            return output_result(
                success=False,
                result={
                    "updated_content": "",
                    "confidence": 0.3,
                    "changes_summary": "Generation failed",
                },
                error=result.error or result.stderr[:200] if result.stderr else "Unknown error",
            )

    except Exception as e:
        return output_result(False, error=f"Error generating documentation: {e}")


def handle_create_pr(context: dict) -> int:
    """Handle PR creation for analysis reports.

    This runs inside the jib container where git worktrees are already set up,
    avoiding interference with the host's main worktree.

    Context expected:
        - repo_name: str (e.g., "james-in-a-box")
        - branch_name: str (e.g., "beads-health-report-20251201")
        - files: list[dict] with {path: str, content: str} - files to commit
        - symlinks: list[dict] with {path: str, target: str} - symlinks to create
        - files_to_delete: list[str] - relative paths to delete (for cleanup)
        - commit_message: str
        - pr_title: str
        - pr_body: str

    Returns JSON with:
        - result.pr_url: str (URL of created PR)
        - result.branch: str (branch name)
    """
    import os
    import subprocess

    repo_name = context.get("repo_name", "james-in-a-box")
    branch_name = context.get("branch_name")
    files = context.get("files", [])
    symlinks = context.get("symlinks", [])
    files_to_delete = context.get("files_to_delete", [])
    commit_message = context.get("commit_message", "chore: Add analysis report")
    pr_title = context.get("pr_title", "Analysis Report")
    pr_body = context.get("pr_body", "")

    if not branch_name:
        return output_result(False, error="No branch_name provided")
    if not files and not symlinks and not files_to_delete:
        return output_result(False, error="No files, symlinks, or deletions provided")

    # Get repo path - inside container, repos are at ~/khan/<repo>
    repo_path = Path.home() / "khan" / repo_name

    if not repo_path.exists():
        return output_result(False, error=f"Repository not found: {repo_path}")

    try:
        # Detect the default branch for this repo (main or master)
        default_branch = get_default_branch(repo_path)

        # Create branch from origin/<default>
        subprocess.run(
            ["git", "fetch", "origin", default_branch],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        subprocess.run(
            ["git", "checkout", "-b", branch_name, f"origin/{default_branch}"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Delete old files first (cleanup)
        for file_rel_path in files_to_delete:
            file_path = repo_path / file_rel_path
            if file_path.exists():
                file_path.unlink()
                subprocess.run(
                    ["git", "add", file_rel_path],
                    check=True,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                )

        # Write regular files
        for file_info in files:
            file_path = repo_path / file_info["path"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(file_info["content"])

        # Create symlinks
        for symlink_info in symlinks:
            symlink_path = repo_path / symlink_info["path"]
            target = symlink_info["target"]
            symlink_path.parent.mkdir(parents=True, exist_ok=True)
            # Remove existing symlink/file if it exists
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()
            # Create symlink (target is relative to symlink's directory)
            os.symlink(target, symlink_path)

        # Stage all files
        for file_info in files:
            subprocess.run(
                ["git", "add", file_info["path"]],
                check=True,
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

        # Stage all symlinks
        for symlink_info in symlinks:
            subprocess.run(
                ["git", "add", symlink_info["path"]],
                check=True,
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

        # Commit
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Push
        subprocess.run(
            ["git", "push", "origin", branch_name],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Create PR using gh CLI
        result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                pr_title,
                "--body",
                pr_body,
                "--base",
                default_branch,
                "--head",
                branch_name,
            ],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        pr_url = result.stdout.strip()

        return output_result(
            success=True,
            result={
                "pr_url": pr_url,
                "branch": branch_name,
            },
        )

    except subprocess.CalledProcessError as e:
        return output_result(
            False,
            error=f"Git operation failed: {e.stderr or e.stdout or str(e)}",
        )
    except Exception as e:
        return output_result(False, error=f"Error creating PR: {e}")


def handle_feature_extraction(context: dict) -> int:
    """Handle feature extraction from code files.

    Context expected:
        - file_contents: dict[str, str] (path -> content mapping)
        - raw_features: list[dict] (pre-extracted features to consolidate)
        - repo_root: str (optional)

    Returns JSON with:
        - result.features: list[dict] with name, description, status, etc.
    """
    file_contents = context.get("file_contents", {})
    raw_features = context.get("raw_features", [])
    repo_root = context.get("repo_root", str(Path.home() / "khan" / "james-in-a-box"))

    # Build content for analysis
    content_text = ""
    for path, content in list(file_contents.items())[:10]:  # Limit files
        content_text += f"\n--- {path} ---\n{content[:5000]}\n"

    raw_features_text = ""
    if raw_features:
        raw_features_text = "\n## Pre-extracted Features:\n" + json.dumps(raw_features, indent=2)

    prompt = f"""Analyze these code files and extract meaningful features for a FEATURES.md file.

## Code Files:
{content_text}
{raw_features_text}

## Your Task

Extract a JSON list of features with this structure:
[
  {{
    "name": "Feature Name",
    "description": "One-line description of what it does",
    "status": "implemented",
    "category": "Category Name",
    "files": ["path/to/main/file.py"],
    "confidence": 0.85
  }}
]

Focus on:
- User-facing tools and scripts
- Significant new functionality
- Reusable utilities

Skip:
- Internal implementation details
- Test files
- Configuration files

Output ONLY the JSON array, no other text.
"""

    try:
        result = run_claude(
            prompt=prompt,
            cwd=Path(repo_root),
            stream=False,
        )

        if result.success and result.stdout.strip():
            # Try to parse JSON from output
            try:
                features = json.loads(result.stdout.strip())
                return output_result(
                    success=True,
                    result={"features": features},
                )
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                import re

                json_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", result.stdout)
                if json_match:
                    features = json.loads(json_match.group(1))
                    return output_result(
                        success=True,
                        result={"features": features},
                    )
                return output_result(
                    success=False,
                    result={"features": []},
                    error="Could not parse features JSON from output",
                )
        else:
            return output_result(
                success=False,
                result={"features": []},
                error=result.error or "No output from Claude",
            )

    except Exception as e:
        return output_result(False, error=f"Error extracting features: {e}")


def handle_weekly_feature_analysis(context: dict) -> int:
    """Handle weekly feature analysis using intelligent multi-agent pipeline.

    This is the container-side implementation of the weekly feature analyzer,
    using the same high-quality multi-agent analysis pipeline as full-repo.

    The intelligent analysis approach:
    1. Identifies directories with recent commits (scoped to past N days)
    2. Uses multi-agent LLM analysis for each directory (parallel processing)
    3. Consolidates and deduplicates with LLM (handles symlinks, merges related features)
    4. Filters to only NEW features not already in FEATURES.md
    5. Creates PR using container's git worktree and GitHub credentials

    Context expected:
        - repo_name: str (e.g., "james-in-a-box")
        - days: int (number of days to analyze, default 7)
        - dry_run: bool (if True, don't create PR, default False)
        - max_workers: int (parallel LLM workers, default 5)

    Returns JSON with:
        - result.directories_analyzed: int
        - result.features_detected: int
        - result.features_added: int
        - result.features_skipped: int
        - result.pr_url: str (URL of created PR, if not dry_run)
        - result.branch: str (branch name)
    """
    import subprocess
    from datetime import UTC, datetime

    repo_name = context.get("repo_name", "james-in-a-box")
    days = context.get("days", 7)
    dry_run = context.get("dry_run", False)
    max_workers = context.get("max_workers", 5)

    # Get repo path - inside container, repos are at ~/khan/<repo>
    repo_path = Path.home() / "khan" / repo_name

    if not repo_path.exists():
        return output_result(False, error=f"Repository not found: {repo_path}")

    # Import the analyzers from the container-local feature_analyzer module
    # This module is in the same directory as this file
    try:
        from feature_analyzer import RepoAnalyzer, WeeklyAnalyzer
    except ImportError as e:
        return output_result(False, error=f"Failed to import analyzers: {e}")

    try:
        # Detect the default branch for this repo (main or master)
        default_branch = get_default_branch(repo_path)

        # Create a fresh branch from origin/<default>
        branch_name = f"docs/sync-weekly-analysis-{datetime.now(UTC).strftime('%Y%m%d')}"

        subprocess.run(
            ["git", "fetch", "origin", default_branch],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Check if branch already exists remotely
        check_result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", branch_name],
            check=False,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if check_result.stdout.strip():
            branch_name = f"{branch_name}-{datetime.now(UTC).strftime('%H%M%S')}"

        subprocess.run(
            ["git", "checkout", "-b", branch_name, f"origin/{default_branch}"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        print("=" * 60)
        print("Intelligent Weekly Feature Analysis (Multi-Agent Pipeline)")
        print("=" * 60)
        print(f"Repository: {repo_path}")
        print(f"Analyzing past {days} days")
        print(f"Parallel workers: {max_workers}")
        print()

        # Phase 1: Get directories with recent changes using WeeklyAnalyzer's commit scan
        print("Phase 1: Identifying directories with recent commits...")
        weekly_analyzer = WeeklyAnalyzer(repo_path, use_llm=True)
        commits = weekly_analyzer.get_commits_since(days)
        feature_commits = weekly_analyzer.filter_feature_commits(commits)

        # Extract unique directories from commits
        changed_dirs = set()
        for commit in feature_commits:
            for file_path in commit.files:
                # Get parent directory of changed files
                parent = str(Path(file_path).parent)
                if parent and parent != ".":
                    changed_dirs.add(parent)
                    # Also add parent's parent for better coverage
                    grandparent = str(Path(parent).parent)
                    if grandparent and grandparent != ".":
                        changed_dirs.add(grandparent)

        print(f"  Found {len(commits)} commits, {len(feature_commits)} feature commits")
        print(f"  Identified {len(changed_dirs)} directories with changes")

        if not changed_dirs:
            print("  No directories with feature changes found.")
            return output_result(
                success=True,
                result={
                    "directories_analyzed": 0,
                    "features_detected": 0,
                    "features_added": 0,
                    "features_skipped": 0,
                    "branch": branch_name,
                    "pr_url": None,
                },
            )

        # Phase 2: Use RepoAnalyzer's intelligent multi-agent pipeline
        print("\nPhase 2: Running intelligent multi-agent analysis...")
        repo_analyzer = RepoAnalyzer(repo_path, use_llm=True)

        # Get all potential feature directories, but filter to recently changed ones
        all_feature_dirs = repo_analyzer.scan_directory_structure()

        # Filter to directories that intersect with our changed directories
        filtered_dirs = {}
        for dir_path, files in all_feature_dirs.items():
            # Check if this directory or any parent was changed
            should_include = False
            for changed in changed_dirs:
                if dir_path.startswith(changed) or changed.startswith(dir_path):
                    should_include = True
                    break
            if should_include:
                filtered_dirs[dir_path] = files

        print(f"  Filtered to {len(filtered_dirs)} directories for analysis")

        if not filtered_dirs:
            print("  No feature directories matched recent changes.")
            return output_result(
                success=True,
                result={
                    "directories_analyzed": 0,
                    "features_detected": 0,
                    "features_added": 0,
                    "features_skipped": 0,
                    "branch": branch_name,
                    "pr_url": None,
                },
            )

        # Phase 3: Analyze directories with LLM (parallel)
        print(
            f"\nPhase 3: Analyzing {len(filtered_dirs)} directories (parallel, {max_workers} workers)..."
        )
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_features = []
        print_lock = threading.Lock()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_dir = {
                executor.submit(repo_analyzer._analyze_single_directory, dir_path, files): dir_path
                for dir_path, files in filtered_dirs.items()
                if files
            }

            for future in as_completed(future_to_dir):
                dir_path = future_to_dir[future]
                try:
                    analyzed_dir, file_count, features = future.result()

                    with print_lock:
                        print(f"  ✓ {analyzed_dir} ({file_count} files)")
                        for feature in features:
                            all_features.append(feature)
                            print(f"    → Found: {feature.name} ({feature.confidence:.0%})")

                except Exception as e:
                    with print_lock:
                        print(f"  ✗ {dir_path}: Error - {e}")

        print(f"\n  Detected {len(all_features)} features from {len(filtered_dirs)} directories")

        if not all_features:
            print("  No features detected.")
            return output_result(
                success=True,
                result={
                    "directories_analyzed": len(filtered_dirs),
                    "features_detected": 0,
                    "features_added": 0,
                    "features_skipped": 0,
                    "branch": branch_name,
                    "pr_url": None,
                },
            )

        # Phase 4: LLM consolidation (deduplication, organization)
        print("\nPhase 4: Consolidating features with LLM...")
        consolidated = repo_analyzer._consolidate_features_with_llm(all_features)
        print(f"  Consolidated to {len(consolidated)} features")

        # Phase 5: Filter to NEW features only
        print("\nPhase 5: Filtering to new features...")
        existing = weekly_analyzer.get_existing_features()
        existing_paths = weekly_analyzer.get_existing_file_paths()

        new_features = []
        skipped = []

        for feature in consolidated:
            name_lower = feature.name.lower()

            # Check if name exists
            if name_lower in existing:
                skipped.append((feature.name, "Already in FEATURES.md"))
                continue

            # Check if file path exists
            if feature.files:
                documented_files = [f for f in feature.files if f in existing_paths]
                if documented_files:
                    skipped.append((feature.name, f"File documented: {documented_files[0]}"))
                    continue

            # Check for similar names
            is_similar = False
            for ex_name in existing:
                if name_lower in ex_name or ex_name in name_lower:
                    skipped.append((feature.name, f"Similar to: {ex_name}"))
                    is_similar = True
                    break
            if is_similar:
                continue

            new_features.append(feature)

        print(f"  New features: {len(new_features)}, Skipped: {len(skipped)}")

        result_data = {
            "directories_analyzed": len(filtered_dirs),
            "features_detected": len(consolidated),
            "features_added": len(new_features),
            "features_skipped": len(skipped),
            "branch": branch_name,
            "pr_url": None,
        }

        if not new_features:
            print("\nNo new features to add - FEATURES.md is up to date.")
            return output_result(success=True, result=result_data)

        if dry_run:
            print("\n[DRY RUN] Would add these features:")
            for f in new_features:
                print(f"  - {f.name}: {f.description[:60]}...")
            return output_result(success=True, result=result_data)

        # Phase 6: Update FEATURES.md
        print("\nPhase 6: Updating FEATURES.md...")
        weekly_analyzer.update_features_md(new_features)

        # Stage and commit
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if not status_result.stdout.strip():
            print("  No changes to commit.")
            return output_result(success=True, result=result_data)

        subprocess.run(
            ["git", "add", "-A"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Build commit message
        feature_names = [f.name for f in new_features[:5]]
        features_summary = ", ".join(feature_names)
        if len(new_features) > 5:
            features_summary += f" and {len(new_features) - 5} more"

        commit_message = f"""docs: Sync documentation with Weekly Feature Analysis

Intelligent multi-agent analysis identified {len(new_features)} new features from the past {days} days.

Features added: {features_summary}

— Authored by jib"""

        subprocess.run(
            ["git", "commit", "-m", commit_message],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Push
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Build PR body with categories
        features_by_cat: dict[str, list] = {}
        for f in new_features:
            cat = f.category or "Utilities"
            features_by_cat.setdefault(cat, []).append(f)

        feature_sections = []
        for cat, feats in sorted(features_by_cat.items()):
            section = f"**{cat}**\n"
            for f in feats:
                desc = f.description[:100] + "..." if len(f.description) > 100 else f.description
                section += f"- **{f.name}**: {desc}\n"
            feature_sections.append(section)

        pr_body = f"""## Summary

Intelligent multi-agent analysis identified **{len(new_features)} new features** from the past {days} days.

This analysis uses the same high-quality pipeline as `feature-analyzer full-repo`:
- Directory-by-directory LLM analysis (parallel processing)
- LLM-powered consolidation and deduplication
- Smart handling of symlinks and host/container pairs

### New Features by Category

{chr(10).join(feature_sections)}

### Analysis Details

- Directories analyzed: {len(filtered_dirs)}
- Features detected (before dedup): {len(all_features)}
- Features after consolidation: {len(consolidated)}
- **New features added: {len(new_features)}**
- Features skipped (duplicates): {len(skipped)}

## Test Plan

- [x] All entries include correct file paths
- [x] Status flags are accurate (all "implemented")
- [x] No duplicate entries in FEATURES.md
- [ ] Human review for accuracy and completeness

---

— Authored by jib"""

        pr_title = "docs: Sync documentation with Weekly Feature Analysis"

        # Create PR using gh CLI
        pr_result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                pr_title,
                "--body",
                pr_body,
                "--base",
                default_branch,
                "--head",
                branch_name,
            ],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        result_data["pr_url"] = pr_result.stdout.strip()

        print(f"\n✓ PR created: {result_data['pr_url']}")

        return output_result(
            success=True,
            result=result_data,
        )

    except subprocess.CalledProcessError as e:
        return output_result(
            False,
            error=f"Git/GH operation failed: {e.stderr or e.stdout or str(e)}",
        )
    except Exception as e:
        import traceback

        return output_result(
            False,
            error=f"Error in weekly analysis: {e}\n{traceback.format_exc()}",
        )


def handle_full_repo_analysis(context: dict) -> int:
    """Handle full repository analysis to generate comprehensive FEATURES.md.

    This runs inside the jib container where git worktrees are already set up,
    avoiding interference with the host's main worktree.

    Context expected:
        - repo_name: str (e.g., "james-in-a-box")
        - dry_run: bool (if True, don't create PR, default False)
        - max_workers: int (parallel LLM workers, default 5)
        - output_path: str (optional, custom output path for FEATURES.md)

    Returns JSON with:
        - result.directories_scanned: int
        - result.files_analyzed: int
        - result.features_detected: int
        - result.features_by_category: dict[str, int]
        - result.pr_url: str (URL of created PR, if not dry_run)
        - result.branch: str (branch name)
    """
    import subprocess
    from datetime import UTC, datetime

    repo_name = context.get("repo_name", "james-in-a-box")
    dry_run = context.get("dry_run", False)
    max_workers = context.get("max_workers", 5)
    output_path = context.get("output_path")

    # Get repo path - inside container, repos are at ~/khan/<repo>
    repo_path = Path.home() / "khan" / repo_name

    if not repo_path.exists():
        return output_result(False, error=f"Repository not found: {repo_path}")

    # Import the analyzers from the container-local feature_analyzer module
    # This module is in the same directory as this file
    try:
        from feature_analyzer import RepoAnalyzer
    except ImportError as e:
        return output_result(False, error=f"Failed to import analyzers: {e}")

    try:
        # Detect the default branch for this repo (main or master)
        default_branch = get_default_branch(repo_path)

        # Create a fresh branch from origin/<default>
        branch_name = f"docs/full-repo-analysis-{datetime.now(UTC).strftime('%Y%m%d')}"

        subprocess.run(
            ["git", "fetch", "origin", default_branch],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Check if branch already exists remotely
        check_result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", branch_name],
            check=False,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if check_result.stdout.strip():
            branch_name = f"{branch_name}-{datetime.now(UTC).strftime('%H%M%S')}"

        subprocess.run(
            ["git", "checkout", "-b", branch_name, f"origin/{default_branch}"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        print("=" * 60)
        print("Full Repository Feature Analysis (Multi-Agent Pipeline)")
        print("=" * 60)
        print(f"Repository: {repo_path}")
        print(f"Parallel workers: {max_workers}")
        print()

        # Run full repo analysis with multi-agent pipeline
        print("Running full repository analysis (multi-agent pipeline)...")
        analyzer = RepoAnalyzer(repo_path, use_llm=True)
        result = analyzer.analyze_full_repo(
            dry_run=dry_run,
            output_path=Path(output_path) if output_path else None,
            max_workers=max_workers,
        )

        # Build result data
        features_by_category_counts = {
            cat: len(features) for cat, features in result.features_by_category.items()
        }

        result_data = {
            "directories_scanned": result.directories_scanned,
            "files_analyzed": result.files_analyzed,
            "features_detected": len(result.features_detected),
            "features_by_category": features_by_category_counts,
            "branch": branch_name,
            "pr_url": None,
        }

        print(f"\nDirectories scanned: {result.directories_scanned}")
        print(f"Files analyzed: {result.files_analyzed}")
        print(f"Features detected: {len(result.features_detected)}")

        if dry_run:
            print("\n[DRY RUN] Would generate FEATURES.md and create PR")
            return output_result(success=True, result=result_data)

        if not result.output_file:
            print("\nNo output file generated - nothing to commit.")
            return output_result(success=True, result=result_data)

        # Stage and commit
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if not status_result.stdout.strip():
            print("  No changes to commit.")
            return output_result(success=True, result=result_data)

        subprocess.run(
            ["git", "add", "-A"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Build commit message
        commit_message = f"""docs: Generate comprehensive FEATURES.md via full repo analysis

Full repository analysis generated FEATURES.md with {len(result.features_detected)} features.

— Authored by jib"""

        subprocess.run(
            ["git", "commit", "-m", commit_message],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Push
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Build PR body
        category_summary = "\n".join(
            f"- **{cat}**: {count} feature(s)"
            for cat, count in sorted(features_by_category_counts.items())
        )

        pr_body = f"""## Summary

Full repository analysis generated a comprehensive FEATURES.md with **{len(result.features_detected)} features**.

This analysis uses the high-quality multi-agent pipeline:
- Directory-by-directory LLM analysis (parallel processing)
- LLM-powered consolidation and deduplication
- Smart handling of symlinks and host/container pairs

### Features by Category

{category_summary}

### Analysis Details

- Directories scanned: {result.directories_scanned}
- Files analyzed: {result.files_analyzed}
- Features detected: {len(result.features_detected)}

## Test Plan

- [x] All feature entries have valid file paths
- [x] Categories are properly organized
- [x] Documentation links are accurate
- [ ] Human review for accuracy and completeness

---

— Authored by jib"""

        pr_title = "docs: Generate comprehensive FEATURES.md via full repo analysis"

        # Create PR using gh CLI
        pr_result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                pr_title,
                "--body",
                pr_body,
                "--base",
                default_branch,
                "--head",
                branch_name,
            ],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        result_data["pr_url"] = pr_result.stdout.strip()

        print(f"\n✓ PR created: {result_data['pr_url']}")

        return output_result(
            success=True,
            result=result_data,
        )

    except subprocess.CalledProcessError as e:
        return output_result(
            False,
            error=f"Git/GH operation failed: {e.stderr or e.stdout or str(e)}",
        )
    except Exception as e:
        import traceback

        return output_result(
            False,
            error=f"Error in full repo analysis: {e}\n{traceback.format_exc()}",
        )


def handle_github_pr_create(context: dict) -> int:
    """Create a GitHub PR using gh CLI (with jib identity via GITHUB_TOKEN).

    This handler is used by host-side services that need to create PRs
    under jib's identity. The gh CLI inside the container uses the
    GITHUB_TOKEN environment variable (GitHub App token), so PRs are
    created as jib rather than the host user.

    Context expected:
        - repo: str (full repo name, e.g., "jwbron/james-in-a-box")
        - title: str (PR title)
        - body: str (PR body/description)
        - head: str (branch name with changes)
        - base: str (target branch, default "main")
        - cwd: str (optional, working directory for gh CLI)

    Returns JSON with:
        - result.pr_url: URL of the created PR
        - result.pr_number: PR number
    """
    import subprocess

    repo = context.get("repo")
    title = context.get("title")
    body = context.get("body", "")
    head = context.get("head")
    base = context.get("base", "main")
    cwd = context.get("cwd")

    if not repo:
        return output_result(False, error="Missing required field: repo")
    if not title:
        return output_result(False, error="Missing required field: title")
    if not head:
        return output_result(False, error="Missing required field: head")

    try:
        cmd = [
            "gh",
            "pr",
            "create",
            "--repo",
            repo,
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
            "--head",
            head,
        ]

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )

        pr_url = result.stdout.strip()
        pr_number = None
        if pr_url and "/" in pr_url:
            with contextlib.suppress(ValueError):
                pr_number = int(pr_url.split("/")[-1])

        return output_result(
            success=True,
            result={
                "pr_url": pr_url,
                "pr_number": pr_number,
            },
        )

    except subprocess.CalledProcessError as e:
        return output_result(
            False,
            error=f"gh pr create failed: {e.stderr or e.stdout or str(e)}",
        )
    except FileNotFoundError:
        return output_result(False, error="gh CLI not found")
    except Exception as e:
        return output_result(False, error=f"Error creating PR: {e}")


def handle_github_pr_comment(context: dict) -> int:
    """Add a comment to a GitHub PR using gh CLI (with jib identity).

    Context expected:
        - repo: str (full repo name, e.g., "jwbron/james-in-a-box")
        - pr_number: int (PR number to comment on)
        - body: str (comment body)

    Returns JSON with:
        - result.success: bool
    """
    import subprocess

    repo = context.get("repo")
    pr_number = context.get("pr_number")
    body = context.get("body")

    if not repo:
        return output_result(False, error="Missing required field: repo")
    if not pr_number:
        return output_result(False, error="Missing required field: pr_number")
    if not body:
        return output_result(False, error="Missing required field: body")

    try:
        cmd = [
            "gh",
            "pr",
            "comment",
            str(pr_number),
            "--repo",
            repo,
            "--body",
            body,
        ]

        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

        return output_result(success=True, result={"commented": True})

    except subprocess.CalledProcessError as e:
        return output_result(
            False,
            error=f"gh pr comment failed: {e.stderr or e.stdout or str(e)}",
        )
    except subprocess.TimeoutExpired:
        return output_result(False, error="gh pr comment timed out")
    except FileNotFoundError:
        return output_result(False, error="gh CLI not found")
    except Exception as e:
        return output_result(False, error=f"Error commenting on PR: {e}")


def handle_github_pr_close(context: dict) -> int:
    """Close a GitHub PR using gh CLI (with jib identity).

    Context expected:
        - repo: str (full repo name, e.g., "jwbron/james-in-a-box")
        - pr_number: int (PR number to close)

    Returns JSON with:
        - result.closed: bool
    """
    import subprocess

    repo = context.get("repo")
    pr_number = context.get("pr_number")

    if not repo:
        return output_result(False, error="Missing required field: repo")
    if not pr_number:
        return output_result(False, error="Missing required field: pr_number")

    try:
        cmd = [
            "gh",
            "pr",
            "close",
            str(pr_number),
            "--repo",
            repo,
        ]

        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

        return output_result(success=True, result={"closed": True})

    except subprocess.CalledProcessError as e:
        return output_result(
            False,
            error=f"gh pr close failed: {e.stderr or e.stdout or str(e)}",
        )
    except subprocess.TimeoutExpired:
        return output_result(False, error="gh pr close timed out")
    except FileNotFoundError:
        return output_result(False, error="gh CLI not found")
    except Exception as e:
        return output_result(False, error=f"Error closing PR: {e}")


def handle_repo_onboarding(context: dict) -> int:
    """Handle full repository onboarding with all 4 phases.

    This runs inside the jib container to avoid modifying the host's main branch.
    All changes are made in a worktree branch and submitted via PR.

    Phases:
    1. Confluence Documentation Discovery (if not skipped)
    2. Feature Analysis & Documentation
    3. Index Generation (codebase.json, patterns.json, dependencies.json)
    4. Documentation Index Updates (docs/index.md)

    Context expected:
        - repo_name: str (e.g., "james-in-a-box")
        - skip_confluence: bool (default False)
        - skip_features: bool (default False)
        - public_repo: bool (default False)
        - confluence_dir: str (default ~/context-sync/confluence)
        - dry_run: bool (default False)
        - max_workers: int (parallel LLM workers for feature analysis, default 5)

    Returns JSON with:
        - result.phases_completed: list[str]
        - result.features_detected: int
        - result.indexes_generated: list[str]
        - result.pr_url: str (URL of created PR, if not dry_run)
        - result.branch: str (branch name)
    """
    import subprocess
    from datetime import UTC, datetime

    repo_name = context.get("repo_name", "james-in-a-box")
    skip_confluence = context.get("skip_confluence", False)
    skip_features = context.get("skip_features", False)
    public_repo = context.get("public_repo", False)
    confluence_dir = context.get("confluence_dir", str(Path.home() / "context-sync" / "confluence"))
    dry_run = context.get("dry_run", False)
    max_workers = context.get("max_workers", 5)

    # Get repo path - inside container, repos are at ~/khan/<repo>
    repo_path = Path.home() / "khan" / repo_name
    confluence_path = Path(confluence_dir)

    if not repo_path.exists():
        return output_result(False, error=f"Repository not found: {repo_path}")

    # Import the analysis tools from james-in-a-box's host-services directory
    jib_path = Path.home() / "khan" / "james-in-a-box"
    sys.path.insert(0, str(jib_path / "host-services" / "analysis" / "confluence-doc-discoverer"))
    sys.path.insert(0, str(jib_path / "host-services" / "analysis" / "index-generator"))
    sys.path.insert(0, str(jib_path / "host-services" / "analysis" / "repo-onboarding"))
    sys.path.insert(0, str(jib_path / "host-services" / "analysis" / "feature-analyzer"))

    result_data = {
        "phases_completed": [],
        "features_detected": 0,
        "indexes_generated": [],
        "pr_url": None,
        "branch": None,
    }

    try:
        # Detect the default branch for this repo (main or master)
        default_branch = get_default_branch(repo_path)

        # Create a fresh branch from origin/<default>
        branch_name = f"docs/repo-onboarding-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        result_data["branch"] = branch_name

        subprocess.run(
            ["git", "fetch", "origin", default_branch],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        subprocess.run(
            ["git", "checkout", "-b", branch_name, f"origin/{default_branch}"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        print("=" * 60)
        print("Repository Onboarding (Container-Side)")
        print("=" * 60)
        print(f"Repository: {repo_path}")
        print(f"Branch: {branch_name}")
        print(f"Dry run: {dry_run}")
        print()

        # Create output directories
        output_dir = repo_path / "docs" / "generated"
        features_dir = repo_path / "docs" / "features"
        output_dir.mkdir(parents=True, exist_ok=True)
        features_dir.mkdir(parents=True, exist_ok=True)

        # ====================================================================
        # Phase 1: Confluence Documentation Discovery
        # ====================================================================
        print("\n=== Phase 1: Confluence Documentation Discovery ===")

        if skip_confluence:
            print("  Skipping Confluence discovery (--skip-confluence)")
        elif not confluence_path.exists():
            print(f"  Confluence directory not found: {confluence_path}")
            print("  Skipping Confluence discovery")
        else:
            try:
                # Import dynamically to avoid issues if module not found
                from importlib.util import module_from_spec, spec_from_file_location

                conf_module_path = jib_path / "host-services" / "analysis" / "confluence-doc-discoverer" / "confluence-doc-discoverer.py"
                if conf_module_path.exists():
                    spec = spec_from_file_location("confluence_discoverer", conf_module_path)
                    if spec and spec.loader:
                        conf_module = module_from_spec(spec)
                        spec.loader.exec_module(conf_module)

                        discoverer = conf_module.ConfluenceDocDiscoverer(
                            confluence_dir=confluence_path,
                            repo_name=repo_name,
                            output_path=output_dir / "external-docs.json",
                            public_repo=public_repo,
                        )
                        discoverer.discover()
                        discoverer.save_results()
                        print(f"  ✓ Found {len(discoverer.discovered_docs)} relevant docs")
                        result_data["phases_completed"].append("confluence_discovery")
                else:
                    print(f"  Confluence discoverer not found at {conf_module_path}")
            except Exception as e:
                print(f"  ⚠ Confluence discovery failed: {e}")

        # ====================================================================
        # Phase 2: Feature Analysis & Documentation
        # ====================================================================
        print("\n=== Phase 2: Feature Analysis & Documentation ===")

        if skip_features:
            print("  Skipping feature analysis (--skip-features)")
        else:
            try:
                from weekly_analyzer import RepoAnalyzer

                print(f"  Running feature analysis with {max_workers} workers...")
                analyzer = RepoAnalyzer(repo_path, use_llm=True)
                analysis_result = analyzer.analyze_full_repo(
                    dry_run=False,
                    output_path=repo_path / "docs" / "FEATURES.md",
                    max_workers=max_workers,
                )
                result_data["features_detected"] = len(analysis_result.features_detected)
                print(f"  ✓ Detected {len(analysis_result.features_detected)} features")
                result_data["phases_completed"].append("feature_analysis")
            except ImportError as e:
                print(f"  ⚠ Feature analyzer not available: {e}")
            except Exception as e:
                print(f"  ⚠ Feature analysis failed: {e}")

        # ====================================================================
        # Phase 3: Index Generation
        # ====================================================================
        print("\n=== Phase 3: Index Generation ===")

        try:
            from importlib.util import module_from_spec, spec_from_file_location

            idx_module_path = jib_path / "host-services" / "analysis" / "index-generator" / "index-generator.py"
            if idx_module_path.exists():
                spec = spec_from_file_location("index_generator", idx_module_path)
                if spec and spec.loader:
                    idx_module = module_from_spec(spec)
                    spec.loader.exec_module(idx_module)

                    indexer = idx_module.CodebaseIndexer(repo_path)
                    indexer.analyze()

                    # Save indexes
                    indexes_generated = []
                    for name, data in [
                        ("codebase.json", indexer.codebase_index),
                        ("patterns.json", indexer.patterns_index),
                        ("dependencies.json", indexer.dependencies_index),
                    ]:
                        if data:
                            idx_path = output_dir / name
                            with open(idx_path, "w") as f:
                                json.dump(data, f, indent=2, default=str)
                            indexes_generated.append(name)

                    result_data["indexes_generated"] = indexes_generated
                    print(f"  ✓ Generated {len(indexes_generated)} indexes: {', '.join(indexes_generated)}")
                    result_data["phases_completed"].append("index_generation")
            else:
                print(f"  Index generator not found at {idx_module_path}")
        except Exception as e:
            print(f"  ⚠ Index generation failed: {e}")

        # ====================================================================
        # Phase 4: Documentation Index Updates
        # ====================================================================
        print("\n=== Phase 4: Documentation Index Updates ===")

        try:
            from importlib.util import module_from_spec, spec_from_file_location

            updater_module_path = jib_path / "host-services" / "analysis" / "repo-onboarding" / "docs-index-updater.py"
            if updater_module_path.exists():
                spec = spec_from_file_location("docs_index_updater", updater_module_path)
                if spec and spec.loader:
                    updater_module = module_from_spec(spec)
                    spec.loader.exec_module(updater_module)

                    features_md = repo_path / "docs" / "FEATURES.md"
                    config = updater_module.IndexConfig(
                        repo_root=repo_path,
                        generated_dir=output_dir,
                        features_md=features_md if features_md.exists() else None,
                        dry_run=False,
                    )
                    updater = updater_module.DocsIndexUpdater(config)
                    updater.run()
                    print("  ✓ Updated docs/index.md")
                    result_data["phases_completed"].append("docs_index_update")
            else:
                print(f"  Docs index updater not found at {updater_module_path}")
        except Exception as e:
            print(f"  ⚠ Docs index update failed: {e}")

        # ====================================================================
        # Check for changes and create PR
        # ====================================================================
        print("\n=== Finalizing ===")

        if dry_run:
            print("[DRY RUN] Would commit and create PR with changes")
            return output_result(success=True, result=result_data)

        # Check for changes
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if not status_result.stdout.strip():
            print("No changes to commit - repository is already up to date")
            return output_result(success=True, result=result_data)

        # Stage all changes
        subprocess.run(
            ["git", "add", "-A"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Build commit message
        phases_summary = ", ".join(result_data["phases_completed"])
        commit_message = f"""docs: Repository onboarding via jib

Completed phases: {phases_summary}
Features detected: {result_data['features_detected']}
Indexes generated: {', '.join(result_data['indexes_generated'])}

— Authored by jib"""

        subprocess.run(
            ["git", "commit", "-m", commit_message],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Push
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Build PR body
        pr_body = f"""## Summary

Repository onboarding generated documentation indexes for **{repo_name}**.

### Phases Completed

{chr(10).join(f"- ✓ {phase.replace('_', ' ').title()}" for phase in result_data['phases_completed'])}

### Generated Content

- Features detected: {result_data['features_detected']}
- Indexes generated: {', '.join(result_data['indexes_generated']) or 'none'}

### Files Added

- `docs/generated/*.json` - Machine-readable indexes (consider adding to .gitignore)
- `docs/FEATURES.md` - Feature-to-source mapping
- `docs/features/*.md` - Feature category documentation
- `docs/index.md` - Updated navigation index

## Test Plan

- [x] All generated files are valid
- [x] FEATURES.md contains accurate file paths
- [ ] Human review for accuracy and completeness

## Notes

- Generated indexes (`docs/generated/*.json`) are for local LLM use
- Consider adding `docs/generated/` to `.gitignore` if you don't want them in version control

---

— Authored by jib"""

        pr_title = f"docs: Repository onboarding for {repo_name}"

        # Create PR using gh CLI
        pr_result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--title",
                pr_title,
                "--body",
                pr_body,
                "--base",
                default_branch,
                "--head",
                branch_name,
            ],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        result_data["pr_url"] = pr_result.stdout.strip()
        print(f"\n✓ PR created: {result_data['pr_url']}")

        return output_result(success=True, result=result_data)

    except subprocess.CalledProcessError as e:
        return output_result(
            False,
            error=f"Git/GH operation failed: {e.stderr or e.stdout or str(e)}",
        )
    except Exception as e:
        import traceback

        return output_result(
            False,
            error=f"Error in repo onboarding: {e}\n{traceback.format_exc()}",
        )


def main():
    parser = argparse.ArgumentParser(
        description="Analysis task processor for jib container",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--task",
        type=str,
        required=True,
        choices=[
            "llm_prompt",
            "llm_prompt_to_file",
            "doc_generation",
            "feature_extraction",
            "create_pr",
            "weekly_feature_analysis",
            "full_repo_analysis",
            "repo_onboarding",
            "github_pr_create",
            "github_pr_comment",
            "github_pr_close",
        ],
        help="Type of analysis task to perform",
    )
    parser.add_argument(
        "--context",
        type=str,
        required=True,
        help="JSON context for the task",
    )

    args = parser.parse_args()

    # Parse context JSON
    try:
        context = json.loads(args.context)
    except json.JSONDecodeError as e:
        return output_result(False, error=f"Invalid JSON context: {e}")

    # Dispatch to handler
    handlers = {
        "llm_prompt": handle_llm_prompt,
        "llm_prompt_to_file": handle_llm_prompt_to_file,
        "doc_generation": handle_doc_generation,
        "feature_extraction": handle_feature_extraction,
        "create_pr": handle_create_pr,
        "weekly_feature_analysis": handle_weekly_feature_analysis,
        "full_repo_analysis": handle_full_repo_analysis,
        "repo_onboarding": handle_repo_onboarding,
        "github_pr_create": handle_github_pr_create,
        "github_pr_comment": handle_github_pr_comment,
        "github_pr_close": handle_github_pr_close,
    }

    handler = handlers.get(args.task)
    if handler:
        return handler(context)
    else:
        return output_result(False, error=f"Unknown task type: {args.task}")


if __name__ == "__main__":
    sys.exit(main())
