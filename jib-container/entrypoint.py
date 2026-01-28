#!/usr/bin/env python3
"""
Jib Container Entrypoint

Sets up the sandboxed container environment for the autonomous AI agent.
Handles user setup, git configuration, service initialization, and launches
the appropriate LLM interface.

Converted from entrypoint.sh for better maintainability.
"""

# Capture container start time FIRST - before any other imports
# This measures from the moment Python starts executing this file
import time


_CONTAINER_START_TIME = time.time()

# Now import everything else
import contextlib
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar


# =============================================================================
# Startup Timing (Debug)
# =============================================================================

# Enabled via JIB_TIMING=1 env var (set by `jib --time` on host)
ENABLE_STARTUP_TIMING = os.environ.get("JIB_TIMING", "0") == "1"


class StartupTimer:
    """Collects timing data for startup phases."""

    def __init__(self):
        self.timings: list[tuple[str, float]] = []
        self.start_time: float = time.perf_counter()
        self._phase_start: float | None = None
        self._phase_name: str | None = None
        self.host_timings: list[tuple[str, float]] = []
        self.host_total_time: float = 0.0
        self.docker_startup_time: float = 0.0  # Gap between host launch and container start
        # Capture time spent in Python init (imports) before this point
        # Uses wall clock since _CONTAINER_START_TIME is wall clock
        self.python_init_time: float = (time.time() - _CONTAINER_START_TIME) * 1000
        self._load_host_timing()

    def _load_host_timing(self) -> None:
        """Load host timing data from environment variable."""
        import json

        host_timing_json = os.environ.get("JIB_HOST_TIMING", "")
        if host_timing_json:
            try:
                data = json.loads(host_timing_json)
                self.host_timings = data.get("timings", [])
                self.host_total_time = data.get("total_time", 0.0)
            except (json.JSONDecodeError, KeyError):
                pass

        # Calculate docker startup gap (time between host launching container and Python starting)
        host_launch_time_str = os.environ.get("JIB_HOST_LAUNCH_TIME", "")
        if host_launch_time_str:
            try:
                host_launch_time = float(host_launch_time_str)
                # Gap = container start time - host launch time (in milliseconds)
                self.docker_startup_time = (_CONTAINER_START_TIME - host_launch_time) * 1000
            except (ValueError, TypeError):
                pass

    def start_phase(self, name: str) -> None:
        """Start timing a phase."""
        if not ENABLE_STARTUP_TIMING:
            return
        self._phase_name = name
        self._phase_start = time.perf_counter()

    def end_phase(self) -> None:
        """End timing the current phase."""
        if not ENABLE_STARTUP_TIMING or self._phase_start is None:
            return
        elapsed = (time.perf_counter() - self._phase_start) * 1000  # ms
        self.timings.append((self._phase_name, elapsed))
        self._phase_name = None
        self._phase_start = None

    def phase(self, name: str):
        """Context manager for timing a phase."""
        timer = self
        phase_name = name

        class PhaseContext:
            def __enter__(self):
                timer.start_phase(phase_name)
                return self

            def __exit__(self, *args):
                timer.end_phase()

        return PhaseContext()

    def print_summary(self) -> None:
        """Print combined timing summary (host + container phases)."""
        if not ENABLE_STARTUP_TIMING:
            return
        if not self.timings and not self.host_timings:
            return

        # Container total includes python_init (imports) + all phases
        phases_total = (time.perf_counter() - self.start_time) * 1000
        container_total = self.python_init_time + phases_total
        grand_total = self.host_total_time + self.docker_startup_time + container_total

        print("\n" + "=" * 60)
        print("STARTUP TIMING SUMMARY")
        print("=" * 60)
        print(f"{'Phase':<40} {'Time (ms)':>10} {'%':>6}")
        print("-" * 60)

        # Print host phases (% of grand total)
        if self.host_timings:
            print("HOST:")
            for name, elapsed in self.host_timings:
                pct = (elapsed / grand_total) * 100 if grand_total > 0 else 0
                bar = "█" * int(pct / 5)
                print(f"  {name:<38} {elapsed:>10.1f} {pct:>5.1f}% {bar}")
            print(f"  {'(host total)':<38} {self.host_total_time:>10.1f}")
            print()

        # Print docker startup gap (time from host launch to container Python starting)
        if self.docker_startup_time > 0:
            print("DOCKER:")
            pct = (self.docker_startup_time / grand_total) * 100 if grand_total > 0 else 0
            bar = "█" * int(pct / 5)
            print(
                f"  {'container_startup':<38} {self.docker_startup_time:>10.1f} {pct:>5.1f}% {bar}"
            )
            print()

        # Print container phases (% of container total for meaningful breakdown)
        if self.timings or self.python_init_time > 0:
            print("CONTAINER:")
            # Show python_init first (time for imports before StartupTimer was created)
            if self.python_init_time > 0:
                pct = (self.python_init_time / container_total) * 100 if container_total > 0 else 0
                bar = "█" * int(pct / 5)
                print(f"  {'python_init':<38} {self.python_init_time:>10.1f} {pct:>5.1f}% {bar}")
            for name, elapsed in self.timings:
                pct = (elapsed / container_total) * 100 if container_total > 0 else 0
                bar = "█" * int(pct / 5)
                print(f"  {name:<38} {elapsed:>10.1f} {pct:>5.1f}% {bar}")
            print(f"  {'(container total)':<38} {container_total:>10.1f}")

        print("-" * 60)
        print(f"{'GRAND TOTAL':<40} {grand_total:>10.1f}")
        print("=" * 60 + "\n")


