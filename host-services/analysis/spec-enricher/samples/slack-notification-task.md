# Task: Add Slack Notification for PR Reviews

## Description

When a PR receives a review approval, send a Slack notification to the author.

## Requirements

- Listen for GitHub PR review events
- When status is "approved", notify the PR author via Slack
- Include PR title, reviewer name, and link
- Use the existing notification system

## Acceptance Criteria

- [ ] PR approval triggers notification
- [ ] Notification includes all required info
- [ ] Tests pass
