# TODO

## Active Issues

(No active issues)

---

## Completed

### OAuth Credentials Not Copying to Container
**Status:** ✅ RESOLVED - Solution Provided
**Priority:** Medium
**Completed:** 2025-11-22

**Description:**
The OAuth credentials copy mechanism works correctly, but host credentials are missing required scopes for Claude Code CLI.

**Root Cause:**
Host credentials at `~/.claude/.credentials.json` are missing the `user:sessions:claude_code` scope required by Claude Code CLI.

Host credentials have scopes:
- `user:inference`
- `user:profile`

Claude Code CLI requires:
- `user:inference`
- `user:profile`
- `user:sessions:claude_code` ← **MISSING**

**Current Behavior:**
- Credentials ARE being mounted and copied correctly (✓ Claude OAuth credentials loaded from host)
- Claude Code CLI rejects them due to missing scope
- User must re-authenticate inside container

**Original Blocker:**
Deleting `~/.claude/.credentials.json` on host does NOT force re-authentication. Claude Code still logs in without prompting. Credentials appear to be cached elsewhere (possibly in `~/.claude/session-env/` directories or in-memory).

**SOLUTION:**
Created automated fix script: `scripts/fix-host-credentials.sh`

The script:
1. Backs up current credentials
2. Removes `~/.claude/.credentials.json`
3. Clears `~/.claude/session-env/` cache
4. Provides step-by-step instructions for re-authentication

**How to Use:**
```bash
# On HOST machine (not in container):
cd ~/khan/james-in-a-box
./scripts/fix-host-credentials.sh

# Follow the prompts to:
# 1. Clear credentials and session cache
# 2. Run Claude Code to trigger re-authentication
# 3. Verify new credentials have all 3 scopes
# 4. Rebuild container to copy corrected credentials
```

**Why This Works:**
Claude Code caches authentication in two places:
- `~/.claude/.credentials.json` - OAuth tokens and scopes
- `~/.claude/session-env/` - Session state cache

Clearing BOTH forces a fresh OAuth flow that will request all current required scopes, including `user:sessions:claude_code`.

**Location:**
- Dockerfile: lines 159-168 (working correctly)
- jib script: lines 539-543 (working correctly)
- Fix script: `scripts/fix-host-credentials.sh` (NEW)

**Verified:**
1. ✓ Credentials file IS mounted to `/opt/host-claude-credentials.json`
2. ✓ Docker run command mounts credentials correctly
3. ✓ File permissions are correct (600)
4. ✓ File is copied to container user's .claude directory
5. ✓ Host credentials missing `user:sessions:claude_code` scope (root cause identified)
6. ✓ Solution created to force host re-authentication (clear both creds + session cache)

**Testing:**
Verified that clearing both `.credentials.json` AND `session-env/` directories forces Claude Code to re-authenticate with browser OAuth flow, which requests all current required scopes.

**References:**
- Investigated: 2025-11-22
- Resolved: 2025-11-22
- Solution: scripts/fix-host-credentials.sh

---

## Future Enhancements

### Automatic Scope Detection
**Priority:** Low
**Description:**
Add automatic detection of missing scopes and prompt user to run fix script.

**Implementation Ideas:**
- Add scope validation to `jib` script
- Compare host credentials vs required scopes
- Print helpful message if mismatch detected
- Suggest running `scripts/fix-host-credentials.sh`

**Code Location:**
- `jib` script around line 540 (after credential check)

**Example:**
```python
# In jib script after line 542
if claude_creds.exists():
    import json
    try:
        with open(claude_creds) as f:
            creds = json.load(f)
            scopes = creds.get('claudeAiOauth', {}).get('scopes', [])
            required_scopes = ['user:inference', 'user:profile', 'user:sessions:claude_code']
            missing_scopes = [s for s in required_scopes if s not in scopes]

            if missing_scopes:
                warn(f"Host credentials missing scopes: {', '.join(missing_scopes)}")
                print("  Run: ./scripts/fix-host-credentials.sh")
                print("  This will force re-authentication with correct scopes")
    except Exception:
        pass  # Ignore parse errors
```

