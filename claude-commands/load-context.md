# Claude Command: Load Context Document

**Command**: `/load-context <filename>`

**Example**: `/load-context tf-hackathon`

## Purpose
Load a context-sharing document from `~/sharing/context/` into the current conversation to provide accumulated knowledge from previous sessions.

## Usage

When you see this command:

1. **Validate filename parameter**:
   - **SECURITY FIX**: Filename must be alphanumeric with hyphens/underscores only
   - Maximum length: 100 characters
   - Pattern: `^[a-zA-Z0-9_-]+$`
   - Reject if contains: path separators (`/`, `\`), dots (`..`), or special characters

2. **Locate the file** at `~/sharing/context/<filename>.md`
   - **ERROR HANDLING**: If file doesn't exist, list available context documents
   - **ERROR HANDLING**: If directory doesn't exist, explain and suggest creating first document
   - Use absolute paths: Resolve `~/` to full path `/home/<username>/sharing/context/`
   - This directory is MOUNTED and persists across container rebuilds

3. **Read the entire document** into context
   - **ERROR HANDLING**: Handle file read errors (permissions, corrupted file)
   - **ERROR HANDLING**: If file is too large, warn user and ask for confirmation
   - **ERROR HANDLING**: If file contains invalid structure, attempt to parse anyway but warn user
   - Don't summarize or truncate
   - Load all sessions, playbooks, anti-patterns, and decision logs

4. **Acknowledge what was loaded**:
   ```
   ✅ Loaded context: <filename>.md

   Summary:
   - Created: <date>
   - Last Updated: <date>
   - Sessions: <count>
   - Topic: <brief description>

   Available knowledge:
   - Lessons Learned: <count> sessions
   - Playbooks: <count> patterns
   - Anti-Patterns: <count> documented failures
   - Decision Log: <count> strategy pivots

   How I'll use this:
   - Reference Session X lessons when applicable
   - Apply <playbook names> to current work
   - Avoid <anti-pattern names>
   - Build on previous decisions
   ```

5. **Apply the knowledge** throughout the conversation:
   - Cite specific sessions when using knowledge
   - Apply documented playbooks proactively
   - Warn about anti-patterns if user's request matches documented failures
   - Build on previous decisions

## Critical Rules

✅ **DO**:
- **NEW**: Validate filename against security pattern before file operations
- **NEW**: Handle missing files gracefully by listing available documents
- **NEW**: Warn about corrupted or malformed files but attempt to use anyway
- **NEW**: Provide clear error messages with recovery suggestions
- Read the full document
- Cite specific sessions when using knowledge
- Apply playbooks proactively
- Warn about anti-patterns
- Build on previous decisions

❌ **DON'T**:
- **NEW**: Accept filenames with path separators or special characters
- **NEW**: Silently fail when file doesn't exist
- **NEW**: Crash or halt on malformed files
- Summarize or skip sections
- Blindly follow without judgment
- Assume context is perfect for current situation

## Error Handling Examples

**Invalid filename**:
```
User: /load-context ../secrets
Claude: ❌ Error: Invalid filename. Filenames must contain only letters, numbers,
hyphens, and underscores (no path separators or special characters).
Example: /load-context terraform-migration
```

**File not found**:
```
User: /load-context nonexistent
Claude: ❌ Context file not found: nonexistent.md

Available context documents:
- terraform-migration.md (Updated: 2025-10-30, 3 sessions)
- feature-x.md (Updated: 2025-11-15, 2 sessions)
- sprint23.md (Updated: 2025-11-20, 1 session)

Use: /load-context <filename> (without .md extension)
```

**Directory doesn't exist**:
```
Claude: ❌ Context directory not found: ~/sharing/context/

This directory is created when you save your first context document.
To create one: /save-context <project-name>
```

**Corrupted file**:
```
Claude: ⚠️ Warning: Context file appears to have formatting issues, but I'll load it anyway.
Some sections may be incomplete or difficult to parse.

✅ Loaded context: project.md (with warnings)
[Shows summary of what could be parsed]

Consider re-saving this context to fix formatting.
```

**File read permission error**:
```
Claude: ❌ Error: Cannot read ~/sharing/context/project.md
Permission denied. Check file permissions:
  ls -la ~/sharing/context/project.md
Expected: -rw-r--r-- (readable by user)
```

## Example Usage

```
User: /load-context terraform-migration
Claude: ✅ Loaded context: terraform-migration.md

Summary:
- Created: 2025-10-29
- Last Updated: 2025-10-30
- Sessions: 2
- Topic: Terraform migration from v0.12 to v1.5

Available knowledge:
- Lessons Learned: 2 sessions
- Playbooks: 3 patterns
  * Deploy Service to Staging (v2)
  * Rollback Procedure (v1)
  * Redis Validation (v1)
- Anti-Patterns: 2 documented failures
  * Don't skip Redis connectivity checks
  * Avoid deploying without terraform plan review
- Decision Log: 3 strategy pivots

How I'll use this:
- Reference Session 2's Redis issues when deploying
- Apply "Deploy Service to Staging" v2 playbook
- Warn if you try to skip Redis validation
- Build on decision to use blue-green deployments

Ready to assist with Terraform work using accumulated experience.

User: I want to deploy a new service
Claude: Based on Session 2's 'Deploy Service to Staging' playbook (v2, Oct 30),
let's validate Redis connectivity before deployment...

⚠️ Anti-pattern warning: Session 2 documented that skipping Redis connectivity
checks caused a 2-hour outage. Let's add validation first.
```

## Recovery Suggestions

If you encounter issues:

1. **File not found**: List available documents or create a new one with `/save-context`
2. **Permission errors**: Check file permissions with `ls -la ~/sharing/context/`
3. **Corrupted file**: Consider recreating with `/save-context` or edit manually
4. **Directory missing**: Create first context document to initialize directory
