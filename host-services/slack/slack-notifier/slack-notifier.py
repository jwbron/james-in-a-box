#!/usr/bin/env python3
"""
Host-Side Slack Notifier

Monitors shared directories on the host machine and sends Slack DMs when changes are detected.
Uses inotify on Linux to watch for file system events.

Threading support:
- Notification files can include YAML frontmatter with thread_ts to reply in existing threads
- Thread mappings are stored in threads.json for persistence across restarts
"""

import os
import sys
import time
import json
import logging
import signal
from pathlib import Path
from datetime import datetime
from typing import List, Set, Optional, Tuple
import subprocess
import re

# Check for required dependencies
try:
    import inotify.adapters
    import inotify.constants
except ImportError:
    print("Error: inotify module not found.", file=sys.stderr)
    print("Run 'uv sync' from host-services/ or run setup.sh", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: requests module not found.", file=sys.stderr)
    print("Run 'uv sync' from host-services/ or run setup.sh", file=sys.stderr)
    sys.exit(1)


class SlackNotifier:
    """Monitors directories and sends Slack notifications for changes."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_file = config_dir / "config.json"
        self.state_file = config_dir / "state.json"
        # Store threads in shared directory (accessible to both host and container)
        # Host: ~/.jib-sharing/tracking/ -> Container: ~/sharing/tracking/
        self.threads_file = Path.home() / ".jib-sharing" / "tracking" / "slack-threads.json"
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
        """Load configuration from ~/.config/jib/.

        Config location: ~/.config/jib/
        - config.yaml: Non-secret settings
        - secrets.env: Secrets (tokens)

        Environment variables override file settings.
        """
        config = {}

        jib_config_dir = Path.home() / '.config' / 'jib'
        jib_secrets = jib_config_dir / 'secrets.env'
        jib_config = jib_config_dir / 'config.yaml'

        # Load secrets from .env file
        if jib_secrets.exists():
            with open(jib_secrets, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        if key == 'SLACK_TOKEN' and value:
                            config['slack_token'] = value
                        elif key == 'SLACK_APP_TOKEN' and value:
                            config['slack_app_token'] = value

        # Load non-secret config from YAML
        if jib_config.exists():
            try:
                import yaml
                with open(jib_config, 'r') as f:
                    yaml_config = yaml.safe_load(f) or {}
                config.update(yaml_config)
            except ImportError:
                self.logger.warning("PyYAML not available, config.yaml not loaded")

        # Set defaults for missing values
        if 'slack_token' not in config:
            config['slack_token'] = ''
        if 'slack_channel' not in config:
            config['slack_channel'] = ''
        if 'batch_window_seconds' not in config:
            config['batch_window_seconds'] = 15
        if 'watch_directories' not in config:
            config['watch_directories'] = ['~/.jib-sharing']

        # Environment variables override everything
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
            self.threads_file.parent.mkdir(parents=True, exist_ok=True)
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
        # Remove .md extension
        name = filename.replace('.md', '')
        # Remove RESPONSE- prefix if present
        name = re.sub(r'^RESPONSE-', '', name)
        return name

    def _parse_frontmatter(self, content: str) -> Tuple[dict, str]:
        """Parse YAML frontmatter from notification content.

        Notifications can include thread context in YAML frontmatter:
        ---
        thread_ts: "1732428847.123456"
        task_id: "task-20251124-111907"
        ---
        # Notification content...

        Args:
            content: Full file content

        Returns:
            Tuple of (metadata dict, content without frontmatter)
        """
        metadata = {}

        # Check for YAML frontmatter (starts with ---)
        if not content.startswith('---'):
            return metadata, content

        # Find the closing ---
        lines = content.split('\n')
        end_idx = -1
        for i, line in enumerate(lines[1:], start=1):  # Skip first ---
            if line.strip() == '---':
                end_idx = i
                break

        if end_idx == -1:
            # No closing ---, treat as no frontmatter
            return metadata, content

        # Parse the frontmatter (simple key: value parsing)
        frontmatter_lines = lines[1:end_idx]
        for line in frontmatter_lines:
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip().strip('"\'')  # Remove quotes
                if value:  # Only add non-empty values
                    metadata[key] = value

        # Return content without frontmatter
        remaining_content = '\n'.join(lines[end_idx + 1:]).strip()
        return metadata, remaining_content

    def _chunk_message(self, content: str, max_length: int = 3000) -> List[str]:
        """Split long messages into chunks that fit Slack's limits.

        Slack's message limit is ~4000 chars, but we chunk at 3000 for safety.
        Tries to split on natural boundaries (paragraphs, sentences).

        Args:
            content: The full message content
            max_length: Maximum characters per chunk (default 3000)

        Returns:
            List of message chunks
        """
        if len(content) <= max_length:
            return [content]

        chunks = []
        remaining = content

        while remaining:
            # If remaining text fits in one chunk, we're done
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break

            # Find the best split point within max_length
            chunk = remaining[:max_length]

            # Try to split on paragraph boundary (double newline)
            split_idx = chunk.rfind('\n\n')

            # If no paragraph boundary, try single newline
            if split_idx == -1:
                split_idx = chunk.rfind('\n')

            # If no newline, try sentence boundary
            if split_idx == -1:
                split_idx = max(
                    chunk.rfind('. '),
                    chunk.rfind('! '),
                    chunk.rfind('? ')
                )
                if split_idx != -1:
                    split_idx += 1  # Include the punctuation

            # If no natural boundary, split at word boundary
            if split_idx == -1:
                split_idx = chunk.rfind(' ')

            # If still no good split point, just cut at max_length
            if split_idx == -1:
                split_idx = max_length

            # Add this chunk
            chunks.append(remaining[:split_idx].strip())
            remaining = remaining[split_idx:].strip()

        # Add chunk indicators if we split the message
        if len(chunks) > 1:
            for i, chunk in enumerate(chunks):
                chunks[i] = f"**(Part {i+1}/{len(chunks)})**\n\n{chunk}"

        return chunks

    def _send_slack_message(self, changes: List[str]) -> bool:
        """Send notification files to Slack with threading support.

        Reads each notification file and sends its full content.
        Thread context is determined by (in order of priority):
        1. YAML frontmatter thread_ts in the notification file
        2. threads.json mapping based on task ID
        3. New thread (if neither found)
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
                    raw_content = f.read().strip()

                if not raw_content:
                    self.logger.warning(f"Empty file: {path}")
                    continue

            except Exception as e:
                self.logger.error(f"Failed to read {path}: {e}")
                continue

            # Parse frontmatter for thread context
            frontmatter, content = self._parse_frontmatter(raw_content)
            frontmatter_thread_ts = frontmatter.get('thread_ts')
            frontmatter_task_id = frontmatter.get('task_id')

            # Extract task ID from filename (fallback)
            filename_task_id = self._extract_task_id(path.name)

            # Use task_id from frontmatter if provided, otherwise use filename
            task_id = frontmatter_task_id or filename_task_id

            # CRITICAL: Reload threads from disk before lookup
            # The receiver may have saved new thread mappings since we started
            # Without this, responses won't thread correctly with the original message
            self.threads = self._load_threads()

            # Determine thread_ts: frontmatter takes priority, then threads.json
            thread_ts = frontmatter_thread_ts or self.threads.get(task_id)

            if frontmatter_thread_ts:
                self.logger.info(f"Using thread_ts from frontmatter: {frontmatter_thread_ts}")
            elif thread_ts:
                self.logger.info(f"Found thread mapping: {task_id} → {thread_ts}")
            else:
                self.logger.info(f"No thread context found for: {task_id} (will create new thread)")

            # Split content into chunks if too long
            chunks = self._chunk_message(content)
            self.logger.info(f"Sending {len(chunks)} chunk(s) for {path.name}")

            # Send each chunk
            first_chunk = True
            for chunk_idx, chunk in enumerate(chunks):
                # Prepare message payload
                payload = {
                    'channel': self.slack_channel,
                    'text': chunk,
                    'mrkdwn': True
                }

                # If we have an existing thread, reply in that thread
                # For multi-chunk messages, subsequent chunks reply to first chunk
                if thread_ts:
                    payload['thread_ts'] = thread_ts
                    if first_chunk:
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
                        if first_chunk:
                            self.logger.info(f"Sent notification: {path.name}")
                            success_count += 1

                            # Store thread_ts for future replies if this is a new thread
                            if not thread_ts and result.get('ts'):
                                thread_ts = result['ts']  # Update for subsequent chunks
                                self.threads[task_id] = result['ts']
                                self._save_threads()
                                self.logger.info(f"Created new thread for task {task_id}: {result['ts']}")
                        else:
                            self.logger.info(f"Sent chunk {chunk_idx + 1}/{len(chunks)} for {path.name}")

                        first_chunk = False

                        # Add small delay between chunks to ensure proper threading
                        if chunk_idx < len(chunks) - 1:  # Not the last chunk
                            time.sleep(0.5)

                    else:
                        error = result.get('error', 'unknown error')
                        self.logger.error(f"Failed to send {path.name} chunk {chunk_idx + 1}: {error}")
                        break  # Don't send remaining chunks if one fails

                except Exception as e:
                    self.logger.error(f"Exception sending {path.name} chunk {chunk_idx + 1}: {e}")
                    break  # Don't send remaining chunks if one fails

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
