# Prompt Caching in jib

## Overview

jib automatically benefits from **Claude's prompt caching** feature, which significantly reduces costs and latency when reusing large portions of prompts across API calls. This document explains how prompt caching works in jib and how to monitor its effectiveness.

## How It Works

### Automatic Caching

Claude Code (the CLI) automatically enables prompt caching when making API calls to Claude. **No configuration is required** - caching is enabled by default.

When you run Claude in jib:
- **System prompts** (CLAUDE.md, mission.md, etc.) are automatically cached
- **Context files** loaded from `~/context-sync/` are cached
- **Tool definitions** are cached
- **Previous conversation turns** are cached

### Cache Duration

- **Default**: 5 minutes of ephemeral caching
- **Extended**: 1-hour caching available (requires different pricing tier)
- Cache automatically refreshes on each use at no additional cost

### Cache Lifecycle

```
Turn 1: Write CLAUDE.md to cache (13,958 tokens) → Pay 1.25x for cache write
Turn 2: Read CLAUDE.md from cache (13,958 tokens) → Pay 0.1x (90% savings)
Turn 3: Read from cache again → Pay 0.1x (90% savings)
... 5 minutes of inactivity ...
Turn N: Cache expired, rewrite → Pay 1.25x for cache write
```

## Monitoring Cache Performance

### Via Trace Collector

jib's trace collector now captures prompt caching metrics for every session.

**Check recent session metrics:**
```bash
cat ~/sharing/traces/$(date +%Y-%m-%d)/sess-*.meta | jq '.cache_hit_rate, .total_cache_read_tokens'
```

**View cache metrics for a session:**
```bash
jq '.' ~/sharing/traces/2025-11-30/sess-20251130-182640-container.meta
```

Example output:
```json
{
  "total_cache_creation_tokens": 15797,
  "total_cache_read_tokens": 41066,
  "total_input_tokens": 14,
  "cache_hit_rate": 72.3
}
```

### Metrics Explained

| Metric | Description |
|--------|-------------|
| `cache_creation_input_tokens` | Tokens written to cache (costs 1.25x base rate) |
| `cache_read_input_tokens` | Tokens read from cache (costs 0.1x base rate, 90% savings) |
| `input_tokens` | Regular input tokens after final cache breakpoint (standard rate) |
| `cache_hit_rate` | Percentage of input tokens served from cache |

> **Note:** Cache metrics are extracted from Claude API's `usage` field in transcript responses.
> They represent server-side measurements, not client-side estimates.

**Good cache hit rate:** 60%+ indicates effective caching
**Low cache hit rate:** <30% may indicate frequent context changes

## Cost Savings

Prompt caching provides significant cost savings for jib workloads:

**Without caching** (15,000 token context per turn × 10 turns):
- Input: 150,000 tokens × $3/MTok = $0.45

**With caching** (same workload, 70% cache hit rate):
- Cache write (turn 1): 15,000 × 1.25 × $3/MTok = $0.056
- Cache reads (turns 2-10): 135,000 × 0.1 × $3/MTok = $0.041
- Regular input: 1,500 × $3/MTok = $0.005
- **Total: $0.102 (77% savings)**

## What Gets Cached

Claude Code automatically caches:

### Always Cached
- System prompts (`CLAUDE.md`)
- Tool definitions (Bash, Edit, Read, etc.)
- MCP server configurations

### Conditionally Cached
- Previous conversation turns (until context window limits)
- Files read via the Read tool (if referenced in subsequent turns)
- Long document context (ADRs, Confluence docs loaded via context-sync)

### Never Cached
- User input (the current prompt)
- Thinking blocks (extended thinking content)
- Real-time data (current timestamps, dynamic content)

## Best Practices for Maximizing Cache Effectiveness

### 1. Structure Stable Content First

The CLAUDE.md file is ideally positioned - it loads before user input, so it's always cached.

✅ **Good:** Large, stable instructions in CLAUDE.md
❌ **Bad:** Embedding constantly-changing data in system prompts

### 2. Reuse Context Across Sessions

When working on the same repository or task:
- Use `@load-context <name>` to load previously saved context
- Keep working directory consistent (`cd ~/khan/<repo>`)
- Resume conversations with `claude --continue` when possible

### 3. Minimize Context Thrashing

Avoid patterns that invalidate the cache:
- ❌ Frequently switching between unrelated repositories
- ❌ Loading different large documents every turn
- ✅ Focus on one repository/task per session
- ✅ Load large context early, query it repeatedly

### 4. Leverage Beads for Persistent Context

```bash
# Instead of re-explaining the same task context each session
bd --allow-stale show beads-xyz  # Load task context from beads
# Now Claude can resume with minimal cache invalidation
```

## Cache Invalidation

The cache is automatically invalidated when:
- **5 minutes of inactivity** pass (default TTL)
- **Tool definitions change** (adding/removing tools)
- **System prompt changes** (editing CLAUDE.md)
- **Web search or citations** are toggled
- **Model parameters change** (`tool_choice`, thinking mode, etc.)

## Troubleshooting

### Low Cache Hit Rates

**Problem:** Cache hit rate consistently below 30%

**Diagnosis:**
```bash
# Check if context is changing frequently
grep "cache_creation_input_tokens" ~/sharing/traces/$(date +%Y-%m-%d)/*.jsonl | wc -l
```

**Solutions:**
1. Consolidate related work into longer sessions
2. Use `@save-context` / `@load-context` for persistence
3. Avoid switching repositories mid-session

### High Cache Write Costs

**Problem:** Many cache creation events

**Diagnosis:**
Look for frequent cache writes in trace logs:
```bash
jq 'select(.cache_creation_input_tokens > 0)' ~/sharing/traces/$(date +%Y-%m-%d)/sess-*.jsonl | wc -l
```

**Solutions:**
1. Use `claude --continue` to resume sessions instead of starting fresh
2. Keep system prompts stable (don't edit CLAUDE.md during active work)
3. Load large documents once, query multiple times

## Future Enhancements

Planned improvements to prompt caching in jib:

1. **Cache Analytics Dashboard**: Web UI showing cache performance over time
2. **Automatic Cache Optimization**: Detect and warn about cache-inefficient patterns
3. **1-Hour Cache Option**: Support for extended cache TTL when cost-effective
4. **Cache-Aware Task Scheduling**: Group related tasks to maximize cache reuse

## References

- [Claude API Prompt Caching Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [ADR: LLM Inefficiency Reporting](../adr/implemented/ADR-LLM-Inefficiency-Reporting.md)

---

**Last Updated:** 2025-11-30
