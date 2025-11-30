# Beads Integration Review

**Date:** 2025-11-30
**Task:** Review beads integration in jib for best practices
**Beads Version:** v0.26.0
**Upstream Repo:** https://github.com/steveyegge/beads

## Executive Summary

The jib project currently integrates beads effectively for basic task tracking, but is **missing several key features** from the beads README that would significantly improve persistent memory and multi-session coordination:

1. ❌ **No Claude Code hooks** for session-ending protocol
2. ❌ **No parent-child chaining** patterns documented
3. ❌ **No stealth mode** configuration option
4. ⚠️ **Limited dependency usage** (only `discovered-from` mentioned)
5. ⚠️ **No session handoff** protocol for container transitions
6. ✅ **Good:** `--allow-stale` usage is correct
7. ✅ **Good:** Basic workflow patterns are solid

## Current State Analysis

### What We're Doing Right

#### 1. Installation (Dockerfile:65-66)
```bash
RUN curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash && \
    which bd
```
- ✅ Installed at container build time (not runtime)
- ✅ Binary placed in `/usr/local/bin/bd`
- ✅ No npm dependency (uses direct install script)

**Rationale:** Unlike Claude Code for Web (which requires runtime npm install), our Docker-based environment can pre-install beads during build. This is more efficient.

#### 2. Persistent Storage (Dockerfile:596-604)
```bash
# Create convenience symlink: ~/beads → ~/sharing/beads
ln -sf "${USER_HOME}/sharing/beads" "${USER_HOME}/beads"

# Import JSONL if needed (cache is auto-rebuilt)
cd "${USER_HOME}/sharing/beads"
gosu "${RUNTIME_UID}:${RUNTIME_GID}" bd sync --import-only > /dev/null 2>&1 || true
```
- ✅ Mounted from host at `~/.jib-sharing/beads/`
- ✅ Survives container rebuilds
- ✅ Shared across all containers
- ✅ Auto-import on container start

#### 3. `--allow-stale` Usage
- ✅ Correctly documented as **mandatory** in ephemeral containers
- ✅ All examples use `--allow-stale`
- ✅ Troubleshooting explains why it's needed

**Why this matters:** Ephemeral containers may have newer database state than git sync state. `--allow-stale` bypasses staleness checks that would block operations.

#### 4. Basic Workflow Patterns (beads-usage.md)
- ✅ Search before create (avoid duplicates)
- ✅ Status transitions (open → in_progress → closed)
- ✅ Label conventions (source, type, priority)
- ✅ Notes for progress tracking

### What We're Missing

#### 1. ❌ Session-Ending Protocol (CRITICAL)

**Beads README emphasizes:**
```
Before finishing work, agents should follow this structured closing routine:

1. File remaining work proactively – Create issues for discovered bugs, TODOs, follow-up tasks
2. Update status accurately – Mark completed issues closed and in-progress work with current status
3. Sync database carefully – Handle git conflicts thoughtfully to ensure no issues are lost
4. Verify clean state – Confirm all changes committed and no untracked files remain
5. Prepare handoff context – Provide formatted prompt with context for next session
```

**What we have:** Nothing automated. Agent must remember to update beads manually.

**Problem:** Containers exit when tasks complete. Without a hook, the agent may forget to:
- Close completed tasks
- File discovered work
- Sync database
- Prepare handoff notes

**Impact:** Lost context between sessions, forgotten tasks, duplicate work.

**Recommended Fix:** Add SessionEnd hook (see recommendations below).

#### 2. ❌ Parent-Child Chaining Patterns

**Beads supports hierarchical work decomposition:**
```bash
bd create "Auth System" -t epic -p 1
# Returns: bd-a3f8e9

bd create "Design login UI" -p 1    # Auto: bd-a3f8e9.1
bd create "Backend validation" -p 1 # Auto: bd-a3f8e9.2
```

**Benefits:**
- Automatic ID cascading (no manual coordination needed)
- Up to 3 nesting levels
- Child namespaces prevent collisions
- Natural work breakdown

**What we document:** Only flat task creation with `--parent` flag for subtasks.

**Missing:**
- No examples of multi-level hierarchies
- No guidance on when to use parent-child vs. flat tasks
- No explanation of auto-numbered child IDs

