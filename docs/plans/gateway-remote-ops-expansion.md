# Plan: Gateway Remote Operations Expansion

## Context

PR #570 added gateway support for `git fetch` and `git ls-remote` to enable authenticated access to private repos. During review, two architectural improvements were identified:

1. **Scope expansion**: Route ALL git remote operations through the gateway, not just fetch/ls-remote
2. **Security hardening**: Use explicit allowlists instead of blocklists for command/flag validation

This plan covers implementing both improvements **within this PR** rather than splitting across multiple PRs.

## Current State (After Implementation)

- `git push` → routed through gateway (`/api/v1/git/push`)
- `git fetch` → routed through gateway (`/api/v1/git/fetch`)
- `git ls-remote` → routed through gateway (`/api/v1/git/fetch`)
- `git pull` → routed through gateway (fetch via gateway, merge locally)
- `git remote update` → routed through gateway (converted to fetch --all)
- `git clone` → NOT routed (deferred - containers receive pre-cloned repos)

## Security Fixes (Implemented)

These fixes from the self-review have been implemented:

- [x] **Path validation for `repo_path`** - Added `validate_repo_path()` using `os.path.realpath()` + prefix check against `ALLOWED_REPO_PATHS`
- [x] **`try/finally` for credential file cleanup** - Both `git_push` and `git_fetch` now use proper cleanup in finally blocks
- [x] **Module-level tempfile import** - `import tempfile` is at module level (line 33)

## Proposed Changes

### Phase 1: Shared Helper Functions

Extract common patterns into reusable helpers:

```python
# gateway-sidecar/gateway.py - new helper functions

def create_credential_helper(token_str: str, env: dict) -> tuple[str, dict]:
    """
    Create temporary credential helper script for git authentication.

    Returns:
        (credential_helper_path, updated_env)
    """
    askpass_script = '''#!/bin/bash
if [[ "$1" == *"Username"* ]]; then
    echo "$GIT_USERNAME"
elif [[ "$1" == *"Password"* ]]; then
    echo "$GIT_PASSWORD"
fi
'''
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="git-askpass-")
    try:
        os.fchmod(fd, 0o700)
        os.write(fd, askpass_script.encode())
    finally:
        os.close(fd)

    env = env.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_USERNAME"] = "x-access-token"
    env["GIT_PASSWORD"] = token_str
    env["GIT_ASKPASS"] = path
    return path, env


def cleanup_credential_helper(path: str | None) -> None:
    """Safely clean up credential helper file."""
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass


def get_token_for_repo(repo: str) -> tuple[str | None, str, str]:
    """
    Get authentication token for a repository.

    Returns:
        (token_str, auth_mode, error_message)
    """
    auth_mode = get_auth_mode(repo)
    github = get_github_client(mode=auth_mode)

    if auth_mode == "incognito":
        token_str = github.get_incognito_token()
        if not token_str:
            return None, auth_mode, "Incognito token not available"
    else:
        token = github.get_token()
        if not token:
            return None, auth_mode, "GitHub token not available"
        token_str = token.token

    return token_str, auth_mode, ""
```

### Phase 2: Add `git pull` Support

**Implementation in `jib-container/scripts/git`:**

```bash
pull)
    # git pull = git fetch + git merge
    # Route the fetch part through gateway, then merge locally

    # Parse args to extract remote and branch
    remote="origin"
    merge_args=()
    fetch_args=()
    skip_next=false
    remote_seen=false

    for arg in "${args_after_globals[@]}"; do
        if $skip_next; then
            # Previous arg was a flag that takes a value
            case "$prev_flag" in
                --depth|--deepen|--shallow-since|--shallow-exclude)
                    fetch_args+=("$prev_flag" "$arg")
                    ;;
                *)
                    merge_args+=("$prev_flag" "$arg")
                    ;;
            esac
            skip_next=false
            continue
        fi

        case "$arg" in
            pull) continue ;;
            --depth|--deepen|--shallow-since|--shallow-exclude)
                prev_flag="$arg"
                skip_next=true
                ;;
            --rebase|--no-rebase|--ff|--no-ff|--ff-only|--squash|--no-squash)
                merge_args+=("$arg")
                ;;
            --all|--tags|--prune|--no-tags)
                fetch_args+=("$arg")
                ;;
            -*)
                # Unknown flag - assume it's for merge
                merge_args+=("$arg")
                ;;
            *)
                if [ "$remote_seen" = "false" ]; then
                    remote="$arg"
                    remote_seen=true
                else
                    # Branch specification
                    fetch_args+=("$arg")
                    merge_args+=("FETCH_HEAD")
                fi
                ;;
        esac
    done

    # Step 1: Fetch via gateway
    if ! check_gateway_available; then
        echo "ERROR: Gateway required for pull operation" >&2
        exit 1
    fi

    if ! fetch_via_gateway "fetch" "$remote" "$git_work_dir" "${fetch_args[@]}"; then
        exit 1
    fi

    # Step 2: Merge locally
    exec "$REAL_GIT" merge "${merge_args[@]}"
    ;;
```

