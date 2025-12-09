# ADR: Automated PR Review Agent

**Driver:** Engineering Leadership
**Approver:** TBD
**Contributors:** James Wiesebron, jib (AI Agent)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Not Implemented

## Table of Contents

- [Context](#context)
- [Goals and Non-Goals](#goals-and-non-goals)
- [Design Principles](#design-principles)
- [Decision](#decision)
- [Detailed Design](#detailed-design)
- [Security Considerations](#security-considerations)
- [Consequences](#consequences)
- [Alternatives Considered](#alternatives-considered)
- [Open Questions](#open-questions)
- [Related ADRs](#related-adrs)

## Context

### Problem Statement

Code review is a critical part of the software development process, but it presents several challenges:

1. **Reviewer Bottleneck**: Human reviewers have limited bandwidth, creating delays in the PR lifecycle
2. **Inconsistent Coverage**: Review quality varies based on reviewer availability, expertise, and fatigue
3. **Mechanical Checks**: Significant review time is spent on mechanical issues (style, security patterns, obvious bugs) that could be automated
4. **Context Gathering**: Reviewers must manually gather context from documentation, related code, and project standards

### Opportunity

An automated PR review agent can provide consistent, thorough first-pass reviews that:
- Catch common issues before human review
- Provide immediate feedback to PR authors
- Free human reviewers to focus on architectural and design concerns
- Maintain consistent application of coding standards

### Scope of This ADR

This ADR defines the architecture and principles for an automated PR review agent within the james-in-a-box ecosystem. The agent should:
- Review pull requests automatically when triggered
- Provide actionable feedback via GitHub comments
- Operate within defined boundaries to ensure reviews are fair and digestible

## Goals and Non-Goals

### Goals

1. **Accelerate PR Feedback**: Provide initial review within minutes of PR creation/update
2. **Consistent Quality Gates**: Apply coding standards uniformly across all PRs
3. **Reduce Review Burden**: Handle mechanical review tasks automatically
4. **Educate PR Authors**: Provide explanations, not just flags, to help authors learn
5. **Integrate with Human Review**: Complement, not replace, human reviewers
6. **Digestible Reviews**: Produce reviews that are themselves easy to review and understand

### Non-Goals

1. **Replace Human Reviewers**: Final approval authority remains with humans
2. **Architectural Review**: Complex design decisions require human judgment
3. **Merge PRs**: The agent should never merge PRs automatically
4. **Access External Systems**: The agent should not query production systems, external APIs, or gather context beyond the PR itself

## Design Principles

### Principle 1: Bounded Context (CRITICAL)

**The reviewer should assess PRs based only on information available to a human reviewer.**

The agent MUST limit its context to:
1. **The PR itself**: Diff, commits, PR description, existing comments
2. **The target repository**: Code being modified, related files, project structure
3. **Project documentation**: README, CONTRIBUTING.md, style guides, ADRs checked into the repo
4. **CI/CD results**: Test failures, linter output, build errors

The agent MUST NOT:
- Query external knowledge bases or documentation systems (Confluence, Notion, etc.)
- Search for information about the PR author
- Access historical PR data beyond what's directly referenced
- Use web searches or external APIs to gather context
- Access any system that a human reviewer wouldn't naturally consult

**Rationale**: A PR should be reviewable based on its own merits. If a reviewer needs extensive external context to understand a PR, that signals the PR itself may be poorly documented or too large. Additionally, reviews should be reproducible and auditable - if the agent's review depends on external systems, the review becomes harder to understand and verify.

### Principle 2: Proportional Response

Review depth should match PR complexity:
- **Small PRs** (< 50 lines): Focus on correctness and style
- **Medium PRs** (50-300 lines): Add security, testing, and documentation checks
- **Large PRs** (> 300 lines): Flag size concern, focus on high-impact issues

### Principle 3: Actionable Feedback

Every comment should:
- Identify the specific issue
- Explain why it matters
- Suggest a concrete fix or improvement
- Indicate severity (blocking, suggestion, nitpick)

### Principle 4: Fail-Open Philosophy

When in doubt:
- Don't block the PR
- Add a suggestion rather than a requirement
- Defer to human judgment on ambiguous cases
- Err on the side of being helpful rather than comprehensive

### Principle 5: Transparency

- Clearly identify automated comments (e.g., signature line)
- Explain the basis for each finding (pattern matched, rule violated)
- Make the review process auditable and reproducible

## Decision

**We will build an automated PR review agent with strictly bounded context that provides first-pass reviews complementing human reviewers.**

### Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Events                             │
│          (PR opened, updated, review requested)              │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   Event Detection                            │
│        (GitHub webhook or polling-based trigger)             │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                Context Gathering                             │
│  Collects ONLY:                                              │
│  - PR metadata (title, description, author)                  │
│  - PR diff (full unified diff)                               │
│  - PR comments and reviews                                   │
│  - CI check results and logs                                 │
│  - Files changed (for repo context lookup)                   │
│  - Repository files (README, CONTRIBUTING, style guides)     │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 Review Generation                            │
│  LLM-powered analysis with:                                  │
│  - Pattern matching for common issues                        │
│  - Contextual analysis of code changes                       │
│  - Style guide compliance checking                           │
│  - Security pattern detection                                │
│  - Test coverage assessment                                  │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│               Review Formatting & Posting                    │
│  - Format as GitHub review comments                          │
│  - Post inline comments where appropriate                    │
│  - Create summary comment                                    │
│  - Track review state                                        │
└─────────────────────────────────────────────────────────────┘
```

### Review Scope Definition

The agent will check for:

| Category | Checks | Severity |
|----------|--------|----------|
| **Security** | Hardcoded secrets, SQL injection, XSS, unsafe functions | Blocking |
| **Correctness** | Obvious bugs, null checks, type errors | Blocking |
| **Testing** | Missing tests for new code, test coverage gaps | Suggestion |
| **Style** | Formatting, naming conventions, code organization | Nitpick |
| **Documentation** | Missing docstrings, outdated comments | Suggestion |
| **Performance** | N+1 queries, unnecessary allocations, obvious inefficiencies | Suggestion |
| **Maintainability** | Complex functions, duplicated code, magic numbers | Suggestion |

### Trigger Mechanisms

The agent can be triggered by:

1. **Automatic**: PR created or updated (new commits pushed)
2. **On-demand**: GitHub slash command (e.g., `/review`) or mention
3. **Scheduled**: Periodic scan for unreviewed PRs

## Detailed Design

### Context Boundary Implementation

To enforce the bounded context principle, the context gathering component:

```python
class PRContextGatherer:
    """Gathers context for PR review with strict boundaries."""

    ALLOWED_SOURCES = [
        "pr_metadata",      # Title, description, author, labels
        "pr_diff",          # Full unified diff
        "pr_comments",      # Existing comments and reviews
        "pr_commits",       # Commit messages and metadata
        "ci_results",       # Check status and logs
        "repo_files",       # Files within the repository
    ]

    FORBIDDEN_SOURCES = [
        "external_docs",    # Confluence, Notion, wikis
        "user_history",     # Author's previous PRs or profile
        "external_apis",    # Web searches, third-party services
        "other_repos",      # Code from unrelated repositories
        "production_data",  # Logs, metrics, customer data
    ]
```

### Review Output Format

Reviews should follow a consistent format:

```markdown
## PR Review Summary

**Files Reviewed**: 5
**Lines Changed**: +142 / -38
**Review Time**: 2.3s

### Issues Found

#### [BLOCKING] Security: Potential SQL Injection (file.py:42)
The query uses string concatenation with user input:
```python
query = f"SELECT * FROM users WHERE id = {user_id}"
```
**Suggestion**: Use parameterized queries:
```python
query = "SELECT * FROM users WHERE id = %s"
cursor.execute(query, (user_id,))
```

#### [SUGGESTION] Testing: New function lacks test coverage (utils.py:15-30)
The `validate_input()` function is new but no corresponding test was added.
**Suggestion**: Add test cases covering valid input, invalid input, and edge cases.

#### [NITPICK] Style: Function name doesn't follow convention (helpers.py:8)
Function `getData` should be `get_data` per PEP 8.

### Positive Observations
- Good test coverage for the main feature (5 new tests)
- Clear commit messages following conventional commits

---
*Automated review by jib. This is a first-pass review; human review is still required.*
```

### State Management

The agent tracks:
- Which PRs have been reviewed (to avoid duplicate reviews)
- Which commit SHA was last reviewed (to re-review on updates)
- Review findings for persistence and audit

### Rate Limiting and Resource Management

- Maximum one concurrent review per repository
- Configurable delay between reviews (default: 30 seconds)
- Review timeout (default: 5 minutes)
- Maximum diff size for review (default: 10,000 lines)

## Security Considerations

### Access Control

The agent requires:
- **Read access**: Repository contents, PR metadata, CI results
- **Write access**: PR comments only
- **No access**: Repository settings, merge capability, secrets

### Credential Handling

- GitHub App token scoped to minimum required permissions
- Token rotated regularly
- No credential storage beyond runtime memory

### Audit Trail

- All review actions logged with timestamp
- Review rationale preserved for reproducibility
- Human override capability for all automated actions

## Consequences

### Benefits

1. **Faster Feedback**: Authors get immediate first-pass review
2. **Consistent Standards**: Every PR receives the same baseline checks
3. **Reduced Toil**: Human reviewers focus on high-value feedback
4. **Educational**: Authors learn patterns and anti-patterns over time
5. **Reproducible**: Reviews based on bounded context are auditable

### Costs

1. **Maintenance Overhead**: Rules and patterns need ongoing refinement
2. **False Positives**: Some automated findings will be incorrect
3. **Noise Risk**: Poor tuning could make reviews more annoying than helpful
4. **Context Limitations**: Bounded context means missing some nuanced issues

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| False positive flood | Start with high-confidence patterns only; expand gradually |
| Authors ignore reviews | Make findings actionable; track engagement metrics |
| Stale review rules | Regular review of patterns based on false positive feedback |
| Security of review agent | Sandbox execution; minimal permissions; audit logging |

## Alternatives Considered

### Alternative 1: Full Context Review

**Description**: Allow the agent to access any context source (Confluence, Slack history, user profiles) for more informed reviews.

**Pros**: More comprehensive context; potentially better reviews

**Cons**:
- Reviews become non-reproducible (external context changes)
- Harder to explain review rationale
- PRs might "pass" based on external docs that should be in the repo
- Privacy and security concerns with broad access
- If a human reviewer would struggle without that context, the PR itself may need improvement

**Decision**: Rejected. Bounded context enforces better PR quality and maintainable reviews.

### Alternative 2: Pure Pattern Matching (No LLM)

**Description**: Use only regex patterns and AST analysis without LLM involvement.

**Pros**: Deterministic; faster; no LLM costs

**Cons**:
- Limited to predefined patterns
- Can't understand semantic issues
- Poor explanations
- High false positive rate for complex code

**Decision**: Rejected. LLM provides better understanding and explanations, though pattern matching remains valuable for obvious issues.

### Alternative 3: GitHub Native Code Scanning

**Description**: Use GitHub's built-in code scanning and Dependabot without custom agent.

**Pros**: No maintenance; integrated experience; security-focused

**Cons**:
- Limited customization for project-specific standards
- Doesn't provide contextual PR review
- Can't enforce style guides or documentation requirements
- No educational feedback component

**Decision**: Rejected as sole solution. GitHub scanning is complementary but insufficient for comprehensive PR review.

## Open Questions

The following questions require clarification before implementation:

1. **Review Timing**: Should the agent review immediately on PR creation, or wait for CI to complete first?

2. **Self-Review**: Should the agent review PRs created by itself (for automated dependency updates, etc.)?

3. **Comment Threading**: Should findings be posted as inline comments, a single summary, or both?

4. **Re-review Triggers**: What changes should trigger a re-review? (new commits only? label changes? comment requests?)

5. **Severity Thresholds**: What severity level should block PR approval vs. be advisory?

6. **Repository Scope**: Should the agent review PRs in all monitored repos, or only explicitly configured ones?

7. **Review Request Handling**: When a human requests review from the bot via GitHub's reviewer system, how should it respond differently than automatic reviews?

8. **Diff Size Limits**: For very large PRs, should the agent decline to review, review partially, or review with caveats?

9. **Language/Framework Specific Rules**: How should language-specific patterns be organized and maintained?

10. **Feedback Loop**: How should the agent learn from "false positive" feedback from humans?

## Related ADRs

- [ADR: Autonomous Software Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) - Parent architecture for the jib agent
- [ADR: Context Sync Strategy](../implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) - How external data is synced (note: PR reviewer intentionally does NOT use most synced context)
- [ADR: Internet Tool Access Lockdown](ADR-Internet-Tool-Access-Lockdown.md) - Security restrictions relevant to bounded context principle

---

*This ADR was drafted collaboratively with jib, the AI agent that would implement this feature.*

*Last updated: 2025-11-28*
