# Workflow Context and Traceability

**Status**: Implemented
**Date**: 2025-11-30

## Overview

JIB automatically adds workflow context to all outputs (PRs, comments, Slack messages, logs) so users can identify which job/workflow generated each action. This provides complete traceability for autonomous operations.

## Problem Statement

When JIB operates autonomously through multiple workflows (GitHub watcher, Slack tasks, scheduled jobs), users need to:
1. Identify which workflow created a PR or comment
2. Debug issues by tracing back to the originating job
3. Understand the context in which automated decisions were made
4. Audit autonomous operations for compliance and review

## Solution

### Workflow Identification

Each workflow execution gets a unique ID with the format:
```
gw-<workflow_type>-<timestamp>-<random>
```

Examples:
- `gw-check_failure-20251130-102305-a1b2c3d4` - GitHub watcher handling check failure
- `gw-comment-20251130-143022-f4e5d6c7` - GitHub watcher responding to comment
- `slack-task-20251130-151500-9a8b7c6d` - Slack task processor

### Components

#### 1. LogContext Extension

**File**: `shared/jib_logging/context.py`

Added fields:
- `workflow_id`: Unique identifier for the workflow/job
- `workflow_type`: Type of workflow (e.g., 'check_failure', 'comment', 'slack_task')

```python
from jib_logging import ContextScope

with ContextScope(
    workflow_id="gw-check_failure-20251130-102305-a1b2",
    workflow_type="check_failure",
    repository="owner/repo",
    pr_number=123,
):
    # All operations within this scope inherit the context
    logger.info("Processing check failure")  # Includes workflow_id in logs
```

#### 2. NotificationContext Extension

**File**: `shared/notifications/types.py`

Added fields:
- `workflow_id`: Included in notification frontmatter
- `workflow_type`: Visible in notification footer

Notifications now render with workflow context:
```markdown
# Notification Title

Body content here...

---
Repo: owner/repo | PR: #123

_(Workflow: Check Failure | ID: `gw-check_failure-20251130-102305-a1b2`)_
```

#### 3. Signature Helpers

**File**: `shared/jib_logging/signatures.py`

Utilities for adding workflow signatures to GitHub operations:

```python
from jib_logging.signatures import (
    add_signature_to_pr_body,
    add_signature_to_comment,
    get_workflow_signature,
)

# PR descriptions
pr_body = add_signature_to_pr_body("Description here")
# Appends: _(Workflow: Check Failure | ID: `gw-...`)_

# GitHub comments
comment = add_signature_to_comment("Comment text here")
# Appends workflow signature

# Raw signature
sig = get_workflow_signature(include_trace_id=True)
# Returns: "_(Workflow: Check Failure | ID: `gw-...` | Trace: `abc12345...`)_"
```

#### 4. Workflow ID Generation

**File**: `host-services/analysis/github-watcher/github-watcher.py`

The github-watcher generates workflow IDs when invoking jib:

```python
# In invoke_jib()
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
workflow_id = f"gw-{task_type}-{timestamp}-{secrets.token_hex(4)}"

context["workflow_id"] = workflow_id
context["workflow_type"] = task_type
```

#### 5. Context Propagation

**File**: `jib-container/jib-tasks/github/github-processor.py`

The container processor establishes workflow context at the entry point:

```python
# Extract workflow context from incoming context
workflow_id = context.get("workflow_id")
workflow_type = context.get("workflow_type", args.task)

# Establish logging context for entire execution
with ContextScope(
    workflow_id=workflow_id,
    workflow_type=workflow_type,
    repository=repository,
    pr_number=pr_number,
):
    # All handlers and operations inherit this context
    handler(context)
```

## Usage Examples

### Example 1: GitHub Check Failure

1. **Host watcher** detects failing check:
   - Generates `workflow_id = "gw-check_failure-20251130-102305-a1b2c3d4"`
   - Invokes container with context including workflow_id

