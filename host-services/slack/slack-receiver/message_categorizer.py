#!/usr/bin/env python3
"""
Message Categorizer for Slack Integration

Uses Claude (via jib_exec) to categorize incoming Slack messages and determine:
1. If it's a request for a specific host function/script (run immediately)
2. If it's a general task for Claude to work on (send to container)
3. If it's a response to a previous notification (send to container)

This enables all host functions and jib scripts to be callable via natural language
through the Slack integration.

IMPORTANT: This module runs on the HOST side and delegates LLM calls to the container
via jib_exec. It does NOT import anthropic or call Claude directly - that would
violate the host-container security boundary.
"""

import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# Add shared directories to path:
# - host-services/shared for jib_exec (host-side utilities)
# - repo root shared for jib_logging (common utilities)
_host_services = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_host_services / "shared"))
sys.path.insert(0, str(_host_services.parent / "shared"))
from jib_exec import is_jib_available, jib_exec
from jib_logging import get_logger


logger = get_logger("message-categorizer")


class MessageCategory(Enum):
    """Categories for incoming messages."""

    HOST_FUNCTION = "host_function"  # Run a host-side script/function immediately
    CONTAINER_TASK = "container_task"  # Send to container for Claude processing
    RESPONSE = "response"  # Response to a previous notification thread
    COMMAND = "command"  # Explicit command (e.g., /jib, /service, help)
    UNKNOWN = "unknown"  # Could not categorize


@dataclass
class CategorizationResult:
    """Result of message categorization."""

    category: MessageCategory
    function_name: str | None = None  # For HOST_FUNCTION: which function to call
    parameters: dict[str, Any] = field(default_factory=dict)  # Parameters for the function
    confidence: float = 0.0  # Confidence score 0-1
    reasoning: str = ""  # Why this categorization was chosen
    original_text: str = ""  # Original message text

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "category": self.category.value,
            "function_name": self.function_name,
            "parameters": self.parameters,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


# Registry of available host functions with their descriptions
# This is used to build the categorization prompt
HOST_FUNCTIONS = {
    # Container management
    "jib_status": {
        "description": "Check the jib container status (running/stopped, uptime)",
        "triggers": ["container status", "is jib running", "check container", "container health"],
        "parameters": {},
    },
    "jib_restart": {
        "description": "Restart the jib container",
        "triggers": ["restart container", "restart jib", "reboot jib"],
        "parameters": {},
    },
    "jib_rebuild": {
        "description": "Rebuild and restart the jib container from scratch",
        "triggers": ["rebuild container", "rebuild jib", "fresh container"],
        "parameters": {},
    },
    "jib_logs": {
        "description": "Get recent logs from the jib container",
        "triggers": ["container logs", "jib logs", "show logs"],
        "parameters": {"lines": "Number of log lines to fetch (default: 50)"},
    },
    # Service management
    "service_list": {
        "description": "List all jib-related systemd services and timers",
        "triggers": ["list services", "show services", "what services"],
        "parameters": {},
    },
    "service_status": {
        "description": "Check status of a specific systemd service",
        "triggers": ["service status", "check service", "is service running"],
        "parameters": {"service_name": "Name of the service (e.g., slack-notifier.service)"},
    },
    "service_restart": {
        "description": "Restart a specific systemd service",
        "triggers": ["restart service", "restart notifier", "restart receiver"],
        "parameters": {"service_name": "Name of the service to restart"},
    },
    "service_start": {
        "description": "Start a specific systemd service",
        "triggers": ["start service", "enable service"],
        "parameters": {"service_name": "Name of the service to start"},
    },
    "service_stop": {
        "description": "Stop a specific systemd service",
        "triggers": ["stop service", "disable service"],
        "parameters": {"service_name": "Name of the service to stop"},
    },
    "service_logs": {
        "description": "Get logs for a specific systemd service",
        "triggers": ["service logs", "notifier logs", "receiver logs"],
        "parameters": {
            "service_name": "Name of the service",
            "lines": "Number of log lines (default: 50)",
        },
    },
    # Analysis tools (host-side scripts)
    "run_beads_analyzer": {
        "description": "Run the Beads task tracking analyzer to check task health metrics",
        "triggers": ["analyze beads", "beads health", "task metrics", "beads report"],
        "parameters": {
            "days": "Number of days to analyze (default: 7)",
            "force": "Force run even if recently run (default: false)",
        },
    },
    "run_github_watcher": {
        "description": "Run the GitHub watcher to check for PR comments, check failures, review requests",
        "triggers": ["check github", "github watch", "check PRs", "PR status"],
        "parameters": {},
    },
    "run_feature_analyzer": {
        "description": "Sync documentation with implemented ADRs",
        "triggers": ["sync docs", "feature analyzer", "update features"],
        "parameters": {"adr_path": "Path to specific ADR file (optional)"},
    },
    "run_index_generator": {
        "description": "Generate machine-readable codebase indexes",
        "triggers": ["generate index", "update index", "reindex codebase"],
        "parameters": {},
    },
    "run_doc_generator": {
        "description": "Generate documentation from code patterns",
        "triggers": ["generate docs", "update docs", "create documentation"],
        "parameters": {},
    },
    "run_inefficiency_report": {
        "description": "Generate weekly inefficiency report from conversation analysis",
        "triggers": ["inefficiency report", "weekly report", "analyze conversations"],
        "parameters": {},
    },
    "run_spec_enricher": {
        "description": "Enrich task specs with relevant documentation links",
        "triggers": ["enrich spec", "add doc links"],
        "parameters": {"spec_path": "Path to spec file"},
    },
    # Help
    "show_help": {
        "description": "Show available commands and functions",
        "triggers": ["help", "what can you do", "commands", "available functions"],
        "parameters": {},
    },
}


