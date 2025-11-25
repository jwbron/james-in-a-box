# Claude Code Configuration

Configuration files for Claude Code CLI integration.

## Structure

### commands/
Slash commands available in Claude Code sessions.

These are invoked with `/command-name` syntax.

**Available commands:**
- `/load-context` - Load accumulated knowledge
- `/save-context` - Save session learnings
- `/create-pr` - Generate PR description
- `/check-staging` - Review staged changes
- `/implement-analyzer-fixes` - Apply analyzer suggestions

### rules/
Agent behavior rules and guidelines.

These define how Claude operates within james-in-a-box.

**Rule files:**
- `mission.md` - Agent mission and responsibilities
- `environment.md` - Sandbox environment constraints
- `khan-academy.md` - Project-specific standards (example)
- `tools-guide.md` - Building reusable tools
- `notification-template.md` - Notification formatting

## Usage

Claude Code automatically loads these files when running in the container.

**Slash Commands:**
```
/load-context my-project
/save-context my-project
/create-pr
```

**Rules:**
Rules are automatically applied. See individual files for details.

## Customization

**Adding Commands:**
1. Create `commands/new-command.md`
2. Follow existing command format
3. Document parameters and usage

**Modifying Rules:**
1. Edit files in `rules/`
2. Test in container session
3. Verify behavior matches intent

## See Also
- [User Guide](../../docs/user-guide/README.md)
- [Commands README](commands/README.md)
- [Rules README](rules/README.md)
