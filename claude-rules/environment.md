# Sandboxed Environment - Technical Constraints

## Your Environment

You are running in a **sandboxed Docker container** with isolated access to code and documentation. This ensures you cannot accidentally access credentials or deploy to production.

**Security Model:**
- **Network Mode**: Bridge networking (isolated from host network)
- **Internet Access**: Outbound HTTP/HTTPS only (for Claude API and package downloads)
- **Credential Isolation**: No SSH keys, cloud credentials, or production access
- **No Inbound Ports**: Container cannot accept connections from outside
- **Result**: You can develop and test freely, but cannot push/deploy to production or access host services

**Important**: You run with "Bypass Permissions" mode because multiple security boundaries protect the host and production:
- **Credential isolation** - No SSH keys, no cloud credentials, no production database access
- **Network isolation** - Cannot access services running on host machine
- **Inbound isolation** - Cannot accept connections, no ports exposed

Even with internet access, you cannot:
- Push code to GitHub (no SSH keys)
- Deploy to GCP/AWS (no cloud credentials)
- Access production databases (no credentials)
- Access host services (network isolated)
- Accept inbound connections (no ports exposed)
- Damage the host system (containerized)

## Capabilities

### What You CAN Do
✅ Read and edit code in `~/khan/`
✅ Create, modify, and delete files
✅ Run tests and development servers
✅ Make local git commits (`git commit`)
✅ Use all development tools (Python, Node.js, Go, Java, PostgreSQL, Redis)
✅ Access the internet for package downloads and AI features
✅ Read documentation and search codebases
✅ Install packages (`apt-get`, `pip`, `npm install -g`)
✅ Build reusable tools in `~/tools/`
✅ Use `~/tmp/` for temporary work and prototyping
✅ Share code for review in `~/sharing/`

### What You CANNOT Do (Deliberately)
❌ **Push to git** (no SSH keys available) - user will push from host
❌ **Deploy to GCP** (no gcloud credentials) - user will deploy from host
❌ **Access Google Secret Manager** (no auth)
❌ **Access any cloud credentials** (AWS, GCP, Kubernetes, etc.)
❌ **Modify host directories** (only sandboxed mounts are available)

## Custom Commands (Installed Slash Commands)

These commands are installed in `~/.claude/commands/` and available as slash commands:

- **`@load-context <project-name>`** - Load accumulated knowledge from previous sessions
  - Reads from `~/sharing/context/<project-name>.md`
  - Helps avoid repeating mistakes and builds on previous work
  
- **`@save-context <project-name>`** - Save current session's learnings
  - Writes to `~/sharing/context/<project-name>.md`
  - Uses ACE methodology: Generation → Reflection → Curation
  - Appends new session (never replaces existing content)
  
- **`@create-pr [audit] [draft]`** - Generate PR description and commit messages
  - Analyzes branch changes vs base branch
  - Generates formatted PR description
  - Saves to `.git/PR_EDITMSG+<branch-name>.save`
  - Optional: `audit` flag for review request, `draft` flag for WIP

## File System Layout

### `~/khan/` - Main Workspace (READ-ONLY)
**Purpose**: Code reference for understanding the codebase
**Access**: Read-only
**Persistence**: Mounted from host
**Why read-only**: Prevents interference with systemd jobs running on host

**IMPORTANT WORKFLOW**:
You CANNOT modify files in `~/khan/` directly. Instead:

1. **Read** - Explore `~/khan/` to understand code structure and context
2. **Copy** - Copy files you want to modify to `~/sharing/staged-changes/<repo-name>/`
3. **Modify** - Make your changes in `~/sharing/staged-changes/`
4. **Document** - Create a clear summary of changes for human review
5. **Human applies** - Human reviews and manually applies approved changes to host

**Example workflow**:
```bash
# 1. Read code for context
cat ~/khan/webapp/server.py

# 2. Copy to staging area
mkdir -p ~/sharing/staged-changes/webapp
cp ~/khan/webapp/server.py ~/sharing/staged-changes/webapp/

# 3. Modify the staged copy
vim ~/sharing/staged-changes/webapp/server.py

# 4. Document changes
cat > ~/sharing/staged-changes/webapp/CHANGES.md <<EOF
## Changes to server.py
- Added OAuth2 authentication
- Fixed timeout handling
- See: JIRA-1234
EOF

# 5. Tell human changes are ready for review
```

