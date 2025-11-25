# Notification Template

When you need to send an asynchronous notification to the human, use this template.

## Thread Context (IMPORTANT)

Notifications support YAML frontmatter for Slack threading. When you create a notification
that should reply in an existing thread, include the `thread_ts` field:

```markdown
---
task_id: "task-20251124-111907"
thread_ts: "1732428847.123456"
---
# Your notification content...
```

**How threading works:**
1. When you receive a task via Slack, the incoming message file contains `thread_ts` in its frontmatter
2. When you create a response notification, include that same `thread_ts` in your notification's frontmatter
3. The host notifier will parse this frontmatter and reply in the correct Slack thread

**When to include thread_ts:**
- When responding to a Slack task (the task file will have the thread_ts)
- When creating follow-up messages to an existing conversation
- When you want your notification to appear as a thread reply, not a new message

**When NOT to include thread_ts:**
- For new, standalone notifications (guidance requests, reports, etc.)
- When you want to start a fresh conversation

## Notification Patterns

There are two patterns for notifications:

### 1. Simple Guidance Request (Single File)
Used when you need human input or guidance on a decision. Creates a single notification file.

### 2. Automated Reports (Summary + Thread)
Used for automated analysis reports from scheduled jobs. Creates two files:
- **Summary file**: `{timestamp}-{topic}.md` - Concise top-level message
- **Detail file**: `RESPONSE-{timestamp}-{topic}.md` - Full context in thread

**Key principle**: Mobile-first Slack experience. The summary should be readable at a glance, with full details available in the thread.

## When to Send Notifications

Send notifications when:
- ✅ Found a better approach than what was requested
- ✅ Skeptical about the proposed solution
- ✅ Need architectural decision not covered by ADRs
- ✅ Discovered unexpected complexity
- ✅ Found a critical issue or security concern
- ✅ Made an important assumption that needs validation
- ✅ Stuck after reasonable debugging
- ✅ Need cross-team coordination
- ✅ Proposed approach conflicts with ADR or best practices

**Do NOT send for**:
- ❌ Minor implementation details
- ❌ Questions you can answer by checking Confluence/ADRs
- ❌ Routine status updates (use conversation instead)
- ❌ Trivial choices (pick reasonable default)

## Pattern 1: Simple Guidance Request

Use this for ad-hoc questions and guidance needs.

### Template

```bash
cat > ~/sharing/notifications/$(date +%Y%m%d-%H%M%S)-brief-topic.md <<'EOF'
# 🔔 Need Guidance: [Brief Topic - 5 words max]

**Priority**: [Low/Medium/High/Urgent]
**Topic**: [Architecture/Implementation/Security/Performance/Other]
**Project**: [JIRA ticket or project name]

## Context
[1-2 sentences: What you're working on]

## Issue/Question
[What you need guidance on - be specific]

## Current Approach
[What was requested or what you're currently doing]

## Alternative/Concern
[Better approach you found, or concern you have with current approach]

## Analysis
**Pros of alternative**:
- [Benefit 1]
- [Benefit 2]

**Cons/Risks**:
- [Risk 1]
- [Risk 2]

**Impact if we proceed with original**:
- [What happens if we don't change course]

## Recommendation
[Clear, specific recommendation: "I recommend we X because Y"]

## Can I proceed?
- [ ] Yes, proceed with original approach
- [ ] Yes, proceed with alternative
- [ ] Wait for discussion
- [ ] Other: ___________

---
📅 $(date)
📂 Working in: [directory/repo]
🔗 References: [ADR links, JIRA tickets, etc.]
EOF
```

## Priority Guidelines

**Urgent**: Blocks current work, security issue, data loss risk
**High**: Significant architectural decision, breaking change
**Medium**: Better approach available, skeptical about solution
**Low**: Nice-to-have improvement, informational

## Examples

### Example 1: Better Approach Found

