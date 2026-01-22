# Configuration Modernization Framework

**Status:** Proposal
**Author:** jib
**Date:** 2026-01-22

## Summary

Create a unified configuration framework for james-in-a-box that provides:
- **Centralized loading** with consistent validation across all services
- **Health check endpoints** for all service configurations
- **Hot-reload capability** for configuration changes without restart
- **Audit logging** for configuration changes
- **Dry-run mode** to test configurations without side effects

## Motivation

The current configuration system has evolved organically with inconsistent patterns:

| Service | Config Pattern | Validation | Health Check |
|---------|---------------|------------|--------------|
| HostConfig | Unified loader | None | None |
| Slack (notifier/receiver) | **Duplicates HostConfig** | Required fields only | None |
| Confluence/JIRA | Class-based | `validate()` method | None |
| Gateway | Env vars + file | Token expiry check | `/api/v1/health` |
| LLM | Env vars only | **None** | None |
| GitHub | Multiple sources | Expiry check | `is_token_valid()` |

**Key Issues:**
1. Slack services duplicate 60+ lines of config loading instead of using `HostConfig`
2. LLM configs have zero validation - API keys not validated before use
3. No pre-flight health checks - services fail at runtime, not startup
4. Inconsistent error messages across services

## Proposed Architecture

```
shared/jib_config/
├── __init__.py           # Public API
├── base.py               # BaseConfig protocol, ValidationResult, HealthCheckResult
├── registry.py           # ConfigRegistry singleton
├── validators.py         # Reusable validators (URL, email, token format)
├── watcher.py            # Hot-reload file watcher
├── audit.py              # Configuration change audit logging
└── configs/
    ├── slack.py          # SlackConfig
    ├── github.py         # GitHubConfig (consolidates token handling)
    ├── llm.py            # LLMConfig (new)
    ├── confluence.py     # ConfluenceConfig (wraps existing)
    ├── jira.py           # JiraConfig (wraps existing)
    └── gateway.py        # GatewayConfig
```

## Key Interfaces

```python
@dataclass
class ValidationResult:
    status: ConfigStatus  # VALID, INVALID, DEGRADED
    errors: list[str]
    warnings: list[str]

@dataclass
class HealthCheckResult:
    healthy: bool
    service_name: str
    message: str
    latency_ms: float | None

class BaseConfig(ABC):
    @abstractmethod
    def validate(self) -> ValidationResult: ...
    @abstractmethod
    def health_check(self, timeout: float) -> HealthCheckResult: ...
    @abstractmethod
    def to_dict(self) -> dict[str, Any]: ...  # secrets masked
    @classmethod
    @abstractmethod
    def from_env(cls) -> "BaseConfig": ...
```

## Implementation Phases

### Phase 1: Core Framework

**Files to create:**

| File | Purpose |
|------|---------|
| `shared/jib_config/__init__.py` | Public API exports |
| `shared/jib_config/base.py` | `BaseConfig`, `ValidationResult`, `HealthCheckResult`, `ConfigProtocol` |
| `shared/jib_config/registry.py` | `ConfigRegistry` singleton with `validate_all()`, `health_check_all()` |
| `shared/jib_config/validators.py` | `validate_url()`, `validate_email()`, `validate_slack_token()`, `validate_github_token()`, `mask_secret()` |

### Phase 2: Service Configurations

**Files to create:**

| File | Key Features |
|------|--------------|
| `shared/jib_config/configs/slack.py` | Token format validation, API auth test health check |
| `shared/jib_config/configs/github.py` | Consolidate 4 token sources, expiry tracking, API health check |
| `shared/jib_config/configs/llm.py` | API key validation, provider health checks |
| `shared/jib_config/configs/confluence.py` | Wrap existing with BaseConfig interface |
| `shared/jib_config/configs/jira.py` | Wrap existing with BaseConfig interface |
| `shared/jib_config/configs/gateway.py` | Secret management, rate limit config |

**Validation rules to add:**

- **Slack tokens**: Must start with `xoxb-`, `xapp-`, or `xoxp-`
- **GitHub tokens**: Must start with `ghp_`, `github_pat_`, `ghs_`, or `gho_`
- **Anthropic keys**: Must start with `sk-ant-`
- **URLs**: Must be valid HTTPS URLs
- **Emails**: Must match email regex pattern

