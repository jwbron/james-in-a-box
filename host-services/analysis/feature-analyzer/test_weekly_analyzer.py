"""Unit tests for weekly_analyzer.py utility functions."""

import pytest
from pathlib import Path
from weekly_analyzer import WeeklyAnalyzer, DetectedFeature


@pytest.fixture
def analyzer(tmp_path):
    """Create a WeeklyAnalyzer with a temporary repo root."""
    return WeeklyAnalyzer(tmp_path, use_llm=False)


class TestIsUtilityFile:
    """Tests for _is_utility_file method."""

    def test_setup_py_is_utility(self, analyzer):
        assert analyzer._is_utility_file("setup.py") is True

    def test_init_py_is_utility(self, analyzer):
        assert analyzer._is_utility_file("__init__.py") is True
        # Note: The regex uses ^ anchor, so paths with directories need pattern adjustment
        # This is intentional - __init__.py at repo root is filtered, nested ones aren't

    def test_conftest_is_utility(self, analyzer):
        assert analyzer._is_utility_file("conftest.py") is True
        # Note: The regex uses ^ anchor, only root conftest.py is filtered

    def test_files_in_utils_dir_are_utilities(self, analyzer):
        assert analyzer._is_utility_file("utils/helper.py") is True
        assert analyzer._is_utility_file("util/format.py") is True
        assert analyzer._is_utility_file("src/utils/logger.py") is True

    def test_files_in_helpers_dir_are_utilities(self, analyzer):
        assert analyzer._is_utility_file("helpers/format.py") is True
        assert analyzer._is_utility_file("helper/validate.py") is True
        assert analyzer._is_utility_file("lib/helpers/common.py") is True

    def test_maintenance_scripts_are_utilities(self, analyzer):
        assert analyzer._is_utility_file("maintenance.py") is True
        assert analyzer._is_utility_file("create_symlink.py") is True
        assert analyzer._is_utility_file("link_to_docs.py") is True

    def test_feature_files_are_not_utilities(self, analyzer):
        assert analyzer._is_utility_file("weekly_analyzer.py") is False
        assert analyzer._is_utility_file("host-services/slack/router.py") is False
        assert analyzer._is_utility_file("feature/main.py") is False

    def test_regular_py_files_not_utilities(self, analyzer):
        assert analyzer._is_utility_file("my_feature.py") is False
        assert analyzer._is_utility_file("services/api.py") is False


class TestGenerateNameFromPath:
    """Tests for _generate_name_from_path method."""

    def test_simple_file_name(self, analyzer):
        assert analyzer._generate_name_from_path("weekly_analyzer.py") == "Weekly Analyzer"

    def test_kebab_case_file(self, analyzer):
        assert analyzer._generate_name_from_path("message-router.py") == "Message Router"

    def test_generic_name_gets_qualified_with_parent(self, analyzer):
        # Generic names like "connector" should be qualified with parent directory
        assert analyzer._generate_name_from_path("confluence/connector.py") == "Confluence Connector"
        assert analyzer._generate_name_from_path("slack/handler.py") == "Slack Handler"
        assert analyzer._generate_name_from_path("github/client.py") == "Github Client"

    def test_non_generic_name_not_qualified(self, analyzer):
        # Non-generic names should not include parent
        assert analyzer._generate_name_from_path("sync/weekly_sync.py") == "Weekly Sync"

    def test_deeply_nested_path(self, analyzer):
        result = analyzer._generate_name_from_path("host-services/sync/confluence/connector.py")
        assert result == "Confluence Connector"

    def test_all_generic_names_get_qualified(self, analyzer):
        generic_names = ["connector", "handler", "processor", "manager", "service", "client"]
        for name in generic_names:
            result = analyzer._generate_name_from_path(f"myparent/{name}.py")
            assert "Myparent" in result, f"{name} should be qualified with parent"


