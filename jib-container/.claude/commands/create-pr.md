# Claude Command: Create Pull Request

**Command**: `/create-pr [audit] [draft]`

**Examples**:
- `/create-pr`
- `/create-pr audit`
- `/create-pr draft`
- `/create-pr audit draft`

## Purpose
Automated workflow to create a pull request by analyzing git history and generating a comprehensive PR description.

## Workflow Steps

### 1. Check Current Branch

**ERROR HANDLING**: Verify we're in a git repository first:
```bash
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Error: Not in a git repository"
    exit 1
fi
```

Run: `git branch -vv`

**ERROR HANDLING**: Check command succeeds:
```bash
if ! BRANCH_INFO=$(git branch -vv 2>&1); then
    echo "❌ Error: Failed to get branch information"
    exit 1
fi
```

Parse output to identify:
- Current branch name
- Upstream configuration (local vs remote)
- Current commit

**Format**: `* branch-name <hash> [upstream] commit message`

### 2. Handle Deploy Branches
**If branch starts with `deploy/`**:
- Run: `git queue`
- **STOP** - do not proceed further

### 3. Verify Upstream Configuration
**Check upstream from step 1**:
- If upstream is **local** (e.g., `[main]`, `[origin/main]`): **proceed**
- If upstream is **remote** or misconfigured:
  - Message: "Please switch to Local Parent Tracking before creating PR"
  - **STOP** execution

### 4. Generate Asymmetrical Diff
Find commits on current branch NOT on base branch.

**Command**: `git log <base-branch>..<current-branch> --oneline`

Where `<base-branch>` is extracted from upstream config.

**ERROR HANDLING**: Validate git log succeeds:
```bash
if ! COMMITS=$(git log "$base_branch..$current_branch" --oneline 2>&1); then
    echo "❌ Error: Failed to get commit history"
    echo "   This may indicate the base branch doesn't exist or git is misconfigured"
    exit 1
fi

if [ -z "$COMMITS" ]; then
    echo "ℹ️  No commits on this branch compared to $base_branch"
    exit 0
fi
```

### 5. Analyze Changes
For each commit from step 4:
- Run: `git show <commit-hash>`
- Understand file changes and purpose
- Build context for PR description

**ERROR HANDLING**: Check git show succeeds for each commit:
```bash
for commit in $COMMITS; do
    if ! git show "$commit" > /dev/null 2>&1; then
        echo "⚠️  Warning: Could not analyze commit $commit"
        continue
    fi
    # Analyze the commit...
done
```

**Goal**: Comprehensive understanding of what changed and why.

### 6. Create PR Description File

**File path**: `./.git/PR_EDITMSG+<branch-name>.save`

**Filename rules**:
- **SECURITY FIX**: Sanitize branch name to prevent path traversal
- Replace `/` with `-slash-`
- Remove any `..`, `~`, or other dangerous patterns
- Validation pattern: `[a-zA-Z0-9._-]+`
- Maximum length: 200 characters
- Examples:
  - `foo/bar` → `PR_EDITMSG+foo-slash-bar.save`
  - `feature/xyz/test` → `PR_EDITMSG+feature-slash-xyz-slash-test.save`
  - `bugfix` → `PR_EDITMSG+bugfix.save`
  - `../etc/passwd` → **REJECTED** (invalid pattern)

**Extract Jira issue from branch name**:
- Pattern: `[A-Z]+-[0-9]+` (e.g., JIRA-123, ABC-456)
- Include in Issue field if found

**File template**:
```
<Concise title summarizing changes (50-72 chars, imperative mood)>

## Summary:
<Detailed explanation of:
- What problem this solves
- Approach taken
- Why this approach was chosen
- Key changes made
>

Issue: <Jira issue if found, otherwise omit this line>

## Test plan:
<How to verify the changes:
- Testing scenarios
- Edge cases
- Manual testing steps
- Automated test coverage
>
```

**Content guidelines**:
- **Title**: Imperative mood, concise, describes the change
- **Summary**: Problem, approach, rationale, key changes
- **Test plan**: Verification steps, scenarios, edge cases

### 7. Execute Git PR Command

**Base**: `git pr --verbatim`

**Add flags**:
- If "audit" mentioned: add `--audit`
- If "draft" mentioned: add `--draft`

**Examples**:
- `/create-pr` → `git pr --verbatim`
- `/create-pr audit` → `git pr --verbatim --audit`
- `/create-pr draft` → `git pr --verbatim --draft`
- `/create-pr audit draft` → `git pr --verbatim --audit --draft`

## Error Handling

### Common Issues

1. **No commits on branch**
   - If step 4 shows no commits
   - Message: "No changes to create PR for"

2. **Detached HEAD**
   - If `git branch -vv` shows no branch
   - Message: "You're in detached HEAD state"

3. **Uncommitted changes**
   - These won't be in PR (expected behavior)
   - Consider mentioning if user seems confused

## Notes

- Execute steps sequentially, don't skip
- Use terminal commands for git operations
- `--verbatim` uses exact message file without modification
- Read git outputs carefully for decision-making
- Be thorough in PR description based on actual code changes
- When unsure, ask user rather than proceeding incorrectly

## Example Flow

```
User: /create-pr audit

Claude: 
1. Checking current branch... [runs git branch -vv]
   Current: feature/add-redis-cache [main]
   
2. Not a deploy branch, proceeding...

3. Upstream is local (main), proceeding...

4. Analyzing commits... [runs git log main..feature/add-redis-cache]
   Found 3 commits:
   - abc123 Add Redis cache configuration
   - def456 Implement cache invalidation
   - ghi789 Add unit tests for caching

5. Analyzing changes... [examines each commit]
   [Shows summary of file changes]

6. Creating PR description at .git/PR_EDITMSG+feature-slash-add-redis-cache.save
   Title: "Add Redis caching layer for API responses"
   [Shows generated description]

7. Executing: git pr --verbatim --audit
   [Shows git command output]

✅ Pull request created!
```

