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
✅ Use `~/tmp/` for temporary work and prototyping
✅ Use `~/sharing/` for persistent data and notifications

### What You CANNOT Do (Deliberately)
❌ **Merge PRs** - NEVER merge your own PRs, even if technically possible. Human must review and merge.
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

- **`@update-confluence-doc <path>`** - Update Confluence documentation
  - Reads original document with synced comments
  - Integrates feedback from inline/footer comments
  - Generates "Changed Sections Only" document
  - Formats content for Confluence compatibility (bare URLs, proper tables)

## File System Layout

### `~/khan/` - Main Workspace (READ-WRITE)
**Purpose**: Working directory for code development
**Access**: Read-write
**Persistence**: Mounted from host (`~/khan-jib/`)
**Usage**: Make changes directly in place, commit to git

**IMPORTANT WORKFLOW**:
You CAN modify files in `~/khan/` directly:

1. **Read** - Explore `~/khan/` to understand code structure and context
2. **Modify** - Make your changes directly in `~/khan/`
3. **Test** - Run tests to verify your changes
4. **Commit** - Commit your changes with clear messages
5. **Create PR** - Use PR helper to create PR for human review

**Example workflow**:
```bash
# 1. Read code for context
cat ~/khan/webapp/server.py

# 2. Modify the file directly
vim ~/khan/webapp/server.py

# 3. Test your changes
pytest tests/test_server.py

# 4. Commit changes
git add ~/khan/webapp/server.py
git commit -m "Add OAuth2 authentication

- Added OAuth2 middleware
- Fixed timeout handling
- See: JIRA-1234"

# 5. Create PR for human review (james-in-a-box repo only)
create-pr-helper.py --auto --reviewer jwiesebron

# For other repos: Notify user with branch name to create PR from host
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

### `~/sharing/` - Persistent Data (Consolidated)
**Purpose**: ALL persistent data that must survive container rebuilds
**Access**: Read-write
**Persistence**: Mounted from host (`~/.jib-sharing/`)
**Structure**: All shared data is organized under this single directory for cleaner host organization

**Subdirectories**:
- **`~/sharing/tmp/`** - Persistent scratch space (also accessible as `~/tmp/` symlink)
  - Download and inspect files
  - Build temporary test environments
  - Prototype before moving to main workspace
  - Store intermediate build artifacts
  - NOTE: Unlike container's `/tmp`, this PERSISTS across rebuilds

- **`~/sharing/notifications/`** - Notifications to human (triggers Slack DM)
  - Write notification files here to send async messages to human
  - Host Slack notifier watches this directory
  - See "Notifications - Async Communication" section below

- **`~/sharing/context/`** - Context documents (`@save-context` / `@load-context`)
  - Accumulated knowledge from previous sessions
  - Used by `@load-context` and `@save-context` commands
  - Helps avoid repeating mistakes across sessions

- **`~/sharing/tracking/`** - Logs from background services
  - Watcher logs
  - Analyzer logs
  - System monitoring output

**Convenience Symlink** (for easier access):
- `~/tmp/` → `~/sharing/tmp/`

**Note**: Code changes are made directly in `~/khan/` and committed to git, not staged in `~/sharing/`

**Host Location**: All of this maps to `~/.jib-sharing/` on the host machine

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

**Human access**: `~/.jib-sharing/notifications/` on host


### Container Filesystem - System Level
**Purpose**: System-wide changes
**Access**: Can modify with sudo
**Persistence**: NOT persisted on rebuild
**Usage**:
```bash
# Install packages (lost on container rebuild - Docker determines layers to rebuild)
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

**Solution**: Use the PR helper to push and create PRs (james-in-a-box repo only)

### Workflow
1. You: Make changes, commit locally
2. You: Create PR with `create-pr-helper.py --auto --reviewer jwiesebron` (james-in-a-box only) OR notify user with branch name (other repos)
3. Human: Reviews PR on GitHub (or creates PR from host for other repos)
4. Human: Approves and merges PR

**IMPORTANT**: You must NEVER merge PRs yourself. Even if the PR helper or other tools give you merge capability, merging is exclusively the human's responsibility. This ensures proper code review and accountability.

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
- Create PR with `create-pr-helper.py --auto --reviewer jwiesebron` (james-in-a-box only) OR notify user with branch name (other repos)
- Save context with `@save-context <project>`
- Summarize what was done for human

## Working with Confluence Documentation

When updating Confluence documentation (ADRs, runbooks, etc.), follow these guidelines to avoid formatting issues.

### Confluence Markdown Quirks

Confluence has limited markdown support. The following do NOT render correctly:

| Feature | Standard Markdown | Confluence Behavior |
|---------|-------------------|---------------------|
| Links | `[text](url)` | Shows as plain text |
| Tables | Various formats | Only `\| --- \|` separator works |
| HTML | `<table>`, `<a>` | Shows as raw HTML |
| Nested lists | Indented `-` | May add extra spacing |

### Best Practice: Changed Sections Only

Instead of creating a full updated document, create a **"Changed Sections Only"** document:

1. **Read the original** - Understand the current structure
2. **Identify changes** - Note what's new vs. modified
3. **Create patch document** - List only the changed sections with instructions

**Output format**:
```markdown
# [Document Name]: Changed Sections Only

Instructions: Copy each section below into the corresponding location in Confluence.

---

## NEW SECTION: Add after "[Section Name]"

[New content here]

---

## MODIFIED: Replace "[Section Name]"

[Updated content here]
```

### Formatting Rules for Confluence

When writing content that will be copied to Confluence:

1. **Links**: Use bare URLs instead of markdown links
   - Do: `See: https://example.com/page`
   - Don't: `See: [Page Name](https://example.com/page)`

2. **Tables**: Use the `| --- |` separator format
   ```markdown
   | Column 1 | Column 2 |
   | --- | --- |
   | Value 1 | Value 2 |
   ```

3. **Lists**: No blank lines between items
   ```markdown
   - Item 1
   - Item 2
   - Item 3
   ```

4. **Code blocks**: Use triple backticks with language identifier

### Using the Command

Use `@update-confluence-doc <path>` to help prepare updates for Confluence pages:
- Reads the original document with comments
- Identifies feedback to integrate
- Generates a "changed sections only" document
- Formats for Confluence compatibility

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


---

**See also**: `mission.md` for your role and workflow.

