# Quick Reference - Claude Code Sandboxed

Daily usage guide with accurate paths and commands.

## TL;DR

```bash
# Start container
./claude-sandboxed

# Inside container
claude                          # Start Claude Code CLI
@load-context myproject        # Load knowledge
# [work naturally with Claude]
@create-pr audit               # Create PR
@save-context myproject        # Save learnings
exit                           # Done
```

## First Time Setup

```bash
# 1. Clone or navigate to project
cd ~/khan/james-in-a-box

# 2. Run (builds Docker image on first use)
./claude-sandboxed

# 3. First run: Browser opens for OAuth login
# After login: Claude Code is ready!

# 4. Inside container, start Claude
claude
```

**That's it!** OAuth credentials are automatically copied to the container.

## Daily Usage

### Starting a Session

```bash
# From host
./claude-sandboxed

# Inside container
claude
```

You'll see:
```
🤖 Autonomous Software Engineering Agent
====================================================================
Role: Autonomous engineer working with minimal supervision
Mission: Plan, implement, test, document, and create PRs
Human: Reviews and ships your work

📋 Your Instructions:
  • ~/CLAUDE.md                      (mission + environment)
  • ~/khan/CLAUDE.md                 (Khan Academy standards)
  • ~/tools-guide.md                 (building reusable tools)
```

### Working with Claude

Claude is **conversational**. Just chat naturally:

```
You: Let's add OAuth2 authentication to the user service for JIRA-1234

Claude: I'll help you with that. Let me first check our ADRs and the JIRA ticket...
[Claude explores context-sync/confluence/ and context-sync/jira/, reviews ADR-012 and JIRA-1234]
[Claude reads current code from ~/khan/webapp/ (read-only)]

Claude: According to ADR-012 and JIRA-1234 requirements, I'll create the implementation.
[Claude copies files to ~/sharing/staged-changes/webapp/]
[Claude modifies the staged copies, writes tests, creates documentation]

You: Show me what you created

Claude: Changes are in ~/sharing/staged-changes/webapp/:
- server.py - Added OAuth2 middleware
- models.py - Added User.oauth_token field
- tests/test_oauth.py - Full test coverage
- README.md - Implementation summary and how to apply

You: Save what we learned

Claude: ✅ Saved Session 2 to ~/sharing/context/auth-work.md

# On host, you review and apply:
cd ~/.jib-sharing/staged-changes/webapp/
# Review changes, then apply to actual repo
```

## Custom Commands

### @load-context <filename>

Load accumulated knowledge from previous sessions.

```bash
You: @load-context redis-migration

Claude: ✅ Loaded context: redis-migration.md
- Created: 2024-10-15
- Last Updated: 2024-11-01
- Sessions: 3
- Playbooks: 5 patterns
- Anti-Patterns: 2 documented failures

Ready to assist using previous experience.
```

**Where it loads from**: `~/sharing/context/<filename>.md`

### @save-context <filename>

Save current session with implementation, lessons, playbooks.

```bash
You: @save-context redis-migration

Claude: [Analyzes session using ACE methodology]
✅ Saved Session 4 to redis-migration.md

Captured:
- What was implemented: Redis connection pooling
- What we learned: Connection timeout tuning
- New playbook: Redis failover testing
- Anti-pattern: Don't skip staging validation
```

**Where it saves to**: `~/sharing/context/<filename>.md`

**Important**: This directory **persists across container rebuilds**!

### @create-pr [audit] [draft]

Create pull request from current branch.

```bash
You: @create-pr audit

Claude: Analyzing git history...
Creating PR for branch: feature/add-caching
✅ PR description generated
✅ Test plan included
✅ Executing: git pr --verbatim --audit
```

Flags:
- `audit` - Include extra validation
- `draft` - Create as draft PR

## Directory Structure

### Inside Container

