# Plan: Add Incognito Mode Configuration to setup.py

## Overview

Extend `setup.py` to support interactive configuration of incognito mode (added in PR #520). This allows users to configure personal GitHub identity for contributing to external repos where bot accounts may not be appropriate.

## Background

PR #520 added incognito mode to the gateway-sidecar with manual YAML configuration. This PR adds setup.py support for:
- `GITHUB_INCOGNITO_TOKEN` in secrets.env
- `incognito` section in repositories.yaml (github_user, git_name, git_email)
- Per-repo `auth_mode: incognito` in repo_settings

## Implementation Plan

### 1. Add Incognito Token Prompt to `prompt_github_auth()`

**Location**: `setup.py:1475-1640` (MinimalSetup.prompt_github_auth)

**Changes**:
- After prompting for GITHUB_TOKEN and GITHUB_READONLY_TOKEN, add optional prompt for GITHUB_INCOGNITO_TOKEN
- Only prompt if user indicates they want incognito mode
- Validate token starts with `ghp_`

**Flow**:
```
"Do you want to configure incognito mode for contributing to external repos?" [y/N]
If yes:
  "GitHub Incognito Token (ghp_...)"
```

### 2. Add Incognito User Configuration Prompt

**Location**: New method `prompt_incognito_config()` in MinimalSetup class

**Prompts**:
- GitHub username (for attribution) - required if incognito token provided
- Git author name (for commits) - optional, defaults to GitHub username
- Git author email - optional

**Returns**: Dict with `github_user`, `git_name`, `git_email` (empty strings if not configured)

### 3. Add Per-Repo Auth Mode Configuration

**Location**: Extend `prompt_repositories()` method

**Changes**:
- After collecting writable repos, prompt for which repos should use incognito mode
- Store in `repo_settings` dict with `auth_mode: incognito`

**Flow**:
```
"Which writable repos should use incognito mode (personal identity)?"
[List repos with checkboxes or comma-separated selection]
```

### 4. Update `write_repositories()` Method

**Location**: `ConfigManager.write_repositories()` (line 602-624)

**Changes**:
- Add `incognito` parameter (dict with github_user, git_name, git_email)
- Add `repo_settings` parameter (dict mapping repo to settings)
- Write both sections to repositories.yaml

**New signature**:
```python
def write_repositories(
    self,
    writable: list[str],
    readable: list[str],
    github_username: str = "",
    local_repos: list[str] | None = None,
    incognito: dict[str, str] | None = None,
    repo_settings: dict[str, dict] | None = None,
):
```

### 5. Update `load_repositories()` Method

**Location**: `ConfigManager.load_repositories()` (line 591-600)

**Changes**:
- Return `incognito` and `repo_settings` in the loaded dict

### 6. Handle Update Mode

**Location**: Throughout MinimalSetup methods

**Changes**:
- Show existing incognito configuration in update mode
- Allow modification or keeping existing values
- Mask existing token when displaying

### 7. Update Secrets Groups

**Location**: `ConfigManager.write_secrets()` (line 529-580) and `ConfigMigrator._write_secrets()` (line 428-478)

**Changes**:
- Add `GITHUB_INCOGNITO_TOKEN` to the "GitHub" secrets group

## Files Modified

1. `setup.py` - Main implementation

## Testing Plan

1. Fresh install: Run `./setup.py`, configure incognito mode, verify repositories.yaml and secrets.env
2. Update mode: Run `./setup.py --update`, verify existing incognito config shown and modifiable
3. Skip incognito: Run setup, decline incognito, verify no incognito sections written
4. Partial config: Configure token but no repos, verify incognito section present but no repo_settings

## Example Output

After setup, `~/.config/jib/repositories.yaml` should contain:

```yaml
github_username: jwbron
writable_repos:
  - jwbron/james-in-a-box
  - Khan/webapp

incognito:
  github_user: jwbron
  git_name: "James Wies"
  git_email: "jwbron@example.com"

repo_settings:
  Khan/webapp:
    auth_mode: incognito
```

And `~/.config/jib/secrets.env` should contain:

```bash
# GitHub
GITHUB_TOKEN="ghp_..."
GITHUB_INCOGNITO_TOKEN="ghp_..."
```

## Notes

- Incognito mode is entirely optional; setup works without it
- The incognito token must be a PAT for the user's personal account (not a GitHub App token)
- Per PR #520 design: incognito mode cannot create PRs (human must create via GitHub UI)
