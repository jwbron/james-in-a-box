# Phase 0: Claude Code Credential Behavior Analysis

Test instructions for understanding how Claude Code validates credentials at startup.

## Preparation

First, back up your current credentials:

```bash
# Backup current state
cp -r ~/.claude ~/.claude.backup 2>/dev/null || echo "No .claude dir"
echo "Current ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:+set}"
```

---

## Test Set A: API Key Scenarios

### A1. No API key present
```bash
unset ANTHROPIC_API_KEY
rm -f ~/.claude/credentials.json 2>/dev/null
claude --version  # Does it start?
claude "hello"    # What error?
```

### A2. Malformed API key
```bash
export ANTHROPIC_API_KEY="not-a-real-key"
claude --version
claude "hello"
```

### A3. Correct format, invalid key
```bash
# API keys are typically sk-ant-api03-... format
export ANTHROPIC_API_KEY="sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
claude --version
claude "hello"
```

### A4. Trace network calls (API key)
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-testkey123"
strace -f -e trace=network claude "hello" 2>&1 | head -100
```

---

## Test Set B: OAuth Token Scenarios

### B1. OAuth only, no API key
```bash
unset ANTHROPIC_API_KEY
# Check what OAuth state looks like
cat ~/.claude/credentials.json 2>/dev/null || echo "No credentials.json"
claude --version
claude "hello"
```

### B2. Expired/invalid OAuth token
```bash
unset ANTHROPIC_API_KEY
# Create fake OAuth credentials
mkdir -p ~/.claude
echo '{"oauth_token": "fake-oauth-token", "expires_at": 0}' > ~/.claude/credentials.json
claude --version
claude "hello"
```

### B3. Valid format OAuth, invalid token
```bash
unset ANTHROPIC_API_KEY
# OAuth tokens are typically longer JWTs or opaque tokens
echo '{"oauth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IlRlc3QiLCJpYXQiOjE1MTYyMzkwMjJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"}' > ~/.claude/credentials.json
claude --version
claude "hello"
```

### B4. Trace network calls (OAuth)
```bash
unset ANTHROPIC_API_KEY
echo '{"oauth_token": "test-oauth-token"}' > ~/.claude/credentials.json
strace -f -e trace=network claude "hello" 2>&1 | head -100
```

---

## Test Set C: Priority/Precedence

### C1. Both API key and OAuth present
```bash
export ANTHROPIC_API_KEY="sk-ant-api03-testkey"
echo '{"oauth_token": "test-oauth-token"}' > ~/.claude/credentials.json
claude "hello"  # Which gets used? Check error message
```

---

## Cleanup & Restore

```bash
# Restore original state
rm -rf ~/.claude
cp -r ~/.claude.backup ~/.claude 2>/dev/null
# Re-export your real API key if needed
```

---

## Results

### Data to Record

For each test, document:

| Test | Starts? | Error Message | When error occurs (startup/first request) |
|------|---------|---------------|-------------------------------------------|
| A1   | Yes     | Prompts to login | First request (lazy validation)        |
| A2   | Yes     | Prompts to login | First request (no local format check)  |
| A3   | Yes     | Prompts to login | First request (server rejects, prompts login) |
| A4   | Yes     | Network calls to 160.79.104.10:443 (Anthropic API), then login prompt | Immediate API validation attempt on startup |
| B1   | Yes     | No credentials.json exists, prompts to login | First request (same as A1) |
| B2   |         |               |                                           |
| B3   |         |               |                                           |
| B4   |         |               |                                           |
| C1   |         |               |                                           |

### Key Questions to Answer

1. Does Claude Code validate credentials at startup or lazily on first API call?
2. Is validation local (format check) or remote (API call)?
3. What's the credential precedence: API key vs OAuth?
4. What are the exact error messages for each failure mode?
5. Can Claude Code start with no credentials at all?
6. What placeholder format (if any) would allow startup without real credentials?

### Findings Summary

**Startup behavior:** Claude Code starts without credentials (`--version` works), validates lazily on first API call.

**Validation timing:** Immediate API call to 160.79.104.10:443 when credentials are present. Falls back to login prompt on auth failure.

**Credential precedence:** TBD (didn't complete C1 test)

**Recommended approach for gateway injection:**

Use `claude setup-token` to generate a long-lived OAuth token, then inject via:
```bash
export CLAUDE_CODE_OAUTH_TOKEN=<token>
```

Benefits:
- Long-lived (1 year validity)
- Environment variable based (easy to inject into containers)
- No file writing required
- Works with Claude subscription
