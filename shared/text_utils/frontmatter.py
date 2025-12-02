"""
YAML frontmatter parsing utilities.

Extracts YAML frontmatter from markdown files. Frontmatter is YAML content
delimited by '---' markers at the start of a file.

Example markdown with frontmatter:
    ---
    task_id: "my-task"
    thread_ts: "123456.789"
    priority: high
    ---

    # Document Title

    Body content here...
"""

import re

import yaml


def parse_yaml_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content.

    Extracts the YAML block at the start of a markdown file (between --- markers)
    and returns both the parsed metadata and the remaining content.

    Args:
        content: The full markdown content, possibly starting with frontmatter.

    Returns:
        A tuple of (metadata_dict, body_content).
        - metadata_dict: Parsed YAML as a dictionary, or empty dict if no frontmatter.
        - body_content: The content after the frontmatter, with leading whitespace stripped.

    Example:
        >>> content = '''---
        ... task_id: "task-123"
        ... priority: high
        ... ---
        ...
        ... # Title
        ...
        ... Body text here.
        ... '''
        >>> metadata, body = parse_yaml_frontmatter(content)
        >>> metadata
        {'task_id': 'task-123', 'priority': 'high'}
        >>> body.startswith('# Title')
        True

    Notes:
        - If no frontmatter is present, returns ({}, original_content)
        - Invalid YAML in frontmatter returns ({}, original_content) with a warning
        - The opening --- must be at the very start of the content
    """
    # Pattern: starts with ---, then YAML content, then ---
    # Use non-greedy match for the YAML content
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        # No frontmatter found, return empty metadata and full content
        return {}, content

    yaml_content = match.group(1)
    body_content = match.group(2)

    try:
        metadata = yaml.safe_load(yaml_content) or {}
        if not isinstance(metadata, dict):
            # YAML parsed but not as a dict (e.g., just a string or list)
            return {}, content
        return metadata, body_content.lstrip()
    except yaml.YAMLError as e:
        # Invalid YAML, return empty metadata
        print(f"Warning: Failed to parse YAML frontmatter: {e}")
        return {}, content
