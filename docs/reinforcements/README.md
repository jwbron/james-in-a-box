# System Reinforcement Records

This directory contains records of system reinforcements - learnings captured from breakages that have been applied to strengthen the system.

## Purpose

When jib causes or encounters a breakage, we don't just fix the immediate issue. We analyze the root cause at a process level and apply reinforcements to prevent similar failures in the future.

The full process documentation is planned for a future ADR.

## Creating a New Record

1. Copy the template below
2. Name the file: `YYYY-MM-DD-brief-description.md`
3. Fill in all sections
4. Commit with your fix or as a follow-up

## Template

```markdown
# Reinforcement: [Brief Title]

**Date:** YYYY-MM-DD
**Breakage Type:** [Test Failure | Build Failure | Runtime Error | Review Feedback]
**Severity:** [Low | Medium | High | Critical]

## What Broke

[Brief description of the failure]

## Immediate Fix

[What code change resolved the immediate issue]

## Root Cause Analysis

### Technical Cause
[Direct technical reason for failure]

### Process Cause
[Why did the system allow this? What was missing?]

### Pattern Category
[Documentation | Testing | Guardrail | Workflow | Context | Edge Case | External Dependency]

## Reinforcement Applied

### Type
[Documentation | Testing | Guardrail | Process | Tooling]

### Changes Made
- [ ] Change 1
- [ ] Change 2

### Files Modified
- `path/to/file` - Description of change

## Prevention Validation

[How we verified this reinforcement would prevent recurrence]

## Lessons Learned

[Key takeaways that generalize beyond this specific case]
```

## Record Index

Records are named `YYYY-MM-DD-brief-description.md` and listed below:

*No records yet - this directory was just created.*

## Monthly Review

On the first of each month, review all records from the previous month to:
- Identify recurring patterns
- Consolidate related reinforcements
- Update documentation or ADRs as needed
- Archive old records that have been superseded
