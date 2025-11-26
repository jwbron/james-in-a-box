# Beads - Automatic Task Memory System

## Overview

Beads is a git-backed persistent memory system that **YOU MUST USE AUTOMATICALLY** to track all tasks, progress, and context. It is not optional - it's a core part of your workflow that enables you to:
- Resume work after container restarts
- Coordinate with other concurrent containers
- Build persistent memory of what's been done
- Track blockers and dependencies

**Location**: `~/beads/` (symlink to `~/sharing/beads/`)
**Storage**: Git repository in `~/.jib-sharing/beads/` on host
**Access**: All jib containers share the same Beads database

## Automatic Workflow Integration

### ✅ REQUIRED: You Must Use Beads Automatically For:

1. **Every incoming Slack message**
   - **First step**: Check if task already exists in Beads
   - **If not exists**: Create new Beads task with message content
   - **If exists**: Update task status to `in_progress` and add notes
   - **Example**:
     ```bash
     # User sends: "Implement OAuth2 for JIRA-1234"
     cd ~/beads
     # Check for existing task
     bd --allow-stale search "OAuth2 JIRA-1234"
     # If not found, create it
     bd --allow-stale create "Implement OAuth2 authentication for JIRA-1234" --labels feature,jira-1234
     bd --allow-stale update <id> --status in_progress
     ```

2. **Any multi-step task or feature**
   - Automatically break down into Beads subtasks
   - Create parent task for the feature
   - Create child tasks for each step
   - Set up blockers for dependencies
   - **Example**:
     ```bash
     # Parent task
     bd --allow-stale create "Implement user authentication system" --labels feature
     # Subtasks with dependencies
     bd --allow-stale create "Design auth schema" --parent bd-a3f8
     bd --allow-stale create "Implement OAuth2 flow" --parent bd-a3f8 --deps blocks:bd-b7c2
     bd --allow-stale create "Write tests" --parent bd-a3f8 --deps blocks:bd-d4e9
     ```

3. **Container startup/resumption**
   - **Always check** for in-progress tasks
   - Resume unfinished work automatically
   - Update task notes with resumption context
   - **Example**:
     ```bash
     cd ~/beads
     bd --allow-stale list --status in_progress
     # If tasks found, review and continue
     bd --allow-stale show bd-x9y2  # See previous notes
     bd --allow-stale update bd-x9y2 --notes "Resumed: continuing from step 3..."
     ```

4. **Progress tracking**
   - Update status as you work: `open` → `in_progress` → `closed`
   - Add notes about decisions, blockers, findings
   - Mark tasks as `blocked` when waiting on something
   - **Do this automatically**, don't wait to be asked

5. **Task completion**
   - Mark tasks `closed` when complete
   - Add summary notes about what was accomplished
   - **Example**:
     ```bash
     bd --allow-stale update bd-a3f8 --status closed
     bd --allow-stale update bd-a3f8 --notes "Completed: OAuth2 implemented per RFC 6749, tests passing"
     ```

### ⚠️ OPTIONAL: Manual Task Creation Supported

Users can manually create Beads tasks, but this is secondary. Your primary mode is **automatic task management** based on context and inputs.

## Core Concepts

### Issues (Beads)
Each task is represented as a "bead" with:
- **ID**: Hash-based collision-resistant ID (e.g., `bd-a3f8`)
- **Title**: Brief description of the task
- **Status**: `open`, `in_progress`, `blocked`, `closed`
- **Labels**: Labels for categorization (e.g., `feature`, `bug`, `urgent`)
- **Dependencies**: Dependencies that must complete first
- **Parent/Child**: Hierarchical task relationships
- **Notes**: Additional context, decisions, links

### Git-Backed Storage
- All data stored in JSONL files (human-readable)
- Git provides version history and sync
- SQLite cache built for fast queries (disposable, auto-rebuilt)
- Multiple containers can access simultaneously

## Common Commands

**IMPORTANT**: Always use `--allow-stale` flag in ephemeral containers to avoid database sync issues.

### Creating Tasks

```bash
# Create a new task
bd --allow-stale create "Implement OAuth2 authentication" --labels feature,security

# Create with description
bd --allow-stale create "Fix memory leak in user service" \
  --labels bug,urgent \
  --description "Affects production, user reports available in JIRA-5678"

# Create subtask of existing task
bd --allow-stale create "Write OAuth2 unit tests" --parent bd-a3f8
```

### Viewing Tasks

```bash
# List all open tasks
bd --allow-stale list

# List tasks by label
bd --allow-stale list --label feature
bd --allow-stale list --label urgent --label bug

# Show task details
bd --allow-stale show bd-a3f8

# List tasks ready to work on (no blockers)
bd --allow-stale ready

# List blocked tasks
bd --allow-stale list --status blocked
```