def _build_function_descriptions() -> str:
    """Build a formatted list of available functions for the prompt."""
    lines = []
    for func_name, info in HOST_FUNCTIONS.items():
        params_str = ""
        if info["parameters"]:
            params = [f"  - {k}: {v}" for k, v in info["parameters"].items()]
            params_str = "\n" + "\n".join(params)
        lines.append(f"- **{func_name}**: {info['description']}{params_str}")
    return "\n".join(lines)


# Cache the function descriptions since HOST_FUNCTIONS is static
_CACHED_FUNCTION_DESCRIPTIONS: str | None = None


def _get_function_descriptions() -> str:
    """Get cached function descriptions for the categorization prompt."""
    global _CACHED_FUNCTION_DESCRIPTIONS
    if _CACHED_FUNCTION_DESCRIPTIONS is None:
        _CACHED_FUNCTION_DESCRIPTIONS = _build_function_descriptions()
    return _CACHED_FUNCTION_DESCRIPTIONS


CATEGORIZATION_PROMPT = """You are a message categorizer for a developer assistant system. Your job is to analyze incoming Slack messages and determine the best way to handle them.

## Available Host Functions

The following functions can be executed immediately on the host machine:

{functions}

## Categories

1. **host_function**: The message is requesting one of the available host functions. Identify which function and extract any parameters.

2. **container_task**: The message is a general task that requires Claude's full capabilities (code analysis, writing code, creating PRs, etc.). These are routed to a container running Claude.

3. **response**: The message is a reply in a thread, responding to a previous notification. These continue existing work.

4. **command**: The message is an explicit slash command like /jib, /service, or help.

## Instructions

Analyze the following message and return a JSON response:

```json
{{
  "category": "host_function" | "container_task" | "response" | "command",
  "function_name": "name_of_function",  // Only for host_function category
  "parameters": {{}},  // Parameters extracted from the message
  "confidence": 0.0-1.0,  // How confident you are in this categorization
  "reasoning": "Brief explanation of why you chose this category"
}}
```

## Rules

1. If the user explicitly asks for a specific function or action that matches a host function, use "host_function"
2. If the message is about analyzing code, writing code, fixing bugs, creating PRs, or general development tasks, use "container_task"
3. If the message starts with "/" it's likely a command
4. When extracting parameters, use reasonable defaults from the function descriptions
5. Be conservative - if unsure, prefer "container_task" as it's more flexible
6. Service names should include the .service suffix (e.g., "slack-notifier.service")

## Message to Categorize

{message}

## Your Response (JSON only)
"""