# Global timer instance
_startup_timer = StartupTimer()


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class Config:
    """Container configuration from environment variables."""

    # Fixed container user - UID/GID adjusted at runtime to match host
    container_user: str = "jib"
    runtime_uid: int = field(default_factory=lambda: int(os.environ.get("RUNTIME_UID", "1000")))
    runtime_gid: int = field(default_factory=lambda: int(os.environ.get("RUNTIME_GID", "1000")))
    quiet: bool = field(default_factory=lambda: os.environ.get("JIB_QUIET", "0") == "1")

    # LLM configuration
    # Auth method: "api_key" (default) or "oauth"
    # When oauth, don't warn about missing ANTHROPIC_API_KEY
    anthropic_auth_method: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_AUTH_METHOD", "api_key").lower()
    )

    # Valid auth methods for validation
    VALID_AUTH_METHODS: ClassVar[tuple[str, ...]] = ("api_key", "oauth")
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY")
    )

    # GitHub tokens
    github_token: str | None = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN"))
    github_readonly_token: str | None = field(
        default_factory=lambda: os.environ.get("GITHUB_READONLY_TOKEN")
    )

    # Derived paths - fixed home directory for jib user
    @property
    def user_home(self) -> Path:
        return Path("/home/jib")

    @property
    def repos_dir(self) -> Path:
        """The directory containing mounted repositories."""
        return self.user_home / "repos"

    @property
    def sharing_dir(self) -> Path:
        return self.user_home / "sharing"

    @property
    def claude_dir(self) -> Path:
        return self.user_home / ".claude"

    @property
    def beads_dir(self) -> Path:
        return self.sharing_dir / "beads"


# =============================================================================
# Logging
# =============================================================================


class Logger:
    """Simple logger with quiet mode support."""

    def __init__(self, quiet: bool = False):
        self.quiet = quiet

    def info(self, msg: str) -> None:
        """Info message (hidden in quiet mode)."""
        if not self.quiet:
            print(msg)

    def success(self, msg: str) -> None:
        """Success message with checkmark (hidden in quiet mode)."""
        if not self.quiet:
            print(f"✓ {msg}")

    def warn(self, msg: str) -> None:
        """Warning message (always shown)."""
        print(f"⚠ {msg}")

    def error(self, msg: str) -> None:
        """Error message (always shown, to stderr)."""
        print(f"✗ {msg}", file=sys.stderr)


# =============================================================================
# Utility Functions
# =============================================================================