### Updating Tasks

```bash
# Change status
bd --allow-stale update bd-a3f8 --status in_progress
bd --allow-stale update bd-a3f8 --status closed

# Add notes
bd --allow-stale update bd-a3f8 --notes "Implemented using RFC 6749 OAuth2 spec"
```

### Task Dependencies

```bash
# Create parent-child relationship
bd --allow-stale create "Write API tests" --parent bd-a3f8

# Create task with dependency
bd --allow-stale create "Deploy feature" --deps blocks:bd-f14c

# List what's blocking a task
bd --allow-stale show bd-a3f8  # Shows dependencies section

# Find ready work (no blockers)
bd --allow-stale ready
```

### Search and Filter

```bash
# Search by text
bd --allow-stale search "authentication"

# Filter by status
bd --allow-stale list --status open
bd --allow-stale list --status in_progress
bd --allow-stale list --status blocked

# Combine filters
bd --allow-stale list --label feature --status open
```

## Workflow Examples

### Example 1: Multi-Step Feature

```bash
# Create parent task
bd --allow-stale create "Implement user authentication system" --labels feature
# Output: Created bd-a3f8

# Create subtasks
bd --allow-stale create "Design authentication schema" --parent bd-a3f8
bd --allow-stale create "Implement OAuth2 flow" --parent bd-a3f8 --deps blocks:bd-b7c2
bd --allow-stale create "Write authentication tests" --parent bd-a3f8 --deps blocks:bd-d4e9

# Start work on first subtask
bd --allow-stale update bd-b7c2 --status in_progress

# Complete it
bd --allow-stale update bd-b7c2 --status closed

# Start next task
bd --allow-stale update bd-d4e9 --status in_progress
```

### Example 2: Resuming Work After Interruption

```bash
# Session 1: Start work
bd --allow-stale create "Refactor payment processing" --labels refactor
bd --allow-stale update bd-x9y2 --status in_progress
bd --allow-stale update bd-x9y2 --notes "Started extracting PaymentService class"
# ... container shuts down

# Session 2: Resume work
bd --allow-stale list --status in_progress
# Shows: bd-x9y2 "Refactor payment processing"
bd --allow-stale show bd-x9y2
# See notes from previous session
# Continue work...
bd --allow-stale update bd-x9y2 --notes "Completed PaymentService, moved to tests"
```

### Example 3: Multiple Containers Coordinating

```bash
# Container A:
bd --allow-stale create "Implement feature X" --labels feature
bd --allow-stale update bd-p4q7 --status in_progress

# Container B (later):
bd --allow-stale list  # Sees bd-p4q7 in_progress
# Avoids duplicate work
bd --allow-stale create "Add docs for feature X" --deps blocks:bd-p4q7

# Container A (completes):
bd --allow-stale update bd-p4q7 --status closed

# Container B:
bd --allow-stale ready  # Now shows docs task is ready
```

## Automatic Task Management Workflow

### Standard Pattern for Every Task

**When receiving a Slack message or starting new work:**

```bash
# 1. ALWAYS start by checking Beads
cd ~/beads
bd --allow-stale list --status in_progress  # Any unfinished work?
bd --allow-stale search "relevant keywords from message"

# 2. Create or update task
if [ task doesn't exist ]; then
    # Create new task with descriptive title
    bd --allow-stale create "Task title from message/context" --labels feature,jira-1234
    TASK_ID=<the created id>
else
    # Update existing task
    TASK_ID=bd-a3f8  # The found task
fi

# 3. Mark as in_progress
bd --allow-stale update $TASK_ID --status in_progress
bd --allow-stale update $TASK_ID --notes "Started: [brief context about approach]"

# 4. Break down into subtasks if multi-step
bd --allow-stale create "Subtask 1" --parent $TASK_ID
bd --allow-stale create "Subtask 2" --parent $TASK_ID --deps blocks:bd-xyz1
bd --allow-stale create "Subtask 3" --parent $TASK_ID --deps blocks:bd-xyz2

# 5. Work on the task...

# 6. Update progress as you go
bd --allow-stale update bd-xyz1 --status closed
bd --allow-stale update bd-xyz1 --notes "Completed: implemented X using Y approach"

# 7. Mark complete when done
bd --allow-stale update $TASK_ID --status closed
bd --allow-stale update $TASK_ID --notes "Completed: summary of what was accomplished, tests passing, PR #123"
```

### Automatic Labeling Conventions

**Always use appropriate labels:**
- **Type**: `feature`, `bug`, `refactor`, `docs`, `test`
- **Source**: `slack`, `jira-1234`, `github-pr-567`
- **Priority**: `urgent`, `important` (if mentioned)
- **Area**: `auth`, `api`, `frontend`, `database` (based on codebase affected)