```markdown
# 🔔 Need Guidance: More Efficient Caching Strategy

**Priority**: Medium
**Topic**: Architecture
**Project**: JIRA-1234 User Service Caching

## Context
Implementing Redis caching for user service to reduce database load.

## Issue/Question
Spec says to cache user objects, but I found that caching user sessions
would be more effective and cover more use cases.

## Current Approach
Cache user objects as specified in JIRA-1234:
- Cache user profile data
- TTL of 1 hour
- Invalidate on profile update

## Alternative/Concern
Cache user sessions instead:
- Includes user profile + permissions + preferences
- Same TTL, same invalidation
- Reduces DB queries for multiple downstream services

## Analysis
**Pros of alternative**:
- Reduces DB load by 80% instead of 40% (measured in staging)
- auth-service, settings-service also benefit
- Aligns with ADR-087 (session-based caching)

**Cons/Risks**:
- Slightly larger cache entries (~2KB vs ~1KB)
- Need to coordinate with auth-service team (5 min conversation)

**Impact if we proceed with original**:
- Will likely need to refactor to session caching in 2-3 months
- auth-service will implement duplicate caching logic

## Recommendation
I recommend we switch to session caching because it's more efficient,
aligns with ADR-087, and prevents future refactoring.

## Can I proceed?
- [ ] Yes, proceed with original (user objects)
- [ ] Yes, proceed with alternative (user sessions)
- [ ] Wait for discussion
- [ ] Other: ___________

---
📅 2025-11-21 14:30:00
📂 Working in: ~/khan/webapp/services/user-service/
🔗 References: JIRA-1234, ADR-087
```

### Example 2: Security Concern

```markdown
# 🔔 Need Guidance: Security Issue with Proposed Approach

**Priority**: High
**Topic**: Security
**Project**: JIRA-5678 Token Refresh Implementation

## Context
Implementing auth token refresh mechanism as specified in JIRA-5678.

## Issue/Question
Spec says to store refresh tokens in localStorage, but this creates
an XSS vulnerability that conflicts with ADR-042.

## Current Approach
Per JIRA-5678 spec:
- Store refresh token in localStorage
- Access on page load to check if access token needs refresh

## Alternative/Concern
Use httpOnly cookies instead:
- Browser automatically sends with requests
- Inaccessible to JavaScript (XSS protection)
- Aligns with ADR-042 (security best practices)

## Analysis
**Pros of alternative**:
- Prevents XSS attacks (token can't be stolen by malicious scripts)
- Follows ADR-042: "Never store auth credentials in localStorage"
- Industry best practice (OWASP recommendation)

**Cons/Risks**:
- Requires backend changes to set cookie
- CORS configuration might need update
- Slightly different client-side code

**Impact if we proceed with original**:
- Security vulnerability (XSS could steal refresh tokens)
- Will fail security review
- Need to refactor before production

## Recommendation
I recommend we use httpOnly cookies because localStorage storage
violates ADR-042 and creates a security vulnerability.

## Can I proceed?
- [ ] Yes, proceed with original (localStorage) - ⚠️ security risk
- [ ] Yes, proceed with alternative (httpOnly cookies)
- [ ] Wait for discussion
- [ ] Other: ___________

---
📅 2025-11-21 14:45:00
📂 Working in: ~/khan/webapp/services/auth-service/
🔗 References: JIRA-5678, ADR-042, OWASP A7:2021
```

### Example 3: Unexpected Complexity

```markdown
# 🔔 Need Guidance: Database Migration More Complex Than Expected

**Priority**: High
**Topic**: Implementation
**Project**: JIRA-9999 User Preferences Migration

## Context
Migrating user preferences from JSON blob to structured columns.

## Issue/Question
Migration affects 50M rows and will take ~8 hours with table locks.
Original estimate was 1 hour with no locks.

## Current Approach
Simple ALTER TABLE migration:
- Add new columns
- Backfill from JSON
- Drop JSON column

## Alternative/Concern
Need multi-phase migration with zero downtime:
1. Add columns (schema only)
2. Dual-write to both old and new (code deploy)
3. Backfill in batches (background job, 24 hours)
4. Switch reads to new columns (code deploy)
5. Drop old column (final schema change)

## Analysis
**Pros of alternative**:
- Zero downtime
- Can pause/resume backfill
- Rollback possible at each step

**Cons/Risks**:
- Takes 3-4 days instead of 1 day
- More complex (5 steps vs 1 step)
- Requires code changes for dual-write

**Impact if we proceed with original**:
- 8-hour downtime (unacceptable for production)
- Rollback very difficult if something fails
- Affects all users globally

## Recommendation
I recommend the multi-phase migration because 8 hours of downtime
is not acceptable for a production service with global users.

## Can I proceed?
- [ ] Yes, proceed with original - ⚠️ 8 hour downtime
- [ ] Yes, proceed with alternative (multi-phase)
- [ ] Wait for discussion
- [ ] Other: ___________

---
📅 2025-11-21 15:00:00
📂 Working in: ~/khan/webapp/migrations/
🔗 References: JIRA-9999, Migration Runbook (confluence)
```

## After Sending

**If you need a response before continuing:**

