"""
Tests for git worktree isolation implementation.

Tests the Container Worktree Isolation ADR implementation:
- Mount structure generation in runtime.py
- Worktree setup logic in entrypoint.py
- gitdir backup/restore mechanism
- Cleanup script functionality

These tests can run on the host machine without Docker.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Load modules under test
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "jib-container"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "jib-container" / "jib_lib"))


class TestMountStructure:
    """Tests for _setup_git_isolation_mounts in runtime.py."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repository with worktree structure."""
        # Create main repo
        repo_path = tmp_path / "source_repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()

        # Create git directory structure
        (git_dir / "objects").mkdir()
        (git_dir / "refs" / "heads").mkdir(parents=True)
        (git_dir / "hooks").mkdir()
        (git_dir / "worktrees").mkdir()
        (git_dir / "config").write_text("[core]\n\trepositoryformatversion = 0\n")
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
        (git_dir / "packed-refs").write_text("# pack-refs with: peeled fully-peeled sorted\n")

        # Create worktree admin directory
        worktree_admin = git_dir / "worktrees" / "test-repo"
        worktree_admin.mkdir()
        (worktree_admin / "HEAD").write_text("ref: refs/heads/test-branch\n")
        (worktree_admin / "index").write_bytes(b"")
        (worktree_admin / "gitdir").write_text(f"{tmp_path}/worktree/test-repo\n")
        (worktree_admin / "commondir").write_text("../..\n")

        # Create worktree working directory
        worktree_path = tmp_path / "worktree" / "test-repo"
        worktree_path.mkdir(parents=True)
        (worktree_path / ".git").write_text(f"gitdir: {worktree_admin}\n")

        return {
            "repo_path": repo_path,
            "git_dir": git_dir,
            "worktree_admin": worktree_admin,
            "worktree_path": worktree_path,
        }

    def test_mount_args_include_worktree_admin(self, git_repo):
        """Test that mount args include worktree admin directory."""
        from runtime import _setup_git_isolation_mounts

        worktrees = {
            "test-repo": {
                "worktree": git_repo["worktree_path"],
                "source": git_repo["repo_path"],
            }
        }
        mount_args = []

        _setup_git_isolation_mounts(worktrees, "test-container", mount_args, quiet=True)

        # Check worktree admin mount
        admin_mount = f"{git_repo['worktree_admin']}:/home/jib/.git-admin/test-repo:rw"
        assert any(admin_mount in arg for arg in mount_args), (
            f"Expected admin mount in {mount_args}"
        )

    def test_mount_args_include_objects_rw(self, git_repo):
        """Test that objects directory is mounted as rw."""
        from runtime import _setup_git_isolation_mounts

        worktrees = {
            "test-repo": {
                "worktree": git_repo["worktree_path"],
                "source": git_repo["repo_path"],
            }
        }
        mount_args = []

        _setup_git_isolation_mounts(worktrees, "test-container", mount_args, quiet=True)

        # Check objects mount is rw
        objects_path = git_repo["git_dir"] / "objects"
        objects_mount = f"{objects_path}:/home/jib/.git-common/test-repo/objects:rw"
        assert any(objects_mount in arg for arg in mount_args), (
            f"Expected objects mount in {mount_args}"
        )

    def test_mount_args_include_refs_rw(self, git_repo):
        """Test that refs directory is mounted as rw."""
        from runtime import _setup_git_isolation_mounts

        worktrees = {
            "test-repo": {
                "worktree": git_repo["worktree_path"],
                "source": git_repo["repo_path"],
            }
        }
        mount_args = []

        _setup_git_isolation_mounts(worktrees, "test-container", mount_args, quiet=True)

        # Check refs mount is rw
        refs_path = git_repo["git_dir"] / "refs"
        refs_mount = f"{refs_path}:/home/jib/.git-common/test-repo/refs:rw"
        assert any(refs_mount in arg for arg in mount_args), f"Expected refs mount in {mount_args}"

    def test_mount_args_include_packed_refs(self, git_repo):
        """Test that packed-refs file is mounted when it exists."""
        from runtime import _setup_git_isolation_mounts

        worktrees = {
            "test-repo": {
                "worktree": git_repo["worktree_path"],
                "source": git_repo["repo_path"],
            }
        }
        mount_args = []

        _setup_git_isolation_mounts(worktrees, "test-container", mount_args, quiet=True)

        # Check packed-refs mount
        packed_refs_path = git_repo["git_dir"] / "packed-refs"
        packed_refs_mount = f"{packed_refs_path}:/home/jib/.git-common/test-repo/packed-refs:rw"
        assert any(packed_refs_mount in arg for arg in mount_args), (
            f"Expected packed-refs mount in {mount_args}"
        )

    def test_mount_args_include_config_ro(self, git_repo):
        """Test that config file is mounted as ro."""
        from runtime import _setup_git_isolation_mounts

        worktrees = {
            "test-repo": {
                "worktree": git_repo["worktree_path"],
                "source": git_repo["repo_path"],
            }
        }
        mount_args = []

        _setup_git_isolation_mounts(worktrees, "test-container", mount_args, quiet=True)

        # Check config mount is ro
        config_path = git_repo["git_dir"] / "config"
        config_mount = f"{config_path}:/home/jib/.git-common/test-repo/config:ro"
        assert any(config_mount in arg for arg in mount_args), (
            f"Expected config mount in {mount_args}"
        )

    def test_mount_args_include_hooks_ro(self, git_repo):
        """Test that hooks directory is mounted as ro."""
        from runtime import _setup_git_isolation_mounts

        worktrees = {
            "test-repo": {
                "worktree": git_repo["worktree_path"],
                "source": git_repo["repo_path"],
            }
        }
        mount_args = []

        _setup_git_isolation_mounts(worktrees, "test-container", mount_args, quiet=True)

        # Check hooks mount is ro
        hooks_path = git_repo["git_dir"] / "hooks"
        hooks_mount = f"{hooks_path}:/home/jib/.git-common/test-repo/hooks:ro"
        assert any(hooks_mount in arg for arg in mount_args), (
            f"Expected hooks mount in {mount_args}"
        )

    def test_no_local_objects_mount(self, git_repo):
        """Test that local objects directory is NOT mounted (removed in new implementation)."""
        from runtime import _setup_git_isolation_mounts

        worktrees = {
            "test-repo": {
                "worktree": git_repo["worktree_path"],
                "source": git_repo["repo_path"],
            }
        }
        mount_args = []

        _setup_git_isolation_mounts(worktrees, "test-container", mount_args, quiet=True)

        # Verify no local-objects mount
        mount_str = " ".join(mount_args)
        assert ".git-local-objects" not in mount_str, "Local objects mount should be removed"

    def test_no_full_git_common_mount(self, git_repo):
        """Test that full git-common directory is NOT mounted (replaced by individual mounts)."""
        from runtime import _setup_git_isolation_mounts

        worktrees = {
            "test-repo": {
                "worktree": git_repo["worktree_path"],
                "source": git_repo["repo_path"],
            }
        }
        mount_args = []

        _setup_git_isolation_mounts(worktrees, "test-container", mount_args, quiet=True)

        # Verify no full git-common mount (should only have subdirectory mounts)
        git_common_full_mount = f"{git_repo['git_dir']}:/home/jib/.git-common/test-repo:ro"
        assert not any(git_common_full_mount in arg for arg in mount_args), (
            "Full git-common mount should be removed"
        )

    def test_multiple_repos(self, tmp_path):
        """Test mount structure with multiple repositories."""
        from runtime import _setup_git_isolation_mounts

        repos = {}
        worktrees = {}

        # Create two repos
        for repo_name in ["repo-a", "repo-b"]:
            repo_path = tmp_path / f"source_{repo_name}"
            repo_path.mkdir()
            git_dir = repo_path / ".git"
            git_dir.mkdir()
            (git_dir / "objects").mkdir()
            (git_dir / "refs").mkdir()
            (git_dir / "hooks").mkdir()
            (git_dir / "worktrees" / repo_name).mkdir(parents=True)
            (git_dir / "config").write_text("[core]\n")
            (git_dir / "worktrees" / repo_name / "HEAD").write_text("ref: refs/heads/main\n")

            worktree_path = tmp_path / "worktrees" / repo_name
            worktree_path.mkdir(parents=True)
            (worktree_path / ".git").write_text(f"gitdir: {git_dir}/worktrees/{repo_name}\n")

            repos[repo_name] = {"git_dir": git_dir, "worktree_path": worktree_path}
            worktrees[repo_name] = {"worktree": worktree_path, "source": repo_path}

        mount_args = []
        _setup_git_isolation_mounts(worktrees, "test-container", mount_args, quiet=True)

        # Verify both repos have their own mounts
        for repo_name in ["repo-a", "repo-b"]:
            assert any(f".git-admin/{repo_name}" in arg for arg in mount_args), (
                f"Missing admin mount for {repo_name}"
            )
            assert any(f".git-common/{repo_name}/objects" in arg for arg in mount_args), (
                f"Missing objects mount for {repo_name}"
            )


