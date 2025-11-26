#!/usr/bin/env python3
"""
Host-Side Slack Receiver

Listens for incoming Slack messages (DMs) and writes them to a shared directory
where the container can pick them up. This enables bidirectional communication:
- Claude → Slack (via host-notify-slack.py)
- Slack → Claude (via this script)

Uses Slack Socket Mode to receive events without exposing a public endpoint.
"""

import json
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# Check for required dependencies
try:
    from slack_sdk import WebClient
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
except ImportError:
    print("Error: slack_sdk module not found.", file=sys.stderr)
    print("Install with: pip install slack-sdk", file=sys.stderr)
    sys.exit(1)


class SlackReceiver:
    """Receives Slack messages and writes them to shared directory."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_file = config_dir / "config.json"
        # Store threads in shared directory (accessible to both host and container)
        # Host: ~/.jib-sharing/tracking/ -> Container: ~/sharing/tracking/
        self.threads_file = Path.home() / ".jib-sharing" / "tracking" / "slack-threads.json"
        self.log_file = config_dir / "receiver.log"

        # Ensure config directory exists with secure permissions
        self.config_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.config_dir, 0o700)

        # Set up logging
        self._setup_logging()

        # Load configuration
        self.config = self._load_config()

        # Load thread state
        self.threads = self._load_threads()

        # Validate tokens
        self.bot_token = self.config.get("slack_token")
        self.app_token = self.config.get("slack_app_token")

        if not self.bot_token:
            self.logger.error("SLACK_TOKEN not configured")
            raise ValueError("SLACK_TOKEN not found in config")

        if not self.app_token:
            self.logger.error("SLACK_APP_TOKEN not configured")
            raise ValueError("SLACK_APP_TOKEN not found in config (required for Socket Mode)")

        # Configuration
        self.allowed_users = self.config.get("allowed_users", [])
        self.self_dm_channel = self.config.get("self_dm_channel")  # User's self-DM channel ID
        self.owner_user_id = self.config.get("owner_user_id")  # User's Slack user ID
        self.bot_user_id = None
        self.incoming_dir = Path(
            self.config.get("incoming_directory", "~/.jib-sharing/incoming")
        ).expanduser()
        self.responses_dir = Path(
            self.config.get("responses_directory", "~/.jib-sharing/responses")
        ).expanduser()

        # Ensure incoming directories exist
        self.incoming_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Slack clients
        self.web_client = WebClient(token=self.bot_token)
        self.socket_client = None
        self.running = True

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _setup_logging(self):
        """Configure logging to file and console."""
        self.logger = logging.getLogger("slack-receiver")
        self.logger.setLevel(logging.INFO)

        # File handler
        fh = logging.FileHandler(self.log_file)
        fh.setLevel(logging.INFO)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
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

        jib_config_dir = Path.home() / ".config" / "jib"
        jib_secrets = jib_config_dir / "secrets.env"
        jib_config = jib_config_dir / "config.yaml"

        # Load secrets from .env file
        if jib_secrets.exists():
            with open(jib_secrets) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip("\"'")
                        if key == "SLACK_TOKEN" and value:
                            config["slack_token"] = value
                        elif key == "SLACK_APP_TOKEN" and value:
                            config["slack_app_token"] = value

        # Load non-secret config from YAML
        if jib_config.exists():
            try:
                import yaml

                with open(jib_config) as f:
                    yaml_config = yaml.safe_load(f) or {}
                config.update(yaml_config)
            except ImportError:
                self.logger.warning("PyYAML not available, config.yaml not loaded")

        # Set defaults for missing values
        if "slack_token" not in config:
            config["slack_token"] = ""
        if "slack_app_token" not in config:
            config["slack_app_token"] = ""
        if "allowed_users" not in config:
            config["allowed_users"] = []
        if "self_dm_channel" not in config:
            config["self_dm_channel"] = ""
        if "owner_user_id" not in config:
            config["owner_user_id"] = ""
        if "incoming_directory" not in config:
            config["incoming_directory"] = "~/.jib-sharing/incoming"
        if "responses_directory" not in config:
            config["responses_directory"] = "~/.jib-sharing/responses"

        # Environment variables override everything
        if os.environ.get("SLACK_TOKEN"):
            config["slack_token"] = os.environ["SLACK_TOKEN"]
        if os.environ.get("SLACK_APP_TOKEN"):
            config["slack_app_token"] = os.environ["SLACK_APP_TOKEN"]

        return config

    def _save_config(self, config: dict):
        """Save configuration to file with secure permissions."""
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)
        os.chmod(self.config_file, 0o600)
        self.logger.info(f"Configuration saved to {self.config_file}")

    def _load_threads(self) -> dict:
        """Load thread state mapping task IDs to Slack thread_ts."""
        if self.threads_file.exists():
            try:
                with open(self.threads_file) as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Failed to load threads file: {e}")
                return {}
        return {}

    def _save_threads(self):
        """Save thread state to file."""
        try:
            self.threads_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.threads_file, "w") as f:
                json.dump(self.threads, f, indent=2)
            os.chmod(self.threads_file, 0o600)
        except Exception as e:
            self.logger.error(f"Failed to save threads file: {e}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        if self.socket_client:
            self.socket_client.close()

    def _get_bot_user_id(self):
        """Get the bot's user ID."""
        try:
            response = self.web_client.auth_test()
            if response["ok"]:
                self.bot_user_id = response["user_id"]
                self.logger.info(f"Bot user ID: {self.bot_user_id}")
            else:
                self.logger.error("Failed to get bot user ID")
        except Exception as e:
            self.logger.error(f"Exception getting bot user ID: {e}")

    def _is_allowed_user(self, user_id: str) -> bool:
        """Check if user is allowed to send messages."""
        # If no allowed_users configured, allow all
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users

    def _execute_command(self, command_text: str) -> bool:
        """
        Execute remote control command.

        Returns True if command was executed, False otherwise.
        """
        # Path to remote control script
        script_dir = Path(__file__).parent
        remote_control = script_dir / "remote-control.sh"

        if not remote_control.exists():
            self.logger.error(f"Remote control script not found: {remote_control}")
            return False

        # Parse command text
        # Expected format: "/jib restart" or "/service restart slack-notifier.service" or "help"
        parts = command_text.strip().split()

        if not parts:
            return False

        # Handle "help" command
        if parts[0].lower() == "help" or parts[0] == "/help":
            parts = ["help"]
        # Handle commands starting with /
        elif parts[0].startswith("/"):
            # Remove leading slash
            parts[0] = parts[0][1:]

        # Execute command in background (async)
        try:
            self.logger.info(f"Executing remote command: {' '.join(parts)}")

            # Run command in background
            subprocess.Popen(
                [str(remote_control)] + parts,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # Detach from parent
            )

            self.logger.info("Command dispatched successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to execute command: {e}")
            return False

    def _parse_message(
        self, text: str, thread_ts: str | None = None, channel: str | None = None
    ) -> dict[str, Any]:
        """
        Parse incoming message to determine type and content.

        Message types:
        1. Remote control command → Execute system command
        2. Thread reply to notification → Response to Claude
        3. Direct message to bot → New task

        Args:
            text: Message text
            thread_ts: Thread timestamp (if this is a thread reply)
            channel: Channel ID where message was sent
        """
        text = text.strip()
        import re

        # Pattern 1: Remote control commands
        # Commands start with "/" or are just "help"
        if text.startswith("/") or text.lower() in ["help", "commands"]:
            return {"type": "command", "content": text}

        # Pattern 2: Thread reply to notification
        # If message is in a thread, extract the parent message timestamp
        if thread_ts:
            # Thread replies are responses to Claude's notifications
            # Extract timestamp from thread if it contains notification format
            timestamp_pattern = r"\b\d{8}-\d{6}\b"

            # Try to find notification timestamp in this message
            referenced_notif = re.search(timestamp_pattern, text)

            return {
                "type": "response",
                "content": text,
                "referenced_notification": referenced_notif.group(0) if referenced_notif else None,
                "thread_ts": thread_ts,
            }

        # Pattern 3: Direct message to bot
        # Any non-threaded DM is treated as a new task
        return {"type": "task", "content": text}

    def _chunk_message(self, content: str, max_length: int = 3000) -> list:
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
            split_idx = chunk.rfind("\n\n")

            # If no paragraph boundary, try single newline
            if split_idx == -1:
                split_idx = chunk.rfind("\n")

            # If no newline, try sentence boundary
            if split_idx == -1:
                split_idx = max(chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "))
                if split_idx != -1:
                    split_idx += 1  # Include the punctuation

            # If no natural boundary, split at word boundary
            if split_idx == -1:
                split_idx = chunk.rfind(" ")

            # If still no good split point, just cut at max_length
            if split_idx == -1:
                split_idx = max_length

            # Add this chunk
            chunks.append(remaining[:split_idx].strip())
            remaining = remaining[split_idx:].strip()

        # Add chunk indicators if we split the message
        if len(chunks) > 1:
            for i, chunk in enumerate(chunks):
                chunks[i] = f"**(Part {i + 1}/{len(chunks)})**\n\n{chunk}"

        return chunks

    def _write_message(self, msg_type: str, content: str, metadata: dict[str, Any]):
        """Write incoming message to appropriate directory.

        IMPORTANT: Messages include YAML frontmatter with thread_ts for proper
        threading when Claude responds. This ensures all related messages stay
        in the same Slack thread.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Choose directory based on message type
        if msg_type == "response":
            target_dir = self.responses_dir
            # If responding to a specific notification, include that in filename
            if metadata.get("referenced_notification"):
                filename = f"RESPONSE-{metadata['referenced_notification']}.md"
            else:
                filename = f"response-{timestamp}.md"
        else:
            target_dir = self.incoming_dir
            filename = f"task-{timestamp}.md"

        filepath = target_dir / filename

        # Extract task ID for thread tracking
        task_id = filename.replace(".md", "")  # e.g., "task-20251124-112705"

        # Build message document with YAML frontmatter for thread context
        doc_parts = []

        # YAML frontmatter with thread context (CRITICAL for proper threading)
        # This frontmatter is parsed by:
        # 1. incoming-processor.py when creating response notifications
        # 2. host-notify-slack.py when sending notifications back to Slack
        thread_ts = metadata.get("thread_ts")
        referenced_notification = metadata.get("referenced_notification")

        doc_parts.append("---")
        doc_parts.append(f'task_id: "{task_id}"')
        if thread_ts:
            doc_parts.append(f'thread_ts: "{thread_ts}"')
        if referenced_notification:
            doc_parts.append(f'referenced_notification: "{referenced_notification}"')
        doc_parts.append(f'channel: "{metadata.get("channel", "")}"')
        doc_parts.append(f'user_id: "{metadata.get("user_id", "")}"')
        doc_parts.append(f'user_name: "{metadata.get("user_name", "")}"')
        doc_parts.append(f'received: "{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"')
        doc_parts.append("---")
        doc_parts.append("")

        if msg_type == "response":
            doc_parts.append(f"# Response from {metadata.get('user_name', 'User')}")
            if referenced_notification:
                doc_parts.append(f"\n**Re:** Notification `{referenced_notification}`")
        else:
            doc_parts.append(f"# New Task from {metadata.get('user_name', 'User')}")

        doc_parts.append(f"\n**Received:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc_parts.append(f"**User ID:** {metadata.get('user_id', 'unknown')}")
        doc_parts.append(f"**Channel:** {metadata.get('channel', 'unknown')}")

        # Include thread_ts if present (also in body for visibility)
        if thread_ts:
            doc_parts.append(f"**Thread:** {thread_ts}")

        # Include full thread context if available
        if metadata.get("thread_context"):
            doc_parts.append("\n## Thread Context\n")
            doc_parts.append("Full conversation history:\n")
            for i, msg in enumerate(metadata["thread_context"], 1):
                doc_parts.append(f"**{i}. {msg['user']}:**")
                doc_parts.append(f"{msg['text']}\n")

        doc_parts.append("\n## Current Message\n")
        doc_parts.append(content)

        doc_parts.append("\n---")
        doc_parts.append(f"\n*Delivered via Slack → {target_dir.name}/ → Claude*")

        # Write file
        try:
            with open(filepath, "w") as f:
                f.write("\n".join(doc_parts))

            self.logger.info(f"Message written: {filepath}")

            # Save thread_ts mapping for new tasks
            # This allows future notifications to reply in the same thread
            if msg_type == "task" and metadata.get("thread_ts"):
                self.threads[task_id] = metadata["thread_ts"]
                self._save_threads()
                self.logger.info(f"Saved thread mapping: {task_id} → {metadata['thread_ts']}")

            return filepath
        except Exception as e:
            self.logger.error(f"Failed to write message to {filepath}: {e}")
            return None

    def _send_ack(self, channel: str, text: str, thread_ts: str | None = None):
        """Send acknowledgment back to Slack.

        Args:
            channel: Channel ID
            text: Message text
            thread_ts: Thread timestamp (creates threaded reply if provided)
        """
        try:
            # Split into chunks if message is too long
            chunks = self._chunk_message(text)

            # Send each chunk
            for chunk_idx, chunk in enumerate(chunks):
                response = self.web_client.chat_postMessage(
                    channel=channel,
                    text=chunk,
                    thread_ts=thread_ts,  # Post as thread reply if provided
                )

                # For multi-chunk messages, thread subsequent chunks to the first
                if chunk_idx == 0 and not thread_ts and response.get("ok"):
                    # First chunk of a new message - use its ts for subsequent chunks
                    thread_ts = response.get("ts")

                # Small delay between chunks to ensure proper ordering
                if chunk_idx < len(chunks) - 1:
                    import time

                    time.sleep(0.5)

        except Exception as e:
            self.logger.error(f"Failed to send ack: {e}")

    def _trigger_processing(self, filepath: Path):
        """Trigger message processing in jib container via jib --exec."""
        try:
            jib_script = Path.home() / "khan" / "james-in-a-box" / "bin" / "jib"

            # Convert host paths to container paths
            # Host: ~/.jib-sharing/incoming/task.md → Container: ~/sharing/incoming/task.md
            container_message_path = str(filepath).replace(
                str(Path.home() / ".jib-sharing"), f"/home/{os.environ['USER']}/sharing"
            )

            # Container path to processor script (james-in-a-box mounted at ~/khan/james-in-a-box/)
            container_processor = f"/home/{os.environ['USER']}/khan/james-in-a-box/jib-container/jib-tasks/slack/incoming-processor.py"

            self.logger.info(f"Triggering processing for {filepath.name}")

            # Execute in background (non-blocking) in a new ephemeral container
            # IMPORTANT: --exec must be LAST (uses argparse.REMAINDER)
            subprocess.Popen(
                [str(jib_script), "--exec", "python3", container_processor, container_message_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # Detach from parent
            )

            self.logger.info(f"Processing triggered for {filepath.name}")
        except Exception as e:
            self.logger.error(f"Failed to trigger processing: {e}")

    def _get_thread_parent_text(self, channel: str, thread_ts: str) -> str:
        """Fetch the parent message text from a thread."""
        try:
            # Get the parent message
            response = self.web_client.conversations_history(
                channel=channel, latest=thread_ts, inclusive=True, limit=1
            )

            if response["ok"] and response["messages"]:
                return response["messages"][0].get("text", "")
        except Exception as e:
            self.logger.error(f"Failed to fetch thread parent: {e}")

        return ""

    def _get_full_thread_context(self, channel: str, thread_ts: str) -> list:
        """Fetch all messages in a thread for full context.

        Returns list of messages in chronological order (oldest first).
        Each message is a dict with 'user', 'text', 'ts' fields.
        """
        try:
            # Get all replies in the thread
            response = self.web_client.conversations_replies(
                channel=channel,
                ts=thread_ts,
                inclusive=True,  # Include the parent message
                limit=100,  # Should be enough for most threads
            )

            if response["ok"] and response["messages"]:
                messages = []
                for msg in response["messages"]:
                    # Get user name for each message
                    user_id = msg.get("user")
                    if user_id:
                        try:
                            user_info = self.web_client.users_info(user=user_id)
                            user_name = (
                                user_info["user"]["real_name"] if user_info["ok"] else user_id
                            )
                        except:
                            user_name = user_id
                    else:
                        user_name = "Unknown"

                    messages.append(
                        {
                            "user": user_name,
                            "user_id": user_id,
                            "text": msg.get("text", ""),
                            "ts": msg.get("ts", ""),
                        }
                    )

                self.logger.info(f"Fetched {len(messages)} messages from thread {thread_ts}")
                return messages

        except Exception as e:
            self.logger.error(f"Failed to fetch full thread context: {e}")

        return []

    def _process_message(self, event: dict[str, Any]):
        """Process incoming message event."""
        # Extract event data
        user_id = event.get("user")
        channel = event.get("channel")
        text = event.get("text", "")
        message_ts = event.get("ts")  # Timestamp of THIS message
        thread_ts = event.get("thread_ts")  # Present if this is a thread reply

        # For threading: use thread_ts if already in a thread, otherwise use message_ts to start a new thread
        reply_thread_ts = thread_ts or message_ts

        # Ignore messages from the bot itself
        if user_id == self.bot_user_id:
            return

        # Check if user is allowed
        if not self._is_allowed_user(user_id):
            self.logger.warning(f"Blocked message from unauthorized user: {user_id}")
            self._send_ack(
                channel,
                "⚠️ You are not authorized to send messages to Claude.",
                thread_ts=reply_thread_ts,
            )
            return

        # Get user info
        try:
            user_info = self.web_client.users_info(user=user_id)
            user_name = user_info["user"]["real_name"] if user_info["ok"] else "Unknown"
        except:
            user_name = "Unknown"

        self.logger.info(f"Received message from {user_name} ({user_id}): {text[:100]}")
        if thread_ts:
            self.logger.info(f"  (thread reply, thread_ts: {thread_ts})")

        # If this is a thread reply, get full thread context
        referenced_notif = None
        thread_context = None
        if thread_ts:
            # Fetch full thread for context
            thread_context = self._get_full_thread_context(channel, thread_ts)
            if thread_context:
                # Extract notification timestamp from first message in thread
                parent_text = thread_context[0]["text"]
                import re

                timestamp_pattern = r"\b\d{8}-\d{6}\b"
                match = re.search(timestamp_pattern, parent_text)
                if match:
                    referenced_notif = match.group(0)
                    self.logger.info(f"  Extracted notification timestamp: {referenced_notif}")

        # Parse message
        parsed = self._parse_message(text, thread_ts=thread_ts, channel=channel)
        msg_type = parsed["type"]

        # Handle remote control commands
        if msg_type == "command":
            self.logger.info(f"Processing remote control command: {parsed['content']}")

            if self._execute_command(parsed["content"]):
                ack_msg = "🎮 Command dispatched. Check notifications for result."
                self._send_ack(channel, ack_msg, thread_ts=reply_thread_ts)
            else:
                ack_msg = "❌ Failed to execute command. Check logs."
                self._send_ack(channel, ack_msg, thread_ts=reply_thread_ts)

            return  # Don't write commands to disk

        # Override referenced_notification if we extracted it from parent
        if referenced_notif:
            parsed["referenced_notification"] = referenced_notif

        # Write to shared directory
        # IMPORTANT: Use reply_thread_ts (which is thread_ts OR message_ts)
        # This ensures new tasks get the message_ts saved for future thread replies
        metadata = {
            "user_id": user_id,
            "user_name": user_name,
            "channel": channel,
            "referenced_notification": parsed.get("referenced_notification"),
            "thread_ts": reply_thread_ts,  # Use reply_thread_ts, not thread_ts
            "thread_context": thread_context,
        }

        filepath = self._write_message(msg_type, parsed["content"], metadata)

        if filepath:
            # Send acknowledgment
            if msg_type == "response":
                ack_msg = (
                    f"✅ Response received and forwarded to Claude\n📁 Saved to: `{filepath.name}`"
                )
            else:
                ack_msg = f"✅ Task received and queued for Claude\n📁 Saved to: `{filepath.name}`"

            self._send_ack(channel, ack_msg, thread_ts=reply_thread_ts)

            # Trigger processing in jib container
            self._trigger_processing(filepath)
        else:
            self._send_ack(
                channel,
                "❌ Failed to process message. Please check logs.",
                thread_ts=reply_thread_ts,
            )

    def _handle_event(self, client: SocketModeClient, req: SocketModeRequest):
        """Handle incoming Socket Mode events."""
        # Acknowledge the event
        response = SocketModeResponse(envelope_id=req.envelope_id)
        client.send_socket_mode_response(response)

        # Process the event
        if req.type == "events_api":
            event = req.payload.get("event", {})
            event_type = event.get("type")

            if event_type == "message":
                # Check if it's a DM or mentioned message
                channel_type = event.get("channel_type")
                if channel_type == "im":  # Direct message
                    self._process_message(event)
                elif event.get("text", "").find(f"<@{self.bot_user_id}>") != -1:
                    # Bot was mentioned
                    self._process_message(event)

    def start(self):
        """Start listening for Slack messages."""
        self.logger.info(f"Starting Slack receiver (PID: {os.getpid()})")

        # Get bot user ID
        self._get_bot_user_id()

        self.logger.info(f"Incoming messages → {self.incoming_dir}")
        self.logger.info(f"Responses → {self.responses_dir}")

        if self.self_dm_channel:
            self.logger.info(f"Self-DM channel: {self.self_dm_channel}")
        else:
            self.logger.warning("No self-DM channel configured - will not detect 'claude:' tasks")

        if self.owner_user_id:
            self.logger.info(f"Owner user ID: {self.owner_user_id}")

        if self.allowed_users:
            self.logger.info(f"Allowed users: {', '.join(self.allowed_users)}")
        else:
            self.logger.warning("No user whitelist configured - accepting messages from all users")

        # Start Socket Mode client
        try:
            self.socket_client = SocketModeClient(
                app_token=self.app_token, web_client=self.web_client
            )

            self.socket_client.socket_mode_request_listeners.append(self._handle_event)

            self.logger.info("Connected to Slack Socket Mode")
            self.logger.info("Listening for direct messages...")

            # Keep running
            self.socket_client.connect()

            # Wait for shutdown
            while self.running:
                import time

                time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            if self.socket_client:
                self.socket_client.close()
            self.logger.info("Slack receiver stopped")


def main():
    """Main entry point."""
    config_dir = Path.home() / ".config" / "jib-notifier"

    try:
        receiver = SlackReceiver(config_dir)
        receiver.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        logging.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
