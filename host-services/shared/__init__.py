"""
Shared utilities for host-side services.

This module contains utilities that run on the HOST, not inside the container.
Host services should use `jib --exec` to invoke container-side processors.

Key modules:
- jib_exec: Execute tasks via `jib --exec` pattern
- container_utils: Container detection utilities

IMPORTANT: Host-side code should NEVER directly import container modules
(like shared/claude). Always use jib --exec to run container-side code.
"""

from .container_utils import is_inside_container

__all__ = ["is_inside_container"]
