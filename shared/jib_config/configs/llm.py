"""
LLM provider configuration for jib services.

Supports multiple LLM providers:
- Anthropic (Claude)
- Google (Gemini)
- OpenAI (via router)
"""

import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..base import BaseConfig, HealthCheckResult, ValidationResult
from ..validators import mask_secret, validate_anthropic_key, validate_non_empty


class LLMProvider(Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENAI = "openai"


# Model used for health checks - uses cheapest/fastest model
# Note: Health checks make minimal API calls (max_tokens=1) but are billable
ANTHROPIC_HEALTH_CHECK_MODEL = "claude-3-haiku-20240307"


@dataclass
class LLMConfig(BaseConfig):
    """Configuration for LLM providers.

    Attributes:
        provider: The LLM provider to use
        anthropic_api_key: Anthropic API key (sk-ant-...)
        google_api_key: Google API key for Gemini
        openai_api_key: OpenAI API key (for router)
        anthropic_base_url: Custom base URL for Anthropic API
        model: Optional model override
        timeout: Request timeout in seconds
    """

    provider: LLMProvider = LLMProvider.ANTHROPIC
    anthropic_api_key: str = ""
    google_api_key: str = ""
    openai_api_key: str = ""
    anthropic_base_url: str = ""
    model: str = ""
    timeout: int = 7200  # 2 hours default

    def validate(self) -> ValidationResult:
        """Validate LLM configuration."""
        errors: list[str] = []
        warnings: list[str] = []

        if self.provider == LLMProvider.ANTHROPIC:
            is_valid, error = validate_non_empty(self.anthropic_api_key, "anthropic_api_key")
            if not is_valid:
                errors.append(error)
            else:
                is_valid, error = validate_anthropic_key(self.anthropic_api_key)
                if not is_valid:
                    errors.append(f"anthropic_api_key: {error}")

        elif self.provider == LLMProvider.GOOGLE:
            is_valid, error = validate_non_empty(self.google_api_key, "google_api_key")
            if not is_valid:
                errors.append(error)
            # Google API keys don't have a standard prefix

        elif self.provider == LLMProvider.OPENAI:
            is_valid, error = validate_non_empty(self.openai_api_key, "openai_api_key")
            if not is_valid:
                errors.append(error)
            # OpenAI keys start with sk- but we won't enforce

        # Warn about custom base URL
        if self.anthropic_base_url:
            warnings.append(f"Using custom Anthropic base URL: {self.anthropic_base_url}")

        if errors:
            return ValidationResult.invalid(errors, warnings)

        return ValidationResult.valid(warnings)

    def health_check(self, timeout: float = 5.0) -> HealthCheckResult:
        """Check LLM provider connectivity.

        For Anthropic, calls the models endpoint to verify API key.
        """
        if self.provider == LLMProvider.ANTHROPIC:
            return self._check_anthropic(timeout)
        elif self.provider == LLMProvider.GOOGLE:
            return self._check_google(timeout)
        elif self.provider == LLMProvider.OPENAI:
            return self._check_openai(timeout)

        return HealthCheckResult(
            healthy=False,
            service_name="llm",
            message=f"Unknown provider: {self.provider}",
        )

    def _check_anthropic(self, timeout: float) -> HealthCheckResult:
        """Check Anthropic API connectivity."""
        if not self.anthropic_api_key:
            return HealthCheckResult(
                healthy=False,
                service_name="llm",
                message="Anthropic API key not configured",
            )

        try:
            import json
            import urllib.request

            base_url = self.anthropic_base_url or "https://api.anthropic.com"
            start = time.time()

            # Use a minimal messages request to verify API key
            # Note: This is a billable API call (minimal cost with max_tokens=1)
            # The /v1/models endpoint requires different auth
            req = urllib.request.Request(
                f"{base_url}/v1/messages",
                data=json.dumps(
                    {
                        "model": ANTHROPIC_HEALTH_CHECK_MODEL,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    }
                ).encode(),
                headers={
                    "x-api-key": self.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=timeout):
                latency = (time.time() - start) * 1000
                return HealthCheckResult(
                    healthy=True,
                    service_name="llm",
                    message="Anthropic API connected",
                    latency_ms=latency,
                )

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return HealthCheckResult(
                    healthy=False,
                    service_name="llm",
                    message="Invalid Anthropic API key",
                )
            elif e.code == 400:
                # Bad request but auth worked
                latency = (time.time() - start) * 1000
                return HealthCheckResult(
                    healthy=True,
                    service_name="llm",
                    message="Anthropic API connected (auth verified)",
                    latency_ms=latency,
                )
            return HealthCheckResult(
                healthy=False,
                service_name="llm",
                message=f"Anthropic API error: HTTP {e.code}",
            )
        except Exception as e:
            return HealthCheckResult(
                healthy=False,
                service_name="llm",
                message=f"Anthropic connection failed: {e}",
            )

    def _check_google(self, timeout: float) -> HealthCheckResult:
        """Check Google Gemini API connectivity."""
        if not self.google_api_key:
            return HealthCheckResult(
                healthy=False,
                service_name="llm",
                message="Google API key not configured",
            )

        try:
            import urllib.request

            start = time.time()
            # List models to verify API key
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1/models?key={self.google_api_key}",
            )

            with urllib.request.urlopen(req, timeout=timeout):
                latency = (time.time() - start) * 1000
                return HealthCheckResult(
                    healthy=True,
                    service_name="llm",
                    message="Google Gemini API connected",
                    latency_ms=latency,
                )

        except urllib.error.HTTPError as e:
            if e.code in {401, 403}:
                return HealthCheckResult(
                    healthy=False,
                    service_name="llm",
                    message="Invalid Google API key",
                )
            return HealthCheckResult(
                healthy=False,
                service_name="llm",
                message=f"Google API error: HTTP {e.code}",
            )
        except Exception as e:
            return HealthCheckResult(
                healthy=False,
                service_name="llm",
                message=f"Google connection failed: {e}",
            )

    def _check_openai(self, timeout: float) -> HealthCheckResult:
        """Check OpenAI API connectivity."""
        if not self.openai_api_key:
            return HealthCheckResult(
                healthy=False,
                service_name="llm",
                message="OpenAI API key not configured",
            )

        try:
            import urllib.request

            start = time.time()
            req = urllib.request.Request(
                "https://api.openai.com/v1/models",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                },
            )

            with urllib.request.urlopen(req, timeout=timeout):
                latency = (time.time() - start) * 1000
                return HealthCheckResult(
                    healthy=True,
                    service_name="llm",
                    message="OpenAI API connected",
                    latency_ms=latency,
                )

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return HealthCheckResult(
                    healthy=False,
                    service_name="llm",
                    message="Invalid OpenAI API key",
                )
            return HealthCheckResult(
                healthy=False,
                service_name="llm",
                message=f"OpenAI API error: HTTP {e.code}",
            )
        except Exception as e:
            return HealthCheckResult(
                healthy=False,
                service_name="llm",
                message=f"OpenAI connection failed: {e}",
            )

    def to_dict(self) -> dict[str, Any]:
        """Return config with secrets masked."""
        return {
            "provider": self.provider.value,
            "anthropic_api_key": mask_secret(self.anthropic_api_key),
            "google_api_key": mask_secret(self.google_api_key),
            "openai_api_key": mask_secret(self.openai_api_key),
            "anthropic_base_url": self.anthropic_base_url or "[default]",
            "model": self.model or "[provider default]",
            "timeout": self.timeout,
        }

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load LLM configuration from environment variables.

        Environment variables:
        - LLM_PROVIDER: anthropic, google, or openai
        - ANTHROPIC_API_KEY: Anthropic API key
        - ANTHROPIC_BASE_URL: Custom base URL
        - GOOGLE_API_KEY: Google/Gemini API key
        - OPENAI_API_KEY: OpenAI API key
        """
        config = cls()

        # Determine provider
        provider_str = os.environ.get("LLM_PROVIDER", "anthropic").lower()
        try:
            config.provider = LLMProvider(provider_str)
        except ValueError:
            config.provider = LLMProvider.ANTHROPIC

        # Load API keys from environment
        config.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        config.google_api_key = os.environ.get("GOOGLE_API_KEY", "")
        config.openai_api_key = os.environ.get("OPENAI_API_KEY", "")

        # Optional settings
        config.anthropic_base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
        config.model = os.environ.get("LLM_MODEL", "")

        timeout_str = os.environ.get("LLM_TIMEOUT", "7200")
        try:
            config.timeout = int(timeout_str)
        except ValueError:
            config.timeout = 7200

        # Try router config file if available
        router_config = Path.home() / ".claude-code-router" / "config.json"
        if router_config.exists() and not config.anthropic_api_key:
            try:
                import json

                with open(router_config) as f:
                    data = json.load(f)
                    if "anthropic_api_key" in data:
                        config.anthropic_api_key = data["anthropic_api_key"]
            except Exception:
                pass

        return config
