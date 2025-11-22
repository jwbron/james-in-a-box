# TODO

## Active Issues

### OAuth Credentials Not Copying to Container
**Status:** RESOLVED - Root Cause Identified
**Priority:** Medium
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

**Solution:**
User needs to re-authenticate on the HOST machine to get credentials with the correct scopes:
```bash
# On host (outside container)
claude
# This will trigger OAuth flow with correct scopes
# After authentication, restart container - credentials will work
```

**Location:**
- Dockerfile: lines 159-168 (working correctly)
- jib script: lines 539-543 (working correctly)

**Verified:**
1. ✓ Credentials file IS mounted to `/opt/host-claude-credentials.json`
2. ✓ Docker run command mounts credentials correctly
3. ✓ File permissions are correct (600)
4. ✓ File is copied to container user's .claude directory
5. ✗ Host credentials missing `user:sessions:claude_code` scope

**References:**
- Investigated: 2025-11-22

---

## Completed

(Move completed items here with completion date)
