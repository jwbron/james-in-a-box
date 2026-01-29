#!/usr/bin/env python3
"""
jib Setup Script - Declarative Setup Architecture

This script replaces setup.sh with a Python-based setup system.
It consolidates all configuration into:
  - ~/.config/jib/secrets.env  (secrets)
  - ~/.config/jib/config.yaml  (non-secret settings)

Usage:
  ./setup.py                    # Full setup (default)
  ./setup.py --enable-services  # Enable all systemd services
  ./setup.py --disable-services # Disable all systemd services
  ./setup.py --enable SERVICE   # Enable specific service
  ./setup.py --disable SERVICE  # Disable specific service
  ./setup.py --update           # Update configs and restart services
  ./setup.py --force            # Force reinstall

For more information, see docs/adr/not-implemented/ADR-Declarative-Setup-Architecture.md
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# Add config directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


# ANSI color codes for terminal output
class Colors:
    """Terminal color codes for formatted output."""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

    @staticmethod
    def strip_if_no_tty(text: str) -> str:
        """Strip ANSI codes if not outputting to a TTY."""
        if not sys.stdout.isatty():
            import re

            return re.sub(r"\033\[[0-9;]+m", "", text)
        return text


class SetupLogger:
    """Handles formatted logging for the setup process."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(message)s")
        self.logger = logging.getLogger(__name__)

    def info(self, msg: str):
        """Print info message."""
        colored = f"{Colors.OKBLUE}i{Colors.ENDC} {msg}"
        print(Colors.strip_if_no_tty(colored))

    def success(self, msg: str):
        """Print success message."""
        colored = f"{Colors.OKGREEN}✓{Colors.ENDC} {msg}"
        print(Colors.strip_if_no_tty(colored))

    def warning(self, msg: str):
        """Print warning message."""
        colored = f"{Colors.WARNING}⚠{Colors.ENDC} {msg}"
        print(Colors.strip_if_no_tty(colored))

    def error(self, msg: str):
        """Print error message."""
        colored = f"{Colors.FAIL}✗{Colors.ENDC} {msg}"
        print(Colors.strip_if_no_tty(colored))

    def header(self, msg: str):
        """Print section header."""
        colored = f"\n{Colors.BOLD}{Colors.HEADER}{msg}{Colors.ENDC}\n"
        print(Colors.strip_if_no_tty(colored))

    def step(self, msg: str):
        """Print step message."""
        colored = f"{Colors.OKCYAN}▸{Colors.ENDC} {msg}"
        print(Colors.strip_if_no_tty(colored))


class DependencyChecker:
    """Checks for required system dependencies."""

    def __init__(self, logger: SetupLogger):
        self.logger = logger
        self.missing = []

    def check_command(self, cmd: str, required: bool = True) -> bool:
        """Check if a command is available in PATH."""
        found = shutil.which(cmd) is not None
        if found:
            self.logger.success(f"{cmd} is installed")
        elif required:
            self.logger.error(f"{cmd} is NOT installed (required)")
            self.missing.append(cmd)
        else:
            self.logger.warning(f"{cmd} is NOT installed (optional)")
        return found

    def check_all(self) -> bool:
        """Check all required dependencies.

        Returns:
            True if all required dependencies are present, False otherwise.
        """
        self.logger.header("Checking Dependencies")

        # Required dependencies
        self.check_command("docker")
        self.check_command("git")
        self.check_command("gh")  # GitHub CLI

        # PyYAML is required (checked at module load)
        self.logger.success("PyYAML is installed")

        # Optional dependencies
        self.check_command("uv", required=False)
        self.check_command("systemctl", required=False)

        if self.missing:
            self.logger.error(f"\nMissing required dependencies: {', '.join(self.missing)}")
            self.logger.error("Please install them before continuing.")
            return False

        self.logger.success("\n✓ All required dependencies are installed")
        return True


class UserPrompter:
    """Handles user input prompts with validation."""

    def __init__(self, logger: SetupLogger):
        self.logger = logger

    def prompt(
        self,
        question: str,
        default: str | None = None,
        required: bool = False,
        validator: Callable | None = None,
    ) -> str:
        """Prompt user for input with validation.

        Args:
            question: The question to ask
            default: Default value (shown in brackets)
            required: If True, empty input is not allowed
            validator: Optional validation function that raises ValueError if invalid

        Returns:
            User's input (or default if provided and user pressed Enter)
        """
        while True:
            if default:
                prompt_text = f"{question} [{default}]: "
            else:
                prompt_text = f"{question}: "

            response = input(
                Colors.strip_if_no_tty(f"{Colors.OKCYAN}?{Colors.ENDC} {prompt_text}")
            ).strip()

            # Use default if no input
            if not response and default:
                response = default

            # Check if required
            if required and not response:
                self.logger.error("This field is required. Please enter a value.")
                continue

            # Run validator if provided
            if validator and response:
                try:
                    validator(response)
                    return response
                except ValueError as e:
                    self.logger.error(str(e))
                    continue

            return response

    def prompt_yes_no(self, question: str, default: bool = True) -> bool:
        """Prompt for yes/no question.

        Args:
            question: The question to ask
            default: Default answer (True for yes, False for no)

        Returns:
            True for yes, False for no
        """
        default_str = "Y/n" if default else "y/N"
        response = (
            input(
                Colors.strip_if_no_tty(
                    f"{Colors.OKCYAN}?{Colors.ENDC} {question} [{default_str}]: "
                )
            )
            .strip()
            .lower()
        )

        if not response:
            return default

        return response in ["y", "yes"]

    def prompt_list(self, question: str, delimiter: str = ",") -> list[str]:
        """Prompt for a comma-separated list.

        Args:
            question: The question to ask
            delimiter: Character to split on (default: comma)

        Returns:
            List of stripped, non-empty strings
        """
        response = input(
            Colors.strip_if_no_tty(f"{Colors.OKCYAN}?{Colors.ENDC} {question}: ")
        ).strip()

        if not response:
            return []

        return [item.strip() for item in response.split(delimiter) if item.strip()]


