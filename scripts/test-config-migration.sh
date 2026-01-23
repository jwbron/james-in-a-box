#!/usr/bin/env bash
#
# Configuration Migration Integration Tests
#
# This script validates that existing jib configuration works correctly
# with the new unified configuration framework.
#
# Run from the host machine:
#   ./scripts/test-config-migration.sh
#
# Options:
#   --dry-run     Show what would be tested without making changes
#   --verbose     Show detailed output
#   --fix         Attempt to fix issues found
#   --skip-health Skip health check tests (don't call external APIs)
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Options
DRY_RUN=false
VERBOSE=false
FIX_ISSUES=false
SKIP_HEALTH=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --fix)
            FIX_ISSUES=true
            shift
            ;;
        --skip-health)
            SKIP_HEALTH=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
WARNINGS=0

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((TESTS_PASSED++))
    ((TESTS_RUN++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((TESTS_FAILED++))
    ((TESTS_RUN++))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
}

log_verbose() {
    if $VERBOSE; then
        echo -e "       $1"
    fi
}

header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE} $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
}

# ==============================================================================
# Phase 1: Check Prerequisites
# ==============================================================================

check_prerequisites() {
    header "Phase 1: Checking Prerequisites"

    # Check Python version
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
        log_success "Python 3 available: $PYTHON_VERSION"
    else
        log_fail "Python 3 not found"
        exit 1
    fi

    # Check PyYAML is available
    if python3 -c "import yaml" 2>/dev/null; then
        log_success "PyYAML module available"
    else
        log_warn "PyYAML not installed - config.yaml loading may fail"
    fi

    # Check jib_config module path
    if [[ -d "$REPO_ROOT/shared/jib_config" ]]; then
        log_success "jib_config module found at $REPO_ROOT/shared/jib_config"
    else
        log_fail "jib_config module not found"
        exit 1
    fi

    # Check config directory exists
    if [[ -d "$HOME/.config/jib" ]]; then
        log_success "Config directory exists: ~/.config/jib"
    else
        log_warn "Config directory not found: ~/.config/jib"
        if $FIX_ISSUES; then
            mkdir -p "$HOME/.config/jib"
            chmod 700 "$HOME/.config/jib"
            log_info "Created ~/.config/jib"
        fi
    fi
}

# ==============================================================================
# Phase 2: Inventory Existing Configuration
# ==============================================================================

inventory_config() {
    header "Phase 2: Inventorying Existing Configuration"

    local config_dir="$HOME/.config/jib"

    # Check secrets.env
    if [[ -f "$config_dir/secrets.env" ]]; then
        log_success "secrets.env exists"
        log_verbose "Contents (keys only):"
        if $VERBOSE; then
            grep -E "^[A-Z_]+=" "$config_dir/secrets.env" 2>/dev/null | cut -d= -f1 | sed 's/^/         /' || true
        fi

        # Check permissions
        local perms=$(stat -c %a "$config_dir/secrets.env" 2>/dev/null || stat -f %Lp "$config_dir/secrets.env" 2>/dev/null)
        if [[ "$perms" == "600" ]]; then
            log_success "secrets.env has correct permissions (600)"
        else
            log_warn "secrets.env permissions are $perms (should be 600)"
            if $FIX_ISSUES; then
                chmod 600 "$config_dir/secrets.env"
                log_info "Fixed permissions on secrets.env"
            fi
        fi
    else
        log_warn "secrets.env not found - tokens must be in environment"
    fi

    # Check config.yaml
    if [[ -f "$config_dir/config.yaml" ]]; then
        log_success "config.yaml exists"
        log_verbose "Top-level keys:"
        if $VERBOSE; then
            python3 -c "
import yaml
with open('$config_dir/config.yaml') as f:
    config = yaml.safe_load(f) or {}
for key in config.keys():
    print(f'         {key}')
" 2>/dev/null || echo "         (failed to parse)"
        fi
    else
        log_warn "config.yaml not found"
    fi

    # Check github-token file
    if [[ -f "$config_dir/github-token" ]]; then
        log_success "github-token file exists"
    else
        log_verbose "github-token file not found (may use other sources)"
    fi

    # Check gateway-secret
    if [[ -f "$config_dir/gateway-secret" ]]; then
        log_success "gateway-secret file exists"
    else
        log_verbose "gateway-secret file not found (will be auto-generated)"
    fi

    # Check repositories.yaml
    if [[ -f "$config_dir/repositories.yaml" ]]; then
        log_success "repositories.yaml exists"
    else
        log_verbose "repositories.yaml not found"
    fi
}

