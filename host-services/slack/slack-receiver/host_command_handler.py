#!/usr/bin/env python3
"""
Host Command Handler

Handles remote control commands from Slack for managing the jib system.
This script runs on the host machine to control containers and services.

Commands supported:
- jib status/restart/rebuild/logs: Container management
- service list/status/restart/start/stop/logs: Systemd service management
- help: Show available commands

Can be used standalone (CLI) or imported by slack-receiver.py.
"""

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class CommandType(Enum):
    """Types of remote commands."""

    JIB = "jib"
    SERVICE = "service"
    HELP = "help"


@dataclass
class CommandResult:
    """Result of executing a command."""

    success: bool
    message: str
    title: str = "Command Result"


class HostCommandHandler:
    """Handles remote control commands for jib system management."""

    # Container name for jib
    CONTAINER_NAME = "jib-claude"

    def __init__(self, notification_dir: Path | None = None, log_file: Path | None = None):
        """Initialize the command handler.

        Args:
            notification_dir: Directory to write notification files.
                            Defaults to ~/.jib-sharing/notifications
            log_file: Path to log file.
                     Defaults to ~/.config/jib-notifier/remote-control.log
        """
        self.notification_dir = notification_dir or (Path.home() / ".jib-sharing" / "notifications")
        self.log_file = log_file or (
            Path.home() / ".config" / "jib-notifier" / "remote-control.log"
        )

        # Find james-in-a-box root directory
        self.script_dir = Path(__file__).parent.parent.parent.parent
        self.jib_container_dir = self.script_dir / "jib-container"

        # Ensure directories exist (gracefully handle permission errors in container)
        try:
            self.notification_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Running in container without host permissions - use temp dir
            self.notification_dir = Path("/tmp/jib-notifications")
            self.notification_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Running in container without host permissions - use temp file
            self.log_file = Path("/tmp/host-command-handler.log")

        # Set up logging
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging to file and console."""
        self.logger = logging.getLogger("host-command-handler")
        self.logger.setLevel(logging.INFO)

        # Avoid duplicate handlers
        if not self.logger.handlers:
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

    def log(self, message: str):
        """Log a message."""
        self.logger.info(message)

    def notify(self, message: str, title: str = "🎮 Remote Command Result"):
        """Send a notification by writing to the notification directory.

        Args:
            message: The notification message content
            title: Title for the notification
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notification_file = self.notification_dir / f"{timestamp}-remote-command.md"

        content = f"""# {title}

```
{message}
```

Executed at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

        try:
            notification_file.write_text(content)
            self.log(f"Notification sent: {notification_file}")
        except Exception as e:
            self.logger.error(f"Failed to write notification: {e}")

    def _run_command(
        self, cmd: list[str], capture_output: bool = True, timeout: int = 60
    ) -> tuple[int, str, str]:
        """Run a shell command and return exit code, stdout, stderr.

        Args:
            cmd: Command and arguments as a list
            capture_output: Whether to capture stdout/stderr
            timeout: Command timeout in seconds

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", f"Command timed out after {timeout}s"
        except Exception as e:
            return 1, "", str(e)

    def _docker_ps_contains(self, name: str) -> bool:
        """Check if docker ps output contains a container name."""
        code, stdout, _ = self._run_command(["docker", "ps"])
        return code == 0 and name in stdout

    def _docker_ps_all_contains(self, name: str) -> bool:
        """Check if docker ps -a output contains a container name."""
        code, stdout, _ = self._run_command(["docker", "ps", "-a"])
        return code == 0 and name in stdout

    # ========== JIB CONTAINER COMMANDS ==========

    def jib_status(self) -> CommandResult:
        """Check jib container status."""
        self.log("Checking jib container status")

        if self._docker_ps_contains(self.CONTAINER_NAME):
            status = "✅ Running"

            # Get container ID
            code, container_id, _ = self._run_command(
                ["docker", "ps", "--filter", f"name={self.CONTAINER_NAME}", "--format", "{{.ID}}"]
            )
            container_id = container_id.strip() if code == 0 else "N/A"

            # Get uptime
            code, uptime, _ = self._run_command(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"name={self.CONTAINER_NAME}",
                    "--format",
                    "{{.Status}}",
                ]
            )
            uptime = uptime.strip() if code == 0 else "N/A"
        else:
            status = "❌ Not running"
            container_id = "N/A"
            uptime = "N/A"

        message = f"""jib Container Status
Status: {status}
Container ID: {container_id}
Uptime: {uptime}"""

        self.notify(message)
        return CommandResult(success=True, message=message, title="Container Status")

    def jib_restart(self) -> CommandResult:
        """Restart the jib container."""
        self.log("Restarting jib container")

        # Stop existing container
        if self._docker_ps_contains(self.CONTAINER_NAME):
            self.log("Stopping existing container")
            self._run_command(["docker", "stop", self.CONTAINER_NAME])

        # Start new container
        self.log("Starting container")
        jib_script = self.jib_container_dir / "jib"

        if not jib_script.exists():
            message = f"❌ jib script not found: {jib_script}"
            self.notify(message)
            return CommandResult(success=False, message=message)

        # Run in background
        subprocess.Popen(
            [str(jib_script)],
            cwd=str(self.jib_container_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        import time

        time.sleep(3)

        if self._docker_ps_contains(self.CONTAINER_NAME):
            message = "✅ jib container restarted successfully"
            success = True
        else:
            message = "❌ jib container failed to restart\nCheck logs: docker logs jib-claude"
            success = False

        self.notify(message)
        return CommandResult(success=success, message=message)

    def jib_rebuild(self) -> CommandResult:
        """Rebuild and restart the jib container."""
        self.log("Rebuilding jib container")

        # Stop and remove existing container
        if self._docker_ps_all_contains(self.CONTAINER_NAME):
            self.log("Stopping and removing existing container")
            self._run_command(["docker", "stop", self.CONTAINER_NAME])
            self._run_command(["docker", "rm", self.CONTAINER_NAME])

        # Rebuild and start
        self.log("Rebuilding container")
        jib_script = self.jib_container_dir / "jib"

        if not jib_script.exists():
            message = f"❌ jib script not found: {jib_script}"
            self.notify(message)
            return CommandResult(success=False, message=message)

        subprocess.Popen(
            [str(jib_script), "--rebuild"],
            cwd=str(self.jib_container_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        import time

        time.sleep(5)

        if self._docker_ps_contains(self.CONTAINER_NAME):
            message = "✅ jib container rebuilt and started successfully"
            success = True
        else:
            message = "❌ jib container rebuild failed\nCheck logs: docker logs jib-claude"
            success = False

        self.notify(message)
        return CommandResult(success=success, message=message)

    def jib_logs(self, lines: int = 50) -> CommandResult:
        """Fetch recent container logs.

        Args:
            lines: Number of log lines to fetch (default 50)
        """
        self.log("Fetching jib container logs")

        if not self._docker_ps_contains(self.CONTAINER_NAME):
            message = "❌ jib container is not running"
            self.notify(message)
            return CommandResult(success=False, message=message)

        code, logs, stderr = self._run_command(
            ["docker", "logs", "--tail", str(lines), self.CONTAINER_NAME]
        )

        if code != 0:
            message = f"❌ Failed to fetch logs: {stderr}"
        else:
            # Combine stdout and stderr from docker logs
            combined_logs = logs if logs else stderr
            message = f"jib Container Logs (last {lines} lines)\n\n{combined_logs}"

        self.notify(message)
        return CommandResult(success=code == 0, message=message)

    # ========== SERVICE COMMANDS ==========

    def _systemctl_user(self, *args: str) -> tuple[int, str, str]:
        """Run systemctl --user command."""
        return self._run_command(["systemctl", "--user", *args])

    def _is_service_active(self, service_name: str) -> bool:
        """Check if a systemd user service is active."""
        code, _, _ = self._systemctl_user("is-active", "--quiet", service_name)
        return code == 0

    def _is_service_enabled(self, service_name: str) -> bool:
        """Check if a systemd user service is enabled."""
        code, _, _ = self._systemctl_user("is-enabled", "--quiet", service_name)
        return code == 0

    def service_status(self, service_name: str) -> CommandResult:
        """Check status of a systemd user service.

        Args:
            service_name: Name of the service (e.g., "slack-notifier.service")
        """
        self.log(f"Checking status of {service_name}")

        active = "✅ Active" if self._is_service_active(service_name) else "❌ Inactive"
        enabled = "✅ Enabled" if self._is_service_enabled(service_name) else "❌ Disabled"

        _code, status, stderr = self._systemctl_user("status", service_name, "--no-pager")
        # Get last 10 lines of status
        status_lines = (status or stderr).strip().split("\n")[-10:]
        status_output = "\n".join(status_lines)

        message = f"""Service Status: {service_name}

Active: {active}
Enabled: {enabled}

Recent Status:
{status_output}"""

        self.notify(message)
        return CommandResult(success=True, message=message)

    def service_restart(self, service_name: str) -> CommandResult:
        """Restart a systemd user service.

        Args:
            service_name: Name of the service
        """
        self.log(f"Restarting service: {service_name}")

        self._systemctl_user("restart", service_name)

        import time

        time.sleep(2)

        if self._is_service_active(service_name):
            message = f"✅ Service restarted: {service_name}"
            success = True
        else:
            message = f"❌ Service failed to restart: {service_name}\nCheck logs: journalctl --user -u {service_name} -n 50"
            success = False

        self.notify(message)
        return CommandResult(success=success, message=message)

    def service_stop(self, service_name: str) -> CommandResult:
        """Stop a systemd user service.

        Args:
            service_name: Name of the service
        """
        self.log(f"Stopping service: {service_name}")

        self._systemctl_user("stop", service_name)

        message = f"Service stopped: {service_name}"
        self.notify(message)
        return CommandResult(success=True, message=message)

    def service_start(self, service_name: str) -> CommandResult:
        """Start a systemd user service.

        Args:
            service_name: Name of the service
        """
        self.log(f"Starting service: {service_name}")

        self._systemctl_user("start", service_name)

        import time

        time.sleep(2)

        if self._is_service_active(service_name):
            message = f"✅ Service started: {service_name}"
            success = True
        else:
            message = f"❌ Service failed to start: {service_name}\nCheck logs: journalctl --user -u {service_name} -n 50"
            success = False

        self.notify(message)
        return CommandResult(success=success, message=message)

    def service_logs(self, service_name: str, lines: int = 50) -> CommandResult:
        """Fetch logs for a systemd user service.

        Args:
            service_name: Name of the service
            lines: Number of log lines to fetch
        """
        self.log(f"Fetching logs for service: {service_name}")

        code, logs, stderr = self._run_command(
            ["journalctl", "--user", "-u", service_name, "-n", str(lines), "--no-pager"]
        )

        if code != 0:
            message = f"❌ Failed to fetch logs: {stderr}"
        else:
            message = f"Service Logs: {service_name} (last {lines} lines)\n\n{logs}"

        self.notify(message)
        return CommandResult(success=code == 0, message=message)

    def list_services(self) -> CommandResult:
        """List all jib-related services and timers."""
        self.log("Listing jib services")

        # List services
        code, services_raw, _ = self._systemctl_user("list-units", "--type=service,timer", "--all")

        # Filter for jib-related services
        services_lines = []
        timers_lines = []

        if code == 0:
            for line in services_raw.split("\n"):
                if any(
                    pattern in line
                    for pattern in ["slack-", "codebase-", "conversation-", "service-failure"]
                ):
                    if ".timer" in line:
                        timers_lines.append(line)
                    else:
                        services_lines.append(line)

        services = "\n".join(services_lines) if services_lines else "No jib services found"
        timers = "\n".join(timers_lines) if timers_lines else "No timers found"

        message = f"""jib Services and Timers

Services:
{services}

Timers:
{timers}"""

        self.notify(message)
        return CommandResult(success=True, message=message)

    # ========== HELP ==========

    def show_help(self) -> CommandResult:
        """Show available commands."""
        help_text = """jib Remote Control Commands

Container:
  /jib status          - Check container status
  /jib restart         - Restart container
  /jib rebuild         - Rebuild and restart container
  /jib logs            - Show recent container logs

Services:
  /service list                    - List all jib services
  /service status <name>           - Check service status
  /service restart <name>          - Restart a service
  /service start <name>            - Start a service
  /service stop <name>             - Stop a service
  /service logs <name> [lines]     - Show service logs

Examples:
  /jib restart
  /service restart slack-notifier.service
  /service logs slack-receiver.service 100"""

        self.notify(help_text, title="📖 Help")
        return CommandResult(success=True, message=help_text, title="Help")

    # ========== COMMAND ROUTING ==========

    def execute(self, command: str, subcommand: str | None = None, *args: str) -> CommandResult:
        """Execute a remote command.

        Args:
            command: Main command (jib, service, help)
            subcommand: Subcommand (status, restart, etc.)
            *args: Additional arguments

        Returns:
            CommandResult with success status and message
        """
        self.log(f"Remote command received: {command} {subcommand} {' '.join(args)}")

        command = command.lower().lstrip("/")

        if command == "jib":
            subcommand = (subcommand or "").lower()
            if subcommand == "status":
                return self.jib_status()
            elif subcommand == "restart":
                return self.jib_restart()
            elif subcommand == "rebuild":
                return self.jib_rebuild()
            elif subcommand == "logs":
                lines = int(args[0]) if args else 50
                return self.jib_logs(lines)
            else:
                return self.show_help()

        elif command == "service":
            subcommand = (subcommand or "").lower()
            if subcommand == "list":
                return self.list_services()
            elif subcommand == "status" and args:
                return self.service_status(args[0])
            elif subcommand == "restart" and args:
                return self.service_restart(args[0])
            elif subcommand == "start" and args:
                return self.service_start(args[0])
            elif subcommand == "stop" and args:
                return self.service_stop(args[0])
            elif subcommand == "logs" and args:
                lines = int(args[1]) if len(args) > 1 else 50
                return self.service_logs(args[0], lines)
            else:
                return self.show_help()

        elif command in ("help", "commands"):
            return self.show_help()

        else:
            message = f"❌ Unknown command: {command}\n\nSend 'help' for available commands"
            self.notify(message)
            return CommandResult(success=False, message=message)

    def execute_from_text(self, command_text: str) -> CommandResult:
        """Execute a command from raw text (as received from Slack).

        Args:
            command_text: Raw command text (e.g., "/jib restart" or "help")

        Returns:
            CommandResult with success status and message
        """
        parts = command_text.strip().split()

        if not parts:
            return CommandResult(success=False, message="No command provided")

        # Handle "help" command
        if parts[0].lower() in ("help", "/help", "commands"):
            return self.show_help()

        # Remove leading slash if present
        if parts[0].startswith("/"):
            parts[0] = parts[0][1:]

        command = parts[0]
        subcommand = parts[1] if len(parts) > 1 else None
        args = tuple(parts[2:]) if len(parts) > 2 else ()

        return self.execute(command, subcommand, *args)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Host command handler for jib remote control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s jib status
  %(prog)s jib restart
  %(prog)s service list
  %(prog)s service restart slack-notifier.service
  %(prog)s help
        """,
    )

    parser.add_argument("command", help="Main command (jib, service, help)")
    parser.add_argument("subcommand", nargs="?", help="Subcommand")
    parser.add_argument("args", nargs="*", help="Additional arguments")

    args = parser.parse_args()

    handler = HostCommandHandler()
    result = handler.execute(args.command, args.subcommand, *args.args)

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
