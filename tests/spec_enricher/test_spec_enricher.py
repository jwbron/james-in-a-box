"""
Tests for the spec enricher and shared enrichment module.

Per ADR: LLM Documentation Index Strategy (Phase 3)
"""

import json

# Import from shared enrichment module
from enrichment import (
    CodeExample,
    DocReference,
    EnrichedContext,
    SpecEnricher,
    enrich_task,
)


class TestSpecEnricherInit:
    """Tests for SpecEnricher initialization."""

    def test_init_sets_project_root(self, temp_dir):
        """Test that init sets project_root correctly."""
        enricher = SpecEnricher(temp_dir)
        assert enricher.project_root == temp_dir.resolve()

    def test_init_sets_docs_paths(self, temp_dir):
        """Test that init sets docs directory paths."""
        enricher = SpecEnricher(temp_dir)
        assert enricher.docs_dir == temp_dir / "docs"
        assert enricher.generated_dir == temp_dir / "docs" / "generated"

    def test_init_loads_empty_indexes_for_missing_files(self, temp_dir):
        """Test that missing index files result in empty dicts."""
        enricher = SpecEnricher(temp_dir)
        assert enricher.codebase_index == {}
        assert enricher.patterns_index == {}


class TestExtractKeywords:
    """Tests for keyword extraction."""

    def test_extracts_slack_keyword(self, temp_dir):
        """Test that 'slack' is detected."""
        enricher = SpecEnricher(temp_dir)
        keywords = enricher.extract_keywords("Add Slack notification")
        assert "slack" in keywords
        assert "notification" in keywords

    def test_extracts_auth_keywords(self, temp_dir):
        """Test that authentication keywords are detected."""
        enricher = SpecEnricher(temp_dir)
        keywords = enricher.extract_keywords("Add JWT authentication to the API")
        assert "auth" in keywords
        assert "authentication" in keywords
        assert "jwt" in keywords
        assert "api" in keywords

    def test_extracts_testing_keyword(self, temp_dir):
        """Test that testing keywords are detected."""
        enricher = SpecEnricher(temp_dir)
        keywords = enricher.extract_keywords("Add unit tests for the service")
        assert "testing" in keywords or "test" in keywords

    def test_extracts_beads_keyword(self, temp_dir):
        """Test that beads keyword is detected."""
        enricher = SpecEnricher(temp_dir)
        keywords = enricher.extract_keywords("Update beads task tracking")
        assert "beads" in keywords

    def test_extracts_github_pr_keywords(self, temp_dir):
        """Test that GitHub and PR keywords are detected."""
        enricher = SpecEnricher(temp_dir)
        keywords = enricher.extract_keywords("Create a PR for the GitHub integration")
        assert "github" in keywords
        assert "pr" in keywords

    def test_no_keywords_for_simple_text(self, temp_dir):
        """Test that simple text without keywords returns empty list."""
        enricher = SpecEnricher(temp_dir)
        keywords = enricher.extract_keywords("Fix typo in README")
        assert keywords == []

    def test_keywords_are_sorted(self, temp_dir):
        """Test that extracted keywords are sorted."""
        enricher = SpecEnricher(temp_dir)
        keywords = enricher.extract_keywords("Slack notification and GitHub PR")
        assert keywords == sorted(keywords)


class TestDynamicDocDiscovery:
    """Tests for dynamic documentation discovery from index.md."""

    def test_parses_index_md_tables(self, temp_dir):
        """Test that markdown tables in index.md are parsed correctly."""
        # Create mock index.md with table
        (temp_dir / "docs").mkdir(parents=True)
        index_content = """# Documentation Index

## Core Documentation

| Document | Description |
|----------|-------------|
| [Slack Integration](architecture/slack-integration.md) | How Slack works |
| [Beads Guide](reference/beads.md) | Task tracking system |
"""
        (temp_dir / "docs" / "index.md").write_text(index_content)

        # Create the doc files so they're found
        (temp_dir / "docs" / "architecture").mkdir(parents=True)
        (temp_dir / "docs" / "reference").mkdir(parents=True)
        (temp_dir / "docs" / "architecture" / "slack-integration.md").touch()
        (temp_dir / "docs" / "reference" / "beads.md").touch()

        enricher = SpecEnricher(temp_dir)

        # Should find docs for slack keyword
        docs = enricher.find_relevant_docs(["slack"])
        assert len(docs) > 0
        doc_paths = [d.path for d in docs]
        assert any("slack" in p for p in doc_paths)

    def test_extracts_keywords_from_descriptions(self, temp_dir):
        """Test that keywords are extracted from doc descriptions."""
        (temp_dir / "docs").mkdir(parents=True)
        index_content = """# Documentation Index

| Document | Description |
|----------|-------------|
| [Auth Guide](setup/auth.md) | Authentication and security setup |
"""
        (temp_dir / "docs" / "index.md").write_text(index_content)
        (temp_dir / "docs" / "setup").mkdir(parents=True)
        (temp_dir / "docs" / "setup" / "auth.md").touch()

        enricher = SpecEnricher(temp_dir)

        # Should find this doc for auth keyword
        docs = enricher.find_relevant_docs(["auth", "security"])
        assert len(docs) > 0


