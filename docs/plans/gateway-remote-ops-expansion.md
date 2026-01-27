# Plan: Gateway Remote Operations Expansion

## Context

PR #570 added gateway support for `git fetch` and `git ls-remote` to enable authenticated access to private repos. During review, two architectural improvements were identified:

1. **Scope expansion**: Route ALL git remote operations through the gateway, not just fetch/ls-remote
2. **Security hardening**: Use explicit allowlists instead of blocklists for command/flag validation

This plan covers implementing both improvements.

## Current State

- `git push` → routed through gateway (`/api/v1/git/push`)
- `git fetch` → routed through gateway (`/api/v1/git/fetch`)
- `git ls-remote` → routed through gateway (`/api/v1/git/fetch`)
- `git pull` → NOT routed (fetch + merge, but fetch part goes direct)
- `git clone` → NOT routed
- `git remote update` → NOT routed

## Proposed Changes

### Phase 1: Consolidate Gateway Endpoint

Replace the separate `/api/v1/git/push` and `/api/v1/git/fetch` endpoints with a unified approach:

```
POST /api/v1/git/remote
{
    "repo_path": "/path/to/repo",
    "operation": "fetch|push|ls-remote|pull|clone",
    "remote": "origin",
    "args": ["--tags"],
    "ref": "main"  // for push
}
```

**Benefits:**
- Single code path for authentication
- Easier to add new operations
- Consistent validation

**Alternative:** Keep separate endpoints but share validation/auth logic. This maintains clearer API boundaries but has more code duplication.

**Recommendation:** Keep separate endpoints for now (push has different policy requirements than read operations). Extract shared logic into helper functions.

### Phase 2: Add Missing Remote Operations

#### 2a. `git pull` support

`git pull` = `git fetch` + `git merge`. Two options:

1. **Intercept and split**: Route fetch through gateway, then run merge locally
2. **Full proxy**: Route entire pull through gateway

**Recommendation:** Option 1 - intercept in git wrapper:
```bash
pull)
    # Extract remote/branch from args
    # Call fetch_via_gateway for the fetch part
    # Run local merge
```

#### 2b. `git clone` support

Clone is typically run once during setup, not by the jib container during normal operation. The container receives pre-cloned repos via volume mounts.

**Recommendation:** Low priority. Document that clone should be done on host or add if needed later.

#### 2c. `git remote update` support

Equivalent to `git fetch --all`.

**Recommendation:** Intercept and convert to `git fetch --all` which already goes through gateway.

### Phase 3: Implement Allowlist Validation

Replace the current blocklist approach with explicit allowlists.

#### 3a. Git Command Allowlist

```python
# gateway-sidecar/git_allowlist.py

GIT_ALLOWED_COMMANDS = {
    # Read operations
    "fetch": {
        "allowed_flags": [
            "--all", "--tags", "--prune", "--depth", "--shallow-since",
            "--shallow-exclude", "-j", "--jobs", "--no-tags", "--force",
            "-v", "--verbose", "-q", "--quiet", "--dry-run", "--recurse-submodules",
        ],
        "blocked_flags": ["--upload-pack", "-c", "--config"],
        "rate_limit": "git_fetch",
    },
    "ls-remote": {
        "allowed_flags": [
            "--heads", "--tags", "--refs", "--quiet", "-q", "--exit-code",
            "--get-url", "--sort", "--symref",
        ],
        "blocked_flags": ["--upload-pack", "-c", "--config"],
        "rate_limit": "git_fetch",
    },
    # Write operations
    "push": {
        "allowed_flags": [
            "--force", "-f", "--force-with-lease", "--tags", "--delete", "-d",
            "-u", "--set-upstream", "-v", "--verbose", "-q", "--quiet",
            "--dry-run", "--no-verify",
        ],
        "blocked_flags": ["--receive-pack", "-c", "--config"],
        "rate_limit": "git_push",
        "requires_branch_ownership": True,
    },
}

# Universal blocked flags (checked before allowed_flags)
ALWAYS_BLOCKED_FLAGS = [
    "--upload-pack",    # Arbitrary command execution
    "--receive-pack",   # Arbitrary command execution
    "--exec",           # Arbitrary command execution
    "-c",               # Config override (security bypass)
    "--config",         # Config override (security bypass)
]
```

#### 3b. Validation Function

