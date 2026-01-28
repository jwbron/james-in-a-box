"""
User-friendly error messages for Private Repo Mode.

Provides clear, actionable error messages that explain:
1. What operation was blocked
2. Why it was blocked
3. What the user can do instead

These messages are designed to be helpful for AI agents that may need
to adjust their behavior based on policy restrictions.
"""


# Error message templates for Private Repo Mode
PRIVATE_REPO_ERROR_MESSAGES = {
    # General visibility errors
    "visibility_unknown": (
        "Cannot determine visibility for repository '{repo}'. "
        "Private Repo Mode requires explicit verification. "
        "{hint}"
    ),
    # Push operations
    "push_public": (
        "Cannot push to public repository '{repo}'. "
        "Private Repo Mode restricts operations to private repositories only. "
        "Consider creating a private fork or using a different repository."
    ),
    # Fetch operations
    "fetch_public": (
        "Cannot fetch from public repository '{repo}'. "
        "Private Repo Mode restricts operations to private repositories only."
    ),
    # Clone operations
    "clone_public": (
        "Cannot clone public repository '{repo}'. "
        "Private Repo Mode restricts operations to private repositories only."
    ),
    # PR operations
    "pr_create_public": (
        "Cannot create PR in public repository '{repo}'. "
        "Private Repo Mode restricts operations to private repositories only."
    ),
    "pr_comment_public": (
        "Cannot comment on PR in public repository '{repo}'. "
        "Private Repo Mode restricts operations to private repositories only."
    ),
    # Issue operations
    "issue_public": (
        "Cannot interact with issues in public repository '{repo}'. "
        "Private Repo Mode restricts operations to private repositories only."
    ),
    # Fork operations
    "fork_from_public": (
        "Cannot fork from public repository '{repo}'. "
        "Private Repo Mode only allows forking from private repositories."
    ),
    "fork_to_public": (
        "Cannot create a public fork. "
        "Private Repo Mode requires all forks to be private. "
        "Set 'make_private=true' or use '--private' flag."
    ),
    # Generic gh execute
    "gh_execute_public": (
        "Cannot execute gh command for public repository '{repo}'. "
        "Private Repo Mode restricts operations to private repositories only."
    ),
    # Default/fallback
    "default": (
        "Operation blocked by Private Repo Mode policy. "
        "This feature restricts all Git/GitHub operations to private repositories only."
    ),
}


def get_error_message(
    error_type: str,
    repo: str | None = None,
    operation: str | None = None,
    hint: str | None = None,
    **kwargs,
) -> str:
    """
    Get a user-friendly error message for a policy violation.

    Args:
        error_type: Type of error (e.g., 'push_public', 'visibility_unknown')
        repo: Repository name for substitution
        operation: Operation name for substitution
        hint: Additional hint text
        **kwargs: Additional substitution variables

    Returns:
        Formatted error message
    """
    # Build substitution dict
    subs = {
        "repo": repo or "unknown",
        "operation": operation or "operation",
        "hint": hint or "",
        **kwargs,
    }

    # Get template
    template = PRIVATE_REPO_ERROR_MESSAGES.get(
        error_type, PRIVATE_REPO_ERROR_MESSAGES["default"]
    )

    # Format with substitutions
    try:
        return template.format(**subs)
    except KeyError:
        # If template has placeholders we don't have, use default
        return PRIVATE_REPO_ERROR_MESSAGES["default"]


def format_policy_blocked_response(
    operation: str,
    reason: str,
    repository: str | None = None,
    visibility: str | None = None,
    hints: list[str] | None = None,
) -> dict:
    """
    Format a standardized policy-blocked response.

    Args:
        operation: The operation that was blocked
        reason: Human-readable reason for blocking
        repository: Repository involved (if any)
        visibility: Repository visibility (if known)
        hints: List of helpful hints for the user

    Returns:
        Dictionary with standardized response structure
    """
    response = {
        "success": False,
        "error": "PolicyViolation",
        "operation": operation,
        "reason": reason,
        "policy": "private_repo_mode",
    }

    if repository:
        response["repository"] = repository

    if visibility:
        response["visibility"] = visibility

    if hints:
        response["hints"] = hints

    return response


# Hints for common scenarios
PRIVATE_REPO_MODE_HINTS = {
    "public_repo": [
        "Private Repo Mode is enabled for security.",
        "Consider using a private repository instead.",
        "Contact the repository owner to make it private.",
    ],
    "visibility_unknown": [
        "The GitHub API could not determine the repository's visibility.",
        "This may be due to rate limiting, network issues, or token permissions.",
        "Try again later or verify your GitHub token has repo access.",
    ],
    "fork_blocked": [
        "Private Repo Mode restricts forking operations.",
        "Forking from public repositories is not allowed.",
        "Forks must be created as private repositories.",
    ],
}


def get_hints_for_error(error_type: str) -> list[str]:
    """
    Get helpful hints for an error type.

    Args:
        error_type: Type of error

    Returns:
        List of hint strings
    """
    if "fork" in error_type.lower():
        return PRIVATE_REPO_MODE_HINTS["fork_blocked"]
    if "unknown" in error_type.lower():
        return PRIVATE_REPO_MODE_HINTS["visibility_unknown"]
    if "public" in error_type.lower():
        return PRIVATE_REPO_MODE_HINTS["public_repo"]
    return []
