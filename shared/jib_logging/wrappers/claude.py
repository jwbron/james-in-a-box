"""
Claude Code wrapper for jib_logging.

Wraps Claude Code CLI invocations to capture model interactions with structured logging.
This is a basic wrapper for Phase 2 - full model output capture is planned for Phase 3.

IMPORTANT: Uses stdin mode with --dangerously-skip-permissions for full tool access.
Never use --print flag which creates a restricted session.
"""

import json
from typing import Any

from .base import ToolResult, ToolWrapper


class ClaudeWrapper(ToolWrapper):
    """Wrapper for Claude Code CLI.

    Captures Claude Code invocations including:
    - Prompts (summarized)
    - Timing
    - Exit status

    Full model output capture (token usage, response storage) is planned for Phase 3.

    IMPORTANT: This wrapper uses stdin mode (input_text parameter) with
    --dangerously-skip-permissions flag for full tool access. The --print flag
    should NEVER be used as it creates a restricted session.

    Usage:
        from jib_logging.wrappers import claude

        # Run claude with a prompt (uses stdin mode)
        result = claude.prompt("What is the capital of France?")

        # Run claude with context file
        result = claude.run_with_file("file.py", "Explain this code")

    Note:
        The claude CLI is typically run with more complex arguments and
        may have long-running sessions. Use appropriate timeouts.
    """

    tool_name = "claude"

    def prompt(
        self,
        prompt_text: str,
        *,
        model: str | None = None,
        output_format: str | None = None,
        max_turns: int | None = None,
        context: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> ToolResult:
        """Run claude with a prompt via stdin.

        Uses stdin mode with --dangerously-skip-permissions for full tool access.
        Never uses --print which creates a restricted session.

        Args:
            prompt_text: The prompt to send (via stdin)
            model: Model to use (overrides default)
            output_format: Output format (text, json, stream-json)
            max_turns: Maximum conversation turns
            context: File or directory to add as context
            timeout: Timeout in seconds
            cwd: Working directory

        Returns:
            ToolResult with response in stdout
        """
        # Use stdin mode, NOT --print (which creates restricted session)
        args: list[str] = ["--dangerously-skip-permissions"]

        if model:
            args.extend(["--model", model])

        if output_format:
            args.extend(["--output-format", output_format])

        if max_turns:
            args.extend(["--max-turns", str(max_turns)])

        if context:
            args.extend(["--context", context])

        # Pass prompt via stdin using input_text parameter
        return self.run(*args, timeout=timeout, cwd=cwd, input_text=prompt_text)

    def run_with_file(
        self,
        file_path: str,
        prompt_text: str | None = None,
        *,
        model: str | None = None,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> ToolResult:
        """Run claude with a file as context.

        Uses stdin mode with --dangerously-skip-permissions for full tool access.

        Args:
            file_path: Path to file for context
            prompt_text: Optional prompt (if None, uses file content as prompt)
            model: Model to use
            timeout: Timeout in seconds
            cwd: Working directory

        Returns:
            ToolResult
        """
        args: list[str] = ["--dangerously-skip-permissions", "--context", file_path]

        if model:
            args.extend(["--model", model])

        # If prompt_text provided, pass via stdin; otherwise use file as prompt
        input_text = prompt_text if prompt_text else None
        return self.run(*args, timeout=timeout, cwd=cwd, input_text=input_text)

    def resume(
        self,
        session_id: str,
        prompt_text: str | None = None,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> ToolResult:
        """Resume a previous claude session.

        Uses stdin mode with --dangerously-skip-permissions for full tool access.

        Args:
            session_id: Session ID to resume
            prompt_text: Optional new prompt (via stdin)
            timeout: Timeout in seconds
            cwd: Working directory

        Returns:
            ToolResult
        """
        args: list[str] = ["--dangerously-skip-permissions", "--resume", session_id]

        # Pass prompt via stdin if provided
        return self.run(*args, timeout=timeout, cwd=cwd, input_text=prompt_text)

    def _extract_context(
        self,
        args: tuple[str, ...],
        stdout: str,
        stderr: str,
    ) -> dict[str, Any]:
        """Extract claude-specific context from command and output."""
        context: dict[str, Any] = {}

        # Extract model if specified
        if "--model" in args:
            try:
                model_idx = args.index("--model")
                if model_idx + 1 < len(args):
                    context["model"] = args[model_idx + 1]
            except (ValueError, IndexError):
                pass

        # Extract prompt (truncated for logging)
        if "-p" in args:
            try:
                prompt_idx = args.index("-p")
                if prompt_idx + 1 < len(args):
                    prompt = args[prompt_idx + 1]
                    # Truncate long prompts for logging
                    context["prompt_preview"] = (
                        prompt[:200] + "..." if len(prompt) > 200 else prompt
                    )
                    context["prompt_length"] = len(prompt)
            except (ValueError, IndexError):
                pass

        # Extract context file if provided
        if "--context" in args:
            try:
                ctx_idx = args.index("--context")
                if ctx_idx + 1 < len(args):
                    context["context_file"] = args[ctx_idx + 1]
            except (ValueError, IndexError):
                pass

        # Extract session ID if resuming
        if "--resume" in args:
            try:
                resume_idx = args.index("--resume")
                if resume_idx + 1 < len(args):
                    context["session_id"] = args[resume_idx + 1]
            except (ValueError, IndexError):
                pass

        # Check for max-turns
        if "--max-turns" in args:
            try:
                turns_idx = args.index("--max-turns")
                if turns_idx + 1 < len(args):
                    context["max_turns"] = int(args[turns_idx + 1])
            except (ValueError, IndexError):
                pass

        # Basic output info (full capture in Phase 3)
        if stdout:
            context["response_length"] = len(stdout)
            # Try to extract any error messages from stderr
            if stderr:
                context["has_stderr"] = True

        # Try to parse JSON output format for more info
        if stdout.strip().startswith("{"):
            try:
                data = json.loads(stdout)
                if "usage" in data:
                    # OpenTelemetry GenAI semantic conventions
                    usage = data["usage"]
                    if "input_tokens" in usage:
                        context["gen_ai.usage.input_tokens"] = usage["input_tokens"]
                    if "output_tokens" in usage:
                        context["gen_ai.usage.output_tokens"] = usage["output_tokens"]
                if "model" in data:
                    context["gen_ai.request.model"] = data["model"]
            except json.JSONDecodeError:
                pass

        return context
