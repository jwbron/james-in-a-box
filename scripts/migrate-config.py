#!/usr/bin/env python3
"""
Configuration Migration Script

Migrates existing jib configuration files to the new unified format.

This script:
1. Reads existing ~/.config/jib/config.yaml and secrets.env
2. Adds new nested sections (slack:, github:, services:)
3. Preserves old top-level keys until you verify the new config works
4. Removes legacy keys with --cleanup after verification

Recommended workflow:
    ./scripts/migrate-config.py              # Show what would change (dry run)
    ./scripts/migrate-config.py --apply      # Add new nested sections
    ./scripts/migrate-config.py --verify     # Verify config loads correctly
    ./scripts/migrate-config.py --cleanup    # Remove old top-level keys

New config.yaml structure:
    slack:
      channel: "C12345"
      allowed_users: [...]
      owner_user_id: "..."
      self_dm_channel: "..."
      batch_window_seconds: 15

    github:
      username: "jib"

    services:
      watch_directories: [...]
      incoming_directory: "..."
      responses_directory: "..."
"""

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


# Try to import yaml
try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)


class ConfigMigrator:
    """Handles migration of jib configuration files."""

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path.home() / ".config" / "jib"
        self.config_yaml = self.config_dir / "config.yaml"
        self.secrets_env = self.config_dir / "secrets.env"
        self.backup_dir = self.config_dir / "backups"

        self.old_config = {}
        self.new_config = {}
        self.secrets = {}
        self.changes = []

    def load_existing_config(self):
        """Load existing configuration files."""
        # Load config.yaml
        if self.config_yaml.exists():
            with open(self.config_yaml) as f:
                self.old_config = yaml.safe_load(f) or {}
            print(f"✓ Loaded {self.config_yaml}")
        else:
            print(f"⚠ No existing config.yaml found at {self.config_yaml}")

        # Load secrets.env
        if self.secrets_env.exists():
            with open(self.secrets_env) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        self.secrets[key.strip()] = value.strip().strip("\"'")
            print(f"✓ Loaded {self.secrets_env}")
        else:
            print(f"⚠ No existing secrets.env found at {self.secrets_env}")

    def plan_migration(self):
        """Plan the migration and record changes."""
        self.new_config = {}

        # =====================================================================
        # Migrate Slack settings
        # =====================================================================
        slack_settings = {}

        # Check for top-level slack settings that need to move
        top_level_slack_keys = {
            "slack_channel": "channel",
            "allowed_users": "allowed_users",
            "owner_user_id": "owner_user_id",
            "self_dm_channel": "self_dm_channel",
            "batch_window_seconds": "batch_window_seconds",
        }

        for old_key, new_key in top_level_slack_keys.items():
            if old_key in self.old_config:
                slack_settings[new_key] = self.old_config[old_key]
                self.changes.append(f"Move '{old_key}' → 'slack.{new_key}'")

        # Also check if there's already a slack section
        if "slack" in self.old_config:
            existing_slack = self.old_config["slack"]
            if isinstance(existing_slack, dict):
                for key, value in existing_slack.items():
                    if key not in slack_settings:
                        slack_settings[key] = value

        if slack_settings:
            self.new_config["slack"] = slack_settings

        # =====================================================================
        # Migrate GitHub settings
        # =====================================================================
        github_settings = {}

        if "github_username" in self.old_config:
            github_settings["username"] = self.old_config["github_username"]
            self.changes.append("Move 'github_username' → 'github.username'")

        if "github" in self.old_config:
            existing_github = self.old_config["github"]
            if isinstance(existing_github, dict):
                for key, value in existing_github.items():
                    if key not in github_settings:
                        github_settings[key] = value

        if github_settings:
            self.new_config["github"] = github_settings

        # =====================================================================
        # Migrate service-specific settings
        # =====================================================================
        services_settings = {}

        service_keys = [
            "watch_directories",
            "incoming_directory",
            "responses_directory",
        ]

        for key in service_keys:
            if key in self.old_config:
                services_settings[key] = self.old_config[key]
                self.changes.append(f"Move '{key}' → 'services.{key}'")

        if "services" in self.old_config:
            existing_services = self.old_config["services"]
            if isinstance(existing_services, dict):
                for key, value in existing_services.items():
                    if key not in services_settings:
                        services_settings[key] = value

        if services_settings:
            self.new_config["services"] = services_settings

        # =====================================================================
        # Preserve other settings
        # =====================================================================
        preserved_keys = set()
        for key in top_level_slack_keys:
            preserved_keys.add(key)
        preserved_keys.update(service_keys)
        preserved_keys.add("github_username")
        preserved_keys.update(["slack", "github", "services"])

        for key, value in self.old_config.items():
            if key not in preserved_keys:
                self.new_config[key] = value
                # Don't record as a change since it's preserved as-is

    def show_plan(self):
        """Display the migration plan."""
        print("\n" + "=" * 60)
        print(" MIGRATION PLAN")
        print("=" * 60)

        if not self.changes:
            print("\n✓ No changes needed - configuration is already in new format")
            return False

        print("\nChanges to be made:\n")
        for i, change in enumerate(self.changes, 1):
            print(f"  {i}. {change}")

        print("\n" + "-" * 60)
        print(" NEW config.yaml STRUCTURE:")
        print("-" * 60)
        print()
        print(yaml.dump(self.new_config, default_flow_style=False, sort_keys=False))

        return True

    def create_backup(self):
        """Create backup of existing config files."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        backed_up = []

        if self.config_yaml.exists():
            backup_path = self.backup_dir / f"config.yaml.{timestamp}"
            shutil.copy2(self.config_yaml, backup_path)
            backed_up.append(str(backup_path))

        if self.secrets_env.exists():
            backup_path = self.backup_dir / f"secrets.env.{timestamp}"
            shutil.copy2(self.secrets_env, backup_path)
            os.chmod(backup_path, 0o600)
            backed_up.append(str(backup_path))

        if backed_up:
            print("\n✓ Backups created:")
            for path in backed_up:
                print(f"    {path}")

        return backed_up

    def apply_migration(self):
        """Apply the migration by adding new nested sections.

        This preserves existing top-level keys so you can verify the new
        structure works before running --cleanup to remove them.
        """
        if not self.changes:
            print("\n✓ No changes needed - configuration is already in new format")
            return

        # Merge new config with old config (preserving old keys)
        merged_config = dict(self.old_config)
        for key, value in self.new_config.items():
            if key in ["slack", "github", "services"]:
                # Add new nested sections
                merged_config[key] = value
            elif key not in merged_config:
                # Preserve other keys from new_config
                merged_config[key] = value

        # Write merged config.yaml
        with open(self.config_yaml, "w") as f:
            f.write("# jib configuration\n")
            f.write("# Migrated to new format: " + datetime.now().isoformat() + "\n")
            f.write("#\n")
            f.write("# Secrets (tokens, API keys) should be in secrets.env, not here.\n")
            f.write("# Run with --cleanup to remove legacy top-level keys after verification.\n")
            f.write("#\n\n")
            yaml.dump(merged_config, f, default_flow_style=False, sort_keys=False)

        print(f"\n✓ Wrote new configuration to {self.config_yaml}")
        print("  Legacy keys preserved. Run --cleanup after verification to remove them.")

    def cleanup_legacy_keys(self):
        """Remove legacy top-level keys that have been migrated to nested sections."""
        # Reload current config
        if not self.config_yaml.exists():
            print("\n⚠ No config.yaml found")
            return False

        with open(self.config_yaml) as f:
            current_config = yaml.safe_load(f) or {}

        # Keys that should be removed (migrated to nested sections)
        legacy_keys = [
            "slack_channel",
            "allowed_users",
            "owner_user_id",
            "self_dm_channel",
            "batch_window_seconds",
            "github_username",
            "watch_directories",
            "incoming_directory",
            "responses_directory",
        ]

        removed = []
        for key in legacy_keys:
            if key in current_config:
                del current_config[key]
                removed.append(key)

        if not removed:
            print("\n✓ No legacy keys to remove - config is clean")
            return True

        # Write cleaned config
        with open(self.config_yaml, "w") as f:
            f.write("# jib configuration\n")
            f.write("# Cleaned: " + datetime.now().isoformat() + "\n")
            f.write("#\n")
            f.write("# Secrets (tokens, API keys) should be in secrets.env, not here.\n")
            f.write("#\n\n")
            yaml.dump(current_config, f, default_flow_style=False, sort_keys=False)

        print(f"\n✓ Removed legacy keys: {', '.join(removed)}")
        print(f"  Config written to {self.config_yaml}")
        return True

    def verify_migration(self, run_health_checks: bool = False):
        """Verify the migration was successful by testing config loading."""
        print("\n" + "=" * 60)
        print(" VERIFICATION")
        print("=" * 60)

        # Add the repo's shared directory to path
        script_dir = Path(__file__).parent
        repo_root = script_dir.parent
        sys.path.insert(0, str(repo_root / "shared"))

        try:
            from jib_config import (
                ConfluenceConfig,
                GatewayConfig,
                GitHubConfig,
                JiraConfig,
                SlackConfig,
            )

            errors = []

            # Test SlackConfig
            slack = SlackConfig.from_env()
            validation = slack.validate()
            if validation.is_valid:
                print("✓ SlackConfig loads successfully")
                print(f"    channel: {slack.channel or '(not set)'}")
                print(f"    bot_token: {'set' if slack.bot_token else 'NOT SET'}")
            else:
                errors.extend(validation.errors)
                print(f"✗ SlackConfig validation errors: {validation.errors}")

            # Test GitHubConfig
            github = GitHubConfig.from_env()
            validation = github.validate()
            if validation.is_valid:
                print("✓ GitHubConfig loads successfully")
                print(
                    f"    token: {'set' if github.token else 'NOT SET'} (source: {github._token_source or 'none'})"
                )
            # GitHub might not be configured, that's OK
            elif github.token:
                errors.extend(validation.errors)
                print(f"✗ GitHubConfig validation errors: {validation.errors}")
            else:
                print("⚠ GitHubConfig: No token configured")

            # Test GatewayConfig
            gateway = GatewayConfig.from_env()
            print("✓ GatewayConfig loads successfully")
            print(
                f"    secret: {'set' if gateway.secret else 'NOT SET'} (source: {gateway._secret_source or 'none'})"
            )

            # Test JiraConfig
            jira = JiraConfig.from_env()
            validation = jira.validate()
            if validation.is_valid:
                print("✓ JiraConfig loads successfully")
                print(f"    base_url: {jira.base_url or '(not set)'}")
            elif jira.base_url:
                errors.extend(validation.errors)
                print(f"✗ JiraConfig validation errors: {validation.errors}")
            else:
                print("⚠ JiraConfig: Not configured")

            # Test ConfluenceConfig
            confluence = ConfluenceConfig.from_env()
            validation = confluence.validate()
            if validation.is_valid:
                print("✓ ConfluenceConfig loads successfully")
                print(f"    base_url: {confluence.base_url or '(not set)'}")
            elif confluence.base_url:
                errors.extend(validation.errors)
                print(f"✗ ConfluenceConfig validation errors: {validation.errors}")
            else:
                print("⚠ ConfluenceConfig: Not configured")

            if errors:
                print("\n⚠ Some validation errors occurred. Check your configuration.")
                return False
            else:
                print("\n✓ All configurations loaded and validated successfully!")

            # Run health checks if requested
            if run_health_checks:
                self._run_health_checks(slack, github, jira, confluence)

            return True

        except Exception as e:
            print(f"\n✗ Verification failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _run_health_checks(self, slack, github, jira, confluence):
        """Run actual API connectivity tests."""
        print("\n" + "=" * 60)
        print(" HEALTH CHECKS (API Connectivity)")
        print("=" * 60)

        # Slack health check
        if slack.bot_token:
            print("\nTesting Slack API...")
            result = slack.health_check(timeout=10.0)
            if result.healthy:
                latency = f" ({result.latency_ms:.0f}ms)" if result.latency_ms else ""
                print(f"  ✓ Slack: {result.message}{latency}")
            else:
                print(f"  ✗ Slack: {result.message}")
        else:
            print("\n⚠ Slack: Skipped (no token configured)")

        # GitHub health check
        if github.token:
            print("\nTesting GitHub API...")
            result = github.health_check(timeout=10.0)
            if result.healthy:
                latency = f" ({result.latency_ms:.0f}ms)" if result.latency_ms else ""
                print(f"  ✓ GitHub: {result.message}{latency}")
            else:
                print(f"  ✗ GitHub: {result.message}")
        else:
            print("\n⚠ GitHub: Skipped (no token configured)")

        # JIRA health check
        if jira.base_url and jira.api_token:
            print("\nTesting JIRA API...")
            result = jira.health_check(timeout=10.0)
            if result.healthy:
                latency = f" ({result.latency_ms:.0f}ms)" if result.latency_ms else ""
                print(f"  ✓ JIRA: {result.message}{latency}")
            else:
                print(f"  ✗ JIRA: {result.message}")
        else:
            print("\n⚠ JIRA: Skipped (not configured)")

        # Confluence health check
        if confluence.base_url and confluence.api_token:
            print("\nTesting Confluence API...")
            result = confluence.health_check(timeout=10.0)
            if result.healthy:
                latency = f" ({result.latency_ms:.0f}ms)" if result.latency_ms else ""
                print(f"  ✓ Confluence: {result.message}{latency}")
            else:
                print(f"  ✗ Confluence: {result.message}")
        else:
            print("\n⚠ Confluence: Skipped (not configured)")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate jib configuration to new format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                 Show migration plan (dry run)
  %(prog)s --apply         Add new nested sections (preserves old keys)
  %(prog)s --cleanup       Remove legacy top-level keys
  %(prog)s --verify        Verify current config loads correctly
  %(prog)s --health        Test API connectivity (Slack, GitHub, JIRA, Confluence)
  %(prog)s --backup        Create backup only

Recommended workflow:
  1. %(prog)s              # Review what will change
  2. %(prog)s --apply      # Add new nested sections
  3. %(prog)s --health     # Test API connectivity
  4. %(prog)s --cleanup    # Remove old top-level keys
        """,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Add new nested sections (preserves legacy keys for verification)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove legacy top-level keys after migration",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup only, don't migrate",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify current configuration loads correctly",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Test API connectivity (Slack, GitHub, JIRA, Confluence)",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        help="Config directory (default: ~/.config/jib)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print(" JIB CONFIGURATION MIGRATION")
    print("=" * 60)

    migrator = ConfigMigrator(args.config_dir)

    if args.verify:
        # Just verify current config
        migrator.verify_migration()
        return

    if args.health:
        # Run health checks (API connectivity tests)
        migrator.verify_migration(run_health_checks=True)
        return

    if args.cleanup:
        # Remove legacy keys
        print("\nRemoving legacy top-level keys...")
        migrator.cleanup_legacy_keys()
        migrator.verify_migration()
        return

    # Load existing config
    print("\nLoading existing configuration...")
    migrator.load_existing_config()

    if args.backup:
        # Backup only
        migrator.create_backup()
        print("\n✓ Backup complete")
        return

    # Plan migration
    migrator.plan_migration()
    has_changes = migrator.show_plan()

    if not has_changes:
        migrator.verify_migration()
        return

    if args.apply:
        # Apply migration (preserves old keys)
        print("\nApplying migration...")
        migrator.apply_migration()

        # Verify
        migrator.verify_migration()

        print("\n" + "-" * 60)
        print(" Next step: Run --cleanup to remove legacy keys")
        print("-" * 60)
    else:
        print("\n" + "-" * 60)
        print(" DRY RUN - No changes made")
        print(" Run with --apply to apply the migration")
        print("-" * 60)


if __name__ == "__main__":
    main()
