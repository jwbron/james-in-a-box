# Context Watcher Configuration

Configuration files for the context watching system.

## Files

### context-watcher.yaml

Main configuration file.

**Structure:**
```yaml
directories:
  - path: ~/context-sync/confluence
    pattern: "*.md"
    trigger: analyze-confluence
    
notifications:
  output_dir: ~/sharing/notifications
  
analysis:
  claude_model: claude-3-sonnet
  max_file_size: 100000
```

**Options:**
- `directories` - Paths to monitor
- `pattern` - File patterns to match
- `trigger` - Action to take on changes
- `notifications.output_dir` - Where to write results
- `analysis.*` - Claude analysis settings

## Customization

Edit `context-watcher.yaml` to:
- Add new directories to watch
- Change file patterns
- Adjust analysis settings
- Configure notification behavior

## See Also
- [Context Watcher Setup](../../../docs/setup/context-watcher-setup.md)
- [Context Watcher Component](../)
