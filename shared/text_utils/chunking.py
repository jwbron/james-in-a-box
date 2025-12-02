"""
Text chunking utilities.

Splits long text into chunks that respect natural boundaries
(paragraphs, sentences, words) for use with APIs that have length limits.
"""

# Default chunk size for Slack (Slack limit is ~4000 chars, 3000 for safety)
DEFAULT_MAX_LENGTH = 3000


def chunk_message(content: str, max_length: int = DEFAULT_MAX_LENGTH) -> list[str]:
    """Split long messages into chunks that fit within length limits.

    Tries to split on natural boundaries in order of preference:
    1. Paragraph boundary (double newline)
    2. Single newline
    3. Sentence boundary (. ! ?)
    4. Word boundary (space)
    5. Hard cut at max_length

    Args:
        content: The full message content to chunk.
        max_length: Maximum characters per chunk (default 3000).

    Returns:
        List of message chunks. If the message fits in one chunk,
        returns a single-element list. Multi-chunk results include
        part indicators like "**(Part 1/3)**".

    Example:
        >>> chunks = chunk_message("Short message")
        >>> len(chunks)
        1
        >>> chunks[0]
        'Short message'

        >>> long_text = "Very long text..." * 1000
        >>> chunks = chunk_message(long_text)
        >>> chunks[0].startswith("**(Part 1/")
        True
    """
    if len(content) <= max_length:
        return [content]

    chunks = []
    remaining = content

    while remaining:
        # If remaining text fits in one chunk, we're done
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Find the best split point within max_length
        chunk = remaining[:max_length]

        # Try to split on paragraph boundary (double newline)
        split_idx = chunk.rfind("\n\n")

        # If no paragraph boundary, try single newline
        if split_idx == -1:
            split_idx = chunk.rfind("\n")

        # If no newline, try sentence boundary
        if split_idx == -1:
            split_idx = max(
                chunk.rfind(". "),
                chunk.rfind("! "),
                chunk.rfind("? "),
            )
            if split_idx != -1:
                split_idx += 1  # Include the punctuation

        # If no natural boundary, split at word boundary
        if split_idx == -1:
            split_idx = chunk.rfind(" ")

        # If still no good split point, just cut at max_length
        if split_idx == -1:
            split_idx = max_length

        # Add this chunk
        chunks.append(remaining[:split_idx].strip())
        remaining = remaining[split_idx:].strip()

    # Add chunk indicators if we split the message
    if len(chunks) > 1:
        for i, chunk in enumerate(chunks):
            chunks[i] = f"**(Part {i + 1}/{len(chunks)})**\n\n{chunk}"

    return chunks
