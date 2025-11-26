"""
Configuration for Confluence documentation sync.
"""

import os


class ConfluenceConfig:
    """Configuration for Confluence instance."""

    # Confluence instance URL (e.g., "https://yourcompany.atlassian.net")
    BASE_URL: str = os.getenv("CONFLUENCE_BASE_URL", "")

    # Authentication
    USERNAME: str = os.getenv("CONFLUENCE_USERNAME", "")
    API_TOKEN: str = os.getenv("CONFLUENCE_API_TOKEN", "")

    # Space keys to sync (comma-separated)
    SPACE_KEYS: str = os.getenv("CONFLUENCE_SPACE_KEYS", "")

    # Output directories
    # Default to ~/context-sync/confluence for new multi-connector architecture
    # Falls back to ./confluence-docs for backwards compatibility
    OUTPUT_DIR: str = os.getenv(
        "CONFLUENCE_OUTPUT_DIR", os.path.expanduser("~/context-sync/confluence")
    )
    PROCESSED_DIR: str = os.getenv("CONFLUENCE_PROCESSED_DIR", "processed")

    # Sync options
    # MAX_PAGES: None means unlimited, otherwise an int limit
    _max_pages_env: str = os.getenv("CONFLUENCE_MAX_PAGES", "0")
    MAX_PAGES: int | None = None if _max_pages_env == "0" else int(_max_pages_env)
    INCLUDE_ATTACHMENTS: bool = (
        os.getenv("CONFLUENCE_INCLUDE_ATTACHMENTS", "false").lower() == "true"
    )

    # Sync behavior
    INCREMENTAL_SYNC: bool = os.getenv("CONFLUENCE_INCREMENTAL_SYNC", "true").lower() == "true"
    SYNC_INTERVAL: int = int(os.getenv("CONFLUENCE_SYNC_INTERVAL", "3600"))  # seconds

    # API options
    REQUEST_TIMEOUT: int = int(os.getenv("CONFLUENCE_REQUEST_TIMEOUT", "30"))
    MAX_RETRIES: int = int(os.getenv("CONFLUENCE_MAX_RETRIES", "3"))

    # Search options
    SEARCH_CONTEXT_LINES: int = int(os.getenv("CONFLUENCE_SEARCH_CONTEXT_LINES", "3"))
    MAX_SEARCH_RESULTS: int = int(os.getenv("CONFLUENCE_MAX_SEARCH_RESULTS", "50"))

    # Output format options
    OUTPUT_FORMAT: str = os.getenv("CONFLUENCE_OUTPUT_FORMAT", "html").lower()

    @classmethod
    def validate(cls) -> bool:
        """Validate that required configuration is present."""
        required_fields = [cls.BASE_URL, cls.USERNAME, cls.API_TOKEN, cls.SPACE_KEYS]
        return all(field for field in required_fields)

    @classmethod
    def get_space_keys_list(cls) -> list[str]:
        """Get space keys as a list."""
        return [key.strip() for key in cls.SPACE_KEYS.split(",") if key.strip()]

    @classmethod
    def get_validation_errors(cls) -> list[str]:
        """Get list of validation errors."""
        errors = []

        if not cls.BASE_URL:
            errors.append("CONFLUENCE_BASE_URL is required")
        elif not cls.BASE_URL.startswith(("http://", "https://")):
            errors.append("CONFLUENCE_BASE_URL must be a valid URL")

        if not cls.USERNAME:
            errors.append("CONFLUENCE_USERNAME is required")
        elif "@" not in cls.USERNAME:
            errors.append("CONFLUENCE_USERNAME should be an email address")

        if not cls.API_TOKEN:
            errors.append("CONFLUENCE_API_TOKEN is required")

        if not cls.SPACE_KEYS:
            errors.append("CONFLUENCE_SPACE_KEYS is required")

        if cls.OUTPUT_FORMAT not in ["html", "markdown"]:
            errors.append("CONFLUENCE_OUTPUT_FORMAT must be either 'html' or 'markdown'")

        return errors
