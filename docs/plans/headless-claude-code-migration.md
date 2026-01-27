# Plan: Switch Slack Workflow from SDK to Headless Claude Code

## Context

The jib slack workflow and all automated processors currently use the `claude_agent_sdk` Python library for programmatic Claude execution. This proposal switches to subprocess-based execution using `claude --print` (headless mode).

## Motivation

- **Simpler dependency**: No SDK package to maintain or update
- **OAuth support**: Native OAuth authentication via Claude Code CLI
- **Consistent infrastructure**: Same CLI used everywhere in jib (interactive and programmatic)
- **Flexibility**: Works with both API key and OAuth auth methods
- **Reduced complexity**: Single execution path for all Claude invocations

## Current State

**File**: `jib-container/llm/claude/runner.py`
- Uses `claude_agent_sdk` Python library (lines 67-76)
- `async for message in sdk.query(...)` with streaming callbacks
- SDK installed in Dockerfile line 64: `pip install claude-agent-sdk`

**Callers** (16 files use `run_agent`):
- `jib-tasks/slack/incoming-processor.py` - Main Slack workflow
- `jib-tasks/github/pr-analyzer.py` - PR analysis
- All other processors in `jib-tasks/`

## Target State

**Headless Claude Code**: subprocess call to `claude --print` with stdin input

```bash
claude --print --dangerously-skip-permissions --model opus --output-format stream-json
```

Key characteristics:
- Prompt passed via stdin (safe for special characters, no length limits)
- Streaming output via `--output-format stream-json`
- Same `AgentResult` interface preserved for all callers

## Files to Modify

| File | Change |
|------|--------|
| `jib-container/llm/claude/runner.py` | Replace SDK with subprocess (main change) |
| `jib-container/Dockerfile` | Remove `claude-agent-sdk` from line 64 |
| `shared/jib_logging/wrappers/claude.py` | Update outdated comment about `--print` |

## Implementation Details

### 1. Replace `runner.py` Core Logic

**Key changes**:
- Remove `import claude_agent_sdk as sdk`
- Use `asyncio.create_subprocess_exec()` for async subprocess
- Parse `stream-json` output for text extraction and metadata
- Preserve timeout handling with `asyncio.timeout()`
- Keep same function signatures (`run_agent()`, `run_agent_async()`)

**Command construction**:
```python
cmd = [
    "claude",
    "--print",
    "--dangerously-skip-permissions",
    "--model", model,
    "--output-format", "stream-json",
]
```

**Stream-json parsing**: Events contain:
- `{"type": "assistant", "message": {...}}` - Text content
- `{"type": "result", ...}` - Final result
- Model/usage metadata in events

### 2. Remove SDK from Dockerfile

```dockerfile
# Before (line 61-66):
RUN pip3 install --no-cache-dir \
    pyyaml \
    requests \
    claude-agent-sdk \
    cryptography \
    PyJWT

# After:
RUN pip3 install --no-cache-dir \
    pyyaml \
    requests \
    cryptography \
    PyJWT
```

### 3. Update ClaudeWrapper Comment

The comment "Never use --print flag which creates a restricted session" in `shared/jib_logging/wrappers/claude.py` is outdated. The `--print --dangerously-skip-permissions` combination works correctly.

## Streaming Support

**Current SDK**: Provides `on_output` callback, called for each text chunk

**Headless approach**: Read stdout line-by-line from subprocess
```python
async for line in process.stdout:
    event = json.loads(line)
    text = extract_text(event)
    if text and on_output:
        on_output(text)
```

This preserves real-time log writing for long-running tasks (up to 2 hours).

## API Compatibility

No changes to callers. Same interface preserved:
```python
result = run_agent(
    prompt="Fix the bug",
    cwd=Path.home() / "repos" / "my-repo",
    timeout=7200,
    model="opus",
    on_output=lambda text: log_file.write(text),
)
```

Returns same `AgentResult`:
- `success: bool`
- `stdout: str`
- `stderr: str`
- `returncode: int`
- `error: str | None`
- `metadata: dict | None` (includes model used)

## Verification Plan

1. **Unit test**: Mock subprocess, verify stream-json parsing
2. **Integration test**: Run `incoming-processor.py` with test message
3. **Timeout test**: Verify 2-hour timeout works correctly
4. **Streaming test**: Verify `on_output` callback receives chunks
5. **End-to-end**: Send Slack message, verify full workflow

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Stream-json format changes | Pin Claude Code version or add format detection |
| Subprocess overhead | Negligible vs API latency |
| Different error handling | Test error scenarios thoroughly |

## Decisions

- **Clean removal**: Remove SDK entirely (no fallback). Single code path, simpler maintenance.
- **OAuth**: Already supported via `ANTHROPIC_AUTH_METHOD` env var (added in PR #567)

## Related

- PR #567: Added `ANTHROPIC_AUTH_METHOD` config for OAuth support
- PR #576: Removed Claude Code Router and Gemini CLI support (simplified to Claude Code only)
- Commit 428a35e: Humanizer module switch to headless Claude Code pattern
