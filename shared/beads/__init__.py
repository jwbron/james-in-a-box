"""
Shared Beads utilities for jib.

Provides utilities for managing persistent task context in Beads,
particularly for GitHub PR tracking across container sessions.

Usage:
    from shared.beads import PRContextManager

    # Create manager instance
    pr_context = PRContextManager()

    # Get or create context for a PR
    beads_id = pr_context.get_or_create_context("owner/repo", 123, "PR Title")

    # Get existing context
    context = pr_context.get_context("owner/repo", 123)
    if context:
        print(f"Task ID: {context['task_id']}")
        print(f"Notes: {context['content']}")

    # Update context with new notes
    pr_context.update_context(beads_id, "Fixed check failures", status="in_progress")
"""

from .pr_context import PRContextManager


__all__ = [
    "PRContextManager",
]
