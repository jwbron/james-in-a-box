"""
Text utilities for jib.

Provides common text processing functions used across the codebase.

Usage:
    from text_utils import chunk_message, parse_yaml_frontmatter

    # Split long text into chunks
    chunks = chunk_message(long_text, max_length=3000)

    # Parse YAML frontmatter from markdown
    metadata, content = parse_yaml_frontmatter(markdown_text)
"""

from .chunking import chunk_message
from .frontmatter import parse_yaml_frontmatter

__all__ = [
    "chunk_message",
    "parse_yaml_frontmatter",
]
