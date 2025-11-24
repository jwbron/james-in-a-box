"""
Configuration for JIRA connector.
"""

import os
from typing import Optional


class JIRAConfig:
    """Configuration for JIRA instance."""
    
    # JIRA instance URL (e.g., "https://khanacademy.atlassian.net")
    BASE_URL: str = os.getenv("JIRA_BASE_URL", "")
    
    # Authentication (same as Confluence for Atlassian Cloud)
    USERNAME: str = os.getenv("JIRA_USERNAME", "")
    API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
    
    # Output directory
    OUTPUT_DIR: str = os.getenv(
        "JIRA_OUTPUT_DIR",
        os.path.expanduser("~/context-sync/jira")
    )
    
    # Sync options
    # JQL query to filter tickets
    # Default: All open INFRA project tickets (including epics)
    JQL_QUERY: str = os.getenv(
        "JIRA_JQL_QUERY",
        "project = INFRA AND resolution = Unresolved ORDER BY updated DESC"
    )
    
    # Maximum tickets to sync (0 = unlimited)
    MAX_TICKETS: int = int(os.getenv("JIRA_MAX_TICKETS", "0"))
    if MAX_TICKETS == 0:
        MAX_TICKETS = float('inf')
    
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
        elif not cls.BASE_URL.startswith(('http://', 'https://')):
            errors.append("JIRA_BASE_URL must be a valid URL")
        
        if not cls.USERNAME:
            errors.append("JIRA_USERNAME is required")
        elif '@' not in cls.USERNAME:
            errors.append("JIRA_USERNAME should be an email address")
        
        if not cls.API_TOKEN:
            errors.append("JIRA_API_TOKEN is required")
        
        return errors

