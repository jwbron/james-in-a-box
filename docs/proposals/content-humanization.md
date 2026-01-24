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

### Wrapper-Based Humanization (jib-container)

Humanization happens in the jib-container's tool wrappers BEFORE content reaches the gateway sidecar. This keeps the gateway as a simple, deterministic policy enforcement layer with no LLM calls.

**Security principle**: The gateway-sidecar is security-critical infrastructure that enforces authentication and authorization policies. It must remain deterministic and auditable. LLM-based transformations belong in the jib-container where Claude Code is already installed and authenticated.

```
┌─────────────────────────────────────────────────────────────────┐
│  jib-container                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Tool Wrappers (git.py, gh.py)                              ││
│  │                                                             ││
│  │  git.commit("Additionally, this is crucial...")             ││
│  │         │                                                   ││
│  │         ▼                                                   ││
│  │  ┌─────────────────────────────────────────────────────────┐││
│  │  │  jib_humanizer module                                   │││
│  │  │  - Invoke Claude Code with /humanizer skill             │││
│  │  │  - Return natural-sounding text                         │││
│  │  │  - Log diff at DEBUG level                              │││
│  │  └─────────────────────────────────────────────────────────┘││
│  │         │                                                   ││
│  │         ▼                                                   ││
│  │  git.commit("Also, this is important...")  [humanized]      ││
│  └─────────────────────────────────────────────────────────────┘│
│         │                                                       │
└─────────┼───────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  gateway-sidecar (unchanged - policy enforcement only)          │
│  - Authenticate request                                         │
│  - Check branch/PR ownership policies                           │
│  - Forward to GitHub API                                        │
└─────────────────────────────────────────────────────────────────┘
```

### Humanizer Module

