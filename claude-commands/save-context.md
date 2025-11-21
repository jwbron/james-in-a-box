# Claude Command: Save Context Document

**Command**: `@save-context <filename>`

**Example**: `@save-context tf-hackathon`

## Purpose
Create or update a context-sharing document that captures accumulated knowledge from the current session using the ACE (Agentic Context Engineering) methodology.

## Usage

When you see this command:

1. **Ensure directory exists**: `~/sharing/context/`
   - Use absolute paths: `/home/<username>/sharing/context/`
   - Create directory if needed: `mkdir -p ~/sharing/context/`
   - This directory is MOUNTED and persists across container rebuilds

2. **Check for existing document** at `~/sharing/context/<filename>.md`
   - If exists: Read it and prepare to append new session
   - If new: Create with Session 1 structure

3. **Generate content** using 3-phase process:
   - **Phase 1 - Generation**: What happened (implementation, commands, timeline)
   - **Phase 2 - Reflection**: What we learned (surprises, failures, pivots)
   - **Phase 3 - Curation**: Actionable patterns (playbooks, anti-patterns)

4. **Append to document** (NEVER replace existing content):
   - Update metadata (Last Updated, Session count)
   - Add new session: `## Session N: YYYY-MM-DD - <Description>`
   - Preserve ALL previous content
   - Version playbooks when refining them
   - Accumulate anti-patterns and lessons learned

5. **Write file** using absolute path

## Critical Rules

✅ **ALWAYS DO**:
- Use absolute paths (`/home/username/...`, never `~/`)
- Append to existing files, never replace
- Add session headers with dates
- Preserve all historical lessons and failures
- Version refined playbooks with dates
- Include negative results and failed approaches

❌ **NEVER DO**:
- Use `~/` in paths (doesn't expand properly)
- Summarize or condense previous sessions
- Remove "resolved" issues or old decisions
- Delete historical content

## Document Structure

### New Document (Session 1):
```markdown
# Context Document: <Topic>

**Created**: YYYY-MM-DD
**Last Updated**: YYYY-MM-DD
**Sessions**: 1
**Status**: <status>

## Purpose & Status
[Context about the work]

## Session 1: YYYY-MM-DD - <Description>

### What Was Implemented
[Generation phase: artifacts, commands, configurations]

### Execution Timeline
[Estimated vs actual, metrics]

### Lessons Learned
[Reflection phase: surprises, failures, pivots]

### Playbooks
[Curation phase: step-by-step patterns]

### Anti-Patterns
[What NOT to do with evidence]

### Decision Log
[Strategy evolution with dates]

### Common Issues & Resolutions
[Troubleshooting guide]
```

### Appending Session:
```markdown
[Update metadata at top: Last Updated, Sessions count]

## Session N: YYYY-MM-DD - <Description>

### What Was Implemented
[This session's work]

### Lessons Learned  
[New lessons - append to accumulated knowledge]

### Playbooks (Updated)
[Refined playbooks with version history]

### Anti-Patterns (New)
[Newly discovered anti-patterns]

### Decision Log
[New decisions with dates and rationale]
```

## Example of Proper Versioning

**Session 1 creates:**
```markdown
## Playbook: Deploy to Staging
**Version**: 1 (Oct 29, 2025)
Steps:
1. Run terraform plan
2. Apply changes
```

**Session 2 refines (CORRECT):**
```markdown
## Playbook: Deploy to Staging
**Version**: 2 (Oct 30, 2025)
**Refinement**: Added validation after Redis issues

Steps:
1. Run terraform plan
2. **NEW**: Validate Redis connectivity
3. Apply changes

**Version history:**
- v1 (Oct 29): Initial version
- v2 (Oct 30): Added Redis validation
```

## Length Guidance
- Playbooks: 10-20 lines each (specific, executable)
- Anti-patterns: 5-10 lines each (one mistake per entry)
- Lessons learned: 3-5 paragraphs (substantive)
- Overall document: 2000-5000 lines is fine (comprehensive > brief)

**Key Principle**: Accumulate wisdom. Failed approaches are MORE valuable than successful ones. Show the journey, not just the destination.

## Reference
Based on: "Agentic Context Engineering" (Zhang et al., 2025)
https://arxiv.org/abs/2510.04618

