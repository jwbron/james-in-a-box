# Slack Receiver

Receives Slack messages and writes to `~/sharing/incoming/`.

## Files
- `host-receive-ctl` - Control script
- `host-receive-slack.py` - Webhook server
- `incoming-watcher.sh` - Monitor incoming

## Usage
```bash
./host-receive-ctl start|stop|status
```