class TestWorktreeSetup:
    """Tests for setup_worktrees in entrypoint.py."""

    @pytest.fixture
    def container_env(self, tmp_path, monkeypatch):
        """Set up a mock container environment."""
        # Create directory structure
        repos_dir = tmp_path / "repos"
        repos_dir.mkdir()
        git_admin_dir = tmp_path / ".git-admin"
        git_admin_dir.mkdir()
        git_common_dir = tmp_path / ".git-common"
        git_common_dir.mkdir()

        # Create a repo with worktree
        repo_name = "test-repo"
        repo_dir = repos_dir / repo_name
        repo_dir.mkdir()

        # Create worktree admin dir
        admin_dir = git_admin_dir / repo_name
        admin_dir.mkdir()
        (admin_dir / "HEAD").write_text("ref: refs/heads/test-branch\n")
        (admin_dir / "index").write_bytes(b"")
        (admin_dir / "gitdir").write_text(f"/host/path/to/worktree/{repo_name}\n")
        (admin_dir / "commondir").write_text("/host/path/to/.git\n")

        # Create .git file in repo (marks it as a worktree)
        (repo_dir / ".git").write_text(f"gitdir: /host/path/to/.git/worktrees/{repo_name}\n")

        # Create git-common structure (simulating mounted components)
        common_repo_dir = git_common_dir / repo_name
        common_repo_dir.mkdir()
        (common_repo_dir / "objects").mkdir()
        (common_repo_dir / "refs").mkdir()

        return {
            "tmp_path": tmp_path,
            "repos_dir": repos_dir,
            "git_admin_dir": git_admin_dir,
            "git_common_dir": git_common_dir,
            "repo_dir": repo_dir,
            "admin_dir": admin_dir,
        }

    def test_gitdir_backup_created(self, container_env):
        """Test that gitdir.host-backup is created on setup."""
        import entrypoint

        admin_dir = container_env["admin_dir"]
        original_gitdir = (admin_dir / "gitdir").read_text()

        # Create mock config
        config = MagicMock()
        config.repos_dir = container_env["repos_dir"]
        config.git_admin_dir = container_env["git_admin_dir"]
        config.git_common_dir = container_env["git_common_dir"]
        config.git_main_dir = container_env["tmp_path"] / ".git-main"  # Doesn't exist
        config.runtime_uid = os.getuid()
        config.runtime_gid = os.getgid()

        logger = MagicMock()

        # Patch run_cmd_with_retry to avoid git config calls
        with patch.object(entrypoint, "run_cmd_with_retry"):
            result = entrypoint.setup_worktrees(config, logger)

        assert result is True
        assert (admin_dir / "gitdir.host-backup").exists()
        assert (admin_dir / "gitdir.host-backup").read_text() == original_gitdir

    def test_gitdir_rewritten_with_container_path(self, container_env):
        """Test that gitdir is rewritten with container-internal path."""
        import entrypoint

        admin_dir = container_env["admin_dir"]

        config = MagicMock()
        config.repos_dir = container_env["repos_dir"]
        config.git_admin_dir = container_env["git_admin_dir"]
        config.git_common_dir = container_env["git_common_dir"]
        config.git_main_dir = container_env["tmp_path"] / ".git-main"
        config.runtime_uid = os.getuid()
        config.runtime_gid = os.getgid()

        logger = MagicMock()

        with patch.object(entrypoint, "run_cmd_with_retry"):
            entrypoint.setup_worktrees(config, logger)

        gitdir_content = (admin_dir / "gitdir").read_text().strip()
        assert gitdir_content == "/home/jib/repos/test-repo"

    def test_commondir_backup_created(self, container_env):
        """Test that commondir.host-backup is created on setup."""
        import entrypoint

        admin_dir = container_env["admin_dir"]
        original_commondir = (admin_dir / "commondir").read_text()

        config = MagicMock()
        config.repos_dir = container_env["repos_dir"]
        config.git_admin_dir = container_env["git_admin_dir"]
        config.git_common_dir = container_env["git_common_dir"]
        config.git_main_dir = container_env["tmp_path"] / ".git-main"
        config.runtime_uid = os.getuid()
        config.runtime_gid = os.getgid()

        logger = MagicMock()

        with patch.object(entrypoint, "run_cmd_with_retry"):
            result = entrypoint.setup_worktrees(config, logger)

        assert result is True
        assert (admin_dir / "commondir.host-backup").exists()
        assert (admin_dir / "commondir.host-backup").read_text() == original_commondir

    def test_commondir_set_to_git_common(self, container_env):
        """Test that commondir is set to .git-common/{repo}."""
        import entrypoint

        admin_dir = container_env["admin_dir"]

        config = MagicMock()
        config.repos_dir = container_env["repos_dir"]
        config.git_admin_dir = container_env["git_admin_dir"]
        config.git_common_dir = container_env["git_common_dir"]
        config.git_main_dir = container_env["tmp_path"] / ".git-main"
        config.runtime_uid = os.getuid()
        config.runtime_gid = os.getgid()

        logger = MagicMock()

        with patch.object(entrypoint, "run_cmd_with_retry"):
            entrypoint.setup_worktrees(config, logger)

        commondir_content = (admin_dir / "commondir").read_text().strip()
        expected = str(container_env["git_common_dir"] / "test-repo")
        assert commondir_content == expected

    def test_git_file_updated(self, container_env):
        """Test that .git file is updated to point to admin dir."""
        import entrypoint

        repo_dir = container_env["repo_dir"]

        config = MagicMock()
        config.repos_dir = container_env["repos_dir"]
        config.git_admin_dir = container_env["git_admin_dir"]
        config.git_common_dir = container_env["git_common_dir"]
        config.git_main_dir = container_env["tmp_path"] / ".git-main"
        config.runtime_uid = os.getuid()
        config.runtime_gid = os.getgid()

        logger = MagicMock()

        with patch.object(entrypoint, "run_cmd_with_retry"):
            entrypoint.setup_worktrees(config, logger)

        git_content = (repo_dir / ".git").read_text().strip()
        expected = f"gitdir: {container_env['git_admin_dir']}/test-repo"
        assert git_content == expected

    def test_no_backup_if_already_exists(self, container_env):
        """Test that backup is not overwritten if it already exists."""
        import entrypoint

        admin_dir = container_env["admin_dir"]

        # Create existing backup with different content
        backup_content = "/original/backup/path\n"
        (admin_dir / "gitdir.host-backup").write_text(backup_content)

        config = MagicMock()
        config.repos_dir = container_env["repos_dir"]
        config.git_admin_dir = container_env["git_admin_dir"]
        config.git_common_dir = container_env["git_common_dir"]
        config.git_main_dir = container_env["tmp_path"] / ".git-main"
        config.runtime_uid = os.getuid()
        config.runtime_gid = os.getgid()

        logger = MagicMock()

        with patch.object(entrypoint, "run_cmd_with_retry"):
            entrypoint.setup_worktrees(config, logger)

        # Backup should not be changed
        assert (admin_dir / "gitdir.host-backup").read_text() == backup_content