# ==============================================================================
# Phase 3: Test Configuration Loading
# ==============================================================================

test_config_loading() {
    header "Phase 3: Testing Configuration Loading"

    python3 << 'PYTHON_SCRIPT'
import sys
import os

# Add jib_config to path
repo_root = os.environ.get("REPO_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(repo_root, "shared"))

from jib_config import SlackConfig, GitHubConfig, LLMConfig, GatewayConfig
from jib_config import ConfluenceConfig, JiraConfig

results = []

def test_config(name, config_class):
    """Test loading a config class."""
    try:
        config = config_class.from_env()
        validation = config.validate()

        if validation.is_valid:
            results.append(("PASS", f"{name}: Loaded and validated successfully"))
        else:
            results.append(("WARN", f"{name}: Loaded but validation errors: {validation.errors}"))

        for warning in validation.warnings:
            results.append(("WARN", f"{name}: {warning}"))

        return config
    except Exception as e:
        results.append(("FAIL", f"{name}: Failed to load: {e}"))
        return None

# Test each config type
slack = test_config("SlackConfig", SlackConfig)
github = test_config("GitHubConfig", GitHubConfig)
llm = test_config("LLMConfig", LLMConfig)
gateway = test_config("GatewayConfig", GatewayConfig)

# These are optional - only test if configured
try:
    confluence = ConfluenceConfig.from_env()
    if confluence.base_url:
        test_config("ConfluenceConfig", ConfluenceConfig)
except:
    pass

try:
    jira = JiraConfig.from_env()
    if jira.base_url:
        test_config("JiraConfig", JiraConfig)
except:
    pass

# Print results
for status, message in results:
    print(f"{status}|{message}")

# Print loaded values summary (masked)
print("---SUMMARY---")
if slack:
    print(f"Slack bot_token: {'set' if slack.bot_token else 'NOT SET'}")
    print(f"Slack app_token: {'set' if slack.app_token else 'NOT SET'}")
    print(f"Slack channel: {slack.channel or 'NOT SET'}")
if github:
    print(f"GitHub token: {'set' if github.token else 'NOT SET'} (source: {github._token_source or 'none'})")
if llm:
    print(f"LLM provider: {llm.provider.value}")
    print(f"Anthropic key: {'set' if llm.anthropic_api_key else 'NOT SET'}")
if gateway:
    print(f"Gateway secret: {'set' if gateway.secret else 'NOT SET'} (source: {gateway._secret_source or 'none'})")
PYTHON_SCRIPT
}

parse_python_results() {
    # Run the Python test and parse results
    local output
    output=$(REPO_ROOT="$REPO_ROOT" python3 << 'PYTHON_SCRIPT'
import sys
import os

repo_root = os.environ.get("REPO_ROOT")
sys.path.insert(0, os.path.join(repo_root, "shared"))

from jib_config import SlackConfig, GitHubConfig, LLMConfig, GatewayConfig

results = []

def test_config(name, config_class):
    try:
        config = config_class.from_env()
        validation = config.validate()

        if validation.is_valid:
            results.append(("PASS", f"{name}: Loaded and validated successfully"))
        else:
            results.append(("WARN", f"{name}: Validation issues: {', '.join(validation.errors)}"))

        for warning in validation.warnings:
            results.append(("WARN", f"{name}: {warning}"))

        return config
    except Exception as e:
        results.append(("FAIL", f"{name}: {e}"))
        return None

slack = test_config("SlackConfig", SlackConfig)
github = test_config("GitHubConfig", GitHubConfig)
llm = test_config("LLMConfig", LLMConfig)
gateway = test_config("GatewayConfig", GatewayConfig)

for status, message in results:
    print(f"{status}|{message}")

print("---VALUES---")
if slack:
    print(f"slack.bot_token={'SET' if slack.bot_token else 'UNSET'}")
    print(f"slack.app_token={'SET' if slack.app_token else 'UNSET'}")
    print(f"slack.channel={slack.channel or 'UNSET'}")
if github:
    print(f"github.token={'SET' if github.token else 'UNSET'}")
    print(f"github.source={github._token_source or 'none'}")
if llm:
    print(f"llm.provider={llm.provider.value}")
    print(f"llm.anthropic_key={'SET' if llm.anthropic_api_key else 'UNSET'}")
if gateway:
    print(f"gateway.secret={'SET' if gateway.secret else 'UNSET'}")
    print(f"gateway.source={gateway._secret_source or 'none'}")
PYTHON_SCRIPT
    )

    # Parse and display results
    local in_values=false
    while IFS= read -r line; do
        if [[ "$line" == "---VALUES---" ]]; then
            in_values=true
            echo ""
            log_info "Configuration Values Summary:"
            continue
        fi

        if $in_values; then
            log_verbose "$line"
        else
            local status="${line%%|*}"
            local message="${line#*|}"
            case "$status" in
                PASS) log_success "$message" ;;
                FAIL) log_fail "$message" ;;
                WARN) log_warn "$message" ;;
            esac
        fi
    done <<< "$output"
}