2. **Container processor** establishes ContextScope:
   - All logs include `workflow_id` and `workflow_type`
   - Beads task tracks workflow context

3. **Claude** fixes issues:
   - Commits changes
   - Posts comment using `add_signature_to_comment()`
   - Comment includes: `_(Workflow: Check Failure | ID: `gw-check_failure-20251130-102305-a1b2c3d4`)_`

4. **User sees**:
   - GitHub comment clearly identifies it came from check_failure workflow
   - Can correlate with logs using workflow_id
   - Understands context of the automated fix

### Example 2: Slack Notification

1. **Container** sends notification:
   ```python
   from notifications import slack_notify, NotificationContext
   from jib_logging import get_current_context

   ctx = get_current_context()
   notification_ctx = NotificationContext(
       task_id=beads_id,
       repository="owner/repo",
       pr_number=123,
       workflow_id=ctx.workflow_id,
       workflow_type=ctx.workflow_type,
   )

   slack_notify("Task Complete", "Fixed check failures", context=notification_ctx)
   ```

2. **Slack message shows**:
   ```
   Task Complete

   Fixed check failures

   ---
   Repo: owner/repo | PR: #123

   _(Workflow: Check Failure | ID: `gw-check_failure-20251130-102305-a1b2`)_
   ```

## Benefits

### 1. Traceability
- Every automated action can be traced back to its originating workflow
- Workflow IDs appear in logs, PR comments, and Slack notifications
- Easy to correlate related actions across systems

### 2. Debugging
- When investigating issues, workflow_id provides complete context
- Logs can be filtered by workflow_id to see full execution trace
- Parallel workflows don't get confused

### 3. Audit Trail
- Clear record of which workflow made which decisions
- Supports compliance and review processes
- Users can verify autonomous operations

### 4. User Trust
- Transparency about automation builds trust
- Users understand what's happening and why
- Clear attribution for all automated actions

## Integration Points

### Automatic Integration

These components automatically include workflow context when used within a ContextScope:

1. **Logs** (`jib_logging.get_logger()`)
   - All structured logs include `workflow_id` and `workflow_type`

2. **Notifications** (`notifications.slack_notify()`)
   - Workflow context appears in Slack message footer

3. **Beads Tasks** (when created within ContextScope)
   - Task metadata includes workflow context

### Manual Integration

For GitHub operations, use the signature helpers:

```python
from jib_logging.signatures import add_signature_to_comment, add_signature_to_pr_body

# PR descriptions
pr_body = add_signature_to_pr_body(body_text)

# Comments
comment = add_signature_to_comment(comment_text)
```

## Future Enhancements

1. **Web UI for Workflow Exploration**
   - Browse workflows by ID
   - View complete execution trace
   - Link to related PRs, comments, logs

2. **Workflow Metrics**
   - Track workflow success rates
   - Identify problematic workflow types
   - Performance monitoring

3. **Workflow Replay**
   - Re-run failed workflows
   - Test workflow changes
   - Debugging aid

4. **Cross-Repository Correlation**
   - Track workflows that span multiple repos
   - Dependency analysis
   - Impact assessment

## References

- **Implementation PR**: [To be added]
- **LogContext docs**: `shared/jib_logging/README.md`
- **Notifications docs**: `shared/notifications/README.md`
- **CLAUDE.md**: Workflow context instructions for Claude

## Testing

### Manual Test

1. Trigger github-watcher on a PR with failing checks
2. Verify workflow_id is generated and logged
3. Check that PR comment includes workflow signature
4. Verify Slack notification shows workflow context
5. Correlate logs using workflow_id

### Automated Test

```python
def test_workflow_context_propagation():
    """Test that workflow context propagates correctly."""
    from jib_logging import ContextScope, get_current_context
    from jib_logging.signatures import get_workflow_signature

    workflow_id = "test-workflow-123"
    workflow_type = "test"

    with ContextScope(workflow_id=workflow_id, workflow_type=workflow_type):
        ctx = get_current_context()
        assert ctx.workflow_id == workflow_id
        assert ctx.workflow_type == workflow_type

        sig = get_workflow_signature()
        assert workflow_id in sig
        assert "Test" in sig  # workflow_type formatted as "Test"
```

