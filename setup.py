#!/usr/bin/env python3
"""
jib Setup Script - Declarative Setup Architecture

This script replaces setup.sh with a Python-based setup system.
It consolidates all configuration into:
  - ~/.config/jib/secrets.env  (secrets)
  - ~/.config/jib/config.yaml  (non-secret settings)

Usage:
  ./setup.py                    # Minimal setup (default)
  ./setup.py --full             # Full setup with optional components
  ./setup.py --enable-services  # Enable all systemd services
  ./setup.py --disable-services # Disable all systemd services
  ./setup.py --enable SERVICE   # Enable specific service
  ./setup.py --disable SERVICE  # Disable specific service
  ./setup.py --update           # Update configs and restart services
  ./setup.py --force            # Force reinstall

For more information, see docs/adr/not-implemented/ADR-Declarative-Setup-Architecture.md
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# Add config directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config.host_config import HostConfig

# ANSI color codes for terminal output
class Colors:
    """Terminal color codes for formatted output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    @staticmethod
    def strip_if_no_tty(text: str) -> str:
        """Strip ANSI codes if not outputting to a TTY."""
        if not sys.stdout.isatty():
            import re
            return re.sub(r'\033\[[0-9;]+m', '', text)
        return text


class SetupLogger:
    """Handles formatted logging for the setup process."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        logging.basicConfig(
            level=logging.DEBUG if verbose else logging.INFO,
            format='%(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def info(self, msg: str):
        """Print info message."""
        colored = f"{Colors.OKBLUE}ℹ{Colors.ENDC} {msg}"
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
        else:
            if required:
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

        # Python-specific checks
        try:
            import yaml  # noqa: F401
            self.logger.success("PyYAML is installed")
        except ImportError:
            self.logger.warning("PyYAML is NOT installed (will use JSON fallback)")

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
        default: Optional[str] = None,
        required: bool = False,
        validator: Optional[callable] = None
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

            response = input(Colors.strip_if_no_tty(f"{Colors.OKCYAN}?{Colors.ENDC} {prompt_text}")).strip()

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
        response = input(Colors.strip_if_no_tty(
            f"{Colors.OKCYAN}?{Colors.ENDC} {question} [{default_str}]: "
        )).strip().lower()

        if not response:
            return default

        return response in ['y', 'yes']

    def prompt_list(self, question: str, delimiter: str = ",") -> list[str]:
        """Prompt for a comma-separated list.

        Args:
            question: The question to ask
            delimiter: Character to split on (default: comma)

        Returns:
            List of stripped, non-empty strings
        """
        response = input(Colors.strip_if_no_tty(
            f"{Colors.OKCYAN}?{Colors.ENDC} {question}: "
        )).strip()

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
        for name, path in self.legacy_locations.items():
            if path.exists():
                return True

        # Check for legacy service configs
        if self.legacy_notifier_config.exists():
            return True
        if self.legacy_context_sync_env.exists():
            return True

        return False

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
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        secrets[key.strip()] = value.strip().strip('"\'')

        # Load existing config if any
        if self.new_config_file.exists():
            try:
                import yaml
                with open(self.new_config_file) as f:
                    config = yaml.safe_load(f) or {}
            except ImportError:
                import json
                config_json = self.new_config_dir / "config.json"
                if config_json.exists():
                    with open(config_json) as f:
                        config = json.load(f)

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
                try:
                    import yaml
                    self.new_config_file.write_text(yaml.dump(config, default_flow_style=False))
                    self.logger.success(f"Config written to {self.new_config_file}")
                except ImportError:
                    import json
                    config_json = self.new_config_dir / "config.json"
                    config_json.write_text(json.dumps(config, indent=2))
                    self.logger.success(f"Config written to {config_json}")

            self.logger.success("\n✓ Configuration migration complete")
            self.logger.info("")
            self.logger.info("Legacy files have been migrated to:")
            self.logger.info(f"  {self.new_secrets_file}")
            self.logger.info(f"  {self.new_config_file}")
            self.logger.info("")
            self.logger.warning("IMPORTANT: The legacy files still exist for backward compatibility.")
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
            "GitHub": ["GITHUB_TOKEN", "GITHUB_READONLY_TOKEN"],
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
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        secrets[key.strip()] = value.strip().strip('"\'')
        return secrets

    def load_config(self) -> dict[str, Any]:
        """Load config from config.yaml.

        Returns:
            Dictionary of configuration values
        """
        if self.config_file.exists():
            try:
                import yaml
                with open(self.config_file) as f:
                    return yaml.safe_load(f) or {}
            except ImportError:
                # Fallback to JSON
                import json
                config_json = self.config_dir / "config.json"
                if config_json.exists():
                    with open(config_json) as f:
                        return json.load(f)
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
        try:
            import yaml
            self.config_file.write_text(yaml.dump(config, default_flow_style=False))
            self.logger.success(f"Config written to {self.config_file}")
        except ImportError:
            # Fallback to JSON
            import json
            config_json = self.config_dir / "config.json"
            config_json.write_text(json.dumps(config, indent=2))
            self.logger.warning(f"PyYAML not available, wrote JSON to {config_json}")

    def write_repositories(self, writable: list[str], readable: list[str]):
        """Write repository configuration.

        Args:
            writable: List of repositories with write access
            readable: List of repositories with read-only access
        """
        try:
            import yaml
            repos_config = {
                "writable_repos": writable,
                "readable_repos": readable,
            }
            self.repos_file.write_text(yaml.dump(repos_config, default_flow_style=False))
            self.logger.success(f"Repository config written to {self.repos_file}")
        except ImportError:
            self.logger.warning("PyYAML not available, skipping repositories.yaml")


class ServiceManager:
    """Manages systemd services."""

    # Core services that should always be enabled (non-LLM)
    CORE_SERVICES = [
        "slack-notifier.service",
        "slack-receiver.service",
        "github-token-refresher.service",
        "worktree-watcher.timer",
    ]

    # LLM-based services that use tokens (opt-in)
    LLM_SERVICES = [
        "context-sync.timer",
        "github-watcher.timer",
        "beads-analyzer.timer",
        "jib-doc-generator.timer",
        "adr-researcher.timer",
    ]

    # Mapping of service names to their setup script paths
    SERVICE_SETUP_SCRIPTS = {
        "slack-notifier.service": "host-services/slack/slack-notifier/setup.sh",
        "slack-receiver.service": "host-services/slack/slack-receiver/setup.sh",
        "github-token-refresher.service": "host-services/utilities/github-token-refresher/setup.sh",
        "worktree-watcher.timer": "host-services/utilities/worktree-watcher/setup.sh",
        "context-sync.timer": "host-services/sync/context-sync/setup.sh",
        "github-watcher.timer": "host-services/analysis/github-watcher/setup.sh",
        "beads-analyzer.timer": "host-services/analysis/beads-analyzer/setup.sh",
        "jib-doc-generator.timer": "host-services/analysis/doc-generator/setup.sh",
        "adr-researcher.timer": "host-services/analysis/adr-researcher/setup.sh",
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
                ["systemctl", "--user", "daemon-reload"],
                check=True,
                capture_output=True,
                text=True
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
        setup_script = self.SERVICE_SETUP_SCRIPTS.get(service)
        if not setup_script:
            # No setup script defined, that's okay
            return True

        script_path = self.repo_root / setup_script
        if not script_path.exists():
            self.logger.warning(f"Setup script not found: {setup_script}")
            return True  # Don't fail if script is missing

        try:
            self.logger.step(f"Running setup script for {service}")
            result = subprocess.run(
                ["bash", str(script_path)],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=60
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
        if not self.has_systemctl:
            self.logger.warning("systemctl not available, skipping service management")
            return False

        # Run setup script if requested
        if run_setup:
            if not self._run_service_setup(service):
                self.logger.warning(f"Setup script failed for {service}, continuing anyway")

        # Reload daemon to pick up any service file changes
        self._daemon_reload()

        try:
            subprocess.run(
                ["systemctl", "--user", "enable", service],
                check=True,
                capture_output=True,
                text=True
            )
            subprocess.run(
                ["systemctl", "--user", "start", service],
                check=True,
                capture_output=True,
                text=True
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
        if not self.has_systemctl:
            self.logger.warning("systemctl not available, skipping service management")
            return False

        try:
            subprocess.run(
                ["systemctl", "--user", "stop", service],
                check=True,
                capture_output=True,
                text=True
            )
            subprocess.run(
                ["systemctl", "--user", "disable", service],
                check=True,
                capture_output=True,
                text=True
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
                    capture_output=True,
                    text=True
                )
                active = active_result.stdout.strip()
            except subprocess.CalledProcessError:
                active = "unknown"

            # Check if enabled
            enabled_result = subprocess.run(
                ["systemctl", "--user", "is-enabled", service],
                capture_output=True,
                text=True
            )
            enabled = enabled_result.stdout.strip() if enabled_result.returncode == 0 else "disabled"

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

            status_line = f"  {active_color}{active_indicator}{Colors.ENDC} {service:<40} {enabled_str:>10}"
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

            status_line = f"  {active_color}{active_indicator}{Colors.ENDC} {service:<40} {enabled_str:>10}"
            print(Colors.strip_if_no_tty(status_line))

        self.logger.info("")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="jib setup script - Declarative setup architecture",
        epilog="For more information, see docs/adr/not-implemented/ADR-Declarative-Setup-Architecture.md"
    )

    # Setup modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Full setup including optional components (default: minimal setup)"
    )
    mode_group.add_argument(
        "--update",
        action="store_true",
        help="Update mode: reload configs and restart services"
    )

    # Service management
    service_group = parser.add_mutually_exclusive_group()
    service_group.add_argument(
        "--enable-services",
        action="store_true",
        help="Enable all jib systemd services (core + LLM)"
    )
    service_group.add_argument(
        "--enable-core-services",
        action="store_true",
        help="Enable only core services (non-LLM)"
    )
    service_group.add_argument(
        "--disable-services",
        action="store_true",
        help="Disable all jib systemd services"
    )
    service_group.add_argument(
        "--enable",
        metavar="SERVICE",
        help="Enable a specific service"
    )
    service_group.add_argument(
        "--disable",
        metavar="SERVICE",
        help="Disable a specific service"
    )
    service_group.add_argument(
        "--status",
        action="store_true",
        help="Show status of all services"
    )

    # Other options
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reinstall (overwrite existing configs)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip dependency checks"
    )

    return parser.parse_args()


class FullSetup:
    """Handles the full setup flow including Docker, beads, and optional components."""

    def __init__(self, logger: SetupLogger, config_manager: ConfigManager, prompter: UserPrompter, verbose: bool = False):
        self.logger = logger
        self.config_manager = config_manager
        self.prompter = prompter
        self.verbose = verbose
        self.repo_root = Path(__file__).parent
        self.shared_dir = Path.home() / ".jib-sharing"
        self.beads_dir = self.shared_dir / "beads"

    def build_docker_image(self) -> bool:
        """Build the jib Docker image.

        Returns:
            True if build succeeded or image already exists, False on error
        """
        self.logger.header("Building Docker Image")

        # Check if image already exists
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", "james-in-a-box"],
                capture_output=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            image_exists = result.returncode == 0
        except FileNotFoundError:
            self.logger.error("Docker is not installed")
            return False

        if image_exists:
            self.logger.success("Docker image 'james-in-a-box' already exists")
            if not self.prompter.prompt_yes_no("Rebuild the image?", default=False):
                self.logger.info("Skipping image rebuild")
                return True

        # Build the image
        self.logger.info("Building Docker image (this may take a few minutes)...")
        self.logger.info("")

        try:
            # Use bin/jib --setup to build the image
            jib_script = self.repo_root / "bin" / "jib"
            if not jib_script.exists():
                self.logger.error(f"jib script not found at {jib_script}")
                return False

            # Run jib --setup with auto-yes
            process = subprocess.Popen(
                [str(jib_script), "--setup"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.repo_root
            )

            # Send 'yes' to any prompts and show output
            stdout, _ = process.communicate(input="yes\n")

            if self.verbose:
                print(stdout)

            if process.returncode == 0:
                self.logger.success("Docker image built successfully")
                return True
            else:
                self.logger.error("Docker image build failed")
                self.logger.error("You can rebuild later with: bin/jib --setup")
                return False

        except Exception as e:
            self.logger.error(f"Failed to build Docker image: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return False

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

            if not self.prompter.prompt_yes_no("Continue without beads?", default=True):
                return False
            return True

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
                ["git", "init"],
                cwd=self.beads_dir,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                self.logger.error(f"Failed to initialize git: {result.stderr}")
                return False

            # Initialize beads
            self.logger.step("Initializing beads...")
            result = subprocess.run(
                ["bd", "init"],
                cwd=self.beads_dir,
                input="n\n",  # Say no to git hooks
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                self.logger.error(f"Failed to initialize beads: {result.stderr}")
                return False

            self.logger.success(f"Beads initialized: {self.beads_dir}")
            self.logger.info("Usage in container: bd --allow-stale create 'task description' --labels feature")
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
        config = self.config_manager.load_config()
        secrets = self.config_manager.load_secrets()

        has_confluence = bool(secrets.get("CONFLUENCE_BASE_URL") and secrets.get("CONFLUENCE_API_TOKEN"))
        has_jira = bool(secrets.get("JIRA_BASE_URL") and secrets.get("JIRA_API_TOKEN"))

        if has_confluence:
            self.logger.success("Confluence configuration found")
        if has_jira:
            self.logger.success("JIRA configuration found")

        if not has_confluence and not has_jira:
            self.logger.info("No Confluence or JIRA configuration found")
            if self.prompter.prompt_yes_no("Configure Confluence/JIRA sync now?", default=False):
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
            base_url = self.prompter.prompt("Confluence Base URL (e.g., https://company.atlassian.net/wiki)")
            username = self.prompter.prompt("Confluence Username/Email")
            api_token = self.prompter.prompt("Confluence API Token", required=True)
            space_keys = self.prompter.prompt("Space Keys (comma-separated, e.g., ENG,TEAM)", required=False)

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
                "JQL Query (e.g., project = ENG AND status != Done)",
                default="status != Done"
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
        self.logger.header("Phase 4: Full Setup Mode")
        self.logger.info("This will set up all components including Docker, beads, and optional features.")
        self.logger.info("")

        try:
            # 1. Create shared directories
            if not self.create_shared_directories():
                self.logger.error("Failed to create shared directories")
                return False

            # 2. Build Docker image
            if not self.build_docker_image():
                self.logger.warning("Docker image build failed, but continuing...")

            # 3. Initialize beads
            if not self.initialize_beads():
                self.logger.warning("Beads initialization failed, but continuing...")

            # 4. Validate context sync
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

    def __init__(self, logger: SetupLogger, config_manager: ConfigManager, prompter: UserPrompter, verbose: bool = False):
        self.logger = logger
        self.config_manager = config_manager
        self.prompter = prompter
        self.verbose = verbose

        # Load existing configuration
        self.existing_secrets = self.config_manager.load_secrets()
        self.existing_config = self.config_manager.load_config()

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
        if not self.existing_config.get("github_username"):
            return False

        return True

    def detect_github_username(self) -> Optional[str]:
        """Try to detect GitHub username from gh CLI."""
        try:
            result = subprocess.run(
                ["gh", "api", "user", "--jq", ".login"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def prompt_github_username(self) -> str:
        """Prompt for GitHub username with auto-detection."""
        # Check if we already have it
        existing = self.existing_config.get("github_username")
        if existing:
            self.logger.success(f"Using existing GitHub username: {existing}")
            return existing

        self.logger.header("GitHub Configuration")

        detected = self.detect_github_username()
        if detected:
            self.logger.info(f"Detected GitHub username: {detected}")
            if self.prompter.prompt_yes_no("Use this username?", default=True):
                return detected

        return self.prompter.prompt(
            "Enter your GitHub username",
            required=True
        )

    def prompt_bot_name(self) -> str:
        """Prompt for bot name."""
        # Check if we already have it
        existing = self.existing_config.get("bot_name")
        if existing:
            self.logger.success(f"Using existing bot name: {existing}")
            return existing

        return self.prompter.prompt(
            "Bot name",
            default="james-in-a-box",
            required=True
        )

    def validate_slack_token(self, token: str, prefix: str):
        """Validate Slack token has correct prefix."""
        if not token.startswith(prefix):
            raise ValueError(f"Token must start with '{prefix}'")

    def prompt_slack_tokens(self) -> dict[str, str]:
        """Prompt for Slack tokens with validation."""
        secrets = {}

        # Check if we already have Slack tokens
        existing_bot_token = self.existing_secrets.get("SLACK_TOKEN")
        existing_app_token = self.existing_secrets.get("SLACK_APP_TOKEN")

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
                validator=lambda t: self.validate_slack_token(t, "xoxb-")
            )
            secrets["SLACK_TOKEN"] = bot_token

        if existing_app_token:
            self.logger.info(f"Using existing Slack app token: {existing_app_token[:20]}...")
            secrets["SLACK_APP_TOKEN"] = existing_app_token
        else:
            app_token = self.prompter.prompt(
                "Slack App Token (xapp-...)",
                required=True,
                validator=lambda t: self.validate_slack_token(t, "xapp-")
            )
            secrets["SLACK_APP_TOKEN"] = app_token

        return secrets

    def prompt_github_auth(self) -> dict[str, str]:
        """Prompt for GitHub authentication (App or PAT)."""
        secrets = {}

        # Check if GitHub auth already exists
        has_github_token = "GITHUB_TOKEN" in self.existing_secrets
        has_github_app = (
            (self.config_manager.config_dir / "github-app-id").exists()
            and (self.config_manager.config_dir / "github-app-private-key.pem").exists()
        )

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
        self.logger.info("  1. GitHub App (recommended for team usage, REQUIRED for PR check status)")
        self.logger.info("  2. Personal Access Token (simpler for personal use)")
        self.logger.info("")
        self.logger.info("Note: GitHub App is required to read PR check run status.")
        self.logger.info("PATs work for most operations but cannot access check runs API.")
        self.logger.info("")

        choice = self.prompter.prompt(
            "Choose authentication method [1/2]",
            default="2",
            validator=lambda c: None if c in ["1", "2"] else ValueError("Choose 1 or 2")
        )

        if choice == "1":
            # GitHub App configuration
            self.logger.info("\nGitHub App Configuration")
            self.logger.info("You'll need: App ID, Installation ID, and Private Key")
            self.logger.info("See: docs/setup/github-app-setup.md for setup instructions")
            self.logger.info("")

            app_id = self.prompter.prompt("GitHub App ID", required=True)
            installation_id = self.prompter.prompt("GitHub App Installation ID", required=True)
            private_key_path = self.prompter.prompt(
                "Path to private key file",
                required=True
            )

            # Read and store private key
            try:
                private_key_file = Path(private_key_path).expanduser()
                if not private_key_file.exists():
                    self.logger.error(f"Private key file not found: {private_key_path}")
                    return self.prompt_github_auth()  # Retry

                # Create GitHub App config files
                gh_app_id_file = self.config_manager.config_dir / "github-app-id"
                gh_app_installation_file = self.config_manager.config_dir / "github-app-installation-id"
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
            self.logger.info("For writable repositories, create a token with READ/WRITE permissions:")
            self.logger.info("  Required scopes: repo (full), workflow")
            self.logger.info("")

            token = self.prompter.prompt(
                "GitHub Personal Access Token (ghp_...)",
                required=True,
                validator=lambda t: None if t.startswith("ghp_") else ValueError("Token must start with 'ghp_'")
            )

            secrets["GITHUB_TOKEN"] = token

            # Optionally prompt for read-only token
            self.logger.info("")
            if self.prompter.prompt_yes_no("Do you have a separate read-only token for monitoring external repos?", default=False):
                self.logger.info("\nFor read-only repositories, create a token with READ-ONLY permissions:")
                self.logger.info("  Required scopes: repo (read-only)")
                self.logger.info("")
                readonly_token = self.prompter.prompt(
                    "GitHub Read-Only Token (ghp_...)",
                    validator=lambda t: None if t.startswith("ghp_") else ValueError("Token must start with 'ghp_'")
                )
                if readonly_token:
                    secrets["GITHUB_READONLY_TOKEN"] = readonly_token

        return secrets

    def prompt_repositories(self, github_username: str) -> tuple[list[str], list[str]]:
        """Prompt for repository configuration."""
        self.logger.header("Repository Configuration")

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

    def get_slack_channel_id(self) -> str:
        """Try to get the user's Slack DM channel ID."""
        self.logger.info("\nFinding your Slack DM channel...")
        self.logger.info("You can find your channel ID by:")
        self.logger.info("  1. Open Slack")
        self.logger.info("  2. Click on your DM with the bot")
        self.logger.info("  3. Look at the URL: /client/T.../D... <- that D... is your channel ID")
        self.logger.info("")

        channel_id = self.prompter.prompt(
            "Slack channel ID (starts with D, C, or G)",
            validator=lambda c: None if c and c[0] in ['D', 'C', 'G'] else ValueError("Channel ID must start with D, C, or G")
        )

        return channel_id if channel_id else ""

    def get_slack_user_id(self) -> str:
        """Prompt for Slack user ID."""
        self.logger.info("\nYour Slack User ID is needed for access control.")
        self.logger.info("Find it at: Slack -> Profile -> More -> Copy member ID")
        self.logger.info("")

        user_id = self.prompter.prompt(
            "Your Slack user ID (starts with U)",
            validator=lambda u: None if u and u.startswith('U') else ValueError("User ID must start with U")
        )

        return user_id if user_id else ""

    def run(self) -> bool:
        """Run the minimal setup flow.

        Returns:
            True if setup completed successfully, False otherwise.
        """
        self.logger.header("Phase 2: Minimal Setup")
        self.logger.info("This will configure the essential settings to get jib running.")
        self.logger.info("You can run './setup.py --full' later for optional components.")
        self.logger.info("")

        # Check if already configured
        if self.is_already_configured():
            self.logger.success("\n✓ Configuration already exists!")
            self.logger.info("")
            self.logger.info("All essential settings are already configured:")
            self.logger.info(f"  - GitHub username: {self.existing_config.get('github_username')}")
            self.logger.info(f"  - Bot name: {self.existing_config.get('bot_name', 'james-in-a-box')}")
            self.logger.info("  - Slack tokens: ✓")
            self.logger.info("  - GitHub authentication: ✓")
            self.logger.info("")
            self.logger.info("Re-running setup will reuse existing values.")
            self.logger.info("To update configuration, edit:")
            self.logger.info(f"  - {self.config_manager.secrets_file}")
            self.logger.info(f"  - {self.config_manager.config_file}")
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

            # 5. GitHub authentication
            github_secrets = self.prompt_github_auth()

            # 6. Repositories
            writable_repos, readable_repos = self.prompt_repositories(github_username)

            # Save configuration
            self.logger.header("Saving Configuration")

            # Combine all secrets
            all_secrets = {**slack_secrets, **github_secrets}
            self.config_manager.write_secrets(all_secrets)

            # Write main config
            config = {
                "bot_name": bot_name,
                "github_username": github_username,
                "slack_channel": slack_channel,
                "allowed_users": [slack_user] if slack_user else [],
                "context_sync_interval": 30,
                "github_sync_interval": 5,
            }
            self.config_manager.write_config(config)

            # Write repository config
            self.config_manager.write_repositories(writable_repos, readable_repos)

            self.logger.success("\n✓ Minimal setup complete!")
            self.logger.info("")
            self.logger.info("Configuration saved to:")
            self.logger.info(f"  - {self.config_manager.secrets_file}")
            self.logger.info(f"  - {self.config_manager.config_file}")
            self.logger.info(f"  - {self.config_manager.repos_file}")
            self.logger.info("")
            self.logger.info("Next steps:")
            self.logger.info("  1. Review the configuration files")
            self.logger.info("  2. Run './setup.py --enable-services' to start jib services")
            self.logger.info("  3. Run './setup.py --full' for additional components")

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
    if args.enable_services or args.enable_core_services or args.disable_services or args.enable or args.disable or args.status:
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
    if args.full:
        # Full setup mode: includes minimal setup + Docker + beads + optional components
        logger.info("Running full setup mode (minimal setup + all components)")

        # First run minimal setup to get config
        minimal_setup = MinimalSetup(logger, config_manager, prompter, verbose=args.verbose)
        if not minimal_setup.run():
            sys.exit(1)

        # Then run full setup for additional components
        full_setup = FullSetup(logger, config_manager, prompter, verbose=args.verbose)
        success = full_setup.run()
    else:
        # Minimal setup only (default)
        minimal_setup = MinimalSetup(logger, config_manager, prompter, verbose=args.verbose)
        success = minimal_setup.run()

    if success:
        logger.info("\n" + "="*60)
        logger.success("Setup completed successfully!")
        logger.info("="*60)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