### Phase 3: Service Migration

**Files to modify:**

| File | Changes |
|------|---------|
| `host-services/slack/slack-notifier/slack-notifier.py` | Replace lines 95-152 with `SlackConfig.from_env()` |
| `host-services/slack/slack-receiver/slack-receiver.py` | Replace lines 116-179 with `SlackConfig.from_env()` |
| `jib-container/llm/config.py` | Use `LLMConfig` from framework |
| `gateway-sidecar/github_client.py` | Use `GitHubConfig` for token management |

**Migration pattern:**

```python
# Before (duplicated in slack-notifier.py and slack-receiver.py):
def _load_config(self):
    jib_secrets = Path.home() / ".config" / "jib" / "secrets.env"
    if jib_secrets.exists():
        with open(jib_secrets) as f:
            for line in f:
                # ... 60 lines of parsing

# After:
from jib_config.configs.slack import SlackConfig

slack_config = SlackConfig.from_env()
validation = slack_config.validate()
if not validation.is_valid:
    raise ValueError(f"Invalid Slack config: {validation.errors}")
self.slack_token = slack_config.bot_token
```

### Phase 4: New Features

**Files to create:**

| File | Purpose |
|------|---------|
| `shared/jib_config/watcher.py` | Poll-based file watcher for hot-reload |
| `shared/jib_config/audit.py` | Structured audit logging for config changes |

**Hot-reload usage:**

```python
from jib_config.watcher import ConfigWatcher

watcher = ConfigWatcher(poll_interval=5.0)
watcher.watch(Path("~/.config/jib/config.yaml"), on_config_change)
watcher.start()
```

**Dry-run mode:**

```python
from jib_config import get_registry

registry = get_registry()
registry.set_dry_run(True)  # Validation runs, writes are logged but not executed
```

### Phase 5: Health Check Enhancement

**Files to modify:**

| File | Changes |
|------|---------|
| `gateway-sidecar/gateway.py` | Enhance `/api/v1/health` to aggregate all service health |
| `host-services/slack/slack-notifier/slack-notifier.py` | Add startup health check |
| `host-services/slack/slack-receiver/slack-receiver.py` | Add startup health check |

**Enhanced health endpoint:**

```json
{
  "status": "healthy|degraded|unhealthy",
  "services": {
    "github": {"healthy": true, "message": "Authenticated as jib", "latency_ms": 150},
    "slack": {"healthy": true, "message": "Connected as jib-bot", "latency_ms": 80},
    "llm": {"healthy": false, "message": "API key not configured"}
  },
  "timestamp": "2026-01-22T..."
}
```

## Verification Plan

1. **Unit tests**: Test each config class validation, masking, loading
2. **Integration tests**: Test `from_env()` with mock files
3. **Health check tests**: Mock API responses for health checks
4. **Migration verification**:
   - Run existing Slack service tests
   - Verify config loading produces same values
   - Test health check endpoints return expected format
5. **End-to-end**:
   - Start services with valid config - should start
   - Start services with invalid config - should fail with clear error
   - Change config file - hot-reload should trigger callback

## Backward Compatibility

- Existing environment variable names preserved
- Existing file locations (`~/.config/jib/`) preserved
- Existing `HostConfig` class remains available (deprecated)
- Migration can be done service-by-service

## Alternatives Considered

### 1. Add pydantic dependency
- **Pros**: Better validation, automatic serialization
- **Cons**: New dependency, learning curve
- **Decision**: Use dataclasses to match existing patterns; can migrate later if needed

### 2. Extend existing HostConfig
- **Pros**: Less new code
- **Cons**: HostConfig is already large (433 lines), mixing concerns
- **Decision**: Create new framework, deprecate HostConfig gradually

### 3. Use environment variables only
- **Pros**: Simple, 12-factor compliant
- **Cons**: Doesn't support structured config, no validation
- **Decision**: Support both files and env vars with env override

## Open Questions

1. Should we add a CLI tool for config validation? (e.g., `jib-config validate`)
2. Should health checks run periodically or only on-demand?
3. How aggressive should hot-reload be? (immediate vs debounced)

---

Authored-by: jib
