"""
Container detection utilities.

This module provides utilities to detect whether code is running inside
the jib container or on the host machine.
"""


def is_inside_container() -> bool:
    """
    Detect if we're running inside the jib container.

    Returns True if Claude CLI is available (only inside container).
    This allows code to auto-detect the execution context and choose
    between direct Claude calls (inside container) or jib_exec (from host).
    """
    try:
        from claude import is_claude_available

        return is_claude_available()
    except ImportError:
        return False
