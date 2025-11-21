# Claude Command: Load Context Document

**Command**: `@load-context <filename>`

**Example**: `@load-context tf-hackathon`

## Purpose
Load a context-sharing document from `~/sharing/context/` into the current conversation to provide accumulated knowledge from previous sessions.

## Usage

When you see this command:

1. **Locate the file** at `~/sharing/context/<filename>.md`
   - If file doesn't exist, list available context documents
   - Use absolute paths: `/home/<username>/sharing/context/`
   - This directory is MOUNTED and persists across container rebuilds

2. **Read the entire document** into context
   - Don't summarize or truncate
   - Load all sessions, playbooks, anti-patterns, and decision logs

3. **Acknowledge what was loaded**:
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

4. **Apply the knowledge** throughout the conversation:
   - Cite specific sessions when using knowledge
   - Apply documented playbooks proactively
   - Warn about anti-patterns if user's request matches documented failures
   - Build on previous decisions

## Critical Rules

✅ **DO**:
- Read the full document
- Cite specific sessions when using knowledge
- Apply playbooks proactively
- Warn about anti-patterns
- Build on previous decisions

❌ **DON'T**:
- Summarize or skip sections
- Blindly follow without judgment
- Assume context is perfect for current situation

## Example Usage

```
User: @load-context terraform-migration
Claude: ✅ Loaded context: terraform-migration.md
[Shows summary and available knowledge]
Ready to assist with Terraform work using accumulated experience.

User: I want to deploy a new service
Claude: Based on Session 2's 'Deploy Service to Staging' playbook (v2, Oct 30), 
let's validate Redis connectivity before deployment...
```

