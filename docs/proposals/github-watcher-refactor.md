# GitHub Watcher Refactor: Splitting into Three Services

## Summary

Refactor the monolithic `github-watcher.py` into three distinct services with clear responsibilities:

1. **Comment Responder** - Respond to PR comments
2. **PR Reviewer** - Review PRs using collaborative development framework
3. **CI/Conflict Fixer** - Fix check failures and merge conflicts

## Current State Analysis

### Existing Architecture

The current `github-watcher.py` (~2300 lines) handles all GitHub PR monitoring in a single service:
- Check failure detection and fixing
- Comment detection and response
- Merge conflict detection and resolution
- PR review requests (from others)
- Review response handling (on bot's own PRs)

**Current Scope Logic:**
- **Writable repos**: Full functionality for user's PRs, bot's PRs, and reviewing other authors' PRs
- **Read-only repos**: Notification-only mode, limited functionality

### Current Trigger Conditions

| Task Type | Current Trigger | Proposed Service |
|-----------|-----------------|------------------|
| `check_failure` | User's PRs + Bot's PRs (writable repos) | CI/Conflict Fixer |
| `merge_conflict` | User's PRs + Bot's PRs (writable repos) | CI/Conflict Fixer |
| `comment` | User's PRs + Bot's PRs | Comment Responder |
| `review_request` | All PRs from other authors (proactive) | PR Reviewer |
| `pr_review_response` | Bot's PRs receiving reviews | Comment Responder |

## Proposed Architecture

### Service 1: Comment Responder (`comment-responder`)

**Purpose**: Respond to comments and review feedback on PRs where jib is engaged.

**Trigger Conditions:**
- PRs where `james-in-a-box` is **assigned**
- PRs where `james-in-a-box` is **tagged** (mentioned in comment)
- PRs where `james-in-a-box` is the **author**

**Task Types:**
- `comment` - Respond to new comments
- `pr_review_response` - Address review feedback on bot's PRs

**Capabilities:**
- Post comments via `gh pr comment`
- Push code changes to address feedback
- Update PR descriptions

**Repos:** All configured `writable_repos`

---

### Service 2: PR Reviewer (`pr-reviewer`)

**Purpose**: Review PRs where jib's review is requested, using collaborative development framework.

**Trigger Conditions:**
- PRs where `james-in-a-box` is **assigned** (as reviewer)
- PRs where `james-in-a-box` is **tagged** (mentioned requesting review)

**Task Types:**
- `review_request` - Perform code review

**Capabilities:**
- Post reviews via `gh pr review`
- Post inline comments
- (Future) Apply collaborative development framework methodology

**Repos:** All configured `writable_repos` + `readable_repos` (for read-only, output to Slack)

**Note:** This is a change from current behavior, which proactively reviews *all* PRs from other authors. The new behavior is opt-in (jib must be explicitly assigned/tagged).

---

### Service 3: CI/Conflict Fixer (`ci-fixer`)

**Purpose**: Automatically fix check failures and merge conflicts on PRs authored by jib or the configured user.

**Trigger Conditions:**
- PRs authored by `james-in-a-box` (bot)
- PRs authored by `github_username` (configured user, e.g., `jwbron`)

**Task Types:**
- `check_failure` - Detect and fix failing CI checks
- `merge_conflict` - Detect and resolve merge conflicts

**Capabilities:**
- Push code fixes
- Merge base branch
- Post status comments

**Repos:** All configured `writable_repos`

**Note:** This service is automatic - it monitors all PRs from jib/user without needing assignment.

---

## Configuration Changes

### `repositories.yaml` Additions

```yaml
# Existing config...
github_username: jwbron
bot_username: james-in-a-box

writable_repos:
  - jwbron/james-in-a-box
  - jwbron/collaborative-development-framework

# NEW: Control which services are enabled per repo
repo_settings:
  jwbron/james-in-a-box:
    restrict_to_configured_users: true
    disable_auto_fix: true  # Existing - disable CI fixer
    # NEW options:
    disable_comment_responder: false  # Default: enabled
    disable_pr_reviewer: false        # Default: enabled
    disable_ci_fixer: false           # Default: enabled (overridden by disable_auto_fix)
```

---

## Questions for Review

### Q1: PR Reviewer Scope

**Current behavior:** Reviews ALL PRs from other authors in writable repos (proactive review).

**Proposed behavior:** Only review PRs where jib is explicitly assigned or tagged.

**Question:** Is this change correct? Should jib still proactively review all PRs, or should it wait to be asked?

**Trade-offs:**
- **Opt-in (proposed):** Less noise, more respectful, but requires explicit assignment
- **Proactive (current):** Ensures all PRs get reviewed, but may be unwanted

### Q2: Comment Responder - "Tagged" Definition

**Question:** What constitutes being "tagged"?

Options:
1. **Mentioned in comment body** - e.g., "@james-in-a-box can you look at this?"
2. **Review requested** - Explicitly added as reviewer via GitHub UI
3. **Both** - Respond to either trigger

Recommendation: Start with **both** - respond when mentioned OR when added as reviewer.

### Q3: Service Scheduling

**Current:** Single timer runs every 5 minutes, executes all checks.

**Options:**
1. **Single timer, three services** - Timer triggers a dispatcher that runs all three
2. **Three separate timers** - Each service has its own timer (allows different intervals)
3. **Shared timer, parallel execution** - Single timer runs all three in parallel

Recommendation: **Option 1** initially for simplicity. Can split timers later if needed.

### Q4: Read-Only Repo Behavior

**Question:** Should the PR Reviewer service work on read-only repos?

**Current behavior:** For read-only repos, review output goes to Slack instead of GitHub.

**Proposed behavior:** Same - if jib is tagged for review in a read-only repo, output review to Slack.

### Q5: State Management

**Current:** Single `~/.local/share/github-watcher/state.json` tracks all processed items.

**Options:**
1. **Keep unified state** - All three services share one state file
2. **Separate state files** - Each service has its own state file
3. **Namespaced state** - Single file with namespaced keys per service

Recommendation: **Option 3** - Single file, but keys prefixed by service (e.g., `comment_responder.processed_comments`).

---

## Implementation Plan

### Phase 1: Extract Shared Code (Foundation)

1. Create `host-services/analysis/github-watcher/lib/` directory
2. Extract shared utilities:
   - `github_api.py` - `gh_json()`, `gh_text()`, rate limiting
   - `state.py` - State management, signatures
   - `tasks.py` - `JibTask` dataclass, `execute_task()`, `execute_tasks_parallel()`
   - `config.py` - Config loading, access level checking
3. Update existing `github-watcher.py` to use shared lib (verify no regression)

### Phase 2: Create Comment Responder

1. Create `comment-responder.py`
2. Move `check_pr_for_comments()` and `check_pr_for_review_response()` logic
3. Add assignment/tagging detection:
   ```python
   def is_jib_engaged(pr_data: dict, bot_username: str) -> bool:
       """Check if jib is assigned, tagged, or the author."""
       # Check if author
       if pr_data.get("author", {}).get("login", "").lower() == bot_username.lower():
           return True
       # Check if assigned
       assignees = [a.get("login", "").lower() for a in pr_data.get("assignees", [])]
       if bot_username.lower() in assignees:
           return True
       # Check if mentioned in recent comments (implementation TBD)
       return False
   ```
4. Create systemd service file `comment-responder.service`

### Phase 3: Create PR Reviewer

1. Create `pr-reviewer.py`
2. Move `check_prs_for_review()` logic
3. Modify trigger to require assignment/tagging
4. Integrate collaborative development framework (placeholder for future enhancement)
5. Create systemd service file `pr-reviewer.service`

### Phase 4: Create CI/Conflict Fixer

1. Create `ci-fixer.py`
2. Move `check_pr_for_failures()` and `check_pr_for_merge_conflict()` logic
3. Limit to PRs authored by bot or configured user
4. Create systemd service file `ci-fixer.service`

### Phase 5: Dispatcher and Migration

1. Create `github-watcher-dispatcher.py` that orchestrates all three
2. Update timer to trigger dispatcher
3. Deprecate monolithic `github-watcher.py`
4. Update documentation

---

## File Structure After Refactor

```
host-services/analysis/github-watcher/
├── lib/
│   ├── __init__.py
│   ├── github_api.py      # gh CLI wrappers, rate limiting
│   ├── state.py           # State management
│   ├── tasks.py           # Task execution
│   └── config.py          # Config loading
├── comment-responder.py   # Service 1
├── pr-reviewer.py         # Service 2
├── ci-fixer.py            # Service 3
├── dispatcher.py          # Main entry point (runs all three)
├── github-watcher.service # Updated to run dispatcher
├── github-watcher.timer   # Unchanged
└── README.md              # Updated documentation
```

---

## Container-Side Changes

The existing `github-processor.py` in `jib-container/jib-tasks/github/` can remain largely unchanged. Each host-side service will continue to invoke it with the appropriate task type and context.

No changes required unless we want to add new task types or modify prompts.

---

## Testing Plan

1. **Unit tests** for shared library functions
2. **Integration tests** - Mock `gh` CLI responses, verify correct tasks generated
3. **Manual testing** - Run each service independently on test PRs
4. **Canary deployment** - Run new services alongside old for one cycle, compare output

---

## Rollback Plan

If issues arise:
1. Disable new services: `systemctl --user stop comment-responder pr-reviewer ci-fixer`
2. Re-enable old service: `systemctl --user start github-watcher`
3. Old `github-watcher.py` preserved until new architecture proven stable

---

## Timeline Estimate

- **Phase 1 (Foundation):** 1-2 hours
- **Phase 2 (Comment Responder):** 2-3 hours
- **Phase 3 (PR Reviewer):** 2-3 hours
- **Phase 4 (CI/Conflict Fixer):** 1-2 hours
- **Phase 5 (Dispatcher):** 1 hour
- **Testing & Documentation:** 2-3 hours

**Total:** ~10-15 hours of implementation work

---

## References

- Current implementation: `host-services/analysis/github-watcher/github-watcher.py`
- Container processor: `jib-container/jib-tasks/github/github-processor.py`
- Config: `config/repositories.yaml` and `config/repo_config.py`
