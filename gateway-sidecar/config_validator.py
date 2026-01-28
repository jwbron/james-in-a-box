"""Configuration validation for gateway startup.

Validates all required configuration at startup to fail fast with clear errors.
This is part of Phase 2: Full Network Lockdown implementation.

Reference: ADR-Internet-Tool-Access-Lockdown.md
"""

import os
import sys
from pathlib import Path


class ConfigError(Exception):
    """Raised when configuration validation fails."""


def validate_config() -> None:
    """Validate all gateway configuration at startup.

    Checks:
    - Required secrets exist
    - Squid configuration is valid
    - Allowed domains file exists and has content

    Raises:
        ConfigError: If any validation fails
    """
    errors: list[str] = []

    # Check for required secrets
    secrets_dir = Path("/secrets")
    if secrets_dir.is_dir():
        # GitHub token (managed by token refresher)
        github_token_file = secrets_dir / ".github-token"
        if not github_token_file.is_file():
            errors.append(
                "GitHub token not found: /secrets/.github-token\n"
                "  Ensure github-token-refresher service is running"
            )

        # Gateway secret (for jib container authentication)
        gateway_secret_file = secrets_dir / "gateway-secret"
        if not gateway_secret_file.is_file():
            errors.append(
                "Gateway secret not found: /secrets/gateway-secret\n"
                "  Run setup.sh to generate gateway secret"
            )
    else:
        errors.append(
            "Secrets directory not mounted: /secrets\n"
            "  Ensure ~/.jib-gateway is mounted at /secrets"
        )

    # Validate Squid configuration (Phase 2)
    squid_conf = Path("/etc/squid/squid.conf")
    if squid_conf.is_file():
        # Allowed domains file
        domains_file = Path("/etc/squid/allowed_domains.txt")
        if not domains_file.is_file():
            errors.append(
                "Allowed domains file not found: /etc/squid/allowed_domains.txt\n"
                "  This file must be present for network lockdown"
            )
        else:
            # Check file has actual domains (not just comments)
            try:
                with open(domains_file) as f:
                    domains = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.strip().startswith("#")
                    ]
                if not domains:
                    errors.append(
                        "Allowed domains file is empty (no domains configured)\n"
                        "  At minimum, api.anthropic.com and github.com are required"
                    )
            except Exception as e:
                errors.append(f"Failed to read allowed domains file: {e}")

        # Check Squid CA certificate
        squid_cert = Path("/etc/squid/squid-ca.pem")
        if not squid_cert.is_file():
            errors.append(
                "Squid CA certificate not found: /etc/squid/squid-ca.pem\n"
                "  This certificate is required for SNI inspection"
            )
    # Note: Squid config is optional - Phase 1 mode works without it

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise ConfigError(f"{len(errors)} configuration error(s) found")


def validate_network_lockdown_mode() -> bool:
    """Check if network lockdown mode is enabled and configured.

    Returns:
        True if network lockdown mode should be active
    """
    # Check if Squid is available and configured
    if not Path("/etc/squid/squid.conf").is_file():
        return False

    # Check if we're on the isolated network
    # In lockdown mode, gateway is dual-homed (jib-isolated + jib-external)
    env_mode = os.environ.get("JIB_NETWORK_MODE", "").lower()
    if env_mode == "lockdown":
        return True

    # Check for the existence of allowed_domains.txt as an indicator
    return Path("/etc/squid/allowed_domains.txt").is_file()


if __name__ == "__main__":
    try:
        validate_config()
        print("Configuration validation passed")

        if validate_network_lockdown_mode():
            print("Network lockdown mode: ENABLED")
        else:
            print("Network lockdown mode: DISABLED (Phase 1 compatibility)")

        sys.exit(0)
    except ConfigError:
        sys.exit(1)
