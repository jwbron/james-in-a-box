# james-in-a-box Deep Clean Plan

> **Status**: Proposed
> **Created**: 2026-01-23
> **Bead**: beads-g37a

## Objectives

1. Ensure documentation is up to date and consistent
2. Check functionality of different features
3. Label and remove features that are half-baked, incomplete, or deemed "not useful"
4. Assess opportunities for code isolation and sharing
5. Find bugs, inconsistencies, errors, and undefined behavior

## Executive Summary

This plan organizes the deep clean into 4 phases:

| Phase | Focus | Scope |
|-------|-------|-------|
| 1 | Feature Removal | Remove claude-router and gemini-cli support |
| 2 | Stale PR Triage | Review and close/merge 10+ stale PRs |
| 3 | Code Quality Assessment | Identify incomplete features, consolidation opportunities |
| 4 | Documentation Update | Sync all docs with current state |

---

## Phase 1: Feature Removal

### 1.1 Remove Claude Code Router Support

**Confirmed for removal** - Support for routing Claude Code to alternative providers (OpenAI, Gemini, DeepSeek).

**Files to delete:**
- `jib-container/llm/claude/router.py`

**Files to modify:**
- `jib-container/llm/claude/__init__.py` - remove router imports
- `jib-container/llm/claude/config.py` - remove `ANTHROPIC_BASE_URL` references
- `jib-container/llm/claude/runner.py` - remove router usage
- `jib-container/llm/__init__.py` - remove router references
- `jib-container/llm/config.py` - remove `OPENAI` provider from enum
- `jib-container/llm/runner.py` - simplify provider selection
- `shared/jib_config/configs/llm.py` - remove router config
- `docs/FEATURES.md` - remove feature #36 "Claude Code Router Support"
- `docs/adr/not-implemented/ADR-Multi-Agent-Pipeline-Architecture.md` - review references

### 1.2 Remove Gemini CLI Support

**Confirmed for removal** - Direct integration with Google's Gemini CLI.

**Directories to delete:**
- `jib-container/llm/gemini/` (entire directory)

**Files to delete:**
- `jib-container/GEMINI.md` (if exists as symlink)

**Files to modify:**
- `jib-container/llm/__init__.py` - remove gemini references
- `jib-container/llm/config.py` - remove `GOOGLE` provider from enum, remove `GEMINI_MODEL` references
- `jib-container/llm/runner.py` - remove gemini provider handling
- `jib-container/entrypoint.py` - remove GEMINI.md symlink setup
- `jib-container/Dockerfile` - remove gemini CLI installation if present
- `jib-container/jib` - remove gemini references
- `shared/jib_config/configs/llm.py` - remove gemini config
- `docs/FEATURES.md` - remove features #34 "Multi-Provider LLM Module" (simplify), #35 "Gemini CLI Integration"
- `tests/jib/test_entrypoint.py` - update tests
- `tests/jib_config/test_configs.py` - update tests

### 1.3 Simplify LLM Module

After removing router and gemini, simplify the LLM module to only support Claude Code:

- Remove the multi-provider abstraction layer
- `LLM_PROVIDER` env var no longer needed (always Anthropic)
- Keep `run_agent`, `run_agent_async`, `run_interactive` but remove provider switching logic

---

## Phase 2: Stale PR Triage

### 2.1 PRs Older Than 30 Days (10 PRs)

Review each PR and decide: **Merge**, **Close**, or **Update**.

| PR | Title | Age | Recommendation |
|----|-------|-----|----------------|
| #497 | ADR for hierarchical feature analyzer | 35 days | Review - is this still relevant? |
| #496 | JIRA Ticket Triage Workflow | 35 days | Review - is this implemented? |
| #411 | Multi-Agent Processing Optimization ADR | 50 days | Review - superseded by other work? |
| #373 | Model Tier Optimization ADR | 51 days | **Close** - conflicts with router removal |
| #352 | Log analyzer with Claude ADR | 52 days | Review - still wanted? |
| #274 | Codebase Analyzer Strategy ADR | 53 days | Review - implemented? |
| #257 | Automated LLM Research ADR | 53 days | Review - still relevant? |
| #256 | Documentation drift analysis ADR | 53 days | Review - implemented as feature #27? |
| #239 | Continuous System Reinforcement ADR | 53 days | Review - in not-implemented/ folder |
| #170 | PR Review Agent ADR | 55 days | Review - implemented as feature #15? |

### 2.2 Triage Process

For each PR:
1. Check if the work has been implemented elsewhere
2. Check if it conflicts with current direction (e.g., router removal)
3. If still relevant, update and address any review comments
4. If obsolete, close with explanation

---

## Phase 3: Code Quality Assessment

### 3.1 Features Marked as Experimental

Per `FEATURES.md`, these analyzers are "works in progress":

| Feature | Status | Recommendation |
|---------|--------|----------------|
| #20 LLM Trace Collector | Experimental | Keep - provides value |
| #21 LLM Inefficiency Detector | Experimental | Keep - ADR implemented |
| #22 Beads Integration Analyzer | Experimental | Keep - provides health reports |
| #23 Feature Analyzer Service | Experimental | Review - maintains FEATURES.md |
| #24 ADR Researcher Service | Experimental | Review - generates many stale PRs |
| #26 Documentation Generator Pipeline | Experimental | Review - usage? |
| #27 Documentation Drift Detector | Experimental | Keep - useful for cleanup |
| #28 Codebase Index Generator | Experimental | Review - used by what? |

**Action**: Add clearer status labels in FEATURES.md (Alpha, Beta, Stable, Deprecated).