class TestFindRelevantDocs:
    """Tests for finding relevant documentation."""

    def test_limits_docs_to_5(self, temp_dir):
        """Test that at most 5 docs are returned."""
        # Create many mock docs via index.md
        (temp_dir / "docs").mkdir(parents=True)
        index_lines = ["# Index\n\n| Doc | Desc |\n|---|---|\n"]
        for i in range(10):
            (temp_dir / "docs" / f"slack{i}.md").touch()
            index_lines.append(f"| [Slack {i}](slack{i}.md) | Slack doc {i} |\n")
        (temp_dir / "docs" / "index.md").write_text("".join(index_lines))

        enricher = SpecEnricher(temp_dir)
        docs = enricher.find_relevant_docs(["slack"])

        assert len(docs) <= 5

    def test_returns_empty_for_unknown_keyword(self, temp_dir):
        """Test that unknown keywords return no docs."""
        enricher = SpecEnricher(temp_dir)
        docs = enricher.find_relevant_docs(["xyz123unknownkeyword"])
        assert docs == []


class TestFindCodeExamples:
    """Tests for finding code examples."""

    def test_finds_examples_from_patterns_json(self, temp_dir):
        """Test that examples are found from patterns.json."""
        # Create mock patterns.json
        (temp_dir / "docs" / "generated").mkdir(parents=True)
        patterns_data = {
            "patterns": {
                "notification": {
                    "description": "Notification system",
                    "examples": [
                        "src/notifier.py:10",
                        "src/alerts.py:20",
                    ],
                }
            }
        }
        (temp_dir / "docs" / "generated" / "patterns.json").write_text(json.dumps(patterns_data))

        enricher = SpecEnricher(temp_dir)
        examples = enricher.find_code_examples(["notification"])

        assert len(examples) > 0
        assert any("notifier.py" in ex.path for ex in examples)

    def test_returns_empty_for_unknown_keyword(self, temp_dir):
        """Test that unknown keywords return no examples."""
        enricher = SpecEnricher(temp_dir)
        examples = enricher.find_code_examples(["xyz123"])
        assert examples == []

    def test_limits_examples_to_5(self, temp_dir):
        """Test that at most 5 examples are returned."""
        # Create mock patterns.json with many examples
        (temp_dir / "docs" / "generated").mkdir(parents=True)
        patterns_data = {
            "patterns": {
                "notification": {
                    "description": "Notification system",
                    "examples": [f"src/file{i}.py:{i}" for i in range(10)],
                }
            }
        }
        (temp_dir / "docs" / "generated" / "patterns.json").write_text(json.dumps(patterns_data))

        enricher = SpecEnricher(temp_dir)
        examples = enricher.find_code_examples(["notification"])

        assert len(examples) <= 5


class TestFindRelevantPatterns:
    """Tests for finding relevant patterns."""

    def test_finds_matching_patterns(self, temp_dir):
        """Test that patterns matching keywords are found."""
        (temp_dir / "docs" / "generated").mkdir(parents=True)
        patterns_data = {
            "patterns": {
                "notification": {"description": "Notification system", "examples": []},
                "sync": {"description": "Synchronization", "examples": []},
            }
        }
        (temp_dir / "docs" / "generated" / "patterns.json").write_text(json.dumps(patterns_data))

        enricher = SpecEnricher(temp_dir)
        patterns = enricher.find_relevant_patterns(["notification"])

        assert "notification" in patterns

    def test_returns_empty_for_unknown_keyword(self, temp_dir):
        """Test that unknown keywords return no patterns."""
        enricher = SpecEnricher(temp_dir)
        patterns = enricher.find_relevant_patterns(["xyz123"])
        assert patterns == []