### `~/context-sync/` - Context Sources
**Purpose**: Multi-source context and knowledge base
**Access**: Read-only
**Persistence**: Mounted from host
**Contents**:
- `confluence/` - Confluence documentation
  - ADRs (Architecture Decision Records)
  - Runbooks and operational docs
  - Best practices and standards
  - Team processes and guidelines
- `jira/` - JIRA tickets and issues
  - Issue descriptions and comments
  - Sprint and epic context
  - Bug reports and feature requests
- `logs/` - Sync logs
- (Future: `github/`, `slack/`, `email/`)

**Usage**:
```bash
# Check ADRs before architectural decisions
ls ~/context-sync/confluence/ENG/ADRs/

# Review JIRA ticket for requirements
grep -r "JIRA-1234" ~/context-sync/jira/

# Review runbooks for operational context
cat ~/context-sync/confluence/INFRA/runbooks/
```

### `~/tools/` - Reusable Utilities
**Purpose**: Build scripts that persist across sessions
**Access**: Read-write
**Persistence**: Mounted from host (`~/.jib-tools/`)
**Usage**:
- Create helper scripts and automation
- Build test runners, code generators
- Store development utilities
**See**: `tools-guide.md` for comprehensive guide

### `~/sharing/` - Persistent Data & Staging Area
**Purpose**: ALL data that must persist across container rebuilds, including staged code changes
**Access**: Read-write
**Persistence**: Mounted from host (`~/.jib-sharing/`)
**What goes here**:
- **`~/sharing/staged-changes/`** - Modified code for human review (PRIMARY USE)
- **`~/sharing/notifications/`** - Notifications to human (triggers Slack DM)
- **`~/sharing/context/`** - Context documents (`@save-context` / `@load-context`)
- Pull request artifacts
- Analysis reports
- Any work product that should survive rebuilds

