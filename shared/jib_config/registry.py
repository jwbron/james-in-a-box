"""
Configuration registry for managing service configurations.

The registry provides:
- Central registration of all service configs
- Bulk validation (validate_all)
- Bulk health checks (health_check_all)
- Dry-run mode for testing
"""

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any

from .base import BaseConfig, HealthCheckResult, ValidationResult


@dataclass
class AggregateHealthResult:
    """Aggregated health check results from all services.

    Attributes:
        status: Overall status (healthy/degraded/unhealthy)
        services: Individual health check results by service name
        timestamp: When the health check was performed
    """

    status: str  # "healthy", "degraded", "unhealthy"
    services: dict[str, HealthCheckResult]
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "services": {name: result.to_dict() for name, result in self.services.items()},
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AggregateValidationResult:
    """Aggregated validation results from all services.

    Attributes:
        all_valid: True if all configs are valid
        results: Individual validation results by service name
    """

    all_valid: bool
    results: dict[str, ValidationResult]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "all_valid": self.all_valid,
            "results": {
                name: {
                    "status": result.status.value,
                    "errors": result.errors,
                    "warnings": result.warnings,
                }
                for name, result in self.results.items()
            },
        }


class ConfigRegistry:
    """Central registry for all service configurations.

    This is a singleton that holds all registered configs and provides
    methods for bulk operations.

    Usage:
        registry = get_registry()
        registry.register(slack_config)
        registry.register(github_config)

        # Validate all configs
        result = registry.validate_all()
        if not result.all_valid:
            for name, validation in result.results.items():
                if not validation.is_valid:
                    print(f"{name}: {validation.errors}")

        # Health check all configs
        health = registry.health_check_all()
        print(health.status)  # "healthy", "degraded", or "unhealthy"
    """

    _instance: "ConfigRegistry | None" = None
    _lock: Lock = Lock()

    def __new__(cls) -> "ConfigRegistry":
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._configs = {}
                    cls._instance._dry_run = False
        return cls._instance

    def __init__(self) -> None:
        # Initialization happens in __new__ to avoid re-init on each call
        pass

    @property
    def configs(self) -> dict[str, BaseConfig]:
        """Return all registered configs."""
        return dict(self._configs)

    @property
    def dry_run(self) -> bool:
        """Return whether dry-run mode is enabled."""
        return self._dry_run

    def set_dry_run(self, enabled: bool) -> None:
        """Enable or disable dry-run mode.

        In dry-run mode, validation runs but writes are logged instead of executed.
        """
        self._dry_run = enabled

    def register(self, config: BaseConfig, name: str | None = None) -> None:
        """Register a configuration.

        Args:
            config: The config instance to register
            name: Optional name override (defaults to config.service_name)
        """
        service_name = name or config.service_name
        self._configs[service_name] = config

    def unregister(self, name: str) -> None:
        """Unregister a configuration by name.

        Args:
            name: The service name to unregister
        """
        self._configs.pop(name, None)

    def get(self, name: str) -> BaseConfig | None:
        """Get a registered config by name.

        Args:
            name: The service name

        Returns:
            The config instance or None if not found
        """
        return self._configs.get(name)

    def validate_all(self) -> AggregateValidationResult:
        """Validate all registered configurations.

        Returns:
            AggregateValidationResult with individual results
        """
        results: dict[str, ValidationResult] = {}
        all_valid = True

        for name, config in self._configs.items():
            result = config.validate()
            results[name] = result
            if not result.is_valid:
                all_valid = False

        return AggregateValidationResult(all_valid=all_valid, results=results)

    def health_check_all(self, timeout: float = 5.0) -> AggregateHealthResult:
        """Run health checks on all registered configurations.

        Args:
            timeout: Maximum time per health check in seconds

        Returns:
            AggregateHealthResult with individual results
        """
        results: dict[str, HealthCheckResult] = {}
        unhealthy_count = 0
        total_count = len(self._configs)

        for name, config in self._configs.items():
            result = config.health_check(timeout=timeout)
            results[name] = result
            if not result.healthy:
                unhealthy_count += 1

        # Determine overall status
        if unhealthy_count == 0:
            status = "healthy"
        elif unhealthy_count == total_count:
            status = "unhealthy"
        else:
            status = "degraded"

        return AggregateHealthResult(status=status, services=results)

    def clear(self) -> None:
        """Clear all registered configurations.

        Primarily useful for testing.
        """
        self._configs.clear()

    def to_dict(self) -> dict[str, Any]:
        """Return all configs as a dictionary with secrets masked.

        Returns:
            Dictionary of service names to masked config dictionaries
        """
        return {name: config.to_dict() for name, config in self._configs.items()}


# Module-level singleton accessor
_registry: ConfigRegistry | None = None


def get_registry() -> ConfigRegistry:
    """Get the global configuration registry instance.

    Returns:
        The singleton ConfigRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ConfigRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the registry to a fresh state.

    Primarily useful for testing to ensure clean state between tests.
    """
    global _registry
    if _registry is not None:
        _registry.clear()
    _registry = None
    ConfigRegistry._instance = None