class TestCleanupOnExit:
    """Tests for cleanup_on_exit in entrypoint.py."""

    @pytest.fixture
    def cleanup_env(self, tmp_path):
        """Set up environment for cleanup tests."""
        git_admin_dir = tmp_path / ".git-admin"
        git_admin_dir.mkdir()

        # Create repo admin dir with backups for both gitdir and commondir
        repo_admin = git_admin_dir / "test-repo"
        repo_admin.mkdir()
        (repo_admin / "gitdir").write_text("/home/jib/repos/test-repo\n")
        (repo_admin / "gitdir.host-backup").write_text("/host/original/path\n")
        (repo_admin / "commondir").write_text("/home/jib/.git-common/test-repo\n")
        (repo_admin / "commondir.host-backup").write_text("/host/original/.git\n")

        return {
            "tmp_path": tmp_path,
            "git_admin_dir": git_admin_dir,
            "repo_admin": repo_admin,
        }

    def test_gitdir_restored_from_backup(self, cleanup_env):
        """Test that gitdir is restored from backup on cleanup."""
        import entrypoint

        repo_admin = cleanup_env["repo_admin"]

        config = MagicMock()
        config.git_admin_dir = cleanup_env["git_admin_dir"]
        config.git_main_dir = cleanup_env["tmp_path"] / ".git-main"  # Doesn't exist
        config.quiet = True

        logger = MagicMock()

        entrypoint.cleanup_on_exit(config, logger)

        assert (repo_admin / "gitdir").read_text() == "/host/original/path\n"

    def test_backup_removed_after_restore(self, cleanup_env):
        """Test that backup files are removed after successful restore."""
        import entrypoint

        repo_admin = cleanup_env["repo_admin"]

        config = MagicMock()
        config.git_admin_dir = cleanup_env["git_admin_dir"]
        config.git_main_dir = cleanup_env["tmp_path"] / ".git-main"
        config.quiet = True

        logger = MagicMock()

        entrypoint.cleanup_on_exit(config, logger)

        assert not (repo_admin / "gitdir.host-backup").exists()
        assert not (repo_admin / "commondir.host-backup").exists()

    def test_commondir_restored_from_backup(self, cleanup_env):
        """Test that commondir is restored from backup on cleanup."""
        import entrypoint

        repo_admin = cleanup_env["repo_admin"]

        config = MagicMock()
        config.git_admin_dir = cleanup_env["git_admin_dir"]
        config.git_main_dir = cleanup_env["tmp_path"] / ".git-main"
        config.quiet = True

        logger = MagicMock()

        entrypoint.cleanup_on_exit(config, logger)

        assert (repo_admin / "commondir").read_text() == "/host/original/.git\n"

    def test_multiple_repos_cleaned(self, cleanup_env):
        """Test that multiple repos are cleaned up."""
        import entrypoint

        git_admin_dir = cleanup_env["git_admin_dir"]

        # Add second repo with both gitdir and commondir backups
        repo2_admin = git_admin_dir / "repo-2"
        repo2_admin.mkdir()
        (repo2_admin / "gitdir").write_text("/home/jib/repos/repo-2\n")
        (repo2_admin / "gitdir.host-backup").write_text("/host/original/repo2\n")
        (repo2_admin / "commondir").write_text("/home/jib/.git-common/repo-2\n")
        (repo2_admin / "commondir.host-backup").write_text("/host/original/repo2/.git\n")

        config = MagicMock()
        config.git_admin_dir = git_admin_dir
        config.git_main_dir = cleanup_env["tmp_path"] / ".git-main"
        config.quiet = True

        logger = MagicMock()

        entrypoint.cleanup_on_exit(config, logger)

        # Both repos should have gitdir and commondir restored
        assert (cleanup_env["repo_admin"] / "gitdir").read_text() == "/host/original/path\n"
        assert (cleanup_env["repo_admin"] / "commondir").read_text() == "/host/original/.git\n"
        assert (repo2_admin / "gitdir").read_text() == "/host/original/repo2\n"
        assert (repo2_admin / "commondir").read_text() == "/host/original/repo2/.git\n"

        # All backups should be removed
        assert not (cleanup_env["repo_admin"] / "gitdir.host-backup").exists()
        assert not (cleanup_env["repo_admin"] / "commondir.host-backup").exists()
        assert not (repo2_admin / "gitdir.host-backup").exists()
        assert not (repo2_admin / "commondir.host-backup").exists()

    def test_no_error_without_backup(self, cleanup_env):
        """Test that cleanup doesn't error if no backup exists."""
        import entrypoint

        repo_admin = cleanup_env["repo_admin"]

        # Remove backups
        (repo_admin / "gitdir.host-backup").unlink()
        (repo_admin / "commondir.host-backup").unlink()

        config = MagicMock()
        config.git_admin_dir = cleanup_env["git_admin_dir"]
        config.git_main_dir = cleanup_env["tmp_path"] / ".git-main"
        config.quiet = True

        logger = MagicMock()

        # Should not raise
        entrypoint.cleanup_on_exit(config, logger)

        # Files should be unchanged (no backup to restore from)
        assert (repo_admin / "gitdir").read_text() == "/home/jib/repos/test-repo\n"
        assert (repo_admin / "commondir").read_text() == "/home/jib/.git-common/test-repo\n"