# ==============================================================================
# Phase 4: Compare Old vs New Loading
# ==============================================================================

compare_old_new_loading() {
    header "Phase 4: Comparing Old vs New Configuration Loading"

    log_info "Testing that new framework loads same values as old code..."

    python3 << 'PYTHON_SCRIPT'
import sys
import os

repo_root = os.environ.get("REPO_ROOT")
sys.path.insert(0, os.path.join(repo_root, "shared"))

from pathlib import Path

# Simulate old loading (from slack-notifier.py before migration)
def load_old_slack_config():
    """Load config the old way."""
    config = {}

    jib_config_dir = Path.home() / ".config" / "jib"
    jib_secrets = jib_config_dir / "secrets.env"
    jib_config = jib_config_dir / "config.yaml"

    # Load secrets from .env file
    if jib_secrets.exists():
        with open(jib_secrets) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("\"'")
                    if key == "SLACK_TOKEN" and value:
                        config["slack_token"] = value
                    elif key == "SLACK_APP_TOKEN" and value:
                        config["slack_app_token"] = value

    # Load non-secret config from YAML
    if jib_config.exists():
        try:
            import yaml
            with open(jib_config) as f:
                yaml_config = yaml.safe_load(f) or {}
            config.update(yaml_config)
        except ImportError:
            pass

    # Defaults
    config.setdefault("slack_token", "")
    config.setdefault("slack_channel", "")
    config.setdefault("batch_window_seconds", 15)
    config.setdefault("watch_directories", ["~/.jib-sharing"])

    # Environment variables override
    if os.environ.get("SLACK_TOKEN"):
        config["slack_token"] = os.environ["SLACK_TOKEN"]
    if os.environ.get("SLACK_CHANNEL"):
        config["slack_channel"] = os.environ["SLACK_CHANNEL"]

    return config

# Load with new framework
from jib_config import SlackConfig

old_config = load_old_slack_config()
new_config = SlackConfig.from_env()

# Compare values
comparisons = [
    ("bot_token", old_config.get("slack_token", ""), new_config.bot_token),
    ("app_token", old_config.get("slack_app_token", ""), new_config.app_token),
    ("channel", old_config.get("slack_channel", ""), new_config.channel),
    ("batch_window_seconds", old_config.get("batch_window_seconds", 15), new_config.batch_window_seconds),
]

all_match = True
for name, old_val, new_val in comparisons:
    if old_val == new_val:
        print(f"PASS|{name}: Values match")
    else:
        print(f"FAIL|{name}: OLD='{old_val[:20] if isinstance(old_val, str) else old_val}...' NEW='{new_val[:20] if isinstance(new_val, str) else new_val}...'")
        all_match = False

if all_match:
    print("PASS|All Slack config values match between old and new loading")
PYTHON_SCRIPT
}