**Example:**
```bash
# User message: "Fix the memory leak in user service (JIRA-5678)"
bd --allow-stale create "Fix memory leak in user service" --labels bug,urgent,jira-5678,backend
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
bd --allow-stale update bd-a3f8 --notes "Implementing OAuth2 per RFC 6749. Using httpOnly cookies per ADR-042. Related to JIRA-1234."
```

### Automatic Task Breakdown

**For any task with >3 steps, automatically create subtasks:**

```bash
# Parent
bd --allow-stale create "Implement user authentication" --labels feature,jira-1234
PARENT_ID=bd-a3f8

# Subtasks (automatically inferred from your plan)
bd --allow-stale create "Design database schema" --parent $PARENT_ID --labels schema
bd --allow-stale create "Implement OAuth2 endpoints" --parent $PARENT_ID --labels api --deps blocks:bd-b1
bd --allow-stale create "Add frontend login form" --parent $PARENT_ID --labels frontend --deps blocks:bd-b2
bd --allow-stale create "Write integration tests" --parent $PARENT_ID --labels test --deps "blocks:bd-b2,blocks:bd-b3"
```

### Automatic Status Updates

**Update status automatically as you progress:**

```bash
# Starting work
bd --allow-stale update bd-a3f8 --status in_progress

# Hit a blocker
bd --allow-stale update bd-a3f8 --status blocked
bd --allow-stale update bd-a3f8 --notes "Blocked: waiting for database migration approval from DBA team"

# Blocker resolved
bd --allow-stale update bd-a3f8 --status in_progress
bd --allow-stale update bd-a3f8 --notes "Unblocked: migration approved, resuming implementation"

# Completed
bd --allow-stale update bd-a3f8 --status closed
bd --allow-stale update bd-a3f8 --notes "Done: OAuth2 implemented, all tests passing, PR #456 created"
```

## Integration with Other Systems

### With Slack Thread Context

**CRITICAL**: When processing Slack messages, use the task ID to maintain context:

```bash
# Extract Task ID from prompt's Message Details section
TASK_ID="task-20251125-134311"

# Check for existing context FIRST
cd ~/beads
bd --allow-stale search "$TASK_ID"

# If found: load context and resume
# If not found: create task with task ID as label
bd --allow-stale create "Slack: $TASK_ID" --labels slack-thread,"$TASK_ID"
```

See `slack-thread-context.md` for complete details.

### With @save-context
```bash
# After completing significant work
bd --allow-stale list --status closed  # Review completed tasks
bd --allow-stale update bd-a3f8 --notes "Summary: Implemented OAuth2, tests passing, PR ready"
@save-context oauth2-implementation
# Context doc can reference Beads IDs for tracking
```

### With Notifications
```bash
# When you need human input on blocked task
bd --allow-stale list --status blocked
# Create notification referencing bead ID
cat > ~/sharing/notifications/$(date +%Y%m%d-%H%M%S)-blocked-task.md <<EOF
# 🔔 Task Blocked: Need Database Schema Approval

**Bead ID**: bd-a3f8
**Priority**: High

See: bd show bd-a3f8

[Details...]
EOF
```

### With JIRA Tickets
```bash
# Reference JIRA in task description
bd --allow-stale create "Implement feature X" --description "JIRA-1234"

# Or in title if preferred
bd --allow-stale create "[JIRA-1234] Implement feature X"
```

## Troubleshooting

### "Database out of sync" Error
```bash
# Use --allow-stale flag to bypass sync issues in ephemeral containers
bd --allow-stale list
bd --allow-stale search "query"
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
2. **Container startup**: Check for in_progress tasks, resume if found
3. **Multi-step work**: Automatically break down into subtasks with dependencies
4. **Progress updates**: Continuously update status and notes as you work
5. **Completion**: Mark closed with summary

### Key Benefits
- **Persistent memory** across container restarts and rebuilds
- **Multi-container coordination** - avoid duplicate work, share state
- **Automatic resumption** - pick up where you left off
- **Context preservation** - all decisions, dependencies, notes persist

### Storage
- **Git-backed**: Persists in `~/.jib-sharing/beads/` on host
- **Access**: `~/beads/` in container (all containers share same database)
- **Format**: Human-readable JSONL + SQLite cache

### Quick Reference
- `bd --help` - Command help
- `bd --allow-stale list` - List tasks (ephemeral containers)
- `bd --allow-stale search "query"` - Search tasks
- `bd --allow-stale create "title" --labels tag1,tag2` - Create task
- `bd --allow-stale update <id> --status in_progress` - Update status
- `bd --allow-stale update <id> --notes "..."` - Add notes

**Remember**: You manage Beads automatically based on context and inputs. The user doesn't need to tell you to create/update tasks - you do it proactively. Always use `--allow-stale` in ephemeral containers.