Uses the [blader/humanizer](https://github.com/blader/humanizer) Claude Code skill. This is a well-maintained skill that identifies and removes 24 AI writing patterns based on Wikipedia's "Signs of AI writing" guide.

#### Skill Installation

The humanizer skill is installed in the jib-container where Claude Code already runs:

```bash
# Install the skill (in jib-container setup)
mkdir -p ~/.claude/skills
git clone https://github.com/blader/humanizer.git ~/.claude/skills/humanizer
```

#### Implementation

Located in `shared/jib_humanizer/` so it can be used by all wrappers:

```python
"""Natural language quality improvement using humanizer skill."""

import subprocess
from dataclasses import dataclass

@dataclass
class HumanizeResult:
    success: bool
    text: str
    original: str
    error: str | None = None

def humanize(text: str) -> str:
    """Rewrite text for natural readability using the humanizer skill."""

    # Invoke Claude Code with the humanizer skill
    prompt = f"/humanizer\n\n{text}"

    result = subprocess.run(
        [
            "claude",
            "--print",           # Output response only, no interactive UI
            "--model", "sonnet", # Use Sonnet for quality
            "--max-turns", "1",  # Single turn
            "-p", prompt,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise HumanizationError(f"Claude Code failed: {result.stderr}")

    return result.stdout.strip()
```

### Why Use the Humanizer Skill

- **Comprehensive**: Covers 24 documented AI writing patterns
- **Well-maintained**: Based on Wikipedia's AI cleanup guidelines
- **No custom prompts**: Skill handles the complexity
- **Consistent**: Same patterns used across all humanization
- **No API key needed**: Uses existing Claude Code OAuth authentication
- **Security**: Runs in jib-container, not in the security-critical gateway

### Cost/Latency

Using Sonnet for quality output:

| Content Type | Typical Size | Latency |
|--------------|--------------|---------|
| PR title | ~50 chars | ~1-2s |
| PR body | ~500 chars | ~2-3s |
| Comment | ~200 chars | ~1-2s |
| Commit msg | ~100 chars | ~1-2s |

**Total per PR**: ~3-5s latency. Cost handled through existing Claude Code billing.

### Error Handling

```python
def humanize(text: str, fail_open: bool = True) -> HumanizeResult:
    """Humanize text with configurable failure mode.

    Args:
        text: Text to humanize
        fail_open: If True, return original text on failure (default).
                   If False, raise exception blocking the operation.
    """
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "sonnet", "--max-turns", "1", "-p", prompt],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise HumanizationError(result.stderr)
        return HumanizeResult(success=True, text=result.stdout.strip(), original=text)
    except (subprocess.TimeoutExpired, HumanizationError) as e:
        logger.error(f"Humanizer error: {e}")
        if fail_open:
            return HumanizeResult(success=False, text=text, original=text, error=str(e))
        raise
```

Default is `fail_open=True` - if Claude Code is unavailable, original content is used rather than blocking operations.

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
  enabled: true         # Default: true
  model: sonnet         # Model for rewriting (passed to claude --model)
  min_length: 50        # Skip for very short text
  fail_open: true       # Allow original on failure
```

Per-repo override:
```yaml
repos:
  some-org/repo:
    humanize:
      enabled: false  # Disable for this repo
```

## Implementation Plan

### Phase 1: Core Humanization Module

Create the humanizer module in jib-container (not shared - it calls Claude Code) and wire it into the gh wrapper for PR/issue operations.

**Architecture Note**: Code that calls Claude Code must be in `jib-container/`, not `shared/`. This maintains the security boundary where only jib-container runs LLM operations.

1. Install [blader/humanizer](https://github.com/blader/humanizer) skill in jib-container
2. Create `jib-container/jib_lib/humanizer/` module to invoke the skill via Claude Code
3. Move git/gh wrappers to `jib-container/jib_lib/wrappers/` with humanization integration
4. Wire humanization into wrappers: `pr_create`, `pr_edit`, `pr_comment`, `issue_create`, `issue_comment`
5. Skip short content (< 50 chars) to reduce latency
6. Log diffs at DEBUG level for quality monitoring

**Files:**
- `jib-container/jib_lib/humanizer/__init__.py` (new - core module)
- `jib-container/jib_lib/humanizer/humanizer.py` (new - implementation)
- `jib-container/jib_lib/wrappers/gh.py` (moved from shared, with humanization)
- `jib-container/jib_lib/wrappers/git.py` (moved from shared, with humanization)
- `jib-container/jib_lib/wrappers/claude.py` (moved from shared)
- `jib-container/Dockerfile` (install humanizer skill)
- `config/repositories.yaml.example` (config docs)
- `jib-container/tests/lib/humanizer/test_humanizer.py` (new)

**Setup**: Install the humanizer skill in the jib-container:
```dockerfile
# In jib-container/Dockerfile
RUN mkdir -p ~/.claude/skills && \
    git clone https://github.com/blader/humanizer.git ~/.claude/skills/humanizer
```

### Phase 2: Commit Message Humanization

Extend humanization to git commit messages in the git wrapper.

**In git wrapper** (`jib-container/jib_lib/wrappers/git.py`):

```python
from jib_lib.humanizer import humanize_and_log

def commit(self, message: str, *args, skip_humanize: bool = False, **kwargs):
    """Commit with humanized message."""
    if not skip_humanize:
        message = humanize_and_log(message, "commit message")
    return self._run(["commit", "-m", message, *args], **kwargs)
```

**Note**: Both phases use the same `jib_humanizer` module. Phase 1 wires it into gh operations, Phase 2 extends to git operations. The `humanize_and_log` function is used instead of `humanize_text` to provide DEBUG-level logging of humanization diffs.

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
    """Nightly batch test - uses LLM verification via headless Claude Code."""
    original = "Fix the authentication bug in the login flow"
    humanized = humanize(original)

    # Use haiku for cheap verification
    result = subprocess.run(
        ["claude", "--print", "--model", "haiku", "--max-turns", "1", "-p",
         f"Do these mean the same thing? Answer only YES or NO.\n\n1: {original}\n2: {humanized}"],
        capture_output=True, text=True, timeout=60,
    )
    assert "YES" in result.stdout.upper()
```

### Integration Tests

- PR creation with humanization enabled
- Humanization bypass for short content
- Graceful degradation on API failure
- Configuration override per-repo

## Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Location** | jib-container wrappers | Gateway-sidecar is security-critical; keep it deterministic with no LLM calls |
| **Model** | Sonnet | Quality matters for natural writing |
| **Diff visibility** | Log only | Users see final output, diffs for debugging |
| **Default state** | Enabled | Goal is improved quality by default |
| **Failure mode** | Fail open | Don't block operations if API unavailable |
| **Caching** | Skip | Adds complexity; revisit only if needed |
| **Commit messages** | Humanize in wrapper | Handle in git/gh wrappers before content reaches gateway |
| **Rollout** | All repos | Enable everywhere from start; fail-open means low risk |

---

*Authored by jib*
