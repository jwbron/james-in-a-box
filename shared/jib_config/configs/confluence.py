"""
Confluence configuration for context sync.

Wraps the existing Confluence connector configuration with the
BaseConfig interface for unified validation and health checks.
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..base import BaseConfig, HealthCheckResult, ValidationResult
from ..utils import safe_bool, safe_int
from ..validators import mask_secret, validate_email, validate_non_empty, validate_url


@dataclass
class ConfluenceConfig(BaseConfig):
    """Configuration for Confluence integration.

    Attributes:
        base_url: Confluence instance URL (https://...)
        username: Atlassian account email
        api_token: Atlassian API token
        space_keys: Comma-separated list of space keys to sync
        output_dir: Directory for synced content
        max_pages: Maximum pages to sync (0 = unlimited)
        include_attachments: Whether to sync attachments
        incremental_sync: Only sync changes since last run
        sync_interval: Seconds between sync runs
        request_timeout: HTTP request timeout
        max_retries: Max retry attempts
        output_format: Output format (html or markdown)
    """

    base_url: str = ""
    username: str = ""
    api_token: str = ""
    space_keys: str = ""
    output_dir: Path = Path.home() / "context-sync" / "confluence"
    max_pages: int = 0
    include_attachments: bool = False
    incremental_sync: bool = True
    sync_interval: int = 3600
    request_timeout: int = 30
    max_retries: int = 3
    output_format: str = "html"

    def validate(self) -> ValidationResult:
        """Validate Confluence configuration."""
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

        # Space keys are required
        is_valid, error = validate_non_empty(self.space_keys, "space_keys")
        if not is_valid:
            errors.append(error)

        # Output format must be valid
        if self.output_format not in ("html", "markdown"):
            errors.append(f"output_format must be 'html' or 'markdown', got '{self.output_format}'")

        if errors:
            return ValidationResult.invalid(errors, warnings)

        return ValidationResult.valid(warnings)

    def health_check(self, timeout: float = 5.0) -> HealthCheckResult:
        """Check Confluence API connectivity.

        Calls the content API to verify authentication.
        """
        if not self.base_url or not self.api_token:
            return HealthCheckResult(
                healthy=False,
                service_name="confluence",
                message="Confluence not configured",
            )

        try:
            import base64
            import urllib.request

            start = time.time()

            # Create basic auth header
            credentials = f"{self.username}:{self.api_token}"
            auth = base64.b64encode(credentials.encode()).decode()

            # Build API URL - handle base_url with or without /wiki suffix
            base = self.base_url.rstrip("/")
            if base.endswith("/wiki"):
                api_url = f"{base}/rest/api/space?limit=1"
            else:
                api_url = f"{base}/wiki/rest/api/space?limit=1"

            # Test with a simple API call
            req = urllib.request.Request(
                api_url,
                headers={
                    "Authorization": f"Basic {auth}",
                    "Accept": "application/json",
                },
            )

            with urllib.request.urlopen(req, timeout=timeout):
                latency = (time.time() - start) * 1000
                return HealthCheckResult(
                    healthy=True,
                    service_name="confluence",
                    message=f"Connected to {self.base_url}",
                    latency_ms=latency,
                )

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return HealthCheckResult(
                    healthy=False,
                    service_name="confluence",
                    message="Invalid credentials",
                )
            return HealthCheckResult(
                healthy=False,
                service_name="confluence",
                message=f"API error: HTTP {e.code}",
            )
        except Exception as e:
            return HealthCheckResult(
                healthy=False,
                service_name="confluence",
                message=f"Connection failed: {e}",
            )

    def to_dict(self) -> dict[str, Any]:
        """Return config with secrets masked."""
        return {
            "base_url": self.base_url,
            "username": self.username,
            "api_token": mask_secret(self.api_token),
            "space_keys": self.space_keys,
            "output_dir": str(self.output_dir),
            "max_pages": self.max_pages,
            "include_attachments": self.include_attachments,
            "incremental_sync": self.incremental_sync,
            "sync_interval": self.sync_interval,
            "request_timeout": self.request_timeout,
            "max_retries": self.max_retries,
            "output_format": self.output_format,
        }

    @classmethod
    def from_env(cls) -> "ConfluenceConfig":
        """Load Confluence configuration from environment and config files.

        Priority:
        1. Environment variables
        2. ~/.config/jib/secrets.env
        """
        from ..utils import load_env_file

        config = cls()

        # Load secrets.env
        secrets_file = Path.home() / ".config" / "jib" / "secrets.env"
        secrets = load_env_file(secrets_file)

        config.base_url = os.environ.get(
            "CONFLUENCE_BASE_URL", secrets.get("CONFLUENCE_BASE_URL", "")
        )
        config.username = os.environ.get(
            "CONFLUENCE_USERNAME", secrets.get("CONFLUENCE_USERNAME", "")
        )
        config.api_token = os.environ.get(
            "CONFLUENCE_API_TOKEN", secrets.get("CONFLUENCE_API_TOKEN", "")
        )
        config.space_keys = os.environ.get(
            "CONFLUENCE_SPACE_KEYS", secrets.get("CONFLUENCE_SPACE_KEYS", "")
        )

        output_dir = os.environ.get("CONFLUENCE_OUTPUT_DIR", "")
        if output_dir:
            config.output_dir = Path(output_dir).expanduser()

        config.max_pages = safe_int(os.environ.get("CONFLUENCE_MAX_PAGES"), 0)
        config.include_attachments = safe_bool(
            os.environ.get("CONFLUENCE_INCLUDE_ATTACHMENTS"), False
        )
        config.incremental_sync = safe_bool(os.environ.get("CONFLUENCE_INCREMENTAL_SYNC"), True)
        config.sync_interval = safe_int(os.environ.get("CONFLUENCE_SYNC_INTERVAL"), 3600)
        config.request_timeout = safe_int(os.environ.get("CONFLUENCE_REQUEST_TIMEOUT"), 30)
        config.max_retries = safe_int(os.environ.get("CONFLUENCE_MAX_RETRIES"), 3)
        config.output_format = os.environ.get("CONFLUENCE_OUTPUT_FORMAT", "html")

        return config

    @property
    def space_keys_list(self) -> list[str]:
        """Return space keys as a list."""
        if not self.space_keys:
            return []
        return [k.strip() for k in self.space_keys.split(",") if k.strip()]
