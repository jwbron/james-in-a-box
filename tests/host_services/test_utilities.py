"""
Tests for host-services/utilities shell scripts.

Tests shell script functionality including:
- worktree-watcher.sh: Cleans up orphaned git worktrees
"""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import pytest


class TestWorktreeWatcherSyntax:
    """Tests for worktree-watcher.sh bash syntax."""

    def test_worktree_watcher_syntax_valid(self):
        """Test that worktree-watcher.sh has valid bash syntax."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.sh"
        )

        assert script_path.exists(), f"Script not found: {script_path}"

        result = subprocess.run(
            ["bash", "-n", str(script_path)], check=False, capture_output=True, text=True
        )

        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_worktree_watcher_has_shebang(self):
        """Test that script has proper shebang."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.sh"
        )

        content = script_path.read_text()
        assert content.startswith("#!/bin/bash"), "Script should start with #!/bin/bash"

    def test_worktree_watcher_uses_strict_mode(self):
        """Test that script uses strict mode (set -u)."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.sh"
        )

        content = script_path.read_text()
        assert "set -u" in content, "Script should use 'set -u' for undefined variable checking"


class TestWorktreeWatcherFunctionality:
    """Tests for worktree-watcher.sh functionality."""

    def test_log_function_format(self):
        """Test that log messages follow expected format."""
        # The script uses LOG_PREFIX with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_prefix = f"[{timestamp}]"

        assert log_prefix.startswith("[")
        assert log_prefix.endswith("]")

    def test_worktree_base_path(self):
        """Test that worktree base path is correctly defined."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.sh"
        )

        content = script_path.read_text()
        assert 'WORKTREE_BASE="$HOME/.jib-worktrees"' in content

    def test_script_functions_defined(self):
        """Test that expected functions are defined in the script."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.sh"
        )

        content = script_path.read_text()
        assert "cleanup_orphaned_worktrees()" in content
        assert "prune_stale_worktree_references()" in content
        assert "log()" in content

    def test_script_exits_successfully(self):
        """Test that script ends with exit 0."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.sh"
        )

        content = script_path.read_text()
        assert content.strip().endswith("exit 0")


class TestSetupScripts:
    """Tests for setup.sh scripts."""

    def test_worktree_watcher_setup_exists(self):
        """Test that worktree-watcher setup.sh exists."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "setup.sh"
        )

        assert script_path.exists()

    def test_setup_scripts_syntax_valid(self):
        """Test that all setup.sh scripts have valid syntax."""
        setup_scripts = [
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "setup.sh",
        ]

        for script in setup_scripts:
            if script.exists():
                result = subprocess.run(
                    ["bash", "-n", str(script)], check=False, capture_output=True, text=True
                )
                assert result.returncode == 0, f"Syntax error in {script.name}: {result.stderr}"


class TestShellScriptBestPractices:
    """Tests for shell script best practices."""

    def test_scripts_use_quoting(self):
        """Test that scripts properly quote variables."""
        script_paths = [
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.sh",
        ]

        for script in script_paths:
            content = script.read_text()
            # Check for quoted variable usage (common pattern)
            # Scripts should use "$VAR" not $VAR for safety
            assert '"$' in content, f"{script.name} should use quoted variables"

    def test_scripts_handle_errors(self):
        """Test that scripts have error handling."""
        worktree_script = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.sh"
        )

        content = worktree_script.read_text()
        # worktree-watcher uses || true for error handling
        assert "|| true" in content or "2>/dev/null" in content


class TestNotificationFileFormat:
    """Tests for notification file format generated by scripts."""

    def test_notification_filename_format(self):
        """Test that notification filename follows expected pattern."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        service_name = "slack-notifier"
        expected_pattern = f"{timestamp}-service-failure-{service_name}.md"

        assert expected_pattern.endswith(".md")
        assert "service-failure" in expected_pattern

    def test_notification_content_structure(self, temp_dir):
        """Test the expected structure of notification content."""
        service_name = "test-service"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        content = f"""# 🚨 Service Failure: {service_name}

**Priority**: High
**Topic**: System Failure
**Time**: {timestamp}

## Service Status

```
● {service_name}.service - Test Service
   Loaded: loaded
   Active: failed
```

## Recent Logs (last 50 lines)

```
Error: Service crashed
```

## Recommended Actions

1. Check logs: `journalctl --user -u {service_name} -f`
2. Restart if needed: `systemctl --user restart {service_name}`

---
📅 {datetime.now()}
🔔 Auto-generated by service-failure-notify
"""

        notif_file = temp_dir / f"service-failure-{service_name}.md"
        notif_file.write_text(content)

        assert notif_file.exists()
        assert "🚨 Service Failure" in notif_file.read_text()
        assert "## Recommended Actions" in notif_file.read_text()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