### Phase 3: Allowlist Validation

#### 3a. Git Flag Normalization

Handle short flag forms by normalizing to long forms:

```python
# gateway-sidecar/git_validation.py

FLAG_NORMALIZATION = {
    # fetch/ls-remote
    "-a": "--all",
    "-t": "--tags",
    "-p": "--prune",
    "-v": "--verbose",
    "-q": "--quiet",
    "-j": "--jobs",
    # push
    "-f": "--force",
    "-d": "--delete",
    "-u": "--set-upstream",
    "-n": "--dry-run",
}

def normalize_flag(flag: str) -> str:
    """Normalize short flags to long form for consistent validation."""
    # Handle -X=value format
    if "=" in flag:
        base, value = flag.split("=", 1)
        normalized = FLAG_NORMALIZATION.get(base, base)
        return f"{normalized}={value}"
    return FLAG_NORMALIZATION.get(flag, flag)
```

#### 3b. gh API Path Validation

```python
import re

GH_API_ALLOWED_PATHS = [
    # PR operations
    re.compile(r"^repos/[^/]+/[^/]+/pulls$"),                    # List PRs
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+$"),                # View PR
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/comments$"),       # PR comments
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/reviews$"),        # PR reviews
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/reviews/\d+$"),    # Specific review
    # Issue operations
    re.compile(r"^repos/[^/]+/[^/]+/issues$"),                   # List issues
    re.compile(r"^repos/[^/]+/[^/]+/issues/\d+$"),               # View issue
    re.compile(r"^repos/[^/]+/[^/]+/issues/\d+/comments$"),      # Issue comments
    # Repository info
    re.compile(r"^repos/[^/]+/[^/]+$"),                          # Repo info
    re.compile(r"^repos/[^/]+/[^/]+/branches$"),                 # List branches
    re.compile(r"^repos/[^/]+/[^/]+/commits$"),                  # List commits
]

def validate_gh_api_path(path: str, method: str = "GET") -> tuple[bool, str]:
    """
    Validate gh api path against allowlist.

    Returns:
        (is_valid, error_message)
    """
    # Only GET and POST allowed
    if method not in ("GET", "POST"):
        return False, f"HTTP method '{method}' not allowed for gh api"

    # Check against allowed patterns
    for pattern in GH_API_ALLOWED_PATHS:
        if pattern.match(path):
            return True, ""

    return False, f"API path '{path}' not in allowlist"
```

### Phase 4: Git Wrapper Updates

Changes needed in `jib-container/scripts/git`:

| Line Range | Change |
|------------|--------|
| 453-532 | Push handling - already complete |
| 533-583 | Fetch handling - already complete |
| 584-634 | ls-remote handling - already complete |
| NEW | Add pull handling (Phase 2) |
| NEW | Add `remote update` → `fetch --all` conversion |

**`remote update` conversion:**

```bash
remote)
    # ... existing remote subcommand handling ...
    case "$subcmd" in
        update)
            # Convert to fetch --all
            if ! check_gateway_available; then
                exec "$REAL_GIT" "$@"
            fi
            fetch_via_gateway "fetch" "--all" "$git_work_dir"
            exit $?
            ;;
        # ... rest unchanged ...
    esac
    ;;
```

### Phase 5: Unit Tests

**File: `gateway-sidecar/tests/test_git_validation.py`**