1. **Wait for response** - Check `~/sharing/responses/RESPONSE-[your-timestamp].md`
2. **How to check**:
   ```bash
   # Wait for response file to appear
   while [ ! -f ~/sharing/responses/RESPONSE-20251121-143000.md ]; do
       sleep 10
   done

   # Read the response
   cat ~/sharing/responses/RESPONSE-20251121-143000.md
   ```

3. **Response will arrive via Slack** - Human replies to your notification in Slack, which gets written to `~/sharing/responses/`

4. **Typical wait time**: Anywhere from minutes to hours depending on human availability

**If you can continue without blocking:**

1. Continue working on what you can
2. Periodically check for response
3. Adjust approach when response arrives

## Response Format

Human responds via **Slack thread reply** to your notification.

The response will be written to:
`~/sharing/responses/RESPONSE-[original-timestamp].md`

**Example check**:
```bash
# Your notification timestamp
NOTIF_TS="20251121-143000"

# Check if response exists
if [ -f ~/sharing/responses/RESPONSE-${NOTIF_TS}.md ]; then
    echo "Response received!"
    cat ~/sharing/responses/RESPONSE-${NOTIF_TS}.md
else
    echo "No response yet, continuing with fallback approach..."
fi
```

## When to Block vs. Continue

**Block (wait for response)**:
- Security concerns require human approval
- Architectural decision with major impact
- Ambiguous requirements - cannot proceed either way
- Destructive operation (data loss, breaking changes)

