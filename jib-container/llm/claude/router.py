"""
Optional helper for managing claude-code-router lifecycle.

The router allows routing Claude Code requests to alternative providers
(OpenAI, Gemini, DeepSeek, etc.) while maintaining Claude Code's tooling.

See: https://github.com/musistudio/claude-code-router
"""

import socket
import subprocess
import time
from pathlib import Path


class RouterManager:
    """Manage claude-code-router lifecycle.

    The router is an optional component that sits between Claude Code
    and the Anthropic API, allowing requests to be routed to alternative
    providers like OpenAI, Gemini, or DeepSeek.

    Example:
        # Manual lifecycle management
        router = RouterManager()
        if router.start():
            try:
                # Use router...
                pass
            finally:
                router.stop()

        # Context manager (recommended)
        with RouterManager() as router:
            if router.is_running():
                # Router is ready
                pass
    """

    def __init__(self, port: int = 3456):
        """Initialize router manager.

        Args:
            port: Port for the router (default: 3456)
        """
        self.port = port
        self.process: subprocess.Popen | None = None

    def is_running(self) -> bool:
        """Check if router is accepting connections.

        Returns:
            True if router is listening on the configured port.
        """
        try:
            with socket.create_connection(("localhost", self.port), timeout=1):
                return True
        except (TimeoutError, ConnectionRefusedError, OSError):
            return False

    def start(self, timeout: float = 3.0) -> bool:
        """Start the router if not already running.

        Requires bun/npm to be installed.

        Args:
            timeout: Maximum seconds to wait for startup

        Returns:
            True if router is running (started or was already running)
        """
        if self.is_running():
            return True

        try:
            self.process = subprocess.Popen(
                ["bunx", "@musistudio/claude-code-router", "start"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            # Try npx as fallback
            try:
                self.process = subprocess.Popen(
                    ["npx", "@musistudio/claude-code-router", "start"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except FileNotFoundError:
                return False

        # Wait for router to be ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_running():
                return True
            time.sleep(0.1)

        return False

    def stop(self) -> None:
        """Stop the router if it was started by this manager."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None

    def __enter__(self) -> "RouterManager":
        """Context manager entry - starts the router."""
        self.start()
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit - stops the router."""
        self.stop()


def get_router_config_path() -> Path:
    """Get the path to the router config file.

    Returns:
        Path to ~/.claude-code-router/config.json
    """
    return Path.home() / ".claude-code-router" / "config.json"


def is_router_configured() -> bool:
    """Check if the router has a configuration file.

    Returns:
        True if config file exists.
    """
    return get_router_config_path().exists()
