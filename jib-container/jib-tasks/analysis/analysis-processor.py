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


# Import shared modules - navigate from jib-tasks/analysis up to repo root, then shared
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
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
        # Create branch from origin/main
        subprocess.run(
            ["git", "fetch", "origin", "main"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        subprocess.run(
            ["git", "checkout", "-b", branch_name, "origin/main"],
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
                "main",
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
    """Handle weekly feature analysis - runs entirely in the container.

    This is the container-side implementation of the weekly feature analyzer.
    It runs the analysis and creates PRs using the container's git worktree
    and GitHub credentials, ensuring PRs are opened by 'jib' (not the host user).

    Context expected:
        - repo_name: str (e.g., "james-in-a-box")
        - days: int (number of days to analyze, default 7)
        - generate_docs: bool (whether to generate docs, default True)
        - deep_analysis: bool (whether to do deep code analysis, default True)
        - dry_run: bool (if True, don't create PR, default False)

    Returns JSON with:
        - result.commits_analyzed: int
        - result.features_detected: int
        - result.features_added: int
        - result.features_skipped: int
        - result.docs_generated: list[str]
        - result.pr_url: str (URL of created PR, if not dry_run)
        - result.branch: str (branch name)
    """
    import os
    import subprocess
    from datetime import datetime, UTC

    repo_name = context.get("repo_name", "james-in-a-box")
    days = context.get("days", 7)
    generate_docs = context.get("generate_docs", True)
    deep_analysis = context.get("deep_analysis", True)
    dry_run = context.get("dry_run", False)

    # Get repo path - inside container, repos are at ~/khan/<repo>
    repo_path = Path.home() / "khan" / repo_name

    if not repo_path.exists():
        return output_result(False, error=f"Repository not found: {repo_path}")

    # Import the weekly analyzer from the host-services directory
    # This is safe because we're inside the container and have access to the mounted code
    sys.path.insert(0, str(repo_path / "host-services" / "analysis" / "feature-analyzer"))

    try:
        from weekly_analyzer import WeeklyAnalyzer, AnalysisResult
    except ImportError as e:
        return output_result(False, error=f"Failed to import WeeklyAnalyzer: {e}")

    try:
        # Create a fresh branch from origin/main
        branch_name = f"docs/sync-weekly-analysis-{datetime.now(UTC).strftime('%Y%m%d')}"

        subprocess.run(
            ["git", "fetch", "origin", "main"],
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
            # Branch exists, add timestamp suffix
            branch_name = f"{branch_name}-{datetime.now(UTC).strftime('%H%M%S')}"

        subprocess.run(
            ["git", "checkout", "-b", branch_name, "origin/main"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Run the weekly analyzer (this modifies FEATURES.md and generates docs)
        # Note: We use use_llm=True because we're inside the container with Claude access
        analyzer = WeeklyAnalyzer(repo_path, use_llm=True)
        analysis_result = analyzer.analyze_and_update(
            days=days,
            dry_run=dry_run,
            generate_docs=generate_docs,
            deep_analysis=deep_analysis,
        )

        result_data = {
            "commits_analyzed": analysis_result.commits_analyzed,
            "features_detected": len(analysis_result.features_detected),
            "features_added": len(analysis_result.features_added),
            "features_skipped": len(analysis_result.features_skipped),
            "docs_generated": analysis_result.docs_generated,
            "branch": branch_name,
            "pr_url": None,
        }

        # If no features were added, don't create a PR
        if not analysis_result.features_added:
            return output_result(
                success=True,
                result=result_data,
            )

        if dry_run:
            return output_result(
                success=True,
                result=result_data,
            )

        # Stage and commit the changes
        # First, check what files were modified
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if not status_result.stdout.strip():
            # No changes to commit
            return output_result(
                success=True,
                result=result_data,
            )

        # Stage all changes
        subprocess.run(
            ["git", "add", "-A"],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        # Build commit message
        feature_names = [f.name for f in analysis_result.features_added[:5]]
        features_summary = ", ".join(feature_names)
        if len(analysis_result.features_added) > 5:
            features_summary += f" and {len(analysis_result.features_added) - 5} more"

        commit_message = f"""docs: Sync documentation with Weekly Feature Analysis

Weekly code analysis identified {len(analysis_result.features_added)} new features from the past {days} days.

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

        # Build PR body
        feature_bullets = []
        for feature in analysis_result.features_added[:10]:
            desc = feature.description[:100] + "..." if len(feature.description) > 100 else feature.description
            feature_bullets.append(f"- **{feature.name}** ({feature.category}): {desc}")
        if len(analysis_result.features_added) > 10:
            feature_bullets.append(f"- *...and {len(analysis_result.features_added) - 10} more*")

        pr_body = f"""## Summary

Weekly code analysis identified {len(analysis_result.features_added)} new features from the past {days} days.


### New Features Detected

{chr(10).join(feature_bullets)}

### Analysis Details

- Commits analyzed: {analysis_result.commits_analyzed}
- Features detected: {len(analysis_result.features_detected)}
- Features added: {len(analysis_result.features_added)}
- Features skipped: {len(analysis_result.features_skipped)}

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
                "main",
                "--head",
                branch_name,
            ],
            check=True,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        result_data["pr_url"] = pr_result.stdout.strip()

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
    }

    handler = handlers.get(args.task)
    if handler:
        return handler(context)
    else:
        return output_result(False, error=f"Unknown task type: {args.task}")


if __name__ == "__main__":
    sys.exit(main())
