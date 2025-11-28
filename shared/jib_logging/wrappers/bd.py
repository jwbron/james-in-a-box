"""
Beads (bd) wrapper for jib_logging.

Wraps the beads task tracking CLI to capture task lifecycle events.
"""

import re
from typing import Any

from .base import ToolResult, ToolWrapper


class BdWrapper(ToolWrapper):
    """Wrapper for the beads (bd) task tracking CLI.

    Captures task lifecycle events including:
    - Task creation
    - Status updates
    - Task queries

    Usage:
        from jib_logging.wrappers import bd

        # Create a task
        result = bd.create("Fix bug in login", labels=["bug", "auth"])

        # Update task status
        result = bd.update("bd-abc123", status="in_progress")

        # List tasks
        result = bd.list(status="in_progress")

        # Search tasks
        result = bd.search("login bug")
    """

    tool_name = "bd"

    def create(
        self,
        title: str,
        *,
        description: str | None = None,
        labels: list[str] | None = None,
        parent: str | None = None,
        deps: list[str] | None = None,
        priority: str | None = None,
        allow_stale: bool = True,
    ) -> ToolResult:
        """Create a new beads task.

        Args:
            title: Task title
            description: Task description
            labels: List of labels to apply
            parent: Parent task ID
            deps: List of dependency specifications
            priority: Task priority (P0-P4)
            allow_stale: Skip staleness check (default True)

        Returns:
            ToolResult with task ID in extra["task_id"]
        """
        args: list[str] = []

        if allow_stale:
            args.append("--allow-stale")

        args.extend(["create", title])

        if description:
            args.extend(["--description", description])

        if labels:
            args.extend(["--labels", ",".join(labels)])

        if parent:
            args.extend(["--parent", parent])

        if deps:
            for dep in deps:
                args.extend(["--deps", dep])

        if priority:
            args.extend(["--priority", priority])

        return self.run(*args)

    def update(
        self,
        task_id: str,
        *,
        status: str | None = None,
        notes: str | None = None,
        labels: list[str] | None = None,
        priority: str | None = None,
        allow_stale: bool = True,
    ) -> ToolResult:
        """Update an existing beads task.

        Args:
            task_id: Task ID (e.g., "bd-abc123")
            status: New status (open, in_progress, blocked, closed)
            notes: Notes to add
            labels: Labels to set (replaces existing)
            priority: New priority (P0-P4)
            allow_stale: Skip staleness check (default True)

        Returns:
            ToolResult
        """
        args: list[str] = []

        if allow_stale:
            args.append("--allow-stale")

        args.extend(["update", task_id])

        if status:
            args.extend(["--status", status])

        if notes:
            args.extend(["--notes", notes])

        if labels:
            args.extend(["--labels", ",".join(labels)])

        if priority:
            args.extend(["--priority", priority])

        return self.run(*args)

    def show(self, task_id: str, *, allow_stale: bool = True) -> ToolResult:
        """Show details of a specific task.

        Args:
            task_id: Task ID to show
            allow_stale: Skip staleness check (default True)

        Returns:
            ToolResult with task details in stdout
        """
        args: list[str] = []

        if allow_stale:
            args.append("--allow-stale")

        args.extend(["show", task_id])

        return self.run(*args)

    def list(
        self,
        *,
        status: str | None = None,
        label: str | None = None,
        allow_stale: bool = True,
    ) -> ToolResult:
        """List beads tasks.

        Args:
            status: Filter by status
            label: Filter by label
            allow_stale: Skip staleness check (default True)

        Returns:
            ToolResult with task list in stdout
        """
        args: list[str] = []

        if allow_stale:
            args.append("--allow-stale")

        args.append("list")

        if status:
            args.extend(["--status", status])

        if label:
            args.extend(["--label", label])

        return self.run(*args)

    def search(self, query: str, *, allow_stale: bool = True) -> ToolResult:
        """Search beads tasks by text.

        Note: Search only checks title, description, and ID - not labels.
        Use list(label="...") to filter by label.

        Args:
            query: Search query text
            allow_stale: Skip staleness check (default True)

        Returns:
            ToolResult with matching tasks in stdout
        """
        args: list[str] = []

        if allow_stale:
            args.append("--allow-stale")

        args.extend(["search", query])

        return self.run(*args)

    def ready(self, *, allow_stale: bool = True) -> ToolResult:
        """List tasks that are ready to be worked on.

        Args:
            allow_stale: Skip staleness check (default True)

        Returns:
            ToolResult with ready tasks in stdout
        """
        args: list[str] = []

        if allow_stale:
            args.append("--allow-stale")

        args.append("ready")

        return self.run(*args)

    def _extract_context(
        self,
        args: tuple[str, ...],
        stdout: str,
        stderr: str,
    ) -> dict[str, Any]:
        """Extract beads-specific context from command and output."""
        context: dict[str, Any] = {}

        # Find the subcommand (skip --allow-stale if present)
        filtered_args = [a for a in args if not a.startswith("-")]
        if filtered_args:
            context["subcommand"] = filtered_args[0]

        # Extract task_id from arguments or output
        task_id = self._find_task_id(args, stdout)
        if task_id:
            context["task_id"] = task_id

        # Extract status if updating
        if "--status" in args:
            try:
                status_idx = args.index("--status")
                if status_idx + 1 < len(args):
                    context["new_status"] = args[status_idx + 1]
            except (ValueError, IndexError):
                pass

        return context

    def _find_task_id(self, args: tuple[str, ...], stdout: str) -> str | None:
        """Find task ID from arguments or command output."""
        # Check args for existing task ID pattern
        for arg in args:
            if re.match(r"^beads-[a-z0-9]+$", arg):
                return arg

        # Check output for created task ID (e.g., "Created issue: beads-abc123")
        match = re.search(r"(beads-[a-z0-9]+)", stdout)
        if match:
            return match.group(1)

        return None
