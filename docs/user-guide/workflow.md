# Staging Workflow - Read-Only Code with Review

## The Problem

Some directories in `~/khan/` are used by systemd jobs running on the host (e.g., `context-watcher`, `jenkins-jobs`, `buildmaster2`). If Claude modifies these files directly, it could break running services.

## The Solution: Staging Pattern

Claude works in a **staging area** (`~/sharing/staged-changes/`) while having read-only access to the actual codebase.

```
┌─────────────────────────────────────────────────────────┐
│  HOST                                                   │
│                                                         │
│  ~/khan/webapp/          ← systemd jobs may use this   │
│  ~/khan/jenkins-jobs/    ← systemd jobs may use this   │
│                                                         │
│  ~/.jib-sharing/staged-changes/             │
│    └── webapp/           ← Claude's proposed changes   │
│        ├── server.py                                    │
│        ├── models.py                                    │
│        └── README.md     ← What changed and why        │
└─────────────────────────────────────────────────────────┘
                           │
                           │ Docker mounts
                           ▼
┌─────────────────────────────────────────────────────────┐
│  CONTAINER                                              │
│                                                         │
│  ~/khan/                 ← READ-ONLY (can't modify)    │
│  ~/sharing/staged-changes/ ← READ-WRITE (work here)   │
└─────────────────────────────────────────────────────────┘
```

## How It Works

### 1. Claude's Workflow

```bash
# Inside container

# Step 1: Read existing code
cat ~/khan/webapp/server.py

# Step 2: Create staging area
mkdir -p ~/sharing/staged-changes/webapp

# Step 3: Copy files to modify
cp ~/khan/webapp/server.py ~/sharing/staged-changes/webapp/
cp ~/khan/webapp/models.py ~/sharing/staged-changes/webapp/

# Step 4: Modify the staged copies
vim ~/sharing/staged-changes/webapp/server.py

# Step 5: Document changes
cat > ~/sharing/staged-changes/webapp/README.md <<EOF
## Changes for JIRA-1234

### Files Modified
- server.py: Added OAuth2 middleware
- models.py: Added User.oauth_token field

### Testing
- All tests passing
- Tested with Google OAuth

### How to Apply
cd ~/.jib-sharing/staged-changes/webapp/
cp *.py ~/khan/webapp/
EOF
```

### 2. Your Workflow (on Host)

```bash
# Step 1: Exit container
exit

# Step 2: Review staged changes
cd ~/.jib-sharing/staged-changes/webapp/
cat README.md           # Read what changed
diff server.py ~/khan/webapp/server.py  # Review diffs

# Step 3: Apply approved changes
cp server.py ~/khan/webapp/
cp models.py ~/khan/webapp/

# Step 4: Commit and push
cd ~/khan/webapp/
git add .
git commit -m "Add OAuth2 support (JIRA-1234)"
git push origin feature-branch

# Step 5: Clean up staging area (optional)
rm -rf ~/.jib-sharing/staged-changes/webapp/
```

## Benefits

✅ **Safe** - Claude can't break running systemd jobs
✅ **Reviewable** - All changes in one place for easy review
✅ **Documented** - Claude includes README explaining changes
✅ **Flexible** - Accept, modify, or reject proposed changes
✅ **Isolated** - Work doesn't affect host until you apply it

## Common Patterns

### Pattern 1: Full Repository Changes

```bash
# Claude creates complete modified copy
~/sharing/staged-changes/webapp/
  ├── server.py
  ├── models.py
  ├── tests/
  │   └── test_oauth.py
  └── README.md
```

### Pattern 2: Partial File Changes (Patches)

```bash
# Claude creates patch files
~/sharing/staged-changes/webapp/
  ├── server.py.patch
  ├── models.py.patch
  └── README.md

# You apply with:
cd ~/khan/webapp/
patch -p1 < ~/.jib-sharing/staged-changes/webapp/server.py.patch
```

### Pattern 3: New Feature Branch

```bash
# Claude creates complete feature implementation
~/sharing/staged-changes/feature-oauth/
  ├── implementation/
  │   ├── server.py
  │   └── models.py
  ├── tests/
  │   └── test_oauth.py
  ├── docs/
  │   └── oauth-setup.md
  └── README.md
```

## Directory Structure

```
~/.jib-sharing/
├── staged-changes/           # All code modifications
│   ├── webapp/              # Changes to webapp repo
│   ├── jenkins-jobs/        # Changes to jenkins-jobs
│   └── frontend/            # Changes to frontend
└── context/                 # Context documents
    └── project.md
```

## Tips for Claude

When proposing code changes:

1. **Always document** - Create README.md explaining changes
2. **Be specific** - List exactly which files changed
3. **Include tests** - Show tests pass in staging area
4. **Reference tickets** - Link to JIRA, ADRs, etc.
5. **Show diffs** - Summarize what changed in each file
6. **Explain rationale** - Why this approach?

## Tips for You

When reviewing staged changes:

1. **Read README first** - Understand what Claude did
2. **Use diff tools** - Compare staged vs actual files
3. **Test before applying** - Copy to a test branch first
4. **Apply selectively** - Accept some files, reject others
5. **Clean up** - Remove staging area after applying

## Example README Template (for Claude)

```markdown
# Changes for JIRA-1234: Add OAuth2 Authentication

## Summary
Implemented OAuth2 authentication flow following ADR-012.

## Files Modified
- `server.py`: Added OAuth2 middleware and token validation
- `models.py`: Added User.oauth_token and User.oauth_provider fields
- `tests/test_oauth.py`: Full test coverage for OAuth flow

## Testing
```bash
cd ~/sharing/staged-changes/webapp/
python -m pytest tests/test_oauth.py
# All 15 tests passing
```

## Dependencies
- Required: `pip install oauthlib requests-oauthlib`
- Added to requirements.txt

## How to Apply
```bash
# On host
cd ~/.jib-sharing/staged-changes/webapp/
cp server.py models.py ~/khan/webapp/
cp tests/test_oauth.py ~/khan/webapp/tests/
cd ~/khan/webapp/
pip install -r requirements.txt
python -m pytest tests/test_oauth.py
git add .
git commit -m "Add OAuth2 support (JIRA-1234)"
```

## References
- ADR-012: Authentication Strategy
- JIRA-1234: Add OAuth2 provider support
- context-sync/confluence/ENG/ADRs/ADR-012.md
```

---

This workflow keeps your running services safe while giving Claude full context to propose high-quality changes.