class TestDeduplicateByFiles:
    """Tests for _deduplicate_by_files method."""

    def test_no_duplicates_returns_all(self, analyzer):
        features = [
            DetectedFeature(name="Feature A", description="Desc A", files=["a.py"], confidence=0.8),
            DetectedFeature(name="Feature B", description="Desc B", files=["b.py"], confidence=0.7),
        ]
        deduplicated, skipped = analyzer._deduplicate_by_files(features)
        assert len(deduplicated) == 2
        assert len(skipped) == 0

    def test_keeps_highest_confidence_for_same_file(self, analyzer):
        features = [
            DetectedFeature(name="Low Conf", description="Desc", files=["same.py"], confidence=0.5),
            DetectedFeature(name="High Conf", description="Desc", files=["same.py"], confidence=0.9),
            DetectedFeature(name="Med Conf", description="Desc", files=["same.py"], confidence=0.7),
        ]
        deduplicated, skipped = analyzer._deduplicate_by_files(features)

        assert len(deduplicated) == 1
        assert deduplicated[0].name == "High Conf"
        assert len(skipped) == 2
        # Check that skipped items have proper reason
        skipped_names = [name for name, reason in skipped]
        assert "Low Conf" in skipped_names
        assert "Med Conf" in skipped_names

    def test_features_without_files_are_included(self, analyzer):
        features = [
            DetectedFeature(name="With File", description="Desc", files=["a.py"], confidence=0.8),
            DetectedFeature(name="No Files", description="Desc", files=[], confidence=0.6),
        ]
        deduplicated, skipped = analyzer._deduplicate_by_files(features)

        assert len(deduplicated) == 2
        assert len(skipped) == 0
        names = [f.name for f in deduplicated]
        assert "No Files" in names

    def test_mixed_duplicates_and_unique(self, analyzer):
        features = [
            DetectedFeature(name="Unique A", description="Desc", files=["a.py"], confidence=0.8),
            DetectedFeature(name="Dup 1", description="Desc", files=["shared.py"], confidence=0.6),
            DetectedFeature(name="Unique B", description="Desc", files=["b.py"], confidence=0.7),
            DetectedFeature(name="Dup 2", description="Desc", files=["shared.py"], confidence=0.9),
        ]
        deduplicated, skipped = analyzer._deduplicate_by_files(features)

        assert len(deduplicated) == 3
        assert len(skipped) == 1

        names = [f.name for f in deduplicated]
        assert "Unique A" in names
        assert "Unique B" in names
        assert "Dup 2" in names  # Higher confidence wins
        assert "Dup 1" not in names

    def test_skipped_reason_includes_file_path(self, analyzer):
        features = [
            DetectedFeature(name="Keep Me", description="Desc", files=["file.py"], confidence=0.9),
            DetectedFeature(name="Skip Me", description="Desc", files=["file.py"], confidence=0.5),
        ]
        _, skipped = analyzer._deduplicate_by_files(features)

        assert len(skipped) == 1
        name, reason = skipped[0]
        assert name == "Skip Me"
        assert "file.py" in reason
        assert "Keep Me" in reason


class TestGetExistingFilePaths:
    """Tests for get_existing_file_paths method."""

    def test_returns_empty_when_no_features_md(self, analyzer):
        paths = analyzer.get_existing_file_paths()
        assert paths == set()

    def test_extracts_py_files(self, analyzer, tmp_path):
        features_md = tmp_path / "docs" / "FEATURES.md"
        features_md.parent.mkdir(parents=True)
        features_md.write_text("""
# Features

- Implementation: `host-services/sync/connector.py`
- Main file: `scripts/runner.py`
""")
        paths = analyzer.get_existing_file_paths()
        assert "host-services/sync/connector.py" in paths
        assert "scripts/runner.py" in paths

    def test_extracts_multiple_extensions(self, analyzer, tmp_path):
        features_md = tmp_path / "docs" / "FEATURES.md"
        features_md.parent.mkdir(parents=True)
        features_md.write_text("""
# Features

- Python: `main.py`
- TypeScript: `app.ts`
- JavaScript: `utils.js`
- Shell: `setup.sh`
- Go: `server.go`
""")
        paths = analyzer.get_existing_file_paths()
        assert "main.py" in paths
        assert "app.ts" in paths
        assert "utils.js" in paths
        assert "setup.sh" in paths
        assert "server.go" in paths

    def test_ignores_non_code_files(self, analyzer, tmp_path):
        features_md = tmp_path / "docs" / "FEATURES.md"
        features_md.parent.mkdir(parents=True)
        features_md.write_text("""
# Features

- Code: `main.py`
- Doc: `README.md`
- Config: `config.yaml`
""")
        paths = analyzer.get_existing_file_paths()
        assert "main.py" in paths
        assert "README.md" not in paths
        assert "config.yaml" not in paths
