# Beads - Automatic Task Memory System

## Overview

Beads is a git-backed persistent memory system that **YOU MUST USE AUTOMATICALLY** to track all tasks, progress, and context. It is not optional - it's a core part of your workflow that enables you to:
- Resume work after container restarts
- Coordinate with other concurrent containers
- Build persistent memory of what's been done
- Track blockers and dependencies

**Location**: `~/beads/` (symlink to `~/sharing/beads/`)
**Storage**: Git repository in `~/.jib-sharing/beads/` on host
**Access**: All JIB containers share the same Beads database

## Automatic Workflow Integration

### ✅ REQUIRED: You Must Use Beads Automatically For:

1. **Every incoming Slack message**
   - **First step**: Check if task already exists in Beads
   - **If not exists**: Create new Beads task with message content
   - **If exists**: Update task status to `in-progress` and add notes
   - **Example**:
     ```bash
     # User sends: "Implement OAuth2 for JIRA-1234"
     cd ~/beads
     # Check for existing task
     beads list --search "OAuth2 JIRA-1234"
     # If not found, create it
     beads add "Implement OAuth2 authentication for JIRA-1234" --tags feature,jira-1234
     beads update <id> --status in-progress
     ```

2. **Any multi-step task or feature**
   - Automatically break down into Beads subtasks
   - Create parent task for the feature
   - Create child tasks for each step
   - Set up blockers for dependencies
   - **Example**:
     ```bash
     # Parent task
     beads add "Implement user authentication system" --tags feature
     # Subtasks with dependencies
     beads add "Design auth schema" --parent bd-a3f8
     beads add "Implement OAuth2 flow" --parent bd-a3f8 --add-blocker bd-b7c2
     beads add "Write tests" --parent bd-a3f8 --add-blocker bd-d4e9
     ```

3. **Container startup/resumption**
   - **Always check** for in-progress tasks
   - Resume unfinished work automatically
   - Update task notes with resumption context
   - **Example**:
     ```bash
     cd ~/beads
     beads list --status in-progress
     # If tasks found, review and continue
     beads show bd-x9y2  # See previous notes
     beads update bd-x9y2 --notes "Resumed: continuing from step 3..."
     ```

4. **Progress tracking**
   - Update status as you work: `open` → `in-progress` → `done`
   - Add notes about decisions, blockers, findings
   - Mark tasks as `blocked` when waiting on something
   - **Do this automatically**, don't wait to be asked

5. **Task completion**
   - Mark tasks `done` when complete
   - Remove blockers from dependent tasks
   - Add summary notes about what was accomplished
   - **Example**:
     ```bash
     beads update bd-a3f8 --status done
     beads update bd-a3f8 --notes "Completed: OAuth2 implemented per RFC 6749, tests passing"
     # Unblock dependent tasks
     beads update bd-d4e9 --remove-blocker bd-a3f8
     ```

### ⚠️ OPTIONAL: Manual Task Creation Supported

Users can manually create Beads tasks, but this is secondary. Your primary mode is **automatic task management** based on context and inputs.

## Core Concepts

### Issues (Beads)
Each task is represented as a "bead" with:
- **ID**: Hash-based collision-resistant ID (e.g., `bd-a3f8`)
- **Title**: Brief description of the task
- **Status**: `open`, `in-progress`, `blocked`, `done`, `cancelled`
- **Tags**: Labels for categorization (e.g., `feature`, `bug`, `urgent`)
- **Blockers**: Dependencies that must complete first
- **Parent/Child**: Hierarchical task relationships
- **Notes**: Additional context, decisions, links

### Git-Backed Storage
- All data stored in JSONL files (human-readable)
- Git provides version history and sync
- SQLite cache built for fast queries (disposable, auto-rebuilt)
- Multiple containers can access simultaneously

## Common Commands

### Creating Tasks

```bash
# Add a new task
bd add "Implement OAuth2 authentication" --tags feature,security

# Add with details
bd add "Fix memory leak in user service" \
  --tags bug,urgent \
  --notes "Affects production, user reports available in JIRA-5678"

# Add subtask to existing task
bd add "Write OAuth2 unit tests" --parent bd-a3f8
```

### Viewing Tasks

```bash
# List all open tasks
bd list

# List tasks by tag
bd list --tags feature
bd list --tags urgent,bug

# Show task details
bd show bd-a3f8

# List tasks ready to work on (no blockers)
bd ready

# List blocked tasks
bd list --status blocked
```

### Updating Tasks

