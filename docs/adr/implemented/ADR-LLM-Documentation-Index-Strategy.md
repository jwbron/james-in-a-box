# ADR: LLM Documentation Index Strategy

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Tyler Burleigh, Marek Zaluski, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Implemented

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Decision Matrix](#decision-matrix)
- [Implementation Details](#implementation-details)
- [Documentation Index Architecture](#documentation-index-architecture)
- [LLM-Authored Documentation Workflows](#llm-authored-documentation-workflows)
- [External Best Practices Integration](#external-best-practices-integration)
- [Migration Strategy](#migration-strategy)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)
- [References](#references)

## Context

### Background

**Problem Statement:**

LLM-powered agents like james-in-a-box face a fundamental challenge: they need to understand and follow project-specific patterns, best practices, and documentation standards, but:

1. **Context Window Limitations:** Dumping entire documentation into CLAUDE.md files creates context overload, leading to poor performance and higher token costs
2. **Documentation Discovery:** Agents struggle to find relevant documentation without explicit guidance ("go do task A" vs. "go do task A, look at these docs for reference")
3. **Documentation Drift:** Documentation becomes stale as code evolves, but manual maintenance is burdensome
4. **Pattern Reinforcement:** Extracting patterns from existing code risks reinforcing bad habits if the codebase has inconsistencies
5. **Knowledge Silos:** Best practices exist across multiple sources (external standards, internal ADRs, code patterns) but aren't unified

**Opportunity:**

Industry trends point toward a solution: **documentation indexes** that help LLMs navigate to relevant information on-demand rather than front-loading everything into context. Combined with LLM-authored documentation workflows, we can create a self-maintaining documentation ecosystem.

### What We're Deciding

This ADR establishes the strategy for:

1. **Documentation Index Architecture:** How to structure indexes that help LLMs find relevant docs without bloating context
2. **LLM-Authored Documentation:** How agents should generate and maintain documentation
3. **External Best Practices Integration:** How to incorporate industry standards and keep up with trends
4. **Spec Enrichment:** How to automatically link specs/tasks to relevant documentation

### Key Requirements

1. **Efficient Context Usage:** Minimize tokens while maximizing relevant information
2. **Self-Orienting Capability:** Agent can find what it needs without human guidance
3. **Documentation Maintenance:** Agent participates in keeping docs current
4. **External Knowledge:** Agent incorporates industry best practices, not just internal patterns
5. **Quality Over Quantity:** Condensed, high-signal documentation beats exhaustive docs

### Current State

**james-in-a-box currently:**
- Uses a large CLAUDE.md file with instructions crammed into it
- Has context sync for Confluence ADRs, JIRA tickets, and GitHub PRs
- Can read documentation but doesn't maintain it
- Relies on human to point to relevant docs for specific tasks
- Has no structured approach to incorporating external best practices

### Industry Context

Several standards and approaches are emerging:

| Standard/Approach | Description | Adoption |
|-------------------|-------------|----------|
| **llms.txt** | Proposed standard for LLM-friendly website content | Stripe, Anthropic, Cursor, Mintlify |
| **AGENTS.md** | OpenAI's convention for agent instructions | GitHub Copilot, AMP, Roo Code |
| **CLAUDE.md** | Anthropic's context file for Claude Code | Claude Code users |
| **BMAD Method** | AI-driven development with specialized agents | Growing community |
| **.instructions.md** | GitHub Copilot's per-directory custom instructions | GitHub Copilot |

## Decision

**We will implement a multi-layered documentation index architecture with LLM-authored documentation workflows and external best practices integration.**

### Core Principles

1. **Index, Don't Dump:** CLAUDE.md becomes a navigation index, not a content dump
2. **Pull, Don't Push:** Agent fetches relevant docs on-demand rather than receiving all upfront
3. **Generate and Validate:** LLM generates docs, but validates against external standards
4. **Descriptive and Prescriptive:** Document both "how we do things" and "how we should do things"
5. **Continuous Maintenance:** Documentation is a living artifact updated with code changes

### Approach Summary

| Layer | Purpose | Maintained By |
|-------|---------|---------------|
| **Navigation Index** | Points to all available docs, brief descriptions | LLM + Human review |
| **Codebase Index** | Machine-readable structure, patterns, relationships | LLM (automated) |
| **Narrative Docs** | Human-readable guides, ADRs, runbooks | LLM + Human review |
| **External Standards** | Industry best practices, up-to-date trends | LLM (web research) + Human review |

## Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **Index Format** | Markdown index with links | Human + LLM readable, simple | JSON-only (less human-friendly) |
| **Codebase Analysis** | Tree-sitter + LLM hybrid | Accurate structure + semantic understanding | Pure LLM (less reliable for structure) |
| **Doc Generation** | Multi-agent pipeline | Specialized agents for each phase | Single-pass generation (lower quality) |
| **External Sources** | Web search + known sources | Current info + trusted baselines | Static docs only (gets stale) |
| **Spec Enrichment** | Automatic link injection | Reduces human effort | Manual linking only (not scalable) |

## Implementation Details

### 1. Navigation Index Architecture

**Primary Index (`CLAUDE.md`):**

Transform CLAUDE.md from a content dump to a navigation hub:

```markdown
# Project Navigation Index

## Quick Reference
- **Mission:** [Link to mission doc]
- **Architecture:** [Link to architecture ADR]
- **Development Workflow:** [Link to workflow guide]

## Documentation Categories

### Standards & Best Practices
| Topic | Description | Location |
|-------|-------------|----------|
| Testing | E2E test patterns, fixtures, assertions | `docs/testing/e2e-guide.md` |
| API Design | REST conventions, error handling | `docs/api/conventions.md` |
| Security | Auth patterns, input validation | `docs/security/checklist.md` |

### Codebase Structure
| Component | Purpose | Key Files |
|-----------|---------|-----------|
| Auth | Authentication & authorization | `src/auth/`, `docs/auth.md` |
| API | REST endpoints | `src/api/`, `docs/api/` |
| Workers | Background jobs | `src/workers/`, `docs/workers.md` |

### Task-Specific Guides
When working on specific tasks, consult:
- **New E2E tests:** Read `docs/testing/e2e-guide.md` first
- **New API endpoints:** Read `docs/api/conventions.md` first
- **Database migrations:** Read `docs/database/migrations.md` first

## How to Use This Index
1. Before starting a task, search this index for relevant docs
2. Read linked docs before implementing
3. Update docs after implementing new patterns
```

**Secondary Index (`docs/index.md` or `llms.txt`):**

Detailed index following llms.txt conventions:

```markdown
# Documentation Index

> Project-name: Brief project description

## Core Documentation
- [Architecture ADR](#architecture): System architecture and design decisions
- [Context Sync Strategy](#context-sync): How external data is synced
- [Security Model](#security): Isolation, permissions, data handling

## Development Guides
- [Testing Guide](#testing): Test frameworks, patterns, fixtures
- [API Conventions](#api): REST design, error handling, versioning
- [Code Style](#style): Formatting, naming, documentation

## Operational Runbooks
- [Deployment](#deployment): How to deploy changes
- [Troubleshooting](#troubleshooting): Common issues and fixes
- [Monitoring](#monitoring): Metrics, alerts, dashboards

## Machine-Readable
- [codebase.json](#codebase): Structured codebase analysis
- [patterns.json](#patterns): Extracted code patterns
```

### 2. Codebase Index (Machine-Readable)

Generate a structured `codebase.json` for efficient LLM queries:

```json
{
  "generated": "2025-11-27T12:00:00Z",
  "project": "james-in-a-box",
  "structure": {
    "src/": {
      "description": "Source code",
      "children": {
        "watchers/": {
          "description": "Event-driven analyzers",
          "files": ["github-watcher.py", "jira-watcher.py"]
        }
      }
    }
  },
  "components": [
    {
      "name": "GitHubWatcher",
      "type": "class",
      "file": "src/watchers/github-watcher.py",
      "line": 45,
      "description": "Monitors GitHub PR events and triggers analysis",
      "dependencies": ["MCP", "SlackNotifier"],
      "patterns": ["observer", "event-driven"]
    }
  ],
  "patterns": {
    "async_processing": {
      "description": "Background task handling pattern",
      "examples": ["src/watchers/github-watcher.py:89", "src/watchers/jira-watcher.py:102"],
      "conventions": ["Use asyncio.gather for parallel operations", "Always include timeout"]
    }
  },
  "dependencies": {
    "internal": {
      "GitHubWatcher": ["MCPClient", "SlackNotifier", "BeadsTracker"]
    },
    "external": {
      "anthropic": "0.35.0",
      "mcp": "1.2.0"
    }
  }
}
```

**Querying the Index:**

Rather than reading the entire file, provide CLI tools or prompts for selective querying:

```bash
# Get info about a specific component
jq '.components[] | select(.name == "GitHubWatcher")' codebase.json

# Find all files using a pattern
jq '.patterns.async_processing.examples' codebase.json

# Get dependencies for a component
jq '.dependencies.internal.GitHubWatcher' codebase.json
```

### 3. Spec Enrichment Workflow

Automatically enrich task specs with relevant documentation links:

**Input Spec (before enrichment):**
```yaml
task: "Add new E2E test for user authentication flow"
requirements:
  - Test login with valid credentials
  - Test login with invalid credentials
  - Test session persistence
```

**Enriched Spec (after processing):**
```yaml
task: "Add new E2E test for user authentication flow"

context:
  documentation:
    - path: "docs/testing/e2e-guide.md"
      instruction: "Read before starting. Follow patterns for auth tests."
    - path: "docs/auth/flows.md"
      instruction: "Understand current auth implementation."

  examples:
    - path: "tests/e2e/auth/login.spec.ts"
      instruction: "Reference existing auth test patterns."

requirements:
  - Test login with valid credentials
  - Test login with invalid credentials
  - Test session persistence
```

**Enrichment Process:**

```python
# spec-enricher.py
def enrich_spec(spec_path: str, docs_index_path: str) -> dict:
    """Add relevant documentation references to a spec."""
    spec = load_spec(spec_path)
    docs_index = load_docs_index(docs_index_path)

    # Extract keywords from spec
    keywords = extract_keywords(spec)

    # Find relevant docs
    relevant_docs = search_docs_index(docs_index, keywords)

    # Find example code
    examples = find_code_examples(keywords)

    # Inject context section
    spec['context'] = {
        'documentation': [
            {'path': doc.path, 'instruction': f"Read for {doc.topic} guidance"}
            for doc in relevant_docs
        ],
        'examples': [
            {'path': ex.path, 'instruction': f"Reference for {ex.pattern} pattern"}
            for ex in examples
        ]
    }

    return spec
```

### 4. LLM-Authored Documentation Workflows

**Multi-Agent Documentation Pipeline:**

Following the DocAider pattern, use specialized agents for documentation:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Documentation Generation Pipeline              │
│                                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │   Context   │    │   Draft     │    │   Review    │          │
│  │   Agent     │───▶│   Agent     │───▶│   Agent     │          │
│  │             │    │             │    │             │          │
│  │ Analyze code│    │ Generate    │    │ Check for   │          │
│  │ Extract     │    │ initial     │    │ accuracy,   │          │
│  │ structure   │    │ documentation│   │ completeness│          │
│  └─────────────┘    └─────────────┘    └──────┬──────┘          │
│                                               │                   │
│                                               ▼                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │   Output    │◀───│   Revise    │◀───│  External   │          │
│  │   Agent     │    │   Agent     │    │  Validation │          │
│  │             │    │             │    │             │          │
│  │ Format and  │    │ Incorporate │    │ Compare to  │          │
│  │ save docs   │    │ feedback    │    │ best pracs  │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

**Types of Documentation Generated:**

| Type | Purpose | Update Trigger |
|------|---------|----------------|
| **Codebase Index** | Machine-readable structure | Weekly + significant changes |
| **Pattern Docs** | "How we do things" extracted from code | When patterns detected |
| **Status Quo Docs** | Current implementation descriptions | On request |
| **Best Practice Docs** | Prescriptive guidelines | External research triggers |
| **ADR Updates** | Decision documentation | After major decisions |

**Documentation Drift Detection:**

```python
# doc-validator.py
def detect_documentation_drift():
    """Find docs that don't match current code."""

    # Get current code structure
    current_structure = analyze_codebase()

    # Get documented structure
    documented_structure = parse_docs()

    # Find discrepancies
    drifts = []
    for doc in documented_structure:
        if not matches_code(doc, current_structure):
            drifts.append({
                'doc': doc.path,
                'issue': 'Code has diverged from documentation',
                'suggested_update': generate_update_suggestion(doc, current_structure)
            })

    return drifts
```

### 5. External Best Practices Integration

**Problem:** Extracting patterns solely from existing code risks reinforcing bad habits. We need external validation.

**Solution:** Combine internal pattern extraction with external best practices research.

**Workflow:**

```
┌─────────────────────────────────────────────────────────────────┐
│                External Best Practices Integration                │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    INTERNAL SOURCES                          │ │
│  │  - Existing codebase patterns                                │ │
│  │  - Team ADRs and conventions                                 │ │
│  │  - Historical PR feedback                                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    PATTERN ANALYSIS                          │ │
│  │  - Extract patterns from code                                │ │
│  │  - Identify conventions                                      │ │
│  │  - Flag inconsistencies                                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   EXTERNAL VALIDATION                        │ │
│  │  - Web search for current best practices                    │ │
│  │  - Check authoritative sources (official docs, RFCs)        │ │
│  │  - Review industry standards (OWASP, NIST, etc.)           │ │
│  │  - Check for newer/better approaches                        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    DOCUMENTATION OUTPUT                      │ │
│  │  - Descriptive: "Here's how we currently do X"              │ │
│  │  - Prescriptive: "Best practice is to do Y"                 │ │
│  │  - Gap Analysis: "We deviate from best practice in Z"       │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**External Sources to Query:**

| Source Type | Examples | Use Case |
|-------------|----------|----------|
| **Official Docs** | Python docs, React docs, API specs | Authoritative patterns |
| **Standards Bodies** | OWASP, NIST, W3C | Security, accessibility |
| **llms.txt Files** | Stripe, Anthropic, framework docs | Integration patterns |
| **Technical Blogs** | Framework authors, thought leaders | Emerging best practices |
| **GitHub Trending** | Popular repos in relevant languages | Community patterns |

**Best Practice Research Prompt Template:**

```markdown
# Best Practice Research Task

## Topic: {topic}

## Research Questions:
1. What are the current industry best practices for {topic}?
2. Have these practices changed in the last 6 months?
3. What are common anti-patterns to avoid?
4. What do official documentation sources recommend?

## Sources to Check:
- Official {technology} documentation
- OWASP guidelines (if security-related)
- Recent conference talks or blog posts from framework authors
- Popular open-source projects using {technology}

## Output Format:
### Current Best Practices
- [List with citations]

### Anti-Patterns to Avoid
- [List with explanations]

### Our Current Approach
- [How does our code compare?]

### Recommendations
- [What should we change, if anything?]
```

**Scheduled External Research:**

```yaml
# best-practices-refresh.yaml
schedules:
  - name: "Security Best Practices"
    cron: "0 0 * * 0"  # Weekly on Sunday
    topics:
      - "authentication best practices 2025"
      - "API security OWASP"
      - "dependency security practices"

  - name: "Framework Updates"
    cron: "0 0 1 * *"  # Monthly
    topics:
      - "Python 3.x new features best practices"
      - "React patterns 2025"
      - "TypeScript strict mode practices"

  - name: "Infrastructure Trends"
    cron: "0 0 1 */3 *"  # Quarterly
    topics:
      - "Docker security hardening"
      - "Kubernetes patterns"
      - "Cloud Run best practices GCP"
```

### 6. PR-Based Research Workflow

**Problem:** Research findings need review and iteration before integration. Simply updating documents in place bypasses discussion and validation.

**Solution:** Output research findings as PRs that enable iterative review before merging.

**Workflow Diagram:**

```
┌─────────────────────────────────────────────────────────────────┐
│                  PR-Based Research Workflow                      │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    1. SCOPE SELECTION                        │ │
│  │  Choose research scope:                                      │ │
│  │  - "open PRs" → ADRs with pending review                    │ │
│  │  - "merged ADRs" → Implemented decisions needing refresh    │ │
│  │  - "specific topic" → Targeted research area                │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    2. RESEARCH EXECUTION                     │ │
│  │  For each ADR/topic:                                         │ │
│  │  - Web search for current best practices (2024-2025)        │ │
│  │  - Check academic sources (arXiv, conference papers)        │ │
│  │  - Review official documentation updates                    │ │
│  │  - Identify industry adoption patterns                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    3. FINDINGS SYNTHESIS                     │ │
│  │  Create "Research Updates" section with:                    │ │
│  │  - Industry adoption tables                                 │ │
│  │  - Key insights with citations                              │ │
│  │  - Implementation recommendations                           │ │
│  │  - Linked research sources                                  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    4. PR CREATION                            │ │
│  │  One PR per ADR with:                                        │ │
│  │  - Summary of research findings                             │ │
│  │  - Specific implementation recommendations                  │ │
│  │  - Links to sources                                         │ │
│  │  - Test plan / validation steps                             │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    5. ITERATIVE REVIEW                       │ │
│  │  PR enables:                                                 │ │
│  │  - Discussion of findings                                   │ │
│  │  - Challenge of recommendations                             │ │
│  │  - Refinement of implementation details                     │ │
│  │  - Decision to implement, defer, or reject                  │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Research Updates Section Template:**

```markdown
## Research Updates ({Month} {Year})

Based on external research into {topic}:

### {Subtopic 1}

{Key findings with context}

| {Column 1} | {Column 2} | {Column 3} |
|------------|------------|------------|
| Data       | Data       | Data       |

**Application to {project}:**
- Specific recommendation 1
- Specific recommendation 2

### {Subtopic 2}

{Additional findings...}

### Research Sources

- [Source Title](URL) - Brief description
- [Source Title](URL) - Brief description
```

**PR Description Template:**

```markdown
## Summary

Updates {ADR-Name} with current industry research on {topic}.

### Key Changes

- **{Category 1}:** {What was updated}
- **{Category 2}:** {What was updated}

### Implementation Recommendations

Based on research, consider:

1. **{Recommendation}:** {Details}
2. **{Recommendation}:** {Details}

### Research Sources

- [Source](URL)
- [Source](URL)

## Test plan

- [x] ADR markdown renders correctly
- [x] All research source links are valid
- [x] Recommendations align with current architecture
```

**Research Source Types:**

| Source Type | Examples | When to Use |
|-------------|----------|-------------|
| **Academic Papers** | arXiv, ACL, NeurIPS, ICML | Cutting-edge research, theoretical foundations |
| **Official Docs** | Anthropic, OpenAI, framework docs | Authoritative patterns, API updates |
| **Industry Blogs** | Engineering blogs, thought leaders | Practical adoption patterns, lessons learned |
| **Standards Bodies** | OWASP, NIST, W3C | Security, compliance, accessibility |
| **Product Announcements** | Release notes, launch posts | New capabilities, deprecations |
| **GitHub/Community** | Trending repos, discussions | Community patterns, adoption signals |

**Host Script (`host-services/analysis/adr-researcher/`):**

The research workflow is implemented as a host service that can be run manually or scheduled:

```bash
# Research all open ADR PRs and post comments
bin/adr-researcher --scope open-prs

# Research all merged/implemented ADRs and create update PRs
bin/adr-researcher --scope merged

# Generate a new ADR from research on a topic
bin/adr-researcher --generate "Topic for new ADR"

# Review and validate an existing ADR with current research
bin/adr-researcher --review path/to/ADR.md

# Research specific ADR topic
bin/adr-researcher --scope topic --query "Docker sandbox isolation"
```

**Output Modes:**

| Mode | Flag | Description | Use Case |
|------|------|-------------|----------|
| **Update existing** | `--scope merged` | Creates PRs with Research Updates section | Refresh implemented ADRs |
| **Comment on PRs** | `--scope open-prs` | Adds research as PR comments | Enrich ADRs under review |
| **Generate new ADR** | `--generate "topic"` | Creates complete ADR from research | New architectural decisions |
| **Review ADR** | `--review path` | Validates ADR against current research | Pre-merge validation |
| **Markdown report** | `--report-only` | Outputs findings without PR/commit | Initial exploration |

**Workflow Variations:**

The research workflow supports three distinct use cases with different outputs:

| Workflow | Input | Output | Research Updates Section? |
|----------|-------|--------|---------------------------|
| **ADR Update** | Existing ADR | PR with Research Updates added | ✅ Yes - appends findings |
| **ADR Generation** | Topic description | New ADR document | ❌ No - research IS the ADR |
| **ADR Review** | Draft ADR | Validation comments | ❌ No - provides feedback |

*ADR Generation and Review workflows produce the ADR itself as the research artifact, so no separate "Research Updates" section is needed.*

**Example Execution:**

```bash
# 1. Research open ADR PRs (posted comments)
bin/adr-researcher --scope open-prs
# → Posted research comments to PRs #124, #144, #138, #126, #170

# 2. Research merged ADRs (created update PRs)
bin/adr-researcher --scope merged
# → Created PRs #174, #175, #176 with findings and recommendations

# 3. Generate new ADR from research
bin/adr-researcher --generate "MCP Server Security Model"
# → Creates docs/adr/proposed/ADR-MCP-Server-Security-Model.md
# → Creates PR with research-backed ADR ready for review

# 4. Review draft ADR before merge
bin/adr-researcher --review docs/adr/proposed/ADR-New-Feature.md
# → Validates against current research
# → Posts review comments on associated PR
```

### 6.1 ADR Generation Workflow

**Purpose:** Create new ADRs grounded in current industry research rather than relying solely on internal knowledge.

**When to Use:**
- Proposing a new architectural pattern
- Evaluating technology choices
- Documenting decisions that benefit from external validation

**Workflow Diagram:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ADR Generation Workflow                       │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    1. TOPIC ANALYSIS                         │ │
│  │  Parse topic description to identify:                        │ │
│  │  - Core technology/pattern being decided                    │ │
│  │  - Key alternatives to evaluate                             │ │
│  │  - Relevant industry domains                                │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    2. RESEARCH EXECUTION                     │ │
│  │  Web search for:                                             │ │
│  │  - Current best practices (prioritize 2024-2025)           │ │
│  │  - Comparison analyses of alternatives                      │ │
│  │  - Industry adoption patterns                               │ │
│  │  - Known pitfalls and anti-patterns                        │ │
│  │  - Official documentation and specifications               │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    3. ADR SYNTHESIS                          │ │
│  │  Generate complete ADR with:                                 │ │
│  │  - Context grounded in research findings                    │ │
│  │  - Decision matrix with cited trade-offs                    │ │
│  │  - Alternatives with research-backed evaluation             │ │
│  │  - References section linking all sources                   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    4. PR CREATION                            │ │
│  │  Create PR with:                                             │ │
│  │  - ADR in docs/adr/proposed/ directory                      │ │
│  │  - Summary of research methodology                          │ │
│  │  - Key findings that informed the decision                  │ │
│  │  - Open questions for reviewer discussion                   │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**ADR Generation Template:**

The generated ADR follows the standard format but with research-backed content:

```markdown
# ADR: {Title}

**Driver:** jib (AI-generated, requires human approval)
**Status:** Proposed
**Research Date:** {Date}

## Context

### Background

{Research-derived context about the problem space}

### Industry Landscape

{Summary of current industry practices with citations}

| Approach | Adoption | Key Trade-offs |
|----------|----------|----------------|
| ...      | ...      | ...            |

## Decision

{Recommended approach with research justification}

## Decision Matrix

| Criterion | Option A | Option B | Option C |
|-----------|----------|----------|----------|
| ...       | ...      | ...      | ...      |

*Evaluation criteria derived from [source citations]*

## Alternatives Considered

### Alternative 1: {Name}
**Research findings:** {What external sources say}
**Rejected because:** {Research-backed reasoning}

## References

- [Source Title](URL) - {How it informed the decision}
- [Source Title](URL) - {How it informed the decision}
```

### 6.2 ADR Review Workflow

**Purpose:** Validate draft ADRs against current industry research before merging.

**When to Use:**
- Before merging any proposed ADR
- When an ADR has been open for extended period (research may be stale)
- When reviewer requests external validation

**Workflow Diagram:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ADR Review Workflow                           │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    1. ADR PARSING                            │ │
│  │  Extract from draft ADR:                                     │ │
│  │  - Core decision and alternatives                           │ │
│  │  - Claims made about technologies                           │ │
│  │  - Referenced sources (check if still valid)                │ │
│  │  - Trade-off assertions                                     │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    2. VALIDATION RESEARCH                    │ │
│  │  For each claim/assertion:                                   │ │
│  │  - Verify against current sources                           │ │
│  │  - Check for newer alternatives not mentioned               │ │
│  │  - Validate trade-off characterizations                     │ │
│  │  - Identify any outdated information                        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    3. GAP ANALYSIS                           │ │
│  │  Identify:                                                   │ │
│  │  - Missing alternatives that research suggests              │ │
│  │  - Outdated claims needing update                           │ │
│  │  - Unsupported assertions lacking citations                 │ │
│  │  - Emerging patterns not yet considered                     │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    4. REVIEW OUTPUT                          │ │
│  │  Post PR review comment with:                                │ │
│  │  - ✅ Validated claims (with supporting sources)            │ │
│  │  - ⚠️ Claims needing update                                 │ │
│  │  - ❌ Potentially incorrect assertions                      │ │
│  │  - 💡 Suggestions for additional considerations             │ │
│  │  - 📚 Additional sources for reviewer reference             │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Review Comment Format:**

```markdown
## 🔍 Research-Based ADR Review

**Reviewed:** {ADR Title}
**Research Date:** {Date}

### ✅ Validated Claims

- **Claim:** "{Quoted claim from ADR}"
  - **Validation:** {Supporting research} ([source](URL))

### ⚠️ Needs Update

- **Claim:** "{Outdated claim}"
  - **Current Status:** {What research shows now}
  - **Suggested Update:** {Recommended revision}
  - **Source:** [link](URL)

### ❌ Potentially Incorrect

- **Claim:** "{Questionable assertion}"
  - **Research Contradicts:** {What sources actually say}
  - **Recommendation:** {How to address}

### 💡 Additional Considerations

- {Alternative or pattern not mentioned in ADR}
  - **Relevance:** {Why reviewer should consider}
  - **Source:** [link](URL)

### 📚 Supplementary Sources

- [Source](URL) - {Brief description}
- [Source](URL) - {Brief description}

---
*— Authored by jib (research-based review)*
```

**Integration with PR Review Process:**

1. Human opens PR with proposed ADR
2. `adr-researcher --review` runs automatically (or on request)
3. Research-based review posted as PR comment
4. Human reviewer incorporates findings
5. ADR updated based on validated research
6. Merge proceeds with research-backed confidence

## Documentation Index Architecture

### File Structure

```
docs/
├── index.md                    # Main navigation index (llms.txt compatible)
├── generated/                  # LLM-generated, machine-readable
│   ├── codebase.json          # Structured codebase analysis
│   ├── patterns.json          # Extracted code patterns
│   ├── dependencies.json      # Dependency graph
│   └── last-updated.json      # Generation metadata
├── standards/                  # Prescriptive guidelines
│   ├── testing.md             # Testing standards
│   ├── api-design.md          # API conventions
│   ├── security.md            # Security checklist
│   └── code-style.md          # Style guide
├── guides/                     # How-to documentation
│   ├── getting-started.md
│   ├── development-workflow.md
│   └── troubleshooting.md
├── adr/                        # Architecture Decision Records
│   ├── ADR-Autonomous-Software-Engineer.md
│   └── ...
└── runbooks/                   # Operational procedures
    ├── deployment.md
    ├── incident-response.md
    └── monitoring.md
```

### Index Update Workflow

```
Code Change (PR merged)
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Index Update Pipeline                          │
│                                                                   │
│  1. Detect changed files                                         │
│  2. Update codebase.json (if structure changed)                  │
│  3. Update patterns.json (if new patterns detected)              │
│  4. Check for documentation drift                                │
│  5. Suggest documentation updates                                │
│  6. Update index.md if new docs created                          │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
Create PR with documentation updates (human reviews)
```

## LLM-Authored Documentation Workflows

### Workflow 1: Pattern Extraction ("Status Quo" Docs)

**Trigger:** On request or when code analyzer detects recurring patterns

**Process:**
1. Analyze specified code area
2. Extract patterns and conventions
3. Generate descriptive documentation
4. Note any inconsistencies found
5. Human reviews and approves

**Example Output:**

```markdown
# Authentication Patterns (Status Quo)

> Auto-generated by jib on 2025-11-27. Review before relying on.

## Current Implementation

### Token Validation
We currently validate JWT tokens using:
- Library: PyJWT 2.8.0
- Algorithm: RS256
- Token location: Authorization header (Bearer scheme)

### Session Management
Sessions are stored in Redis with:
- TTL: 24 hours
- Key format: `session:{user_id}:{session_id}`
- Refresh: On each authenticated request

## Inconsistencies Detected
- `src/legacy/auth.py` uses HS256 (line 45) while rest of codebase uses RS256
- Session TTL is 24h in code but documentation says 12h

## Recommendations
- Migrate `src/legacy/auth.py` to RS256
- Update documentation or code to match session TTL
```

### Workflow 2: Best Practice Documentation (Prescriptive)

**Trigger:** Scheduled or when implementing new patterns

**Process:**
1. Research external best practices (web search)
2. Compare with current implementation
3. Generate prescriptive documentation
4. Include citations to authoritative sources
5. Human reviews and approves

**Example Output:**

```markdown
# JWT Security Best Practices

> Auto-generated by jib on 2025-11-27 with external research.

## Industry Standards

Per OWASP JWT Security Cheat Sheet (2024):
- Use strong algorithms (RS256, ES256)
- Set appropriate expiration times
- Validate all claims
- Use secure key storage

## Our Compliance

| Practice | Status | Notes |
|----------|--------|-------|
| Strong algorithm | ✅ | Using RS256 |
| Short expiration | ⚠️ | 24h may be too long for sensitive ops |
| Claim validation | ✅ | All standard claims validated |
| Secure key storage | ✅ | Using Secret Manager |

## Recommendations

1. Consider shorter token expiration for admin operations
2. Add jti (JWT ID) claim for token revocation support

## Sources
- [OWASP JWT Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [RFC 7519](https://tools.ietf.org/html/rfc7519)
```

### Workflow 3: Documentation Drift Correction

**Trigger:** Scheduled weekly or on significant code changes

**Process:**
1. Compare documentation against current code
2. Identify discrepancies
3. Generate corrective updates
4. Create PR for human review

**Example:**

```
Documentation Drift Report - 2025-11-27

Files with drift detected:
1. docs/api/authentication.md
   - Documentation says: "Sessions expire after 12 hours"
   - Code says: "SESSION_TTL = 86400" (24 hours)
   - Suggested fix: Update documentation to "24 hours"

2. docs/testing/e2e-guide.md
   - Documentation references: "tests/e2e/setup.ts"
   - File moved to: "tests/e2e/fixtures/setup.ts"
   - Suggested fix: Update path reference

PR created: #142 "Fix documentation drift in auth and testing docs"
```

## Migration Strategy

### Phase 1: Index Structure

1. Create `docs/index.md` navigation index
2. Refactor CLAUDE.md to be index-focused
3. Organize existing docs into category folders
4. Add llms.txt compatible format

**Success Criteria:** Agent can navigate to relevant docs using index

### Phase 2: Codebase Index Generation

**Dependencies:** Phase 1 (index structure in place)

1. Implement codebase analyzer using tree-sitter
2. Generate initial `codebase.json`
3. Create CLI tools for querying index
4. Add to weekly regeneration schedule

**Success Criteria:** Machine-readable codebase index exists and updates automatically

### Phase 3: Spec Enrichment

**Dependencies:** Phase 1 and Phase 2 (indexes available for linking)

1. Implement spec enricher script
2. Integrate with task ingestion workflow
3. Test with sample specs
4. Roll out to all incoming specs

**Success Criteria:** Specs automatically include relevant documentation links

### Phase 4: LLM Documentation Authoring

**Dependencies:** Phase 2 (codebase index for analysis)

1. Implement multi-agent documentation pipeline
2. Create pattern extraction workflow
3. Add documentation drift detection
4. Schedule regular documentation generation

**Success Criteria:** Agent generates and maintains documentation with human review

### Phase 5: External Best Practices

**Dependencies:** Phase 4 (documentation authoring pipeline established)

1. Implement web research workflow
2. Create best practice research prompts
3. Set up scheduled research tasks
4. Integrate external standards into documentation

**Success Criteria:** Documentation includes externally-validated best practices

## Consequences

### Benefits

1. **Reduced Context Overhead:** Index-based navigation uses fewer tokens than content dumps
2. **Self-Orienting Agent:** Agent finds relevant docs without human guidance
3. **Living Documentation:** Docs stay current with code changes
4. **Quality Validation:** External research prevents reinforcing bad patterns
5. **Faster Onboarding:** Better docs help both humans and agents
6. **Consistency:** Automated generation ensures uniform format

### Drawbacks

1. **Initial Investment:** Significant effort to set up pipeline
2. **Human Review Required:** Generated docs need human approval
3. **Web Research Costs:** External searches use additional tokens/API calls
4. **False Positives:** Drift detection may flag intentional differences
5. **Maintenance:** Pipeline itself needs maintenance

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Generated docs are inaccurate | Multi-stage review with validation agent |
| External sources are unreliable | Prioritize authoritative sources (official docs, RFCs) |
| Too much documentation noise | Focus on high-value docs, prune low-value |
| Agent ignores index | Prompt engineering to use index first |
| Stale external research | Scheduled refresh with recency bias |

## Decision Permanence

**Medium permanence.**

The documentation index approach aligns with emerging industry standards (llms.txt, AGENTS.md) and can evolve as standards mature. The multi-agent pipeline is modular and can be adjusted.

**Low-permanence elements:**
- Specific file formats (JSON vs. YAML)
- Scheduling frequencies
- External sources to query

**Higher-permanence elements:**
- Index-based navigation pattern
- Separation of machine-readable and narrative docs
- External validation principle

## Alternatives Considered

### Alternative 1: Larger CLAUDE.md File

**Description:** Continue expanding CLAUDE.md with all documentation.

**Pros:**
- Simple, no new infrastructure
- Everything in one place

**Cons:**
- Context window limits
- Token inefficiency
- Hard to maintain at scale

**Rejected because:** Doesn't scale; industry moving toward indexes.

### Alternative 2: Pure Code Extraction (No External Research)

**Description:** Generate all documentation from codebase analysis only.

**Pros:**
- Simpler implementation
- No external dependencies

**Cons:**
- Reinforces existing patterns, good or bad
- Misses industry improvements
- No quality validation

**Rejected because:** Risk of reinforcing anti-patterns; want aspirational docs.

### Alternative 3: Manual Documentation Only

**Description:** Humans write all documentation, agent only reads.

**Pros:**
- High quality control
- No automation complexity

**Cons:**
- Documentation gets stale
- Significant human burden
- Doesn't scale

**Rejected because:** Documentation drift is already a problem; need automation.

### Alternative 4: Full RAG System

**Description:** Implement full Retrieval-Augmented Generation with vector embeddings.

**Pros:**
- Sophisticated semantic search
- Can handle very large doc sets

**Cons:**
- Complex infrastructure
- Overkill for current scale
- Embedding drift issues

**Rejected because:** Over-engineered for current needs; can revisit if scale demands.

## References

- [llms.txt Standard](https://llmstxt.org/) - Proposed standard for LLM-friendly content
- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices) - Anthropic's guidance
- [AGENTS.md Convention](https://pnote.eu/notes/agents-md/) - Emerging standard for agent instructions
- [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD) - AI-driven development methodology
- [Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) - Anthropic's context management guide
- [RAG for Large Scale Code Repos](https://www.qodo.ai/blog/rag-for-large-scale-code-repos/) - Codebase indexing patterns
- [DigitalOcean Context Management](https://docs.digitalocean.com/products/gradient-ai-platform/concepts/context-management/) - Best practices for AI context
- [DocAider Multi-Agent Documentation](https://techcommunity.microsoft.com/blog/educatordeveloperblog/docaider-automated-documentation-maintenance-for-open-source-github-repositories/4245588) - Microsoft's automated documentation approach
- [GitBook llms.txt Support](https://www.gitbook.com/blog/what-is-llms-txt) - Industry adoption of llms.txt

### Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-LLM-Inefficiency-Reporting](../in-progress/ADR-LLM-Inefficiency-Reporting.md) | Documentation indexes help detect Tool Discovery Failures (Category 1 in inefficiency taxonomy) |

---

**Last Updated:** 2025-11-28
**Next Review:** 2025-12-28 (Monthly)
**Status:** Implemented