### 3.2 Incomplete or Unused Features

Features to investigate:

| Feature | Concern | Action |
|---------|---------|--------|
| Sprint Ticket Analyzer (#10) | Is this used regularly? | Verify usage |
| PR Analyzer Tool (#17) | Duplicates functionality with #15, #16? | Assess overlap |
| Spec Enricher CLI (#29) | Usage unclear | Verify usage |
| Codebase Index Query Tool (#46) | Separate from Index Generator? | Consider consolidation |

### 3.3 Code Consolidation Opportunities

**Similar patterns found:**

1. **Host service setup scripts** - Each service has its own `setup.sh`:
   - Could share a common service setup framework
   - Location: `host-services/*/setup.sh`

2. **Systemd service templates** - Many similar `.service` and `.timer` files:
   - Could use a templating system
   - 24 service/timer units with similar structure

3. **Analysis processors** - Multiple `*-processor.py` files with similar patterns:
   - `jib-container/jib-tasks/*/` all follow similar patterns
   - Could share base processor class

4. **Configuration management**:
   - `shared/jib_config/` provides a framework
   - Not all services use it consistently

### 3.4 Potential Bugs and Issues to Investigate

| Area | Issue | Investigation Needed |
|------|-------|---------------------|
| Beads | 50+ in_progress beads may be stale | Run audit, close stale beads |
| Gateway sidecar | PR #531 notes read-only refs error | Review and fix |
| Migration scripts | PR #529 suggests removal needed | Complete migration cleanup |
| docs/index.md | References PRs #240, #243, #245, #246 | Update references |

---

## Phase 4: Documentation Update

### 4.1 Documentation Audit Checklist

| Document | Issue | Action |
|----------|-------|--------|
| `docs/index.md` | References stale PRs | Update after Phase 2 |
| `docs/FEATURES.md` | Will have removed features | Regenerate after Phase 1 |
| `docs/adr/README.md` | May reference removed features | Review and update |
| `README.md` | Check if mentions removed features | Review and update |
| `jib-container/.claude/rules/` | Check for LLM provider references | Update after Phase 1 |

### 4.2 ADR Status Review

**In-Progress ADRs** (1 listed, more may exist):
- `ADR-Autonomous-Software-Engineer.md` - Core architecture, keep in-progress

**Not-Implemented ADRs** (6 listed):
| ADR | Decision |
|-----|----------|
| Continuous System Reinforcement | Review - keep? |
| GCP Deployment | Keep - future work |
| Internet Tool Access Lockdown | Actually in-progress folder, misfiled |
| Jib Repository Onboarding | Review - implemented? |
| Message Queue Integration | Keep - future work |
| Slack Bot GCP Integration | Keep - future work |
| Slack Integration Strategy | Review - may be implemented |

### 4.3 Documentation Consistency Checks

Run the following after Phase 1 changes:

```bash
# Check for broken doc links
bin/check-doc-drift

# Check for references to removed features
grep -r "gemini\|router\|LLM_PROVIDER" docs/

# Validate all internal links
bin/fix-doc-links --dry-run
```

### 4.4 FEATURES.md Regeneration

After Phase 1 completion:
```bash
feature-analyzer full-repo --repo-root ~/repos/james-in-a-box
```

---

## Implementation Order

### Week 1: Phase 1 (Feature Removal)

1. Create feature branch for cleanup
2. Remove claude-code-router support
3. Remove gemini CLI support
4. Simplify LLM module
5. Run tests, fix any breakages
6. Create PR for feature removal

### Week 2: Phase 2 (PR Triage)

1. Review each stale PR
2. Close obsolete PRs with explanations
3. Merge any that are ready
4. Update PRs that need minor fixes

### Week 3: Phase 3 (Code Quality)

1. Run Beads audit, close stale beads
2. Investigate experimental features
3. Document consolidation opportunities (don't implement yet)
4. File issues for identified bugs

### Week 4: Phase 4 (Documentation)

1. Update docs after Phase 1 changes
2. Fix broken links
3. Update ADR statuses
4. Regenerate FEATURES.md
5. Final review and cleanup

---

## Success Criteria

- [ ] Claude router code completely removed
- [ ] Gemini CLI code completely removed
- [ ] LLM module simplified to Claude-only
- [ ] All tests pass
- [ ] All stale PRs (>30 days) triaged
- [ ] FEATURES.md reflects current state
- [ ] docs/index.md has no broken links or stale references
- [ ] No grep hits for "gemini" or "router" in active code
- [ ] Beads in_progress count reduced to <20

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing workflows | High | Run full test suite, test manually |
| Losing valuable WIP in stale PRs | Medium | Review PRs carefully before closing |
| Documentation becomes inconsistent | Medium | Run drift detector after changes |
| Incomplete cleanup | Low | Use grep to verify complete removal |

---

## Appendix: Files Affected Summary

### Files to Delete (Phase 1)
```
jib-container/llm/claude/router.py
jib-container/llm/gemini/__init__.py
jib-container/llm/gemini/config.py
jib-container/llm/gemini/runner.py
jib-container/GEMINI.md (if exists)
```

### Files to Modify (Phase 1)
```
jib-container/llm/__init__.py
jib-container/llm/claude/__init__.py
jib-container/llm/claude/config.py
jib-container/llm/claude/runner.py
jib-container/llm/config.py
jib-container/llm/runner.py
jib-container/entrypoint.py
jib-container/Dockerfile
jib-container/jib
shared/jib_config/configs/llm.py
docs/FEATURES.md
tests/jib/test_entrypoint.py
tests/jib_config/test_configs.py
```

---

Authored-by: jib