**Critical Usage for Code Changes**:
```bash
# THIS IS HOW YOU MODIFY CODE (~/khan/ is read-only!)

# 1. Create staging area for a repo
mkdir -p ~/sharing/staged-changes/webapp

# 2. Copy files you want to modify
cp ~/khan/webapp/server.py ~/sharing/staged-changes/webapp/
cp ~/khan/webapp/models.py ~/sharing/staged-changes/webapp/

# 3. Make your changes
vim ~/sharing/staged-changes/webapp/server.py

# 4. REQUIRED: Document what changed and why in CHANGES.md
cat > ~/sharing/staged-changes/webapp/CHANGES.md <<'EOF'
# Changes for JIRA-1234: Add OAuth2 Support

## Overview
Brief description of what this change accomplishes.

## Files Modified
- server.py: Added OAuth2 middleware
- models.py: Added User.oauth_token field

## Testing
- Unit tests passing (see test_oauth.py)
- Tested with Google OAuth provider

## Deployment
How human should apply these changes:
```bash
cp ~/sharing/staged-changes/webapp/* ~/khan/webapp/
```

## Dependencies
Any new packages or system requirements.

## Breaking Changes
Any backwards incompatible changes.
EOF

# 5. Tell human
echo "Changes staged in ~/sharing/staged-changes/webapp/ - ready for review"
echo "See CHANGES.md for complete documentation"
```

**IMPORTANT**: Always include a `CHANGES.md` file in the staging directory. This allows the human to:
- Understand what changed and why
- Review changes before applying
- Have documentation for git commits
- Track dependencies and breaking changes

**Notifications - Async Communication**:
```bash
# When you need guidance but human isn't in active conversation
# Create a notification file - it will trigger a Slack DM within ~30 seconds

cat > ~/sharing/notifications/$(date +%Y%m%d-%H%M%S)-topic.md <<'EOF'
# 🔔 Need Guidance: [Topic]

**Priority**: [Low/Medium/High/Urgent]

## Context
Working on: [what you're doing]

## Issue
[What you need guidance on]

## Recommendation
[What you think should be done]
EOF

# The host Slack notifier watches ~/sharing/notifications/
# Human gets notified via Slack DM and can respond
```

**Use cases for notifications**:
- Found a better approach than requested
- Skeptical about proposed solution
- Need architectural decision
- Discovered unexpected complexity
- Critical issue found
- Important assumption needs validation

**Human access**: `~/.jib-sharing/staged-changes/` and `~/.jib-sharing/notifications/` on host

**Important**: `~/khan/` is READ-ONLY. ALL code modifications must go through `~/sharing/staged-changes/`!

### `~/tmp/` - Scratch Space
**Purpose**: Temporary work, not persisted
**Access**: Read-write
**Persistence**: Container-only (ephemeral)
**Usage**:
- Download and inspect files
- Build temporary test environments
- Prototype before moving to main workspace
- Store intermediate build artifacts

### Container Filesystem - System Level
**Purpose**: System-wide changes
**Access**: Can modify with sudo
**Persistence**: NOT persisted on rebuild
**Usage**:
```bash
# Install packages (lost on --rebuild)
apt-get update && apt-get install -y ripgrep
pip install pytest-watch
npm install -g typescript-language-server
```

**For persistent tools**: Create wrapper scripts in `~/tools/setup-dev-env.sh`

## Git Workflow

### What You Can Do
```bash
# Local operations work fine
git status
git add .
git commit -m "descriptive message"
git log
git branch
git checkout -b feature/new-work
```

### What Happens at Push
```bash
git push
# ❌ Permission denied (publickey)
# This is intentional - no SSH keys in sandbox
```

**Solution**: Commit locally, human pushes and opens PR from host

### Workflow
1. You: Create branch, make changes, commit locally
2. You: Prepare PR description with `@create-pr` (generates description file)
3. Human: Reviews commits in sandbox
4. Human: Pushes from host machine (has SSH keys)
5. Human: Opens PR on GitHub with generated description
6. Human: Reviews and merges PR

## Testing and Validation

### Running Tests
```bash
# Python tests
pytest tests/
python -m pytest path/to/test.py

# JavaScript/Node tests  
npm test
npm run test:watch

# Project-specific (Khan Academy)
make test
```

### Running Services
```bash
# PostgreSQL and Redis start automatically

# Check if running
service postgresql status
service redis-server status

# Restart if needed
sudo service postgresql restart
sudo service redis-server restart
```

### Linting and Formatting
```bash
# Python
pylint file.py
black file.py
mypy file.py

# JavaScript/TypeScript
eslint file.js
prettier --write file.js

# Project-specific
make lint
make fix
```

## Error Handling

### Permission Denied Errors
If you encounter credential-related errors:
1. **Don't try to authenticate** - You don't have access
2. **Document the limitation** - Note what needs user action
3. **Work around it** - Focus on what you can accomplish
4. **Be clear** - Tell user what they need to do on host

Examples:
```bash
# ❌ This will fail (expected)
git push
gcloud app deploy
gsm read secret-name

# ✅ Do this instead
git commit -m "changes ready"
# Tell human: "Changes committed locally, ready for you to push"
```

### Service Conflicts
If PostgreSQL or Redis fail to start:
```bash
# Usually means host is already running on same port
# This is fine - use host services or change container port
```

### File Not Found
If expected files are missing:
- Check you're in right directory (`pwd`)
- Check file system layout above
- Mounted directories may not exist if not configured
- Context sources (confluence, jira) require separate sync setup

## Best Practices

### Before Starting Work
```bash
# Check you're in right location
pwd
# Should be ~/khan/ or subdirectory

# Ensure services are running
service postgresql status
service redis-server status

# Load relevant context
@load-context <project>
```

### During Development
- Commit frequently with clear messages
- Test changes before committing
- Check linters pass
- Document non-obvious decisions

### After Completing Work
- Run full test suite
- Prepare PR artifacts with `@create-pr audit` (generates description)
- Save context with `@save-context <project>`
- Summarize what was done for human
- Human will open PR on GitHub

## Installation and Packages

### System Packages (Not Persisted)
```bash
# These are lost on container rebuild
apt-get update && apt-get install -y package-name
pip install package-name
npm install -g package-name
```

### Project Dependencies (Persisted in Code)
```bash
# These ARE persisted (in package.json, requirements.txt)
cd ~/khan/
npm install --save package-name
pip install package-name >> requirements.txt
```

### For Persistent System Tools
Create setup script in `~/tools/`:
```bash
#!/bin/bash
# ~/tools/setup-dev-env.sh
apt-get update && apt-get install -y ripgrep fd-find
pip install pytest-watch black mypy
npm install -g prettier eslint
```

Then run on each container start if needed.

---

**See also**: `mission.md` for your role and workflow, `tools-guide.md` for building reusable utilities.

