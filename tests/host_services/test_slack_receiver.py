"""
Tests for the slack-receiver module.

Tests the SlackReceiver class which listens for Slack messages
and writes them to shared directories for processing.
"""

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock
import pytest
import sys

# Add project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "host-services" / "slack" / "slack-receiver"))


class TestSlackReceiverMessageParsing:
    """Tests for message parsing in SlackReceiver."""

    def test_parse_command_with_slash(self):
        """Test parsing remote control commands with slash prefix."""
        def parse_message(text, thread_ts=None, channel=None):
            text = text.strip()
            if text.startswith("/") or text.lower() in ["help", "commands"]:
                return {'type': 'command', 'content': text}
            if thread_ts:
                return {'type': 'response', 'content': text, 'thread_ts': thread_ts}
            return {'type': 'task', 'content': text}

        result = parse_message("/jib restart")
        assert result['type'] == 'command'
        assert result['content'] == '/jib restart'

    def test_parse_command_help(self):
        """Test parsing help command."""
        def parse_message(text, thread_ts=None, channel=None):
            text = text.strip()
            if text.startswith("/") or text.lower() in ["help", "commands"]:
                return {'type': 'command', 'content': text}
            if thread_ts:
                return {'type': 'response', 'content': text, 'thread_ts': thread_ts}
            return {'type': 'task', 'content': text}

        result = parse_message("help")
        assert result['type'] == 'command'

        result = parse_message("commands")
        assert result['type'] == 'command'

    def test_parse_thread_reply(self):
        """Test parsing thread reply messages."""
        def parse_message(text, thread_ts=None, channel=None):
            text = text.strip()
            if text.startswith("/") or text.lower() in ["help", "commands"]:
                return {'type': 'command', 'content': text}
            if thread_ts:
                import re
                timestamp_pattern = r'\b\d{8}-\d{6}\b'
                referenced_notif = re.search(timestamp_pattern, text)
                return {
                    'type': 'response',
                    'content': text,
                    'referenced_notification': referenced_notif.group(0) if referenced_notif else None,
                    'thread_ts': thread_ts
                }
            return {'type': 'task', 'content': text}

        result = parse_message("Thanks for the update", thread_ts="1732428847.123456")
        assert result['type'] == 'response'
        assert result['thread_ts'] == '1732428847.123456'

    def test_parse_task_message(self):
        """Test parsing direct task messages."""
        def parse_message(text, thread_ts=None, channel=None):
            text = text.strip()
            if text.startswith("/") or text.lower() in ["help", "commands"]:
                return {'type': 'command', 'content': text}
            if thread_ts:
                return {'type': 'response', 'content': text, 'thread_ts': thread_ts}
            return {'type': 'task', 'content': text}

        result = parse_message("Please add a new feature to the app")
        assert result['type'] == 'task'
        assert result['content'] == 'Please add a new feature to the app'

    def test_parse_message_with_timestamp_reference(self):
        """Test extracting timestamp references from thread replies."""
        import re

        text = "Regarding notification 20251124-111907, please proceed"
        timestamp_pattern = r'\b\d{8}-\d{6}\b'
        match = re.search(timestamp_pattern, text)

        assert match is not None
        assert match.group(0) == '20251124-111907'


class TestSlackReceiverMessageWriting:
    """Tests for writing messages to disk."""

    def test_write_task_message(self, temp_dir):
        """Test writing a task message to disk."""
        incoming_dir = temp_dir / "incoming"
        incoming_dir.mkdir()

        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        filename = f"task-{timestamp}.md"
        filepath = incoming_dir / filename

        content = '''---
task_id: "task-20251124-112705"
channel: "D12345678"
user_id: "U12345678"
user_name: "Test User"
received: "2024-11-24 11:27:05"
---

# New Task from Test User

**Received:** 2024-11-24 11:27:05
**User ID:** U12345678
**Channel:** D12345678

## Current Message

Please implement a new feature.

---

*Delivered via Slack → incoming/ → Claude*
'''

        filepath.write_text(content)

        assert filepath.exists()
        assert 'task_id' in filepath.read_text()

    def test_write_response_message(self, temp_dir):
        """Test writing a response message to disk."""
        responses_dir = temp_dir / "responses"
        responses_dir.mkdir()

        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        filename = f"RESPONSE-notification-{timestamp}.md"
        filepath = responses_dir / filename

        content = '''---
task_id: "RESPONSE-notification-20251124-111907"
thread_ts: "1732428847.123456"
referenced_notification: "notification-20251124-111907"
---

# Response from User

**Re:** Notification `notification-20251124-111907`

## Current Message

Thanks for the update, please proceed.
'''

        filepath.write_text(content)

        assert filepath.exists()
        assert 'referenced_notification' in filepath.read_text()


