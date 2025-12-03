"""
Container detection utilities.

This module provides utilities to detect whether code is running inside
the jib container or on the host machine.
"""

import os


def is_inside_container() -> bool:
    """
    Detect if we're running inside the jib container.

    Returns True if the JIB_CONTAINER environment variable is set,
    which is only present inside the jib container.

    This allows code to auto-detect the execution context. However,
    host-services code should ALWAYS use jib_exec - it should never
    call Claude directly, even if somehow running inside a container.
    """
    return os.environ.get("JIB_CONTAINER") == "1"
