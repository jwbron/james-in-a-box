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
import random
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


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
    llm_provider: str = field(default_factory=lambda: os.environ.get("LLM_PROVIDER", "anthropic"))
    # Auth method: "api_key" (default) or "oauth"
    # When oauth, don't warn about missing ANTHROPIC_API_KEY
    anthropic_auth_method: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_AUTH_METHOD", "api_key")
    )
    google_api_key: str | None = field(default_factory=lambda: os.environ.get("GOOGLE_API_KEY"))
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY")
    )
    openai_api_key: str | None = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY"))
    gemini_model: str | None = field(default_factory=lambda: os.environ.get("GEMINI_MODEL"))

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
    def git_main_dir(self) -> Path:
        return self.user_home / ".git-main"

    @property
    def claude_dir(self) -> Path:
        return self.user_home / ".claude"

    @property
    def gemini_dir(self) -> Path:
        return self.user_home / ".gemini"

    @property
    def beads_dir(self) -> Path:
        return self.sharing_dir / "beads"

    @property
    def router_dir(self) -> Path:
        return self.user_home / ".claude-code-router"

    @property
    def router_config(self) -> Path:
        return self.router_dir / "config.json"


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


def run_cmd_with_retry(
    cmd: list[str],
    max_retries: int = 5,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    check: bool = True,
    capture: bool = False,
    timeout: int = 30,
    as_user: tuple[int, int] | None = None,
) -> subprocess.CompletedProcess:
    """Run a command with exponential backoff retry for transient failures.

    This is useful for git config commands that may fail due to lock contention
    when multiple containers start simultaneously.

    Args:
        cmd: Command to run
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        check: Whether to raise on non-zero exit code (after all retries exhausted)
        capture: Whether to capture stdout/stderr in returned result
        timeout: Command timeout in seconds
        as_user: Optional (uid, gid) tuple to run command as different user
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            # Always capture internally so we can detect lock errors in stderr
            result = run_cmd(
                cmd,
                check=check,
                capture=True,
                timeout=timeout,
                as_user=as_user,
            )
            # If caller didn't want capture, clear the output
            if not capture:
                result.stdout = ""
                result.stderr = ""
            return result
        except subprocess.CalledProcessError as e:
            last_exception = e
            # Check if this looks like a lock contention error
            stderr = e.stderr or ""
            if "could not lock" not in stderr:
                # Not a lock error, don't retry
                raise

            if attempt < max_retries:
                # Exponential backoff with jitter
                delay = min(base_delay * (2**attempt), max_delay)
                delay *= 0.5 + random.random()  # Add jitter
                # Log retry for debugging
                print(
                    f"⚠ Git config lock contention, retrying ({attempt + 1}/{max_retries})...",
                    file=sys.stderr,
                )
                time.sleep(delay)

    # All retries exhausted
    if last_exception:
        raise last_exception
    raise RuntimeError(f"Command failed after {max_retries} retries: {cmd}")


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

    # Fix local repo configs
    if config.git_main_dir.exists():
        for repo_config in config.git_main_dir.glob("*/config"):
            _fix_repo_config(repo_config, logger)

    logger.success("Git configured to commit as jib <jib@localhost>")


def _fix_repo_config(repo_config: Path, logger: Logger) -> None:
    """Fix a single repo config file (identity, token cleanup, SSH->HTTPS).

    Uses retry logic with exponential backoff to handle lock contention
    when multiple containers start simultaneously.
    """
    # Clean up stale lock files from crashed containers (older than 60 seconds).
    # We don't delete fresh locks as they may be legitimately held by another process.
    # The retry logic handles genuine concurrent access.
    lock_file = repo_config.with_suffix(".lock")
    if lock_file.exists():
        try:
            lock_age = time.time() - lock_file.stat().st_mtime
            if lock_age > 60:
                lock_file.unlink()
                logger.warn(f"Removed stale git lock file: {lock_file} (age: {lock_age:.0f}s)")
        except OSError:
            pass  # Another process may have removed it, or stat failed

    # Set identity with retry for lock contention
    run_cmd_with_retry(["git", "config", "-f", str(repo_config), "user.name", "jib"])
    run_cmd_with_retry(["git", "config", "-f", str(repo_config), "user.email", "jib@localhost"])

    # Get remote URL
    try:
        result = run_cmd(
            ["git", "config", "-f", str(repo_config), "remote.origin.url"],
            capture=True,
            check=False,
        )
        remote_url = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return

    if not remote_url:
        return

    # Check for embedded tokens
    token_patterns = ["x-access-token:", "ghs_", "ghp_", "github_pat_"]
    if any(p in remote_url for p in token_patterns):
        logger.warn("Found token in git remote URL, cleaning it up...")
        # Strip token from URL
        import re

        clean_url = re.sub(r"https://[^@]*@github\.com/", "https://github.com/", remote_url)
        run_cmd_with_retry(
            ["git", "config", "-f", str(repo_config), "remote.origin.url", clean_url]
        )
        logger.info(f"  Cleaned: {remote_url} -> {clean_url}")

    # Convert SSH to HTTPS
    if remote_url.startswith("git@github.com:"):
        https_url = remote_url.replace("git@github.com:", "https://github.com/")
        run_cmd_with_retry(
            ["git", "config", "-f", str(repo_config), "remote.origin.url", https_url]
        )
        logger.info(f"  Converted SSH to HTTPS: {https_url}")


def setup_worktrees(config: Config, logger: Logger) -> bool:
    """Configure git worktrees. Returns False if setup failed fatally."""
    if not config.repos_dir.exists():
        logger.warn("Repos workspace not found - check mount configuration")
        return True

    # Check for worktrees
    worktree_dirs = [d for d in config.repos_dir.iterdir() if (d / ".git").is_file()]
    if not worktree_dirs:
        return True

    # Verify .git-main mount
    if not config.git_main_dir.exists():
        logger.error("FATAL: ~/.git-main not mounted but worktrees exist")
        logger.error("  This means jib failed to mount the git directories.")
        logger.error("  Container cannot start with broken git configuration.")
        logger.error("")
        logger.error("  Possible causes:")
        logger.error("    - Docker mount failed")
        logger.error("    - Host .git directories don't exist")
        logger.error("    - Permission issues on host")
        return False

    # Configure each worktree
    configured = 0
    failed = 0
    failed_repos = []

    for repo_dir in worktree_dirs:
        repo_name = repo_dir.name
        git_file = repo_dir / ".git"

        # Read original gitdir path
        content = git_file.read_text().strip()
        original_gitdir = content.replace("gitdir: ", "")
        worktree_admin = Path(original_gitdir).name

        # Build target path
        target_path = config.git_main_dir / repo_name / "worktrees" / worktree_admin

        if target_path.is_dir():
            git_file.write_text(f"gitdir: {target_path}\n")
            os.chown(git_file, config.runtime_uid, config.runtime_gid)
            configured += 1
        else:
            logger.error(f"FATAL: Worktree path doesn't exist for {repo_name}")
            logger.error(f"  Expected: {target_path}")
            logger.error(f"  Original: {original_gitdir}")
            failed += 1
            failed_repos.append(repo_name)

    if failed > 0:
        logger.error("")
        logger.error(f"FATAL: {failed} worktree(s) failed to configure: {' '.join(failed_repos)}")
        logger.error("  Container cannot start with broken git configuration.")
        return False

    if configured > 0:
        logger.success(f"Repo worktrees configured: {configured} repo(s)")
        logger.info("  Git metadata mounted read-write from ~/.git-main/")

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
    """Set up CLAUDE.md and GEMINI.md agent rules."""
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

    # Create GEMINI.md as symlink to CLAUDE.md
    gemini_md = config.user_home / "GEMINI.md"
    if gemini_md.is_symlink():
        gemini_md.unlink()
    gemini_md.symlink_to(claude_md)
    os.lchown(gemini_md, config.runtime_uid, config.runtime_gid)

    if config.repos_dir.exists():
        repos_gemini = config.repos_dir / "GEMINI.md"
        if repos_gemini.is_symlink():
            repos_gemini.unlink()
        repos_gemini.symlink_to(claude_md)
        os.lchown(repos_gemini, config.runtime_uid, config.runtime_gid)

    logger.success("AI agent rules installed: ~/CLAUDE.md and ~/GEMINI.md (symlinked to ~/repos/)")
    logger.info(f"  Combined {len(rules_order)} rule files (index-based per LLM Doc ADR)")
    logger.info("  Note: Reference docs in ~/repos/james-in-a-box/docs/ (fetched on-demand)")


def setup_claude(config: Config, logger: Logger) -> None:
    """Set up Claude CLI configuration."""
    # Create directories
    config.claude_dir.mkdir(parents=True, exist_ok=True)
    (config.claude_dir / "commands").mkdir(exist_ok=True)
    (config.claude_dir / "hooks").mkdir(exist_ok=True)
    (config.user_home / ".config" / "claude-code").mkdir(parents=True, exist_ok=True)

    # Check API key (only warn if using api_key auth method)
    if config.llm_provider == "anthropic":
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

    # Copy custom hooks
    hooks_src = Path("/opt/claude-hooks")
    if hooks_src.exists():
        for hook in hooks_src.glob("*.sh"):
            dest = config.claude_dir / "hooks" / hook.name
            dest.write_text(hook.read_text())
            dest.chmod(0o755)
        logger.success("Custom hooks installed:")
        if not config.quiet:
            for hook in (config.claude_dir / "hooks").glob("*.sh"):
                print(f"    {hook.name}")

    # Create settings.json
    # Use baked-in trace-collector from /opt/jib-runtime (not mounted repo)
    # This ensures container uses the version that matches the image
    trace_collector = Path(
        "/opt/jib-runtime/host-services/analysis/trace-collector/hook_handler.py"
    )
    beads_hook = config.claude_dir / "hooks/session-end.sh"

    settings = {
        "alwaysThinkingEnabled": True,
        "defaultPermissionMode": "bypassPermissions",
        "autoApproveEdits": True,
        "editorMode": "normal",
        "autoUpdate": False,
        "outputStyle": "default",
        "defaultModel": "opus",
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": ".*",
                    "hooks": [
                        {"type": "command", "command": f"python3 {trace_collector} post-tool-use"}
                    ],
                }
            ],
            "SessionEnd": [
                {
                    "hooks": [
                        {"type": "command", "command": f"python3 {trace_collector} session-end"},
                        {"type": "command", "command": f"bash {beads_hook}"},
                    ]
                }
            ],
        },
    }

    settings_file = config.claude_dir / "settings.json"
    settings_file.write_text(json.dumps(settings, indent=2))
    os.chown(settings_file, config.runtime_uid, config.runtime_gid)

    # Create ~/.claude.json user state to skip onboarding prompts
    user_state = {
        "hasCompletedOnboarding": True,
        "lastOnboardingVersion": "2.0.69",
        "numStartups": 1,
        "installMethod": "api_key",
        "autoUpdates": False,
    }
    user_state_file = config.user_home / ".claude.json"
    user_state_file.write_text(json.dumps(user_state, indent=2))
    os.chown(user_state_file, config.runtime_uid, config.runtime_gid)
    user_state_file.chmod(0o600)

    # Fix ownership
    chown_recursive(config.claude_dir, config.runtime_uid, config.runtime_gid)
    chown_recursive(
        config.user_home / ".config/claude-code", config.runtime_uid, config.runtime_gid
    )
    config.claude_dir.chmod(0o700)

    logger.success(f"Claude settings created: {settings_file}")
    logger.success(f"Claude user state created: {user_state_file} (onboarding skipped)")
    if not config.quiet:
        print(json.dumps(settings, indent=2))
        print()


def setup_gemini(config: Config, logger: Logger) -> None:
    """Set up Gemini CLI configuration."""
    config.gemini_dir.mkdir(parents=True, exist_ok=True)
    os.chown(config.gemini_dir, config.runtime_uid, config.runtime_gid)

    # Check API key
    if config.llm_provider in ("google", "gemini"):
        if config.google_api_key:
            logger.success("Google API key configured")
        else:
            logger.warn("GOOGLE_API_KEY not set")
            logger.info("  Set via: export GOOGLE_API_KEY=AIza...")

    # Configure API key in .env file
    if config.google_api_key:
        env_file = config.gemini_dir / ".env"
        env_file.write_text(
            f"# Auto-configured by jib entrypoint\nGEMINI_API_KEY={config.google_api_key}\n"
        )
        os.chown(env_file, config.runtime_uid, config.runtime_gid)
        env_file.chmod(0o600)
        logger.success("Gemini API key configured in ~/.gemini/.env")

    # Configure settings
    settings = {
        "autoAccept": True,
        "sandbox": False,
        "hideBanner": True,
        "usageStatisticsEnabled": False,
    }

    settings_file = config.gemini_dir / "settings.json"
    settings_file.write_text(json.dumps(settings, indent=2))
    os.chown(settings_file, config.runtime_uid, config.runtime_gid)
    settings_file.chmod(0o600)

    logger.success("Gemini CLI settings configured")


def setup_router(config: Config, logger: Logger) -> None:
    """Set up claude-code-router for multi-provider support."""
    config.router_dir.mkdir(parents=True, exist_ok=True)
    (config.router_dir / "plugins").mkdir(exist_ok=True)
    (config.router_dir / "logs").mkdir(exist_ok=True)
    chown_recursive(config.router_dir, config.runtime_uid, config.runtime_gid)

    logger.info(f"LLM Provider: {config.llm_provider}")

    # Build router config based on provider
    if config.llm_provider in ("google", "gemini"):
        if not config.google_api_key:
            logger.warn("LLM_PROVIDER=google but GOOGLE_API_KEY not set")

        router_config = {
            "log": True,
            "LOG_LEVEL": "debug",
            "NON_INTERACTIVE_MODE": True,
            "Providers": [
                {
                    "name": "gemini",
                    "api_base_url": "https://generativelanguage.googleapis.com/v1beta/models/",
                    "api_key": "$GOOGLE_API_KEY",
                    "models": ["gemini-3-pro-preview"],
                    "transformer": {"use": ["gemini"]},
                }
            ],
            "Router": {"default": "gemini,gemini-3-pro-preview"},
        }
        logger.success("Router configured for Google Gemini 3 Pro")
        logger.info(
            "  Router logs: ~/.claude-code-router/logs/ and ~/.claude-code-router/claude-code-router.log"
        )

    elif config.llm_provider == "openai":
        if not config.openai_api_key:
            logger.warn("LLM_PROVIDER=openai but OPENAI_API_KEY not set")

        router_config = {
            "log": False,
            "NON_INTERACTIVE_MODE": True,
            "Providers": [
                {
                    "name": "openai",
                    "api_base_url": "https://api.openai.com/v1/chat/completions",
                    "api_key": "$OPENAI_API_KEY",
                    "models": ["gpt-5.2"],
                }
            ],
            "Router": {"default": "openai,gpt-5.2"},
        }
        logger.success("Router configured for OpenAI GPT-5.2")

    else:  # anthropic (default)
        if config.anthropic_api_key:
            logger.success("Anthropic API key configured")
            logger.info("Using Claude Code directly with API key (no router)")
        elif config.anthropic_auth_method == "oauth":
            logger.success("Anthropic OAuth authentication enabled")
            logger.info("Using Claude Code directly with OAuth (no router)")
        else:
            logger.warn("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY not set")
            logger.info("  Set via: export ANTHROPIC_API_KEY=sk-ant-...")
            logger.info("  Or use OAuth: export ANTHROPIC_AUTH_METHOD=oauth")

        # Claude Code natively supports Anthropic via API key or OAuth
        # No router needed
        return

    # Write config
    config.router_config.write_text(json.dumps(router_config, indent=2))
    os.chown(config.router_config, config.runtime_uid, config.runtime_gid)


def start_router(config: Config, logger: Logger) -> int | None:
    """Start claude-code-router and return its PID, or None if not needed."""
    if not config.router_config.exists():
        return None

    logger.info(f"Router config: {config.router_config}")
    if not config.quiet:
        print(config.router_config.read_text())
    logger.info("")

    # Start the router in background
    logger.info("Starting claude-code-router...")

    router_log = Path("/tmp/claude-code-router.log")
    with open(router_log, "w") as log_file:
        proc = subprocess.Popen(
            [
                "gosu",
                f"{config.runtime_uid}:{config.runtime_gid}",
                "ccr",
                "start",
                "--port",
                "3456",
            ],
            stdout=log_file,
            stderr=log_file,
        )

    # Wait for router to be ready (up to 10 seconds)
    for _ in range(20):
        try:
            # Check if port 3456 is listening
            result = subprocess.run(
                ["nc", "-z", "localhost", "3456"],
                check=False,
                capture_output=True,
                timeout=1,
            )
            if result.returncode == 0:
                logger.success(f"Router started (PID: {proc.pid}, port: 3456)")
                break
        except (subprocess.TimeoutExpired, Exception):
            pass
        time.sleep(0.5)
    else:
        logger.warn("Router may not be ready - check /tmp/claude-code-router.log")
        with contextlib.suppress(Exception):
            print(router_log.read_text())

    # Get activation environment
    logger.info("Activating router environment...")
    try:
        result = run_cmd(
            ["ccr", "activate"],
            as_user=(config.runtime_uid, config.runtime_gid),
            capture=True,
            check=False,
        )
        activate_output = result.stdout.strip()
        logger.info("ccr activate output:")
        print(activate_output)

        # Parse and export environment variables
        for line in activate_output.split("\n"):
            line = line.strip()
            if line.startswith("export "):
                # Parse: export VAR=value or export VAR="value"
                parts = line[7:].split("=", 1)
                if len(parts) == 2:
                    key = parts[0]
                    value = parts[1].strip('"').strip("'")
                    os.environ[key] = value

        logger.info("")
        logger.info("Environment after activation:")
        logger.info(f"  ANTHROPIC_BASE_URL={os.environ.get('ANTHROPIC_BASE_URL', 'not set')}")
        logger.info(
            f"  ANTHROPIC_AUTH_TOKEN={'set' if os.environ.get('ANTHROPIC_AUTH_TOKEN') else 'not set'}"
        )
    except Exception as e:
        logger.warn(f"Failed to activate router environment: {e}")

    return proc.pid


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


def generate_docs_indexes(config: Config, logger: Logger) -> None:
    """Generate documentation indexes."""
    # Use baked-in index-generator from /opt/jib-runtime (not mounted repo)
    # This ensures container uses the version that matches the image
    index_generator = Path(
        "/opt/jib-runtime/host-services/analysis/index-generator/index-generator.py"
    )
    jib_dir = config.repos_dir / "james-in-a-box"

    if not index_generator.exists() or not jib_dir.exists():
        return

    logger.info("")
    logger.info("Generating documentation indexes...")

    try:
        run_cmd(
            [
                "python3",
                str(index_generator),
                "--project",
                str(jib_dir),
                "--output",
                str(jib_dir / "docs/generated"),
            ],
            as_user=(config.runtime_uid, config.runtime_gid),
            capture=True,
        )
        logger.success("Documentation indexes generated")
        logger.info("  Location: ~/repos/james-in-a-box/docs/generated/")
    except Exception:
        logger.warn("Documentation index generation failed (non-critical)")


# =============================================================================
# Cleanup
# =============================================================================


def cleanup_on_exit(config: Config, logger: Logger) -> None:
    """Cleanup handler for container shutdown."""
    if not config.quiet:
        print("")
        print("Cleaning up on container exit...")

    # Check and clean git remote URLs
    if config.git_main_dir.exists():
        for repo_config in config.git_main_dir.glob("*/config"):
            try:
                result = run_cmd(
                    ["git", "config", "-f", str(repo_config), "remote.origin.url"],
                    capture=True,
                    check=False,
                )
                remote_url = result.stdout.strip() if result.returncode == 0 else ""

                token_patterns = ["x-access-token:", "ghs_", "ghp_", "github_pat_"]
                if remote_url and any(p in remote_url for p in token_patterns):
                    print("WARNING: Git remote URL was modified during session!")
                    print(f"  Found token in: {repo_config}")
                    import re

                    clean_url = re.sub(
                        r"https://[^@]*@github\.com/", "https://github.com/", remote_url
                    )
                    run_cmd(
                        ["git", "config", "-f", str(repo_config), "remote.origin.url", clean_url]
                    )
                    print(f"  Cleaned: {remote_url} -> {clean_url}")
            except Exception:
                pass

    if not config.quiet:
        print("✓ Cleanup complete")


# =============================================================================
# Main Entry Points
# =============================================================================


def run_interactive(config: Config, logger: Logger) -> None:
    """Launch interactive LLM session."""
    # Start the router (timed phase)
    with _startup_timer.phase("start_router"):
        start_router(config, logger)

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

    # Build environment for LLM
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": "/opt/jib-runtime/jib-container:/opt/jib-runtime/shared",
            "LLM_PROVIDER": config.llm_provider,
            "GOOGLE_API_KEY": config.google_api_key or "",
            "GEMINI_API_KEY": config.google_api_key or "",
            "GEMINI_MODEL": config.gemini_model or "",
            # Pass through router environment
            "ANTHROPIC_BASE_URL": os.environ.get("ANTHROPIC_BASE_URL", ""),
            "ANTHROPIC_AUTH_TOKEN": os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
            "NO_PROXY": os.environ.get("NO_PROXY", "127.0.0.1"),
            "DISABLE_TELEMETRY": os.environ.get("DISABLE_TELEMETRY", ""),
            "DISABLE_COST_WARNINGS": os.environ.get("DISABLE_COST_WARNINGS", ""),
        }
    )

    logger.info(f"Launching LLM interactive mode (provider: {config.llm_provider})...")

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

    if config.llm_provider in ("google", "gemini"):
        # Gemini native mode - no router needed
        logger.info("Exec mode with Gemini CLI environment")
        env["GOOGLE_API_KEY"] = config.google_api_key or ""
        env["GEMINI_API_KEY"] = config.google_api_key or ""
    # Claude/OpenAI - start router for claude-agent-sdk compatibility
    elif config.router_config.exists():
        logger.info("Starting claude-code-router for exec mode...")
        with _startup_timer.phase("start_router"):
            start_router(config, logger)

        # Pass through router environment
        env["ANTHROPIC_BASE_URL"] = os.environ.get("ANTHROPIC_BASE_URL", "")
        env["ANTHROPIC_AUTH_TOKEN"] = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")

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

    with _startup_timer.phase("setup_gemini"):
        setup_gemini(config, logger)

    with _startup_timer.phase("setup_router"):
        setup_router(config, logger)

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

    with _startup_timer.phase("generate_docs_indexes"):
        generate_docs_indexes(config, logger)

    # Run appropriate mode (timing summary is printed inside each mode)
    if len(sys.argv) == 1:
        run_interactive(config, logger)
    else:
        run_exec(config, logger, sys.argv[1:])


if __name__ == "__main__":
    main()
