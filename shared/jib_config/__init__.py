"""
Shared configuration utilities for jib components.

This module provides configuration loading and path utilities that are shared
between the jib launcher and the gateway sidecar.
"""

from .config import Config, get_local_repos, get_repos_config_file


__all__ = [
    "Config",
    "get_local_repos",
    "get_repos_config_file",
]
