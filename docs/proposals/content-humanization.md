# Proposal: Natural Language Quality for LLM Output

**Status**: Draft
**Author**: jib
**Date**: 2026-01-23
**Related**: [blader/humanizer](https://github.com/blader/humanizer) (MIT licensed)

## Problem Statement

LLM-generated text has recognizable patterns that make interactions feel unnatural:
- Overused phrases: "Additionally", "crucial", "delve", "I'd be happy to help"
- Structural tells: em-dash overuse, rule-of-three lists, "not just X...it's Y"
- Tonal issues: excessive hedging, sycophantic openings, generic conclusions

When jib creates PR descriptions, comments, and commit messages, these patterns make the output feel like "talking to an LLM" rather than natural technical communication. This degrades the quality of human-LLM collaboration.

## Goals

1. **Improve interaction quality**: Make jib's output read like natural technical writing
2. **Remove AI prose patterns**: Eliminate telltale LLM-isms that disrupt reading flow
3. **Preserve meaning**: Rewrite for clarity without changing technical content
4. **Automatic by default**: Apply to all jib output without manual intervention
5. **Configurable**: Enable/disable per-repo if needed

## Non-Goals

This proposal is **not** about:
- Hiding that jib is an AI (the bot identity is preserved)
- Evading AI detection systems
- Deceiving collaborators about authorship

The goal is simply better writing quality. A PR authored by `james-in-a-box[bot]` should still be clearly bot-authored - it should just be well-written.

## Scope

### In Scope

| Operation | Field(s) to Humanize |
|-----------|---------------------|
| `gh pr create` | Title, body |
| `gh pr edit` | Title, body |
| `gh pr comment` | Comment body |
| `gh pr review` | Review body |
| `gh issue create` | Title, body |
| `gh issue comment` | Comment body |
| `git commit` | Commit message (Phase 2) |

### Out of Scope

- File contents (code/docs) - handled by normal editing
- Branch names - rarely need humanization

## AI Prose Patterns to Address

Based on [blader/humanizer](https://github.com/blader/humanizer)'s analysis of 24 common patterns:

### Vocabulary

| Pattern | Example | Fix |
|---------|---------|-----|
| Overused transitions | "Additionally", "Furthermore", "Moreover" | "Also" or restructure |
| Inflated words | "crucial", "vital", "essential" | "important" or remove |
| AI-isms | "delve", "tapestry", "landscape", "testament" | Plain alternatives |

### Structure

| Pattern | Example | Fix |
|---------|---------|-----|
| Copula avoidance | "serves as", "functions as" | "is" |
| False parallelism | "It's not just X, it's Y" | State directly |
| Rule of three | "fast, efficient, and reliable" | Use natural groupings |
| Em-dash overuse | "The feature — which is important — works" | Commas or separate sentences |

### Tone

| Pattern | Example | Fix |
|---------|---------|-----|
| Sycophantic openers | "Great question!", "Excellent point!" | Remove or be genuine |
| Excessive hedging | "It could potentially perhaps be..." | "It may..." |
| Generic conclusions | "The future looks bright" | Specific next steps |

### Key Insight

> "Pattern-removal alone produces sterile results. Effective humanization requires injecting authentic voice."

This means we need **LLM-based rewriting**, not just regex replacement.

## Architecture

### Gateway-Based Humanization

All humanization happens in the gateway sidecar, which already handles all git/gh operations.

```
┌─────────────────────────────────────────────────────────────────┐
│  jib-container                                                  │
│                                                                 │
│  gh pr create --title "..." --body "..."                        │
│         │                                                       │
└─────────┼───────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  gateway-sidecar                                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  humanizer.py                                               ││
│  │                                                             ││
│  │  - Receive original content                                 ││
│  │  - Call Claude API for rewrite                              ││
│  │  - Return natural-sounding text                             ││
│  │  - Log diff at DEBUG level                                  ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                  │
│                              ▼                                  │
│                     ┌─────────────────┐                         │
│                     │  GitHub API     │                         │
│                     └─────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
```

### Humanizer Module

```python
"""Natural language quality improvement for LLM output."""

import anthropic

HUMANIZER_SYSTEM_PROMPT = """You are a writing editor improving LLM-generated text for natural readability.

Remove these common LLM patterns:
- Overused words: "Additionally", "crucial", "delve", "landscape", "tapestry", "testament"
- Structural patterns: "not just X...it's Y", rule-of-three lists, "serves as" (use "is")
- Tone issues: sycophantic openers ("Great question!"), excessive hedging, generic conclusions
- Formatting: em-dash overuse, unnecessary bold, decorative emojis

Write naturally:
- Use first person where appropriate ("I fixed" not "This PR fixes")
- Be direct and specific
- Vary sentence length
- Keep technical accuracy

Preserve the exact meaning. Keep it concise. This is for GitHub PR/comment content."""


def humanize(text: str) -> str:
    """Rewrite text for natural readability."""
    response = anthropic.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=len(text) * 2,
        system=HUMANIZER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}]
    )
    return response.content[0].text
```

### Cost/Latency

Using Sonnet for quality output (pricing: $3/1M input, $15/1M output):

| Content Type | Typical Size | Cost | Latency |
|--------------|--------------|------|---------|
| PR title | ~50 chars | ~$0.0003 | ~1s |
| PR body | ~500 chars | ~$0.003 | ~2s |
| Comment | ~200 chars | ~$0.001 | ~1s |
| Commit msg | ~100 chars | ~$0.0006 | ~1s |

**Total per PR**: ~$0.005, ~3s latency. Worth it for interaction quality.

### Error Handling

```python
def humanize(text: str, fail_open: bool = True) -> HumanizeResult:
    """Humanize text with configurable failure mode.

    Args:
        text: Text to humanize
        fail_open: If True, return original text on API failure (default).
                   If False, raise exception blocking the operation.
    """
    try:
        response = anthropic.messages.create(...)
        return HumanizeResult(success=True, text=response.content[0].text, original=text)
    except anthropic.APIError as e:
        logger.error(f"Humanizer API error: {e}")
        if fail_open:
            return HumanizeResult(success=False, text=text, original=text, error=str(e))
        raise HumanizationError(f"Cannot humanize content: {e}")
```

Default is `fail_open=True` - if the API is unavailable, original content is used rather than blocking operations.

### Diff Logging

Humanization diffs are logged for debugging but NOT shown to users:

```python
def humanize_and_log(text: str, context: str) -> str:
    result = humanize(text)
    if result.success and result.text != result.original:
        logger.info(f"Humanized {context}", extra={
            "original_length": len(result.original),
            "humanized_length": len(result.text),
        })
        logger.debug(f"Humanization diff", extra={
            "original": result.original,
            "humanized": result.text
        })
    return result.text
```

## Configuration

```yaml
# In repositories.yaml
humanize:
  enabled: true                      # Default: true
  model: claude-sonnet-4-20250514    # Model for rewriting
  min_length: 50                     # Skip for very short text
  fail_open: true                    # Allow original on API failure
```

Per-repo override:
```yaml
repos:
  some-org/repo:
    humanize:
      enabled: false  # Disable for this repo
```

## Implementation Plan

### Phase 1: Core Humanization

1. Create `gateway-sidecar/humanizer.py` with LLM integration
2. Add Anthropic API client to gateway
3. Wire humanization into `gh_pr_create`, `gh_pr_edit`, `gh_pr_comment`
4. Skip short content (< 50 chars) to reduce latency
5. Log diffs at DEBUG level for quality monitoring

**Files:**
- `gateway-sidecar/humanizer.py` (new)
- `gateway-sidecar/gateway.py` (integration)
- `gateway-sidecar/requirements.txt` (anthropic SDK)
- `config/repositories.yaml.example` (config docs)
- `tests/gateway/test_humanizer.py` (new)

### Phase 2: Commit Message Humanization

Extend to commit messages via gateway validation on push:

```python
def get_commits_in_push(repo_path: str, refspec: str) -> list[Commit]:
    """Extract commit messages from a git push operation."""
    local_ref = refspec.split(":")[0] if ":" in refspec else refspec

    result = subprocess.run(
        ["git", "-C", repo_path, "log", "--format=%H%n%B%n---COMMIT---",
         f"{local_ref}@{{push}}..{local_ref}"],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        # Fallback: commits since diverging from origin/main
        result = subprocess.run(
            ["git", "-C", repo_path, "log", "--format=%H%n%B%n---COMMIT---",
             "--ancestry-path", "origin/main..HEAD"],
            capture_output=True, text=True
        )

    commits = []
    for block in result.stdout.split("---COMMIT---"):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n", 1)
        commits.append(Commit(sha=lines[0], message=lines[1].strip() if len(lines) > 1 else ""))

    return commits
```

### Phase 3: Quality Monitoring

- A/B comparison logging
- Periodic review of humanization quality
- User feedback collection

## Testing Strategy

### Unit Tests

```python
def test_humanization_removes_ai_patterns():
    examples = [
        {
            "input": "Additionally, this PR implements a crucial feature.",
            "should_not_contain": ["Additionally", "crucial"],
        },
        {
            "input": "Great question! I'd be happy to help with that.",
            "should_not_contain": ["Great question", "happy to help"],
        },
    ]
    for example in examples:
        result = humanize(example["input"])
        for pattern in example["should_not_contain"]:
            assert pattern.lower() not in result.lower()

def test_meaning_preserved():
    """Nightly batch test - uses LLM verification."""
    original = "Fix the authentication bug in the login flow"
    humanized = humanize(original)

    verification = anthropic.messages.create(
        model="claude-3-5-haiku-20241022",
        messages=[{
            "role": "user",
            "content": f"Do these mean the same thing? YES or NO.\n\n1: {original}\n2: {humanized}"
        }]
    )
    assert "YES" in verification.content[0].text.upper()
```

### Integration Tests

- PR creation with humanization enabled
- Humanization bypass for short content
- Graceful degradation on API failure
- Configuration override per-repo

## Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Model** | Sonnet | Quality matters for natural writing |
| **Diff visibility** | Log only | Users see final output, diffs for debugging |
| **Default state** | Enabled | Goal is improved quality by default |
| **Failure mode** | Fail open | Don't block operations if API unavailable |

## Remaining Questions

1. **Caching**: Cache humanized text to avoid re-processing on retries?
2. **Commit messages**: Humanize on push, or validation-only?
3. **Rollout**: Gradual per-repo, or enable everywhere?

---

*Authored by jib*
