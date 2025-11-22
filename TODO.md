# TODO

## Active Issues

### OAuth Credentials Not Copying to Container
**Status:** Open - Need to Force Host Re-authentication
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

**Blocker:**
Deleting `~/.claude/.credentials.json` on host does NOT force re-authentication. Claude Code still logs in without prompting. Credentials appear to be cached elsewhere (possibly in `~/.claude/session-env/` directories or in-memory).

**Next Steps:**
1. Find how to force Claude Code to re-authenticate with new scopes on host
2. Options to investigate:
   - Clear `~/.claude/session-env/` directories
   - Find if there's a `claude logout` or `claude clear-auth` command
   - Check if newer Claude Code version has scope refresh capability
   - Contact Anthropic support for how to request additional scopes

**Location:**
- Dockerfile: lines 159-168 (working correctly)
- jib script: lines 539-543 (working correctly)

**Verified:**
1. ✓ Credentials file IS mounted to `/opt/host-claude-credentials.json`
2. ✓ Docker run command mounts credentials correctly
3. ✓ File permissions are correct (600)
4. ✓ File is copied to container user's .claude directory
5. ✗ Host credentials missing `user:sessions:claude_code` scope
6. ✗ Cannot force host re-authentication (credentials cached elsewhere)

**References:**
- Investigated: 2025-11-22

---

## Completed

(Move completed items here with completion date)
