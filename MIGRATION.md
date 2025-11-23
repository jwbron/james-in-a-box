# Migration Guide

Repository restructured to component-based organization.

## Host Machine Steps

```bash
cd ~/khan/james-in-a-box
git pull

# Stop services
systemctl --user stop slack-notifier.service codebase-analyzer.timer conversation-analyzer.timer

# Remove old service files
rm ~/.config/systemd/user/{slack-notifier,codebase-analyzer,conversation-analyzer,service-failure-notify@}.{service,timer}

# Install new service files
cp components/slack-notifier/slack-notifier.service ~/.config/systemd/user/
cp components/codebase-analyzer/*.{service,timer} ~/.config/systemd/user/
cp components/conversation-analyzer/*.{service,timer} ~/.config/systemd/user/
cp components/service-monitor/service-failure-notify@.service ~/.config/systemd/user/

# Reload and restart
systemctl --user daemon-reload
systemctl --user start slack-notifier.service
systemctl --user start codebase-analyzer.timer
systemctl --user start conversation-analyzer.timer

# Verify
systemctl --user status slack-notifier.service
```

## Container Steps

Inside container:

```bash
cd ~/khan/james-in-a-box
git pull

# Context watcher moved
cd jib-container/components/context-watcher
./context-watcher-ctl start
```

## Verify

- [ ] Slack notifier running
- [ ] Timers active
- [ ] Context watcher running (container)
- [ ] No errors in logs

## Cleanup

After 1-2 weeks: `rm -rf archive/`
