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
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


# Add shared directories to path:
# - host-services/shared for jib_exec (used by message_categorizer)
# - repo root shared for jib_logging and jib_config (common utilities)
_host_services = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_host_services / "shared"))
sys.path.insert(0, str(_host_services.parent / "shared"))
from host_command_handler import HostCommandHandler
from jib_config import SlackConfig
from jib_config.utils import load_yaml_file
from jib_logging import get_logger

# Import message categorizer and host command handler
from message_categorizer import CategorizationResult, MessageCategorizer, MessageCategory


# Check for required dependencies
try:
    from slack_sdk import WebClient
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
except ImportError:
    print("Error: slack_sdk module not found.", file=sys.stderr)
    print("Run 'uv sync' from host-services/ or run setup.sh", file=sys.stderr)
    sys.exit(1)


class SlackReceiver:
    """Receives Slack messages and writes them to shared directory."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_file = config_dir / "config.json"
        # Store threads in shared directory (accessible to both host and container)
        # Host: ~/.jib-sharing/tracking/ -> Container: ~/sharing/tracking/
        self.threads_file = Path.home() / ".jib-sharing" / "tracking" / "slack-threads.json"

        # Ensure config directory exists with secure permissions
        self.config_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.config_dir, 0o700)

        # Initialize jib_logging logger
        self.logger = get_logger("slack-receiver")

        # Load and validate Slack configuration using unified config framework
        self.slack_config = SlackConfig.from_env()
        validation = self.slack_config.validate()
        if not validation.is_valid:
            for error in validation.errors:
                self.logger.error("Configuration error", error=error)
            raise ValueError(f"Invalid Slack configuration: {validation.errors}")
        for warning in validation.warnings:
            self.logger.warning("Configuration warning", warning=warning)

        # Load thread state
        self.threads = self._load_threads()

        # Extract config values
        self.bot_token = self.slack_config.bot_token
        self.app_token = self.slack_config.app_token

        if not self.app_token:
            self.logger.error("SLACK_APP_TOKEN not configured")
            raise ValueError("SLACK_APP_TOKEN not found in config (required for Socket Mode)")

        # Configuration from SlackConfig
        self.allowed_users = self.slack_config.allowed_users
        self.self_dm_channel = self.slack_config.self_dm_channel
        self.owner_user_id = self.slack_config.owner_user_id
        self.bot_user_id = None

        # Load service-specific settings from config.yaml
        service_config = self._load_service_config()
        self.incoming_dir = Path(
            service_config.get("incoming_directory", "~/.jib-sharing/incoming")
        ).expanduser()
        self.responses_dir = Path(
            service_config.get("responses_directory", "~/.jib-sharing/responses")
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

        # Initialize message categorizer for LLM-based message routing
        # Uses ANTHROPIC_API_KEY from environment if available
        self.categorizer = MessageCategorizer()

        # Initialize host command handler for executing host functions
        self.command_handler = HostCommandHandler()

    def _load_service_config(self) -> dict:
        """Load service-specific configuration from ~/.config/jib/config.yaml.

        Returns settings specific to slack-receiver that aren't part of SlackConfig:
        - incoming_directory: Directory for incoming task files
        - responses_directory: Directory for response files
        """
        config_file = Path.home() / ".config" / "jib" / "config.yaml"
        yaml_config = load_yaml_file(config_file)
        return yaml_config

    def _save_config(self, config: dict):
        """Save configuration to file with secure permissions."""
        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2)
        os.chmod(self.config_file, 0o600)
        self.logger.info("Configuration saved", file=str(self.config_file))

    def _load_threads(self) -> dict:
        """Load thread state mapping task IDs to Slack thread_ts."""
        if self.threads_file.exists():
            try:
                with open(self.threads_file) as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error("Failed to load threads file", error=str(e))
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
            self.logger.error("Failed to save threads file", error=str(e))

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info("Received shutdown signal", signal=signum)
        self.running = False
        if self.socket_client:
            self.socket_client.close()

    def _get_bot_user_id(self):
        """Get the bot's user ID."""
        try:
            response = self.web_client.auth_test()
            if response["ok"]:
                self.bot_user_id = response["user_id"]
                self.logger.info("Bot user ID retrieved", bot_user_id=self.bot_user_id)
            else:
                self.logger.error("Failed to get bot user ID")
        except Exception as e:
            self.logger.error("Exception getting bot user ID", error=str(e))

    def _is_allowed_user(self, user_id: str) -> bool:
        """Check if user is allowed to send messages."""
        # If no allowed_users configured, allow all
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users

    def _execute_command(self, command_text: str) -> bool:
        """
        Execute remote control command using the HostCommandHandler.

        Returns True if command was executed, False otherwise.
        """
        try:
            self.logger.info("Executing remote command", command=command_text)

            # Execute in a separate thread to avoid blocking
            # Use self.command_handler which is initialized in __init__
            def run_command():
                try:
                    self.command_handler.execute_from_text(command_text)
                except Exception as e:
                    self.logger.error("Command execution failed", error=str(e))

            thread = threading.Thread(target=run_command, daemon=True)
            thread.start()

            self.logger.info("Command dispatched successfully")
            return True

        except Exception as e:
            self.logger.error("Failed to execute command", error=str(e), command=command_text)
            return False

    def _execute_command_shell(self, command_text: str) -> bool:
        """
        Fallback: Execute remote control command via shell script.

        Returns True if command was executed, False otherwise.
        """
        # Path to remote control script
        script_dir = Path(__file__).parent
        remote_control = script_dir / "remote-control.sh"

        if not remote_control.exists():
            self.logger.error("Remote control script not found", script=str(remote_control))
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
            self.logger.info("Executing remote command via shell fallback", command_parts=parts)

            # Run command in background
            subprocess.Popen(
                [str(remote_control)] + parts,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # Detach from parent
            )

            self.logger.info("Shell command dispatched successfully")
            return True

        except Exception as e:
            self.logger.error("Failed to execute shell command", error=str(e))
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
        # Message content directly after frontmatter (metadata is in frontmatter)
        doc_parts.append(content)

        # Write file
        try:
            with open(filepath, "w") as f:
                f.write("\n".join(doc_parts))

            self.logger.info("Message written", file=str(filepath))

            # Save thread_ts mapping for new tasks
            # This allows future notifications to reply in the same thread
            if msg_type == "task" and metadata.get("thread_ts"):
                self.threads[task_id] = metadata["thread_ts"]
                self._save_threads()
                self.logger.info(
                    "Saved thread mapping", task_id=task_id, thread_ts=metadata["thread_ts"]
                )

            return filepath
        except Exception as e:
            self.logger.error("Failed to write message", file=str(filepath), error=str(e))
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
            self.logger.error("Failed to send acknowledgment", error=str(e))

    def _build_workflow_context(self, categorization: CategorizationResult) -> str:
        """Build a human-readable workflow context string from categorization.

        This provides the user with visibility into how their message was
        interpreted and what workflow will be triggered.

        Args:
            categorization: The result from MessageCategorizer

        Returns:
            Formatted string describing the workflow, ending with newline if non-empty
        """
        category = categorization.category
        reasoning = categorization.reasoning

        # Map categories to user-friendly descriptions
        category_descriptions = {
            MessageCategory.CONTAINER_TASK: "🤖 *Workflow:* General development task",
            MessageCategory.RESPONSE: "💬 *Workflow:* Continuing conversation",
            MessageCategory.HOST_FUNCTION: f"⚡ *Workflow:* Host function `{categorization.function_name}`",
            MessageCategory.COMMAND: "🎮 *Workflow:* Command execution",
            MessageCategory.UNKNOWN: "❓ *Workflow:* Unknown (defaulting to task)",
        }

        workflow_desc = category_descriptions.get(category, f"📋 *Workflow:* {category.value}")

        # Add reasoning if available and confidence is less than 100%
        if reasoning and categorization.confidence < 1.0:
            # Truncate reasoning if too long
            short_reasoning = reasoning[:80] + "..." if len(reasoning) > 80 else reasoning
            return f"{workflow_desc}\n💡 _{short_reasoning}_\n"

        return f"{workflow_desc}\n"

    def _create_failure_notification(
        self,
        task_id: str,
        thread_ts: str | None,
        error_message: str,
        stderr_output: str = "",
    ):
        """Create a notification file for container startup failures.

        This runs on the HOST side, so we write directly to ~/.jib-sharing/notifications/
        which the slack-notifier service monitors.

        Args:
            task_id: Task ID for filename and identification
            thread_ts: Slack thread timestamp for threading (if available)
            error_message: Description of what went wrong
            stderr_output: Captured stderr from the failed process
        """
        notifications_dir = Path.home() / ".jib-sharing" / "notifications"
        notifications_dir.mkdir(parents=True, exist_ok=True)

        # Build notification with YAML frontmatter for proper threading
        frontmatter_lines = [
            "---",
            f'task_id: "{task_id}"',
        ]
        if thread_ts:
            frontmatter_lines.append(f'thread_ts: "{thread_ts}"')
        frontmatter_lines.append("---")
        frontmatter_lines.append("")

        frontmatter = "\n".join(frontmatter_lines)

        # Truncate stderr if too long
        stderr_preview = stderr_output[:1000] if stderr_output else "None captured"

        notification_content = f"""{frontmatter}# Container Startup Failed

**Task ID:** `{task_id}`
**Status:** Failed to start container

## Error Details

{error_message}

**Stderr output:**
```
{stderr_preview}
```

## What you can do

- Check if Docker is running: `docker ps`
- Check jib logs: `journalctl -u jib-services -n 50`
- Try running manually: `jib --exec echo "test"`
- Check for container build issues

---
*Generated by slack-receiver (host-side failure notification)*
"""

        notification_file = notifications_dir / f"{task_id}-startup-failed.md"
        try:
            notification_file.write_text(notification_content)
            self.logger.info(
                "Created failure notification",
                file=notification_file.name,
                thread_ts=thread_ts or None,
            )
        except Exception as e:
            self.logger.error("Failed to write failure notification", error=str(e))

    def _monitor_container_process(
        self,
        process: subprocess.Popen,
        task_id: str,
        thread_ts: str | None,
        filepath: Path,
        log_file: Path,
    ):
        """Monitor a container process in a background thread and notify on failure.

        This runs in a separate thread to avoid blocking the main event loop.
        Streams stdout to log_file in real-time for visibility.
        If the process exits with a non-zero code, creates a failure notification.

        Args:
            process: The Popen process object to monitor
            task_id: Task ID for notifications
            thread_ts: Slack thread timestamp for threading
            filepath: Original message file path
            log_file: Path to write real-time Claude output
        """
        stderr_lines = []
        timeout_seconds = 45 * 60

        try:
            # Stream both stdout and stderr to log file in real-time
            self.logger.info(
                "Streaming container output",
                log_file=str(log_file),
                task_id=task_id,
            )

            with open(log_file, "w") as f:
                f.write(f"=== Container output for {task_id} ===\n")
                f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
                f.flush()

                # Thread to read stderr and stream to log file
                def read_stderr():
                    if process.stderr:
                        for line in process.stderr:
                            stderr_lines.append(line)
                            # Stream stderr to log file too (prefixed for clarity)
                            f.write(f"[stderr] {line}")
                            f.flush()

                stderr_thread = threading.Thread(target=read_stderr, daemon=True)
                stderr_thread.start()

                if process.stdout:
                    for line in process.stdout:
                        # Write to log file immediately (real-time streaming)
                        f.write(line)
                        f.flush()

                # Wait for process to complete
                process.wait(timeout=timeout_seconds)

                # Wait for stderr thread to finish
                stderr_thread.join(timeout=5)

                f.write("\n" + "=" * 50 + "\n")
                f.write(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Exit code: {process.returncode}\n")
                f.flush()

            stderr_str = "".join(stderr_lines)

            if process.returncode != 0:
                self.logger.error(
                    "Container process failed",
                    file=filepath.name,
                    return_code=process.returncode,
                    stderr_preview=stderr_str[:200] if stderr_str else None,
                )

                # Create a failure notification
                error_msg = f"Container exited with code {process.returncode}"
                if "error" in stderr_str.lower() or "failed" in stderr_str.lower():
                    # Extract the most relevant error line
                    for line in stderr_str.split("\n"):
                        if "error" in line.lower() or "failed" in line.lower():
                            error_msg = f"{error_msg}\n\n**Key error:** {line.strip()}"
                            break

                self._create_failure_notification(
                    task_id=task_id,
                    thread_ts=thread_ts,
                    error_message=error_msg,
                    stderr_output=stderr_str,
                )
            else:
                self.logger.info(
                    "Container process completed successfully",
                    file=filepath.name,
                    log_file=str(log_file),
                )

        except subprocess.TimeoutExpired:
            self.logger.error(
                "Container process timed out",
                file=filepath.name,
                timeout_minutes=timeout_seconds // 60,
            )
            process.kill()
            stderr_str = "".join(stderr_lines)

            self._create_failure_notification(
                task_id=task_id,
                thread_ts=thread_ts,
                error_message=f"Container timed out after {timeout_seconds // 60} minutes",
                stderr_output=stderr_str,
            )

        except Exception as e:
            self.logger.error(
                "Error monitoring container process",
                file=filepath.name,
                error=str(e),
            )
            self._create_failure_notification(
                task_id=task_id,
                thread_ts=thread_ts,
                error_message=f"Monitor error: {e!s}",
                stderr_output="",
            )

    def _trigger_processing(self, filepath: Path, task_id: str, thread_ts: str | None):
        """Trigger message processing in jib container via jib --exec.

        Claude output is streamed to a log file at ~/.jib-sharing/logs/{task_id}.log
        You can tail this file to see Claude's output in real-time:
            tail -f ~/.jib-sharing/logs/{task_id}.log

        Args:
            filepath: Path to the message file
            task_id: Task ID for tracking and notifications
            thread_ts: Slack thread timestamp for threading (if available)
        """
        try:
            jib_script = Path.home() / "khan" / "james-in-a-box" / "bin" / "jib"

            # Convert host paths to container paths
            # Host: ~/.jib-sharing/incoming/task.md → Container: ~/sharing/incoming/task.md
            container_message_path = str(filepath).replace(
                str(Path.home() / ".jib-sharing"), f"/home/{os.environ['USER']}/sharing"
            )

            # Create log file for streaming Claude output
            logs_dir = Path.home() / ".jib-sharing" / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_file = logs_dir / f"{task_id}.log"

            self.logger.info(
                "Triggering processing",
                file=filepath.name,
                task_id=task_id,
                log_file=str(log_file),
            )

            # Execute in background but stream output to log file
            # Use text=True for string output instead of bytes
            # incoming-processor is in PATH inside the container via /opt/jib-runtime/bin
            process = subprocess.Popen(
                [str(jib_script), "--exec", "incoming-processor", container_message_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,  # Text mode for string output
                start_new_session=True,  # Detach from parent
            )

            self.logger.info(
                "Processing triggered - stream to log file",
                file=filepath.name,
                pid=process.pid,
                log_file=str(log_file),
            )

            # Start a background thread to monitor the process and stream output
            # This allows us to detect failures, send notifications, and stream Claude logs
            monitor_thread = threading.Thread(
                target=self._monitor_container_process,
                args=(process, task_id, thread_ts, filepath, log_file),
                daemon=True,  # Don't block shutdown
            )
            monitor_thread.start()

        except Exception as e:
            self.logger.error("Failed to trigger processing", error=str(e), file=filepath.name)
            # Even if we can't start the process, notify the user
            self._create_failure_notification(
                task_id=task_id,
                thread_ts=thread_ts,
                error_message=f"Failed to start container: {e!s}",
                stderr_output="",
            )

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
            self.logger.warning("Blocked message from unauthorized user", user_id=user_id)
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

        # Ignore empty or whitespace-only messages
        if not text.strip():
            self.logger.info(
                "Ignoring empty message",
                user_name=user_name,
                user_id=user_id,
                thread_ts=thread_ts or None,
            )
            return

        self.logger.info(
            "Received message",
            user_name=user_name,
            user_id=user_id,
            preview=text[:100],
            thread_ts=thread_ts or None,
        )

        # If this is a thread reply, extract notification timestamp if present
        # We don't fetch the full thread here - Claude can look it up from files if needed
        referenced_notif = None
        if thread_ts:
            # Try to extract notification timestamp from the current message
            import re

            timestamp_pattern = r"\b\d{8}-\d{6}\b"
            match = re.search(timestamp_pattern, text)
            if match:
                referenced_notif = match.group(0)
                self.logger.info(
                    "Extracted notification timestamp", referenced_notif=referenced_notif
                )

        # Use LLM-based categorization to determine message type and routing
        # This enables natural language commands like "run beads analyzer" or "check container status"
        is_thread_reply = thread_ts is not None
        categorization = self.categorizer.categorize(text, is_thread_reply=is_thread_reply)

        self.logger.info(
            "Message categorized",
            category=categorization.category.value,
            function=categorization.function_name,
            confidence=categorization.confidence,
            reasoning=categorization.reasoning[:100] if categorization.reasoning else None,
        )

        # Handle based on category
        if categorization.category == MessageCategory.COMMAND:
            # Explicit slash commands (e.g., /jib, /service, help)
            self.logger.info("Processing explicit command", command=text)

            if self._execute_command(text):
                ack_msg = "🎮 Command dispatched. Check notifications for result."
                self._send_ack(channel, ack_msg, thread_ts=reply_thread_ts)
            else:
                ack_msg = "❌ Failed to execute command. Check logs."
                self._send_ack(channel, ack_msg, thread_ts=reply_thread_ts)

            return  # Commands are executed immediately, not written to disk

        elif categorization.category == MessageCategory.HOST_FUNCTION:
            # Natural language request for a host function (e.g., "run beads analyzer")
            # Execute immediately on the host without spinning up a container
            self.logger.info(
                "Executing host function",
                function=categorization.function_name,
                parameters=categorization.parameters,
            )

            # Send acknowledgment that we're processing
            self._send_ack(
                channel,
                f"🔧 Executing `{categorization.function_name}`...\n"
                f"_Confidence: {categorization.confidence:.0%}_",
                thread_ts=reply_thread_ts,
            )

            # Execute the function
            try:
                result = self.command_handler.execute_function(
                    categorization.function_name,
                    categorization.parameters,
                )
                if result.success:
                    self.logger.info(
                        "Host function completed successfully",
                        function=categorization.function_name,
                    )
                else:
                    self.logger.warning(
                        "Host function failed",
                        function=categorization.function_name,
                        message=result.message[:200] if result.message else None,
                    )
            except Exception as e:
                self.logger.error(
                    "Host function execution error",
                    function=categorization.function_name,
                    error=str(e),
                )
                self._send_ack(
                    channel,
                    f"❌ Error executing `{categorization.function_name}`: {e}",
                    thread_ts=reply_thread_ts,
                )

            return  # Host functions don't need container processing

        elif categorization.category == MessageCategory.RESPONSE:
            # Response to a previous notification thread
            msg_type = "response"
            parsed_content = text
        else:
            # Container task or unknown - send to Claude in container
            msg_type = "task"
            parsed_content = text

        # Build metadata for the message file
        metadata = {
            "user_id": user_id,
            "user_name": user_name,
            "channel": channel,
            "referenced_notification": referenced_notif,
            "thread_ts": reply_thread_ts,
            "categorization": categorization.to_dict(),  # Include categorization info
        }

        # Write to shared directory for container processing
        filepath = self._write_message(msg_type, parsed_content, metadata)

        if filepath:
            task_id = filepath.stem
            log_file_path = f"~/.jib-sharing/logs/{task_id}.log"

            # Build workflow context from categorization
            workflow_context = self._build_workflow_context(categorization)

            if msg_type == "response":
                ack_msg = (
                    f"✅ Response received and forwarded to Claude\n"
                    f"{workflow_context}"
                    f"📁 Saved to: `{filepath.name}`\n"
                    f"📋 Stream logs: `tail -f {log_file_path}`"
                )
            else:
                ack_msg = (
                    f"✅ Task received and queued for Claude\n"
                    f"{workflow_context}"
                    f"📁 Saved to: `{filepath.name}`\n"
                    f"📋 Stream logs: `tail -f {log_file_path}`"
                )

            self._send_ack(channel, ack_msg, thread_ts=reply_thread_ts)

            # Trigger processing in jib container
            self._trigger_processing(filepath, task_id=task_id, thread_ts=reply_thread_ts)
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
        self.logger.info("Starting Slack receiver", pid=os.getpid())

        # Get bot user ID
        self._get_bot_user_id()

        self.logger.info(
            "Directories configured",
            incoming_dir=str(self.incoming_dir),
            responses_dir=str(self.responses_dir),
        )

        if self.self_dm_channel:
            self.logger.info("Self-DM channel configured", channel=self.self_dm_channel)
        else:
            self.logger.warning("No self-DM channel configured - will not detect 'claude:' tasks")

        if self.owner_user_id:
            self.logger.info("Owner user ID configured", owner_user_id=self.owner_user_id)

        if self.allowed_users:
            self.logger.info("Allowed users configured", allowed_users=self.allowed_users)
        else:
            self.logger.warning("No user whitelist configured - accepting messages from all users")

        # Start Socket Mode client
        try:
            self.socket_client = SocketModeClient(
                app_token=self.app_token, web_client=self.web_client
            )

            self.socket_client.socket_mode_request_listeners.append(self._handle_event)

            self.logger.info("Connected to Slack Socket Mode, listening for direct messages")

            # Keep running
            self.socket_client.connect()

            # Wait for shutdown
            while self.running:
                import time

                time.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e:
            self.logger.error("Fatal error", error=str(e))
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
        sys.exit(1)


if __name__ == "__main__":
    main()
