"""Tests for jib_logging.wrappers.bd module."""

from unittest.mock import MagicMock, patch

from jib_logging.wrappers.bd import BdWrapper


class TestBdWrapper:
    """Tests for BdWrapper class."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = BdWrapper()

    def test_tool_name_is_bd(self):
        """Test that tool_name is 'bd'."""
        assert self.wrapper.tool_name == "bd"


class TestBdCreate:
    """Tests for BdWrapper.create() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = BdWrapper()

    @patch.object(BdWrapper, "run")
    def test_create_basic(self, mock_run):
        """Test basic task creation."""
        mock_run.return_value = MagicMock(
            exit_code=0,
            stdout="Created issue: beads-abc123",
        )

        self.wrapper.create("Fix login bug")

        mock_run.assert_called_once()
        args = mock_run.call_args[0]
        assert "--allow-stale" in args
        assert "create" in args
        assert "Fix login bug" in args

    @patch.object(BdWrapper, "run")
    def test_create_with_labels(self, mock_run):
        """Test task creation with labels."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.create("Fix bug", labels=["bug", "auth"])

        args = mock_run.call_args[0]
        assert "--labels" in args
        labels_idx = args.index("--labels")
        assert args[labels_idx + 1] == "bug,auth"

    @patch.object(BdWrapper, "run")
    def test_create_with_description(self, mock_run):
        """Test task creation with description."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.create("Fix bug", description="Detailed description")

        args = mock_run.call_args[0]
        assert "--description" in args

    @patch.object(BdWrapper, "run")
    def test_create_with_parent(self, mock_run):
        """Test task creation with parent task."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.create("Subtask", parent="beads-parent")

        args = mock_run.call_args[0]
        assert "--parent" in args
        assert "beads-parent" in args

    @patch.object(BdWrapper, "run")
    def test_create_with_priority(self, mock_run):
        """Test task creation with priority."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.create("Urgent task", priority="P0")

        args = mock_run.call_args[0]
        assert "--priority" in args
        assert "P0" in args

    @patch.object(BdWrapper, "run")
    def test_create_without_allow_stale(self, mock_run):
        """Test task creation without --allow-stale."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.create("Task", allow_stale=False)

        args = mock_run.call_args[0]
        assert "--allow-stale" not in args


class TestBdUpdate:
    """Tests for BdWrapper.update() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = BdWrapper()

    @patch.object(BdWrapper, "run")
    def test_update_status(self, mock_run):
        """Test updating task status."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.update("beads-abc123", status="in_progress")

        args = mock_run.call_args[0]
        assert "update" in args
        assert "beads-abc123" in args
        assert "--status" in args
        assert "in_progress" in args

    @patch.object(BdWrapper, "run")
    def test_update_with_notes(self, mock_run):
        """Test updating task with notes."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.update("beads-abc123", notes="Progress made")

        args = mock_run.call_args[0]
        assert "--notes" in args
        assert "Progress made" in args

    @patch.object(BdWrapper, "run")
    def test_update_multiple_fields(self, mock_run):
        """Test updating multiple fields at once."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.update(
            "beads-abc123",
            status="closed",
            notes="Completed",
            priority="P2",
        )

        args = mock_run.call_args[0]
        assert "--status" in args
        assert "--notes" in args
        assert "--priority" in args


class TestBdShow:
    """Tests for BdWrapper.show() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = BdWrapper()

    @patch.object(BdWrapper, "run")
    def test_show_task(self, mock_run):
        """Test showing task details."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="Task details...")

        self.wrapper.show("beads-abc123")

        args = mock_run.call_args[0]
        assert "show" in args
        assert "beads-abc123" in args


class TestBdList:
    """Tests for BdWrapper.list() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = BdWrapper()

    @patch.object(BdWrapper, "run")
    def test_list_basic(self, mock_run):
        """Test basic task listing."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.list()

        args = mock_run.call_args[0]
        assert "list" in args

    @patch.object(BdWrapper, "run")
    def test_list_by_status(self, mock_run):
        """Test listing tasks by status."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.list(status="in_progress")

        args = mock_run.call_args[0]
        assert "--status" in args
        assert "in_progress" in args

    @patch.object(BdWrapper, "run")
    def test_list_by_label(self, mock_run):
        """Test listing tasks by label."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.list(label="task-12345")

        args = mock_run.call_args[0]
        assert "--label" in args
        assert "task-12345" in args


class TestBdSearch:
    """Tests for BdWrapper.search() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = BdWrapper()

    @patch.object(BdWrapper, "run")
    def test_search_basic(self, mock_run):
        """Test basic search."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.search("login bug")

        args = mock_run.call_args[0]
        assert "search" in args
        assert "login bug" in args


class TestBdReady:
    """Tests for BdWrapper.ready() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = BdWrapper()

    @patch.object(BdWrapper, "run")
    def test_ready_basic(self, mock_run):
        """Test listing ready tasks."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.ready()

        args = mock_run.call_args[0]
        assert "ready" in args


class TestBdContextExtraction:
    """Tests for context extraction in BdWrapper."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = BdWrapper()

    def test_extracts_task_id_from_create_output(self):
        """Test that task ID is extracted from create output."""
        context = self.wrapper._extract_context(
            ("--allow-stale", "create", "New task"),
            "Created issue: beads-xyz789\n",
            "",
        )
        assert context.get("task_id") == "beads-xyz789"

    def test_extracts_task_id_from_args(self):
        """Test that task ID is extracted from command args."""
        context = self.wrapper._extract_context(
            ("--allow-stale", "update", "beads-abc123", "--status", "done"),
            "",
            "",
        )
        assert context.get("task_id") == "beads-abc123"

    def test_extracts_subcommand(self):
        """Test that subcommand is extracted."""
        context = self.wrapper._extract_context(
            ("--allow-stale", "update", "beads-abc123"),
            "",
            "",
        )
        assert context.get("subcommand") == "update"

    def test_extracts_new_status(self):
        """Test that new status is extracted."""
        context = self.wrapper._extract_context(
            ("--allow-stale", "update", "beads-abc123", "--status", "in_progress"),
            "",
            "",
        )
        assert context.get("new_status") == "in_progress"
