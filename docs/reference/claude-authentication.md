# Claude Code Authentication in Containers

## Summary

We investigated using token-based authentication for Claude Code in containerized environments but found it's not currently supported by Claude Code CLI.

## What We Tried

### Approach 1: CLAUDE_CODE_OAUTH_TOKEN Environment Variable
- **Goal**: Use `claude setup-token` to generate a long-lived token, pass it via env var
- **Implementation**:
  - User runs `claude setup-token` to get token
  - Token stored in `~/.jib/claude_token`
  - Container launched with `-e CLAUDE_CODE_OAUTH_TOKEN=<token>`
- **Result**: ❌ Failed
- **Findings**:
  - Claude Code CLI doesn't recognize or use the `CLAUDE_CODE_OAUTH_TOKEN` environment variable for authentication
  - `claude --help` works (doesn't require auth)
  - `claude --print` works (doesn't require auth)
  - Interactive `claude` mode requires OAuth credentials file, not env var

### Approach 2: Credentials File with Token
- **Goal**: Create `~/.claude/.credentials.json` with token as `accessToken`
- **Result**: ❌ Not attempted (Claude Code likely validates token format/source)
- **Reasoning**:
  - The token from `claude setup-token` is meant for a different purpose
  - Claude Code expects full OAuth flow with proper token structure
  - Simply inserting token into credentials file unlikely to work

## Current Authentication Challenges

### OAuth in Containers/SSH
1. **Scope Issues**: OAuth via copy/paste doesn't grant `user:sessions:claude_code` scope
2. **Session Binding**: OAuth credentials appear tied to specific sessions/environments
3. **Container Ephemeral Nature**: Credentials from one container don't transfer to new containers reliably

### What Works
- ✅ Authenticating inside a long-running container (interactive `jib` session)
- ✅ `claude --print` mode (doesn't require authentication)

### What Doesn't Work
- ❌ Token-based authentication via environment variable
- ❌ Copying OAuth credentials from container → host → new container
- ❌ OAuth with full scopes in SSH/remote environments (copy/paste flow)

## Current Recommendation

**For james-in-a-box:**
1. Use `claude --print` mode for automated tasks (incoming-processor)
2. Document that interactive `claude` sessions require container-based authentication
3. Accept that OAuth credentials need to be created fresh in each container session
4. Consider future: Wait for Anthropic to add proper token-based auth support

## Related Code
- `bin/jib` - Setup prompts for token (currently unused)
- `jib-container/Dockerfile` - Checks for `CLAUDE_CODE_OAUTH_TOKEN` (not functional)
- `jib-container/jib-tasks/slack/incoming-processor.py` - Uses `claude` with stdin (requires auth)

## Future Possibilities
- Anthropic may add official token-based authentication for CLI
- MCP (Model Context Protocol) servers might provide alternative auth mechanisms
- Container-to-container credential sharing improvements
