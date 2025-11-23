# Reference Documentation

Quick reference guides and troubleshooting.

## Available References

### [Slack Quick Reference](slack-quick-reference.md)
Common Slack operations and commands.

**Quick answers for:**
- Sending test notifications
- Checking service status
- Troubleshooting connection issues
- Managing channels and tokens

### [Codebase Analyzer](codebase-analyzer.md)
Automated code analysis system reference.

**Information about:**
- What it analyzes
- When it runs
- How to interpret results
- Configuration options

## Common Issues

**Slack not receiving notifications:**
1. Check service: `bin/systemctl --user status`
2. Verify token: Check logs for authentication errors
3. Test manually: Write file to `~/.jib-sharing/notifications/`

**Claude Code not available:**
1. Authenticate: `claude auth login`
2. Check version: `claude --version`
3. Verify PATH: `which claude`

**Container issues:**
1. Rebuild: `./jib --reset`
2. Check Docker: `docker ps`
3. View logs: `docker logs jib`

## See Also
- [User Guide](../user-guide/)
- [Troubleshooting](../../README.md#troubleshooting)
