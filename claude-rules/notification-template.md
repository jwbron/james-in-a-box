# Notification Template

When you need to send an asynchronous notification to the human, use this template.

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

## Template

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
📂 Working in: ~/sharing/staged-changes/webapp/services/user-service/
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
📂 Working in: ~/sharing/staged-changes/webapp/services/auth-service/
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
📂 Working in: ~/sharing/staged-changes/webapp/migrations/
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
