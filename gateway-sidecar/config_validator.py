"""Configuration validation for gateway startup.

Validates all required configuration at startup to fail fast with clear errors.
This validates the network lockdown implementation.

Reference: ADR-Internet-Tool-Access-Lockdown.md

Security Invariant:
When ALLOW_ALL_NETWORK is enabled, PUBLIC_REPO_ONLY_MODE must also be enabled
to ensure: open network access = public repos only. This prevents data
exfiltration from private repositories via open network access.
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

    # Validate Squid configuration (required for network lockdown)
    squid_conf = Path("/etc/squid/squid.conf")
    if not squid_conf.is_file():
        errors.append(
            "Squid configuration not found: /etc/squid/squid.conf\n"
            "  This file is required for network lockdown"
        )

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
                    line.strip() for line in f if line.strip() and not line.strip().startswith("#")
                ]
            if not domains:
                errors.append(
                    "Allowed domains file is empty (no domains configured)\n"
                    "  At minimum, api.anthropic.com is required"
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

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise ConfigError(f"{len(errors)} configuration error(s) found")


def validate_network_lockdown_mode() -> bool:
    """Check if network lockdown mode is properly configured.

    Returns:
        True if all lockdown components are present
    """
    # Verify all required components
    squid_conf = Path("/etc/squid/squid.conf").is_file()
    domains_file = Path("/etc/squid/allowed_domains.txt").is_file()
    squid_cert = Path("/etc/squid/squid-ca.pem").is_file()

    return squid_conf and domains_file and squid_cert


def is_allow_all_network_mode() -> bool:
    """Check if allow-all-network mode is enabled.

    Returns:
        True if ALLOW_ALL_NETWORK is set to true/1
    """
    value = os.environ.get("ALLOW_ALL_NETWORK", "false").lower().strip()
    return value in ("true", "1")


def is_public_repo_only_mode_enabled() -> bool:
    """Check if public repo only mode is enabled.

    Returns:
        True if PUBLIC_REPO_ONLY_MODE is set to true/1
    """
    value = os.environ.get("PUBLIC_REPO_ONLY_MODE", "false").lower().strip()
    return value in ("true", "1")


def validate_allow_all_network_mode() -> list[str]:
    """Validate configuration for allow-all-network mode.

    When ALLOW_ALL_NETWORK is enabled, we need additional safety checks.
    The security invariant is: open network = public repos only.

    Returns:
        List of warning messages (empty if all checks pass)
    """
    warnings: list[str] = []

    if not is_allow_all_network_mode():
        return warnings

    # Check that squid-allow-all.conf exists
    allow_all_conf = Path("/etc/squid/squid-allow-all.conf")
    if not allow_all_conf.is_file():
        warnings.append(
            "ALLOW_ALL_NETWORK is enabled but squid-allow-all.conf not found\n"
            "  The gateway may not allow all network traffic as expected"
        )

    # Verify security invariant: open network = public repos only
    if not is_public_repo_only_mode_enabled():
        warnings.append(
            "ALLOW_ALL_NETWORK is enabled but PUBLIC_REPO_ONLY_MODE is not set\n"
            "  This configuration allows access to private repos with open network\n"
            "  Set PUBLIC_REPO_ONLY_MODE=true for secure operation"
        )

    return warnings


if __name__ == "__main__":
    try:
        validate_config()
        print("Configuration validation passed")

        if is_allow_all_network_mode():
            print("Network mode: ALLOW_ALL_NETWORK (all domains permitted)")
            warnings = validate_allow_all_network_mode()
            for warning in warnings:
                print(f"WARNING: {warning}")
        elif validate_network_lockdown_mode():
            print("Network lockdown mode: READY")
        else:
            print("WARNING: Network lockdown components missing")

        sys.exit(0)
    except ConfigError:
        sys.exit(1)