parse_comparison_results() {
    local output
    output=$(REPO_ROOT="$REPO_ROOT" python3 << 'PYTHON_SCRIPT'
import sys
import os
from pathlib import Path

repo_root = os.environ.get("REPO_ROOT")
sys.path.insert(0, os.path.join(repo_root, "shared"))

def load_old_slack_config():
    config = {}
    jib_config_dir = Path.home() / ".config" / "jib"
    jib_secrets = jib_config_dir / "secrets.env"
    jib_config_file = jib_config_dir / "config.yaml"

    if jib_secrets.exists():
        with open(jib_secrets) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("\"'")
                    if key == "SLACK_TOKEN" and value:
                        config["slack_token"] = value
                    elif key == "SLACK_APP_TOKEN" and value:
                        config["slack_app_token"] = value

    if jib_config_file.exists():
        try:
            import yaml
            with open(jib_config_file) as f:
                yaml_config = yaml.safe_load(f) or {}
            config.update(yaml_config)
        except:
            pass

    config.setdefault("slack_token", "")
    config.setdefault("slack_channel", "")
    config.setdefault("batch_window_seconds", 15)

    if os.environ.get("SLACK_TOKEN"):
        config["slack_token"] = os.environ["SLACK_TOKEN"]
    if os.environ.get("SLACK_CHANNEL"):
        config["slack_channel"] = os.environ["SLACK_CHANNEL"]

    return config

from jib_config import SlackConfig

old_config = load_old_slack_config()
new_config = SlackConfig.from_env()

comparisons = [
    ("bot_token", old_config.get("slack_token", ""), new_config.bot_token),
    ("app_token", old_config.get("slack_app_token", ""), new_config.app_token),
    ("channel", old_config.get("slack_channel", ""), new_config.channel),
    ("batch_window_seconds", old_config.get("batch_window_seconds", 15), new_config.batch_window_seconds),
]

for name, old_val, new_val in comparisons:
    if old_val == new_val:
        print(f"PASS|{name}: Values match")
    else:
        old_preview = str(old_val)[:20] + "..." if len(str(old_val)) > 20 else str(old_val)
        new_preview = str(new_val)[:20] + "..." if len(str(new_val)) > 20 else str(new_val)
        print(f"FAIL|{name}: OLD='{old_preview}' vs NEW='{new_preview}'")
PYTHON_SCRIPT
    )

    while IFS= read -r line; do
        local status="${line%%|*}"
        local message="${line#*|}"
        case "$status" in
            PASS) log_success "$message" ;;
            FAIL) log_fail "$message" ;;
        esac
    done <<< "$output"
}

# ==============================================================================
# Phase 5: Test Health Checks (Optional)
# ==============================================================================

test_health_checks() {
    if $SKIP_HEALTH; then
        header "Phase 5: Health Checks (SKIPPED)"
        log_info "Skipping health checks (--skip-health flag)"
        return
    fi

    header "Phase 5: Testing Health Checks"

    log_warn "Health checks will make API calls to external services"
    log_info "Testing connectivity to configured services..."

    python3 << 'PYTHON_SCRIPT'
import sys
import os

repo_root = os.environ.get("REPO_ROOT")
sys.path.insert(0, os.path.join(repo_root, "shared"))

from jib_config import SlackConfig, GitHubConfig, GatewayConfig

def test_health(name, config):
    """Run health check for a config."""
    try:
        result = config.health_check(timeout=10.0)
        if result.healthy:
            latency = f" ({result.latency_ms:.0f}ms)" if result.latency_ms else ""
            print(f"PASS|{name}: {result.message}{latency}")
        else:
            print(f"WARN|{name}: {result.message}")
    except Exception as e:
        print(f"FAIL|{name}: Health check error: {e}")

# Test Slack (if configured)
slack = SlackConfig.from_env()
if slack.bot_token:
    test_health("Slack", slack)
else:
    print("SKIP|Slack: No bot token configured")

# Test GitHub (if configured)
github = GitHubConfig.from_env()
if github.token:
    test_health("GitHub", github)
else:
    print("SKIP|GitHub: No token configured")

# Test Gateway (if running)
gateway = GatewayConfig.from_env()
if gateway.secret:
    test_health("Gateway", gateway)
else:
    print("SKIP|Gateway: No secret configured")
PYTHON_SCRIPT
}