```
~/khan/                      Code reference (MOUNTED ro - READ ONLY!)
  ├── actions/
  ├── buildmaster2/
  ├── james-in-a-box/
  ├── frontend/
  ├── internal-services/
  ├── jenkins-jobs/
  ├── terraform-modules/
  ├── webapp/
  └── ... (entire codebase for reference)
~/context-sync/              Context sources (MOUNTED ro)
  ├── confluence/            Confluence docs (ADRs, runbooks)
  ├── jira/                  JIRA tickets and issues
  └── logs/                  Sync logs
~/tools/                     Reusable scripts (MOUNTED rw)
~/sharing/                   Persistent data (MOUNTED rw)
  ├── staged-changes/        CODE CHANGES GO HERE (for review)
  └── context/               Context documents
~/tmp/                       Scratch space (ephemeral)
```

### On Host

```
~/.claude-sandbox/           Build context and config
~/.jib-tools/     Mapped to ~/tools/ in container
~/.jib-sharing/   Mapped to ~/sharing/ in container
~/khan/                      Your real codebase (MOUNTED to container)
```

### What Persists

✅ **Always persists** (mounted from host):
- `~/khan/` - Entire codebase (READ-ONLY, for reference)
- `~/tools/` - Your reusable scripts
- `~/sharing/` - Staged changes, context docs, work products
  - `~/sharing/staged-changes/` - Where Claude puts modified code for your review

❌ **Lost on container exit** (ephemeral):
- `~/tmp/` - Scratch files (container-only)
- System packages installed with apt/pip/npm

**Important**: Code changes in `~/khan/` are immediately visible on host!

## What Claude Can/Cannot Do

### ✅ Claude CAN:
- Read code from `~/khan/` (read-only reference)
- Propose changes in `~/sharing/staged-changes/` for your review
- Run tests and analysis (read-only code access)
- Read context sources (Confluence docs, JIRA tickets, etc.)
- Install packages (`apt`, `pip`, `npm`)
- Build tools in `~/tools/`
- Document and explain proposed changes

### ❌ Claude CANNOT:
- `git push` (no SSH keys)
- Deploy to GCP (no gcloud)
- Access Google Secret Manager
- Access any cloud credentials
- Modify host system

### 👤 YOU Handle (on host):

```bash
# Review Claude's staged changes
cd ~/.jib-sharing/staged-changes/

# Apply approved changes
cp webapp/*.py ~/khan/webapp/

# Commit and push
cd ~/khan/webapp/
git add .
git commit -m "Add OAuth2 support"
git push origin my-branch

# Deploy
gcloud app deploy
```

## Typical Workflows

### 1. Feature Implementation

```bash
./claude-sandboxed
claude

You: Implement user profile editing feature
Claude: [Asks questions, checks ADRs, implements]

You: Run tests
Claude: [Executes tests, fixes issues]

You: Create a PR
@create-pr audit

You: Save this session
@save-context user-profiles

exit
# Review PR on GitHub, approve, merge
```

### 2. Bug Fix with Context

```bash
claude

You: @load-context timeout-issues
# Claude loads previous investigation

You: Users reporting timeouts on /api/data again
Claude: Based on Session 2, this was solved by increasing
connection pool size. I'll check current settings...
[Applies previous solution]

You: @create-pr
You: @save-context timeout-issues
```

### 3. Building Reusable Tools

```bash
claude

You: I keep running the same test commands. Make me a helper
Claude: I'll create ~/tools/smart-test.sh
[Creates script with smart test selection]

You: Thanks! Now one for PR validation
Claude: [Creates ~/tools/check-pr.sh]

# Next time you start container:
~/tools/smart-test.sh          # Tool is still there!
```

## Commands Reference

```bash
# Start container (builds on first run)
./claude-sandboxed

# Management commands (rarely needed)
./claude-sandboxed --setup      # Reconfigure mounts
./claude-sandboxed --reset      # Complete reset

# Inside container
claude                          # Start Claude Code
exit                            # Exit container (or Ctrl+D)

# View agent rules
cat ~/CLAUDE.md                 # Mission + environment
cat ~/khan/CLAUDE.md            # Khan Academy standards
cat ~/tools-guide.md            # Tools reference
```

