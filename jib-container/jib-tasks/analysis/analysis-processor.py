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
        - timeout: int (optional, default 300)
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

    timeout = context.get("timeout", 300)
    cwd = context.get("cwd")
    if cwd:
        cwd = Path(cwd)
    stream = context.get("stream", False)

    try:
        result = run_claude(
            prompt=prompt,
            timeout=timeout,
            cwd=cwd,
            stream=stream,
        )

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
            timeout=300,
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
            timeout=300,
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
        choices=["llm_prompt", "doc_generation", "feature_extraction", "create_pr"],
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
        "doc_generation": handle_doc_generation,
        "feature_extraction": handle_feature_extraction,
        "create_pr": handle_create_pr,
    }

    handler = handlers.get(args.task)
    if handler:
        return handler(context)
    else:
        return output_result(False, error=f"Unknown task type: {args.task}")


if __name__ == "__main__":
    sys.exit(main())