**Continue (don't block)**:
- Better approach found but can proceed with original if needed
- Minor implementation detail questions
- Performance optimizations
- Nice-to-have improvements

**Use your judgment**: If you can make reasonable progress while waiting, do so. If you're completely blocked, it's okay to wait.

## Pattern 2: Automated Reports with Threading

Use this pattern for automated analysis reports (conversation analyzer, codebase analyzer, etc.).

### File Naming Convention

**Summary file**: `{timestamp}-{topic}.md`
- This creates the top-level Slack message
- Should be concise but informative
- Include key metrics and priority

**Detail file**: `RESPONSE-{timestamp}-{topic}.md`
- This creates a threaded reply under the summary
- Contains full report with all context
- Can be verbose - users can expand to read

### Threading Pattern

```python
# Generate task ID
timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
task_id = f"{timestamp}-{topic}"

# 1. Create summary notification (top-level message)
summary_file = notification_dir / f"{task_id}.md"
summary = f"""# {emoji} {Title}

**Priority**: {priority} | Key metric 1 | Key metric 2

**Quick Stats:**
- Stat 1: {value}
- Stat 2: {value}
- Stat 3: {value}

📄 Full {context_type} in thread below
"""
summary_file.write_text(summary)

# 2. Create detailed report (thread reply)
detail_file = notification_dir / f"RESPONSE-{task_id}.md"
detail = f"""# Full {Title}

## Detailed Section 1
[Full content...]

## Detailed Section 2
[Full content...]

## Next Steps
[Action items...]

---
📅 Generated: {timestamp}
🤖 Automated by {component_name}
"""
detail_file.write_text(detail)
```

### Examples

**Conversation Analyzer Summary**:
```markdown
# 📊 Conversation Analysis Complete

**Priority**: Medium | 12 conversations analyzed | 8 recommendations

**Quick Stats:**
- ✅ Success: 10 | ❌ Failed: 1 | 🚫 Blocked: 1
- Quality: 8.2/10 | Single-iteration success: 75.0%
- 🎯 Prompt improvements: 5 | 💬 Communication improvements: 3

📄 Full report in thread below
```

**Codebase Analyzer Summary**:
```markdown
# 🔍 Codebase Analysis Complete

**Priority**: High | 45 files analyzed | 23 issues found

**Quick Stats:**
- 🔴 HIGH: 8 file issues, 3 web findings
- 🟡 MEDIUM: 12 file issues, 5 web findings
- 🛡️ Security: ADEQUATE

📄 Full analysis in thread below
```

### Guidelines for Summaries

**DO**:
- ✅ Keep to 3-5 lines of key information
- ✅ Use priority indicators (High/Medium/Low)
- ✅ Include 2-4 key metrics
- ✅ Use emojis for quick visual scanning
- ✅ End with "Full [X] in thread below"

**DON'T**:
- ❌ Include full lists or tables
- ❌ Add detailed explanations
- ❌ Repeat information from detail file
- ❌ Use more than 5-6 lines

### Guidelines for Detailed Reports

**DO**:
- ✅ Include all sections from analysis
- ✅ Use proper markdown formatting
- ✅ Group related items together
- ✅ Include next steps and action items
- ✅ Add metadata footer (timestamp, automation source)

**Structure**:
1. Title and metadata
2. Detailed summary section
3. Main analysis sections (2-5 sections)
4. Next steps / action items
5. Footer with timestamp and source

## Pattern 3: Work Completed Notification

Use this pattern when you've completed a task and committed changes to a branch.

**When to use:**
- Finished implementing a feature or fix
- Made commits to a branch
- Task is ready for human review or PR creation
- Need to report what branch contains your changes

### Template

```bash
cat > ~/sharing/notifications/$(date +%Y%m%d-%H%M%S)-work-completed.md <<'EOF'
# ✅ Work Completed: [Brief description]

**Repository**: [repo name]
**Branch**: `[branch-name]`
**Commits**: [number] commit(s)

## What Was Done

[2-3 sentence summary of what was implemented/fixed/changed]

## Changes Made

- [Key change 1]
- [Key change 2]
- [Key change 3]

## Testing

- [Test approach 1]
- [Test approach 2]
- [Test results]

## Next Steps

- [ ] Human review commits on branch `[branch-name]`
- [ ] Create PR: `/pr create [repo]` via Slack (or let me know to create it)
- [ ] [Any other follow-up needed]

---
📅 $(date)
📂 Repository: [~/khan/repo-name]
🔀 Branch: `[branch-name]`
🔗 Related: [JIRA ticket, context doc, etc.]
EOF
```

### Example: Feature Implementation

```markdown
# ✅ Work Completed: OAuth2 Authentication Added

**Repository**: webapp
**Branch**: `feature/oauth2-authentication`
**Commits**: 5 commit(s)

## What Was Done

Implemented OAuth2 authentication for the user service with session-based
caching. Integrated with existing auth-service infrastructure and added
comprehensive test coverage.

## Changes Made

- Added OAuth2Handler class with token exchange and validation
- Created session caching layer (aligned with ADR-087)
- Added 15 unit tests and 3 integration tests
- Updated configuration for OAuth2 client settings
- Added migration for oauth_sessions table

## Testing

- All tests pass: `pytest tests/test_oauth.py` (100% coverage)
- Manual testing: OAuth flow works end-to-end
- Verified backward compatibility with existing session tokens
- Tested token refresh after 1-hour expiry

## Next Steps

- [ ] Human review commits on branch `feature/oauth2-authentication`
- [ ] Create PR: `/pr create webapp` via Slack
- [ ] Coordinate with auth-service team for deployment

---
📅 2025-11-23 10:30:00
📂 Repository: ~/khan/webapp
🔀 Branch: `feature/oauth2-authentication`
🔗 Related: JIRA-1234, ADR-087
```

### Example: Bug Fix

```markdown
# ✅ Work Completed: Fixed Memory Leak in Conversation Analyzer

**Repository**: james-in-a-box
**Branch**: `fix/conversation-analyzer-memory-leak`
**Commits**: 2 commit(s)

## What Was Done

Fixed memory leak in conversation analyzer caused by unclosed file handles.
Added proper context managers and verified leak is resolved.

## Changes Made

- Added context managers (`with` statements) for file operations
- Fixed 3 instances of unclosed file handles
- Added memory profiling test to prevent regression

## Testing

- Memory usage stable after 1000 iterations (was growing before)
- All existing tests still pass
- Added new test: `test_no_memory_leak_in_batch_processing`

## Next Steps

- [ ] Human review commits on branch `fix/conversation-analyzer-memory-leak`
- [ ] Create PR: `/pr create` via Slack (targeting main)

---
📅 2025-11-23 11:15:00
📂 Repository: ~/khan/james-in-a-box
🔀 Branch: `fix/conversation-analyzer-memory-leak`
🔗 Related: Discovered during weekly analysis
```

### Guidelines for Work Completed Notifications

**Always include:**
- ✅ Repository name (which repo in ~/khan/)
- ✅ Branch name (where the commits are)
- ✅ Number of commits
- ✅ What was done (brief summary)
- ✅ Key changes (bulleted list)
- ✅ Testing performed
- ✅ Next steps (usually PR creation)

**Be specific:**
- Mention the exact branch name so human can find your work
- Include commit count so human knows scope
- Specify which repo (especially important with multiple repos)
- Reference any related tickets, ADRs, or context docs

**Next steps should guide human:**
- Typically: review commits, create PR
- Sometimes: additional testing needed, coordination with other teams
- Make it clear what action you're expecting from human
