# User Guide

Day-to-day usage documentation for james-in-a-box.

## Guides

### [Quickstart](quickstart.md)
Get started with james-in-a-box in 5 minutes.

**Covers:**
- Running jib for the first time
- Basic Claude Code usage
- Common workflows
- Where things are stored

### [Workflow](workflow.md)
Best practices and daily usage patterns.

**Covers:**
- Development workflow
- Using slash commands
- Managing context
- Creating PRs
- Reviewing agent output

## Common Tasks

**Start a Session:**
```bash
./jib
```

**Use Slash Commands:**
```
/load-context project-name
/save-context project-name
/create-pr
```

**Review Agent Output:**
- Check `~/.jib-sharing/notifications/` for reports
- Review commits before pushing
- Validate PR descriptions

## See Also
- [Setup Guides](../setup/)
- [Architecture](../architecture/)
- [CLI Tools](../../bin/)
