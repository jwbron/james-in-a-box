#!/usr/bin/env python3
"""Log access policy enforcement.

This module implements access control rules for log requests, following
the same policy-first pattern used for git operations in policy.py.

Access rules:
- Task access: Allowed if requester's container owns the task
- Container access: Allowed only for self-access (requester == target)
- Search: Always scoped to requester's own logs
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add shared directory to path for jib_logging
_shared_path = Path(__file__).parent.parent / "shared"
if _shared_path.exists():
    sys.path.insert(0, str(_shared_path))
from jib_logging import get_logger

# Import from local modules
try:
    from .log_index import get_log_index
except ImportError:
    from log_index import get_log_index

logger = get_logger("gateway-sidecar.log_policy")


@dataclass
class LogPolicyResult:
    """Result of a log access policy check.

    Attributes:
        allowed: Whether the access is permitted
        reason: Human-readable explanation of the decision
        details: Additional context for debugging/audit (optional)
    """

    allowed: bool
    reason: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {"allowed": self.allowed, "reason": self.reason}
        if self.details:
            result["details"] = self.details
        return result


class LogPolicy:
    """Log access policy enforcement.

    Implements the principle of least privilege: agents can only access
    their own logs unless explicitly granted broader access.
    """

    def __init__(self):
        self._log_index = get_log_index()

    def check_task_access(
        self,
        requester_container_id: str,
        requester_task_id: str | None,
        target_task_id: str,
    ) -> LogPolicyResult:
        """Check if requester can access logs for target task.

        Access is allowed if:
        1. The requester's container owns the target task
        2. The requester's task_id matches the target task_id

        Args:
            requester_container_id: Container ID making the request
            requester_task_id: Task ID of the requester (if any)
            target_task_id: Task whose logs are being requested

        Returns:
            LogPolicyResult indicating whether access is allowed
        """
        # Look up task's owner container
        owner_container = self._log_index.get_container_for_task(target_task_id)

        if owner_container is None:
            return LogPolicyResult(
                allowed=False,
                reason="Task not found in log index",
                details={"target_task_id": target_task_id},
            )

        # Check ownership by container
        if owner_container == requester_container_id:
            return LogPolicyResult(
                allowed=True,
                reason="Owner access (container match)",
            )

        # Check ownership by task identity
        if requester_task_id and requester_task_id == target_task_id:
            return LogPolicyResult(
                allowed=True,
                reason="Owner access (task identity match)",
            )

        return LogPolicyResult(
            allowed=False,
            reason="Cross-container log access denied",
            details={
                "requester_container": requester_container_id,
                "owner_container": owner_container,
                "target_task_id": target_task_id,
            },
        )

    def check_container_access(
        self,
        requester_container_id: str,
        target_container_id: str,
    ) -> LogPolicyResult:
        """Check if requester can access logs for target container.

        Access is allowed only if requester == target (self-access).

        Args:
            requester_container_id: Container ID making the request
            target_container_id: Container whose logs are being requested

        Returns:
            LogPolicyResult indicating whether access is allowed
        """
        if requester_container_id == target_container_id:
            return LogPolicyResult(
                allowed=True,
                reason="Self-access (container identity match)",
            )

        return LogPolicyResult(
            allowed=False,
            reason="Cross-container log access denied",
            details={
                "requester_container": requester_container_id,
                "target_container": target_container_id,
            },
        )

    def check_search_access(
        self,
        requester_container_id: str,
        scope: str,
    ) -> LogPolicyResult:
        """Check if requester can perform a log search.

        Searches are always scoped to the requester's own logs.
        The 'scope' parameter is validated but currently only 'self' is allowed.

        Args:
            requester_container_id: Container ID making the request
            scope: The requested search scope (must be 'self')

        Returns:
            LogPolicyResult indicating whether access is allowed
        """
        if scope != "self":
            return LogPolicyResult(
                allowed=False,
                reason="Invalid search scope",
                details={"scope": scope, "allowed_scopes": ["self"]},
            )

        return LogPolicyResult(
            allowed=True,
            reason="Search allowed (self scope)",
        )


# Singleton instance
_log_policy: LogPolicy | None = None


def get_log_policy() -> LogPolicy:
    """Get the singleton LogPolicy instance."""
    global _log_policy
    if _log_policy is None:
        _log_policy = LogPolicy()
    return _log_policy
