# Proposal: Content Humanization for Incognito Mode

**Status**: Draft
**Author**: jib
**Date**: 2025-01-23
**Related**: Incognito mode (implemented), [blader/humanizer](https://github.com/blader/humanizer)

## Problem Statement

When jib operates in incognito mode (contributing under a personal GitHub identity), the output should be indistinguishable from a human developer. This has two dimensions:

1. **Identity exposure**: References to Claude, Anthropic, jib, james-in-a-box
2. **AI prose style**: Telltale patterns that mark text as LLM-generated

Currently, identity protection is policy only (CLAUDE.md) with no enforcement. Prose style is not addressed at all - jib's PR descriptions and comments read like talking to an LLM.

## Goals

1. **Remove identity markers**: Block/strip references to AI/bot identity
2. **Humanize prose style**: Rewrite content to sound naturally human-written
3. **Automatic for incognito**: All outbound content humanized by default
4. **Configurable**: Enable/disable per-repo, adjust aggressiveness

## Scope

### In Scope

| Operation | Field(s) to Check | Enforcement Point |
|-----------|------------------|-------------------|
| `git commit` | Commit message, author name/email | Pre-commit hook + gateway |
| `gh pr create` | Title, body | Gateway sidecar |
| `gh pr edit` | Title, body | Gateway sidecar |
| `gh pr comment` | Comment body | Gateway sidecar |
| `gh pr review` | Review body | Gateway sidecar |
| `gh issue create` | Title, body | Gateway sidecar |
| `gh issue comment` | Comment body | Gateway sidecar |

### Out of Scope (Phase 1)

- File contents (code/docs) - too invasive, handled by code review
- Branch names - rarely contain AI references
- Prose style humanization (blader/humanizer patterns)

## Patterns to Detect

### Critical (Block in incognito mode)

```python
CRITICAL_PATTERNS = [
    r'\bClaude\b',                    # AI name
    r'\bAnthropic\b',                 # Company name
    r'\bjames-in-a-box\b',            # Infrastructure name
    r'\bjib\b',                       # Short name (case-sensitive)
    r'Co-Authored-By:\s*Claude',      # Git trailer
    r'claude\.ai',                    # URLs
    r'anthropic\.com',                # URLs
]
```

### Warning (Log but don't block)

```python
WARNING_PATTERNS = [
    r'\bAI\s+(assistant|agent|generated)\b',   # Generic AI mentions
    r'\bLLM\b',                                  # Language model
    r'\bGPT\b',                                  # Other AI
    r'\bautonomous(ly)?\b',                     # Automation hints
]
```

## Architecture

### Option A: Gateway-Only (Recommended)

All sanitization happens in the gateway sidecar since all git/gh operations already flow through it.

```
┌─────────────────┐     ┌─────────────────────────────────────┐
│  jib-container  │────▶│  gateway-sidecar                    │
│                 │     │  ┌─────────────────────────────────┐│
│  git push       │────▶│  │  sanitizer.py                   ││
│  gh pr create   │────▶│  │  - check_text(text, auth_mode)  ││
│  gh pr comment  │────▶│  │  - sanitize_text(text)          ││
│                 │     │  │  - get_patterns(auth_mode)      ││
│                 │     │  └─────────────────────────────────┘│
└─────────────────┘     └─────────────────────────────────────┘
```

**Pros:**
- Single enforcement point
- Already has auth_mode context
- Can access repo configuration
- Audit logging already in place

**Cons:**
- Commit messages already written before push (can only block, not fix)
- Requires extracting commit messages from push payload

### Option B: Gateway + Pre-Commit Hook

Add a pre-commit hook in the jib-container for commit message sanitization.

```
┌─────────────────────────────────────────┐
│  jib-container                          │
│  ┌─────────────────────────────────────┐│
│  │  pre-commit hook                    ││
│  │  - Check commit message             ││
│  │  - Block if patterns found          ││
│  └─────────────────────────────────────┘│
│                  │                      │
│                  ▼                      │
│  ┌─────────────────────────────────────┐│
│  │  gateway-sidecar                    ││
│  │  - Check PR/comment content         ││
│  │  - Additional commit message check  ││
│  └─────────────────────────────────────┘│
└─────────────────────────────────────────┘
```

**Pros:**
- Catches commit messages early (before push)
- Better UX (fail fast)

**Cons:**
- Two enforcement points to maintain
- Pre-commit hook needs auth_mode awareness

## Recommended Approach: Option A (Gateway-Only)

### New Module: `gateway-sidecar/sanitizer.py`

```python
"""AI reference sanitization for incognito mode."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class SanitizeAction(Enum):
    ALLOW = "allow"        # No patterns found
    WARN = "warn"          # Warning patterns found, allow but log
    BLOCK = "block"        # Critical patterns found, block operation
    SANITIZE = "sanitize"  # Auto-replace patterns (future)

@dataclass
class SanitizeResult:
    action: SanitizeAction
    matches: list[str]
    sanitized_text: Optional[str] = None
    reason: Optional[str] = None

CRITICAL_PATTERNS = [
    (r'\bClaude\b', 'AI assistant name'),
    (r'\bAnthropic\b', 'AI company name'),
    (r'\bjames-in-a-box\b', 'Infrastructure name'),
    (r'(?<![a-zA-Z])jib(?![a-zA-Z])', 'Bot identity'),  # Word boundary
    (r'Co-Authored-By:\s*Claude', 'AI attribution trailer'),
    (r'claude\.ai', 'AI service URL'),
    (r'anthropic\.com', 'AI company URL'),
]

WARNING_PATTERNS = [
    (r'\bAI\s+(assistant|agent|generated)\b', 'Generic AI mention'),
    (r'\bLLM\b', 'Language model mention'),
    (r'\bGPT-?\d*\b', 'Other AI mention'),
]

def check_text(text: str, auth_mode: str = "bot") -> SanitizeResult:
    """Check text for AI/bot references.

    Args:
        text: The text to check
        auth_mode: "bot" or "incognito"

    Returns:
        SanitizeResult with action and any matches found
    """
    if not text:
        return SanitizeResult(action=SanitizeAction.ALLOW, matches=[])

    matches = []

    # Check critical patterns
    for pattern, description in CRITICAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            matches.append(f"{description}: {pattern}")

    if matches and auth_mode == "incognito":
        return SanitizeResult(
            action=SanitizeAction.BLOCK,
            matches=matches,
            reason=f"Text contains AI/bot references not allowed in incognito mode: {', '.join(matches)}"
        )

    # Check warning patterns
    for pattern, description in WARNING_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            matches.append(f"{description}: {pattern}")

    if matches:
        return SanitizeResult(
            action=SanitizeAction.WARN,
            matches=matches,
        )

    return SanitizeResult(action=SanitizeAction.ALLOW, matches=[])


def check_commit_message(message: str, auth_mode: str = "bot") -> SanitizeResult:
    """Check a git commit message for AI references."""
    return check_text(message, auth_mode)


def check_pr_content(title: str, body: str, auth_mode: str = "bot") -> SanitizeResult:
    """Check PR title and body for AI references."""
    combined = f"{title}\n{body}"
    return check_text(combined, auth_mode)
```

### Integration Points in `gateway.py`

#### 1. PR Creation (`gh_pr_create`)

```python
# After line 618 (validation), before line 620 (policy check)
from sanitizer import check_pr_content, SanitizeAction

# Check for AI references
sanitize_result = check_pr_content(title, body, auth_mode)
if sanitize_result.action == SanitizeAction.BLOCK:
    audit_log("pr_create_blocked_sanitizer", "gh_pr_create", success=False,
              details={"repo": repo, "reason": sanitize_result.reason, "matches": sanitize_result.matches})
    return make_error(sanitize_result.reason, status_code=403)
elif sanitize_result.action == SanitizeAction.WARN:
    logger.warning(f"PR content contains AI references (allowed): {sanitize_result.matches}")
```

#### 2. PR Comments (`gh_pr_comment`)

```python
# After body validation, before ownership check
sanitize_result = check_text(body, auth_mode)
if sanitize_result.action == SanitizeAction.BLOCK:
    return make_error(sanitize_result.reason, status_code=403)
```

#### 3. Git Push (Commit Messages)

Extract commit messages from the push and check each:

```python
# In git_push(), after ownership check passes
# Get commit messages in the push range
commits = get_commits_in_push(repo_path, refspec)
for commit in commits:
    result = check_commit_message(commit.message, auth_mode)
    if result.action == SanitizeAction.BLOCK:
        return make_error(f"Commit {commit.sha[:8]} contains blocked content: {result.reason}")
```

## Configuration

### In `repositories.yaml`

```yaml
incognito:
  github_user: personal-user

  # Sanitization settings (new)
  sanitize:
    enabled: true              # Default: true for incognito
    mode: block                # "warn", "block", or "sanitize"
    additional_patterns:       # Repo-specific patterns to block
      - '\bmy-secret-project\b'
```

### Per-Repo Override

```yaml
repos:
  some-org/public-repo:
    auth_mode: incognito
    sanitize:
      mode: warn               # Override to warn-only for this repo
```

## Humanizer Integration

The [blader/humanizer](https://github.com/blader/humanizer) library identifies 24 AI prose patterns:

### Pattern Categories

| Category | Examples | Fix |
|----------|----------|-----|
| **Content** | "pivotal moment", "testament to", significance inflation | State facts directly |
| **Vocabulary** | "Additionally", "crucial", "delve", "tapestry", "landscape" | Use plain words |
| **Structure** | Rule-of-three, "not just X...it's Y", copula avoidance | Simplify |
| **Style** | Em-dash overuse, bold headers, emojis | Clean formatting |
| **Tone** | "Great question!", hedging, generic conclusions | Be direct |

### Key Insight

> "Pattern-removal alone produces sterile results. Effective humanization requires injecting authentic voice through specific details, mixed emotions, varied sentence structures."

This means we need **LLM-based rewriting**, not just regex replacement.

## Two-Tier Architecture

### Tier 1: Fast Pattern Blocking (Gateway)

Regex-based detection of identity markers. No LLM needed. Blocks on match.

```
Content → Pattern Check → BLOCK if identity patterns found
                       → PASS to Tier 2 if clean
```

### Tier 2: LLM Humanization (New Service)

LLM rewrites content to sound human. Uses humanizer patterns as guidance.

```
Content → LLM Rewrite → Humanized content → GitHub
```

### Architecture Diagram

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
│  ┌─────────────────┐   ┌─────────────────────────────────────┐  │
│  │  Tier 1:        │   │  Tier 2: humanizer.py               │  │
│  │  sanitizer.py   │   │                                     │  │
│  │                 │   │  - Load humanizer patterns          │  │
│  │  - Identity     │──▶│  - Call Claude API                  │  │
│  │    patterns     │   │  - Rewrite with human voice         │  │
│  │  - Fast regex   │   │  - Return humanized text            │  │
│  │  - Block/pass   │   │                                     │  │
│  └─────────────────┘   └──────────────┬──────────────────────┘  │
│                                       │                         │
│                                       ▼                         │
│                              ┌─────────────────┐                │
│                              │  GitHub API     │                │
│                              └─────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

### Humanizer Prompt Template

```python
HUMANIZER_SYSTEM_PROMPT = """You are a writing editor. Rewrite the following text to sound naturally human-written.

Remove these AI tells:
- Overused words: "Additionally", "crucial", "delve", "landscape", "tapestry", "testament"
- Structural patterns: "not just X...it's Y", rule-of-three lists, copula avoidance ("serves as")
- Tone issues: sycophancy, excessive hedging, generic conclusions
- Formatting: em-dash overuse, unnecessary bold, emojis

Add human voice:
- Use first person naturally ("I fixed" not "This PR fixes")
- Be direct and specific
- Vary sentence length
- Express genuine (not performed) uncertainty when appropriate

Keep the same meaning. Keep it concise. This is for a GitHub PR/comment."""

def humanize(text: str) -> str:
    response = anthropic.messages.create(
        model="claude-3-5-haiku-20241022",  # Fast and cheap
        max_tokens=len(text) * 2,
        system=HUMANIZER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}]
    )
    return response.content[0].text
```

### Cost/Latency Considerations

| Content Type | Typical Size | Haiku Cost | Latency |
|--------------|--------------|------------|---------|
| PR title | ~50 chars | $0.0001 | <500ms |
| PR body | ~500 chars | $0.001 | ~1s |
| Comment | ~200 chars | $0.0004 | <500ms |
| Commit msg | ~100 chars | $0.0002 | <500ms |

**Total per PR**: ~$0.002, ~2s latency. Acceptable for incognito mode.

## Implementation Plan

### Phase 1: Identity Pattern Blocking

Fast regex-based blocking of identity markers. No LLM.

1. Create `gateway-sidecar/sanitizer.py` with identity pattern checking
2. Integrate into `gh_pr_create`, `gh_pr_edit`, `gh_pr_comment`
3. Add configuration support in `repo_config.py`
4. Block operations that contain identity patterns in incognito mode

**Files:**
- `gateway-sidecar/sanitizer.py` (new)
- `gateway-sidecar/gateway.py` (integration)
- `config/repo_config.py` (configuration)
- `tests/gateway/test_sanitizer.py` (new)

### Phase 2: LLM Humanization

Add LLM-based content rewriting using humanizer patterns.

1. Create `gateway-sidecar/humanizer.py` with LLM integration
2. Add Anthropic API client to gateway (or use existing)
3. Wire humanization into PR/comment flow for incognito mode
4. Add bypass for short content (< 50 chars) to reduce latency

**Files:**
- `gateway-sidecar/humanizer.py` (new)
- `gateway-sidecar/requirements.txt` (anthropic SDK if not present)
- `config/repositories.yaml.example` (humanize config)
- `tests/gateway/test_humanizer.py` (new)

**Configuration:**
```yaml
incognito:
  humanize:
    enabled: true
    model: claude-3-5-haiku-20241022
    min_length: 50  # Skip humanization for short text
```

### Phase 3: Commit Message Handling

Two options:

**Option A: Pre-commit hook in container**
- Install hook that checks/rewrites commit messages
- Requires LLM call before each commit
- Higher latency during development

**Option B: Gateway validation on push**
- Extract commits from push, check messages
- Block if patterns found, user must amend
- No rewriting, just validation

**Recommendation:** Option B for Phase 3 (validation only), consider Option A later.

### Phase 4: Bot Mode Integration (Optional)

Apply humanization to bot mode as well, making all jib output sound more human.

- Make humanization opt-in for bot mode
- Useful for external-facing repos even with bot identity

## Testing Strategy

### Unit Tests

```python
def test_critical_patterns_blocked_in_incognito():
    result = check_text("Thanks Claude!", auth_mode="incognito")
    assert result.action == SanitizeAction.BLOCK
    assert "Claude" in str(result.matches)

def test_critical_patterns_warn_in_bot_mode():
    result = check_text("Thanks Claude!", auth_mode="bot")
    assert result.action == SanitizeAction.WARN

def test_clean_text_allowed():
    result = check_text("Fix bug in login flow", auth_mode="incognito")
    assert result.action == SanitizeAction.ALLOW
```

### Integration Tests

- PR creation with blocked content returns 403
- PR creation with clean content succeeds
- Warning patterns logged but allowed
- Configuration override respected

## Security Considerations

1. **False positives**: "jib" appears in legitimate words (e.g., "jibing"). Use word boundaries.
2. **Evasion**: Intentional obfuscation (Cl@ude) not covered. Acceptable - policy is for accidents.
3. **Logging**: Don't log full text content, only pattern matches.

## Open Questions

1. **LLM choice**: Haiku is fast/cheap but less capable. Should we use Sonnet for better quality?
2. **Caching**: Should we cache humanized text to avoid re-processing on retries?
3. **Diff visibility**: Should we show the user what was changed? (original vs humanized)
4. **Bot mode**: Should humanization be available (opt-in) for bot mode too?
5. **Commit messages**: LLM rewrite on every commit adds latency. Worth it?

## Decision Requested

Please review and provide feedback on:

1. **Architecture**: Two-tier (regex blocking + LLM humanization) vs LLM-only?
2. **Scope**: Start with Phase 1+2 together, or Phase 1 first?
3. **Model**: Haiku (fast/cheap) or Sonnet (better quality)?
4. **Transparency**: Show diff of humanization to user, or silent?
5. **Commit handling**: Validation-only (Phase 3 Option B) acceptable?

## Alternatives Considered

### Alternative A: Humanizer as Skill Only

Make `/humanize` a skill that jib uses manually before creating PRs.

**Pros**: No gateway changes, user control, can review changes
**Cons**: Relies on jib remembering, not automatic

### Alternative B: Post-hoc PR Editing

Create PR with original content, then immediately edit with humanized version.

**Pros**: Simpler gateway logic, can show diff in PR history
**Cons**: Extra API calls, brief window of unhuman content visible

### Alternative C: Client-side Humanization

Add humanization to the Python wrappers in jib-container instead of gateway.

**Pros**: Closer to source, can humanize before commit
**Cons**: Duplicates logic if gateway also needs it, harder to enforce

**Recommendation**: Gateway-based (proposed approach) for central enforcement.

---

*Authored by jib*