def run_cmd(
    cmd: list[str],
    check: bool = True,
    capture: bool = False,
    timeout: int = 30,
    as_user: tuple[int, int] | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, optionally as a different user via gosu."""
    if as_user:
        uid, gid = as_user
        cmd = ["gosu", f"{uid}:{gid}"] + cmd

    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )


def chown_recursive(path: Path, uid: int, gid: int) -> None:
    """Recursively change ownership of a path."""
    run_cmd(["chown", "-R", f"{uid}:{gid}", str(path)])


# =============================================================================
# Setup Functions
# =============================================================================


def setup_user(config: Config, logger: Logger) -> None:
    """Adjust jib user's UID/GID to match host user for proper file permissions."""
    import grp
    import pwd

    logger.info(
        f"Setting up sandboxed environment for user: {config.container_user} "
        f"(uid={config.runtime_uid}, gid={config.runtime_gid})"
    )

    # Get current jib user's UID/GID
    try:
        current_uid = pwd.getpwnam(config.container_user).pw_uid
        current_gid = grp.getgrnam(config.container_user).gr_gid
    except KeyError:
        logger.error(f"User {config.container_user} not found - container image may be corrupt")
        raise

    # Adjust GID if needed
    if current_gid != config.runtime_gid:
        logger.info(
            f"Adjusting {config.container_user} group GID: {current_gid} -> {config.runtime_gid}"
        )
        run_cmd(["groupmod", "-g", str(config.runtime_gid), config.container_user])

    # Adjust UID if needed
    if current_uid != config.runtime_uid:
        logger.info(
            f"Adjusting {config.container_user} user UID: {current_uid} -> {config.runtime_uid}"
        )
        run_cmd(["usermod", "-u", str(config.runtime_uid), config.container_user])

    # Fix ownership of home directory after UID/GID change
    if current_uid != config.runtime_uid or current_gid != config.runtime_gid:
        logger.info("Fixing home directory ownership...")
        start_time = time.time()
        chown_recursive(config.user_home, config.runtime_uid, config.runtime_gid)
        elapsed = time.time() - start_time
        if elapsed > 1.0:
            logger.info(f"  chown completed in {elapsed:.1f}s")


# NOTE: PostgreSQL and Redis service startup removed for now.
# If needed in the future, add a setup_services() function here that starts them:
#   service postgresql start
#   service redis-server start
# The container image still includes these services if installed via docker-setup.py.


def setup_environment(config: Config) -> None:
    """Set up environment variables."""
    os.environ["HOME"] = str(config.user_home)
    os.environ["USER"] = config.container_user

    # Add user's local bin (Claude Code native install) and jib runtime scripts to PATH
    current_path = os.environ.get("PATH", "")
    local_bin = config.user_home / ".local" / "bin"
    os.environ["PATH"] = (
        f"{local_bin}:/opt/jib-runtime/jib-container/bin:/usr/local/bin:{current_path}"
    )

    # Python settings
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["PYTHONUNBUFFERED"] = "1"

    # Claude settings
    os.environ["DISABLE_AUTOUPDATER"] = "1"

    # Beads directory
    os.environ["BEADS_DIR"] = str(config.beads_dir / ".beads")

    # Git editor - use 'true' (no-op) for non-interactive environment
    # This allows git rebase --continue to work without an interactive editor.
    # Side effects: git commit without -m creates empty messages, git rebase -i
    # applies default picks. This is intentional for autonomous operation.
    os.environ["GIT_EDITOR"] = "true"


def setup_git(config: Config, logger: Logger) -> None:
    """Configure git for jib identity and credential helper."""
    user_tuple = (config.runtime_uid, config.runtime_gid)

    # Set git identity
    run_cmd(["git", "config", "--global", "user.name", "jib"], as_user=user_tuple)
    run_cmd(["git", "config", "--global", "user.email", "jib@localhost"], as_user=user_tuple)

    # Configure credential helper if token available
    if config.github_token:
        run_cmd(
            [
                "git",
                "config",
                "--global",
                "credential.helper",
                "/opt/jib-runtime/jib-container/bin/git-credential-github-token",
            ],
            as_user=user_tuple,
        )
        run_cmd(
            ["git", "config", "--global", "credential.useHttpPath", "true"],
            as_user=user_tuple,
        )
        logger.success("Git credential helper configured for GitHub push")
    else:
        run_cmd(["git", "config", "--global", "credential.helper", ""], as_user=user_tuple)

    # Never embed tokens in URLs
    run_cmd(
        ["git", "config", "--global", "advice.pushUpdateRejected", "false"],
        as_user=user_tuple,
    )

    logger.success("Git configured to commit as jib <jib@localhost>")


def setup_worktrees(config: Config, logger: Logger) -> bool:
    """Validate gateway-managed worktree configuration.

    This implements the Gateway-Managed Worktrees ADR:
    - Gateway creates/manages worktrees before container starts
    - Container mounts only working directory (no git metadata access)
    - All git operations route through gateway API
    - No path rewriting needed - gateway controls all paths

    The .git file/directory is shadowed by tmpfs mount, so container
    cannot perform local git operations - they must go through gateway.

    Returns False if setup failed fatally.
    """
    if not config.repos_dir.exists():
        logger.warn("Repos workspace not found - check mount configuration")
        return True

    # Count repos for logging
    repo_count = 0
    for repo_dir in config.repos_dir.iterdir():
        if repo_dir.is_dir():
            repo_count += 1

    if repo_count > 0:
        logger.success(f"Repos mounted: {repo_count} repo(s) (gateway-managed worktrees)")
        logger.info("  All git operations route through gateway API")

    return True


def setup_jib_symlink(config: Config, logger: Logger) -> None:
    """Create ~/jib symlink to runtime scripts.

    This provides a consistent, short path to jib runtime scripts that:
    - Points to /opt/jib-runtime/jib-container (baked into Docker image)
    - Is independent of the mounted ~/repos/james-in-a-box
    - Matches the container image version
    """
    jib_link = config.user_home / "jib"
    target = Path("/opt/jib-runtime/jib-container")

    # Validate target exists (should always be true if Docker image built correctly)
    if not target.is_dir():
        logger.error(f"Runtime directory not found: {target}")
        logger.error("  This indicates a problem with the Docker image build")
        return

    if jib_link.is_symlink():
        jib_link.unlink()
    elif jib_link.exists():
        logger.warn("~/jib exists but is not a symlink, skipping")
        return

    jib_link.symlink_to(target)
    os.lchown(jib_link, config.runtime_uid, config.runtime_gid)

    logger.success("Runtime symlink created: ~/jib -> /opt/jib-runtime/jib-container")
    logger.info("  Use ~/jib/ for runtime scripts instead of ~/repos/james-in-a-box/jib-container/")


def setup_sharing(config: Config, logger: Logger) -> None:
    """Set up shared directories and symlinks."""
    if not config.sharing_dir.exists():
        logger.warn("Sharing directory not found - check mount configuration")
        return

    # Create symlink: ~/tmp -> ~/sharing/tmp
    tmp_link = config.user_home / "tmp"
    if tmp_link.is_symlink():
        tmp_link.unlink()
    tmp_link.symlink_to(config.sharing_dir / "tmp")

    # Ensure subdirectories exist
    subdirs = ["tmp", "notifications", "context", "tracking", "traces", "logs"]
    for subdir in subdirs:
        (config.sharing_dir / subdir).mkdir(parents=True, exist_ok=True)

    chown_recursive(config.sharing_dir, config.runtime_uid, config.runtime_gid)

    logger.success("Shared directories configured:")
    logger.info("  ~/sharing/tmp/           (mounted from ~/.jib-sharing/tmp/)")
    logger.info("  ~/sharing/notifications/ (mounted from ~/.jib-sharing/notifications/)")
    logger.info("  ~/sharing/context/       (mounted from ~/.jib-sharing/context/)")
    logger.info("  ~/sharing/traces/        (LLM trace collection)")
    logger.info("  ~/sharing/logs/          (trace collector logs)")
    logger.info("  Convenience symlink: ~/tmp -> ~/sharing/tmp")


def setup_agent_rules(config: Config, logger: Logger) -> None:
    """Set up CLAUDE.md agent rules."""
    rules_dir = Path("/opt/claude-rules")
    rules_order = [
        "mission.md",
        "environment.md",
        "beads-usage.md",
        "context-tracking.md",
        "code-standards.md",
        "test-workflow.md",
        "pr-descriptions.md",
        "notification-template.md",
    ]

    if not (rules_dir / "mission.md").exists():
        return

    # Combine rules into CLAUDE.md
    claude_md = config.user_home / "CLAUDE.md"
    content_parts = []

    for rule_file in rules_order:
        rule_path = rules_dir / rule_file
        if rule_path.exists():
            content_parts.append(rule_path.read_text())

    claude_md.write_text("\n\n---\n\n".join(content_parts))
    os.chown(claude_md, config.runtime_uid, config.runtime_gid)

    # Symlink in ~/repos/
    if config.repos_dir.exists():
        repos_claude = config.repos_dir / "CLAUDE.md"
        if repos_claude.is_symlink():
            repos_claude.unlink()
        repos_claude.symlink_to(claude_md)
        os.lchown(repos_claude, config.runtime_uid, config.runtime_gid)

    logger.success("AI agent rules installed: ~/CLAUDE.md (symlinked to ~/repos/)")
    logger.info(f"  Combined {len(rules_order)} rule files (index-based per LLM Doc ADR)")
    logger.info("  Note: Reference docs in ~/repos/james-in-a-box/docs/ (fetched on-demand)")


def setup_claude(config: Config, logger: Logger) -> None:
    """Set up Claude CLI configuration."""
    # Create directories
    config.claude_dir.mkdir(parents=True, exist_ok=True)
    (config.claude_dir / "commands").mkdir(exist_ok=True)
    (config.user_home / ".config" / "claude-code").mkdir(parents=True, exist_ok=True)

    # Check API key (only warn if using api_key auth method)
    # Validate auth method
    if config.anthropic_auth_method not in config.VALID_AUTH_METHODS:
        logger.warn(
            f"Invalid ANTHROPIC_AUTH_METHOD '{config.anthropic_auth_method}', "
            f"expected one of: {', '.join(config.VALID_AUTH_METHODS)}"
        )

    if config.anthropic_api_key:
        logger.success("Anthropic API key configured")
    elif config.anthropic_auth_method == "oauth":
        logger.success("Anthropic OAuth authentication enabled")
    else:
        logger.warn("ANTHROPIC_API_KEY not set")
        logger.info("  Set via: export ANTHROPIC_API_KEY=sk-ant-...")
        logger.info("  Or use OAuth: export ANTHROPIC_AUTH_METHOD=oauth")

    # Copy custom commands
    commands_src = Path("/usr/local/share/claude-commands")
    if commands_src.exists():
        for cmd in commands_src.glob("*.md"):
            if cmd.name != "README.md":
                (config.claude_dir / "commands" / cmd.name).write_text(cmd.read_text())
        logger.success("Custom commands installed:")
        if not config.quiet:
            for cmd in (config.claude_dir / "commands").glob("*.md"):
                print(f"    @{cmd.stem}")

    # Create settings.json
    settings = {
        "alwaysThinkingEnabled": True,
        "defaultPermissionMode": "bypassPermissions",
        "autoApproveEdits": True,
        "editorMode": "normal",
        "autoUpdate": False,
        "outputStyle": "default",
        "defaultModel": "opus",
    }

    settings_file = config.claude_dir / "settings.json"
    settings_file.write_text(json.dumps(settings, indent=2))
    os.chown(settings_file, config.runtime_uid, config.runtime_gid)

    # Ensure ~/.claude.json has required settings to skip onboarding prompts
    # The file may be bind-mounted from host, so we merge rather than overwrite
    user_state_file = config.user_home / ".claude.json"
    required_settings = {
        "hasCompletedOnboarding": True,
        "autoUpdates": False,
    }
    # These are only set on new files, not forced on existing ones
    default_settings = {
        "lastOnboardingVersion": "2.0.69",
        "numStartups": 1,
        "installMethod": "api_key",
    }

    # Read existing config if present
    file_existed = user_state_file.exists()
    existing_config = {}
    if file_existed:
        with contextlib.suppress(json.JSONDecodeError, OSError):
            existing_config = json.loads(user_state_file.read_text())

    # Check if required settings need updating
    needs_update = False
    for key, value in required_settings.items():
        if existing_config.get(key) != value:
            needs_update = True
            existing_config[key] = value

    # Add defaults only for missing keys
    for key, value in default_settings.items():
        if key not in existing_config:
            needs_update = True
            existing_config[key] = value

    # Write back if changes needed
    if needs_update:
        user_state_file.write_text(json.dumps(existing_config, indent=2))
        os.chown(user_state_file, config.runtime_uid, config.runtime_gid)
        user_state_file.chmod(0o600)
        user_state_status = "created" if not file_existed else "updated"
    else:
        user_state_status = "unchanged"

    # Fix ownership
    chown_recursive(config.claude_dir, config.runtime_uid, config.runtime_gid)
    chown_recursive(
        config.user_home / ".config/claude-code", config.runtime_uid, config.runtime_gid
    )
    config.claude_dir.chmod(0o700)

    logger.success(f"Claude settings created: {settings_file}")
    logger.success(f"Claude user state {user_state_status}: {user_state_file}")
    if not config.quiet:
        print(json.dumps(settings, indent=2))
        print()


def setup_bashrc(config: Config, logger: Logger) -> None:
    """Set up .bashrc with aliases."""
    bashrc = config.user_home / ".bashrc"

    # Append our settings
    with open(bashrc, "a") as f:
        f.write("\n# Added by jib entrypoint\n")
        f.write("alias claude='claude --dangerously-skip-permissions'\n")
        f.write(
            r"export PS1='\[\033[01;32m\]\u@sandboxed\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '"
            + "\n"
        )

    os.chown(bashrc, config.runtime_uid, config.runtime_gid)
    logger.success("Claude alias created (bypasses permissions in sandbox)")


def setup_beads(config: Config, logger: Logger) -> bool:
    """Validate and set up Beads persistent memory. Returns False on fatal error."""
    if not config.beads_dir.exists():
        logger.error("ERROR: Beads directory not found")
        logger.error("")
        logger.error("Beads must be initialized before starting the container.")
        logger.error("Please run setup.sh on the host:")
        logger.error("")
        logger.error("  cd ~/repos/james-in-a-box")
        logger.error("  ./setup.sh")
        logger.error("")
        return False

    beads_jsonl = config.beads_dir / ".beads" / "issues.jsonl"
    if not beads_jsonl.exists():
        logger.error("ERROR: Beads not initialized")
        logger.error("")
        logger.error("Beads repository exists but is not properly initialized.")
        logger.error("Please run setup.sh on the host:")
        logger.error("")
        logger.error("  cd ~/repos/james-in-a-box")
        logger.error("  ./setup.sh")
        logger.error("")
        return False

    # Set up beads
    chown_recursive(config.beads_dir, config.runtime_uid, config.runtime_gid)

    # Create convenience symlink: ~/beads -> ~/sharing/beads
    beads_link = config.user_home / "beads"
    if beads_link.is_symlink():
        beads_link.unlink()
    beads_link.symlink_to(config.beads_dir)

    # Import JSONL if needed
    with contextlib.suppress(Exception):
        run_cmd(
            ["bd", "sync", "--import-only"],
            as_user=(config.runtime_uid, config.runtime_gid),
            check=False,
            capture=True,
        )

    logger.success("Beads memory system ready")
    logger.info("  Location: ~/beads/ (symlink to ~/sharing/beads/)")
    logger.info("  Usage: bd --allow-stale create 'task description' --labels feature,important")

    return True


def check_gateway_health(config: Config, logger: Logger) -> bool:
    """Wait for gateway readiness before starting (Phase 2 lockdown mode).

    In network lockdown mode, the container cannot reach the internet directly.
    All traffic must go through the gateway's proxy. This function ensures
    the gateway and proxy are ready before the agent starts.

    Returns:
        True if gateway is ready (or not in lockdown mode), False on timeout
    """
    import requests
    from requests.exceptions import RequestException

    # Check if we're in lockdown mode
    network_mode = os.environ.get("JIB_NETWORK_MODE", "legacy")
    if network_mode != "lockdown":
        logger.info("Network mode: legacy (gateway health check skipped)")
        return True

    logger.info("Network mode: lockdown (Phase 2)")
    logger.info("Waiting for gateway readiness...")

    gateway_url = os.environ.get("GATEWAY_URL", "http://jib-gateway:9847")
    proxy_url = os.environ.get("HTTPS_PROXY", "http://gateway:3128")

    timeout = 60  # seconds
    interval = 2  # seconds
    elapsed = 0

    while elapsed < timeout:
        try:
            # Check gateway API health
            health_response = requests.get(
                f"{gateway_url}/api/v1/health",
                timeout=5,
            )
            if health_response.status_code != 200:
                raise RequestException("Gateway not ready")

            # Check proxy connectivity by testing an allowed domain
            # Use proxies dict to route through gateway proxy
            proxies = {"http": proxy_url, "https": proxy_url}
            api_response = requests.get(
                "https://api.github.com/",
                proxies=proxies,
                timeout=10,
                verify=True,
            )
            # GitHub returns 200 for unauthenticated, 401 for bad auth
            # Either means the proxy is working
            if api_response.status_code in (200, 401, 403):
                logger.success("Gateway ready (API + proxy verified)")
                return True

        except RequestException as e:
            if not config.quiet:
                logger.info(f"  Waiting... ({elapsed}/{timeout}s) - {type(e).__name__}")

        time.sleep(interval)
        elapsed += interval

    logger.error(f"Gateway not ready after {timeout} seconds")
    logger.error("The gateway sidecar may not be running or misconfigured.")
    logger.error("In lockdown mode, all network traffic requires the gateway.")
    return False


# =============================================================================
# Cleanup
# =============================================================================


def cleanup_on_exit(config: Config, logger: Logger) -> None:
    """Cleanup handler for container shutdown.

    In the gateway-managed worktree architecture, the container doesn't
    have access to git metadata, so there's minimal cleanup needed.
    The gateway handles worktree cleanup when containers exit.
    """
    if not config.quiet:
        print("")
        print("Cleaning up on container exit...")
        print("✓ Cleanup complete")


# =============================================================================
# Main Entry Points
# =============================================================================


def run_interactive(config: Config, logger: Logger) -> None:
    """Launch interactive Claude Code session."""
    logger.info("")
    logger.info("Analysis Pattern: Exec-based (triggered by host services)")
    logger.info("  - Context analysis: Triggered after context-sync")
    logger.info("  - GitHub analysis: Triggered after github-sync")
    logger.info("  - Message processing: Triggered by slack-receiver")
    logger.info("")

    # Change to repos directory
    if config.repos_dir.exists():
        os.chdir(config.repos_dir)
    else:
        os.chdir(config.user_home)

    # Build environment for Claude Code
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": "/opt/jib-runtime/jib-container:/opt/jib-runtime/shared",
            "NO_PROXY": os.environ.get("NO_PROXY", "127.0.0.1"),
            "DISABLE_TELEMETRY": os.environ.get("DISABLE_TELEMETRY", ""),
            "DISABLE_COST_WARNINGS": os.environ.get("DISABLE_COST_WARNINGS", ""),
        }
    )

    logger.info("Launching Claude Code interactive mode...")

    # Print timing summary right before launching LLM
    _startup_timer.print_summary()

    # Launch via gosu
    os.execvpe(
        "gosu",
        [
            "gosu",
            f"{config.runtime_uid}:{config.runtime_gid}",
            "python3",
            "-c",
            "from llm import run_interactive; run_interactive()",
        ],
        env,
    )