**Impact:** Agent may create flat tasks when hierarchies would be clearer.

**Recommended Fix:** Add parent-child examples to beads-usage.md and reference docs.

#### 3. ❌ Stealth Mode Option

**Beads README offers stealth mode:**
```bash
bd init --stealth
```

**What it does:**
- Configures global gitignore: `**/.beads/` in `~/.config/git/ignore`
- Adds `bd onboard` instruction to `.claude/settings.local.json`
- Perfect for isolated personal usage without exposing beads to collaborators

**What we have:** Regular init (beads files visible in repo).

**When stealth mode helps:**
- Experimenting with beads without affecting shared repos
- Personal task tracking in company codebases
- Avoiding team confusion if beads isn't adopted

**Current jib behavior:** Beads is in `~/sharing/beads/` (outside git repos), so it's already "stealthy" by design. We **don't need** stealth mode.

**Conclusion:** No action needed. Our architecture already achieves isolation.

#### 4. ⚠️ Limited Dependency Type Usage

**Beads supports 4 dependency types:**
| Type | Purpose | Affects Ready Work |
|------|---------|-------------------|
| `blocks` | Hard blocker | Yes - blocks until resolved |
| `related` | Soft reference | No |
| `discovered-from` | Found during other work | No |
| `parent-child` | Hierarchical decomposition | No |

**What we document:** Only `discovered-from` in examples.

**Missing:**
- `blocks` usage for hard dependencies
- `related` usage for contextual links
- Examples of dependency chains

**Impact:** Agent may not leverage blocking dependencies to manage work order.

**Recommended Fix:** Document all 4 types with examples.

#### 5. ⚠️ No Session Handoff Protocol

**Beads README mentions:**
> "Prepare handoff context – Provide formatted prompt with context for next session"

**What we have:** `@save-context` and `@load-context` commands (separate system).

**Gap:** No integration between beads tasks and context system.

**Ideal flow:**
```bash
# At session end
bd --allow-stale list --status in_progress --json > ~/sharing/context/active-tasks.json
@save-context project-name  # Includes active-tasks.json reference
```

**At session start (new container):**
```bash
@load-context project-name
# Loads context pointing to active-tasks.json
bd --allow-stale show <id-from-json>  # Resume work
```

**Impact:** Context and beads are disconnected. Agent must manually correlate.

**Recommended Fix:** Enhance `@save-context` to snapshot active beads tasks.

## Recommendations

### Priority 1: Add SessionEnd Hook (CRITICAL)

**File:** `jib-container/.claude/hooks/session-end.sh`

```bash
#!/bin/bash
# .claude/hooks/session-end.sh
# Beads session-ending protocol

set -euo pipefail

cd ~/beads || exit 0

echo "🧹 Beads Session-Ending Protocol"
echo ""

# 1. Show current in-progress work
IN_PROGRESS=$(bd --allow-stale list --status in_progress --json 2>/dev/null | jq -r 'length')
if [ "$IN_PROGRESS" -gt 0 ]; then
    echo "⚠️  WARNING: ${IN_PROGRESS} task(s) still in progress"
    echo "   Consider closing or updating them before exit:"
    bd --allow-stale list --status in_progress
    echo ""
fi

# 2. Show open tasks (may be forgotten work)
OPEN=$(bd --allow-stale list --status open --json 2>/dev/null | jq -r 'length')
if [ "$OPEN" -gt 0 ]; then
    echo "ℹ️  INFO: ${OPEN} open task(s) (not started)"
    echo ""
fi

# 3. Sync database
echo "Syncing beads database..."
if bd sync --flush-only 2>&1 | grep -q "error"; then
    echo "⚠️  WARNING: Beads sync failed - changes may be lost"
else
    echo "✓ Beads database synced"
fi

echo ""
echo "Session cleanup complete."
```

**Make executable:**
```bash
chmod +x jib-container/.claude/hooks/session-end.sh
```

**Update Dockerfile settings.json (line 458):**
```json
{
  "hooks": {
    "PostToolUse": [...],
    "SessionEnd": [
      {
        "type": "command",
        "command": "python3 ${TRACE_COLLECTOR} session-end"
      },
      {
        "type": "command",
        "command": "${HOME}/.claude/hooks/session-end.sh"
      }
    ]
  }
}
```

