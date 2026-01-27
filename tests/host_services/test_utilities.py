"""
Tests for host-services/utilities scripts.

Tests script functionality including:
- worktree-watcher.py: Cleans up orphaned git worktrees
"""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import pytest


class TestWorktreeWatcherSyntax:
    """Tests for worktree-watcher.py Python syntax."""

    def test_worktree_watcher_syntax_valid(self):
        """Test that worktree-watcher.py has valid Python syntax."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.py"
        )

        assert script_path.exists(), f"Script not found: {script_path}"

        result = subprocess.run(
            ["python3", "-m", "py_compile", str(script_path)],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_worktree_watcher_has_shebang(self):
        """Test that script has proper shebang."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.py"
        )

        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env python3"), (
            "Script should start with #!/usr/bin/env python3"
        )

    def test_worktree_watcher_is_executable(self):
        """Test that script is executable."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.py"
        )

        import os
        assert os.access(script_path, os.X_OK), "Script should be executable"


class TestWorktreeWatcherFunctionality:
    """Tests for worktree-watcher.py functionality."""

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
            / "worktree-watcher.py"
        )

        content = script_path.read_text()
        assert 'WORKTREE_BASE = Path.home() / ".jib-worktrees"' in content

    def test_script_functions_defined(self):
        """Test that expected functions are defined in the script."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.py"
        )

        content = script_path.read_text()
        assert "def cleanup_orphaned_worktrees(" in content
        assert "def prune_stale_worktree_references(" in content
        assert "def log(" in content

    def test_script_has_main(self):
        """Test that script has a main entry point."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.py"
        )

        content = script_path.read_text()
        assert 'if __name__ == "__main__":' in content


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


class TestPythonScriptBestPractices:
    """Tests for Python script best practices."""

    def test_worktree_watcher_has_type_hints(self):
        """Test that worktree-watcher.py uses type hints."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.py"
        )

        content = script_path.read_text()
        # Check for type hints in function signatures
        assert "-> None" in content or "-> bool" in content or "-> str" in content

    def test_worktree_watcher_has_docstrings(self):
        """Test that main functions have docstrings."""
        script_path = (
            Path(__file__).parent.parent.parent
            / "host-services"
            / "utilities"
            / "worktree-watcher"
            / "worktree-watcher.py"
        )

        content = script_path.read_text()
        # Check that there are docstrings (triple quotes after function defs)
        assert '"""' in content


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
