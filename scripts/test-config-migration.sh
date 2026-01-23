#!/usr/bin/env bash
#
# Configuration Integration Tests
#
# Verifies that the jib configuration framework works correctly
# after migration. Run this after running migrate-config.py.
#
# Usage:
#   ./scripts/test-config-migration.sh              # Run all tests
#   ./scripts/test-config-migration.sh --skip-health  # Skip API calls
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

SKIP_HEALTH=false
[[ "${1:-}" == "--skip-health" ]] && SKIP_HEALTH=true

TESTS_PASSED=0
TESTS_FAILED=0

log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; ((TESTS_PASSED++)); }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; ((TESTS_FAILED++)); }
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE} $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
}

# ==============================================================================
# Test 1: Config Files Exist
# ==============================================================================
test_config_files() {
    header "Test 1: Configuration Files"

    local config_dir="$HOME/.config/jib"

    if [[ -d "$config_dir" ]]; then
        log_pass "Config directory exists: $config_dir"
    else
        log_fail "Config directory missing: $config_dir"
        return 1
    fi

    if [[ -f "$config_dir/config.yaml" ]]; then
        log_pass "config.yaml exists"
    else
        log_fail "config.yaml missing"
    fi

    if [[ -f "$config_dir/secrets.env" ]]; then
        log_pass "secrets.env exists"

        # Check permissions
        local perms=$(stat -c %a "$config_dir/secrets.env" 2>/dev/null || stat -f %Lp "$config_dir/secrets.env" 2>/dev/null)
        if [[ "$perms" == "600" ]]; then
            log_pass "secrets.env has correct permissions (600)"
        else
            log_warn "secrets.env permissions are $perms (should be 600)"
        fi
    else
        log_fail "secrets.env missing"
    fi
}

# ==============================================================================
# Test 2: Config Structure
# ==============================================================================
test_config_structure() {
    header "Test 2: Configuration Structure"

    python3 << PYTHON
import sys
import yaml
from pathlib import Path

config_file = Path.home() / ".config" / "jib" / "config.yaml"
if not config_file.exists():
    print("FAIL|config.yaml not found")
    sys.exit(1)

with open(config_file) as f:
    config = yaml.safe_load(f) or {}

# Check for new structure
if "slack" in config and isinstance(config["slack"], dict):
    print("PASS|slack section exists and is a dict")
    slack = config["slack"]
    if "channel" in slack:
        print("PASS|slack.channel is set")
    else:
        print("WARN|slack.channel not set")
else:
    print("FAIL|slack section missing or invalid")

# Check for legacy top-level keys that should have been migrated
legacy_keys = ["slack_channel", "allowed_users", "owner_user_id", "batch_window_seconds"]
for key in legacy_keys:
    if key in config:
        print(f"FAIL|Legacy key '{key}' still at top level - run migrate-config.py")
PYTHON
}

parse_structure_results() {
    local output
    output=$(python3 << 'PYTHON'
import sys
import yaml
from pathlib import Path

config_file = Path.home() / ".config" / "jib" / "config.yaml"
if not config_file.exists():
    print("FAIL|config.yaml not found")
    sys.exit(0)

with open(config_file) as f:
    config = yaml.safe_load(f) or {}

if "slack" in config and isinstance(config["slack"], dict):
    print("PASS|slack section exists")
    if config["slack"].get("channel"):
        print("PASS|slack.channel is configured")
    else:
        print("WARN|slack.channel not set")
else:
    print("FAIL|slack section missing - run migrate-config.py --apply")

legacy_keys = ["slack_channel", "allowed_users", "owner_user_id", "batch_window_seconds"]
for key in legacy_keys:
    if key in config:
        print(f"FAIL|Legacy key '{key}' at top level - run migrate-config.py --apply")
PYTHON
    )

    while IFS= read -r line; do
        local status="${line%%|*}"
        local message="${line#*|}"
        case "$status" in
            PASS) log_pass "$message" ;;
            FAIL) log_fail "$message" ;;
            WARN) log_warn "$message" ;;
        esac
    done <<< "$output"
}