class TestEnrich:
    """Tests for the main enrich method."""

    def test_enrich_returns_context(self, temp_dir):
        """Test that enrich returns an EnrichedContext."""
        enricher = SpecEnricher(temp_dir)
        result = enricher.enrich("Add Slack notification")
        assert isinstance(result, EnrichedContext)

    def test_enrich_includes_keywords(self, temp_dir):
        """Test that enriched context includes matched keywords."""
        enricher = SpecEnricher(temp_dir)
        result = enricher.enrich("Add Slack notification")
        assert "slack" in result.keywords_matched
        assert "notification" in result.keywords_matched

    def test_enrich_empty_for_simple_text(self, temp_dir):
        """Test that simple text has empty context."""
        enricher = SpecEnricher(temp_dir)
        result = enricher.enrich("Fix typo")
        assert result.keywords_matched == []
        assert result.documentation == []


class TestEnrichTaskFunction:
    """Tests for the convenience enrich_task function."""

    def test_returns_markdown_string(self, temp_dir):
        """Test that enrich_task returns markdown."""
        result = enrich_task("Add Slack notification", temp_dir)
        assert isinstance(result, str)
        # Should have markdown formatting
        if result:  # May be empty if no docs found
            assert "##" in result or "*" in result

    def test_returns_empty_for_no_keywords(self, temp_dir):
        """Test that simple text returns empty string."""
        result = enrich_task("Fix typo", temp_dir)
        assert result == ""


class TestFormatting:
    """Tests for output formatting."""

    def test_format_yaml_includes_context(self, temp_dir):
        """Test that YAML format includes context key."""
        enricher = SpecEnricher(temp_dir)
        context = EnrichedContext(
            documentation=[DocReference("docs/test.md", "Test doc", 1.0, "Read this")],
            examples=[],
            patterns=[],
            keywords_matched=["test"],
        )
        yaml_output = enricher.format_yaml(context)
        assert "context:" in yaml_output
        assert "documentation:" in yaml_output

    def test_format_markdown_includes_header(self, temp_dir):
        """Test that Markdown format includes header."""
        enricher = SpecEnricher(temp_dir)
        context = EnrichedContext(
            documentation=[DocReference("docs/test.md", "Test doc", 1.0, "Read this")],
            examples=[],
            patterns=[],
            keywords_matched=["test"],
        )
        md_output = enricher.format_markdown(context)
        assert "## Relevant Documentation Context" in md_output

    def test_format_markdown_empty_for_no_keywords(self, temp_dir):
        """Test that Markdown format is empty when no keywords matched."""
        enricher = SpecEnricher(temp_dir)
        context = EnrichedContext(
            documentation=[],
            examples=[],
            patterns=[],
            keywords_matched=[],
        )
        md_output = enricher.format_markdown(context)
        assert md_output == ""

    def test_format_json_is_valid(self, temp_dir):
        """Test that JSON format is valid JSON."""
        enricher = SpecEnricher(temp_dir)
        context = EnrichedContext(
            documentation=[DocReference("docs/test.md", "Test doc", 1.0, "Read this")],
            examples=[],
            patterns=[],
            keywords_matched=["test"],
        )
        json_output = enricher.format_json(context)
        # Should parse without error
        parsed = json.loads(json_output)
        assert "context" in parsed


class TestDataclasses:
    """Tests for dataclass structures."""

    def test_doc_reference_fields(self):
        """Test DocReference has expected fields."""
        ref = DocReference(
            path="docs/test.md",
            description="Test doc",
            relevance_score=1.0,
            instruction="Read this",
        )
        assert ref.path == "docs/test.md"
        assert ref.description == "Test doc"
        assert ref.relevance_score == 1.0
        assert ref.instruction == "Read this"

    def test_code_example_fields(self):
        """Test CodeExample has expected fields."""
        ex = CodeExample(
            path="src/test.py",
            line=42,
            pattern="test_pattern",
            description="Test example",
            instruction="Reference this",
        )
        assert ex.path == "src/test.py"
        assert ex.line == 42
        assert ex.pattern == "test_pattern"

    def test_enriched_context_default_empty_lists(self):
        """Test EnrichedContext has empty defaults."""
        ctx = EnrichedContext()
        assert ctx.documentation == []
        assert ctx.examples == []
        assert ctx.patterns == []
        assert ctx.keywords_matched == []
