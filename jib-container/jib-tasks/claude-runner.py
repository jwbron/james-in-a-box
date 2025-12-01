#!/usr/bin/env python3
"""
Claude Runner - Container-side script for running Claude CLI.

This script is invoked by host-side services via `jib --exec` when they need
to run Claude. Since Claude CLI is only available inside the container, this
provides a bridge for host services that need LLM capabilities.

Usage:
    jib --exec python3 claude-runner.py --prompt "Your prompt here"
    jib --exec python3 claude-runner.py --prompt-file /path/to/prompt.txt
    jib --exec python3 claude-runner.py --prompt "..." --timeout 600 --cwd /path

Output:
    Writes JSON to stdout with structure:
    {
        "success": true/false,
        "stdout": "Claude's output",
        "stderr": "Any errors",
        "returncode": 0,
        "error": null or "error message"
    }

This allows host-side code to parse the response and handle success/failure.
"""

import argparse
import json
import sys
from pathlib import Path


# Import shared modules - navigate from jib-tasks up to repo root, then shared
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
from claude import ClaudeResult, run_claude


def main():
    parser = argparse.ArgumentParser(
        description="Run Claude CLI inside container",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--prompt",
        type=str,
        help="The prompt to send to Claude",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        help="Path to file containing the prompt (alternative to --prompt)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        help="Working directory for Claude",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream output to stderr while running (stdout still gets JSON result)",
    )

    args = parser.parse_args()

    # Get prompt from either --prompt or --prompt-file
    if args.prompt:
        prompt = args.prompt
    elif args.prompt_file:
        if not args.prompt_file.exists():
            result = {
                "success": False,
                "stdout": "",
                "stderr": "",
                "returncode": -1,
                "error": f"Prompt file not found: {args.prompt_file}",
            }
            print(json.dumps(result))
            return 1
        prompt = args.prompt_file.read_text()
    else:
        # Read from stdin if no prompt specified
        prompt = sys.stdin.read()

    if not prompt.strip():
        result = {
            "success": False,
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "error": "No prompt provided",
        }
        print(json.dumps(result))
        return 1

    # Run Claude
    try:
        claude_result: ClaudeResult = run_claude(
            prompt=prompt,
            timeout=args.timeout,
            cwd=args.cwd,
            stream=args.stream,
            stream_to=sys.stderr if args.stream else None,  # Stream to stderr, not stdout
        )

        # Output result as JSON to stdout
        result = {
            "success": claude_result.success,
            "stdout": claude_result.stdout,
            "stderr": claude_result.stderr,
            "returncode": claude_result.returncode,
            "error": claude_result.error,
        }
        print(json.dumps(result))
        return 0 if claude_result.success else 1

    except Exception as e:
        result = {
            "success": False,
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "error": f"Error running Claude: {e}",
        }
        print(json.dumps(result))
        return 1


if __name__ == "__main__":
    sys.exit(main())
