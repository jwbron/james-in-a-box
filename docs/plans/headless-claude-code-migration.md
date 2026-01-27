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

## Stream-JSON Format

The `--output-format stream-json` emits newline-delimited JSON events. Example output:

```json
{"type":"system","subtype":"init","cwd":"/home/jib/repos","session_id":"abc123","tools":["Bash","Read","Write"]}
{"type":"assistant","message":{"id":"msg_01X","type":"message","role":"assistant","content":[{"type":"text","text":"I'll fix that bug."}],"model":"claude-opus-4-20250514","usage":{"input_tokens":150,"output_tokens":25}}}
{"type":"assistant","message":{"id":"msg_02Y","type":"message","role":"assistant","content":[{"type":"tool_use","id":"tu_01","name":"Read","input":{"file_path":"/app/main.py"}}],"model":"claude-opus-4-20250514"}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"tu_01","content":"def main():..."}]}}
{"type":"result","subtype":"success","total_cost_usd":0.012,"duration_ms":5432,"duration_api_ms":4890,"num_turns":3}
```

**Key event types**:
- `{"type":"system","subtype":"init",...}` - Session init with model info
- `{"type":"assistant","message":{...}}` - Claude's response with `model` and `usage`
- `{"type":"result","subtype":"success"|"error",...}` - Final result

**Model extraction**: The `model` field in assistant messages provides the actual model used. First assistant message is authoritative.

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

**Memory management**: Text is written to callback immediately, not accumulated. Only the final concatenated result is stored in `AgentResult.stdout`, limiting memory to the final response size (not all intermediate chunks).

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

## Error Handling

Subprocess error detection differs from SDK exceptions. The implementation maps exit codes and stderr patterns to structured errors:

| Error Type | Detection Method | `AgentResult` Fields |
|------------|------------------|----------------------|
| **Success** | `returncode == 0` | `success=True` |
| **API key invalid** | `returncode != 0`, stderr contains `invalid_api_key` or `authentication` | `error="Authentication failed"` |
| **Rate limit** | `returncode != 0`, stderr contains `rate_limit` or `429` | `error="Rate limited"` |
| **Model not found** | `returncode != 0`, stderr contains `model` and `not found` | `error="Model not available"` |
| **Timeout** | `asyncio.TimeoutError` raised | `error="Timeout after {n}s"` |
| **Permission denied** | `returncode != 0`, stderr contains `permission` | `error="Permission denied"` |
| **Unknown error** | `returncode != 0`, no pattern match | `error=stderr[:500]` |

**Implementation**:
```python
def _classify_error(returncode: int, stderr: str) -> str:
    """Map subprocess failure to error category."""
    stderr_lower = stderr.lower()
    if "invalid_api_key" in stderr_lower or "authentication" in stderr_lower:
        return "Authentication failed"
    if "rate_limit" in stderr_lower or "429" in stderr_lower:
        return "Rate limited"
    if "model" in stderr_lower and "not found" in stderr_lower:
        return "Model not available"
    if "permission" in stderr_lower:
        return "Permission denied"
    return stderr[:500] if stderr else f"Exit code {returncode}"
```

## Process Cleanup

Long-running tasks (up to 2 hours) require proper process lifecycle management to prevent orphan/zombie processes.

**Timeout handling with graceful shutdown**:
```python
async def run_agent_async(..., timeout: int = 7200):
    process = await asyncio.create_subprocess_exec(...)
    try:
        async with asyncio.timeout(timeout):
            # Read output...
            await process.wait()
    except asyncio.TimeoutError:
        # Graceful: SIGTERM first, allow 5s for cleanup
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            # Force kill if SIGTERM ignored
            process.kill()
            await process.wait()
        raise
```

**Zombie prevention**:
- Always call `process.wait()` after process exits (ensures kernel cleanup)
- Use `finally` block to guarantee `wait()` even on exceptions
- `asyncio.create_subprocess_exec` with proper context management

**Parent process termination**:
- Python subprocess module sets child processes to same process group
- If parent is killed with SIGTERM/SIGKILL, child becomes orphan (adopted by init)
- Mitigation: Claude Code CLI handles SIGTERM gracefully and exits
- For catastrophic parent death: container restart cleans up orphans

**Implementation skeleton**:
```python
async def run_agent_async(...):
    process = None
    try:
        process = await asyncio.create_subprocess_exec(...)
        async with asyncio.timeout(timeout):
            # ... read output ...
            await process.wait()
    except asyncio.TimeoutError:
        if process:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
        raise TimeoutError(f"Agent timed out after {timeout}s")
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
```

## Verification Plan

1. **Unit tests** (new file: `tests/test_runner.py`):
   - Mock subprocess, verify stream-json parsing
   - Test error classification for each error type
   - Test timeout with SIGTERM/SIGKILL sequence
2. **Integration test**: Run `incoming-processor.py` with test message
3. **Timeout test**: Verify 2-hour timeout works correctly
4. **Streaming test**: Verify `on_output` callback receives chunks
5. **End-to-end**: Send Slack message, verify full workflow

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Stream-json format changes | Add format detection: check for expected keys (`type`, `message`), log warning and fall back to raw stdout on parse failure |
| Subprocess overhead | Negligible vs API latency (subprocess spawn ~10ms vs API ~1-10s) |
| Different error handling | Error classification function with pattern matching (see Error Handling section above) |
| Process orphans/zombies | Graceful SIGTERM → SIGKILL sequence with guaranteed `wait()` (see Process Cleanup section above) |
| Memory for long tasks | Stream text to callback immediately; only final result stored |

**Version compatibility**: Add startup check:
```python
def _check_claude_version():
    result = subprocess.run(["claude", "--version"], capture_output=True, text=True)
    # Log warning if version < minimum known-good version
```

## Decisions

- **Clean removal**: Remove SDK entirely (no fallback). Single code path, simpler maintenance.
- **OAuth**: Already supported via `ANTHROPIC_AUTH_METHOD` env var (added in PR #567)

## Related

- PR #567: Added `ANTHROPIC_AUTH_METHOD` config for OAuth support
- PR #576: Removed Claude Code Router and Gemini CLI support (simplified to Claude Code only)
- Commit 428a35e: Humanizer module switch to headless Claude Code pattern
