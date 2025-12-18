"""
Configuration for JIRA connector.
"""

import os


class JIRAConfig:
    """Configuration for JIRA instance."""

    # JIRA instance URL (e.g., "https://khanacademy.atlassian.net")
    BASE_URL: str = os.getenv("JIRA_BASE_URL", "")

    # Authentication (same as Confluence for Atlassian Cloud)
    USERNAME: str = os.getenv("JIRA_USERNAME", "")
    API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")

    # Output directory
    OUTPUT_DIR: str = os.getenv("JIRA_OUTPUT_DIR", os.path.expanduser("~/context-sync/jira"))

    # Sync options
    # JQL query to filter tickets
    # Default: All open INFRA project tickets (including epics)
    JQL_QUERY: str = os.getenv(
        "JIRA_JQL_QUERY", "project = INFRA AND resolution = Unresolved ORDER BY updated DESC"
    )

    # Maximum tickets to sync (None = unlimited)
    _max_tickets_env: int = int(os.getenv("JIRA_MAX_TICKETS", "0"))
    MAX_TICKETS: int | None = None if _max_tickets_env == 0 else _max_tickets_env

    # Include ticket comments
    INCLUDE_COMMENTS: bool = os.getenv("JIRA_INCLUDE_COMMENTS", "true").lower() == "true"

    # Include attachments metadata (not the files themselves)
    INCLUDE_ATTACHMENTS: bool = os.getenv("JIRA_INCLUDE_ATTACHMENTS", "true").lower() == "true"

    # Include work logs
    INCLUDE_WORKLOGS: bool = os.getenv("JIRA_INCLUDE_WORKLOGS", "false").lower() == "true"

    # API options
    REQUEST_TIMEOUT: int = int(os.getenv("JIRA_REQUEST_TIMEOUT", "30"))
    MAX_RETRIES: int = int(os.getenv("JIRA_MAX_RETRIES", "3"))

    # Incremental sync
    INCREMENTAL_SYNC: bool = os.getenv("JIRA_INCREMENTAL_SYNC", "true").lower() == "true"

    # -------------------------------------------------------------------------
    # JIB Triage Configuration (ADR: JIRA Ticket Triage Workflow)
    # -------------------------------------------------------------------------

    # Enable/disable JIB triage workflow
    JIB_TRIAGE_ENABLED: bool = os.getenv("JIB_TRIAGE_ENABLED", "true").lower() == "true"

    # Repositories enabled for JIB triage (comma-separated)
    JIB_TRIAGE_ENABLED_REPOS: str = os.getenv("JIB_TRIAGE_ENABLED_REPOS", "jwbron/james-in-a-box")

    # Labels that identify JIB-tagged tickets (comma-separated, case-insensitive)
    JIB_TAG_LABELS: str = os.getenv("JIB_TAG_LABELS", "jib,james-in-a-box")

    # Score threshold for trivial classification (0-100)
    JIB_TRIVIALITY_THRESHOLD: int = int(os.getenv("JIB_TRIVIALITY_THRESHOLD", "50"))

    # Auto-classify security tickets as non-trivial
    JIB_AUTO_SECURITY_NONTRIVIAL: bool = os.getenv("JIB_AUTO_SECURITY_NONTRIVIAL", "true").lower() == "true"

    # Directory for planning documents (relative to repo)
    JIB_PLAN_OUTPUT_DIR: str = os.getenv("JIB_PLAN_OUTPUT_DIR", "docs/plans")

    # Maximum tokens for context gathering
    JIB_MAX_CONTEXT_TOKENS: int = int(os.getenv("JIB_MAX_CONTEXT_TOKENS", "50000"))

    # Timeout for context gathering (seconds)
    JIB_CONTEXT_TIMEOUT_SECONDS: int = int(os.getenv("JIB_CONTEXT_TIMEOUT_SECONDS", "60"))

    @classmethod
    def get_jib_tag_labels(cls) -> list[str]:
        """Get list of JIB tag labels."""
        return [l.strip().lower() for l in cls.JIB_TAG_LABELS.split(",")]

    @classmethod
    def get_jib_enabled_repos(cls) -> list[str]:
        """Get list of enabled repositories for JIB triage."""
        return [r.strip() for r in cls.JIB_TRIAGE_ENABLED_REPOS.split(",")]

    @classmethod
    def validate(cls) -> bool:
        """Validate that required configuration is present."""
        required_fields = [cls.BASE_URL, cls.USERNAME, cls.API_TOKEN]
        return all(field for field in required_fields)

    @classmethod
    def get_validation_errors(cls) -> list[str]:
        """Get list of validation errors."""
        errors = []

        if not cls.BASE_URL:
            errors.append("JIRA_BASE_URL is required")
        elif not cls.BASE_URL.startswith(("http://", "https://")):
            errors.append("JIRA_BASE_URL must be a valid URL")

        if not cls.USERNAME:
            errors.append("JIRA_USERNAME is required")
        elif "@" not in cls.USERNAME:
            errors.append("JIRA_USERNAME should be an email address")

        if not cls.API_TOKEN:
            errors.append("JIRA_API_TOKEN is required")

        return errors
