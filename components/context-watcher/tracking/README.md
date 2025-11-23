# Context Watcher Tracking

Tracking data for monitored files and analysis history.

## Purpose

Stores metadata about:
- Files being monitored
- Last modification times
- Analysis history
- Processing status

## Files

Tracking files use JSON format:
```json
{
  "file": "/path/to/file.md",
  "last_modified": "2025-11-23T10:30:00",
  "last_analyzed": "2025-11-23T10:31:00",
  "status": "analyzed"
}
```

## Usage

Used internally by context-watcher to:
- Detect changes since last analysis
- Avoid re-analyzing unchanged files
- Track processing status
- Maintain analysis history

## Maintenance

Generally managed automatically. Can be reset if needed:
```bash
rm ~/.jib-sharing/tracking/*
# Context watcher will rebuild on next run
```
