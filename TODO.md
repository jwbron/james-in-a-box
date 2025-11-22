# TODO

## Active Issues

### OAuth Credentials Not Copying to Container
**Status:** Open
**Priority:** Medium
**Description:**
The OAuth credentials copy in the Dockerfile entrypoint is not working. Claude credentials are not being synced from host to container.

**Current Behavior:**
- Dockerfile line 157-165 attempts to copy `/opt/host-claude-credentials.json` to container
- Credentials file not being found/copied
- Users see: "⚠ No OAuth credentials found - you'll need to authenticate with browser"

**Expected Behavior:**
- Host credentials at `~/.claude/.credentials.json` should be mounted/copied
- Container should have credentials at `~/.claude/.credentials.json`
- No re-authentication needed in container

**Location:**
- Dockerfile: lines 156-165
- Entrypoint script within Dockerfile

**Investigation Needed:**
1. Check if credentials file is being mounted to `/opt/host-claude-credentials.json`
2. Verify docker run command mounts the credentials correctly
3. Check file permissions (should be 600)
4. Verify path on host: `~/.claude/.credentials.json` exists

**References:**
- User feedback: "the auth copy still doesn't work"

---

## Completed

(Move completed items here with completion date)
