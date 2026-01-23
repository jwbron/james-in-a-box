"""
Slack configuration for jib services.

Loads configuration from:
1. Environment variables (highest priority)
2. ~/.config/jib/secrets.env (for tokens)
3. ~/.config/jib/config.yaml (for other settings)
"""

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..base import BaseConfig, HealthCheckResult, ValidationResult
from ..utils import load_env_file, load_yaml_file
from ..validators import mask_secret, validate_non_empty, validate_slack_token


@dataclass
class SlackConfig(BaseConfig):
    """Configuration for Slack integration.

    Attributes:
        bot_token: Slack bot token (xoxb-...)
        app_token: Slack app-level token for Socket Mode (xapp-...)
        channel: Default channel for notifications
        allowed_users: List of allowed Slack user IDs (empty = all allowed)
        owner_user_id: Owner's Slack user ID for DMs
        self_dm_channel: User's self-DM channel ID
        batch_window_seconds: Seconds to batch notifications
    """

    bot_token: str = ""
    app_token: str = ""
    channel: str = ""
    allowed_users: list[str] = field(default_factory=list)
    owner_user_id: str = ""
    self_dm_channel: str = ""
    batch_window_seconds: int = 15

    def validate(self) -> ValidationResult:
        """Validate Slack configuration."""
        errors: list[str] = []
        warnings: list[str] = []

        # Validate bot token
        is_valid, error = validate_non_empty(self.bot_token, "bot_token")
        if not is_valid:
            errors.append(error)
        else:
            is_valid, error = validate_slack_token(self.bot_token)
            if not is_valid:
                errors.append(f"bot_token: {error}")

        # App token is optional but must be valid if provided
        if self.app_token:
            is_valid, error = validate_slack_token(self.app_token)
            if not is_valid:
                errors.append(f"app_token: {error}")
            if not self.app_token.startswith("xapp-"):
                warnings.append("app_token should start with 'xapp-' for Socket Mode")

        # Channel is required for notifier
        if not self.channel:
            warnings.append("channel not set - required for notifications")

        if errors:
            return ValidationResult.invalid(errors, warnings)

        return ValidationResult.valid(warnings)

    def health_check(self, timeout: float = 5.0) -> HealthCheckResult:
        """Check Slack API connectivity.

        Calls auth.test to verify the token is valid.
        """
        if not self.bot_token:
            return HealthCheckResult(
                healthy=False,
                service_name="slack",
                message="Bot token not configured",
            )

        try:
            import json
            import urllib.request

            start = time.time()
            req = urllib.request.Request(
                "https://slack.com/api/auth.test",
                headers={
                    "Authorization": f"Bearer {self.bot_token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode())
                latency = (time.time() - start) * 1000

                if data.get("ok"):
                    bot_name = data.get("user", "unknown")
                    team = data.get("team", "unknown")
                    return HealthCheckResult(
                        healthy=True,
                        service_name="slack",
                        message=f"Authenticated as {bot_name} in {team}",
                        latency_ms=latency,
                    )
                else:
                    error = data.get("error", "unknown error")
                    return HealthCheckResult(
                        healthy=False,
                        service_name="slack",
                        message=f"Auth failed: {error}",
                        latency_ms=latency,
                    )

        except Exception as e:
            return HealthCheckResult(
                healthy=False,
                service_name="slack",
                message=f"Connection failed: {e}",
            )

    def to_dict(self) -> dict[str, Any]:
        """Return config with secrets masked."""
        return {
            "bot_token": mask_secret(self.bot_token),
            "app_token": mask_secret(self.app_token),
            "channel": self.channel,
            "allowed_users": self.allowed_users,
            "owner_user_id": self.owner_user_id,
            "self_dm_channel": self.self_dm_channel,
            "batch_window_seconds": self.batch_window_seconds,
        }

    @classmethod
    def from_env(cls) -> "SlackConfig":
        """Load Slack configuration from environment and config files.

        Priority:
        1. Environment variables
        2. ~/.config/jib/secrets.env
        3. ~/.config/jib/config.yaml (supports both nested 'slack:' and top-level keys)

        For backwards compatibility, supports both config structures:
        - Nested: slack: { channel: "C123" }
        - Top-level: slack_channel: "C123"
        """
        config = cls()

        # Load from secrets.env file
        secrets_file = Path.home() / ".config" / "jib" / "secrets.env"
        secrets = load_env_file(secrets_file)

        # Load from config.yaml
        config_file = Path.home() / ".config" / "jib" / "config.yaml"
        yaml_config = load_yaml_file(config_file)
        slack_config = yaml_config.get("slack", {})

        # Helper to get value from nested or top-level config
        def get_config(nested_key: str, top_level_key: str, default: any = "") -> any:
            """Get value from nested slack config, falling back to top-level."""
            return slack_config.get(nested_key) or yaml_config.get(top_level_key, default)

        # Bot token: env > secrets.env
        config.bot_token = os.environ.get(
            "SLACK_TOKEN",
            secrets.get("SLACK_TOKEN", ""),
        )

        # App token: env > secrets.env
        config.app_token = os.environ.get(
            "SLACK_APP_TOKEN",
            secrets.get("SLACK_APP_TOKEN", ""),
        )

        # Channel: env > config.yaml (nested or top-level)
        config.channel = os.environ.get(
            "SLACK_CHANNEL",
            get_config("channel", "slack_channel", ""),
        )

        # Other settings from config.yaml (nested or top-level)
        config.allowed_users = get_config("allowed_users", "allowed_users", [])
        config.owner_user_id = get_config("owner_user_id", "owner_user_id", "")
        config.self_dm_channel = get_config("self_dm_channel", "self_dm_channel", "")
        config.batch_window_seconds = get_config("batch_window_seconds", "batch_window_seconds", 15)

        return config
