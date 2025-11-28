# ADR Researcher

Research-based ADR (Architecture Decision Record) workflow tool implementing Phase 6 of the [ADR-LLM-Documentation-Index-Strategy](../../../docs/adr/implemented/ADR-LLM-Documentation-Index-Strategy.md).

## Overview

This service enables research-driven ADR workflows:

1. **Research Open PRs** (`--scope open-prs`): Research ADRs in open PRs and post findings as PR comments
2. **Update Merged ADRs** (`--scope merged`): Research implemented ADRs and create update PRs with new findings
3. **Generate ADRs** (`--generate "topic"`): Create new ADRs grounded in current industry research
4. **Review ADRs** (`--review path`): Validate ADR claims against current research

## Architecture

```
Host (adr-researcher.py)          Container (adr-processor.py)
┌─────────────────────────┐       ┌─────────────────────────┐
│                         │       │                         │
│ • Find ADRs to research │       │ • Build research prompt │
│ • Parse ADR content     │──jib──│ • Run Claude for search │
│ • Invoke jib container  │       │ • Output findings       │
│ • Post results (PR/GH)  │       │ • Create PR if needed   │
│                         │       │                         │
└─────────────────────────┘       └─────────────────────────┘
```

## Usage

### Research Open ADR PRs

Post research findings as comments on open PRs that modify ADR files:

```bash
bin/adr-researcher --scope open-prs
```

### Update Implemented ADRs

Create PRs with "Research Updates" sections for implemented ADRs:

```bash
bin/adr-researcher --scope merged
```

### Generate New ADR

Generate a complete ADR from research on a topic:

```bash
bin/adr-researcher --generate "MCP Server Security Model"
```

### Review Existing ADR

Validate an ADR's claims against current research:

```bash
bin/adr-researcher --review docs/adr/proposed/ADR-New-Feature.md
```

### Research Specific Topic

Research a topic without creating/updating ADRs:

```bash
bin/adr-researcher --scope topic --query "Docker sandbox isolation"
bin/adr-researcher --scope topic --query "Docker sandbox isolation" --report-only
```

## Options

| Flag | Description |
|------|-------------|
| `--scope` | Research scope: `open-prs`, `merged`, `topic` |
| `--generate TOPIC` | Generate new ADR from research |
| `--review PATH` | Review existing ADR file |
| `--query QUERY` | Research query (with `--scope topic`) |
| `--report-only` | Output as report without creating PR |
| `--dry-run` | Show what would be done |
| `--json` | Output results as JSON |

## Output Modes

| Mode | Trigger | Output |
|------|---------|--------|
| `pr_comment` | Open PR exists | Comment on PR with findings |
| `update_pr` | Merged ADR | New PR adding Research Updates section |
| `new_pr` | `--generate` | New PR with complete ADR |
| `report` | `--report-only` | Markdown to stdout |

## Research Updates Section Template

When updating existing ADRs, findings are added in this format:

```markdown
## Research Updates (November 2025)

Based on external research into [topic]:

### [Subtopic 1]

[Key findings with context]

| Aspect | Current State | Industry Trend |
|--------|---------------|----------------|
| ...    | ...           | ...            |

**Application to this ADR:**
- Specific recommendation 1
- Specific recommendation 2

### Research Sources

- [Source Title](URL) - Brief description
```

## Requirements

- `jib` command must be in PATH (for invoking research container)
- `gh` CLI must be authenticated (for GitHub operations)
- Python 3.10+ with PyYAML

## Files

| File | Purpose |
|------|---------|
| `adr-researcher.py` | Host-side CLI and orchestrator |
| `../../jib-container/jib-tasks/adr/adr-processor.py` | Container-side research processor |

## Related

- [ADR-LLM-Documentation-Index-Strategy](../../../docs/adr/implemented/ADR-LLM-Documentation-Index-Strategy.md) - Parent ADR
- [doc-generator](../doc-generator/) - Pattern extraction from code (Phase 4)
- [spec-enricher](../spec-enricher/) - Spec enrichment workflow (Phase 3)