```bash
# Change status
bd update bd-a3f8 --status in-progress
bd update bd-a3f8 --status done

# Add tags
bd update bd-a3f8 --add-tags reviewed,tested

# Add notes
bd update bd-a3f8 --notes "Implemented using RFC 6749 OAuth2 spec"

# Add blocker
bd update bd-a3f8 --add-blocker bd-f14c

# Remove blocker (when dependency complete)
bd update bd-a3f8 --remove-blocker bd-f14c
```

### Task Dependencies

```bash
# Create parent-child relationship
bd add "Write API tests" --parent bd-a3f8

# Block task until another completes
bd update bd-a3f8 --add-blocker bd-f14c

# List what's blocking a task
bd show bd-a3f8  # Shows blockers section

# Find ready work (no blockers)
bd ready
```

### Search and Filter

```bash
# Search by text
bd list --search "authentication"

# Filter by status
bd list --status open
bd list --status in-progress
bd list --status blocked

# Combine filters
bd list --tags feature --status open
```

## Workflow Examples

### Example 1: Multi-Step Feature

```bash
# Create parent task
bd add "Implement user authentication system" --tags feature
# Output: Created bd-a3f8

# Add subtasks
bd add "Design authentication schema" --parent bd-a3f8
bd add "Implement OAuth2 flow" --parent bd-a3f8 --add-blocker bd-b7c2
bd add "Write authentication tests" --parent bd-a3f8 --add-blocker bd-d4e9

# Start work on first subtask
bd update bd-b7c2 --status in-progress

# Complete it
bd update bd-b7c2 --status done

# Remove blocker, start next task
bd update bd-d4e9 --remove-blocker bd-b7c2
bd update bd-d4e9 --status in-progress
```

### Example 2: Resuming Work After Interruption

```bash
# Session 1: Start work
bd add "Refactor payment processing" --tags refactor
bd update bd-x9y2 --status in-progress
bd update bd-x9y2 --notes "Started extracting PaymentService class"
# ... container shuts down

# Session 2: Resume work
bd list --status in-progress
# Shows: bd-x9y2 "Refactor payment processing"
bd show bd-x9y2
# See notes from previous session
# Continue work...
bd update bd-x9y2 --notes "Completed PaymentService, moved to tests"
```

### Example 3: Multiple Containers Coordinating

```bash
# Container A:
bd add "Implement feature X" --tags feature
bd update bd-p4q7 --status in-progress

# Container B (later):
bd list  # Sees bd-p4q7 in-progress
# Avoids duplicate work
bd add "Add docs for feature X" --add-blocker bd-p4q7

# Container A (completes):
bd update bd-p4q7 --status done

# Container B:
bd ready  # Now shows docs task is ready
```

## Automatic Task Management Workflow

### Standard Pattern for Every Task

**When receiving a Slack message or starting new work:**

```bash
# 1. ALWAYS start by checking Beads
cd ~/beads
bd list --status in-progress  # Any unfinished work?
bd list --search "relevant keywords from message"

# 2. Create or update task
if [ task doesn't exist ]; then
    # Create new task with descriptive title
    bd add "Task title from message/context" --tags feature,jira-1234
    TASK_ID=$(beads list | head -1 | awk '{print $1}')  # Get the ID
else
    # Update existing task
    TASK_ID=bd-a3f8  # The found task
fi

# 3. Mark as in-progress
bd update $TASK_ID --status in-progress
bd update $TASK_ID --notes "Started: [brief context about approach]"

# 4. Break down into subtasks if multi-step
bd add "Subtask 1" --parent $TASK_ID
bd add "Subtask 2" --parent $TASK_ID --add-blocker bd-xyz1
bd add "Subtask 3" --parent $TASK_ID --add-blocker bd-xyz2

# 5. Work on the task...

# 6. Update progress as you go
bd update bd-xyz1 --status done
bd update bd-xyz1 --notes "Completed: implemented X using Y approach"
bd update bd-xyz2 --remove-blocker bd-xyz1  # Unblock next task

# 7. Mark complete when done
bd update $TASK_ID --status done
bd update $TASK_ID --notes "Completed: summary of what was accomplished, tests passing, PR #123"
```

### Automatic Tagging Conventions

**Always tag appropriately:**
- **Type**: `feature`, `bug`, `refactor`, `docs`, `test`
- **Source**: `slack`, `jira-1234`, `github-pr-567`
- **Priority**: `urgent`, `important` (if mentioned)
- **Area**: `auth`, `api`, `frontend`, `database` (based on codebase affected)