**Note:** The hook directory doesn't exist yet. Create it:
```bash
mkdir -p jib-container/.claude/hooks
```

**Impact:**
- ✅ Reminds agent of unclosed tasks
- ✅ Prevents lost work from unsync'd database
- ✅ Provides session summary
- ✅ Aligns with beads best practices

### Priority 2: Enhance Beads Documentation

**Update:** `jib-container/.claude/rules/beads-usage.md`

**Add section: "Parent-Child Task Hierarchies"**

```markdown
## Parent-Child Task Hierarchies

Beads supports automatic ID cascading for hierarchical work:

```bash
# Create parent epic
bd --allow-stale create "Auth System Overhaul" --type epic --priority 1
# Returns: bd-a3f8e9

# Create child tasks (auto-numbered)
bd --allow-stale create "Design login UI" --parent bd-a3f8e9
# Returns: bd-a3f8e9.1

bd --allow-stale create "Backend validation" --parent bd-a3f8e9
# Returns: bd-a3f8e9.2

# Create sub-subtask (up to 3 levels)
bd --allow-stale create "Email template" --parent bd-a3f8e9.2
# Returns: bd-a3f8e9.2.1
```

**When to use:**
- Breaking large features into subtasks
- Multi-phase projects (Phase 1, Phase 2, etc.)
- Epics with multiple stories

**Benefits:**
- Auto-numbered IDs (no collision risk)
- Hierarchical visualization
- Scoped namespaces per parent
```

**Add section: "Dependency Types"**

```markdown
## Dependency Types

Beads supports 4 dependency types:

### 1. Blocks (Hard Blocker)
```bash
# Task B cannot start until Task A is done
bd --allow-stale dep add bd-B bd-A --type blocks

# Or create with dependency
bd --allow-stale create "Deploy feature" --deps blocks:bd-A
```
**Effect:** Task B won't appear in `bd ready` until Task A is closed.

### 2. Related (Soft Reference)
```bash
# Tasks are related but not blocking
bd --allow-stale dep add bd-X bd-Y --type related
```
**Effect:** No impact on ready work. Useful for context linking.

### 3. Discovered-From (Work Found During Implementation)
```bash
# Found a bug while implementing Feature X
bd --allow-stale create "Fix edge case" --deps discovered-from:bd-X
```
**Effect:** Tracks origin. Useful for tracing issues back to parent work.

### 4. Parent-Child (Hierarchical Decomposition)
```bash
# Already covered in "Parent-Child Task Hierarchies" section
bd --allow-stale create "Subtask" --parent bd-parent
```
**Effect:** Auto-numbered IDs, hierarchical structure.
```

**Add section: "Session Handoff Protocol"**

```markdown
## Session Handoff Protocol

When a container exits, prepare context for the next session:

### At Session End
```bash
# 1. Review in-progress work
bd --allow-stale list --status in_progress

# 2. Update task notes with current state
bd --allow-stale update bd-xyz --notes "Progress: completed X, blocked on Y"

# 3. Close completed tasks
bd --allow-stale update bd-abc --status closed --notes "Done. PR #123 created."

# 4. File discovered work
bd --allow-stale create "Found: issue description" --deps discovered-from:bd-xyz

# 5. Sync database
cd ~/beads && bd sync
```

### At Session Start (Next Container)
```bash
# 1. Check for in-progress work to resume
bd --allow-stale list --status in_progress

# 2. Load context
bd --allow-stale show bd-xyz

# 3. Resume work
bd --allow-stale update bd-xyz --notes "Resuming work..."
```

**CRITICAL:** The SessionEnd hook automates step 5 (sync). Steps 1-4 should be done manually before exit.
```

### Priority 3: Document Stealth Mode (Optional)

**Update:** `docs/reference/beads.md`

**Add section near initialization:**

```markdown
## Stealth Mode (Optional)

Beads can be configured for isolated personal usage without exposing beads infrastructure to collaborators:

```bash
bd init --stealth
```

**What stealth mode does:**
- Configures global gitignore: `**/.beads/` in `~/.config/git/ignore`
- Adds `bd onboard` instruction to `.claude/settings.local.json`

**When to use:**
- Personal task tracking in shared/company codebases
- Experimenting without team adoption
- Avoiding confusion with collaborators

**jib behavior:**
- Beads is already in `~/sharing/beads/` (outside git repos)
- Stealth mode **not needed** for jib use case
- Documented here for completeness
```

