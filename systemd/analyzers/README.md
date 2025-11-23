# Analyzer Services

Automated code and conversation analysis services.

## Services

### Codebase Analyzer
**Files:** `codebase-analyzer.service`, `codebase-analyzer.timer`

Analyzes the james-in-a-box codebase for improvements weekly.

**Schedule:** Monday at 11:00 AM + 5min after boot  
**Script:** `internal/codebase-analyzer.py`  
**Output:** `~/.jib-sharing/notifications/`

**Install:**
```bash
bin/analyzer-ctl install
bin/analyzer-ctl enable
```

### Conversation Analyzer
**Files:** `conversation-analyzer.service`, `conversation-analyzer.timer`

Analyzes Claude conversation logs for prompt improvements daily.

**Schedule:** Daily at 2:00 AM + 10min after boot  
**Analysis Window:** Last 7 days  
**Output:** `~/.jib-sharing/notifications/`

**Install:**
```bash
bin/conversation-analyzer-ctl install
bin/conversation-analyzer-ctl enable
```

## Manual Runs

```bash
# Run codebase analyzer now
bin/analyzer-ctl start

# Run conversation analyzer now
bin/conversation-analyzer-ctl start
```

## Logs

```bash
# Codebase analyzer
journalctl --user -u codebase-analyzer -f

# Conversation analyzer
journalctl --user -u conversation-analyzer -f
```