# ==============================================================================
# Test 3: Config Loading
# ==============================================================================
test_config_loading() {
    header "Test 3: Configuration Loading"

    local output
    output=$(PYTHONPATH="$REPO_ROOT/shared" python3 << 'PYTHON'
import sys
sys.path.insert(0, ".")

from jib_config import SlackConfig, GitHubConfig, LLMConfig, GatewayConfig

configs = [
    ("SlackConfig", SlackConfig),
    ("GitHubConfig", GitHubConfig),
    ("LLMConfig", LLMConfig),
    ("GatewayConfig", GatewayConfig),
]

for name, cls in configs:
    try:
        config = cls.from_env()
        print(f"PASS|{name} loads successfully")
    except Exception as e:
        print(f"FAIL|{name} failed to load: {e}")
PYTHON
    )

    while IFS= read -r line; do
        local status="${line%%|*}"
        local message="${line#*|}"
        case "$status" in
            PASS) log_pass "$message" ;;
            FAIL) log_fail "$message" ;;
        esac
    done <<< "$output"
}

# ==============================================================================
# Test 4: Validation
# ==============================================================================
test_validation() {
    header "Test 4: Configuration Validation"

    local output
    output=$(PYTHONPATH="$REPO_ROOT/shared" python3 << 'PYTHON'
from jib_config import SlackConfig, GitHubConfig, LLMConfig, GatewayConfig

def test_validation(name, config):
    result = config.validate()
    if result.is_valid:
        print(f"PASS|{name} validates successfully")
    else:
        for error in result.errors:
            print(f"FAIL|{name}: {error}")
    for warning in result.warnings:
        print(f"WARN|{name}: {warning}")

test_validation("SlackConfig", SlackConfig.from_env())
test_validation("GitHubConfig", GitHubConfig.from_env())
test_validation("LLMConfig", LLMConfig.from_env())
test_validation("GatewayConfig", GatewayConfig.from_env())
PYTHON
    )

    while IFS= read -r line; do
        local status="${line%%|*}"
        local message="${line#*|}"
        case "$status" in
            PASS) log_pass "$message" ;;
            FAIL) log_fail "$message" ;;
            WARN) log_warn "$message" ;;
        esac
    done <<< "$output"
}

# ==============================================================================
# Test 5: Token Formats
# ==============================================================================
test_token_formats() {
    header "Test 5: Token Format Validation"

    local output
    output=$(PYTHONPATH="$REPO_ROOT/shared" python3 << 'PYTHON'
from jib_config import SlackConfig, GitHubConfig, LLMConfig

slack = SlackConfig.from_env()
github = GitHubConfig.from_env()
llm = LLMConfig.from_env()

if slack.bot_token:
    if slack.bot_token.startswith("xoxb-"):
        print("PASS|Slack bot token has correct prefix (xoxb-)")
    else:
        print(f"FAIL|Slack bot token has wrong prefix: {slack.bot_token[:8]}...")
else:
    print("SKIP|Slack bot token not configured")

if slack.app_token:
    if slack.app_token.startswith("xapp-"):
        print("PASS|Slack app token has correct prefix (xapp-)")
    else:
        print(f"FAIL|Slack app token has wrong prefix: {slack.app_token[:8]}...")
else:
    print("SKIP|Slack app token not configured")

if github.token:
    valid_prefixes = ["ghp_", "github_pat_", "ghs_", "gho_"]
    if any(github.token.startswith(p) for p in valid_prefixes):
        print("PASS|GitHub token has valid prefix")
    else:
        print(f"FAIL|GitHub token has unrecognized prefix: {github.token[:8]}...")
else:
    print("SKIP|GitHub token not configured")

if llm.anthropic_api_key:
    if llm.anthropic_api_key.startswith("sk-ant-"):
        print("PASS|Anthropic API key has correct prefix (sk-ant-)")
    else:
        print(f"FAIL|Anthropic key has wrong prefix: {llm.anthropic_api_key[:8]}...")
else:
    print("SKIP|Anthropic API key not configured")
PYTHON
    )

    while IFS= read -r line; do
        local status="${line%%|*}"
        local message="${line#*|}"
        case "$status" in
            PASS) log_pass "$message" ;;
            FAIL) log_fail "$message" ;;
            SKIP) log_info "$message" ;;
        esac
    done <<< "$output"
}