class ConfigMigrator:
    """Handles migration from legacy config locations to new structure."""

    def __init__(self, logger: SetupLogger):
        self.logger = logger
        self.new_config_dir = Path.home() / ".config" / "jib"
        self.new_secrets_file = self.new_config_dir / "secrets.env"
        self.new_config_file = self.new_config_dir / "config.yaml"

        # Legacy config locations in ~/.config/jib (standalone files)
        self.legacy_locations = {
            "anthropic_api_key": self.new_config_dir / "anthropic-api-key",
            "google_api_key": self.new_config_dir / "google-api-key",
            "openai_api_key": self.new_config_dir / "openai-api-key",
            "github_app_id": self.new_config_dir / "github-app-id",
            "github_app_installation": self.new_config_dir / "github-app-installation-id",
            "github_app_key": self.new_config_dir / "github-app-private-key.pem",
            "github_token": self.new_config_dir / "github-token",
        }

        # Legacy config from other services
        self.legacy_notifier_config = Path.home() / ".config" / "jib-notifier" / "config.json"
        self.legacy_context_sync_env = Path.home() / ".config" / "context-sync" / ".env"

    def check_needs_migration(self) -> bool:
        """Check if any legacy config files exist that need migration.

        Returns:
            True if migration is needed, False otherwise
        """
        # Check for standalone API key files and other legacy files
        for _name, path in self.legacy_locations.items():
            if path.exists():
                return True

        # Check for legacy service configs
        if self.legacy_notifier_config.exists():
            return True
        return bool(self.legacy_context_sync_env.exists())

    def migrate_configs(self) -> bool:
        """Migrate legacy configurations to new structure.

        Returns:
            True if migration succeeded, False otherwise
        """
        if not self.check_needs_migration():
            return True  # Nothing to migrate

        self.logger.header("Migrating Legacy Configuration")
        self.logger.info("Found legacy configuration files. Migrating to new structure...")
        self.logger.info("")

        migrated = False
        secrets = {}
        config = {}

        # Load existing secrets if any
        if self.new_secrets_file.exists():
            with open(self.new_secrets_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        secrets[key.strip()] = value.strip().strip("\"'")

        # Load existing config if any
        if self.new_config_file.exists():
            with open(self.new_config_file) as f:
                config = yaml.safe_load(f) or {}

        # Migrate from jib-notifier config.json
        if self.legacy_notifier_config.exists():
            self.logger.info(f"Migrating from {self.legacy_notifier_config}")
            try:
                with open(self.legacy_notifier_config) as f:
                    notifier_config = json.load(f)

                # Extract secrets
                if notifier_config.get("slack_token") and "SLACK_TOKEN" not in secrets:
                    secrets["SLACK_TOKEN"] = notifier_config["slack_token"]
                    self.logger.success("Migrated Slack bot token")
                    migrated = True
                if notifier_config.get("slack_app_token") and "SLACK_APP_TOKEN" not in secrets:
                    secrets["SLACK_APP_TOKEN"] = notifier_config["slack_app_token"]
                    self.logger.success("Migrated Slack app token")
                    migrated = True

                # Extract non-secret settings
                if notifier_config.get("slack_channel") and "slack_channel" not in config:
                    config["slack_channel"] = notifier_config["slack_channel"]
                    self.logger.success("Migrated slack_channel")
                    migrated = True
                if notifier_config.get("allowed_users") and "allowed_users" not in config:
                    config["allowed_users"] = notifier_config["allowed_users"]
                    self.logger.success("Migrated allowed_users")
                    migrated = True

            except Exception as e:
                self.logger.warning(f"Failed to migrate jib-notifier config: {e}")

        # Migrate from context-sync .env
        if self.legacy_context_sync_env.exists():
            self.logger.info(f"Migrating from {self.legacy_context_sync_env}")
            try:
                with open(self.legacy_context_sync_env) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            key = key.strip()
                            value = value.strip().strip("\"'")
                            if value and key not in secrets:
                                secrets[key] = value
                                self.logger.success(f"Migrated {key}")
                                migrated = True
            except Exception as e:
                self.logger.warning(f"Failed to migrate context-sync env: {e}")

        # Migrate standalone API key files
        api_key_mapping = {
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "google_api_key": "GOOGLE_API_KEY",
            "openai_api_key": "OPENAI_API_KEY",
        }

        for legacy_name, secret_name in api_key_mapping.items():
            legacy_file = self.legacy_locations[legacy_name]
            if legacy_file.exists() and secret_name not in secrets:
                try:
                    api_key = legacy_file.read_text().strip()
                    if api_key:
                        secrets[secret_name] = api_key
                        self.logger.success(f"Migrated {legacy_name} → {secret_name}")
                        migrated = True
                except Exception as e:
                    self.logger.warning(f"Failed to migrate {legacy_name}: {e}")

        # Migrate GitHub token file
        github_token_file = self.legacy_locations.get("github_token")
        if github_token_file and github_token_file.exists() and "GITHUB_TOKEN" not in secrets:
            try:
                token = github_token_file.read_text().strip()
                if token:
                    secrets["GITHUB_TOKEN"] = token
                    self.logger.success("Migrated github-token → GITHUB_TOKEN")
                    migrated = True
            except Exception as e:
                self.logger.warning(f"Failed to migrate github-token: {e}")

        # Save migrated secrets
        if migrated:
            if secrets:
                self._write_secrets(secrets)
            if config:
                self.new_config_file.write_text(yaml.dump(config, default_flow_style=False))
                self.logger.success(f"Config written to {self.new_config_file}")

            self.logger.success("\n✓ Configuration migration complete")
            self.logger.info("")
            self.logger.info("Legacy files have been migrated to:")
            self.logger.info(f"  {self.new_secrets_file}")
            self.logger.info(f"  {self.new_config_file}")
            self.logger.info("")
            self.logger.warning(
                "IMPORTANT: The legacy files still exist for backward compatibility."
            )
            self.logger.warning("You can safely delete them after verifying jib works correctly.")
            self.logger.info("")

        return True

    def _write_secrets(self, secrets: dict[str, str]):
        """Write secrets to secrets.env with proper formatting.

        Args:
            secrets: Dictionary of secret key-value pairs
        """
        lines = [
            "# jib Secrets Configuration",
            "# This file contains sensitive credentials - DO NOT COMMIT",
            "",
        ]

        # Group secrets by service
        groups = {
            "LLM API Keys": ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"],
            "Slack Integration": ["SLACK_TOKEN", "SLACK_APP_TOKEN"],
            "GitHub": ["GITHUB_TOKEN", "GITHUB_READONLY_TOKEN", "GITHUB_INCOGNITO_TOKEN"],
            "Confluence": [
                "CONFLUENCE_BASE_URL",
                "CONFLUENCE_USERNAME",
                "CONFLUENCE_API_TOKEN",
                "CONFLUENCE_SPACE_KEYS",
            ],
            "JIRA": [
                "JIRA_BASE_URL",
                "JIRA_USERNAME",
                "JIRA_API_TOKEN",
                "JIRA_JQL_QUERY",
            ],
        }

        written = set()
        for group_name, keys in groups.items():
            group_secrets = [(k, secrets.get(k)) for k in keys if secrets.get(k)]
            if group_secrets:
                lines.append(f"# {group_name}")
                for key, value in group_secrets:
                    lines.append(f'{key}="{value}"')
                    written.add(key)
                lines.append("")

        # Write any remaining secrets not in groups
        remaining = [(k, v) for k, v in secrets.items() if k not in written]
        if remaining:
            lines.append("# Other")
            for key, value in remaining:
                lines.append(f'{key}="{value}"')
            lines.append("")

        self.new_secrets_file.write_text("\n".join(lines))
        os.chmod(self.new_secrets_file, 0o600)


class ConfigManager:
    """Manages configuration file reading and writing."""

    def __init__(self, logger: SetupLogger):
        self.logger = logger
        self.config_dir = Path.home() / ".config" / "jib"
        self.secrets_file = self.config_dir / "secrets.env"
        self.config_file = self.config_dir / "config.yaml"
        self.repos_file = self.config_dir / "repositories.yaml"

    def ensure_config_dir(self):
        """Ensure config directory exists with proper permissions."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self.config_dir, 0o700)
            self.logger.success(f"Config directory ready: {self.config_dir}")
        except PermissionError as e:
            self.logger.error(f"Cannot create config directory: {e}")
            self.logger.error(f"Please ensure {self.config_dir.parent} is writable")
            raise

    def load_secrets(self) -> dict[str, str]:
        """Load secrets from secrets.env.

        Returns:
            Dictionary of secret key-value pairs
        """
        secrets = {}
        if self.secrets_file.exists():
            with open(self.secrets_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        secrets[key.strip()] = value.strip().strip("\"'")
        return secrets

    def load_config(self) -> dict[str, Any]:
        """Load config from config.yaml.

        Returns:
            Dictionary of configuration values
        """
        if self.config_file.exists():
            with open(self.config_file) as f:
                return yaml.safe_load(f) or {}
        return {}

    def write_secrets(self, secrets: dict[str, str]):
        """Write secrets to secrets.env with secure permissions.

        Args:
            secrets: Dictionary of secret key-value pairs
        """
        lines = [
            "# jib Secrets Configuration",
            "# This file contains sensitive credentials - DO NOT COMMIT",
            "",
        ]

        # Group secrets by service
        groups = {
            "Slack Integration": ["SLACK_TOKEN", "SLACK_APP_TOKEN"],
            "GitHub": ["GITHUB_TOKEN", "GITHUB_READONLY_TOKEN"],
            "Anthropic": ["ANTHROPIC_API_KEY"],
            "Confluence": [
                "CONFLUENCE_BASE_URL",
                "CONFLUENCE_USERNAME",
                "CONFLUENCE_API_TOKEN",
                "CONFLUENCE_SPACE_KEYS",
            ],
            "JIRA": [
                "JIRA_BASE_URL",
                "JIRA_USERNAME",
                "JIRA_API_TOKEN",
                "JIRA_JQL_QUERY",
            ],
        }

        written = set()
        for group_name, keys in groups.items():
            group_secrets = [(k, secrets.get(k)) for k in keys if secrets.get(k)]
            if group_secrets:
                lines.append(f"# {group_name}")
                for key, value in group_secrets:
                    lines.append(f'{key}="{value}"')
                    written.add(key)
                lines.append("")

        # Write any remaining secrets not in groups
        remaining = [(k, v) for k, v in secrets.items() if k not in written]
        if remaining:
            lines.append("# Other")
            for key, value in remaining:
                lines.append(f'{key}="{value}"')
            lines.append("")

        self.secrets_file.write_text("\n".join(lines))
        os.chmod(self.secrets_file, 0o600)
        self.logger.success(f"Secrets written to {self.secrets_file}")

    def write_config(self, config: dict[str, Any]):
        """Write non-secret config to config.yaml.

        Args:
            config: Dictionary of configuration values
        """
        self.config_file.write_text(yaml.dump(config, default_flow_style=False))
        self.logger.success(f"Config written to {self.config_file}")

    def load_repositories(self) -> dict[str, Any]:
        """Load repository configuration.

        Returns:
            Dictionary with writable_repos, readable_repos, incognito, and repo_settings
        """
        if self.repos_file.exists():
            with open(self.repos_file) as f:
                config = yaml.safe_load(f) or {}
                # Ensure all expected keys exist
                config.setdefault("writable_repos", [])
                config.setdefault("readable_repos", [])
                config.setdefault("incognito", None)
                config.setdefault("repo_settings", {})
                return config
        return {"writable_repos": [], "readable_repos": [], "incognito": None, "repo_settings": {}}

    def write_repositories(
        self,
        writable: list[str],
        readable: list[str],
        github_username: str = "",
        local_repos: list[str] | None = None,
        incognito: dict[str, str | None] | None = None,
        repo_settings: dict[str, dict] | None = None,
    ):
        """Write repository configuration.

        Args:
            writable: List of repositories with write access
            readable: List of repositories with read-only access
            github_username: GitHub username for config file
            local_repos: List of local repository paths to mount
            incognito: Incognito mode config (github_user, git_name, git_email)
            repo_settings: Per-repo settings (e.g., auth_mode)
        """
        repos_config: dict[str, Any] = {
            "github_username": github_username,
            "writable_repos": writable,
            "readable_repos": readable,
            "local_repos": {"paths": local_repos or []},
        }

        # Add incognito config if provided (filter out None values)
        if incognito:
            filtered_incognito = {k: v for k, v in incognito.items() if v is not None}
            if filtered_incognito:
                repos_config["incognito"] = filtered_incognito

        # Add repo_settings if provided
        if repo_settings:
            repos_config["repo_settings"] = repo_settings

        self.repos_file.write_text(yaml.dump(repos_config, default_flow_style=False))
        self.logger.success(f"Repository config written to {self.repos_file}")


class ServiceManager:
    """Manages systemd services."""

    # Core services that should always be enabled (non-LLM)
    # Note: venv-setup must be first since other Python services depend on it
    CORE_SERVICES = [
        "venv-setup.service",
        "slack-notifier.service",
        "slack-receiver.service",
        "github-token-refresher.timer",
        "worktree-watcher.timer",
        "gateway-sidecar.service",
    ]

    # LLM-based services that use tokens (opt-in)
    LLM_SERVICES = [
        "context-sync.timer",
    ]

    # Mapping of service names to their setup script paths
    SERVICE_SETUP_SCRIPTS = {
        "venv-setup.service": "host-services/venv-setup.sh",
        "slack-notifier.service": "host-services/slack/slack-notifier/setup.sh",
        "slack-receiver.service": "host-services/slack/slack-receiver/setup.sh",
        "github-token-refresher.timer": "host-services/utilities/github-token-refresher/setup.sh",
        "github-token-refresher.service": "host-services/utilities/github-token-refresher/setup.sh",
        "worktree-watcher.timer": "host-services/utilities/worktree-watcher/setup.sh",
        "gateway-sidecar.service": "gateway-sidecar/setup.sh",
        "context-sync.timer": "host-services/sync/context-sync/setup.sh",
        "context-sync.service": "host-services/sync/context-sync/setup.sh",
    }

    def __init__(self, logger: SetupLogger):
        self.logger = logger
        self.has_systemctl = shutil.which("systemctl") is not None
        self.repo_root = Path(__file__).parent

    def _daemon_reload(self) -> bool:
        """Reload systemd daemon to pick up service file changes.

        Returns:
            True if successful, False otherwise
        """
        if not self.has_systemctl:
            return False

        try:
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"], check=True, capture_output=True, text=True
            )
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to reload systemd daemon: {e.stderr}")
            return False

    def _run_service_setup(self, service: str) -> bool:
        """Run the setup script for a service if it exists.

        Args:
            service: Service name (e.g., "jib-slack-notifier.service")

        Returns:
            True if successful or no setup script exists, False on error
        """
        # Normalize service name - try with .service suffix if not found
        setup_script = self.SERVICE_SETUP_SCRIPTS.get(service)
        if not setup_script and not service.endswith((".service", ".timer")):
            setup_script = self.SERVICE_SETUP_SCRIPTS.get(f"{service}.service")
        if not setup_script:
            # No setup script defined, that's okay
            return True

        script_path = self.repo_root / setup_script
        if not script_path.exists():
            self.logger.warning(f"Setup script not found: {setup_script}")
            return True  # Don't fail if script is missing

        try:
            self.logger.step(f"Running setup script for {service}")
            cmd = ["bash", str(script_path)]
            result = subprocess.run(
                cmd,
                check=False,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=120,  # Container build may take longer
            )
            if result.returncode != 0:
                self.logger.warning(f"Setup script exited with code {result.returncode}")
                if result.stderr:
                    self.logger.warning(f"  {result.stderr.strip()}")
                # Don't fail - setup script may have warnings
            return True
        except subprocess.TimeoutExpired:
            self.logger.error(f"Setup script timed out for {service}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to run setup script for {service}: {e}")
            return False

    def enable_service(self, service: str, run_setup: bool = True) -> bool:
        """Enable and start a single service.

        Args:
            service: Service name (e.g., "jib-slack-notifier.service")
            run_setup: Whether to run the service's setup script first

        Returns:
            True if successful, False otherwise
        """
        # Gateway sidecar runs as Docker container, not systemd service
        # Its setup script handles everything (build image, start container)
        if service == "gateway-sidecar.service":
            if run_setup:
                if self._run_service_setup(service):
                    self.logger.success("Gateway sidecar container configured")
                    return True
                else:
                    self.logger.error("Gateway sidecar setup failed")
                    return False
            return True

        if not self.has_systemctl:
            self.logger.warning("systemctl not available, skipping service management")
            return False

        # Run setup script if requested
        if run_setup and not self._run_service_setup(service):
            self.logger.warning(f"Setup script failed for {service}, continuing anyway")

        # Reload daemon to pick up any service file changes
        self._daemon_reload()

        try:
            subprocess.run(
                ["systemctl", "--user", "enable", service],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["systemctl", "--user", "start", service],
                check=True,
                capture_output=True,
                text=True,
            )
            self.logger.success(f"Enabled and started {service}")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to enable {service}: {e.stderr}")
            return False

    def disable_service(self, service: str) -> bool:
        """Disable and stop a single service.

        Args:
            service: Service name (e.g., "jib-slack-notifier.service")

        Returns:
            True if successful, False otherwise
        """
        # Gateway sidecar runs as Docker container
        if service == "gateway-sidecar.service":
            try:
                subprocess.run(
                    ["docker", "rm", "-f", "jib-gateway"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.logger.success("Stopped gateway sidecar container")
                return True
            except Exception as e:
                self.logger.error(f"Failed to stop gateway container: {e}")
                return False

        if not self.has_systemctl:
            self.logger.warning("systemctl not available, skipping service management")
            return False

        try:
            subprocess.run(
                ["systemctl", "--user", "stop", service], check=True, capture_output=True, text=True
            )
            subprocess.run(
                ["systemctl", "--user", "disable", service],
                check=True,
                capture_output=True,
                text=True,
            )
            self.logger.success(f"Stopped and disabled {service}")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to disable {service}: {e.stderr}")
            return False

    def enable_all_services(self) -> bool:
        """Enable all jib services (core + LLM).

        Returns:
            True if all services enabled successfully, False otherwise
        """
        self.logger.header("Enabling All Services")

        all_services = self.CORE_SERVICES + self.LLM_SERVICES
        success = True

        for service in all_services:
            if not self.enable_service(service):
                success = False

        if success:
            self.logger.success("\n✓ All services enabled")
        else:
            self.logger.warning("\n⚠ Some services failed to enable")

        return success

    def disable_all_services(self) -> bool:
        """Disable all jib services (core + LLM).

        Returns:
            True if all services disabled successfully, False otherwise
        """
        self.logger.header("Disabling All Services")

        all_services = self.CORE_SERVICES + self.LLM_SERVICES
        success = True

        for service in all_services:
            if not self.disable_service(service):
                success = False

        if success:
            self.logger.success("\n✓ All services disabled")
        else:
            self.logger.warning("\n⚠ Some services failed to disable")

        return success

    def enable_core_services(self) -> bool:
        """Enable only core (non-LLM) services.

        Returns:
            True if all core services enabled successfully, False otherwise
        """
        self.logger.header("Enabling Core Services")

        success = True
        for service in self.CORE_SERVICES:
            if not self.enable_service(service):
                success = False

        if success:
            self.logger.success("\n✓ Core services enabled")
        else:
            self.logger.warning("\n⚠ Some core services failed to enable")

        return success

    def get_service_status(self) -> dict[str, dict[str, str]]:
        """Get status of all jib services.

        Returns:
            Dictionary mapping service names to status info (active, enabled, is_core)
        """
        if not self.has_systemctl:
            return {}

        all_services = self.CORE_SERVICES + self.LLM_SERVICES
        statuses = {}

        for service in all_services:
            # Check if active
            try:
                active_result = subprocess.run(
                    ["systemctl", "--user", "is-active", service],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                active = active_result.stdout.strip()
            except subprocess.CalledProcessError:
                active = "unknown"

            # Check if enabled
            enabled_result = subprocess.run(
                ["systemctl", "--user", "is-enabled", service],
                check=False,
                capture_output=True,
                text=True,
            )
            enabled = (
                enabled_result.stdout.strip() if enabled_result.returncode == 0 else "disabled"
            )

            statuses[service] = {
                "active": active,
                "enabled": enabled,
                "is_core": service in self.CORE_SERVICES,
            }

        return statuses

    def print_service_status(self) -> None:
        """Print a formatted table of service statuses."""
        statuses = self.get_service_status()
        if not statuses:
            self.logger.warning("No service status available")
            return

        self.logger.header("Service Status")

        # Print core services
        self.logger.info("\nCore Services:")
        for service in self.CORE_SERVICES:
            status = statuses.get(service, {})
            active = status.get("active", "unknown")
            enabled = status.get("enabled", "unknown")

            # Color code the status
            active_indicator = "●" if active == "active" else "○"
            active_color = Colors.OKGREEN if active == "active" else Colors.FAIL
            enabled_str = "enabled" if enabled == "enabled" else enabled

            status_line = (
                f"  {active_color}{active_indicator}{Colors.ENDC} {service:<40} {enabled_str:>10}"
            )
            print(Colors.strip_if_no_tty(status_line))

        # Print LLM services
        self.logger.info("\nLLM-Based Services:")
        for service in self.LLM_SERVICES:
            status = statuses.get(service, {})
            active = status.get("active", "unknown")
            enabled = status.get("enabled", "unknown")

            active_indicator = "●" if active == "active" else "○"
            active_color = Colors.OKGREEN if active == "active" else Colors.FAIL
            enabled_str = "enabled" if enabled == "enabled" else enabled

            status_line = (
                f"  {active_color}{active_indicator}{Colors.ENDC} {service:<40} {enabled_str:>10}"
            )
            print(Colors.strip_if_no_tty(status_line))

        self.logger.info("")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="jib setup script - Declarative setup architecture",
        epilog="For more information, see docs/adr/not-implemented/ADR-Declarative-Setup-Architecture.md",
    )

    # Setup modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--update", action="store_true", help="Update mode: reload configs and restart services"
    )

    # Service management
    service_group = parser.add_mutually_exclusive_group()
    service_group.add_argument(
        "--enable-services",
        action="store_true",
        help="Enable all jib systemd services (core + LLM)",
    )
    service_group.add_argument(
        "--enable-core-services", action="store_true", help="Enable only core services (non-LLM)"
    )
    service_group.add_argument(
        "--disable-services", action="store_true", help="Disable all jib systemd services"
    )
    service_group.add_argument("--enable", metavar="SERVICE", help="Enable a specific service")
    service_group.add_argument("--disable", metavar="SERVICE", help="Disable a specific service")
    service_group.add_argument("--status", action="store_true", help="Show status of all services")

    # Other options
    parser.add_argument(
        "--force", action="store_true", help="Force reinstall (overwrite existing configs)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--skip-deps", action="store_true", help="Skip dependency checks")

    return parser.parse_args()


class FullSetup:
    """Handles the full setup flow including Docker, beads, and optional components."""

    def __init__(
        self,
        logger: SetupLogger,
        config_manager: ConfigManager,
        prompter: UserPrompter,
        verbose: bool = False,
    ):
        self.logger = logger
        self.config_manager = config_manager
        self.prompter = prompter
        self.verbose = verbose
        self.repo_root = Path(__file__).parent
        self.shared_dir = Path.home() / ".jib-sharing"
        self.beads_dir = self.shared_dir / "beads"

    def create_shared_directories(self) -> bool:
        """Create shared directories for communication with containers.

        Returns:
            True if successful, False otherwise
        """
        self.logger.header("Creating Shared Directories")

        try:
            # Create main shared directory
            self.shared_dir.mkdir(parents=True, exist_ok=True)
            self.logger.success(f"Shared directory ready: {self.shared_dir}")

            # Create subdirectories
            subdirs = ["notifications", "incoming", "responses", "context", "beads", "logs"]
            for subdir in subdirs:
                (self.shared_dir / subdir).mkdir(exist_ok=True)
                self.logger.success(f"  - {subdir}/")

            return True

        except PermissionError as e:
            self.logger.error(f"Permission denied creating shared directories: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to create shared directories: {e}")
            return False

    def initialize_beads(self) -> bool:
        """Initialize the beads persistent memory system.

        Returns:
            True if successful or already initialized, False otherwise
        """
        self.logger.header("Initializing Beads Persistent Memory")

        # Check if bd command is available
        if not shutil.which("bd"):
            self.logger.warning("beads (bd) not found")
            self.logger.info("Install from: https://github.com/steveyegge/beads")

            return self.prompter.prompt_yes_no("Continue without beads?", default=True)

        # Check if already initialized
        beads_config = self.beads_dir / ".beads" / "issues.jsonl"
        if beads_config.exists():
            self.logger.success(f"Beads already initialized: {self.beads_dir}")
            return True

        # Initialize beads
        self.logger.info(f"Initializing beads repository at {self.beads_dir}...")

        try:
            # Create directory
            self.beads_dir.mkdir(parents=True, exist_ok=True)

            # Initialize git (required by beads)
            self.logger.step("Initializing git repository...")
            result = subprocess.run(
                ["git", "init"], check=False, cwd=self.beads_dir, capture_output=True, text=True
            )
            if result.returncode != 0:
                self.logger.error(f"Failed to initialize git: {result.stderr}")
                return False

            # Initialize beads
            self.logger.step("Initializing beads...")
            result = subprocess.run(
                ["bd", "init"],
                check=False,
                cwd=self.beads_dir,
                input="n\n",  # Say no to git hooks
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                self.logger.error(f"Failed to initialize beads: {result.stderr}")
                return False

            self.logger.success(f"Beads initialized: {self.beads_dir}")
            self.logger.info(
                "Usage in container: bd --allow-stale create 'task description' --labels feature"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize beads: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False

    def validate_context_sync(self) -> bool:
        """Validate context sync configuration.

        Returns:
            True if validation passes or user skips, False on error
        """
        self.logger.header("Context Sync Configuration")

        # Check for Confluence/JIRA config
        self.config_manager.load_config()
        secrets = self.config_manager.load_secrets()

        has_confluence = bool(
            secrets.get("CONFLUENCE_BASE_URL") and secrets.get("CONFLUENCE_API_TOKEN")
        )
        has_jira = bool(secrets.get("JIRA_BASE_URL") and secrets.get("JIRA_API_TOKEN"))

        if has_confluence:
            self.logger.success("Confluence configuration found")
        if has_jira:
            self.logger.success("JIRA configuration found")

        if not has_confluence and not has_jira:
            self.logger.info("No Confluence or JIRA configuration found")
            self.logger.info("Context sync is optional and can be configured later.")
            if self.prompter.prompt_yes_no(
                "Would you like to configure Confluence/JIRA sync now?", default=False
            ):
                return self.prompt_context_sync_config()
            else:
                self.logger.info("Skipping context sync configuration")
                self.logger.info("You can configure it later by editing ~/.config/jib/secrets.env")
                return True

        return True

    def prompt_context_sync_config(self) -> bool:
        """Prompt for Confluence and JIRA configuration.

        Returns:
            True if configuration saved, False otherwise
        """
        secrets = self.config_manager.load_secrets()
        updated = False

        # Confluence
        if self.prompter.prompt_yes_no("Configure Confluence sync?", default=False):
            self.logger.info("\nConfluence Configuration:")
            base_url = self.prompter.prompt(
                "Confluence Base URL (e.g., https://company.atlassian.net/wiki)"
            )
            username = self.prompter.prompt("Confluence Username/Email")
            api_token = self.prompter.prompt("Confluence API Token", required=True)
            space_keys = self.prompter.prompt(
                "Space Keys (comma-separated, e.g., ENG,TEAM)", required=False
            )

            if base_url:
                secrets["CONFLUENCE_BASE_URL"] = base_url
            if username:
                secrets["CONFLUENCE_USERNAME"] = username
            if api_token:
                secrets["CONFLUENCE_API_TOKEN"] = api_token
            if space_keys:
                secrets["CONFLUENCE_SPACE_KEYS"] = space_keys
            updated = True

        # JIRA
        if self.prompter.prompt_yes_no("Configure JIRA sync?", default=False):
            self.logger.info("\nJIRA Configuration:")
            base_url = self.prompter.prompt("JIRA Base URL (e.g., https://company.atlassian.net)")
            username = self.prompter.prompt("JIRA Username/Email")
            api_token = self.prompter.prompt("JIRA API Token", required=True)
            jql_query = self.prompter.prompt(
                "JQL Query (e.g., project = ENG AND status != Done)", default="status != Done"
            )

            if base_url:
                secrets["JIRA_BASE_URL"] = base_url
            if username:
                secrets["JIRA_USERNAME"] = username
            if api_token:
                secrets["JIRA_API_TOKEN"] = api_token
            if jql_query:
                secrets["JIRA_JQL_QUERY"] = jql_query
            updated = True

        if updated:
            self.config_manager.write_secrets(secrets)
            self.logger.success("Context sync configuration saved")

        return True

    def run(self) -> bool:
        """Run the full setup flow.

        Returns:
            True if setup completed successfully, False otherwise
        """
        self.logger.header("Full Setup Mode")
        self.logger.info(
            "This will set up all components including Docker, beads, and optional features."
        )
        self.logger.info("")

        try:
            # 1. Create shared directories
            if not self.create_shared_directories():
                self.logger.error("Failed to create shared directories")
                return False

            # 2. Initialize beads
            if not self.initialize_beads():
                self.logger.warning("Beads initialization failed, but continuing...")

            # 3. Validate context sync (optional)
            if not self.validate_context_sync():
                self.logger.warning("Context sync validation failed, but continuing...")

            self.logger.success("\n✓ Full setup complete!")
            self.logger.info("")
            self.logger.info("Next steps:")
            self.logger.info("  1. Review the configuration files")
            self.logger.info("  2. Run './setup.py --enable-services' to start all jib services")
            self.logger.info("  3. Test the bot by sending a message in Slack")

            return True

        except KeyboardInterrupt:
            self.logger.warning("\n\nSetup cancelled by user")
            return False
        except Exception as e:
            self.logger.error(f"\n\nFull setup failed: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False


class MinimalSetup:
    """Handles the minimal setup flow."""

    def __init__(
        self,
        logger: SetupLogger,
        config_manager: ConfigManager,
        prompter: UserPrompter,
        verbose: bool = False,
        update_mode: bool = False,
    ):
        self.logger = logger
        self.config_manager = config_manager
        self.prompter = prompter
        self.verbose = verbose
        self.update_mode = update_mode

        # Load existing configuration
        self.existing_secrets = self.config_manager.load_secrets()
        self.existing_config = self.config_manager.load_config()
        self.existing_repos = self.config_manager.load_repositories()

        # Flag to track if user wants to remove incognito mode (set by _prompt_incognito_token)
        self._remove_incognito = False

    def is_already_configured(self) -> bool:
        """Check if essential configuration already exists.

        Returns:
            True if all essential config is present, False otherwise
        """
        # Required secrets
        required_secrets = ["SLACK_TOKEN", "SLACK_APP_TOKEN"]
        # Need either GITHUB_TOKEN or GitHub App config
        has_github = "GITHUB_TOKEN" in self.existing_secrets or (
            (self.config_manager.config_dir / "github-app-id").exists()
            and (self.config_manager.config_dir / "github-app-private-key.pem").exists()
        )

        # Check all required secrets exist
        for secret in required_secrets:
            if not self.existing_secrets.get(secret):
                return False

        if not has_github:
            return False

        # Check essential config values
        return self.existing_config.get("github_username")

    def detect_github_username(self) -> str | None:
        """Try to detect GitHub username from gh CLI."""
        try:
            result = subprocess.run(
                ["gh", "api", "user", "--jq", ".login"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def prompt_github_username(self) -> str:
        """Prompt for GitHub username with auto-detection."""
        existing = self.existing_config.get("github_username")

        # In update mode, always prompt with existing as default
        if self.update_mode:
            self.logger.header("GitHub Configuration")
            if existing:
                return self.prompter.prompt("GitHub username", default=existing, required=True)
            # Fall through to normal flow if no existing value

        # Check if we already have it (non-update mode)
        if existing:
            self.logger.success(f"Using existing GitHub username: {existing}")
            return existing

        self.logger.header("GitHub Configuration")

        detected = self.detect_github_username()
        if detected:
            self.logger.info(f"Detected GitHub username: {detected}")
            if self.prompter.prompt_yes_no("Use this username?", default=True):
                return detected

        return self.prompter.prompt("Enter your GitHub username", required=True)

    def prompt_bot_name(self) -> str:
        """Prompt for bot name."""
        existing = self.existing_config.get("bot_name")

        # In update mode, always prompt with existing as default
        if self.update_mode and existing:
            return self.prompter.prompt("Bot name", default=existing, required=True)

        # Check if we already have it (non-update mode)
        if existing:
            self.logger.success(f"Using existing bot name: {existing}")
            return existing

        return self.prompter.prompt("Bot name", default="james-in-a-box", required=True)

    def validate_slack_token(self, token: str, prefix: str):
        """Validate Slack token has correct prefix."""
        if not token.startswith(prefix):
            raise ValueError(f"Token must start with '{prefix}'")

    def _validate_choice(
        self, value: str, valid_choices: list[str], error_msg: str, case_insensitive: bool = False
    ) -> None:
        """Validate value is one of the valid choices."""
        check_value = value.lower() if case_insensitive else value
        check_choices = [c.lower() for c in valid_choices] if case_insensitive else valid_choices
        if check_value not in check_choices:
            raise ValueError(error_msg)

    def _validate_prefix(
        self, value: str, prefix: str, error_msg: str, allow_empty: bool = False
    ) -> None:
        """Validate that value starts with the expected prefix.

        Args:
            value: The value to validate
            prefix: Required prefix string
            error_msg: Error message if validation fails
            allow_empty: If True, empty values pass validation

        Raises:
            ValueError: If value doesn't start with prefix (unless empty and allow_empty)
        """
        if allow_empty and not value:
            return
        if not value.startswith(prefix):
            raise ValueError(error_msg)

    def _validate_first_char(
        self, value: str, valid_chars: list[str], error_msg: str, allow_empty: bool = False
    ) -> None:
        """Validate that value starts with one of the valid characters.

        Args:
            value: The value to validate
            valid_chars: List of valid first characters
            error_msg: Error message if validation fails
            allow_empty: If True, empty values pass validation

        Raises:
            ValueError: If first char not in valid_chars (unless empty and allow_empty)
        """
        if allow_empty and not value:
            return
        if not value or value[0] not in valid_chars:
            raise ValueError(error_msg)

    def _mask_secret(self, secret: str, visible_chars: int = 8) -> str:
        """Mask a secret for display, showing only first few characters."""
        if not secret:
            return ""
        if len(secret) <= visible_chars:
            return "*" * len(secret)
        return secret[:visible_chars] + "..." + "*" * 8

    def prompt_slack_tokens(self) -> dict[str, str]:
        """Prompt for Slack tokens with validation."""
        secrets = {}

        # Check if we already have Slack tokens
        existing_bot_token = self.existing_secrets.get("SLACK_TOKEN")
        existing_app_token = self.existing_secrets.get("SLACK_APP_TOKEN")

        # In update mode, prompt with option to keep existing
        if self.update_mode:
            self.logger.header("Slack Integration")
            self.logger.info("Get tokens from: https://api.slack.com/apps")
            self.logger.info("Press Enter to keep existing value, or enter new token.")
            self.logger.info("")

            if existing_bot_token:
                self.logger.info(f"Current bot token: {self._mask_secret(existing_bot_token)}")
                new_bot_token = self.prompter.prompt(
                    "Slack Bot Token (xoxb-...) [keep existing]",
                    validator=lambda t: self.validate_slack_token(t, "xoxb-") if t else None,
                )
                secrets["SLACK_TOKEN"] = new_bot_token if new_bot_token else existing_bot_token
            else:
                secrets["SLACK_TOKEN"] = self.prompter.prompt(
                    "Slack Bot Token (xoxb-...)",
                    required=True,
                    validator=lambda t: self.validate_slack_token(t, "xoxb-"),
                )

            if existing_app_token:
                self.logger.info(f"Current app token: {self._mask_secret(existing_app_token)}")
                new_app_token = self.prompter.prompt(
                    "Slack App Token (xapp-...) [keep existing]",
                    validator=lambda t: self.validate_slack_token(t, "xapp-") if t else None,
                )
                secrets["SLACK_APP_TOKEN"] = new_app_token if new_app_token else existing_app_token
            else:
                secrets["SLACK_APP_TOKEN"] = self.prompter.prompt(
                    "Slack App Token (xapp-...)",
                    required=True,
                    validator=lambda t: self.validate_slack_token(t, "xapp-"),
                )

            return secrets

        # Non-update mode: use existing if available
        if existing_bot_token and existing_app_token:
            self.logger.success("Using existing Slack tokens")
            return {
                "SLACK_TOKEN": existing_bot_token,
                "SLACK_APP_TOKEN": existing_app_token,
            }

        self.logger.header("Slack Integration")
        self.logger.info("Get tokens from: https://api.slack.com/apps")
        self.logger.info("")

        if existing_bot_token:
            self.logger.info(f"Using existing Slack bot token: {existing_bot_token[:20]}...")
            secrets["SLACK_TOKEN"] = existing_bot_token
        else:
            bot_token = self.prompter.prompt(
                "Slack Bot Token (xoxb-...)",
                required=True,
                validator=lambda t: self.validate_slack_token(t, "xoxb-"),
            )
            secrets["SLACK_TOKEN"] = bot_token

        if existing_app_token:
            self.logger.info(f"Using existing Slack app token: {existing_app_token[:20]}...")
            secrets["SLACK_APP_TOKEN"] = existing_app_token
        else:
            app_token = self.prompter.prompt(
                "Slack App Token (xapp-...)",
                required=True,
                validator=lambda t: self.validate_slack_token(t, "xapp-"),
            )
            secrets["SLACK_APP_TOKEN"] = app_token

        return secrets

    def prompt_github_auth(self) -> dict[str, str]:
        """Prompt for GitHub authentication (App or PAT)."""
        secrets = {}

        # Check if GitHub auth already exists
        has_github_token = "GITHUB_TOKEN" in self.existing_secrets
        has_github_app = (self.config_manager.config_dir / "github-app-id").exists() and (
            self.config_manager.config_dir / "github-app-private-key.pem"
        ).exists()

        # In update mode, allow updating existing tokens
        if self.update_mode and has_github_token:
            self.logger.header("GitHub Authentication")
            existing_token = self.existing_secrets.get("GITHUB_TOKEN", "")
            self.logger.info(f"Current GitHub token: {self._mask_secret(existing_token)}")
            self.logger.info("Press Enter to keep existing, or enter new token.")
            self.logger.info(
                "Required permissions: Contents (R/W), Pull requests (R/W), Workflows (R)"
            )
            self.logger.info("")

            new_token = self.prompter.prompt(
                "GitHub Personal Access Token (ghp_...) [keep existing]",
                validator=lambda t: self._validate_prefix(
                    t, "ghp_", "Token must start with 'ghp_'", allow_empty=True
                ),
            )
            secrets["GITHUB_TOKEN"] = new_token if new_token else existing_token

            # Handle read-only token
            existing_readonly = self.existing_secrets.get("GITHUB_READONLY_TOKEN", "")
            if existing_readonly:
                self.logger.info(f"Current read-only token: {self._mask_secret(existing_readonly)}")
                self.logger.info("Required permissions: Contents (R), Pull requests (R)")
                new_readonly = self.prompter.prompt(
                    "GitHub Read-Only Token (ghp_...) [keep existing]",
                    validator=lambda t: self._validate_prefix(
                        t, "ghp_", "Token must start with 'ghp_'", allow_empty=True
                    ),
                )
                secrets["GITHUB_READONLY_TOKEN"] = (
                    new_readonly if new_readonly else existing_readonly
                )
            elif self.prompter.prompt_yes_no(
                "Add a read-only token for monitoring external repos?", default=False
            ):
                self.logger.info("Required permissions: Contents (R), Pull requests (R)")
                readonly_token = self.prompter.prompt(
                    "GitHub Read-Only Token (ghp_...)",
                    validator=lambda t: self._validate_prefix(
                        t, "ghp_", "Token must start with 'ghp_'"
                    ),
                )
                if readonly_token:
                    secrets["GITHUB_READONLY_TOKEN"] = readonly_token

            # Prompt for incognito token (was missing in update mode)
            self._prompt_incognito_token(secrets)

            return secrets

        # Non-update mode: use existing if available
        if has_github_token or has_github_app:
            if has_github_app:
                self.logger.success("Using existing GitHub App configuration")
            else:
                self.logger.success("Using existing GitHub token")

            # Return existing tokens
            if has_github_token:
                secrets["GITHUB_TOKEN"] = self.existing_secrets["GITHUB_TOKEN"]
            if "GITHUB_READONLY_TOKEN" in self.existing_secrets:
                secrets["GITHUB_READONLY_TOKEN"] = self.existing_secrets["GITHUB_READONLY_TOKEN"]
            return secrets

        self.logger.header("GitHub Authentication")
        self.logger.info("Choose authentication method:")
        self.logger.info(
            "  1. GitHub App (recommended for team usage, REQUIRED for PR check status)"
        )
        self.logger.info("  2. Personal Access Token (simpler for personal use)")
        self.logger.info("")
        self.logger.info("Note: GitHub App is required to read PR check run status.")
        self.logger.info("PATs work for most operations but cannot access check runs API.")
        self.logger.info("")

        choice = self.prompter.prompt(
            "Choose authentication method [1/2]",
            default="2",
            validator=lambda c: self._validate_choice(c, ["1", "2"], "Choose 1 or 2"),
        )

        if choice == "1":
            # GitHub App configuration
            self.logger.info("\nGitHub App Configuration")
            self.logger.info("You'll need: App ID, Installation ID, and Private Key")
            self.logger.info("See: docs/setup/github-app-setup.md for setup instructions")
            self.logger.info("")

            app_id = self.prompter.prompt("GitHub App ID", required=True)
            installation_id = self.prompter.prompt("GitHub App Installation ID", required=True)
            private_key_path = self.prompter.prompt("Path to private key file", required=True)

            # Read and store private key
            try:
                private_key_file = Path(private_key_path).expanduser()
                if not private_key_file.exists():
                    self.logger.error(f"Private key file not found: {private_key_path}")
                    return self.prompt_github_auth()  # Retry

                # Create GitHub App config files
                gh_app_id_file = self.config_manager.config_dir / "github-app-id"
                gh_app_installation_file = (
                    self.config_manager.config_dir / "github-app-installation-id"
                )
                gh_app_key_file = self.config_manager.config_dir / "github-app-private-key.pem"

                gh_app_id_file.write_text(app_id)
                gh_app_installation_file.write_text(installation_id)
                gh_app_key_file.write_text(private_key_file.read_text())

                # Secure permissions
                os.chmod(gh_app_id_file, 0o600)
                os.chmod(gh_app_installation_file, 0o600)
                os.chmod(gh_app_key_file, 0o600)

                self.logger.success("GitHub App configuration saved")

            except Exception as e:
                self.logger.error(f"Failed to read private key: {e}")
                return self.prompt_github_auth()  # Retry

        else:
            # Personal Access Token
            self.logger.info("\nPersonal Access Token Configuration")
            self.logger.info("Create a token at: https://github.com/settings/tokens")
            self.logger.info("")
            self.logger.info(
                "For writable repositories, create a token with READ/WRITE permissions:"
            )
            self.logger.info("  Required scopes: repo (full), workflow")
            self.logger.info("")

            token = self.prompter.prompt(
                "GitHub Personal Access Token (ghp_...)",
                required=True,
                validator=lambda t: self._validate_prefix(
                    t, "ghp_", "Token must start with 'ghp_'"
                ),
            )

            secrets["GITHUB_TOKEN"] = token

            # Optionally prompt for read-only token
            self.logger.info("")
            if self.prompter.prompt_yes_no(
                "Do you have a separate read-only token for monitoring external repos?",
                default=False,
            ):
                self.logger.info(
                    "\nFor read-only repositories, create a token with READ-ONLY permissions:"
                )
                self.logger.info("  Required scopes: repo (read-only)")
                self.logger.info("")
                readonly_token = self.prompter.prompt(
                    "GitHub Read-Only Token (ghp_...)",
                    validator=lambda t: self._validate_prefix(
                        t, "ghp_", "Token must start with 'ghp_'"
                    ),
                )
                if readonly_token:
                    secrets["GITHUB_READONLY_TOKEN"] = readonly_token

        # Optionally prompt for incognito token
        self._prompt_incognito_token(secrets)

        return secrets

    def _validate_github_pat(self, token: str) -> None:
        """Validate that a token is a valid GitHub PAT format.

        Raises:
            ValueError: If token doesn't start with ghp_ or github_pat_
        """
        if not token.startswith(("ghp_", "github_pat_")):
            raise ValueError("Token must be a GitHub PAT (ghp_... or github_pat_...)")

    def _prompt_incognito_token(self, secrets: dict[str, str]) -> None:
        """Prompt for incognito token configuration.

        Args:
            secrets: Dictionary to update with GITHUB_INCOGNITO_TOKEN if provided
        """
        # Check for existing incognito token
        existing_incognito_token = self.existing_secrets.get("GITHUB_INCOGNITO_TOKEN", "")

        # In update mode with existing config, ask whether to keep it
        if self.update_mode and existing_incognito_token:
            self.logger.info("")
            self.logger.info(
                f"Current incognito token: {self._mask_secret(existing_incognito_token)}"
            )
            if self.prompter.prompt_yes_no("Keep incognito mode configuration?", default=True):
                # Keep existing, but allow updating the token
                new_token = self.prompter.prompt(
                    "New incognito token (Enter to keep existing)",
                    validator=lambda t: self._validate_github_pat(t) if t else None,
                )
                secrets["GITHUB_INCOGNITO_TOKEN"] = (
                    new_token if new_token else existing_incognito_token
                )
            else:
                # User wants to remove incognito mode - don't add token to secrets
                self.logger.info("Incognito mode will be removed.")
                self._remove_incognito = True
            return

        # Fresh setup or update mode without existing config
        self.logger.info("")
        if self.prompter.prompt_yes_no(
            "Configure incognito mode for contributing to external repos?",
            default=False,
        ):
            self.logger.info("\nIncognito Mode Configuration")
            self.logger.info("Use a Personal Access Token (PAT) from your personal GitHub account.")
            self.logger.info(
                "Operations on incognito repos will be attributed to your personal identity."
            )
            self.logger.info(
                "Create a fine-grained PAT at: https://github.com/settings/tokens?type=beta"
            )
            self.logger.info("  Required permissions: Contents (R/W), Pull requests (R/W)")
            self.logger.info("")

            incognito_token = self.prompter.prompt(
                "GitHub Incognito Token (ghp_... or github_pat_...)",
                required=True,
                validator=lambda t: self._validate_github_pat(t),
            )
            secrets["GITHUB_INCOGNITO_TOKEN"] = incognito_token

    def prompt_incognito_config(self, has_incognito_token: bool) -> dict[str, str | None] | None:
        """Prompt for incognito user identity configuration.

        Args:
            has_incognito_token: Whether an incognito token was configured

        Returns:
            Dict with github_user, git_name, git_email keys (None for unconfigured fields),
            or None if incognito is not configured or being removed.
        """
        # If no token or user is removing incognito, return None
        if not has_incognito_token or self._remove_incognito:
            return None

        # Load existing incognito config
        existing_incognito = self.existing_repos.get("incognito") or {}

        # In update mode with existing config
        if self.update_mode and existing_incognito:
            self.logger.header("Incognito User Identity")
            self.logger.info("Current incognito identity:")
            if existing_incognito.get("github_user"):
                self.logger.info(f"  GitHub user: {existing_incognito['github_user']}")
            if existing_incognito.get("git_name"):
                self.logger.info(f"  Git name: {existing_incognito['git_name']}")
            if existing_incognito.get("git_email"):
                self.logger.info(f"  Git email: {existing_incognito['git_email']}")
            self.logger.info("")

            if not self.prompter.prompt_yes_no("Modify incognito identity?", default=False):
                return existing_incognito

        # Fresh setup or user wants to modify
        self.logger.header("Incognito User Identity")
        self.logger.info("Configure the identity to use for incognito mode operations.")
        self.logger.info("")

        github_user = self.prompter.prompt(
            "GitHub username (for attribution)",
            default=existing_incognito.get("github_user", ""),
            required=True,
        )

        git_name = self.prompter.prompt(
            "Git author name (for commits)",
            default=existing_incognito.get("git_name", github_user),
        )

        git_email = self.prompter.prompt(
            "Git author email",
            default=existing_incognito.get("git_email", ""),
        )

        return {
            "github_user": github_user,
            "git_name": git_name if git_name else None,
            "git_email": git_email if git_email else None,
        }

    def prompt_incognito_repos(
        self, writable_repos: list[str], has_incognito_token: bool
    ) -> dict[str, dict]:
        """Prompt for which repos should use incognito mode.

        Args:
            writable_repos: List of writable repository names
            has_incognito_token: Whether an incognito token was configured

        Returns:
            Dict mapping repo names to their settings (e.g., auth_mode: incognito)
        """
        # If no token or removing incognito, return empty settings
        if not has_incognito_token or self._remove_incognito:
            return {}

        # Load existing repo settings
        existing_settings = self.existing_repos.get("repo_settings") or {}

        # Get list of repos currently set to incognito
        existing_incognito_repos = [
            repo
            for repo, settings in existing_settings.items()
            if settings.get("auth_mode") == "incognito"
        ]

        # In update mode with existing config
        if self.update_mode and existing_incognito_repos:
            self.logger.header("Incognito Repositories")
            self.logger.info("Current repos using incognito mode:")
            for repo in existing_incognito_repos:
                self.logger.info(f"  - {repo}")
            self.logger.info("")

            if not self.prompter.prompt_yes_no("Modify incognito repo selection?", default=False):
                return existing_settings

        # Show available repos and prompt for selection
        self.logger.header("Incognito Repositories")
        self.logger.info("Select which writable repos should use incognito mode.")
        self.logger.info("These repos will use your personal identity instead of the bot.")
        self.logger.info("")

        if not writable_repos:
            self.logger.info("No writable repositories configured.")
            return {}

        self.logger.info("Available writable repositories:")
        for i, repo in enumerate(writable_repos, 1):
            marker = "[*]" if repo in existing_incognito_repos else "[ ]"
            self.logger.info(f"  {i}. {marker} {repo}")
        self.logger.info("")
        self.logger.info(
            "Enter repo numbers to toggle incognito (comma-separated), or Enter to skip:"
        )
        self.logger.info("Example: 1,3 to select repos 1 and 3")

        selection = self.prompter.prompt("Selection")
        if not selection:
            # Keep existing if in update mode, empty otherwise
            return existing_settings if self.update_mode else {}

        # Parse selection
        selected_repos = set()
        try:
            for part in selection.split(","):
                idx = int(part.strip()) - 1
                if 0 <= idx < len(writable_repos):
                    selected_repos.add(writable_repos[idx])
        except ValueError:
            self.logger.warning("Invalid selection, keeping existing configuration")
            return existing_settings if self.update_mode else {}

        # Build repo_settings
        repo_settings = {}
        for repo in selected_repos:
            repo_settings[repo] = {"auth_mode": "incognito"}

        # Preserve other settings from existing repos (non-auth_mode settings)
        for repo, settings in existing_settings.items():
            if repo not in repo_settings:
                # Check if there are non-auth_mode settings to preserve
                other_settings = {k: v for k, v in settings.items() if k != "auth_mode"}
                if other_settings:
                    repo_settings[repo] = other_settings
            else:
                # Merge other settings with incognito
                other_settings = {k: v for k, v in settings.items() if k != "auth_mode"}
                repo_settings[repo].update(other_settings)

        return repo_settings

    def prompt_repositories(self, github_username: str) -> tuple[list[str], list[str]]:
        """Prompt for repository configuration."""
        self.logger.header("Repository Configuration")

        # Load existing repos
        existing_writable = self.existing_repos.get("writable_repos", [])
        existing_readable = self.existing_repos.get("readable_repos", [])

        # In update mode, show existing and allow modification
        if self.update_mode and (existing_writable or existing_readable):
            self.logger.info("Current writable repositories:")
            for repo in existing_writable:
                self.logger.info(f"  - {repo}")
            if existing_readable:
                self.logger.info("\nCurrent read-only repositories:")
                for repo in existing_readable:
                    self.logger.info(f"  - {repo}")
            self.logger.info("")

            if not self.prompter.prompt_yes_no("Modify repository configuration?", default=False):
                return existing_writable, existing_readable

            # Allow full reconfiguration
            self.logger.info("\nReconfiguring repositories...")
            self.logger.info("Enter writable repositories one per line (empty line to finish):")
            self.logger.info(f"(Press Enter with no input to keep: {', '.join(existing_writable)})")

            writable_repos = []
            first_input = self.prompter.prompt("Repository (owner/name)")
            if not first_input:
                # Keep existing
                writable_repos = existing_writable
            else:
                writable_repos.append(first_input)
                while True:
                    repo = self.prompter.prompt("Repository (owner/name)")
                    if not repo:
                        break
                    writable_repos.append(repo)

            self.logger.info("\nEnter read-only repositories one per line (empty line to finish):")
            if existing_readable:
                self.logger.info(
                    f"(Press Enter with no input to keep: {', '.join(existing_readable)})"
                )

            readable_repos = []
            first_input = self.prompter.prompt("Repository (owner/name)")
            if not first_input and existing_readable:
                readable_repos = existing_readable
            elif first_input:
                readable_repos.append(first_input)
                while True:
                    repo = self.prompter.prompt("Repository (owner/name)")
                    if not repo:
                        break
                    readable_repos.append(repo)

            return writable_repos, readable_repos

        # Non-update mode: standard flow
        default_writable = f"{github_username}/james-in-a-box"
        self.logger.info(f"Default writable repo: {default_writable}")
        self.logger.info("")

        writable_repos = [default_writable]

        if self.prompter.prompt_yes_no("Add more writable repositories?", default=False):
            self.logger.info("Enter repositories one per line (empty line to finish):")
            while True:
                repo = self.prompter.prompt("Repository (owner/name)")
                if not repo:
                    break
                writable_repos.append(repo)

        readable_repos = []
        if self.prompter.prompt_yes_no("Add read-only repositories to monitor?", default=False):
            self.logger.info("Enter repositories one per line (empty line to finish):")
            while True:
                repo = self.prompter.prompt("Repository (owner/name)")
                if not repo:
                    break
                readable_repos.append(repo)

        return writable_repos, readable_repos

    def prompt_local_repos(self) -> list[str]:
        """Prompt for local repository paths to mount into the container."""
        self.logger.header("Local Repository Configuration")

        # Load existing local repos
        existing_local = self.existing_repos.get("local_repos", {})
        existing_paths = existing_local.get("paths", []) if isinstance(existing_local, dict) else []

        # In update mode, show existing and allow modification
        if self.update_mode and existing_paths:
            self.logger.info("Current local repositories:")
            for path in existing_paths:
                self.logger.info(f"  - {path}")
            self.logger.info("")

            if not self.prompter.prompt_yes_no("Modify local repository paths?", default=False):
                return existing_paths

            # Allow full reconfiguration
            self.logger.info("\nReconfiguring local repositories...")
            self.logger.info("Enter local repo paths one per line (empty line to finish):")
            self.logger.info("(Press Enter with no input to keep existing paths)")

            local_repos = []
            first_input = self.prompter.prompt("Local repo path (absolute)")
            if not first_input:
                # Keep existing
                return existing_paths
            else:
                expanded = str(Path(first_input).expanduser().resolve())
                if Path(expanded).exists():
                    local_repos.append(expanded)
                else:
                    self.logger.warning(f"Path does not exist: {expanded}")

                while True:
                    repo_path = self.prompter.prompt("Local repo path (absolute)")
                    if not repo_path:
                        break
                    expanded = str(Path(repo_path).expanduser().resolve())
                    if Path(expanded).exists():
                        local_repos.append(expanded)
                    else:
                        self.logger.warning(f"Path does not exist: {expanded}")

            return local_repos

        # Non-update mode: standard flow
        self.logger.info("Configure local repositories that jib will have access to.")
        self.logger.info("These paths will be volume-mounted into the container and")
        self.logger.info("git worktrees will be created for isolated development.")
        self.logger.info("")
        self.logger.info("Example paths:")
        self.logger.info("  ~/projects/my-app")
        self.logger.info("  /home/user/work/repo")
        self.logger.info("")

        local_repos = []
        if self.prompter.prompt_yes_no("Add local repositories?", default=True):
            self.logger.info("Enter local repo paths one per line (empty line to finish):")
            while True:
                repo_path = self.prompter.prompt("Local repo path (absolute)")
                if not repo_path:
                    break
                expanded = str(Path(repo_path).expanduser().resolve())
                if Path(expanded).exists():
                    local_repos.append(expanded)
                    self.logger.success(f"Added: {expanded}")
                else:
                    self.logger.warning(f"Path does not exist: {expanded}")
                    if self.prompter.prompt_yes_no("Add anyway?", default=False):
                        local_repos.append(expanded)

        return local_repos

    def get_slack_channel_id(self) -> str:
        """Try to get the user's Slack DM channel ID."""
        existing = self.existing_config.get("slack_channel", "")

        # In update mode, show existing and allow modification
        if self.update_mode and existing:
            return (
                self.prompter.prompt(
                    "Slack channel ID (starts with D, C, or G)",
                    default=existing,
                    validator=lambda c: self._validate_first_char(
                        c,
                        ["D", "C", "G"],
                        "Channel ID must start with D, C, or G",
                        allow_empty=True,
                    ),
                )
                or existing
            )

        self.logger.info("\nFinding your Slack DM channel...")
        self.logger.info("You can find your channel ID by:")
        self.logger.info("  1. Open Slack")
        self.logger.info("  2. Click on your DM with the bot")
        self.logger.info("  3. Look at the URL: /client/T.../D... <- that D... is your channel ID")
        self.logger.info("")

        channel_id = self.prompter.prompt(
            "Slack channel ID (starts with D, C, or G)",
            validator=lambda c: self._validate_first_char(
                c, ["D", "C", "G"], "Channel ID must start with D, C, or G"
            ),
        )

        return channel_id if channel_id else ""

    def get_slack_user_id(self) -> str:
        """Prompt for Slack user ID."""
        existing_users = self.existing_config.get("allowed_users", [])
        existing = existing_users[0] if existing_users else ""

        # In update mode, show existing and allow modification
        if self.update_mode and existing:
            return (
                self.prompter.prompt(
                    "Your Slack user ID (starts with U)",
                    default=existing,
                    validator=lambda u: self._validate_prefix(
                        u, "U", "User ID must start with U", allow_empty=True
                    ),
                )
                or existing
            )

        self.logger.info("\nYour Slack User ID is needed for access control.")
        self.logger.info("Find it at: Slack -> Profile -> More -> Copy member ID")
        self.logger.info("")

        user_id = self.prompter.prompt(
            "Your Slack user ID (starts with U)",
            validator=lambda u: self._validate_prefix(u, "U", "User ID must start with U"),
        )

        return user_id if user_id else ""

    def prompt_anthropic_auth(self) -> str:
        """Prompt for Anthropic authentication method.

        Returns:
            'api_key' or 'oauth'
        """
        existing = self.existing_config.get("anthropic_auth_method", "api_key")

        self.logger.header("Anthropic Authentication")
        self.logger.info("Choose how to authenticate with Claude/Anthropic:")
        self.logger.info("  1. API Key - Use ANTHROPIC_API_KEY environment variable")
        self.logger.info("  2. OAuth - Use Claude Max/Pro subscription (browser login)")
        self.logger.info("")

        # In update mode, show existing and allow modification
        if self.update_mode:
            choice = self.prompter.prompt(
                "Auth method (api_key/oauth)",
                default=existing,
                validator=lambda v: self._validate_choice(
                    v, ["api_key", "oauth"], "Must be 'api_key' or 'oauth'", case_insensitive=True
                ),
            )
            return choice.lower() if choice else existing

        # Check if API key is already set
        has_api_key = bool(self.existing_secrets.get("ANTHROPIC_API_KEY"))
        if has_api_key:
            self.logger.success("Anthropic API key found in secrets")
            if not self.prompter.prompt_yes_no("Use API key authentication?", default=True):
                return "oauth"
            return "api_key"

        # No API key - offer choice
        choice = self.prompter.prompt(
            "Auth method (api_key/oauth)",
            default="oauth",
            validator=lambda v: self._validate_choice(
                v, ["api_key", "oauth"], "Must be 'api_key' or 'oauth'", case_insensitive=True
            ),
        )
        return choice.lower() if choice else "oauth"

    def prompt_network_mode(self) -> str:
        """Prompt for network mode configuration.

        Network modes control network access and repository visibility:
        - default: Network lockdown, all repos accessible (private + public)
        - allow-all: All network traffic allowed, PUBLIC repos only
        - private-only: Network lockdown, PRIVATE repos only

        Returns:
            'default', 'allow-all', or 'private-only'
        """
        # Read existing mode from file
        network_mode_file = self.config_manager.config_dir / "network-mode"
        existing = "default"
        if network_mode_file.exists():
            try:
                existing = network_mode_file.read_text().strip()
                if existing not in ("default", "allow-all", "private-only"):
                    existing = "default"
            except OSError:
                pass

        self.logger.header("Network Mode")
        self.logger.info("Choose how jib handles network access and repository visibility:")
        self.logger.info("")
        self.logger.info("  default      - Network lockdown, all repos accessible")
        self.logger.info("                 (Most common: work on any repo, no web access)")
        self.logger.info("")
        self.logger.info("  allow-all    - Allow all network traffic, PUBLIC repos only")
        self.logger.info(
            "                 (For open source: web search enabled, private repos blocked)"
        )
        self.logger.info("")
        self.logger.info("  private-only - Network lockdown, PRIVATE repos only")
        self.logger.info("                 (Extra security: public repos blocked)")
        self.logger.info("")

        choice = self.prompter.prompt(
            "Network mode (default/allow-all/private-only)",
            default=existing,
            validator=lambda v: self._validate_choice(
                v,
                ["default", "allow-all", "private-only"],
                "Must be 'default', 'allow-all', or 'private-only'",
                case_insensitive=True,
            ),
        )
        return choice.lower() if choice else existing

    def _write_network_mode(self, mode: str) -> None:
        """Write network mode to config file.

        Args:
            mode: Network mode ('default', 'allow-all', or 'private-only')
        """
        # Write mode file
        network_mode_file = self.config_manager.config_dir / "network-mode"
        network_mode_file.write_text(mode)

        # Write env file for gateway
        network_env_file = self.config_manager.config_dir / "network.env"
        if mode == "allow-all":
            env_vars = {
                "ALLOW_ALL_NETWORK": "true",
                "PRIVATE_REPO_MODE": "false",
            }
        elif mode == "private-only":
            env_vars = {
                "ALLOW_ALL_NETWORK": "false",
                "PRIVATE_REPO_MODE": "true",
            }
        else:
            env_vars = {
                "ALLOW_ALL_NETWORK": "false",
                "PRIVATE_REPO_MODE": "false",
            }

        lines = [f"# Auto-generated by setup.py - network mode: {mode}"]
        for key, value in env_vars.items():
            lines.append(f"{key}={value}")
        network_env_file.write_text("\n".join(lines) + "\n")

    def run(self) -> bool:
        """Run the minimal setup flow.

        Returns:
            True if setup completed successfully, False otherwise.
        """
        if self.update_mode:
            self.logger.header("jib Configuration Update")
            self.logger.info("Update your configuration. Press Enter to keep existing values.")
            self.logger.info("")
        else:
            self.logger.header("jib Setup")
            self.logger.info("This will configure the essential settings to get jib running.")
            self.logger.info("")

        # Check if already configured (skip in update mode)
        if not self.update_mode and self.is_already_configured():
            self.logger.success("\n✓ Configuration already exists!")
            self.logger.info("")
            self.logger.info("All essential settings are already configured:")
            self.logger.info(f"  - GitHub username: {self.existing_config.get('github_username')}")
            self.logger.info(
                f"  - Bot name: {self.existing_config.get('bot_name', 'james-in-a-box')}"
            )
            self.logger.info("  - Slack tokens: ✓")
            self.logger.info("  - GitHub authentication: ✓")
            self.logger.info("")
            self.logger.info("To update configuration, run: ./setup.py --update")
            self.logger.info("")
            return True

        try:
            # 1. GitHub username
            github_username = self.prompt_github_username()

            # 2. Bot name
            bot_name = self.prompt_bot_name()

            # 3. Slack tokens
            slack_secrets = self.prompt_slack_tokens()

            # 4. Slack channel and user
            slack_channel = self.get_slack_channel_id()
            slack_user = self.get_slack_user_id()

            # 5. GitHub authentication (includes incognito token prompt)
            github_secrets = self.prompt_github_auth()

            # 6. Incognito user identity (if token was configured)
            has_incognito_token = "GITHUB_INCOGNITO_TOKEN" in github_secrets
            incognito_config = self.prompt_incognito_config(has_incognito_token)

            # 7. Repositories
            writable_repos, readable_repos = self.prompt_repositories(github_username)

            # 8. Incognito repo selection (if token was configured)
            repo_settings = self.prompt_incognito_repos(writable_repos, has_incognito_token)

            # 9. Local repositories (for volume mounts)
            local_repos = self.prompt_local_repos()

            # 10. Anthropic authentication method
            anthropic_auth_method = self.prompt_anthropic_auth()

            # 11. Network mode
            network_mode = self.prompt_network_mode()

            # Save configuration
            self.logger.header("Saving Configuration")

            # Combine all secrets, preserving existing ones not prompted for
            # (e.g., Confluence, JIRA, LLM API keys)
            all_secrets = {**self.existing_secrets, **slack_secrets, **github_secrets}

            # If removing incognito, ensure token is removed from secrets
            if self._remove_incognito and "GITHUB_INCOGNITO_TOKEN" in all_secrets:
                del all_secrets["GITHUB_INCOGNITO_TOKEN"]

            self.config_manager.write_secrets(all_secrets)

            # Write main config using new nested structure
            # (compatible with jib_config classes from PR #523)
            config = {
                "bot_name": bot_name,
                "github_username": github_username,
                # Anthropic auth method: 'api_key' or 'oauth'
                "anthropic_auth_method": anthropic_auth_method,
                # New nested slack section for SlackConfig.from_env()
                "slack": {
                    "channel": slack_channel,
                    "allowed_users": [slack_user] if slack_user else [],
                },
                # Legacy top-level keys for backward compatibility
                "slack_channel": slack_channel,
                "allowed_users": [slack_user] if slack_user else [],
                "context_sync_interval": 30,
                "github_sync_interval": 5,
            }
            self.config_manager.write_config(config)

            # Write repository config (with incognito settings if configured)
            self.config_manager.write_repositories(
                writable_repos,
                readable_repos,
                github_username,
                local_repos,
                incognito=incognito_config,
                repo_settings=repo_settings if repo_settings else None,
            )

            # Write network mode
            self._write_network_mode(network_mode)

            if self.update_mode:
                self.logger.success("\n✓ Configuration updated!")
            else:
                self.logger.success("\n✓ Minimal setup complete!")
            self.logger.info("")
            self.logger.info("Configuration saved to:")
            self.logger.info(f"  - {self.config_manager.secrets_file}")
            self.logger.info(f"  - {self.config_manager.config_file}")
            self.logger.info(f"  - {self.config_manager.repos_file}")
            self.logger.info(f"  - {self.config_manager.config_dir / 'network-mode'}")
            self.logger.info("")
            self.logger.info("Next steps:")
            self.logger.info("  1. Review the configuration files")
            self.logger.info("  2. Run './setup.py --enable-services' to start jib services")
            self.logger.info("  3. Run 'jib' to start using the container")

            return True

        except KeyboardInterrupt:
            self.logger.warning("\n\nSetup cancelled by user")
            return False
        except Exception as e:
            self.logger.error(f"\n\nSetup failed: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return False


def main():
    """Main setup entry point."""
    args = parse_args()
    logger = SetupLogger(verbose=args.verbose)

    # Print banner
    logger.header("🤖 jib Setup - Declarative Setup Architecture")

    # Handle service-only operations (no setup required)
    if (
        args.enable_services
        or args.enable_core_services
        or args.disable_services
        or args.enable
        or args.disable
        or args.status
    ):
        service_manager = ServiceManager(logger)

        if args.enable_services:
            sys.exit(0 if service_manager.enable_all_services() else 1)
        elif args.enable_core_services:
            sys.exit(0 if service_manager.enable_core_services() else 1)
        elif args.disable_services:
            sys.exit(0 if service_manager.disable_all_services() else 1)
        elif args.enable:
            sys.exit(0 if service_manager.enable_service(args.enable) else 1)
        elif args.disable:
            sys.exit(0 if service_manager.disable_service(args.disable) else 1)
        elif args.status:
            service_manager.print_service_status()
            sys.exit(0)

    # Check dependencies (unless skipped)
    if not args.skip_deps:
        dep_checker = DependencyChecker(logger)
        if not dep_checker.check_all():
            sys.exit(1)

    # Initialize managers
    config_manager = ConfigManager(logger)
    config_manager.ensure_config_dir()
    prompter = UserPrompter(logger)

    # Run configuration migration if needed
    migrator = ConfigMigrator(logger)
    if not migrator.migrate_configs():
        logger.error("Configuration migration failed")
        sys.exit(1)

    # Run appropriate setup flow
    if args.update:
        # Update mode: prompt for all settings with existing values as defaults
        logger.info("Running configuration update")
        minimal_setup = MinimalSetup(
            logger, config_manager, prompter, verbose=args.verbose, update_mode=True
        )
        if not minimal_setup.run():
            sys.exit(1)

        # Restart services after update
        logger.header("Restarting Services")
        service_manager = ServiceManager(logger)
        service_manager._daemon_reload()
        logger.success("Configuration updated. Services will use new config on next run.")
        logger.info("")
        logger.info("To restart services now:")
        logger.info("  systemctl --user restart slack-notifier slack-receiver")
        success = True
    else:
        # Default: Full setup mode (includes minimal setup + Docker + beads + optional components)
        logger.info("Running setup (all components)")

        # First run minimal setup to get config
        minimal_setup = MinimalSetup(logger, config_manager, prompter, verbose=args.verbose)
        if not minimal_setup.run():
            sys.exit(1)

        # Then run full setup for additional components
        full_setup = FullSetup(logger, config_manager, prompter, verbose=args.verbose)
        success = full_setup.run()

    if success:
        # Run configuration validation to verify secrets are valid
        logger.info("\n" + "=" * 60)
        logger.info("Validating configuration...")
        logger.info("=" * 60)

        validate_script = Path(__file__).parent / "scripts" / "validate-config.py"
        if validate_script.exists():
            result = subprocess.run(
                [sys.executable, str(validate_script)],
                capture_output=False,
                check=False,
            )
            if result.returncode != 0:
                logger.warning("Configuration validation found issues (see above)")
                logger.info(
                    "Run './scripts/validate-config.py --health' for API connectivity tests"
                )
        else:
            logger.warning(f"Validation script not found: {validate_script}")

        logger.info("\n" + "=" * 60)
        logger.success("Setup completed successfully!")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
