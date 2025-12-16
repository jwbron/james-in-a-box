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
        "jib-slack-notifier.service",
        "jib-slack-receiver.service",
        "jib-github-token-refresher.service",
        "jib-worktree-watcher.timer",
    ]

    # LLM-based services that use tokens (opt-in)
    LLM_SERVICES = [
        "jib-context-sync.timer",
        "jib-github-watcher.timer",
        "jib-conversation-analyzer.timer",
        "jib-doc-generator.timer",
        "jib-adr-researcher.timer",
    ]

    def __init__(self, logger: SetupLogger):
        self.logger = logger
        self.has_systemctl = shutil.which("systemctl") is not None

    def enable_service(self, service: str) -> bool:
        """Enable and start a single service.

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

    def get_service_status(self) -> dict[str, str]:
        """Get status of all jib services.

        Returns:
            Dictionary mapping service names to status strings
        """
        if not self.has_systemctl:
            return {}

        all_services = self.CORE_SERVICES + self.LLM_SERVICES
        statuses = {}

        for service in all_services:
            try:
                result = subprocess.run(
                    ["systemctl", "--user", "is-active", service],
                    capture_output=True,
                    text=True
                )
                statuses[service] = result.stdout.strip()
            except subprocess.CalledProcessError:
                statuses[service] = "unknown"

        return statuses


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


class MinimalSetup:
    """Handles the minimal setup flow."""

    def __init__(self, logger: SetupLogger, config_manager: ConfigManager, prompter: UserPrompter, verbose: bool = False):
        self.logger = logger
        self.config_manager = config_manager
        self.prompter = prompter
        self.verbose = verbose

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
        self.logger.header("Slack Integration")
        self.logger.info("Get tokens from: https://api.slack.com/apps")
        self.logger.info("")

        bot_token = self.prompter.prompt(
            "Slack Bot Token (xoxb-...)",
            required=True,
            validator=lambda t: self.validate_slack_token(t, "xoxb-")
        )

        app_token = self.prompter.prompt(
            "Slack App Token (xapp-...)",
            required=True,
            validator=lambda t: self.validate_slack_token(t, "xapp-")
        )

        return {
            "SLACK_TOKEN": bot_token,
            "SLACK_APP_TOKEN": app_token,
        }

    def prompt_github_auth(self) -> dict[str, str]:
        """Prompt for GitHub authentication (App or PAT)."""
        self.logger.header("GitHub Authentication")
        self.logger.info("Choose authentication method:")
        self.logger.info("  1. GitHub App (recommended for team usage)")
        self.logger.info("  2. Personal Access Token (simpler for personal use)")
        self.logger.info("")

        choice = self.prompter.prompt(
            "Choose authentication method [1/2]",
            default="2",
            validator=lambda c: None if c in ["1", "2"] else ValueError("Choose 1 or 2")
        )

        secrets = {}

        if choice == "1":
            # GitHub App configuration
            self.logger.info("\nGitHub App Configuration")
            self.logger.info("You'll need: App ID, Installation ID, and Private Key")
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
            self.logger.info("Required scopes: repo, workflow")
            self.logger.info("")

            token = self.prompter.prompt(
                "GitHub Personal Access Token (ghp_...)",
                required=True,
                validator=lambda t: None if t.startswith("ghp_") else ValueError("Token must start with 'ghp_'")
            )

            secrets["GITHUB_TOKEN"] = token

            # Optionally prompt for read-only token
            if self.prompter.prompt_yes_no("Do you have a separate read-only token for monitoring external repos?", default=False):
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
    if args.enable_services or args.disable_services or args.enable or args.disable:
        service_manager = ServiceManager(logger)

        if args.enable_services:
            sys.exit(0 if service_manager.enable_all_services() else 1)
        elif args.disable_services:
            sys.exit(0 if service_manager.disable_all_services() else 1)
        elif args.enable:
            sys.exit(0 if service_manager.enable_service(args.enable) else 1)
        elif args.disable:
            sys.exit(0 if service_manager.disable_service(args.disable) else 1)

    # Check dependencies (unless skipped)
    if not args.skip_deps:
        dep_checker = DependencyChecker(logger)
        if not dep_checker.check_all():
            sys.exit(1)

    # Initialize managers
    config_manager = ConfigManager(logger)
    config_manager.ensure_config_dir()

    # Run minimal setup flow
    prompter = UserPrompter(logger)
    minimal_setup = MinimalSetup(logger, config_manager, prompter, verbose=args.verbose)

    if args.full:
        logger.warning("Full setup mode not yet implemented (Phase 4)")
        logger.info("Running minimal setup for now...")

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