## Troubleshooting

### Workflow ID Not Appearing in Logs

**Problem**: Logs don't include `workflow_id` field

**Diagnosis**:
1. Check if `ContextScope` was established at the entry point
2. Verify workflow_id was passed in the context dict
3. Check that you're using structured logging (`logger.info()`, not `print()`)

**Solution**:
```python
# Ensure ContextScope is established
from jib_logging import ContextScope

workflow_id = context.get("workflow_id")
workflow_type = context.get("workflow_type", "unknown")

with ContextScope(workflow_id=workflow_id, workflow_type=workflow_type):
    # All operations in this scope will have workflow context
    logger.info("Processing task")
```

### Workflow Signature Missing from GitHub Comments

**Problem**: PR comments don't include workflow signature

**Diagnosis**:
1. Check if `add_signature_to_comment()` was called
2. Verify ContextScope includes workflow_id and workflow_type
3. Check for errors in signature helper

**Solution**:
```python
from jib_logging.signatures import add_signature_to_comment

# Use try/except to ensure failures don't block the task
try:
    comment_with_sig = add_signature_to_comment("Your comment")
except Exception as e:
    logger.warning(f"Failed to add signature: {e}")
    comment_with_sig = "Your comment"  # Fallback to unsigned

# Post the comment
```

### Workflow Context Not Propagating

**Problem**: Nested functions/calls don't have workflow context

**Diagnosis**:
1. Ensure you're within a ContextScope
2. Check that context is being read with `get_current_context()`
3. Verify you're not creating a new context that overwrites workflow fields

**Solution**:
```python
# Parent function establishes scope
with ContextScope(workflow_id="abc", workflow_type="test"):
    # Child function automatically inherits context
    child_function()

def child_function():
    # Access inherited context
    ctx = get_current_context()
    assert ctx.workflow_id == "abc"
```

### Workflow Signature Format Issues

**Problem**: Workflow type displays as `check_failure` instead of `Check Failure`

**Diagnosis**: Using `workflow_type` directly instead of formatted version

**Solution**: The signature helpers automatically format workflow_type with `.replace("_", " ").title()`. If you're manually building signatures, use the same formatting:

```python
workflow_display = workflow_type.replace("_", " ").title()
```

### Verifying Workflow Context

**To verify workflow context is working correctly**:

1. **Check logs**: Look for `workflow_id` and `workflow_type` fields in structured log output
2. **Check GitHub comments**: Look for signature at end: `_(Workflow: ... | ID: ...)_`
3. **Check Slack notifications**: Look for workflow context in footer
4. **Correlate across systems**: Use workflow_id to find related entries in logs, GitHub, and Slack

**Example verification**:
```bash
# Search logs for workflow_id
grep "gw-check_failure-20251130-102305" ~/.jib-sharing/logs/*.log

# Check GitHub for matching signature
# (search PR comments for the workflow_id)

# Check Slack for notification with same workflow_id
```

## Migration Notes

### Existing Code

No migration required for most code. Workflow context is:
- **Opt-in** via ContextScope
- **Backward compatible** - code without ContextScope continues to work
- **Additive** - only adds fields, doesn't remove anything

### Recommended Updates

For code that invokes workflows (like github-watcher):
1. Generate workflow_id
2. Pass in context dict
3. Establish ContextScope at entry point

Example:
```python
# Before
context = {"repository": repo, "pr_number": pr_num}
invoke_container(context)

# After
workflow_id = generate_workflow_id(task_type)
context = {
    "repository": repo,
    "pr_number": pr_num,
    "workflow_id": workflow_id,
    "workflow_type": task_type,
}
invoke_container(context)
```