## Common Issues

### "Not authenticated"

OAuth credentials should be copied automatically. If not:

```bash
# On host (outside container)
claude
# Browser opens for OAuth login

# Then restart container
./claude-sandboxed
```

### "Container won't start"

```bash
# Check Docker is running
docker ps

# If needed, rebuild
./claude-sandboxed --setup
```

### "My changes disappeared"

- **Code in `~/khan/`**: Always persists (mounted from host) ✅
- **Context docs in `~/sharing/`**: Always persist (mounted from host) ✅
- **System packages**: Lost on container exit (reinstall or add to ~/tools/ script)
- **Files in `~/tmp/`**: Lost on container exit (ephemeral scratch space)

**Solution**: Use `@save-context` for accumulated knowledge. Code changes persist automatically.

### "Forgot what Claude can do"

```bash
# Inside container
cat ~/CLAUDE.md                 # Read agent mission
ls claude-commands/             # List custom commands
```

## Tips for Effective Collaboration

### 1. Be Clear About Goals

```
✅ Good: "Add OAuth2 auth following ADR-012, backwards compatible"
⚠️ Okay: "Add authentication"
❌ Vague: "Make it secure"
```

### 2. Use Context Documents

```bash
# First session on a topic
@save-context topic-name

# Later sessions
@load-context topic-name
# Claude remembers what worked and what failed
```

### 3. Let Claude Ask Questions

```
Claude: "Should this be a breaking change?"
You: [Provide guidance]
```

### 4. Reference Documentation

```
You: "Check the deployment runbook and review JIRA-5678"
Claude: [Searches ~/context-sync/confluence/ and ~/context-sync/jira/, follows documented procedures]
```

### 5. Build Tools Over Time

```bash
# First time: Manual command
npm test -- --coverage --verbose

# Claude: "Want me to make this a reusable script?"
# Creates ~/tools/test-with-coverage.sh

# Next time:
~/tools/test-with-coverage.sh
```

## File Locations Reference

### Agent Instructions (automatically loaded)
- `~/CLAUDE.md` - Mission + environment rules
- `~/khan/CLAUDE.md` - Khan Academy standards
- `~/tools-guide.md` - Reference for building tools

### Context Documents (use commands)
- `~/sharing/context/<filename>.md` - Saved sessions

### Reusable Tools (you create)
- `~/tools/<script>.sh` - Your helper scripts

### Context Sources (read-only)
- `~/context-sync/confluence/` - Confluence docs (ADRs, runbooks, docs)
- `~/context-sync/jira/` - JIRA tickets and issues
- `~/context-sync/github/` - GitHub PRs (future)
- `~/context-sync/slack/` - Slack messages (future)

## Example Session (Start to Finish)

```bash
# 1. Start (from host)
cd ~/khan/james-in-a-box
./claude-sandboxed

# 2. Launch Claude (inside container)
claude

# 3. Load context
You: @load-context webapp-refactor

# 4. Give task
You: Refactor user auth module to use new AuthService

# 5. Claude works
Claude: I'll examine the current implementation...
[Explores, asks questions, implements, tests]
Claude: Complete. All tests passing.

# 6. Create PR
You: Create a PR
@create-pr audit

# 7. Save knowledge
You: @save-context webapp-refactor
Claude: ✅ Saved Session 4

# 8. Exit and review
exit

# On host: Review PR, approve, merge
```

## Remember

- Claude is **autonomous** - Give direction, let it work
- Claude **accumulates knowledge** - Use @save-context
- Claude **builds tools** - Leverage ~/tools/
- You're the **reviewer** - Approve and ship
- Ask questions - Claude explains its work

---

**See also:**
- **README.md** - Architecture and philosophy
- **claude-rules/README.md** - Agent instructions system
- **claude-commands/README.md** - Custom commands guide
