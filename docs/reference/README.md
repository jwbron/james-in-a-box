# Reference Documentation

Quick reference guides and troubleshooting.

## Available References

### [Beads Task Tracking](beads.md)
Persistent task memory system for autonomous agents.

**Essential for:**
- Tracking work across container restarts
- Finding existing tasks before creating new ones
- Recording decisions and progress
- Linking related work (Slack threads, PRs, JIRA)

**Quick start:** Always run `bd --allow-stale list --status in_progress` before starting work.

### [Slack Quick Reference](slack-quick-reference.md)
Common Slack operations and commands.

**Quick answers for:**
- Sending test notifications
- Checking service status
- Troubleshooting connection issues
- Managing channels and tokens

### [Khan Academy Culture](khan-academy-culture.md)
Engineering culture standards from the Khan Academy Career Ladder.

**Information about:**
- L3-L4 (Senior Software Engineer) behavioral expectations
- Problem solving, communication, and collaboration standards
- Engineering principles

### [Conversation Analysis Criteria](conversation-analysis-criteria.md)
Assessment criteria for the conversation analyzer.

**Information about:**
- Assessment dimensions and scoring
- Positive and negative indicators
- Target performance levels

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
