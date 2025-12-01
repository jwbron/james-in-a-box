"""
Shared utilities for host-side services.

This module contains utilities that can ONLY be used on the host, not inside
the container. For code that needs to run Claude, use the jib_claude module
which invokes Claude via `jib --exec` into the container.
"""