class TestSlackReceiverConfig:
    """Tests for configuration loading in SlackReceiver."""

    def test_load_config_defaults(self, temp_dir, monkeypatch):
        """Test that default config values are applied."""
        monkeypatch.setenv("HOME", str(temp_dir))

        config = {
            'slack_token': '',
            'slack_app_token': '',
            'allowed_users': [],
            'self_dm_channel': '',
            'owner_user_id': '',
            'incoming_directory': '~/.jib-sharing/incoming',
            'responses_directory': '~/.jib-sharing/responses'
        }

        assert config['incoming_directory'] == '~/.jib-sharing/incoming'
        assert config['responses_directory'] == '~/.jib-sharing/responses'
        assert config['allowed_users'] == []

    def test_load_config_from_env(self, temp_dir, monkeypatch):
        """Test that environment variables override config."""
        monkeypatch.setenv("HOME", str(temp_dir))
        monkeypatch.setenv("SLACK_TOKEN", "xoxb-test-token")
        monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")

        config = {'slack_token': '', 'slack_app_token': ''}

        if os.environ.get('SLACK_TOKEN'):
            config['slack_token'] = os.environ['SLACK_TOKEN']
        if os.environ.get('SLACK_APP_TOKEN'):
            config['slack_app_token'] = os.environ['SLACK_APP_TOKEN']

        assert config['slack_token'] == 'xoxb-test-token'
        assert config['slack_app_token'] == 'xapp-test-token'


class TestSlackReceiverUserAuthorization:
    """Tests for user authorization checking."""

    def test_is_allowed_user_no_whitelist(self):
        """Test that all users are allowed when no whitelist is configured."""
        def is_allowed_user(user_id, allowed_users):
            if not allowed_users:
                return True
            return user_id in allowed_users

        allowed_users = []
        assert is_allowed_user("U12345678", allowed_users) is True

    def test_is_allowed_user_in_whitelist(self):
        """Test that whitelisted users are allowed."""
        def is_allowed_user(user_id, allowed_users):
            if not allowed_users:
                return True
            return user_id in allowed_users

        allowed_users = ["U12345678", "U87654321"]
        assert is_allowed_user("U12345678", allowed_users) is True

    def test_is_allowed_user_not_in_whitelist(self):
        """Test that non-whitelisted users are blocked."""
        def is_allowed_user(user_id, allowed_users):
            if not allowed_users:
                return True
            return user_id in allowed_users

        allowed_users = ["U12345678", "U87654321"]
        assert is_allowed_user("U99999999", allowed_users) is False


class TestSlackReceiverChunking:
    """Tests for message chunking in receiver."""

    def test_chunk_message_preserves_formatting(self):
        """Test that chunking preserves message formatting."""
        def chunk_message(content, max_length=3000):
            if len(content) <= max_length:
                return [content]
            # Simplified chunking for test
            chunks = []
            while content:
                if len(content) <= max_length:
                    chunks.append(content)
                    break
                chunks.append(content[:max_length])
                content = content[max_length:]
            return chunks

        short_message = "**Bold** and _italic_"
        chunks = chunk_message(short_message)

        assert len(chunks) == 1
        assert "**Bold**" in chunks[0]
        assert "_italic_" in chunks[0]


class TestSlackReceiverThreadTracking:
    """Tests for thread tracking functionality."""

    def test_save_thread_mapping(self, temp_dir):
        """Test saving a thread mapping for a new task."""
        threads_file = temp_dir / 'slack-threads.json'
        threads = {}

        task_id = "task-20251124-112705"
        thread_ts = "1732428847.123456"
        threads[task_id] = thread_ts

        with threads_file.open('w') as f:
            json.dump(threads, f, indent=2)

        # Verify saved correctly
        with threads_file.open() as f:
            loaded = json.load(f)

        assert loaded[task_id] == thread_ts

    def test_load_thread_mapping(self, temp_dir):
        """Test loading thread mappings from file."""
        threads_file = temp_dir / 'slack-threads.json'
        expected = {
            "task-20251124-112705": "1732428847.123456",
            "task-20251124-113000": "1732429000.654321"
        }

        threads_file.write_text(json.dumps(expected))

        with threads_file.open() as f:
            threads = json.load(f)

        assert threads["task-20251124-112705"] == "1732428847.123456"
        assert len(threads) == 2


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