**Example:**
```bash
# User message: "Fix the memory leak in user service (JIRA-5678)"
bd add "Fix memory leak in user service" --tags bug,urgent,jira-5678,backend
```

### Automatic Context Preservation

**Always add notes with important context:**
- JIRA ticket references
- Relevant ADR numbers
- Implementation decisions and why
- Blockers or dependencies discovered
- Links to PRs or related work

**Example:**
```bash
bd update bd-a3f8 --notes "Implementing OAuth2 per RFC 6749. Using httpOnly cookies per ADR-042. Related to JIRA-1234. Blocks JIRA-5678."
```

### Automatic Task Breakdown

**For any task with >3 steps, automatically create subtasks:**

```bash
# Parent
bd add "Implement user authentication" --tags feature,jira-1234
PARENT_ID=bd-a3f8

# Subtasks (automatically inferred from your plan)
bd add "Design database schema" --parent $PARENT_ID --tags schema
bd add "Implement OAuth2 endpoints" --parent $PARENT_ID --tags api --add-blocker bd-b1
bd add "Add frontend login form" --parent $PARENT_ID --tags frontend --add-blocker bd-b2
bd add "Write integration tests" --parent $PARENT_ID --tags test --add-blocker bd-b2,bd-b3
```

### Automatic Status Updates

**Update status automatically as you progress:**

```bash
# Starting work
bd update bd-a3f8 --status in-progress

# Hit a blocker
bd update bd-a3f8 --status blocked
bd update bd-a3f8 --notes "Blocked: waiting for database migration approval from DBA team"

# Blocker resolved
bd update bd-a3f8 --status in-progress
bd update bd-a3f8 --notes "Unblocked: migration approved, resuming implementation"

# Completed
bd update bd-a3f8 --status done
bd update bd-a3f8 --notes "Done: OAuth2 implemented, all tests passing, PR #456 created"
```

## Integration with Other Systems

### With @save-context
```bash
# After completing significant work
bd list --status done  # Review completed tasks
bd update bd-a3f8 --notes "Summary: Implemented OAuth2, tests passing, PR ready"
@save-context oauth2-implementation
# Context doc can reference Beads IDs for tracking
```

### With Notifications
```bash
# When you need human input on blocked task
bd list --status blocked
# Create notification referencing bead ID
cat > ~/sharing/notifications/$(date +%Y%m%d-%H%M%S)-blocked-task.md <<EOF
# 🔔 Task Blocked: Need Database Schema Approval

**Bead ID**: bd-a3f8
**Priority**: High

See: beads show bd-a3f8

[Details...]
EOF
```

### With JIRA Tickets
```bash
# Reference JIRA in task notes
bd add "Implement feature X" --notes "JIRA-1234"

# Or in title if preferred
bd add "[JIRA-1234] Implement feature X"
```

## Troubleshooting

### "No issues found"
```bash
# Rebuild SQLite cache
cd ~/beads
bd build-cache
```

### Changes Not Persisting
```bash
# Ensure you're in the beads directory
cd ~/beads

# Check git status
git status

# Beads auto-commits to git, but verify
git log --oneline -5
```

### Multiple Container Conflicts
Beads uses hash-based IDs to prevent conflicts. If two containers create tasks simultaneously, they'll have different IDs. This is by design.

## Summary

**Beads is AUTOMATIC, not optional:**

### Required Behavior
1. **Every Slack message**: First step is check/create Beads task
2. **Container startup**: Check for in-progress tasks, resume if found
3. **Multi-step work**: Automatically break down into subtasks with blockers
4. **Progress updates**: Continuously update status and notes as you work
5. **Completion**: Mark done, add summary, unblock dependent tasks

### Key Benefits
- **Persistent memory** across container restarts and rebuilds
- **Multi-container coordination** - avoid duplicate work, share state
- **Automatic resumption** - pick up where you left off
- **Context preservation** - all decisions, blockers, notes persist

### Storage
- **Git-backed**: Persists in `~/.jib-sharing/beads/` on host
- **Access**: `~/beads/` in container (all containers share same database)
- **Format**: Human-readable JSONL + SQLite cache

### Quick Reference
- `bd --help` - Command help
- `@beads-status` - View current tasks and recommendations
- `@beads-sync` - Force git sync and cache rebuild

**Remember**: You manage Beads automatically based on context and inputs. The user doesn't need to tell you to create/update tasks - you do it proactively.