# ==============================================================================
# Test 6: Health Checks
# ==============================================================================
test_health_checks() {
    if $SKIP_HEALTH; then
        header "Test 6: Health Checks (SKIPPED)"
        log_info "Use without --skip-health to run API connectivity tests"
        return
    fi

    header "Test 6: Health Checks (API Connectivity)"

    log_info "Testing connectivity to configured services..."

    local output
    output=$(PYTHONPATH="$REPO_ROOT/shared" python3 << 'PYTHON'
from jib_config import SlackConfig, GitHubConfig, GatewayConfig

def test_health(name, config):
    if not hasattr(config, 'health_check'):
        print(f"SKIP|{name}: No health check method")
        return

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
    test_health("Slack API", slack)
else:
    print("SKIP|Slack API: No token configured")

github = GitHubConfig.from_env()
if github.token:
    test_health("GitHub API", github)
else:
    print("SKIP|GitHub API: No token configured")

gateway = GatewayConfig.from_env()
test_health("Gateway", gateway)
PYTHON
    )

    while IFS= read -r line; do
        local status="${line%%|*}"
        local message="${line#*|}"
        case "$status" in
            PASS) log_pass "$message" ;;
            FAIL) log_fail "$message" ;;
            WARN) log_warn "$message" ;;
            SKIP) log_info "$message" ;;
        esac
    done <<< "$output"
}

# ==============================================================================
# Test 7: Service Imports
# ==============================================================================
test_service_imports() {
    header "Test 7: Service Module Imports"

    # Test that migrated services can import the new framework
    if python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT/shared')
sys.path.insert(0, '$REPO_ROOT/host-services/shared')
from jib_config import SlackConfig
from jib_config.utils import load_yaml_file
config = SlackConfig.from_env()
" 2>/dev/null; then
        log_pass "Slack services can import jib_config"
    else
        log_fail "Slack services cannot import jib_config"
    fi

    # Test CLI tool
    if python3 -c "
import sys
sys.path.insert(0, '$REPO_ROOT/shared')
from jib_config.cli import main
" 2>/dev/null; then
        log_pass "jib-config CLI imports successfully"
    else
        log_fail "jib-config CLI import failed"
    fi
}

# ==============================================================================
# Summary
# ==============================================================================
print_summary() {
    header "Test Summary"

    local total=$((TESTS_PASSED + TESTS_FAILED))

    echo ""
    echo -e "  Total tests:  $total"
    echo -e "  ${GREEN}Passed:${NC}       $TESTS_PASSED"
    echo -e "  ${RED}Failed:${NC}       $TESTS_FAILED"
    echo ""

    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN} ✓ All tests passed! Configuration is working correctly.${NC}"
        echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
        return 0
    else
        echo -e "${RED}═══════════════════════════════════════════════════════════${NC}"
        echo -e "${RED} ✗ Some tests failed. See details above.${NC}"
        echo -e "${RED}═══════════════════════════════════════════════════════════${NC}"
        echo ""
        echo "If you haven't migrated yet, run:"
        echo "  ./scripts/migrate-config.py --apply"
        echo ""
        return 1
    fi
}

# ==============================================================================
# Main
# ==============================================================================
main() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║       JIB Configuration Integration Tests                 ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"

    test_config_files
    parse_structure_results
    test_config_loading
    test_validation
    test_token_formats
    test_health_checks
    test_service_imports

    print_summary
}

main "$@"