### Priority 4: Integrate Beads with Context System (Future Enhancement)

**Goal:** Automatically snapshot active beads tasks in `@save-context`.

**Proposed implementation:**

**File:** `jib-container/.claude/commands/save-context.md`

```markdown
# Save Context

Save current session's learnings for future reference.

## Usage

```
@save-context <project-name>
```

## What Gets Saved

- **Active beads tasks** (in_progress status)
- **Decisions made** (from beads notes)
- **Files changed** (git diff summary)
- **Key learnings** (manual summary)

## Example

```
@save-context james-in-a-box

# Saves to ~/sharing/context/james-in-a-box.json:
{
  "timestamp": "2025-11-30T18:23:54Z",
  "beads_tasks": [
    {
      "id": "bd-a3f8",
      "title": "Implement OAuth flow",
      "status": "in_progress",
      "notes": "Completed token validation, next: refresh logic"
    }
  ],
  "files_changed": [...],
  "learnings": "..."
}
```
```

**Implementation:** Modify `save-context.sh` to call:
```bash
bd --allow-stale list --status in_progress --json > ~/sharing/context/${PROJECT}-beads.json
```

**Impact:**
- ✅ Automatic context preservation
- ✅ Beads tasks included in session snapshots
- ✅ Easier session resumption

## Comparison: jib vs. Beads README Recommendations

| Feature | Beads README | jib Current | Gap | Priority |
|---------|-------------|-------------|-----|----------|
| Installation | `npm install -g @beads/bd` | Script install in Dockerfile | None (different environment) | ✅ |
| SessionStart Hook | Recommended for Claude Code Web | Not needed (pre-installed) | None | ✅ |
| SessionEnd Hook | **Mandatory** | ❌ Missing | Add `.claude/hooks/session-end.sh` | P1 |
| Parent-Child IDs | Documented | Mentioned but not explained | Add examples | P2 |
| 4 Dependency Types | Documented | Only `discovered-from` shown | Add blocks/related examples | P2 |
| Stealth Mode | Optional | Not needed (already isolated) | Document as "not needed" | P3 |
| Session Handoff | Recommended protocol | Ad-hoc | Formalize protocol | P2 |
| `--allow-stale` | Required in ephemeral | ✅ Documented | None | ✅ |
| Agent Onboarding | `bd onboard` command | Manual docs | None (prefer docs) | ✅ |

## Action Items

### Immediate (P1)
- [ ] Create `.claude/hooks/` directory
- [ ] Add `session-end.sh` hook
- [ ] Update Dockerfile settings.json to call hook
- [ ] Test hook on container exit

### Short-term (P2)
- [ ] Update `beads-usage.md` with parent-child examples
- [ ] Update `beads-usage.md` with all 4 dependency types
- [ ] Add session handoff protocol to docs
- [ ] Update `beads.md` reference doc

### Long-term (P3)
- [ ] Document stealth mode as "not needed for jib"
- [ ] Consider beads + context system integration
- [ ] Evaluate Agent Mail for multi-container coordination (if we add concurrent agents)

## Conclusion

The jib beads integration is **fundamentally sound** but **missing best practices** from the upstream README:

**Strengths:**
- ✅ Correct installation method for Docker environment
- ✅ Persistent storage via `~/sharing/beads/`
- ✅ `--allow-stale` usage is correct
- ✅ Basic workflow patterns work well

**Critical gaps:**
- ❌ No SessionEnd hook (agents forget to close tasks)
- ⚠️ Parent-child chaining under-documented
- ⚠️ Dependency types under-utilized

**Next steps:**
1. Add SessionEnd hook (prevents lost work)
2. Enhance documentation (parent-child, dependencies)
3. Consider context system integration

**Risk if unchanged:** Agent "forgets" to update beads at session end, leading to lost context and duplicate work across container restarts.

---

**Generated:** 2025-11-30
**Beads Task:** beads-bqlc
**Reviewer:** jwbron
