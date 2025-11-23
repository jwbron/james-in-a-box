#!/usr/bin/env python3
"""
Host-Side Slack Notifier

Monitors shared directories on the host machine and sends Slack DMs when changes are detected.
Uses inotify on Linux to watch for file system events.
"""

import os
import sys
import time
import json
import logging
import signal
from pathlib import Path
from datetime import datetime
from typing import List, Set
import subprocess

# Check for required dependencies
try:
    import inotify.adapters
    import inotify.constants
except ImportError:
    print("Error: inotify module not found.", file=sys.stderr)
    print("Install with: pip install inotify", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: requests module not found.", file=sys.stderr)
    print("Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


class SlackNotifier:
    """Monitors directories and sends Slack notifications for changes."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_file = config_dir / "config.json"
        self.state_file = config_dir / "state.json"
        self.threads_file = config_dir / "threads.json"
        self.log_file = config_dir / "notifier.log"

        # Ensure config directory exists with secure permissions
        self.config_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.config_dir, 0o700)

        # Set up logging
        self._setup_logging()

        # Load configuration
        self.config = self._load_config()

        # Validate Slack token
        self.slack_token = self.config.get('slack_token')
        if not self.slack_token:
            self.logger.error("SLACK_TOKEN not configured")
            raise ValueError("SLACK_TOKEN not found in config")

        # Configuration
        # SECURITY FIX: Do not hardcode channel ID - require it to be configured
        self.slack_channel = self.config.get('slack_channel')
        if not self.slack_channel:
            self.logger.error("SLACK_CHANNEL not configured")
            raise ValueError("SLACK_CHANNEL not found in config. Set it in config.json or environment.")
        # How long to wait before sending batched notifications (seconds)
        # Lower = faster notifications, Higher = fewer Slack messages
        self.batch_window = self.config.get('batch_window_seconds', 15)
        self.watch_dirs = [Path(d).expanduser() for d in self.config.get('watch_directories', [])]

        # State
        self.pending_changes: Set[str] = set()
        self.last_batch_time = time.time()
        self.running = True
        self.threads = self._load_threads()

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _setup_logging(self):
        """Configure logging to file and console."""
        self.logger = logging.getLogger('jib-notifier')
        self.logger.setLevel(logging.INFO)

        # File handler
        fh = logging.FileHandler(self.log_file)
        fh.setLevel(logging.INFO)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s',
                                     datefmt='%Y-%m-%d %H:%M:%S')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        self.logger.addHandler(fh)
        self.logger.addHandler(ch)

    def _load_config(self) -> dict:
        """Load configuration from file or environment."""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                config = json.load(f)
        else:
            # Create default config
            # SECURITY FIX: Do not hardcode channel ID - use environment variable
            config = {
                'slack_token': os.environ.get('SLACK_TOKEN', ''),
                'slack_channel': os.environ.get('SLACK_CHANNEL', ''),
                # How many seconds to wait before sending notifications
                # 15 = send every 15 seconds, 30 = send every 30 seconds
                'batch_window_seconds': 15,
                'watch_directories': [
                    '~/.jib-sharing',
                    '~/.jib-tools'
                ]
            }
            self._save_config(config)

        # Override with environment variables if present
        if os.environ.get('SLACK_TOKEN'):
            config['slack_token'] = os.environ['SLACK_TOKEN']
        if os.environ.get('SLACK_CHANNEL'):
            config['slack_channel'] = os.environ['SLACK_CHANNEL']

        return config

    def _save_config(self, config: dict):
        """Save configuration to file with secure permissions."""
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
        os.chmod(self.config_file, 0o600)
        self.logger.info(f"Configuration saved to {self.config_file}")

    def _load_threads(self) -> dict:
        """Load thread state mapping task IDs to Slack thread_ts."""
        if self.threads_file.exists():
            try:
                with open(self.threads_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Failed to load threads file: {e}")
                return {}
        return {}

    def _save_threads(self):
        """Save thread state to file."""
        try:
            with open(self.threads_file, 'w') as f:
                json.dump(self.threads, f, indent=2)
            os.chmod(self.threads_file, 0o600)
        except Exception as e:
            self.logger.error(f"Failed to save threads file: {e}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _should_ignore(self, path: str) -> bool:
        """Check if a path should be ignored."""
        ignore_patterns = [
            '.swp', '.tmp', '.lock', '~',
            '.git/', '__pycache__/',
            'node_modules/', '.venv/'
        ]
        return any(pattern in path for pattern in ignore_patterns)

    def _extract_task_id(self, filename: str) -> str:
        """Extract task ID from notification filename.

        Examples:
          - task-20251123-143022.md → task-20251123-143022
          - RESPONSE-task-20251123-143022.md → task-20251123-143022
          - notification-20251123-143022.md → notification-20251123-143022
        """
        import re
        # Remove .md extension
        name = filename.replace('.md', '')
        # Remove RESPONSE- prefix if present
        name = re.sub(r'^RESPONSE-', '', name)
        return name

    def _send_slack_message(self, changes: List[str]) -> bool:
        """Send notification files to Slack with threading support.

        Reads each notification file and sends its full content.
        - If this is a response to an existing task, replies in thread
        - If this is a new notification, creates a new thread and stores thread_ts
        """
        if not changes:
            return True

        success_count = 0

        for change_path in changes:
            path = Path(change_path)

            # Only process .md files
            if not path.suffix == '.md':
                continue

            # Read file content
            try:
                with open(path, 'r') as f:
                    content = f.read().strip()

                if not content:
                    self.logger.warning(f"Empty file: {path}")
                    continue

            except Exception as e:
                self.logger.error(f"Failed to read {path}: {e}")
                continue

            # Extract task ID to check for existing thread
            task_id = self._extract_task_id(path.name)
            thread_ts = self.threads.get(task_id)

            # Prepare message payload
            payload = {
                'channel': self.slack_channel,
                'text': content,
                'mrkdwn': True
            }

            # If we have an existing thread, reply in that thread
            if thread_ts:
                payload['thread_ts'] = thread_ts
                self.logger.info(f"Replying in thread {thread_ts} for task {task_id}")

            # Send to Slack
            try:
                response = requests.post(
                    'https://slack.com/api/chat.postMessage',
                    headers={
                        'Authorization': f'Bearer {self.slack_token}',
                        'Content-Type': 'application/json'
                    },
                    json=payload,
                    timeout=10
                )

                result = response.json()

                if result.get('ok'):
                    self.logger.info(f"Sent notification: {path.name}")
                    success_count += 1

                    # Store thread_ts for future replies if this is a new thread
                    if not thread_ts and result.get('ts'):
                        self.threads[task_id] = result['ts']
                        self._save_threads()
                        self.logger.info(f"Created new thread for task {task_id}: {result['ts']}")

                else:
                    error = result.get('error', 'unknown error')
                    self.logger.error(f"Failed to send {path.name}: {error}")

            except Exception as e:
                self.logger.error(f"Exception sending {path.name}: {e}")

        self.logger.info(f"Sent {success_count}/{len(changes)} notifications")
        return success_count > 0

    def _process_batch(self):
        """Process accumulated changes and send notification."""
        if not self.pending_changes:
            return

        changes = sorted(list(self.pending_changes))
        self.logger.info(f"Processing batch of {len(changes)} change(s)")

        self._send_slack_message(changes)

        # Clear pending changes
        self.pending_changes.clear()
        self.last_batch_time = time.time()

    def watch(self):
        """Start watching directories for changes."""
        # Validate watch directories exist
        for watch_dir in self.watch_dirs:
            if not watch_dir.exists():
                self.logger.warning(f"Watch directory does not exist: {watch_dir}")
                watch_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Created watch directory: {watch_dir}")

        self.logger.info(f"Starting Slack notifier (PID: {os.getpid()})")
        self.logger.info(f"Watching {len(self.watch_dirs)} directories:")
        for watch_dir in self.watch_dirs:
            self.logger.info(f"  - {watch_dir}")
        self.logger.info(f"Batch window: {self.batch_window} seconds")
        self.logger.info(f"Slack channel: {self.slack_channel}")

        # Create inotify watcher
        i = inotify.adapters.Inotify()

        # Add watches for each directory (recursive)
        watches_added = 0
        for watch_dir in self.watch_dirs:
            try:
                i.add_watch(str(watch_dir), mask=inotify.constants.IN_CREATE |
                                                 inotify.constants.IN_MOVED_TO)
                watches_added += 1
                self.logger.info(f"Added watch for: {watch_dir}")
                # Also watch subdirectories
                for root, dirs, files in os.walk(watch_dir):
                    for d in dirs:
                        subdir = os.path.join(root, d)
                        if not self._should_ignore(subdir):
                            try:
                                i.add_watch(subdir, mask=inotify.constants.IN_CREATE |
                                                         inotify.constants.IN_MOVED_TO)
                            except Exception as e:
                                self.logger.debug(f"Could not watch {subdir}: {e}")
            except Exception as e:
                self.logger.error(f"Failed to watch {watch_dir}: {e}")

        self.logger.info(f"Total watches added: {watches_added}")
        if watches_added == 0:
            self.logger.error("No watches were added - cannot monitor for changes")
            return

        # Main event loop
        self.logger.info("Starting main event loop...")
        event_count = 0
        try:
            while self.running:
                for event in i.event_gen(yield_nones=False, timeout_s=1):
                    if event is None:
                        continue

                    event_count += 1
                    if event_count % 100 == 0:
                        self.logger.debug(f"Processed {event_count} events...")

                    if not self.running:
                        self.logger.info("Received shutdown signal, exiting loop")
                        break

                    (_, type_names, path, filename) = event

                    # Build full path
                    if filename:
                        full_path = os.path.join(path, filename)
                    else:
                        full_path = path

                    # Skip ignored files
                    if self._should_ignore(full_path):
                        continue

                    # Add to pending changes
                    self.pending_changes.add(full_path)
                    self.logger.debug(f"Change detected: {full_path} ({', '.join(type_names)})")

                    # Check if batch window has elapsed
                    if time.time() - self.last_batch_time >= self.batch_window:
                        self._process_batch()

                    # Process any remaining changes when shutting down
                    if not self.running and self.pending_changes:
                        self._process_batch()

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            self.logger.info(f"Event loop exited after {event_count} events")
            # Process any remaining changes
            if self.pending_changes:
                self._process_batch()

            self.logger.info("Slack notifier stopped")


def main():
    """Main entry point."""
    config_dir = Path.home() / '.config' / 'jib-notifier'

    try:
        notifier = SlackNotifier(config_dir)
        notifier.watch()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        logging.exception("Fatal error")
        sys.exit(1)


if __name__ == '__main__':
    main()