```python
import pytest
from gateway import validate_repo_path, sanitize_git_args

class TestRepoPathValidation:
    def test_valid_repos_path(self):
        valid, _ = validate_repo_path("/home/jib/repos/myrepo")
        assert valid

    def test_valid_worktree_path(self):
        valid, _ = validate_repo_path("/home/jib/.jib-worktrees/jib-123/repo")
        assert valid

    def test_path_traversal_blocked(self):
        valid, error = validate_repo_path("/home/jib/repos/../../../etc/passwd")
        assert not valid
        assert "allowed directories" in error

    def test_absolute_escape_blocked(self):
        valid, error = validate_repo_path("/etc/passwd")
        assert not valid

    def test_symlink_escape_blocked(self, tmp_path):
        # Create symlink pointing outside allowed dirs
        # This test requires filesystem setup
        pass

class TestGitArgsSanitization:
    def test_upload_pack_blocked(self):
        valid, error, _ = sanitize_git_args(["--upload-pack=/evil/cmd"])
        assert not valid
        assert "Blocked" in error

    def test_exec_blocked(self):
        valid, error, _ = sanitize_git_args(["--exec=/evil/cmd"])
        assert not valid

    def test_short_u_blocked(self):
        valid, error, _ = sanitize_git_args(["-u=/evil/cmd"])
        assert not valid

    def test_normal_args_allowed(self):
        valid, _, args = sanitize_git_args(["--tags", "--prune", "main"])
        assert valid
        assert args == ["--tags", "--prune", "main"]

    def test_non_string_rejected(self):
        valid, error, _ = sanitize_git_args([{"nested": "object"}])
        assert not valid
        assert "Invalid argument type" in error
```

### Phase 6: Integration Testing (Human Required)

#### Pre-requisites
- Fresh jib container in incognito mode
- Access to a private test repository

#### Test Matrix

| # | Test | Command | Expected Result | Human Verified |
|---|------|---------|-----------------|----------------|
| 1 | Basic fetch | `git fetch origin` | Success, refs updated | [ ] |
| 2 | Fetch with tags | `git fetch --tags origin` | Success, tags fetched | [ ] |
| 3 | Blocked flag | `git fetch --upload-pack=evil origin` | Rejected with clear error | [ ] |
| 4 | Pull operation | `git pull origin main` | Success (fetch via gateway, merge local) | [ ] |
| 5 | Remote update | `git remote update` | Success (converted to fetch --all) | [ ] |
| 6 | ls-remote | `git ls-remote origin` | Success, refs listed | [ ] |
| 7 | Push owned branch | `git push origin jib-feature` | Success | [ ] |
| 8 | Push blocked branch | `git push origin main` | Rejected (not owned) | [ ] |
| 9 | PR create | `gh pr create ...` | Success | [ ] |
| 10 | PR merge blocked | `gh pr merge ...` | Rejected by policy | [ ] |

#### Security Negative Tests

| # | Test | Input | Expected |
|---|------|-------|----------|
| S1 | Path traversal in repo_path | `{"repo_path": "/etc/passwd"}` | 403 with clear error |
| S2 | Path traversal via symlink | `{"repo_path": "/home/jib/repos/evil-symlink"}` | 403 if symlink points outside |
| S3 | Config override attempt | `git fetch -c protocol.file.allow=always origin` | Rejected |
| S4 | Credential file persistence | Kill gateway mid-operation | No credential files in /tmp |

#### Sign-off

Human reviewer should run through test matrix and confirm all pass before merge.

## Implementation Order

All changes are being implemented in this PR (#570) rather than split across multiple PRs, because:

1. The security fixes and allowlist validation are tightly coupled - shipping them together ensures consistent security posture
2. The `git pull` and `git remote update` support are small additions once the foundation is in place
3. Avoids shipping a partial solution that still has known security gaps

**Checklist:**
- [x] Security fixes (path validation, try/finally cleanup, module-level import)
- [x] Shared helper functions (create_credential_helper, cleanup_credential_helper, get_token_for_repo)
- [x] `git pull` support in wrapper (fetch via gateway, merge locally)
- [x] `git remote update` support in wrapper (converted to fetch --all)
- [x] Allowlist validation
  - [x] FLAG_NORMALIZATION defined
  - [x] normalize_flag() called in validate_git_args() before validation
  - [x] GIT_ALLOWED_COMMANDS per-operation allowlists defined
  - [x] validate_git_args() implemented and called in git_fetch()
  - [x] GH_API_ALLOWED_PATHS defined
  - [x] validate_gh_api_path() called in gh_execute() for 'gh api' commands
- [x] Error messages include allowed commands/flags for guidance
- [x] Unit tests for validation functions (test_git_validation.py)
- [ ] Integration test sign-off (human required)

## Open Questions

1. Should we allow `--recurse-submodules` for fetch? (Potential for additional network calls)
   - **Recommendation**: Allow, as submodule fetches will also route through gateway
2. Should `gh api` be further restricted or is path-based allowlist sufficient?
   - **Recommendation**: Path-based allowlist is sufficient for now
3. Do we need `git clone` support or is host-side clone sufficient?
   - **Recommendation**: Defer - containers receive pre-cloned repos

## References

- PR #570: Initial git fetch/ls-remote support
- Self-review comment #3802509018: Scope expansion recommendation
- Self-review comment #3802513340: Allowlist security recommendation