```python
def validate_git_command(operation: str, args: list[str]) -> tuple[bool, str]:
    """
    Validate git command and arguments against allowlist.

    Returns:
        (is_valid, error_message)
    """
    if operation not in GIT_ALLOWED_COMMANDS:
        return False, f"Git operation '{operation}' is not allowed"

    config = GIT_ALLOWED_COMMANDS[operation]

    for arg in args:
        # Check universal blocks first
        for blocked in ALWAYS_BLOCKED_FLAGS:
            if arg.startswith(blocked):
                return False, f"Flag '{arg}' is not allowed for security reasons"

        # Check operation-specific blocks
        for blocked in config.get("blocked_flags", []):
            if arg.startswith(blocked):
                return False, f"Flag '{arg}' is not allowed for git {operation}"

        # For flags, verify they're in allowlist
        if arg.startswith("-"):
            flag_base = arg.split("=")[0]  # Handle --flag=value
            if flag_base not in config["allowed_flags"]:
                return False, f"Flag '{flag_base}' is not in allowlist for git {operation}"

    return True, ""
```

#### 3c. gh Command Allowlist

```python
GH_ALLOWED_COMMANDS = {
    "pr": {
        "create": ["--title", "--body", "--base", "--head", "--draft", "--label",
                   "--assignee", "--reviewer", "--milestone", "--web"],
        "view": ["--json", "--jq", "--comments", "--web"],
        "list": ["--state", "--limit", "--json", "--jq", "--author", "--label",
                 "--base", "--head", "--search"],
        "comment": ["--body", "--edit-last"],
        "edit": ["--title", "--body", "--base", "--add-label", "--remove-label",
                 "--add-assignee", "--remove-assignee", "--add-reviewer", "--remove-reviewer"],
        "close": ["--comment", "--delete-branch"],
        "reopen": [],
        "checks": ["--json", "--jq", "--watch", "--interval"],
        "diff": ["--color", "--patch"],
        "ready": [],
        "review": ["--approve", "--comment", "--request-changes", "--body"],
        # "merge" intentionally absent - blocked by policy
    },
    "issue": {
        "create": ["--title", "--body", "--label", "--assignee", "--milestone", "--web"],
        "view": ["--json", "--jq", "--comments", "--web"],
        "list": ["--state", "--limit", "--json", "--jq", "--author", "--label",
                 "--search", "--assignee"],
        "comment": ["--body", "--edit-last"],
        "edit": ["--title", "--body", "--add-label", "--remove-label",
                 "--add-assignee", "--remove-assignee"],
        "close": ["--comment", "--reason"],
        "reopen": [],
    },
    "api": {
        # API is powerful - only allow specific patterns
        "_allowed_paths": [
            r"^repos/[^/]+/[^/]+/pulls/\d+/comments$",  # PR comments
            r"^repos/[^/]+/[^/]+/pulls/\d+/reviews$",   # PR reviews
            r"^repos/[^/]+/[^/]+/issues/\d+/comments$", # Issue comments
        ],
        "_allowed_methods": ["GET", "POST"],
    },
}
```

### Phase 4: Update Git Wrapper

Update `jib-container/scripts/git` to:

1. Route `pull` through gateway (fetch part)
2. Convert `remote update` to `fetch --all`
3. Pass full argument list to gateway for validation

### Phase 5: Testing

#### Unit Tests (gateway-sidecar)
- `test_git_allowlist.py`: Validate allowlist logic
- Test blocked flags are rejected
- Test unknown flags are rejected
- Test valid commands pass

#### Integration Tests
- Test `git fetch` with various flags
- Test `git pull` works end-to-end
- Test blocked flags return clear errors
- Test `git remote update` converts correctly

## Implementation Order

1. **PR A**: Extract shared validation logic, add allowlist validation to existing endpoints
2. **PR B**: Add `git pull` support to wrapper
3. **PR C**: Add `git remote update` support
4. **PR D**: Add gh allowlist validation (if not already sufficient)

## Open Questions

1. Should we allow `--recurse-submodules` for fetch? (Potential for additional network calls)
2. Should `gh api` be further restricted or is path-based allowlist sufficient?
3. Do we need `git clone` support or is host-side clone sufficient?

## References

- PR #570: Initial git fetch/ls-remote support
- Self-review comment #3802509018: Scope expansion recommendation
- Self-review comment #3802513340: Allowlist security recommendation