parse_health_results() {
    if $SKIP_HEALTH; then
        return
    fi

    local output
    output=$(REPO_ROOT="$REPO_ROOT" python3 << 'PYTHON_SCRIPT'
import sys
import os

repo_root = os.environ.get("REPO_ROOT")
sys.path.insert(0, os.path.join(repo_root, "shared"))

from jib_config import SlackConfig, GitHubConfig, GatewayConfig

def test_health(name, config):
    try:
        result = config.health_check(timeout=10.0)
        if result.healthy:
            latency = f" ({result.latency_ms:.0f}ms)" if result.latency_ms else ""
            print(f"PASS|{name}: {result.message}{latency}")
        else:
            print(f"WARN|{name}: {result.message}")
    except Exception as e:
        print(f"FAIL|{name}: {e}")

slack = SlackConfig.from_env()
if slack.bot_token:
    test_health("Slack", slack)
else:
    print("SKIP|Slack: No token")

github = GitHubConfig.from_env()
if github.token:
    test_health("GitHub", github)
else:
    print("SKIP|GitHub: No token")

gateway = GatewayConfig.from_env()
if gateway.secret:
    test_health("Gateway", gateway)
else:
    print("SKIP|Gateway: No secret")
PYTHON_SCRIPT
    )

    while IFS= read -r line; do
        local status="${line%%|*}"
        local message="${line#*|}"
        case "$status" in
            PASS) log_success "$message" ;;
            FAIL) log_fail "$message" ;;
            WARN) log_warn "$message" ;;
            SKIP) log_verbose "$message" ;;
        esac
    done <<< "$output"
}

# ==============================================================================
# Phase 6: Test Service Imports
# ==============================================================================

test_service_imports() {
    header "Phase 6: Testing Service Imports"

    log_info "Verifying migrated services can import new config framework..."

    # Test slack-notifier imports
    if python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT/shared')
sys.path.insert(0, '$REPO_ROOT/host-services/shared')
from jib_config import SlackConfig
from jib_config.utils import load_yaml_file
" 2>/dev/null; then
        log_success "slack-notifier: Imports work correctly"
    else
        log_fail "slack-notifier: Import failed"
    fi

    # Test slack-receiver imports
    if python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT/shared')
sys.path.insert(0, '$REPO_ROOT/host-services/shared')
from jib_config import SlackConfig
from jib_config.utils import load_yaml_file
" 2>/dev/null; then
        log_success "slack-receiver: Imports work correctly"
    else
        log_fail "slack-receiver: Import failed"
    fi

    # Test CLI tool
    if python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT/shared')
from jib_config.cli import main
" 2>/dev/null; then
        log_success "jib-config CLI: Imports work correctly"
    else
        log_fail "jib-config CLI: Import failed"
    fi
}

# ==============================================================================
# Phase 7: Validate Token Formats
# ==============================================================================

validate_token_formats() {
    header "Phase 7: Validating Token Formats"

    log_info "Checking that tokens have correct prefixes..."

    python3 << 'PYTHON_SCRIPT'
import sys
import os

repo_root = os.environ.get("REPO_ROOT")
sys.path.insert(0, os.path.join(repo_root, "shared"))

from jib_config import SlackConfig, GitHubConfig, LLMConfig

slack = SlackConfig.from_env()
github = GitHubConfig.from_env()
llm = LLMConfig.from_env()

# Check Slack bot token
if slack.bot_token:
    if slack.bot_token.startswith("xoxb-"):
        print("PASS|Slack bot token has correct prefix (xoxb-)")
    else:
        print(f"FAIL|Slack bot token has wrong prefix: {slack.bot_token[:10]}...")

# Check Slack app token
if slack.app_token:
    if slack.app_token.startswith("xapp-"):
        print("PASS|Slack app token has correct prefix (xapp-)")
    else:
        print(f"FAIL|Slack app token has wrong prefix: {slack.app_token[:10]}...")

# Check GitHub token
if github.token:
    valid_prefixes = ["ghp_", "github_pat_", "ghs_", "gho_"]
    if any(github.token.startswith(p) for p in valid_prefixes):
        prefix = next(p for p in valid_prefixes if github.token.startswith(p))
        print(f"PASS|GitHub token has valid prefix ({prefix})")
    else:
        print(f"FAIL|GitHub token has unrecognized prefix: {github.token[:10]}...")

# Check Anthropic key
if llm.anthropic_api_key:
    if llm.anthropic_api_key.startswith("sk-ant-"):
        print("PASS|Anthropic API key has correct prefix (sk-ant-)")
    else:
        print(f"FAIL|Anthropic API key has wrong prefix: {llm.anthropic_api_key[:10]}...")
PYTHON_SCRIPT
}

