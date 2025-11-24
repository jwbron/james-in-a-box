# JIRA Connector

Syncs JIRA tickets and comments to local markdown files.

## Features

- Syncs tickets based on JQL query (default: your assigned tickets)
- Includes ticket comments
- Includes attachment metadata
- Includes work logs (optional)
- Converts Atlassian Document Format (ADF) to markdown
- Incremental sync (only updates changed tickets)
- Outputs clean markdown files

## Configuration

Set these environment variables (or add to `.env` file):

### Required

```bash
JIRA_BASE_URL=https://khanacademy.atlassian.net
JIRA_USERNAME=your.email@khanacademy.org
JIRA_API_TOKEN=your_api_token
```

### Optional

```bash
# JQL query to filter tickets (default: assigned to you)
JIRA_JQL_QUERY="assignee = currentUser() ORDER BY updated DESC"

# Maximum tickets to sync (0 = unlimited)
JIRA_MAX_TICKETS=0

# Include comments (default: true)
JIRA_INCLUDE_COMMENTS=true

# Include attachment metadata (default: true)
JIRA_INCLUDE_ATTACHMENTS=true

# Include work logs (default: false)
JIRA_INCLUDE_WORKLOGS=false

# Output directory (default: ~/context-sync/jira)
JIRA_OUTPUT_DIR=~/context-sync/jira

# Incremental sync (default: true)
JIRA_INCREMENTAL_SYNC=true

# API timeout (default: 30 seconds)
JIRA_REQUEST_TIMEOUT=30
```

## Getting Your API Token

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a name like "Context Sync"
4. Copy the token and use it as `JIRA_API_TOKEN`

**Note:** The same Confluence API token works for JIRA since they're both Atlassian Cloud.

## Usage

### Run Standalone

```bash
# Sync your tickets
python -m connectors.jira.connector

# Full sync (re-fetch everything)
python -m connectors.jira.connector --full

# Custom output directory
python -m connectors.jira.connector --output-dir /path/to/output
```

### Via Main Orchestrator

The JIRA connector is automatically included when you run:

```bash
./sync_all.py
```

## JQL Query Examples

```bash
# Your assigned tickets
JIRA_JQL_QUERY="assignee = currentUser() ORDER BY updated DESC"

# Open tickets assigned to you
JIRA_JQL_QUERY="assignee = currentUser() AND status != Done ORDER BY updated DESC"

# Recently updated tickets you're watching
JIRA_JQL_QUERY="watcher = currentUser() AND updated >= -7d ORDER BY updated DESC"

# Tickets in specific project
JIRA_JQL_QUERY="project = INFRA AND assignee = currentUser()"

# Tickets with specific label
JIRA_JQL_QUERY="labels = terraform AND assignee = currentUser()"

# Tickets you reported
JIRA_JQL_QUERY="reporter = currentUser() ORDER BY created DESC"
```

## Output Format

Each ticket is saved as a markdown file named `{KEY}_{SUMMARY}.md`:

```
~/context-sync/jira/
├── INFRA-1234_Fix_deployment_issue.md
├── INFRA-1235_Add_monitoring_alerts.md
└── PRODUCT-567_Implement_new_feature.md
```

### Example Output

```markdown
# INFRA-1234: Fix deployment issue

**URL:** [INFRA-1234](https://khanacademy.atlassian.net/browse/INFRA-1234)
**Type:** Bug
**Status:** In Progress
**Priority:** High
**Assignee:** John Doe
**Reporter:** Jane Smith
**Created:** 2025-11-15T10:30:00.000-0800
**Updated:** 2025-11-21T14:15:00.000-0800
**Labels:** deployment, urgent
**Components:** Infrastructure, CI/CD

---

## Description

The deployment pipeline is failing on the production environment...

## Comments

### Comment 1 - Jane Smith (2025-11-15T11:00:00.000-0800)

I've investigated this and it seems to be related to...

### Comment 2 - John Doe (2025-11-15T14:30:00.000-0800)

Thanks for the investigation. I'll work on a fix...

## Attachments

- **error_log.txt** (12345 bytes) - uploaded by John Doe on 2025-11-15
  - [Download](https://...)
```

## Incremental Sync

The connector maintains state in `~/context-sync/jira/.sync_state` to avoid re-fetching unchanged tickets.

It detects changes based on:
- Ticket update timestamp
- Number of comments

To force a full re-sync:
```bash
rm ~/context-sync/jira/.sync_state
./sync_all.py
```

## Troubleshooting

### "Invalid configuration"

Make sure all required environment variables are set:
```bash
echo $JIRA_BASE_URL
echo $JIRA_USERNAME
# Don't echo the API token for security
```

### "Failed to authenticate"

- Check that your API token is correct
- Verify your username (email) is correct
- Make sure the token hasn't expired

### "No tickets found"

- Check your JQL query: `echo $JIRA_JQL_QUERY`
- Test the query in JIRA's web interface
- Make sure you have tickets assigned to you

### Rate Limiting

If you see rate limit errors:
- Reduce `JIRA_MAX_TICKETS` to sync fewer tickets
- The connector includes automatic delays between requests

## Performance

- **Initial sync:** ~5-10 seconds per 100 tickets
- **Incremental sync:** Only fetches changed tickets (much faster)
- **Network:** Uses JIRA REST API v3
- **Memory:** Low (processes tickets one at a time)

## Privacy & Security

- API tokens are stored in `.env` (not committed to git)
- Synced files are local only (not uploaded anywhere)
- Comments and descriptions are stored as-is
- Attachment files are NOT downloaded (only metadata)

## Limitations

- Attachments are listed but not downloaded (only metadata)
- Large tickets (>1000 comments) may take longer to process
- Some ADF formatting may not convert perfectly to markdown
- Emoji and special characters are preserved in markdown

