"""
JIRA configuration for context sync.

Wraps the existing JIRA connector configuration with the
BaseConfig interface for unified validation and health checks.
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..base import BaseConfig, HealthCheckResult, ValidationResult
from ..validators import mask_secret, validate_email, validate_non_empty, validate_url


@dataclass
class JiraConfig(BaseConfig):
    """Configuration for JIRA integration.

    Attributes:
        base_url: JIRA instance URL (https://...)
        username: Atlassian account email
        api_token: Atlassian API token
        jql_query: JQL query to filter issues
        output_dir: Directory for synced content
        max_tickets: Maximum tickets to sync (0 = unlimited)
        include_comments: Whether to sync comments
        include_attachments: Whether to sync attachments
        include_worklogs: Whether to sync work logs
        incremental_sync: Only sync changes since last run
        request_timeout: HTTP request timeout
        max_retries: Max retry attempts
    """

    base_url: str = ""
    username: str = ""
    api_token: str = ""
    jql_query: str = "project = INFRA AND resolution = Unresolved ORDER BY updated DESC"
    output_dir: Path = Path.home() / "context-sync" / "jira"
    max_tickets: int = 0
    include_comments: bool = True
    include_attachments: bool = True
    include_worklogs: bool = False
    incremental_sync: bool = True
    request_timeout: int = 30
    max_retries: int = 3

    def validate(self) -> ValidationResult:
        """Validate JIRA configuration."""
        errors: list[str] = []
        warnings: list[str] = []

        # Base URL is required and must be HTTPS
        is_valid, error = validate_non_empty(self.base_url, "base_url")
        if not is_valid:
            errors.append(error)
        else:
            is_valid, error = validate_url(self.base_url, require_https=True)
            if not is_valid:
                errors.append(f"base_url: {error}")

        # Username must be an email
        is_valid, error = validate_non_empty(self.username, "username")
        if not is_valid:
            errors.append(error)
        else:
            is_valid, error = validate_email(self.username)
            if not is_valid:
                errors.append(f"username: {error}")

        # API token is required
        is_valid, error = validate_non_empty(self.api_token, "api_token")
        if not is_valid:
            errors.append(error)

        # JQL query validation (basic)
        if not self.jql_query:
            warnings.append("jql_query is empty - will sync all accessible issues")

        if errors:
            return ValidationResult.invalid(errors, warnings)

        return ValidationResult.valid(warnings)

    def health_check(self, timeout: float = 5.0) -> HealthCheckResult:
        """Check JIRA API connectivity.

        Calls the myself endpoint to verify authentication.
        """
        if not self.base_url or not self.api_token:
            return HealthCheckResult(
                healthy=False,
                service_name="jira",
                message="JIRA not configured",
            )

        try:
            import base64
            import json
            import urllib.request

            start = time.time()

            # Create basic auth header
            credentials = f"{self.username}:{self.api_token}"
            auth = base64.b64encode(credentials.encode()).decode()

            # Test with the myself endpoint
            req = urllib.request.Request(
                f"{self.base_url.rstrip('/')}/rest/api/3/myself",
                headers={
                    "Authorization": f"Basic {auth}",
                    "Accept": "application/json",
                },
            )

            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode())
                latency = (time.time() - start) * 1000

                display_name = data.get("displayName", "unknown")
                return HealthCheckResult(
                    healthy=True,
                    service_name="jira",
                    message=f"Authenticated as {display_name}",
                    latency_ms=latency,
                )

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return HealthCheckResult(
                    healthy=False,
                    service_name="jira",
                    message="Invalid credentials",
                )
            return HealthCheckResult(
                healthy=False,
                service_name="jira",
                message=f"API error: HTTP {e.code}",
            )
        except Exception as e:
            return HealthCheckResult(
                healthy=False,
                service_name="jira",
                message=f"Connection failed: {e}",
            )

    def to_dict(self) -> dict[str, Any]:
        """Return config with secrets masked."""
        return {
            "base_url": self.base_url,
            "username": self.username,
            "api_token": mask_secret(self.api_token),
            "jql_query": self.jql_query,
            "output_dir": str(self.output_dir),
            "max_tickets": self.max_tickets,
            "include_comments": self.include_comments,
            "include_attachments": self.include_attachments,
            "include_worklogs": self.include_worklogs,
            "incremental_sync": self.incremental_sync,
            "request_timeout": self.request_timeout,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_env(cls) -> "JiraConfig":
        """Load JIRA configuration from environment variables.

        All settings use the JIRA_ prefix.
        """
        config = cls()

        config.base_url = os.environ.get("JIRA_BASE_URL", "")
        config.username = os.environ.get("JIRA_USERNAME", "")
        config.api_token = os.environ.get("JIRA_API_TOKEN", "")
        config.jql_query = os.environ.get(
            "JIRA_JQL_QUERY",
            "project = INFRA AND resolution = Unresolved ORDER BY updated DESC",
        )

        output_dir = os.environ.get("JIRA_OUTPUT_DIR", "")
        if output_dir:
            config.output_dir = Path(output_dir).expanduser()

        config.max_tickets = int(os.environ.get("JIRA_MAX_TICKETS", "0"))
        config.include_comments = os.environ.get("JIRA_INCLUDE_COMMENTS", "true").lower() == "true"
        config.include_attachments = (
            os.environ.get("JIRA_INCLUDE_ATTACHMENTS", "true").lower() == "true"
        )
        config.include_worklogs = os.environ.get("JIRA_INCLUDE_WORKLOGS", "false").lower() == "true"
        config.incremental_sync = os.environ.get("JIRA_INCREMENTAL_SYNC", "true").lower() == "true"
        config.request_timeout = int(os.environ.get("JIRA_REQUEST_TIMEOUT", "30"))
        config.max_retries = int(os.environ.get("JIRA_MAX_RETRIES", "3"))

        return config