parse_token_results() {
    local output
    output=$(REPO_ROOT="$REPO_ROOT" python3 << 'PYTHON_SCRIPT'
import sys
import os

repo_root = os.environ.get("REPO_ROOT")
sys.path.insert(0, os.path.join(repo_root, "shared"))

from jib_config import SlackConfig, GitHubConfig, LLMConfig

slack = SlackConfig.from_env()
github = GitHubConfig.from_env()
llm = LLMConfig.from_env()

if slack.bot_token:
    if slack.bot_token.startswith("xoxb-"):
        print("PASS|Slack bot token: correct prefix (xoxb-)")
    else:
        print(f"FAIL|Slack bot token: wrong prefix ({slack.bot_token[:8]}...)")
else:
    print("SKIP|Slack bot token: not set")

if slack.app_token:
    if slack.app_token.startswith("xapp-"):
        print("PASS|Slack app token: correct prefix (xapp-)")
    else:
        print(f"FAIL|Slack app token: wrong prefix ({slack.app_token[:8]}...)")
else:
    print("SKIP|Slack app token: not set")

if github.token:
    valid = ["ghp_", "github_pat_", "ghs_", "gho_"]
    if any(github.token.startswith(p) for p in valid):
        print("PASS|GitHub token: valid prefix")
    else:
        print(f"FAIL|GitHub token: unrecognized prefix ({github.token[:8]}...)")
else:
    print("SKIP|GitHub token: not set")

if llm.anthropic_api_key:
    if llm.anthropic_api_key.startswith("sk-ant-"):
        print("PASS|Anthropic key: correct prefix (sk-ant-)")
    else:
        print(f"FAIL|Anthropic key: wrong prefix ({llm.anthropic_api_key[:8]}...)")
else:
    print("SKIP|Anthropic key: not set")
PYTHON_SCRIPT
    )

    while IFS= read -r line; do
        local status="${line%%|*}"
        local message="${line#*|}"
        case "$status" in
            PASS) log_success "$message" ;;
            FAIL) log_fail "$message" ;;
            SKIP) log_verbose "$message" ;;
        esac
    done <<< "$output"
}

# ==============================================================================
# Summary
# ==============================================================================

print_summary() {
    header "Test Summary"

    echo ""
    echo -e "  Tests run:    ${TESTS_RUN}"
    echo -e "  ${GREEN}Passed:${NC}       ${TESTS_PASSED}"
    echo -e "  ${RED}Failed:${NC}       ${TESTS_FAILED}"
    echo -e "  ${YELLOW}Warnings:${NC}     ${WARNINGS}"
    echo ""

    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN} ✓ All tests passed! Configuration migration successful.${NC}"
        echo -e "${GREEN}══════════════════════════════════════════════════════════${NC}"
        return 0
    else
        echo -e "${RED}══════════════════════════════════════════════════════════${NC}"
        echo -e "${RED} ✗ Some tests failed. Review issues above.${NC}"
        echo -e "${RED}══════════════════════════════════════════════════════════${NC}"
        return 1
    fi
}

# ==============================================================================
# Main
# ==============================================================================

main() {
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     JIB Configuration Migration Integration Tests        ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"

    if $DRY_RUN; then
        log_info "DRY RUN MODE - No changes will be made"
    fi

    check_prerequisites
    inventory_config
    parse_python_results
    parse_comparison_results
    parse_health_results
    test_service_imports
    parse_token_results

    print_summary
}

main "$@"