def run_exec(config: Config, logger: Logger, args: list[str]) -> None:
    """Run a command in exec mode."""
    env = os.environ.copy()

    # Print timing summary before exec
    _startup_timer.print_summary()

    os.execvpe(
        "gosu",
        ["gosu", f"{config.runtime_uid}:{config.runtime_gid}"] + args,
        env,
    )


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    """Main entry point."""
    config = Config()
    logger = Logger(config.quiet)

    # Register cleanup handler
    def signal_handler(signum, frame):
        cleanup_on_exit(config, logger)
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Run setup with timing instrumentation
    with _startup_timer.phase("setup_user"):
        setup_user(config, logger)

    with _startup_timer.phase("setup_environment"):
        setup_environment(config)

    with _startup_timer.phase("setup_jib_symlink"):
        setup_jib_symlink(config, logger)

    with _startup_timer.phase("setup_git"):
        setup_git(config, logger)

    with _startup_timer.phase("setup_worktrees"):
        if not setup_worktrees(config, logger):
            logger.error("")
            logger.error("Container startup aborted due to worktree configuration failure.")
            logger.error("Please check your jib setup and try again.")
            sys.exit(1)

    with _startup_timer.phase("setup_sharing"):
        setup_sharing(config, logger)

    with _startup_timer.phase("setup_agent_rules"):
        setup_agent_rules(config, logger)

    with _startup_timer.phase("setup_claude"):
        setup_claude(config, logger)

    with _startup_timer.phase("setup_bashrc"):
        setup_bashrc(config, logger)

    # Ensure tracking directory
    with _startup_timer.phase("setup_tracking_dir"):
        tracking_dir = config.sharing_dir / "tracking"
        if config.sharing_dir.exists():
            tracking_dir.mkdir(exist_ok=True)
            os.chown(tracking_dir, config.runtime_uid, config.runtime_gid)

    with _startup_timer.phase("setup_beads"):
        if not setup_beads(config, logger):
            sys.exit(1)

    # Phase 2: Wait for gateway readiness in lockdown mode
    with _startup_timer.phase("check_gateway"):
        if not check_gateway_health(config, logger):
            logger.error("")
            logger.error("Container startup aborted: gateway not ready.")
            logger.error("Ensure the gateway sidecar is running with JIB_NETWORK_MODE=lockdown")
            sys.exit(1)

    # Run appropriate mode (timing summary is printed inside each mode)
    if len(sys.argv) == 1:
        run_interactive(config, logger)
    else:
        run_exec(config, logger, sys.argv[1:])


if __name__ == "__main__":
    main()