class TestCleanupScript:
    """Tests for bin/jib-cleanup-worktree script."""

    @pytest.fixture
    def script_path(self):
        """Return path to the cleanup script."""
        return Path(__file__).parent.parent.parent / "scripts" / "jib-cleanup-worktree"

    def test_script_exists(self, script_path):
        """Test that the cleanup script exists."""
        assert script_path.exists(), f"Script not found at {script_path}"

    def test_script_is_executable(self, script_path):
        """Test that the cleanup script is executable."""
        assert os.access(script_path, os.X_OK), "Script is not executable"

    def test_script_dry_run(self, script_path, tmp_path, monkeypatch):
        """Test that --dry-run shows what would be restored without changes."""
        # Create mock git directory structure
        git_dir = tmp_path / ".git" / "test-repo" / "worktrees" / "test-worktree"
        git_dir.mkdir(parents=True)
        (git_dir / "gitdir").write_text("/container/path\n")
        (git_dir / "gitdir.host-backup").write_text("/host/original/path\n")

        # Change HOME to tmp_path so script finds the backup
        monkeypatch.setenv("HOME", str(tmp_path))

        result = subprocess.run(
            [str(script_path), "--dry-run"],
            capture_output=True,
            text=True,
        )

        # Script should succeed
        assert result.returncode == 0

        # Should mention dry run
        assert "dry run" in result.stdout.lower() or "would restore" in result.stdout.lower()

        # Backup should still exist (not actually restored)
        assert (git_dir / "gitdir.host-backup").exists()
        assert (git_dir / "gitdir").read_text() == "/container/path\n"

    def test_script_restores_backup(self, script_path, tmp_path, monkeypatch):
        """Test that script restores gitdir and commondir from backups."""
        # Create mock git directory structure
        git_dir = tmp_path / ".git" / "test-repo" / "worktrees" / "test-worktree"
        git_dir.mkdir(parents=True)
        (git_dir / "gitdir").write_text("/container/path\n")
        (git_dir / "gitdir.host-backup").write_text("/host/original/path\n")
        (git_dir / "commondir").write_text("/home/jib/.git-common/test-repo\n")
        (git_dir / "commondir.host-backup").write_text("../..\n")

        monkeypatch.setenv("HOME", str(tmp_path))

        result = subprocess.run(
            [str(script_path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

        # gitdir should be restored
        assert (git_dir / "gitdir").read_text() == "/host/original/path\n"

        # commondir should be restored
        assert (git_dir / "commondir").read_text() == "../..\n"

        # Backups should be removed
        assert not (git_dir / "gitdir.host-backup").exists()
        assert not (git_dir / "commondir.host-backup").exists()

    def test_script_no_backups(self, script_path, tmp_path, monkeypatch):
        """Test that script handles no backups gracefully."""
        monkeypatch.setenv("HOME", str(tmp_path))

        result = subprocess.run(
            [str(script_path), "--verbose"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0


class TestConfigProperties:
    """Tests for Config properties in entrypoint.py."""

    def test_git_admin_dir_path(self):
        """Test git_admin_dir returns correct path."""
        import entrypoint

        config = entrypoint.Config()
        assert config.git_admin_dir == Path("/home/jib/.git-admin")

    def test_git_common_dir_path(self):
        """Test git_common_dir returns correct path."""
        import entrypoint

        config = entrypoint.Config()
        assert config.git_common_dir == Path("/home/jib/.git-common")

    def test_obsolete_properties_removed(self):
        """Test that obsolete properties are removed."""
        import entrypoint

        config = entrypoint.Config()

        # These properties should no longer exist
        assert not hasattr(config, "git_local_objects_dir")
        assert not hasattr(config, "git_shared_objects_dir")
        assert not hasattr(config, "git_shared_refs_dir")


class TestHostWorktreeIntegration:
    """Integration tests that verify host worktree operations work correctly.

    These tests create actual git repositories and worktrees to verify
    the implementation works end-to-end.
    """

    @pytest.fixture
    def real_git_repo(self, tmp_path):
        """Create a real git repository with a worktree."""
        # Create main repo
        main_repo = tmp_path / "main-repo"
        main_repo.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=main_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=main_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=main_repo,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        (main_repo / "README.md").write_text("# Test Repo\n")
        subprocess.run(["git", "add", "README.md"], cwd=main_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=main_repo,
            check=True,
            capture_output=True,
        )

        # Create worktree
        worktree_path = tmp_path / "worktree"
        subprocess.run(
            ["git", "worktree", "add", "-b", "test-branch", str(worktree_path)],
            cwd=main_repo,
            check=True,
            capture_output=True,
        )

        return {
            "main_repo": main_repo,
            "worktree_path": worktree_path,
            "git_dir": main_repo / ".git",
        }

    def test_worktree_has_correct_structure(self, real_git_repo):
        """Test that git worktree has expected structure."""
        worktree_path = real_git_repo["worktree_path"]
        git_dir = real_git_repo["git_dir"]

        # .git file should exist in worktree
        assert (worktree_path / ".git").is_file()

        # Worktree admin dir should exist
        worktree_name = worktree_path.name
        admin_dir = git_dir / "worktrees" / worktree_name
        assert admin_dir.is_dir()

        # Admin dir should have required files
        assert (admin_dir / "HEAD").exists()
        assert (admin_dir / "gitdir").exists()
        assert (admin_dir / "commondir").exists()

    def test_gitdir_backup_restore_cycle(self, real_git_repo):
        """Test complete backup/restore cycle for gitdir."""
        git_dir = real_git_repo["git_dir"]
        worktree_name = real_git_repo["worktree_path"].name
        admin_dir = git_dir / "worktrees" / worktree_name

        # Save original gitdir content
        original_gitdir = (admin_dir / "gitdir").read_text()

        # Simulate container startup: backup and rewrite
        backup_path = admin_dir / "gitdir.host-backup"
        shutil.copy2(admin_dir / "gitdir", backup_path)
        (admin_dir / "gitdir").write_text("/home/jib/repos/worktree\n")

        # Verify git operations still work in main repo
        result = subprocess.run(
            ["git", "status"],
            cwd=real_git_repo["main_repo"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Simulate container exit: restore
        shutil.copy2(backup_path, admin_dir / "gitdir")
        backup_path.unlink()

        # Verify gitdir is restored
        assert (admin_dir / "gitdir").read_text() == original_gitdir
        assert not backup_path.exists()

        # Verify worktree operations work
        result = subprocess.run(
            ["git", "status"],
            cwd=real_git_repo["worktree_path"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_commondir_modification_doesnt_break_main_repo(self, real_git_repo):
        """Test that modifying commondir doesn't break main repo operations."""
        git_dir = real_git_repo["git_dir"]
        worktree_name = real_git_repo["worktree_path"].name
        admin_dir = git_dir / "worktrees" / worktree_name

        # Save original commondir
        original_commondir = (admin_dir / "commondir").read_text()

        # Simulate container: change commondir to container path
        (admin_dir / "commondir").write_text("/home/jib/.git-common/test-repo\n")

        # Main repo should still work (commondir only affects worktree)
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=real_git_repo["main_repo"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Restore commondir
        (admin_dir / "commondir").write_text(original_commondir)

        # Worktree should work again
        result = subprocess.run(
            ["git", "status"],
            cwd=real_git_repo["worktree_path"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_worktree_fails_without_commondir_restore(self, real_git_repo):
        """Test that worktree FAILS if commondir points to non-existent container path.

        This demonstrates WHY we need backup/restore for commondir:
        - Container writes /home/jib/.git-common/repo to commondir
        - After container exit, this path doesn't exist on host
        - Git operations on worktree fail with "unable to read commondir"

        The backup/restore mechanism in entrypoint.py prevents this.
        """
        git_dir = real_git_repo["git_dir"]
        worktree_name = real_git_repo["worktree_path"].name
        admin_dir = git_dir / "worktrees" / worktree_name

        # Save original commondir for cleanup
        original_commondir = (admin_dir / "commondir").read_text()

        try:
            # Simulate container exit WITHOUT restore (crash scenario)
            (admin_dir / "commondir").write_text("/home/jib/.git-common/test-repo\n")

            # Worktree operations should FAIL because commondir path doesn't exist
            result = subprocess.run(
                ["git", "status"],
                cwd=real_git_repo["worktree_path"],
                capture_output=True,
                text=True,
            )

            # This SHOULD fail - that's the bug we're protecting against
            assert result.returncode != 0, (
                "Expected git status to fail with invalid commondir, "
                "but it succeeded. This test verifies the need for backup/restore."
            )
            assert "commondir" in result.stderr.lower() or "fatal" in result.stderr.lower()

        finally:
            # Always restore for test cleanup
            (admin_dir / "commondir").write_text(original_commondir)

    def test_commondir_backup_restore_cycle(self, real_git_repo):
        """Test complete backup/restore cycle for commondir (same as gitdir test)."""
        git_dir = real_git_repo["git_dir"]
        worktree_name = real_git_repo["worktree_path"].name
        admin_dir = git_dir / "worktrees" / worktree_name

        # Save original commondir content
        original_commondir = (admin_dir / "commondir").read_text()

        # Simulate container startup: backup and rewrite
        backup_path = admin_dir / "commondir.host-backup"
        shutil.copy2(admin_dir / "commondir", backup_path)
        (admin_dir / "commondir").write_text("/home/jib/.git-common/test-repo\n")

        # Main repo should still work
        result = subprocess.run(
            ["git", "status"],
            cwd=real_git_repo["main_repo"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Simulate container exit: restore
        shutil.copy2(backup_path, admin_dir / "commondir")
        backup_path.unlink()

        # Verify commondir is restored
        assert (admin_dir / "commondir").read_text() == original_commondir
        assert not backup_path.exists()

        # Verify worktree operations work after restore
        result = subprocess.run(
            ["git", "status"],
            cwd=real_git_repo["worktree_path"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