class MessageCategorizer:
    """Categorizes incoming Slack messages using Claude via jib_exec.

    This class delegates LLM calls to the container via jib_exec, maintaining
    the host-container security boundary. It does NOT import anthropic or
    call Claude directly from the host.
    """

    def __init__(self):
        """Initialize the categorizer.

        Unlike the previous implementation, this does not require an API key
        since LLM calls are delegated to the container via jib_exec.
        """
        self._jib_available = None
        logger.info("Categorizer initialized (using jib_exec for LLM)")

    def _check_jib_available(self) -> bool:
        """Check if jib is available for LLM categorization."""
        if self._jib_available is None:
            self._jib_available = is_jib_available()
            if not self._jib_available:
                logger.warning("jib not available - categorization will use heuristics only")
        return self._jib_available

    def _categorize_with_heuristics(
        self, text: str, is_thread_reply: bool = False
    ) -> CategorizationResult:
        """Fallback categorization using simple heuristics when jib is unavailable.

        Args:
            text: Message text to categorize
            is_thread_reply: Whether this message is a reply in a thread
        """
        text_lower = text.lower().strip()

        # Check for explicit commands
        if text_lower.startswith("/") or text_lower in ["help", "commands"]:
            return CategorizationResult(
                category=MessageCategory.COMMAND,
                confidence=0.95,
                reasoning="Message starts with / or is a help command",
                original_text=text,
            )

        # Thread replies are responses
        if is_thread_reply:
            return CategorizationResult(
                category=MessageCategory.RESPONSE,
                confidence=0.9,
                reasoning="Message is a reply in a thread",
                original_text=text,
            )

        # Check for host function triggers
        for func_name, info in HOST_FUNCTIONS.items():
            for trigger in info.get("triggers", []):
                if trigger.lower() in text_lower:
                    return CategorizationResult(
                        category=MessageCategory.HOST_FUNCTION,
                        function_name=func_name,
                        confidence=0.7,
                        reasoning=f"Message matches trigger '{trigger}' for {func_name}",
                        original_text=text,
                    )

        # Default to container task
        return CategorizationResult(
            category=MessageCategory.CONTAINER_TASK,
            confidence=0.6,
            reasoning="No specific triggers matched - routing to container for full processing",
            original_text=text,
        )

    def _categorize_with_llm(self, text: str) -> CategorizationResult | None:
        """Use LLM via jib_exec to categorize the message.

        Args:
            text: Message text to categorize

        Returns:
            CategorizationResult if successful, None if failed
        """
        # Build the prompt
        prompt = CATEGORIZATION_PROMPT.format(
            functions=_get_function_descriptions(),
            message=text,
        )

        logger.info("Calling jib_exec for categorization", text_preview=text[:50])

        # Call Claude via jib_exec using the analysis-processor's llm_prompt task
        result = jib_exec(
            processor="analysis-processor",
            task_type="llm_prompt",
            context={
                "prompt": prompt,
                "timeout": 30,  # Short timeout for categorization
            },
            timeout=60,  # Overall timeout including container startup
        )

        if not result.success:
            logger.error("jib_exec failed for categorization", error=result.error)
            return None

        # Extract the response from the result
        if not result.json_output:
            logger.error("No JSON output from jib_exec")
            return None

        # The analysis-processor returns {"success": true, "result": {"stdout": "...", ...}}
        inner_result = result.json_output.get("result", {})
        response_text = inner_result.get("stdout", "").strip()

        if not response_text:
            logger.error("Empty stdout from analysis-processor")
            return None

        try:
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            parsed = json.loads(response_text)

            # Convert to CategorizationResult
            category = MessageCategory(parsed.get("category", "unknown"))

            return CategorizationResult(
                category=category,
                function_name=parsed.get("function_name"),
                parameters=parsed.get("parameters", {}),
                confidence=parsed.get("confidence", 0.5),
                reasoning=parsed.get("reasoning", ""),
                original_text=text,
            )

        except json.JSONDecodeError as e:
            logger.error("Failed to parse categorization response", error=str(e))
            return None
        except ValueError as e:
            logger.error("Invalid category in response", error=str(e))
            return None

    def categorize(self, text: str, is_thread_reply: bool = False) -> CategorizationResult:
        """Categorize an incoming message.

        Args:
            text: Message text to categorize
            is_thread_reply: Whether this message is a reply in a thread

        Returns:
            CategorizationResult with category, function, parameters, etc.
        """
        # Quick checks that don't need LLM
        text_stripped = text.strip()

        # Explicit commands bypass categorization
        if text_stripped.startswith("/") or text_stripped.lower() in ["help", "commands"]:
            return CategorizationResult(
                category=MessageCategory.COMMAND,
                confidence=1.0,
                reasoning="Explicit command detected",
                original_text=text,
            )

        # Thread replies are always responses
        if is_thread_reply:
            return CategorizationResult(
                category=MessageCategory.RESPONSE,
                confidence=1.0,
                reasoning="Thread reply detected",
                original_text=text,
            )

        # Try LLM-based categorization via jib_exec
        if self._check_jib_available():
            llm_result = self._categorize_with_llm(text)
            if llm_result is not None:
                return llm_result
            # Fall through to heuristics if LLM failed

        logger.info("Using heuristic categorization")
        return self._categorize_with_heuristics(text, is_thread_reply)

    def get_available_functions(self) -> dict[str, dict]:
        """Get the registry of available host functions.

        Returns:
            Dictionary mapping function names to their descriptions and parameters.
        """
        return HOST_FUNCTIONS.copy()


def main():
    """CLI for testing the categorizer."""
    import argparse

    parser = argparse.ArgumentParser(description="Test message categorization")
    parser.add_argument("message", help="Message to categorize")
    parser.add_argument("--thread-reply", action="store_true", help="Treat as thread reply")

    args = parser.parse_args()

    categorizer = MessageCategorizer()
    result = categorizer.categorize(args.message, is_thread_reply=args.thread_reply)

    print(f"Category: {result.category.value}")
    print(f"Function: {result.function_name}")
    print(f"Parameters: {result.parameters}")
    print(f"Confidence: {result.confidence}")
    print(f"Reasoning: {result.reasoning}")


if __name__ == "__main__":
    main()
